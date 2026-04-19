# -*- coding: utf-8 -*-
"""
webmap_generator.py — Generates a self-contained interactive HTML webmap
from a LOOM SVG output.

The SVG is embedded inline and geo-registered using the latlng-box attribute
that LOOM writes on the root <svg> element. The map uses MapLibre GL JS with
a CartoCDN basemap, requires no tile server, and opens directly from the
filesystem.
"""

import re
import os


def generate(svg_content: str, output_path: str) -> None:
    """
    Build a self-contained HTML webmap from a LOOM SVG string and write it
    to output_path.

    Parameters
    ----------
    svg_content : str
        Full SVG file content (including <?xml …?> header if present).
    output_path : str
        Absolute path where the .html file will be written.
    """
    # ── Strip XML declaration and DOCTYPE ──────────────────────────────
    svg = re.sub(r'<\?xml[^?]*\?>', '', svg_content)
    svg = re.sub(r'<!DOCTYPE[^>]*>', '', svg)
    svg = svg.strip()

    # ── Extract latlng-box ─────────────────────────────────────────────
    m = re.search(r'latlng-box=["\']([^"\']+)["\']', svg)
    if m:
        parts = [float(x.strip()) for x in m.group(1).split(',')]
        min_lon, min_lat, max_lon, max_lat = parts
    else:
        # Fallback: Abidjan rough bounds
        min_lon, min_lat, max_lon, max_lat = -4.1, 5.28, -3.90, 5.45

    # ── Extract viewBox dimensions ─────────────────────────────────────
    vb = re.search(r'viewBox=["\']([^"\']+)["\']', svg)
    if vb:
        vb_parts = vb.group(1).split()
        svg_w = float(vb_parts[2])
        svg_h = float(vb_parts[3])
    else:
        svg_w, svg_h = 1829.0, 1441.0

    # ── Add id to svg root ─────────────────────────────────────────────
    svg = re.sub(r'<svg ', '<svg id="network-svg" ', svg, count=1)

    center_lon = (min_lon + max_lon) / 2
    center_lat = (min_lat + max_lat) / 2

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Réseau LOOM – Webmap</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300&display=swap" rel="stylesheet"/>
<link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet"/>
<script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
<style>
:root {{
  --bg: #0d0f14;
  --border: rgba(255,255,255,0.08);
  --accent: #f0c040;
  --text: #e8eaf0;
  --muted: #7a8099;
  --radius: 10px;
  --font-head: 'Syne', sans-serif;
  --font-body: 'DM Sans', sans-serif;
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 100%; height: 100%; overflow: hidden; background: var(--bg); color: var(--text); font-family: var(--font-body); }}
#map {{ position: absolute; inset: 0; }}

/* SVG overlay */
#svg-overlay {{ position: absolute; inset: 0; pointer-events: none; overflow: hidden; }}
#svg-wrapper {{
  position: absolute;
  transform-origin: top left;
  pointer-events: none;
}}
#network-svg {{ display: block; overflow: visible; pointer-events: none; }}
#network-svg .station-poly {{
  pointer-events: all;
  cursor: pointer;
  transition: fill 0.15s;
}}
#network-svg .station-poly:hover {{ fill: #f0c040 !important; }}
#network-svg .station-label {{ display: none; }}
#network-svg .line-label {{ display: none; }}

/* Header */
#header {{
  position: absolute; top: 16px; left: 50%; transform: translateX(-50%);
  z-index: 20; display: flex; align-items: center; gap: 18px;
  background: rgba(13,15,20,0.88); backdrop-filter: blur(14px);
  border: 1px solid var(--border); border-radius: 50px;
  padding: 10px 20px 10px 14px; box-shadow: 0 4px 32px rgba(0,0,0,0.5);
  white-space: nowrap;
}}
#header .logos {{ display: flex; align-items: center; gap: 10px; }}
#header .logo-wrap {{
  height: 34px; display: flex; align-items: center;
  background: rgba(255,255,255,0.06); border-radius: 6px; padding: 4px 8px;
}}
#header .logo-wrap img {{ height: 26px; width: auto; object-fit: contain; filter: brightness(1.1); }}
#header .logo-wrap.fallback {{
  font-family: var(--font-head); font-weight: 800; font-size: 13px;
  letter-spacing: 0.06em; color: var(--accent); padding: 4px 10px;
}}
.logo-divider {{ width: 1px; height: 28px; background: var(--border); }}
#header .title-block h1 {{ font-family: var(--font-head); font-weight: 700; font-size: 13px; color: var(--text); line-height: 1.2; }}
#header .title-block p {{ font-size: 11px; color: var(--muted); font-weight: 300; margin-top: 1px; }}

/* Basemap switcher */
#basemap-switcher {{
  position: absolute; bottom: 32px; right: 16px; z-index: 20;
  display: flex; flex-direction: column; gap: 6px;
}}
#basemap-switcher .bm-label {{
  font-family: var(--font-head); font-size: 9px; font-weight: 700;
  letter-spacing: 0.12em; color: var(--muted); text-transform: uppercase;
  text-align: right; margin-bottom: 2px;
}}
.bm-btn {{
  background: rgba(13,15,20,0.88); backdrop-filter: blur(10px);
  border: 1px solid var(--border); border-radius: var(--radius);
  color: var(--muted); font-family: var(--font-body); font-size: 12px;
  font-weight: 500; padding: 7px 14px; cursor: pointer;
  transition: all 0.18s ease; text-align: right;
}}
.bm-btn:hover {{ border-color: rgba(255,255,255,0.2); color: var(--text); }}
.bm-btn.active {{ border-color: var(--accent); color: var(--accent); background: rgba(240,192,64,0.1); }}

/* Zoom controls */
#zoom-ctrl {{
  position: absolute; bottom: 32px; left: 16px; z-index: 20;
  display: flex; flex-direction: column; gap: 4px;
}}
.z-btn {{
  width: 36px; height: 36px;
  background: rgba(13,15,20,0.88); backdrop-filter: blur(10px);
  border: 1px solid var(--border); border-radius: var(--radius);
  color: var(--text); font-size: 18px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: border-color 0.15s;
}}
.z-btn:hover {{ border-color: var(--accent); color: var(--accent); }}

/* Tooltip */
#tooltip {{ position: fixed; z-index: 30; pointer-events: none; display: none; min-width: 160px; }}
.tt-inner {{
  background: rgba(13,15,20,0.95); backdrop-filter: blur(16px);
  border: 1px solid var(--border); border-radius: var(--radius);
  padding: 10px 14px; box-shadow: 0 8px 32px rgba(0,0,0,0.6);
}}
.tt-type {{ font-size: 9px; font-family: var(--font-head); font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: var(--muted); margin-bottom: 4px; }}
.tt-name {{ font-family: var(--font-head); font-size: 14px; font-weight: 700; color: var(--text); line-height: 1.2; }}

/* Legend */
#legend {{
  position: absolute; top: 80px; left: 16px; z-index: 20;
  background: rgba(13,15,20,0.88); backdrop-filter: blur(14px);
  border: 1px solid var(--border); border-radius: var(--radius);
  padding: 12px 16px; min-width: 148px;
}}
.leg-title {{ font-family: var(--font-head); font-size: 9px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: var(--muted); margin-bottom: 9px; }}
.leg-row {{ display: flex; align-items: center; gap: 9px; margin-bottom: 7px; font-size: 12px; color: var(--text); font-weight: 300; }}
.leg-line {{ width: 22px; height: 3px; border-radius: 2px; }}
.leg-dot {{ width: 10px; height: 10px; border-radius: 50%; border: 2px solid #555; flex-shrink: 0; }}

@keyframes fadeUp {{ from {{ opacity:0; transform:translateY(8px); }} to {{ opacity:1; transform:translateY(0); }} }}
#header, #legend, #basemap-switcher, #zoom-ctrl {{ animation: fadeUp 0.5s ease both; }}
#legend {{ animation-delay: 0.1s; }} #basemap-switcher {{ animation-delay: 0.15s; }} #zoom-ctrl {{ animation-delay: 0.2s; }}
.maplibregl-ctrl-bottom-left {{ display: none; }}
</style>
</head>
<body>

<div id="map"></div>
<div id="svg-overlay"><div id="svg-wrapper">{svg}</div></div>

<div id="header">
  <div class="logos">
    <div class="logo-wrap" id="amuga-logo-wrap">
      <img src="https://media.licdn.com/dms/image/v2/C4E0BAQGi1I7tnEjaGg/company-logo_200_200/company-logo_200_200/0/1643099720996/amugaci_logo?e=2147483647&v=beta&t=K_eBcVXBqbJGghwyBBNMfUnafggSKOWAynwwlGaIjaI" alt="AMUGA"
           onerror="this.parentElement.classList.add('fallback'); this.parentElement.innerHTML='AMUGA';"/>
    </div>
    <div class="logo-divider"></div>
    <div class="logo-wrap" id="sotra-logo-wrap">
      <img src="https://dgpe.gouv.ci/fr/wp-content/uploads/2022/12/sotra.jpg" alt="SOTRA"
           onerror="this.parentElement.classList.add('fallback'); this.parentElement.innerHTML='SOTRA';"/>
    </div>
  </div>
  <div class="title-block">
    <h1>Réseau LOOM</h1>
    <p>Grand Abidjan · Réseau complet</p>
  </div>
</div>

<div id="legend">
  <div class="leg-title">Légende</div>
  <div class="leg-row"><div class="leg-line" style="background:#0cf370"></div>Lignes principales</div>
  <div class="leg-row"><div class="leg-line" style="background:#630cf3"></div>Connexions internes</div>
  <div class="leg-row"><div class="leg-dot" style="background:#fff"></div>Arrêts</div>
</div>

<div id="basemap-switcher">
  <div class="bm-label">Fond de carte</div>
  <button class="bm-btn active" data-style="dark"    onclick="switchBasemap(this)">Nuit</button>
  <button class="bm-btn"        data-style="streets" onclick="switchBasemap(this)">Rues</button>
  <button class="bm-btn"        data-style="light"   onclick="switchBasemap(this)">Jour</button>
</div>

<div id="zoom-ctrl">
  <button class="z-btn" onclick="map.zoomIn()">+</button>
  <button class="z-btn" onclick="map.zoomOut()">−</button>
</div>

<div id="tooltip">
  <div class="tt-inner">
    <div class="tt-type">Arrêt</div>
    <div class="tt-name" id="tt-name"></div>
  </div>
</div>

<script>
const GEO   = {{ minLon:{min_lon}, minLat:{min_lat}, maxLon:{max_lon}, maxLat:{max_lat} }};
const SVG_W = {svg_w}, SVG_H = {svg_h};
const CENTER = [(GEO.minLon+GEO.maxLon)/2, (GEO.minLat+GEO.maxLat)/2];

const STYLES = {{
  dark:    'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
  streets: 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
  light:   'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
}};

const map = new maplibregl.Map({{
  container: 'map',
  style: STYLES.dark,
  center: CENTER,
  zoom: 12,
  attributionControl: true,
}});

function updateSvgTransform() {{
  const wrapper = document.getElementById('svg-wrapper');
  const tl = map.project([GEO.minLon, GEO.maxLat]);
  const br = map.project([GEO.maxLon, GEO.minLat]);
  const scaleX = (br.x - tl.x) / SVG_W;
  const scaleY = (br.y - tl.y) / SVG_H;
  wrapper.style.left      = tl.x + 'px';
  wrapper.style.top       = tl.y + 'px';
  wrapper.style.width     = SVG_W + 'px';
  wrapper.style.height    = SVG_H + 'px';
  wrapper.style.transform = `scale(${{scaleX}}, ${{scaleY}})`;
}}

map.on('load',   updateSvgTransform);
map.on('move',   updateSvgTransform);
map.on('zoom',   updateSvgTransform);
map.on('resize', updateSvgTransform);

// Build station label lookup
const stationLabels = {{}};
document.querySelectorAll('text.station-label').forEach(txt => {{
  const tp = txt.querySelector('textPath');
  if (!tp) return;
  const href = (tp.getAttribute('xlink:href') || tp.getAttribute('href') || '').replace('#','');
  const label = txt.textContent.trim();
  if (href && label) stationLabels[href] = label;
}});

const pathAnchors = {{}};
document.querySelectorAll('defs path[id^="stlblp"]').forEach(p => {{
  const m = (p.getAttribute('d') || '').match(/M\\s*([\\d.]+)\\s+([\\d.]+)/);
  if (m) pathAnchors[p.id] = {{ x: parseFloat(m[1]), y: parseFloat(m[2]) }};
}});

function polyCenter(poly) {{
  const raw = poly.getAttribute('points').trim().split(/[ ,]+/).filter(Boolean);
  const pts = [];
  for (let i = 0; i < raw.length - 1; i += 2) pts.push([parseFloat(raw[i]), parseFloat(raw[i+1])]);
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  return {{ x: xs.reduce((a,b)=>a+b,0)/xs.length, y: ys.reduce((a,b)=>a+b,0)/ys.length }};
}}

function dist2(a, b) {{ return (a.x-b.x)**2 + (a.y-b.y)**2; }}

document.querySelectorAll('.station-poly').forEach(poly => {{
  const c = polyCenter(poly);
  let best = null, bestD = Infinity;
  for (const [id, anchor] of Object.entries(pathAnchors)) {{
    const d = dist2(c, anchor);
    if (d < bestD) {{ bestD = d; best = id; }}
  }}
  if (best && stationLabels[best]) poly.dataset.label = stationLabels[best];
}});

// Tooltip
const tooltip = document.getElementById('tooltip');
const ttName  = document.getElementById('tt-name');

document.querySelectorAll('.station-poly').forEach(poly => {{
  poly.addEventListener('mouseenter', e => {{
    if (!poly.dataset.label) return;
    ttName.textContent = poly.dataset.label;
    tooltip.style.display = 'block';
    moveTooltip(e);
  }});
  poly.addEventListener('mousemove', moveTooltip);
  poly.addEventListener('mouseleave', () => {{ tooltip.style.display = 'none'; }});
}});

function moveTooltip(e) {{
  const x = e.clientX, y = e.clientY;
  const tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
  let left = x + 16, top = y - 10;
  if (left + tw > window.innerWidth - 10) left = x - tw - 16;
  if (top  + th > window.innerHeight - 10) top = window.innerHeight - th - 10;
  tooltip.style.left = left + 'px';
  tooltip.style.top  = top  + 'px';
}}

function switchBasemap(btn) {{
  document.querySelectorAll('.bm-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const center = map.getCenter(), zoom = map.getZoom();
  map.setStyle(STYLES[btn.dataset.style]);
  map.once('styledata', () => {{ map.setCenter(center); map.setZoom(zoom); }});
}}
</script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
