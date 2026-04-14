# -*- coding: utf-8 -*-
"""
dialog.py — Qt dialog for the LOOM QGIS plugin.

Provides a clean, well-labelled UI for all pipeline parameters documented in
the handoff document (section 4.6) plus diagnostics and output handling.
"""

import os
import json

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QComboBox, QCheckBox, QDoubleSpinBox,
    QLineEdit, QPushButton, QFileDialog, QTabWidget, QWidget,
    QTextEdit, QProgressBar, QMessageBox, QFormLayout, QSizePolicy,
)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtGui import QFont, QColor
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsMapLayerProxyModel,
)
try:
    from qgis.gui import QgsMapLayerComboBox
    HAS_LAYER_COMBO = True
except ImportError:
    HAS_LAYER_COMBO = False

from .runner import PipelineConfig, PipelineResult, run_pipeline
from .binary_resolver import check_binaries, get_platform_info


# ---------------------------------------------------------------------------
# Background worker thread
# ---------------------------------------------------------------------------

class PipelineWorker(QThread):
    progress    = pyqtSignal(int, str)
    finished    = pyqtSignal(object)   # PipelineResult

    def __init__(self, cfg: PipelineConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg

    def run(self):
        result = run_pipeline(self.cfg, progress_cb=self.progress.emit)
        self.finished.emit(result)


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class LoomDialog(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface   = iface
        self.worker  = None
        self._result = None

        self.setWindowTitle("LOOM Transit Map Generator")
        self.setMinimumWidth(560)
        self.setMinimumHeight(640)

        self._build_ui()
        self._check_binaries_status()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # Title bar
        title = QLabel("LOOM Transit Map Generator")
        title.setAlignment(Qt.AlignCenter)
        f = title.font()
        f.setPointSize(14)
        f.setBold(True)
        title.setFont(f)
        subtitle = QLabel(
            "Powered by LOOM · University of Freiburg · Windows port by Transport for Cairo"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: gray; font-size: 10px;")
        root.addWidget(title)
        root.addWidget(subtitle)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._build_input_tab(),    "Input")
        tabs.addTab(self._build_options_tab(),  "Options")
        tabs.addTab(self._build_output_tab(),   "Output")
        tabs.addTab(self._build_diag_tab(),     "Diagnostics")
        root.addWidget(tabs)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.progress_bar)
        root.addWidget(self.progress_label)

        # Buttons
        btn_box = QDialogButtonBox()
        self.run_btn    = btn_box.addButton("Run Pipeline", QDialogButtonBox.AcceptRole)
        self.cancel_btn = btn_box.addButton("Close",        QDialogButtonBox.RejectRole)
        self.run_btn.clicked.connect(self._on_run)
        self.cancel_btn.clicked.connect(self.reject)
        root.addWidget(btn_box)

    # ---- Input tab -------------------------------------------------------

    def _build_input_tab(self) -> QWidget:
        w  = QWidget()
        vb = QVBoxLayout(w)

        # Source selection
        src_group = QGroupBox("Input Source")
        src_form  = QFormLayout(src_group)

        # Layer combo (if available)
        if HAS_LAYER_COMBO:
            self.layer_combo = QgsMapLayerComboBox()
            self.layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer)
            self.layer_combo.setAllowEmptyLayer(True)
            self.layer_combo.setCurrentIndex(0)
            src_form.addRow("QGIS layer:", self.layer_combo)
        else:
            self.layer_combo = None

        # GeoJSON file
        geojson_row = QHBoxLayout()
        self.geojson_path = QLineEdit()
        self.geojson_path.setPlaceholderText("Or select a GeoJSON file…")
        btn_geojson = QPushButton("Browse")
        btn_geojson.clicked.connect(self._browse_geojson)
        geojson_row.addWidget(self.geojson_path)
        geojson_row.addWidget(btn_geojson)
        src_form.addRow("GeoJSON file:", geojson_row)

        # GTFS zip
        gtfs_row = QHBoxLayout()
        self.gtfs_path = QLineEdit()
        self.gtfs_path.setPlaceholderText("Or select a GTFS .zip file…")
        btn_gtfs = QPushButton("Browse")
        btn_gtfs.clicked.connect(self._browse_gtfs)
        gtfs_row.addWidget(self.gtfs_path)
        gtfs_row.addWidget(btn_gtfs)
        src_form.addRow("GTFS zip file:", gtfs_row)

        # Transport mode (only relevant for GTFS input)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["tram", "bus", "rail", "all"])
        src_form.addRow("Transport mode:", self.mode_combo)

        vb.addWidget(src_group)
        vb.addStretch()
        return w

    # ---- Options tab -----------------------------------------------------

    def _build_options_tab(self) -> QWidget:
        w  = QWidget()
        vb = QVBoxLayout(w)

        # Rendering
        render_group = QGroupBox("Rendering")
        render_form  = QFormLayout(render_group)

        self.render_style = QComboBox()
        self.render_style.addItems(["geographic", "octilinear", "orthoradial"])
        render_form.addRow("Render style:", self.render_style)

        self.show_labels = QCheckBox("Show line labels")
        self.show_labels.setChecked(True)
        render_form.addRow("", self.show_labels)

        self.line_width = QDoubleSpinBox()
        self.line_width.setRange(0.1, 50.0)
        self.line_width.setValue(2.0)
        self.line_width.setSuffix(" px")
        self.line_width.setSpecialValueText("(default)")
        render_form.addRow("Line width:", self.line_width)

        self.line_spacing = QDoubleSpinBox()
        self.line_spacing.setRange(0.1, 50.0)
        self.line_spacing.setValue(1.5)
        self.line_spacing.setSuffix(" px")
        render_form.addRow("Line spacing:", self.line_spacing)

        self.outline_width = QDoubleSpinBox()
        self.outline_width.setRange(0.0, 20.0)
        self.outline_width.setValue(1.0)
        self.outline_width.setSuffix(" px")
        render_form.addRow("Outline width:", self.outline_width)

        self.output_format = QComboBox()
        self.output_format.addItems(["SVG", "MVT tiles"])
        render_form.addRow("Output format:", self.output_format)

        vb.addWidget(render_group)

        # Solver
        solver_group = QGroupBox("ILP Solver")
        solver_form  = QFormLayout(solver_group)
        self.solver_combo = QComboBox()
        self.solver_combo.addItems(["auto", "glpk", "cbc"])
        solver_form.addRow("Solver:", self.solver_combo)
        vb.addWidget(solver_group)

        # Pipeline stages
        stages_group = QGroupBox("Pipeline Stages")
        stages_form  = QFormLayout(stages_group)
        self.use_topo = QCheckBox("Run topo (resolve overlapping edges)")
        self.use_topo.setChecked(True)
        stages_form.addRow("", self.use_topo)
        vb.addWidget(stages_group)

        vb.addStretch()
        return w

    # ---- Output tab ------------------------------------------------------

    def _build_output_tab(self) -> QWidget:
        w  = QWidget()
        vb = QVBoxLayout(w)

        out_group = QGroupBox("Output Destination")
        out_form  = QFormLayout(out_group)

        out_row = QHBoxLayout()
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("Leave blank to load into QGIS only")
        btn_out = QPushButton("Browse")
        btn_out.clicked.connect(self._browse_output)
        out_row.addWidget(self.output_path)
        out_row.addWidget(btn_out)
        out_form.addRow("Save to file:", out_row)

        self.load_qgis = QCheckBox("Load result as QGIS annotation layer")
        self.load_qgis.setChecked(True)
        out_form.addRow("", self.load_qgis)

        vb.addWidget(out_group)

        # SVG preview (read-only text display)
        preview_group = QGroupBox("SVG Output Preview")
        preview_vb = QVBoxLayout(preview_group)
        self.svg_preview = QTextEdit()
        self.svg_preview.setReadOnly(True)
        self.svg_preview.setFont(QFont("Courier New", 9))
        self.svg_preview.setPlaceholderText("SVG output will appear here after running…")
        preview_vb.addWidget(self.svg_preview)
        vb.addWidget(preview_group)

        return w

    # ---- Diagnostics tab -------------------------------------------------

    def _build_diag_tab(self) -> QWidget:
        w  = QWidget()
        vb = QVBoxLayout(w)

        vb.addWidget(QLabel("<b>Platform:</b>"))
        self.platform_label = QLabel(get_platform_info())
        vb.addWidget(self.platform_label)

        vb.addWidget(QLabel("<b>Binary Status:</b>"))
        self.diag_text = QTextEdit()
        self.diag_text.setReadOnly(True)
        self.diag_text.setFont(QFont("Courier New", 9))
        vb.addWidget(self.diag_text)

        btn_row = QHBoxLayout()

        refresh_btn = QPushButton("Re-check binaries")
        refresh_btn.clicked.connect(self._check_binaries_status)
        btn_row.addWidget(refresh_btn)

        redownload_btn = QPushButton("Re-download binaries…")
        redownload_btn.clicked.connect(self._on_redownload)
        btn_row.addWidget(redownload_btn)

        vb.addLayout(btn_row)

        vb.addWidget(QLabel("<b>Last run — stderr / warnings:</b>"))
        self.error_text = QTextEdit()
        self.error_text.setReadOnly(True)
        self.error_text.setFont(QFont("Courier New", 9))
        vb.addWidget(self.error_text)

        return w

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_binaries_status(self):
        status = check_binaries()
        lines = []
        for name, ok in status.items():
            mark = "✔" if ok else "✘"
            lines.append(f"  {mark}  {name}")
        self.diag_text.setPlainText("\n".join(lines))

    def _browse_geojson(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select GeoJSON file", "", "GeoJSON files (*.geojson *.json)"
        )
        if path:
            self.geojson_path.setText(path)

    def _browse_gtfs(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select GTFS zip", "", "GTFS zip files (*.zip)"
        )
        if path:
            self.gtfs_path.setText(path)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save output", "", "SVG files (*.svg);;All files (*)"
        )
        if path:
            self.output_path.setText(path)

    # ------------------------------------------------------------------
    # Build config from UI
    # ------------------------------------------------------------------

    def _build_config(self) -> PipelineConfig:
        cfg = PipelineConfig()

        # --- Input ---
        gtfs = self.gtfs_path.text().strip()
        if gtfs:
            cfg.gtfs_zip_path    = gtfs
            cfg.transport_mode   = self.mode_combo.currentText()
        else:
            geojson_file = self.geojson_path.text().strip()
            if geojson_file and os.path.isfile(geojson_file):
                with open(geojson_file, "r", encoding="utf-8") as fh:
                    cfg.input_geojson = fh.read()
            elif HAS_LAYER_COMBO and self.layer_combo:
                layer = self.layer_combo.currentLayer()
                if layer:
                    cfg.input_geojson = self._layer_to_geojson(layer)

        # --- Options ---
        style = self.render_style.currentText()
        cfg.schematic   = style in ("octilinear", "orthoradial")
        cfg.base_graph  = style if cfg.schematic else "octilinear"
        cfg.show_labels = self.show_labels.isChecked()
        cfg.line_width  = self.line_width.value()  if self.line_width.value()  > 0 else None
        cfg.line_spacing = self.line_spacing.value() if self.line_spacing.value() > 0 else None
        cfg.outline_width = self.outline_width.value() if self.outline_width.value() > 0 else None
        cfg.render_engine = "mvt" if self.output_format.currentIndex() == 1 else "svg"
        cfg.ilp_solver    = self.solver_combo.currentText()
        cfg.include_topo  = self.use_topo.isChecked()

        return cfg

    @staticmethod
    def _layer_to_geojson(layer: QgsVectorLayer) -> str:
        """Export a QGIS vector layer to a GeoJSON string."""
        import tempfile, json
        tmp = tempfile.NamedTemporaryFile(suffix=".geojson", delete=False)
        tmp.close()
        error = QgsVectorFileWriter.writeAsVectorFormat(
            layer, tmp.name, "utf-8", layer.crs(), "GeoJSON"
        )
        try:
            with open(tmp.name, "r", encoding="utf-8") as fh:
                return fh.read()
        finally:
            os.unlink(tmp.name)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _on_run(self):
        cfg = self._build_config()

        if not cfg.input_geojson and not cfg.gtfs_zip_path:
            QMessageBox.warning(
                self, "No input",
                "Please select a QGIS layer, a GeoJSON file, or a GTFS zip file."
            )
            return

        # Disable UI during run
        self.run_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.progress_label.setText("Starting…")
        self.error_text.clear()
        self.svg_preview.clear()

        self.worker = PipelineWorker(cfg, parent=self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, pct: int, label: str):
        self.progress_bar.setValue(pct)
        self.progress_label.setText(label)

    def _on_finished(self, result: PipelineResult):
        self._result = result
        self.run_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setText("")

        # Show warnings / errors
        lines = []
        for stage, msg in result.warnings.items():
            lines.append(f"[{stage}] WARNING:\n{msg}")
        for stage, msg in result.errors.items():
            lines.append(f"[{stage}] ERROR:\n{msg}")
        self.error_text.setPlainText("\n\n".join(lines))

        if not result.success:
            QMessageBox.critical(
                self, "Pipeline failed",
                "LOOM pipeline failed. See the Diagnostics tab for details."
            )
            return

        # Display SVG preview
        self.svg_preview.setPlainText(result.svg_output[:50_000])

        # Save to file if requested
        out_path = self.output_path.text().strip()
        if out_path:
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(result.svg_output)

        # Load into QGIS
        if self.load_qgis.isChecked() and result.svg_output:
            self._load_into_qgis(result.svg_output, out_path)

        QMessageBox.information(self, "Done", "Transit map generated successfully!")

    def _on_redownload(self):
        from .download_dialog import DownloadDialog
        dlg = DownloadDialog(parent=self, auto_start=False)
        dlg.download_complete.connect(self._check_binaries_status)
        dlg.exec_()
        self._check_binaries_status()

    def _load_into_qgis(self, svg_text: str, saved_path: str):
        """Load the SVG as a QGIS SVG annotation or simply notify the user."""
        if saved_path and os.path.isfile(saved_path):
            # Attempt to add as a vector layer (SVG)
            try:
                from qgis.core import QgsSvgAnnotation
                ann = QgsSvgAnnotation()
                ann.setFilePath(saved_path)
                QgsProject.instance().annotationManager().addAnnotation(ann)
                self.iface.mapCanvas().refresh()
                return
            except Exception:
                pass
            # Fallback: notify
            self.iface.messageBar().pushMessage(
                "LOOM",
                f"Transit map saved to: {saved_path}",
                level=0,  # Qgis.Info
                duration=8,
            )
        else:
            self.iface.messageBar().pushMessage(
                "LOOM",
                "Pipeline complete. Specify an output path to save the SVG.",
                level=0,
                duration=8,
            )
