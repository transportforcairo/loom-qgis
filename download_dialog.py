# -*- coding: utf-8 -*-
"""
download_dialog.py — First-run dialog that downloads LOOM binaries.

Shown automatically when the plugin starts and no binaries are found.
Can also be triggered manually from the Diagnostics tab.
"""

import platform

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QDialogButtonBox, QSizePolicy,
)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtGui  import QFont

from .downloader import download_binaries, binaries_present, BINARIES_REPO


# ---------------------------------------------------------------------------
# Worker thread — keeps the UI responsive during download
# ---------------------------------------------------------------------------

class DownloadWorker(QThread):
    progress  = pyqtSignal(int, int, str)   # bytes_done, total, message
    succeeded = pyqtSignal(str)             # bin_dir
    failed    = pyqtSignal(str)             # error message

    def run(self):
        def _cb(done, total, msg):
            self.progress.emit(done or 0, total or 0, msg)

        try:
            bin_dir = download_binaries(progress_cb=_cb)
            self.succeeded.emit(bin_dir)
        except Exception as exc:
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class DownloadDialog(QDialog):

    # Emitted after a successful download so the caller can proceed
    download_complete = pyqtSignal()

    def __init__(self, parent=None, auto_start: bool = False):
        super().__init__(parent)
        self.worker = None
        self._success = False

        self.setWindowTitle("LOOM — Download Binaries")
        self.setMinimumWidth(500)
        self.setMinimumHeight(360)
        self.setWindowModality(Qt.ApplicationModal)

        self._build_ui()

        if auto_start:
            self._start_download()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # Header
        title = QLabel("LOOM Binaries Required")
        f = title.font()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        root.addWidget(title)

        # Platform info
        system  = platform.system()
        machine = platform.machine()
        info = QLabel(
            f"No pre-built LOOM binaries were found for your platform "
            f"(<b>{system} {machine}</b>).\n\n"
            f"Click <b>Download</b> to fetch them automatically from GitHub "
            f"(<code>{BINARIES_REPO}</code>).<br>"
            "This is a one-time download (~10–80 MB depending on platform)."
        )
        info.setWordWrap(True)
        info.setTextFormat(Qt.RichText)
        root.addWidget(info)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        # Log area (shown on error)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Courier New", 9))
        self.log.setVisible(False)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.log)

        # Buttons
        btn_row = QHBoxLayout()

        self.download_btn = QPushButton("Download")
        self.download_btn.setDefault(True)
        self.download_btn.clicked.connect(self._start_download)

        self.skip_btn = QPushButton("Skip (I'll add binaries manually)")
        self.skip_btn.clicked.connect(self.reject)

        self.close_btn = QPushButton("Close")
        self.close_btn.setVisible(False)
        self.close_btn.clicked.connect(self.accept)

        btn_row.addWidget(self.download_btn)
        btn_row.addWidget(self.skip_btn)
        btn_row.addWidget(self.close_btn)
        root.addLayout(btn_row)

        # Manual instructions (collapsed by default)
        manual_label = QLabel(
            "<small><a href='#'>Where do I get binaries manually?</a></small>"
        )
        manual_label.setTextFormat(Qt.RichText)
        manual_label.setOpenExternalLinks(False)
        manual_label.linkActivated.connect(self._show_manual_instructions)
        root.addWidget(manual_label)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _start_download(self):
        self.download_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)   # indeterminate until we know size
        self.log.setVisible(False)
        self.status_label.setText("Contacting GitHub…")

        self.worker = DownloadWorker(parent=self)
        self.worker.progress.connect(self._on_progress)
        self.worker.succeeded.connect(self._on_success)
        self.worker.failed.connect(self._on_failure)
        self.worker.start()

    def _on_progress(self, done: int, total: int, msg: str):
        self.status_label.setText(msg)
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)
        else:
            self.progress_bar.setRange(0, 0)  # keep spinner

    def _on_success(self, bin_dir: str):
        self._success = True
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(
            f"✔  Binaries installed successfully.\n{bin_dir}"
        )
        self.download_btn.setVisible(False)
        self.skip_btn.setVisible(False)
        self.close_btn.setVisible(True)
        self.close_btn.setDefault(True)
        self.download_complete.emit()

    def _on_failure(self, error: str):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("✘  Download failed. See details below.")
        self.log.setVisible(True)
        self.log.setPlainText(error)
        self.download_btn.setEnabled(True)
        self.download_btn.setText("Retry")
        self.skip_btn.setEnabled(True)

    def _show_manual_instructions(self):
        self.log.setVisible(True)
        self.log.setPlainText(
            "Manual binary installation\n"
            "==========================\n\n"
            f"1. Go to: https://github.com/{BINARIES_REPO}\n"
            "2. Download the ZIP for your platform:\n"
            "     Windows : loom-binaries-windows-x64.zip\n"
            "     macOS   : loom-binaries-macos-arm64.zip\n"
            "     Linux   : loom-binaries-linux-x64.zip\n\n"
            "3. Extract the contents into:\n"
            "     <QGIS plugins folder>/qgis-loom-plugin/plugin/bin/windows/\n"
            "     <QGIS plugins folder>/qgis-loom-plugin/plugin/bin/macos/\n"
            "     <QGIS plugins folder>/qgis-loom-plugin/plugin/bin/linux/\n\n"
            "4. Restart QGIS.\n\n"
            "Alternatively, if you have LOOM compiled and on your system PATH,\n"
            "the plugin will find and use those binaries automatically."
        )

    def was_successful(self) -> bool:
        return self._success
