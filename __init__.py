# -*- coding: utf-8 -*-
"""
LOOM Transit Map Generator — QGIS Plugin
Wraps the LOOM suite (github.com/ad-freiburg/loom) with a cross-platform GUI.

Original LOOM tool © University of Freiburg (Bast, Brosi, Storandt), GPL-3.0.
Windows port & QGIS plugin by Transport for Cairo (transportforcairo.com), 2026.
"""


def classFactory(iface):
    from .loom_plugin import LoomPlugin
    return LoomPlugin(iface)
