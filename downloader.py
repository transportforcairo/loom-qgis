# -*- coding: utf-8 -*-
"""
downloader.py — Download pre-built LOOM binaries from the loom-binaries repo.

Binaries are stored as ZIP files in the root of:
  https://github.com/transportforcairo/loom-binaries

Files are downloaded via raw.githubusercontent.com — no API, no tokens,
no releases required. Just a direct file download.

ZIP naming convention:
    loom-binaries-windows-x64.zip
    loom-binaries-macos-arm64.zip
    loom-binaries-linux-x64.zip

Each ZIP contains the binaries flat (no subdirectory):
    loom.exe, topo.exe, ... + DLLs   (Windows)
    loom, topo, octi, ...             (macOS / Linux)
"""

import os
import platform
import stat
import tempfile
import urllib.request
import zipfile
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BINARIES_REPO  = "transportforcairo/loom_binaries"
BINARIES_BRANCH = "main"

# Base URL for raw file downloads
_RAW_BASE = f"https://raw.githubusercontent.com/{BINARIES_REPO}/{BINARIES_BRANCH}"

# Map (system, machine) → ZIP filename suffix
_ASSET_MAP = {
    ("Windows", "AMD64"):   "windows-x64",
    ("Windows", "x86_64"):  "windows-x64",
    ("Darwin",  "arm64"):   "macos-arm64",
    ("Darwin",  "x86_64"):  "macos-arm64",   # fallback — arm64 build runs via Rosetta
    ("Linux",   "x86_64"):  "linux-x64",
    ("Linux",   "aarch64"): "linux-x64",
}

_PLATFORM_SUBDIR = {
    "Windows": "windows",
    "Darwin":  "macos",
    "Linux":   "linux",
}

# ---------------------------------------------------------------------------
# Progress callback: (bytes_downloaded, total_bytes_or_None, message)
# ---------------------------------------------------------------------------
ProgressCB = Callable[[int, Optional[int], str], None]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plugin_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _bin_dir() -> str:
    system = platform.system()
    sub    = _PLATFORM_SUBDIR.get(system, "linux")
    return os.path.join(_plugin_dir(), "bin", sub)


def _download_url() -> str:
    system  = platform.system()
    machine = platform.machine()
    suffix  = _ASSET_MAP.get((system, machine))
    if not suffix:
        raise RuntimeError(
            f"No pre-built binaries available for {system} {machine}.\n"
            "Please build LOOM from source — see "
            f"https://github.com/{BINARIES_REPO} for build scripts."
        )
    return f"{_RAW_BASE}/loom-binaries-{suffix}.zip"


def _download_file(url: str, dest_path: str, progress_cb: Optional[ProgressCB]) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "qgis-loom-plugin/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total      = resp.headers.get("Content-Length")
        total      = int(total) if total else None
        downloaded = 0
        chunk_size = 64 * 1024  # 64 KB

        with open(dest_path, "wb") as fh:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                fh.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    mb = downloaded / 1_048_576
                    if total:
                        msg = f"Downloading… {mb:.1f} / {total / 1_048_576:.1f} MB"
                    else:
                        msg = f"Downloading… {mb:.1f} MB"
                    progress_cb(downloaded, total, msg)


def _extract_zip(zip_path: str, dest_dir: str) -> None:
    """Extract ZIP flat into dest_dir; make binaries executable on Unix."""
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            filename = os.path.basename(member.filename)
            if not filename:
                continue
            dest_file = os.path.join(dest_dir, filename)
            with zf.open(member) as src, open(dest_file, "wb") as dst:
                dst.write(src.read())

    if platform.system() != "Windows":
        for fname in os.listdir(dest_dir):
            fpath = os.path.join(dest_dir, fname)
            st = os.stat(fpath)
            os.chmod(fpath, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def binaries_present() -> bool:
    """True if the main loom binary already exists in the bin dir."""
    system = platform.system()
    ext    = ".exe" if system == "Windows" else ""
    return os.path.isfile(os.path.join(_bin_dir(), f"loom{ext}"))


def download_binaries(progress_cb: Optional[ProgressCB] = None) -> str:
    """
    Download and install LOOM binaries for the current platform.
    Returns the bin_dir path on success.
    Raises RuntimeError with a human-readable message on failure.
    """
    url = _download_url()

    if progress_cb:
        progress_cb(0, None, f"Connecting to GitHub…")

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="loom_binaries_")
    os.close(tmp_fd)

    try:
        _download_file(url, tmp_path, progress_cb)

        if progress_cb:
            progress_cb(0, None, "Extracting…")

        _extract_zip(tmp_path, _bin_dir())

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if progress_cb:
        progress_cb(1, 1, f"Done — binaries installed to {_bin_dir()}")

    return _bin_dir()
