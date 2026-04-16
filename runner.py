# -*- coding: utf-8 -*-
"""
runner.py — Execute the LOOM pipeline via subprocess.PIPE chains.
All flags verified against actual --help output from the built binaries.
"""

import os
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .binary_resolver import get_loom_binaries


@dataclass
class PipelineConfig:
    # Input
    input_geojson: str = ""
    gtfs_zip_path: str = ""
    transport_mode: str = "all"
    gtfs_prune_threshold: Optional[float] = None   # -p

    # topo
    include_topo: bool = True
    topo_max_aggr_dist: Optional[float] = None     # -d (default 50)
    topo_smooth: bool = False                       # --smooth (flag only, no value)
    topo_random_colors: bool = False                # --random-colors
    topo_no_infer_restrs: bool = False             # --no-infer-restrs
    topo_max_comp_dist: Optional[float] = None     # --max-comp-dist
    topo_write_stats: bool = False                 # --write-stats
    topo_write_components: bool = False            # --write-components

    # loom
    optim_method: str = "comb-no-ilp"             # -m (default is comb-no-ilp)
    loom_no_untangle: bool = False                 # --no-untangle
    loom_no_prune: bool = False                    # --no-prune
    loom_same_seg_cross_pen: Optional[float] = None   # --same-seg-cross-pen (default 4)
    loom_diff_seg_cross_pen: Optional[float] = None   # --diff-seg-cross-pen (default 1)
    loom_in_stat_cross_pen_same: Optional[float] = None  # --in-stat-cross-pen-same-seg (default 12)
    loom_in_stat_cross_pen_diff: Optional[float] = None  # --in-stat-cross-pen-diff-seg (default 3)
    loom_sep_pen: Optional[float] = None           # --sep-pen (default 3)
    loom_in_stat_sep_pen: Optional[float] = None   # --in-stat-sep-pen (default 9)
    loom_ilp_solver: str = "auto"                  # --ilp-solver
    loom_ilp_time_limit: Optional[int] = None      # --ilp-time-limit (-1 = infinite)
    loom_ilp_num_threads: Optional[int] = None     # --ilp-num-threads

    # octi
    schematic: bool = False
    base_graph: str = "octilinear"                 # -base-graph
    grid_size: Optional[str] = None               # -g (e.g. "120%" or "80")
    octi_optim_mode: str = "heur"                  # -m heur | ilp
    octi_geo_pen: Optional[float] = None           # --geo-pen
    octi_diag_pen: Optional[float] = None          # --diag-pen
    octi_vert_pen: Optional[float] = None          # --vert-pen
    octi_hori_pen: Optional[float] = None          # --hori-pen
    octi_pen_90: Optional[float] = None            # --pen-90 (default 1.5)
    octi_pen_45: Optional[float] = None            # --pen-45 (default 2)
    octi_pen_135: Optional[float] = None           # --pen-135 (default 1)
    octi_pen_180: Optional[float] = None           # --pen-180 (default 0)
    octi_nd_move_pen: Optional[float] = None       # --nd-move-pen (default 0.5)
    octi_density_pen: Optional[float] = None       # --density-pen (default 10)
    octi_ilp_time_limit: Optional[int] = None      # --ilp-time-limit (default 60)
    octi_write_stats: bool = False                 # --write-stats

    # transitmap
    show_labels: bool = True                       # -l
    render_engine: str = "svg"                     # --render-engine
    mvt_path: str = ""                             # --mvt-path
    mvt_zoom: str = "14"                           # -z
    line_width: Optional[float] = None             # --line-width (default 20)
    line_spacing: Optional[float] = None           # --line-spacing (default 10)
    outline_width: Optional[float] = None          # --outline-width (default 1)
    line_label_textsize: Optional[float] = None    # --line-label-textsize (default 40)
    station_label_textsize: Optional[float] = None # --station-label-textsize (default 60)
    no_deg2_labels: bool = False                   # --no-deg2-labels
    render_dir_markers: bool = False               # --render-dir-markers
    smoothing: Optional[float] = None              # --smoothing (default 1)
    random_colors: bool = False                    # --random-colors
    tight_stations: bool = False                   # --tight-stations
    no_render_stations: bool = False               # --no-render-stations
    padding: Optional[float] = None                # --padding (-1 = auto)


@dataclass
class PipelineResult:
    success: bool = False
    cancelled: bool = False
    svg_output: str = ""
    geojson_intermediate: str = ""
    mvt_path: str = ""
    errors: Dict[str, str] = field(default_factory=dict)
    warnings: Dict[str, str] = field(default_factory=dict)


ProgressCallback = Callable[[int, str], None]


class PipelineRunner:
    def __init__(self):
        self._lock      = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._cancelled = False

    def cancel(self):
        with self._lock:
            self._cancelled = True
            if self._proc:
                try:
                    self._proc.kill()
                except Exception:
                    pass

    def _is_cancelled(self):
        with self._lock:
            return self._cancelled

    def _run_stage(self, cmd, input_data, stage_name, result, capture_stdout=True):
        if self._is_cancelled():
            result.cancelled = True
            return None

        with self._lock:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

        stdout, stderr = self._proc.communicate(input=input_data)
        returncode = self._proc.returncode

        with self._lock:
            self._proc = None

        if self._is_cancelled():
            result.cancelled = True
            return None

        if stderr:
            decoded = stderr.decode("utf-8", errors="replace")
            # Only store as warning if exit was clean
            if returncode == 0:
                result.warnings[stage_name] = decoded
            else:
                result.errors[stage_name] = decoded
                return None

        if returncode != 0:
            result.errors[stage_name] = f"exited with code {returncode}"
            return None

        return stdout if capture_stdout else b""

    def run(self, cfg: PipelineConfig, progress_cb=None) -> PipelineResult:
        result = PipelineResult()

        def _p(pct, label):
            if progress_cb:
                progress_cb(pct, label)

        try:
            bins = get_loom_binaries()
        except RuntimeError as exc:
            result.errors["binary_resolver"] = str(exc)
            return result

        data: bytes = cfg.input_geojson.encode("utf-8")

        # ------------------------------------------------------------------
        # Stage 0: gtfs2graph
        # ------------------------------------------------------------------
        if cfg.gtfs_zip_path:
            _p(5, "Converting GTFS → GeoJSON line graph…")
            cmd = [bins["gtfs2graph"], "-m", cfg.transport_mode, cfg.gtfs_zip_path]
            if cfg.gtfs_prune_threshold is not None:
                cmd += ["-p", str(cfg.gtfs_prune_threshold)]
            out = self._run_stage(cmd, b"", "gtfs2graph", result)
            if out is None:
                return result
            data = out

        # ------------------------------------------------------------------
        # Stage 1: topo
        # ------------------------------------------------------------------
        if cfg.include_topo:
            _p(20, "Resolving topology…")
            cmd = [bins["topo"]]
            if cfg.topo_max_aggr_dist is not None:
                cmd += ["-d", str(cfg.topo_max_aggr_dist)]
            if cfg.topo_smooth:
                cmd.append("--smooth")
            if cfg.topo_random_colors:
                cmd.append("--random-colors")
            if cfg.topo_no_infer_restrs:
                cmd.append("--no-infer-restrs")
            if cfg.topo_max_comp_dist is not None:
                cmd += ["--max-comp-dist", str(cfg.topo_max_comp_dist)]
            if cfg.topo_write_stats:
                cmd.append("--write-stats")
            if cfg.topo_write_components:
                cmd.append("--write-components")
            out = self._run_stage(cmd, data, "topo", result)
            if out is None:
                return result
            if not out.strip():
                result.errors["topo"] = "topo produced empty output — check warnings for details."
                return result
            data = out

        # ------------------------------------------------------------------
        # Stage 2: loom
        # ------------------------------------------------------------------
        _p(40, f"Optimising line orderings ({cfg.optim_method})…")
        cmd = [bins["loom"], "-m", cfg.optim_method]
        if cfg.loom_no_untangle:
            cmd.append("--no-untangle")
        if cfg.loom_no_prune:
            cmd.append("--no-prune")
        if cfg.loom_same_seg_cross_pen is not None:
            cmd += ["--same-seg-cross-pen", str(cfg.loom_same_seg_cross_pen)]
        if cfg.loom_diff_seg_cross_pen is not None:
            cmd += ["--diff-seg-cross-pen", str(cfg.loom_diff_seg_cross_pen)]
        if cfg.loom_in_stat_cross_pen_same is not None:
            cmd += ["--in-stat-cross-pen-same-seg", str(cfg.loom_in_stat_cross_pen_same)]
        if cfg.loom_in_stat_cross_pen_diff is not None:
            cmd += ["--in-stat-cross-pen-diff-seg", str(cfg.loom_in_stat_cross_pen_diff)]
        if cfg.loom_sep_pen is not None:
            cmd += ["--sep-pen", str(cfg.loom_sep_pen)]
        if cfg.loom_in_stat_sep_pen is not None:
            cmd += ["--in-stat-sep-pen", str(cfg.loom_in_stat_sep_pen)]
        if cfg.loom_ilp_solver != "auto":
            cmd += ["--ilp-solver", cfg.loom_ilp_solver]
        if cfg.loom_ilp_time_limit is not None:
            cmd += ["--ilp-time-limit", str(cfg.loom_ilp_time_limit)]
        if cfg.loom_ilp_num_threads is not None:
            cmd += ["--ilp-num-threads", str(cfg.loom_ilp_num_threads)]

        out = self._run_stage(cmd, data, "loom", result)
        if out is None:
            return result
        if not out.strip():
            result.errors["loom"] = "loom produced empty output — check warnings for details."
            return result
        data = out
        result.geojson_intermediate = data.decode("utf-8", errors="replace")

        # ------------------------------------------------------------------
        # Stage 3: octi
        # ------------------------------------------------------------------
        if cfg.schematic:
            _p(60, f"Schematising ({cfg.base_graph})…")
            cmd = [bins["octi"], "-b", cfg.base_graph, "-m", cfg.octi_optim_mode]
            if cfg.grid_size:
                cmd += ["-g", cfg.grid_size]
            if cfg.octi_geo_pen is not None:
                cmd += ["--geo-pen", str(cfg.octi_geo_pen)]
            if cfg.octi_diag_pen is not None:
                cmd += ["--diag-pen", str(cfg.octi_diag_pen)]
            if cfg.octi_vert_pen is not None:
                cmd += ["--vert-pen", str(cfg.octi_vert_pen)]
            if cfg.octi_hori_pen is not None:
                cmd += ["--hori-pen", str(cfg.octi_hori_pen)]
            if cfg.octi_pen_90 is not None:
                cmd += ["--pen-90", str(cfg.octi_pen_90)]
            if cfg.octi_pen_45 is not None:
                cmd += ["--pen-45", str(cfg.octi_pen_45)]
            if cfg.octi_pen_135 is not None:
                cmd += ["--pen-135", str(cfg.octi_pen_135)]
            if cfg.octi_pen_180 is not None:
                cmd += ["--pen-180", str(cfg.octi_pen_180)]
            if cfg.octi_nd_move_pen is not None:
                cmd += ["--nd-move-pen", str(cfg.octi_nd_move_pen)]
            if cfg.octi_density_pen is not None:
                cmd += ["--density-pen", str(cfg.octi_density_pen)]
            if cfg.octi_ilp_time_limit is not None:
                cmd += ["--ilp-time-limit", str(cfg.octi_ilp_time_limit)]
            if cfg.octi_write_stats:
                cmd.append("--write-stats")
            out = self._run_stage(cmd, data, "octi", result)
            if out is None:
                return result
            if not out.strip():
                result.errors["octi"] = "octi produced empty output — check warnings for details."
                return result
            data = out

        # ------------------------------------------------------------------
        # Stage 4: transitmap
        # ------------------------------------------------------------------
        _p(80, "Rendering transit map…")
        cmd = [bins["transitmap"], "--render-engine", cfg.render_engine]
        if cfg.show_labels:
            cmd.append("-l")
        if cfg.line_width is not None:
            cmd += ["--line-width", str(cfg.line_width)]
        if cfg.line_spacing is not None:
            cmd += ["--line-spacing", str(cfg.line_spacing)]
        if cfg.outline_width is not None:
            cmd += ["--outline-width", str(cfg.outline_width)]
        if cfg.line_label_textsize is not None:
            cmd += ["--line-label-textsize", str(cfg.line_label_textsize)]
        if cfg.station_label_textsize is not None:
            cmd += ["--station-label-textsize", str(cfg.station_label_textsize)]
        if cfg.no_deg2_labels:
            cmd.append("--no-deg2-labels")
        if cfg.render_dir_markers:
            cmd.append("--render-dir-markers")
        if cfg.smoothing is not None:
            cmd += ["--smoothing", str(cfg.smoothing)]
        if cfg.random_colors:
            cmd.append("--random-colors")
        if cfg.tight_stations:
            cmd.append("--tight-stations")
        if cfg.no_render_stations:
            cmd.append("--no-render-stations")
        if cfg.padding is not None:
            cmd += ["--padding", str(cfg.padding)]
        if cfg.render_engine == "mvt":
            if not cfg.mvt_path:
                result.errors["transitmap"] = "MVT output requires --mvt-path to be set."
                return result
            os.makedirs(cfg.mvt_path, exist_ok=True)
            cmd += ["--mvt-path", cfg.mvt_path, "-z", cfg.mvt_zoom]

        out = self._run_stage(cmd, data, "transitmap", result,
                              capture_stdout=(cfg.render_engine == "svg"))
        if out is None:
            return result

        if cfg.render_engine == "svg":
            result.svg_output = out.decode("utf-8", errors="replace")
        else:
            result.mvt_path = cfg.mvt_path

        _p(100, "Done.")
        result.success = True
        return result


def run_pipeline(cfg, progress_cb=None):
    return PipelineRunner().run(cfg, progress_cb)
