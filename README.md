# QGIS LOOM Transit Map Generator

A cross-platform QGIS plugin that wraps the [LOOM](https://github.com/ad-freiburg/loom) transit map generation suite with a friendly GUI. Generate schematic and geographically accurate transit maps directly inside QGIS — no command line required.

**LOOM** © University of Freiburg (Hannah Bast, Patrick Brosi, Sabine Storandt), GPL-3.0.  
**Windows port & QGIS plugin** by [Transport for Cairo](https://transportforcairo.com), 2026.

---

## Installation

1. Download the latest plugin ZIP from the [Releases](../../releases) page.
2. In QGIS: **Plugins → Manage and Install Plugins → Install from ZIP**.
3. Enable **LOOM Transit Map Generator** in the plugin list.
4. Click the toolbar button — on first run the plugin will automatically download the pre-built LOOM binaries for your platform (~10–80 MB, one-time).

No compiling required.

---

## Usage

1. Open the plugin via **Plugins → LOOM Transit Maps** or the toolbar button.
2. **Input tab** — select a QGIS vector layer, a GeoJSON file, or a GTFS zip.
3. **Options tab** — choose render style, labels, line widths, ILP solver.
4. **Output tab** — set a save path and/or load the result directly into QGIS.
5. Click **Run Pipeline**.

### Render styles

| Style | Description |
|---|---|
| Geographic | Lines on their real-world geometry |
| Octilinear | Schematic map on a 45°/90° grid (metro-map style) |
| Orthoradial | Schematic map on a radial/concentric grid |

### Pipeline

```
[gtfs2graph]  →  topo  →  loom  →  [octi]  →  transitmap  →  SVG / MVT
```

All stages run as `subprocess.PIPE` chains — no shell redirection, works identically on Windows, macOS, and Linux.

---

## Binaries

Pre-built binaries are hosted at [transportforcairo/loom-binaries](https://github.com/transportforcairo/loom-binaries) and downloaded automatically on first run. To re-download or update, go to the plugin's **Diagnostics tab → Re-download binaries**.

---

## Repository structure

```
qgis-loom-plugin/
├── plugin/
│   ├── __init__.py            QGIS classFactory entry point
│   ├── loom_plugin.py         Plugin lifecycle (menu, toolbar, first-run check)
│   ├── dialog.py              Main Qt dialog (Input / Options / Output / Diagnostics)
│   ├── runner.py              Subprocess pipeline runner
│   ├── binary_resolver.py     OS detection and binary path resolution
│   ├── downloader.py          Binary downloader (pulls from loom-binaries repo)
│   ├── download_dialog.py     First-run download UI
│   ├── metadata.txt           QGIS plugin metadata
│   ├── bin/
│   │   ├── windows/           Populated automatically by downloader
│   │   ├── macos/             Populated automatically by downloader
│   │   └── linux/             Populated automatically by downloader
│   └── resources/
│       └── icon.png
├── README.md
└── LICENSE
```

---

## Attribution

This plugin uses [LOOM](https://github.com/ad-freiburg/loom), developed by Hannah Bast, Patrick Brosi, and Sabine Storandt at the University of Freiburg, licensed under GPL-3.0. Windows port by [Transport for Cairo](https://transportforcairo.com), 2026.

Key publications:
- Bast, Brosi, Storandt. *Efficient Generation of Geographically Accurate Transit Maps.* SIGSPATIAL 2018.
- Bast, Brosi, Storandt. *Metro Maps on Octilinear Grid Graphs.* EuroVis 2020.
- Bast, Brosi, Storandt. *Metro Maps on Flexible Base Grids.* SSTD 2021.

---

## Licence

GPL-3.0 — matching the upstream LOOM project.
