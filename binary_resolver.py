# -*- coding: utf-8 -*-
"""
binary_resolver.py — Detect OS and return paths to bundled LOOM binaries.

Bundled binary layout:
  plugin/bin/windows/   → loom.exe, topo.exe, octi.exe, gtfs2graph.exe,
                           transitmap.exe, topoeval.exe  + bundled DLLs
  plugin/bin/macos/     → same names, no extension
  plugin/bin/linux/     → same names, no extension

If bundled binaries are absent the resolver falls back to PATH so that
developers who have built LOOM from source can still use the plugin.
"""

import os
import platform
import shutil
from typing import Dict, Optional


BINARY_NAMES = ["loom", "topo", "octi", "gtfs2graph", "transitmap", "topoeval"]

# Map platform.system() → subdirectory name
_PLATFORM_DIR: Dict[str, str] = {
    "Windows": "windows",
    "Darwin":  "macos",
    "Linux":   "linux",
}

# On Windows native executables carry the .exe extension
_PLATFORM_EXT: Dict[str, str] = {
    "Windows": ".exe",
    "Darwin":  "",
    "Linux":   "",
}


def _plugin_dir() -> str:
    """Absolute path to the plugin/ directory (where this file lives)."""
    return os.path.dirname(os.path.abspath(__file__))


def get_loom_binaries() -> Dict[str, str]:
    """
    Return a dict mapping binary name → absolute path string.

    Preference order:
      1. Bundled binary inside plugin/bin/<os>/
      2. Binary found on PATH via shutil.which()

    Raises RuntimeError if a required binary cannot be located.
    """
    system = platform.system()
    sub_dir = _PLATFORM_DIR.get(system, "linux")
    ext     = _PLATFORM_EXT.get(system, "")
    bin_dir = os.path.join(_plugin_dir(), "bin", sub_dir)

    result: Dict[str, str] = {}
    missing = []

    for name in BINARY_NAMES:
        fname    = f"{name}{ext}"
        bundled  = os.path.join(bin_dir, fname)

        if os.path.isfile(bundled):
            result[name] = bundled
        else:
            # Fallback: search PATH
            on_path: Optional[str] = shutil.which(fname) or shutil.which(name)
            if on_path:
                result[name] = on_path
            else:
                missing.append(name)

    if missing:
        raise RuntimeError(
            f"LOOM binaries not found: {', '.join(missing)}\n\n"
            f"Expected location: {bin_dir}\n"
            "Please copy the compiled LOOM binaries into the plugin's bin/ "
            "directory or ensure they are on your system PATH.\n\n"
            "See README.md for build instructions."
        )

    return result


def check_binaries() -> Dict[str, bool]:
    """
    Non-raising version — returns dict of name → exists (bool).
    Useful for the settings / diagnostics dialog.
    """
    system  = platform.system()
    sub_dir = _PLATFORM_DIR.get(system, "linux")
    ext     = _PLATFORM_EXT.get(system, "")
    bin_dir = os.path.join(_plugin_dir(), "bin", sub_dir)

    status: Dict[str, bool] = {}
    for name in BINARY_NAMES:
        fname   = f"{name}{ext}"
        bundled = os.path.join(bin_dir, fname)
        if os.path.isfile(bundled):
            status[name] = True
        else:
            on_path = shutil.which(fname) or shutil.which(name)
            status[name] = on_path is not None

    return status


def get_platform_info() -> str:
    """Human-readable platform string for display in the UI."""
    system  = platform.system()
    machine = platform.machine()
    version = platform.version()
    return f"{system} {machine} — {version}"
