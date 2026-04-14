# -*- coding: utf-8 -*-
"""
runner.py — Execute the LOOM pipeline via subprocess.PIPE chains.

Design notes
------------
* Never uses shell=True — avoids all cmd.exe / PowerShell redirection quirks
  and works identically on Windows, macOS, and Linux.
* Each stage's stdout is fed directly as the next stage's stdin — no temp files.
* Progress is reported via a callback so the caller (QgsTask) can update the UI.
* Errors from any stage are captured and surfaced with the stage name.
"""

import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from .binary_resolver import get_loom_binaries


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    """All user-tunable parameters collected from the dialog."""

    # Input
    input_geojson: str = ""          # raw GeoJSON string (from layer or file)
    gtfs_zip_path: str = ""          # path to GTFS zip (alternative to GeoJSON)
    transport_mode: str = "tram"     # gtfs2graph -m flag

    # Schematisation
    schematic: bool = False          # run octi stage?
    base_graph: str = "octilinear"   # octi -b flag  (octilinear | orthoradial)

    # Rendering
    show_labels: bool = True         # transitmap -l
    line_width: Optional[float] = None    # --line-width
    line_spacing: Optional[float] = None  # --line-spacing
    outline_width: Optional[float] = None # --outline-width
    render_engine: str = "svg"       # svg | mvt

    # Solver
    ilp_solver: str = "auto"         # auto | glpk | cbc

    # Internal
    include_topo: bool = True        # run topo stage (usually True)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    success: bool = False
    svg_output: str = ""
    geojson_intermediate: str = ""   # output after loom stage (before octi/render)
    errors: Dict[str, str] = field(default_factory=dict)  # stage -> stderr text
    warnings: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Progress callback type alias
# ---------------------------------------------------------------------------
ProgressCallback = Callable[[int, str], None]   # (percent 0-100, stage label)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pipeline(
    cfg: PipelineConfig,
    progress_cb: Optional[ProgressCallback] = None,
) -> PipelineResult:
    """
    Execute the full LOOM pipeline and return a PipelineResult.

    Pipeline stages (all optional except loom + transitmap):
        [gtfs2graph]  → topo  → loom  → [octi]  → transitmap

    Parameters
    ----------
    cfg          : PipelineConfig populated from the dialog
    progress_cb  : optional callable(percent, label) for UI progress updates
    """
    result = PipelineResult()

    def _progress(pct: int, label: str) -> None:
        if progress_cb:
            progress_cb(pct, label)

    try:
        bins = get_loom_binaries()
    except RuntimeError as exc:
        result.errors["binary_resolver"] = str(exc)
        return result

    data: bytes = cfg.input_geojson.encode("utf-8")

    # ------------------------------------------------------------------
    # Stage 0: gtfs2graph  (only when GTFS zip provided instead of GeoJSON)
    # ------------------------------------------------------------------
    if cfg.gtfs_zip_path:
        _progress(5, "Converting GTFS → GeoJSON line graph…")
        cmd = [bins["gtfs2graph"], "-m", cfg.transport_mode, cfg.gtfs_zip_path]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            result.errors["gtfs2graph"] = proc.stderr.decode("utf-8", errors="replace")
            return result
        if proc.stderr:
            result.warnings["gtfs2graph"] = proc.stderr.decode("utf-8", errors="replace")
        data = proc.stdout

    # ------------------------------------------------------------------
    # Stage 1: topo  (resolve overlapping edges)
    # ------------------------------------------------------------------
    if cfg.include_topo:
        _progress(20, "Resolving topology…")
        proc = subprocess.run([bins["topo"]], input=data, capture_output=True)
        if proc.returncode != 0:
            result.errors["topo"] = proc.stderr.decode("utf-8", errors="replace")
            return result
        if proc.stderr:
            result.warnings["topo"] = proc.stderr.decode("utf-8", errors="replace")
        data = proc.stdout

    # ------------------------------------------------------------------
    # Stage 2: loom  (optimise line orderings)
    # ------------------------------------------------------------------
    _progress(40, "Optimising line orderings (loom)…")
    loom_cmd = [bins["loom"]]
    if cfg.ilp_solver != "auto":
        loom_cmd += ["--ilp-solver", cfg.ilp_solver]

    proc = subprocess.run(loom_cmd, input=data, capture_output=True)
    if proc.returncode != 0:
        result.errors["loom"] = proc.stderr.decode("utf-8", errors="replace")
        return result
    if proc.stderr:
        result.warnings["loom"] = proc.stderr.decode("utf-8", errors="replace")
    data = proc.stdout
    result.geojson_intermediate = data.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Stage 3: octi  (optional schematisation)
    # ------------------------------------------------------------------
    if cfg.schematic:
        _progress(60, f"Schematising ({cfg.base_graph})…")
        octi_cmd = [bins["octi"], "-b", cfg.base_graph]
        proc = subprocess.run(octi_cmd, input=data, capture_output=True)
        if proc.returncode != 0:
            result.errors["octi"] = proc.stderr.decode("utf-8", errors="replace")
            return result
        if proc.stderr:
            result.warnings["octi"] = proc.stderr.decode("utf-8", errors="replace")
        data = proc.stdout

    # ------------------------------------------------------------------
    # Stage 4: transitmap  (render to SVG / MVT)
    # ------------------------------------------------------------------
    _progress(80, "Rendering transit map…")
    tm_cmd = [bins["transitmap"]]

    if cfg.show_labels:
        tm_cmd.append("-l")
    if cfg.line_width is not None:
        tm_cmd += ["--line-width", str(cfg.line_width)]
    if cfg.line_spacing is not None:
        tm_cmd += ["--line-spacing", str(cfg.line_spacing)]
    if cfg.outline_width is not None:
        tm_cmd += ["--outline-width", str(cfg.outline_width)]
    if cfg.render_engine == "mvt":
        tm_cmd += ["--render-engine", "mvt"]

    proc = subprocess.run(tm_cmd, input=data, capture_output=True)
    if proc.returncode != 0:
        result.errors["transitmap"] = proc.stderr.decode("utf-8", errors="replace")
        return result
    if proc.stderr:
        result.warnings["transitmap"] = proc.stderr.decode("utf-8", errors="replace")

    _progress(100, "Done.")
    result.svg_output = proc.stdout.decode("utf-8", errors="replace")
    result.success = True
    return result
