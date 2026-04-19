# -*- coding: utf-8 -*-
"""
dialog.py — Qt dialog for the LOOM QGIS plugin.
All flags verified against actual --help output from the built binaries.
"""

import os

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QCheckBox, QDoubleSpinBox, QSpinBox, QLineEdit,
    QPushButton, QFileDialog, QTabWidget, QWidget, QTextEdit,
    QProgressBar, QMessageBox, QFormLayout, QScrollArea,
)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtGui import QFont
from qgis.core import QgsProject, QgsVectorLayer, QgsMapLayerProxyModel

try:
    from qgis.gui import QgsMapLayerComboBox
    HAS_LAYER_COMBO = True
except ImportError:
    HAS_LAYER_COMBO = False

from .runner import PipelineConfig, PipelineResult, PipelineRunner
from .binary_resolver import check_binaries, get_platform_info


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class PipelineWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg    = cfg
        self.runner = PipelineRunner()

    def cancel(self):
        self.runner.cancel()

    def run(self):
        self.finished.emit(self.runner.run(self.cfg, self.progress.emit))


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _dspin(lo, hi, val, suffix="", special="", tip="", dec=1):
    w = QDoubleSpinBox()
    w.setRange(lo, hi); w.setValue(val); w.setDecimals(dec)
    if suffix: w.setSuffix(f" {suffix}")
    if special: w.setSpecialValueText(special)
    if tip: w.setToolTip(tip)
    return w

def _ispin(lo, hi, val, suffix="", special="", tip=""):
    w = QSpinBox()
    w.setRange(lo, hi); w.setValue(val)
    if suffix: w.setSuffix(f" {suffix}")
    if special: w.setSpecialValueText(special)
    if tip: w.setToolTip(tip)
    return w

def _scrolled(w):
    s = QScrollArea(); s.setWidgetResizable(True); s.setWidget(w)
    s.setFrameShape(QScrollArea.NoFrame); return s

def _cb(label, tip=""):
    w = QCheckBox(label)
    if tip: w.setToolTip(tip)
    return w


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class LoomDialog(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface  = iface
        self.worker = None
        self.setWindowTitle("LOOM Transit Map Generator")
        self.setMinimumWidth(640); self.setMinimumHeight(700)
        self._build_ui()
        self._check_binaries_status()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setSpacing(8)

        title = QLabel("LOOM Transit Map Generator")
        title.setAlignment(Qt.AlignCenter)
        f = title.font(); f.setPointSize(14); f.setBold(True); title.setFont(f)
        sub = QLabel("Powered by LOOM · University of Freiburg · Windows port by Transport for Cairo")
        sub.setAlignment(Qt.AlignCenter); sub.setStyleSheet("color: gray; font-size: 10px;")
        root.addWidget(title); root.addWidget(sub)

        tabs = QTabWidget()
        tabs.addTab(self._tab_input(),      "Input")
        tabs.addTab(self._tab_topo(),       "Topo")
        tabs.addTab(self._tab_loom(),       "Loom")
        tabs.addTab(self._tab_octi(),       "Octi")
        tabs.addTab(self._tab_render(),     "Render")
        tabs.addTab(self._tab_output(),     "Output")
        tabs.addTab(self._tab_diag(),       "Diagnostics")
        root.addWidget(tabs)

        self.progress_bar   = QProgressBar(); self.progress_bar.setVisible(False)
        self.progress_label = QLabel(""); self.progress_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.progress_bar); root.addWidget(self.progress_label)

        row = QHBoxLayout()
        self.run_btn    = QPushButton("Run Pipeline"); self.run_btn.setDefault(True)
        self.run_btn.clicked.connect(self._on_run)
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.setVisible(False)
        self.cancel_btn.setStyleSheet("color: red;"); self.cancel_btn.clicked.connect(self._on_cancel)
        self.close_btn  = QPushButton("Close"); self.close_btn.clicked.connect(self.reject)
        row.addWidget(self.run_btn); row.addWidget(self.cancel_btn)
        row.addStretch(); row.addWidget(self.close_btn)
        root.addLayout(row)

    # ---- Input -----------------------------------------------------------

    def _tab_input(self):
        w = QWidget(); vb = QVBoxLayout(w)
        g = QGroupBox("Input Source"); f = QFormLayout(g)

        if HAS_LAYER_COMBO:
            self.layer_combo = QgsMapLayerComboBox()
            self.layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer)
            self.layer_combo.setAllowEmptyLayer(True)
            f.addRow("QGIS layer:", self.layer_combo)
        else:
            self.layer_combo = None

        self.geojson_path = QLineEdit(); self.geojson_path.setPlaceholderText("Or select a GeoJSON file…")
        r = QHBoxLayout(); r.addWidget(self.geojson_path)
        b = QPushButton("Browse"); b.clicked.connect(self._browse_geojson); r.addWidget(b)
        f.addRow("GeoJSON file:", r)

        self.gtfs_path = QLineEdit(); self.gtfs_path.setPlaceholderText("Or select a GTFS .zip file…")
        r2 = QHBoxLayout(); r2.addWidget(self.gtfs_path)
        b2 = QPushButton("Browse"); b2.clicked.connect(self._browse_gtfs); r2.addWidget(b2)
        f.addRow("GTFS zip:", r2)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["all", "tram", "bus", "rail", "subway", "ferry",
                                   "cablecar", "gondola", "funicular", "coach", "monorail", "trolleybus"])
        f.addRow("Transport mode:", self.mode_combo)

        self.gtfs_prune = _dspin(0, 1, 0, "", "off", "Prune lines occurring less than this fraction (0–1).", dec=2)
        f.addRow("Prune threshold:", self.gtfs_prune)

        vb.addWidget(g); vb.addStretch(); return w

    # ---- Topo ------------------------------------------------------------

    def _tab_topo(self):
        inner = QWidget(); vb = QVBoxLayout(inner)
        g = QGroupBox("Topo Options"); f = QFormLayout(g)

        self.use_topo = _cb("Run topo stage (recommended — resolves overlapping edges)")
        self.use_topo.setChecked(True); f.addRow("", self.use_topo)

        self.topo_max_aggr_dist = _dspin(0, 500, 0, "m", "default 50 m",
            "Max distance between segments to merge into one corridor.")
        f.addRow("Max aggr. dist:", self.topo_max_aggr_dist)

        self.topo_max_comp_dist = _dspin(0, 50000, 0, "m", "default 10000 m",
            "Max distance between nodes in a connected component.")
        f.addRow("Max comp. dist:", self.topo_max_comp_dist)

        self.topo_smooth          = _cb("--smooth (smooth output edge geometries)")
        self.topo_random_colors   = _cb("--random-colors (assign random colors to routes missing hex codes)")
        self.topo_no_infer_restrs = _cb("--no-infer-restrs (disable turn restriction inference — use if routes are cut off)")
        self.topo_write_stats     = _cb("--write-stats")
        self.topo_write_components = _cb("--write-components (write component ID to edge attributes)")
        for w in [self.topo_smooth, self.topo_random_colors, self.topo_no_infer_restrs,
                  self.topo_write_stats, self.topo_write_components]:
            f.addRow("", w)

        vb.addWidget(g); vb.addStretch(); return _scrolled(inner)

    # ---- Loom ------------------------------------------------------------

    def _tab_loom(self):
        inner = QWidget(); vb = QVBoxLayout(inner)

        g = QGroupBox("Line Ordering"); f = QFormLayout(g)
        self.optim_method = QComboBox()
        self.optim_method.addItems(["comb-no-ilp", "comb", "ilp", "ilp-naive",
                                     "greedy", "greedy-lookahead", "hillc", "hillc-random",
                                     "anneal", "anneal-random", "exhaust", "null"])
        self.optim_method.setCurrentText("comb-no-ilp")
        self.optim_method.setToolTip(
            "comb-no-ilp    — Default. Fast + good quality\n"
            "comb           — Best quality, uses ILP\n"
            "ilp            — Mathematically optimal, very slow\n"
            "ilp-naive      — Simpler ILP, sometimes faster\n"
            "greedy         — Very fast, lower quality\n"
            "greedy-lookahead — Greedy with lookahead\n"
            "hillc / hillc-random — Hill climbing\n"
            "anneal / anneal-random — Simulated annealing\n"
            "exhaust        — Tiny networks only!\n"
            "null           — No optimisation"
        )
        f.addRow("Optim method:", self.optim_method)

        self.loom_no_untangle = _cb("--no-untangle"); f.addRow("", self.loom_no_untangle)
        self.loom_no_prune    = _cb("--no-prune");    f.addRow("", self.loom_no_prune)
        vb.addWidget(g)

        pg = QGroupBox("Crossing & Separation Penalties (leave at 0 to use defaults)")
        pf = QFormLayout(pg)
        self.loom_same_seg_cross_pen  = _dspin(0,50,0,"","default 4",  "Same-segment crossing penalty.")
        self.loom_diff_seg_cross_pen  = _dspin(0,50,0,"","default 1",  "Different-segment crossing penalty.")
        self.loom_in_stat_cross_same  = _dspin(0,50,0,"","default 12", "Same-segment crossing at station penalty.")
        self.loom_in_stat_cross_diff  = _dspin(0,50,0,"","default 3",  "Diff-segment crossing at station penalty.")
        self.loom_sep_pen             = _dspin(0,50,0,"","default 3",  "Separation penalty.")
        self.loom_in_stat_sep_pen     = _dspin(0,50,0,"","default 9",  "Separation at station penalty.")
        pf.addRow("Same-seg cross:", self.loom_same_seg_cross_pen)
        pf.addRow("Diff-seg cross:", self.loom_diff_seg_cross_pen)
        pf.addRow("Station cross (same):", self.loom_in_stat_cross_same)
        pf.addRow("Station cross (diff):", self.loom_in_stat_cross_diff)
        pf.addRow("Sep pen:", self.loom_sep_pen)
        pf.addRow("Station sep pen:", self.loom_in_stat_sep_pen)
        vb.addWidget(pg)

        ig = QGroupBox("ILP Options (only apply to ilp / comb methods)")
        if_ = QFormLayout(ig)
        self.loom_ilp_solver     = QComboBox(); self.loom_ilp_solver.addItems(["auto", "glpk", "cbc", "gurobi"])
        self.loom_ilp_time_limit = _ispin(-1, 86400, -1, "s", "unlimited", "ILP solve time limit. -1 = unlimited.")
        self.loom_ilp_threads    = _ispin(0, 64, 0, "", "solver default", "ILP solver threads. 0 = solver default.")
        if_.addRow("ILP solver:", self.loom_ilp_solver)
        if_.addRow("Time limit:", self.loom_ilp_time_limit)
        if_.addRow("Threads:", self.loom_ilp_threads)
        vb.addWidget(ig)

        vb.addStretch(); return _scrolled(inner)

    # ---- Octi ------------------------------------------------------------

    def _tab_octi(self):
        inner = QWidget(); vb = QVBoxLayout(inner)

        g = QGroupBox("Schematisation"); f = QFormLayout(g)
        self.schematic = _cb("Run octi (schematise the map)"); f.addRow("", self.schematic)

        self.base_graph = QComboBox()
        self.base_graph.addItems(["octilinear", "ortholinear", "orthoradial", "quadtree", "octihanan"])
        self.base_graph.setToolTip(
            "octilinear  — 8-directional grid (classic metro map)\n"
            "ortholinear — Right angles only\n"
            "orthoradial — Concentric + radial\n"
            "quadtree    — Adaptive quadtree\n"
            "octihanan   — Hanan grid, minimises line length"
        )
        f.addRow("Base graph:", self.base_graph)

        self.octi_optim_mode = QComboBox(); self.octi_optim_mode.addItems(["heur", "ilp"])
        self.octi_optim_mode.setToolTip("heur = fast heuristic (default), ilp = exact but slow")
        f.addRow("Optim mode:", self.octi_optim_mode)

        self.grid_size = QLineEdit(); self.grid_size.setPlaceholderText("e.g. 120% or 80 (default 100%)")
        self.grid_size.setToolTip("Grid cell size. Percentage of avg station distance, or absolute value.")
        f.addRow("Grid size:", self.grid_size)

        self.octi_write_stats = _cb("--write-stats"); f.addRow("", self.octi_write_stats)
        vb.addWidget(g)

        pg = QGroupBox("Direction Penalties (leave at 0 to use defaults)")
        pf = QFormLayout(pg)
        self.octi_geo_pen     = _dspin(0,10,0,"","default 0",   "Geo-accuracy penalty — >0 keeps lines close to real coords.")
        self.octi_diag_pen    = _dspin(0,10,0,"","default 0.5", "Diagonal edge penalty.")
        self.octi_vert_pen    = _dspin(0,10,0,"","default 0",   "Vertical edge penalty.")
        self.octi_hori_pen    = _dspin(0,10,0,"","default 0",   "Horizontal edge penalty.")
        self.octi_density_pen = _dspin(0,50,0,"","default 10",  "Density penalty — discourages crowded areas.")
        pf.addRow("Geo pen:", self.octi_geo_pen)
        pf.addRow("Diag pen:", self.octi_diag_pen)
        pf.addRow("Vert pen:", self.octi_vert_pen)
        pf.addRow("Hori pen:", self.octi_hori_pen)
        pf.addRow("Density pen:", self.octi_density_pen)
        vb.addWidget(pg)

        ag = QGroupBox("Angle Penalties (leave at 0 to use defaults)")
        af = QFormLayout(ag)
        self.octi_pen_90  = _dspin(0,20,0,"","default 1.5", "90° bend penalty.")
        self.octi_pen_45  = _dspin(0,20,0,"","default 2",   "45° bend penalty.")
        self.octi_pen_135 = _dspin(0,20,0,"","default 1",   "135° bend penalty.")
        self.octi_pen_180 = _dspin(0,20,0,"","default 0",   "180° U-turn penalty.")
        self.octi_nd_move = _dspin(0,10,0,"","default 0.5", "Node movement penalty — discourages moving stations.")
        af.addRow("Pen 90°:",  self.octi_pen_90)
        af.addRow("Pen 45°:",  self.octi_pen_45)
        af.addRow("Pen 135°:", self.octi_pen_135)
        af.addRow("Pen 180°:", self.octi_pen_180)
        af.addRow("Nd move pen:", self.octi_nd_move)
        vb.addWidget(ag)

        ig = QGroupBox("ILP Options (only when optim mode = ilp)")
        if_ = QFormLayout(ig)
        self.octi_ilp_time_limit = _ispin(-1, 86400, 60, "s", "", "ILP time limit (default 60s). -1 = unlimited.")
        if_.addRow("Time limit:", self.octi_ilp_time_limit)
        vb.addWidget(ig)

        vb.addStretch(); return _scrolled(inner)

    # ---- Render ----------------------------------------------------------

    def _tab_render(self):
        inner = QWidget(); vb = QVBoxLayout(inner)
        g = QGroupBox("Rendering Options"); f = QFormLayout(g)

        self.render_engine = QComboBox(); self.render_engine.addItems(["svg", "mvt"])
        f.addRow("Output format:", self.render_engine)

        self.show_labels = _cb("Render labels (-l)"); self.show_labels.setChecked(True)
        f.addRow("", self.show_labels)

        self.line_width              = _dspin(0,200,0,"","default 20")
        self.line_spacing            = _dspin(0,100,0,"","default 10")
        self.outline_width           = _dspin(0,50,0,"","default 1")
        self.line_label_textsize     = _dspin(0,500,0,"","default 40")
        self.station_label_textsize  = _dspin(0,500,0,"","default 60")
        self.smoothing               = _dspin(0,20,0,"","default 1",  "Input line smoothing.")
        self.padding                 = _dspin(-1,500,-1,"","auto (-1)", "Canvas padding. -1 = auto.")
        f.addRow("Line width:",           self.line_width)
        f.addRow("Line spacing:",         self.line_spacing)
        f.addRow("Outline width:",        self.outline_width)
        f.addRow("Line label size:",      self.line_label_textsize)
        f.addRow("Station label size:",   self.station_label_textsize)
        f.addRow("Smoothing:",            self.smoothing)
        f.addRow("Padding:",              self.padding)

        self.no_deg2_labels      = _cb("--no-deg2-labels (hide labels at minor intermediate stops)")
        self.render_dir_markers  = _cb("--render-dir-markers (show direction arrows on lines)")
        self.random_colors       = _cb("--random-colors (assign random colors to uncoloured routes)")
        self.tight_stations      = _cb("--tight-stations (don't expand node fronts at stations)")
        self.no_render_stations  = _cb("--no-render-stations")
        for w in [self.no_deg2_labels, self.render_dir_markers, self.random_colors,
                  self.tight_stations, self.no_render_stations]:
            f.addRow("", w)

        vb.addWidget(g); vb.addStretch(); return _scrolled(inner)

    # ---- Output ----------------------------------------------------------

    def _tab_output(self):
        w = QWidget(); vb = QVBoxLayout(w)
        g = QGroupBox("Output"); f = QFormLayout(g)

        self.output_path = QLineEdit(); self.output_path.setPlaceholderText("SVG save path (leave blank for QGIS only)")
        r = QHBoxLayout(); r.addWidget(self.output_path)
        b = QPushButton("Browse"); b.clicked.connect(self._browse_output); r.addWidget(b)
        f.addRow("Save SVG to:", r)

        self.mvt_path = QLineEdit(); self.mvt_path.setPlaceholderText("Required when output format is MVT")
        r2 = QHBoxLayout(); r2.addWidget(self.mvt_path)
        b2 = QPushButton("Browse"); b2.clicked.connect(self._browse_mvt); r2.addWidget(b2)
        f.addRow("MVT path (--mvt-path):", r2)

        self.mvt_zoom = QLineEdit("14")
        self.mvt_zoom.setToolTip("Zoom levels for MVT tiles, e.g. '14' or '12,13,14' or '12-15'")
        f.addRow("MVT zoom (-z):", self.mvt_zoom)

        self.open_after = _cb("Open SVG in system viewer after generation")
        self.open_after.setChecked(True); f.addRow("", self.open_after)

        # Webmap
        self.webmap_enabled = _cb("Generate interactive webmap (HTML)")
        self.webmap_enabled.setToolTip(
            "Embeds the SVG in a self-contained HTML file with a MapLibre basemap,\n"
            "hover tooltips, and basemap switcher. Opens directly in any browser."
        )
        f.addRow("", self.webmap_enabled)

        self.webmap_path = QLineEdit()
        self.webmap_path.setPlaceholderText("Webmap save path (e.g. output/map.html)")
        r3 = QHBoxLayout(); r3.addWidget(self.webmap_path)
        b3 = QPushButton("Browse"); b3.clicked.connect(self._browse_webmap); r3.addWidget(b3)
        f.addRow("Webmap HTML:", r3)

        self.webmap_open = _cb("Open webmap in browser after generation")
        self.webmap_open.setChecked(True); f.addRow("", self.webmap_open)

        vb.addWidget(g)
        pg = QGroupBox("SVG Preview"); pvb = QVBoxLayout(pg)
        self.svg_preview = QTextEdit(); self.svg_preview.setReadOnly(True)
        self.svg_preview.setFont(QFont("Courier New", 9))
        self.svg_preview.setPlaceholderText("SVG output will appear here…")
        pvb.addWidget(self.svg_preview); vb.addWidget(pg)
        return w

    # ---- Diagnostics -----------------------------------------------------

    def _tab_diag(self):
        w = QWidget(); vb = QVBoxLayout(w)
        vb.addWidget(QLabel("<b>Platform:</b>"))
        vb.addWidget(QLabel(get_platform_info()))
        vb.addWidget(QLabel("<b>Binary status:</b>"))
        self.diag_text = QTextEdit(); self.diag_text.setReadOnly(True)
        self.diag_text.setFont(QFont("Courier New", 9)); vb.addWidget(self.diag_text)
        row = QHBoxLayout()
        b1 = QPushButton("Re-check"); b1.clicked.connect(self._check_binaries_status); row.addWidget(b1)
        b2 = QPushButton("Re-download binaries…"); b2.clicked.connect(self._on_redownload); row.addWidget(b2)
        vb.addLayout(row)
        vb.addWidget(QLabel("<b>Last run stderr / warnings:</b>"))
        self.error_text = QTextEdit(); self.error_text.setReadOnly(True)
        self.error_text.setFont(QFont("Courier New", 9)); vb.addWidget(self.error_text)
        return w

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_binaries_status(self):
        status = check_binaries()
        self.diag_text.setPlainText("\n".join(f"  {'✔' if ok else '✘'}  {n}" for n, ok in status.items()))

    def _browse_geojson(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select GeoJSON", "", "GeoJSON (*.geojson *.json)")
        if p: self.geojson_path.setText(p)

    def _browse_gtfs(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select GTFS zip", "", "GTFS zip (*.zip)")
        if p: self.gtfs_path.setText(p)

    def _browse_output(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save SVG", "", "SVG (*.svg);;All (*)")
        if p: self.output_path.setText(p)

    def _browse_mvt(self):
        p = QFileDialog.getExistingDirectory(self, "Select MVT output folder")
        if p: self.mvt_path.setText(p)

    def _browse_webmap(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save Webmap HTML", "", "HTML (*.html);;All (*)")
        if p: self.webmap_path.setText(p)

    def _v(self, spinbox):
        """Return spinbox value or None if at minimum (= 'use default')."""
        v = spinbox.value()
        return None if v == spinbox.minimum() else v

    def _build_config(self):
        cfg = PipelineConfig()

        gtfs = self.gtfs_path.text().strip()
        if gtfs:
            cfg.gtfs_zip_path        = gtfs
            cfg.transport_mode       = self.mode_combo.currentText()
            cfg.gtfs_prune_threshold = self._v(self.gtfs_prune)
        else:
            gj = self.geojson_path.text().strip()
            if gj and os.path.isfile(gj):
                with open(gj, "r", encoding="utf-8") as fh:
                    cfg.input_geojson = fh.read()
            elif HAS_LAYER_COMBO and self.layer_combo:
                layer = self.layer_combo.currentLayer()
                if layer:
                    cfg.input_geojson = self._layer_to_geojson(layer)

        cfg.include_topo          = self.use_topo.isChecked()
        cfg.topo_max_aggr_dist    = self._v(self.topo_max_aggr_dist)
        cfg.topo_max_comp_dist    = self._v(self.topo_max_comp_dist)
        cfg.topo_smooth           = self.topo_smooth.isChecked()
        cfg.topo_random_colors    = self.topo_random_colors.isChecked()
        cfg.topo_no_infer_restrs  = self.topo_no_infer_restrs.isChecked()
        cfg.topo_write_stats      = self.topo_write_stats.isChecked()
        cfg.topo_write_components = self.topo_write_components.isChecked()

        cfg.optim_method              = self.optim_method.currentText()
        cfg.loom_no_untangle          = self.loom_no_untangle.isChecked()
        cfg.loom_no_prune             = self.loom_no_prune.isChecked()
        cfg.loom_same_seg_cross_pen   = self._v(self.loom_same_seg_cross_pen)
        cfg.loom_diff_seg_cross_pen   = self._v(self.loom_diff_seg_cross_pen)
        cfg.loom_in_stat_cross_pen_same = self._v(self.loom_in_stat_cross_same)
        cfg.loom_in_stat_cross_pen_diff = self._v(self.loom_in_stat_cross_diff)
        cfg.loom_sep_pen              = self._v(self.loom_sep_pen)
        cfg.loom_in_stat_sep_pen      = self._v(self.loom_in_stat_sep_pen)
        cfg.loom_ilp_solver           = self.loom_ilp_solver.currentText()
        cfg.loom_ilp_time_limit       = self._v(self.loom_ilp_time_limit)
        cfg.loom_ilp_num_threads      = self._v(self.loom_ilp_threads)

        cfg.schematic            = self.schematic.isChecked()
        cfg.base_graph           = self.base_graph.currentText()
        cfg.octi_optim_mode      = self.octi_optim_mode.currentText()
        cfg.grid_size            = self.grid_size.text().strip() or None
        cfg.octi_geo_pen         = self._v(self.octi_geo_pen)
        cfg.octi_diag_pen        = self._v(self.octi_diag_pen)
        cfg.octi_vert_pen        = self._v(self.octi_vert_pen)
        cfg.octi_hori_pen        = self._v(self.octi_hori_pen)
        cfg.octi_density_pen     = self._v(self.octi_density_pen)
        cfg.octi_pen_90          = self._v(self.octi_pen_90)
        cfg.octi_pen_45          = self._v(self.octi_pen_45)
        cfg.octi_pen_135         = self._v(self.octi_pen_135)
        cfg.octi_pen_180         = self._v(self.octi_pen_180)
        cfg.octi_nd_move_pen     = self._v(self.octi_nd_move)
        cfg.octi_ilp_time_limit  = self._v(self.octi_ilp_time_limit)
        cfg.octi_write_stats     = self.octi_write_stats.isChecked()

        cfg.render_engine            = self.render_engine.currentText()
        cfg.show_labels              = self.show_labels.isChecked()
        cfg.line_width               = self._v(self.line_width)
        cfg.line_spacing             = self._v(self.line_spacing)
        cfg.outline_width            = self._v(self.outline_width)
        cfg.line_label_textsize      = self._v(self.line_label_textsize)
        cfg.station_label_textsize   = self._v(self.station_label_textsize)
        cfg.smoothing                = self._v(self.smoothing)
        cfg.padding                  = self._v(self.padding)
        cfg.no_deg2_labels           = self.no_deg2_labels.isChecked()
        cfg.render_dir_markers       = self.render_dir_markers.isChecked()
        cfg.random_colors            = self.random_colors.isChecked()
        cfg.tight_stations           = self.tight_stations.isChecked()
        cfg.no_render_stations       = self.no_render_stations.isChecked()
        cfg.mvt_path                 = self.mvt_path.text().strip()
        cfg.mvt_zoom                 = self.mvt_zoom.text().strip() or "14"

        return cfg

    @staticmethod
    def _layer_to_geojson(layer):
        import tempfile
        from qgis.core import QgsVectorFileWriter
        tmp = tempfile.NamedTemporaryFile(suffix=".geojson", delete=False)
        tmp.close()
        QgsVectorFileWriter.writeAsVectorFormat(layer, tmp.name, "utf-8", layer.crs(), "GeoJSON")
        try:
            with open(tmp.name, "r", encoding="utf-8") as fh:
                return fh.read()
        finally:
            os.unlink(tmp.name)

    def _set_running(self, running):
        self.run_btn.setVisible(not running)
        self.cancel_btn.setVisible(running)
        self.progress_bar.setVisible(running)
        if not running:
            self.progress_bar.setValue(0); self.progress_label.setText("")

    def _on_run(self):
        cfg = self._build_config()
        if not cfg.input_geojson and not cfg.gtfs_zip_path:
            QMessageBox.warning(self, "No input", "Please select a QGIS layer, GeoJSON file, or GTFS zip.")
            return
        if cfg.render_engine == "mvt" and not cfg.mvt_path:
            QMessageBox.warning(self, "No MVT path", "Please set the MVT output path in the Output tab.")
            return
        self._set_running(True)
        self.error_text.clear(); self.svg_preview.clear()
        self.worker = PipelineWorker(cfg, parent=self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_cancel(self):
        if self.worker:
            self.progress_label.setText("Cancelling…")
            self.cancel_btn.setEnabled(False)
            self.worker.cancel()

    def _on_progress(self, pct, label):
        self.progress_bar.setValue(pct); self.progress_label.setText(label)

    def _on_finished(self, result):
        self._set_running(False); self.cancel_btn.setEnabled(True)

        if result.cancelled:
            self.progress_label.setText("Cancelled."); return

        lines = []
        for stage, msg in result.warnings.items(): lines.append(f"[{stage}] WARNING:\n{msg}")
        for stage, msg in result.errors.items():   lines.append(f"[{stage}] ERROR:\n{msg}")
        self.error_text.setPlainText("\n\n".join(lines))

        if not result.success:
            QMessageBox.critical(self, "Pipeline failed", "LOOM pipeline failed. See the Diagnostics tab.")
            return

        out_path = self.output_path.text().strip()

        if result.svg_output:
            self.svg_preview.setPlainText(result.svg_output[:50_000])
            if out_path:
                with open(out_path, "w", encoding="utf-8") as fh:
                    fh.write(result.svg_output)
            if self.open_after.isChecked() and out_path and os.path.isfile(out_path):
                import subprocess, sys
                if sys.platform == "win32":
                    os.startfile(out_path)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", out_path])
                else:
                    subprocess.Popen(["xdg-open", out_path])

            # ── Webmap ────────────────────────────────────────────────
            if self.webmap_enabled.isChecked():
                wm_path = self.webmap_path.text().strip()
                if not wm_path:
                    # Auto-derive from SVG path or use temp dir
                    if out_path:
                        wm_path = os.path.splitext(out_path)[0] + "_webmap.html"
                    else:
                        import tempfile
                        wm_path = os.path.join(tempfile.gettempdir(), "loom_webmap.html")
                    self.webmap_path.setText(wm_path)
                try:
                    from .webmap_generator import generate as generate_webmap
                    generate_webmap(result.svg_output, wm_path)
                    self.iface.messageBar().pushMessage(
                        "LOOM", f"Webmap written to: {wm_path}", level=0, duration=8
                    )
                    if self.webmap_open.isChecked() and os.path.isfile(wm_path):
                        import subprocess, sys
                        if sys.platform == "win32":
                            os.startfile(wm_path)
                        elif sys.platform == "darwin":
                            subprocess.Popen(["open", wm_path])
                        else:
                            subprocess.Popen(["xdg-open", wm_path])
                except Exception as e:
                    QMessageBox.warning(self, "Webmap error", f"Failed to generate webmap:\n{e}")

        if result.mvt_path:
            self.iface.messageBar().pushMessage("LOOM", f"MVT tiles written to: {result.mvt_path}", level=0, duration=8)

        QMessageBox.information(self, "Done", "Transit map generated successfully!")

    def _on_redownload(self):
        from .download_dialog import DownloadDialog
        dlg = DownloadDialog(parent=self, auto_start=False)
        dlg.download_complete.connect(self._check_binaries_status)
        dlg.exec_(); self._check_binaries_status()
