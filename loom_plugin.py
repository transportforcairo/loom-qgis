# -*- coding: utf-8 -*-
"""
loom_plugin.py — QGIS plugin entry point.

On first run (or whenever binaries are missing) the DownloadDialog is shown
before the main dialog so the user can fetch pre-built binaries automatically.
"""

import os

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui     import QIcon
from qgis.core           import QgsApplication

from .downloader import binaries_present


class LoomPlugin:

    def __init__(self, iface):
        self.iface   = iface
        self.action  = None
        self.dialog  = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "resources", "icon.png")
        icon = QIcon(icon_path) if os.path.isfile(icon_path) \
               else QgsApplication.getThemeIcon("/mActionAddLayer.svg")

        self.action = QAction(icon, "LOOM Transit Map Generator", self.iface.mainWindow())
        self.action.setToolTip(
            "Generate schematic or geographic transit maps using LOOM\n"
            "(github.com/ad-freiburg/loom) — Windows port by Transport for Cairo"
        )
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&LOOM Transit Maps", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginMenu("&LOOM Transit Maps", self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dialog:
            self.dialog.close()

    def run(self):
        if not binaries_present():
            self._show_download_dialog()
        else:
            self._show_main_dialog()

    def _show_download_dialog(self):
        from .download_dialog import DownloadDialog
        dlg = DownloadDialog(parent=self.iface.mainWindow(), auto_start=False)
        dlg.exec_()
        # Proceed to main dialog whether they downloaded or skipped
        # (skip case: maybe binaries are on PATH)
        if dlg.was_successful() or binaries_present():
            self._show_main_dialog()

    def _show_main_dialog(self):
        from .dialog import LoomDialog
        if self.dialog is None:
            self.dialog = LoomDialog(self.iface, parent=self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
