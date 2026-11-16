# -*- coding: utf-8 -*-
"""Restyle the five simulator screens to match reference UIs with ZPL data."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "current_template.html"
APP = ROOT / "lunar_web_app.py"

FINAL_CSS = r"""
        /* ===== FINAL SCREEN LOOK · reference fidelity + ZPL data ===== */
        @import url("https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&display=swap");
        .screen-nav { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)) 128px; gap:8px; padding:0 10px 10px; }
        .screen-nav button {
            min-height:46px; border-radius:4px; border:1px solid #2a7a96;
            background:linear-gradient(180deg,#0d2433,#081820); color:#b6d6e2;
            font:700 12px/1.15 "Orbitron","Rajdhani",sans-serif; letter-spacing:.6px; text-transform:uppercase;
            box-shadow:inset 0 0 0 1px rgba(0,229,255,.08);
        }
        .screen-nav button[aria-pressed="true"] {
            background:linear-gradient(180deg,#1a4a5c,#0e3040); color:#7af4ff;
            border-color:#5eebff; box-shadow:0 0 16px rgba(0,229,255,.25), inset 0 0 12px rgba(0,229,255,.12);
        }

        /* --- OPS / SITE CALL (Artemisite layout) --- */
        .ops-board {
            margin:0 0 14px; padding:0; border:1px solid #1c6f86; border-radius:4px;
            background:#050a0e; color:#e9f7ff; box-shadow:inset 0 0 40px rgba(0,40,60,.35);
            font-family:"Rajdhani","Segoe UI",sans-serif; overflow:hidden;
        }
        .ops-top {
            display:grid; grid-template-columns:minmax(0,1.5fr) auto minmax(240px,.75fr);
            gap:14px; align-items:center; padding:10px 14px;
            background:linear-gradient(90deg,#1a1810 0%,#0b151e 45%,#081018 100%);
            border-bottom:2px solid #c9a227;
        }
        .ops-brand img { width:44px; height:44px; border:1px solid #c9a227; border-radius:4px; background:#041018; }
        .ops-brand h2 {
            margin:0; font:800 20px/1.1 "Orbitron",sans-serif; letter-spacing:2px;
            color:#ffd700; text-shadow:0 0 12px rgba(255,215,0,.35); text-transform:uppercase;
        }
        .ops-brand p { margin:2px 0 0; color:#9ad7e4; letter-spacing:1.4px; font-size:11px; text-transform:uppercase; font-family:"Share Tech Mono",monospace; }
        .ops-met {
            text-align:center; padding:8px 14px; border:1px solid #149bae; border-radius:4px;
            background:rgba(4,16,24,.85); box-shadow:0 0 12px rgba(0,229,255,.12);
        }
        .ops-met span { display:block; color:#8fd8df; letter-spacing:1.6px; font-size:10px; font-family:"Orbitron",sans-serif; }
        .ops-met strong { color:#00e5ff; font:700 18px "Share Tech Mono",monospace; letter-spacing:1px; }
        .ops-lights { display:grid; grid-template-columns:1fr 1fr; gap:3px 14px; margin:0; padding:0; list-style:none; font-size:11px; letter-spacing:.8px; font-family:"Share Tech Mono",monospace; }
        .ops-lights b { color:#d7f6ff; }
        .ops-lights i { display:inline-block; width:8px; height:8px; margin-right:6px; border-radius:50%; background:#4dff8d; box-shadow:0 0 8px #4dff8d; }
        .ops-lights i.warn { background:#f4bd65; box-shadow:0 0 8px #f4bd65; }
        .ops-lights i.bad { background:#ff6b73; box-shadow:0 0 8px #ff6b73; }
        .ops-mid { display:grid; grid-template-columns:minmax(0,1.65fr) minmax(260px,.55fr); gap:10px; margin:10px; }
        .ops-low { display:grid; grid-template-columns:minmax(0,1.05fr) minmax(0,1fr); gap:10px; margin:0 10px 10px; }
        .ops-pane {
            min-width:0; padding:10px; border:1px solid #1c6f86; border-radius:4px;
            background:linear-gradient(180deg,#0b151e,#071018); box-shadow:inset 0 0 20px rgba(0,80,100,.1);
        }
        .ops-kicker {
            margin:0 0 8px; color:#8fd8df; letter-spacing:1.6px; font-size:10px;
            font-family:"Orbitron",sans-serif; text-transform:uppercase;
        }
        #ops-arc { display:block; width:100%; height:min(42vh,340px); background:#040c14; border:1px solid #12384a; }
        .ops-gauges { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; }
        .ops-gauges canvas {
            width:100%; height:118px; border:1px solid #1a4a5c; border-radius:4px;
            background:radial-gradient(circle at 50% 60%,#0e2430,#050a0e);
        }
        .ops-figures { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:10px; }
        .ops-figures div { padding-top:8px; border-top:1px solid #1c6f86; }
        .ops-figures span { display:block; color:#8fd8df; font-size:10px; letter-spacing:1.2px; font-family:"Orbitron",sans-serif; }
        .ops-figures strong { color:#00e5ff; font:700 22px "Share Tech Mono",monospace; }
        #ops-alt, #ops-slope {
            display:block; width:100%; height:130px; margin-top:6px;
            border:1px solid #12384a; background:#040c14;
        }
        .pros-cons { display:grid; grid-template-columns:1fr; gap:10px; max-height:min(42vh,340px); overflow:auto; }
        #ops-pros, #ops-cons { margin:0; padding-left:18px; }
        #ops-pros li, #ops-cons li {
            margin:6px 0; font-size:12px; line-height:1.4; font-family:"Share Tech Mono",monospace; letter-spacing:.3px;
        }

        /* --- PATHFINDER --- */
        .path-board {
            margin:0 0 14px; padding:0; border:1px solid rgba(52,117,139,.95); border-radius:4px;
            background:#02070d; box-shadow:inset 0 0 40px rgba(29,110,136,.2); overflow:hidden;
            font-family:"Rajdhani","Segoe UI",sans-serif;
        }
        .path-board h2 {
            margin:0; padding:14px 12px 8px; text-align:center;
            color:#66edf3 !important; letter-spacing:.18em !important;
            font:800 clamp(20px,2.4vw,36px)/1.1 "Orbitron",sans-serif !important;
            text-transform:uppercase;
            text-shadow:0 0 22px rgba(72,219,232,.9), 0 0 4px rgba(214,255,255,.95) !important;
        }
        .path-board > .purpose { margin:0 12px 8px; }
        .path-stage {
            position:relative; min-height:0; height:clamp(540px,64vh,860px); overflow:hidden;
            border-top:1px solid rgba(51,121,146,.95);
            background:#040a0f; box-shadow:inset 0 0 40px rgba(0,0,0,.55);
        }
        .path-card {
            position:absolute; top:14px; z-index:3; width:min(230px,28vw);
            border:1px solid rgba(0,229,255,.75); border-radius:2px;
            background:rgba(4,12,18,.82); padding:10px 12px;
            color:#e7f7ff; font-size:13px; line-height:1.4;
            box-shadow:0 0 18px rgba(0,229,255,.15), inset 0 0 0 1px rgba(0,229,255,.08);
            backdrop-filter:blur(6px);
        }
        .path-card h3 {
            margin:0 0 8px; color:#7af4ff; font:700 11px "Orbitron",sans-serif;
            letter-spacing:.2em; text-transform:uppercase;
        }
        .path-card p { margin:0 0 3px; font-family:"Share Tech Mono",monospace; font-size:12px; }
        .path-go { color:#4dff8d; text-shadow:0 0 10px rgba(77,255,141,.75); font-weight:700; }
        .path-legend {
            position:absolute; left:50%; bottom:12px; transform:translateX(-50%); z-index:4;
            display:flex; flex-wrap:wrap; justify-content:center; gap:6px 16px;
            padding:8px 14px; border:1px solid rgba(143,216,223,.85); border-radius:4px;
            background:rgba(4,12,18,.92); font-size:12px; letter-spacing:.06em; color:#eaf7ff;
            box-shadow:0 8px 24px rgba(0,0,0,.4); backdrop-filter:blur(4px);
        }

        /* --- TOPOGRAPHY --- */
        .topo-board {
            margin:0 0 14px; padding:0; border:1px solid #1c6f86; border-radius:4px;
            background:#05080d; color:#d7f6ff; overflow:hidden;
            font-family:"Rajdhani","Segoe UI",sans-serif;
        }
        .topo-head {
            display:flex; justify-content:space-between; align-items:center; gap:12px;
            padding:10px 14px; border-bottom:1px solid #1c6f86;
            background:linear-gradient(90deg,#0c1822,#071016);
            font:12px "Share Tech Mono",monospace; letter-spacing:1px; color:#8fd8df;
        }
        .topo-head h2 {
            margin:0; color:#7af4ff; letter-spacing:2px;
            font:800 16px "Orbitron",sans-serif; text-transform:uppercase;
            text-shadow:0 0 12px rgba(0,229,255,.35);
        }
        .topo-layout { display:grid; grid-template-columns:minmax(0,1fr) 268px; gap:0; min-height:0; }
        .topo-stage {
            position:relative; min-width:0; overflow:hidden;
            border-right:1px solid #1c6f86; background:#000;
        }
        #topo-canvas { display:block; width:100%; height:min(68vh,640px); }
        .topo-compass {
            position:absolute; top:14px; right:14px; width:84px; height:84px;
            border:1px solid #2f8ea8; border-radius:50%;
            display:grid; place-items:center; background:rgba(7,16,24,.88);
            box-shadow:0 0 16px rgba(0,229,255,.2);
        }
        .topo-legend {
            position:absolute; left:12px; bottom:12px; border:1px solid #1c6f86; border-radius:4px;
            background:rgba(7,16,24,.92); padding:10px 12px; backdrop-filter:blur(4px);
        }
        .topo-legend strong {
            display:block; margin-bottom:6px; color:#7af4ff;
            font:700 10px "Orbitron",sans-serif; letter-spacing:1.4px;
        }
        .topo-side {
            border:0; border-radius:0; background:#071018; padding:12px 14px;
            display:flex; flex-direction:column; gap:4px; overflow:auto;
        }
        .topo-side h3 {
            margin:12px 0 8px; padding-bottom:4px; border-bottom:1px solid #1c6f86;
            color:#7af4ff; font:700 11px "Orbitron",sans-serif; letter-spacing:1.6px;
        }
        .topo-side h3:first-child { margin-top:0; }
        .topo-side label {
            display:grid; grid-template-columns:1fr auto; gap:6px; align-items:center;
            margin:8px 0; font-size:12px; font-family:"Share Tech Mono",monospace;
        }
        .topo-side input[type=range] {
            width:100%; grid-column:1 / -1; accent-color:#00e5ff; height:4px;
        }
        .topo-row {
            display:flex; justify-content:space-between; align-items:center; gap:8px;
            margin:6px 0; font-size:13px; font-family:"Share Tech Mono",monospace;
        }
        .topo-row strong { color:#f4fbff; font-size:15px; }
        .topo-row input[type=checkbox] {
            appearance:none; width:42px; height:22px; border-radius:11px;
            border:1px solid #1c6f86; background:#0a1820; position:relative; cursor:pointer;
        }
        .topo-row input[type=checkbox]::after {
            content:"OFF"; position:absolute; inset:2px; border-radius:9px;
            background:#1a2a34; color:#8fd8df; font:700 9px "Orbitron",sans-serif;
            display:grid; place-items:center; letter-spacing:.5px;
        }
        .topo-row input[type=checkbox]:checked {
            border-color:#00e5ff; box-shadow:0 0 10px rgba(0,229,255,.35);
        }
        .topo-row input[type=checkbox]:checked::after {
            content:"ON"; background:linear-gradient(90deg,#0a5a6e,#00e5ff); color:#041018;
        }
        .topo-foot {
            display:flex; justify-content:space-between; gap:12px; padding:8px 14px;
            border-top:1px solid #1c6f86; font:11px "Share Tech Mono",monospace;
            letter-spacing:1px; color:#8fd8df; background:#071016;
        }

        /* --- HABITAT SCANNER --- */
        .hab-board {
            border:1px solid #14566c; border-radius:4px; background:#05080d; color:#d7f4ff;
            font-family:"Rajdhani","Segoe UI",sans-serif; overflow:hidden;
        }
        .hab-top {
            display:flex; align-items:center; gap:14px; min-height:48px; padding:8px 14px;
            background:linear-gradient(90deg,#0c1822,#071016 40%,#0c1822);
            border-bottom:1px solid #1a6a82; overflow:hidden;
        }
        .hab-brand {
            display:flex; align-items:center; gap:10px; color:#f4fbff;
            font:800 15px "Orbitron",sans-serif; letter-spacing:1.2px; text-transform:uppercase;
            white-space:nowrap;
        }
        .hab-brand img, .hab-nasa { width:32px; height:32px; flex:none; border-radius:4px; border:1px solid #2f8ea8; }
        .hab-meta {
            display:flex; flex-wrap:wrap; gap:10px 16px; align-items:center; margin-left:auto;
            color:#b7e4ef; font:12px "Share Tech Mono",monospace; letter-spacing:.4px;
        }
        .hab-meta b.ok { color:#4dff8d; text-shadow:0 0 8px rgba(77,255,141,.5); }
        .hab-body {
            flex:1; min-height:0;
            display:grid; grid-template-columns:minmax(220px,.95fr) minmax(0,1.7fr) minmax(210px,.95fr);
            gap:8px; padding:8px;
        }
        .hab-pane {
            min-height:0; display:flex; flex-direction:column;
            border:1px solid #1a6d86; border-radius:2px;
            background:linear-gradient(180deg,rgba(8,20,30,.98),rgba(4,9,14,.99));
            padding:8px 10px; box-shadow:inset 0 0 24px rgba(30,120,150,.1);
        }
        .hab-kicker {
            margin:0 0 6px; color:#7af4ff; font:700 11px "Orbitron",sans-serif; letter-spacing:1.4px;
        }
        .hab-bar p {
            display:flex; justify-content:space-between; gap:8px; margin:0 0 3px;
            color:#d5eef6; font:600 11px "Share Tech Mono",monospace; letter-spacing:.4px;
        }
        .hab-track { height:8px; background:#0d2430; border-radius:1px; overflow:hidden; border:1px solid #12384a; }
        .hab-track b { display:block; height:100%; background:linear-gradient(90deg,#128eaa,#7af4ff); box-shadow:0 0 10px #3ee0f088; }
        .hab-track.amber b { background:linear-gradient(90deg,#c45a12,#ffb15a); box-shadow:0 0 10px #ff8a2a88; }
        .hab-badge {
            display:flex; align-items:center; gap:6px; padding:4px 10px;
            font:700 11px "Orbitron",sans-serif; letter-spacing:.8px;
            background:rgba(4,10,16,.75); border:1px solid #1c6f86;
        }
        .hab-badge.ok { color:#4dff8d; border-color:#4dff8d; box-shadow:0 0 10px rgba(77,255,141,.25); }
        .hab-badge.warn { color:#ffb15a; border-color:#ffb15a; box-shadow:0 0 10px rgba(255,177,90,.25); }

        /* --- DESCENT SIMULATOR --- */
        .descent-board {
            border:1px solid #14566c; border-radius:4px; background:#050b14; color:#e7f6ff;
            font-family:"Rajdhani","Segoe UI",sans-serif; overflow:hidden;
            box-shadow:inset 0 0 40px rgba(0,60,100,.2);
        }
        .des-top {
            display:flex; align-items:center; gap:18px; min-height:56px; padding:10px 16px;
            background:linear-gradient(90deg,#071018,#0c2433 40%,#071018);
            border-bottom:1px solid #1a6d86;
        }
        .des-brand { display:flex; align-items:center; gap:12px; min-width:250px; }
        .des-mark {
            display:grid; place-items:center; width:40px; height:40px;
            border:2px solid #4da3ff; border-radius:50%; color:#7af4ff; font-size:18px;
            box-shadow:0 0 14px rgba(77,163,255,.45); background:#041018;
        }
        .des-brand strong {
            display:block; letter-spacing:2px; font:800 16px "Orbitron",sans-serif; color:#e8f4ff;
        }
        .des-brand small {
            color:#4da3ff; letter-spacing:1.6px; font:700 10px "Orbitron",sans-serif;
        }
        .des-live {
            display:flex; align-items:center; gap:8px; color:#39ff14;
            font:700 12px "Orbitron",sans-serif; letter-spacing:1.2px;
        }
        .des-live i { width:9px; height:9px; border-radius:50%; background:#39ff14; box-shadow:0 0 12px #39ff14; }
        .des-mission { margin-left:auto; letter-spacing:1px; color:#9ad7e4; font:13px "Share Tech Mono",monospace; }
        .des-mission b, .des-clock b { color:#f4fbff; }
        .des-clock { letter-spacing:1px; font:14px "Share Tech Mono",monospace; color:#9ad7e4; }
        .des-body {
            flex:1; min-height:0;
            display:grid; grid-template-columns:230px minmax(0,1fr) 250px;
            gap:10px; padding:10px;
        }
        .des-pane {
            min-height:0; border:1px solid #4da3ff55; border-radius:2px;
            background:linear-gradient(180deg,#0c1c28,#071018);
            padding:10px; display:flex; flex-direction:column;
            box-shadow:0 0 0 1px rgba(77,163,255,.08), inset 0 0 20px rgba(0,80,140,.08);
            clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px));
        }
        .des-pane > p:first-child {
            margin:0 0 6px; color:#4da3ff; letter-spacing:1.4px;
            font:700 10px "Orbitron",sans-serif;
        }
        .des-gauges {
            flex:1; min-height:0; display:grid; grid-template-rows:repeat(4,minmax(0,1fr)); gap:8px;
        }
        .des-gauges canvas {
            width:100%; height:100%; min-height:72px; display:block;
            border:1px solid #1a4a5c; border-radius:2px;
            background:radial-gradient(circle at 50% 55%,#0e2430,#050a0e);
        }
        .des-safe strong { display:block; margin-top:4px; color:#39ff14; font:800 24px "Orbitron",sans-serif; letter-spacing:.5px; text-shadow:0 0 12px rgba(57,255,20,.4); }
        .des-safe strong.hold { color:#ff8c00; text-shadow:0 0 12px rgba(255,140,0,.4); }
        .des-stage {
            position:relative; min-height:320px; border:1px solid #4da3ff66; border-radius:2px;
            overflow:hidden; background:#02060c;
            box-shadow:inset 0 0 40px rgba(0,40,80,.35), 0 0 20px rgba(77,163,255,.1);
        }
        .des-concept {
            position:absolute; top:12px; left:12px; z-index:2; max-width:min(300px,50%);
            padding:8px 12px; border:1px solid #4da3ff88; border-radius:2px;
            background:rgba(3,10,18,.86); color:#e6f4ff; font-size:12px; line-height:1.35;
            backdrop-filter:blur(4px);
        }
        .des-concept strong { display:block; color:#4da3ff; letter-spacing:1px; font:700 10px "Orbitron",sans-serif; }
        .des-caption {
            position:absolute; left:12px; bottom:12px; z-index:2; margin:0; max-width:70%;
            padding:6px 10px; border:1px solid #4da3ff66; border-radius:2px;
            background:rgba(3,10,16,.88); color:#d7f4ff; font:11px "Share Tech Mono",monospace;
        }
        .des-rate { margin:2px 0; color:#4da3ff; font:800 28px "Share Tech Mono",monospace; letter-spacing:.5px; text-shadow:0 0 10px rgba(77,163,255,.35); }
        .des-tank {
            position:relative; width:36px; height:84px; margin:0; flex:none;
            border:1px solid #3ec6ff; border-radius:6px; background:#041018; overflow:hidden;
            box-shadow:0 0 14px rgba(62,198,255,.35), inset 0 0 12px rgba(62,198,255,.15);
        }
        .des-tank i { position:absolute; left:0; right:0; bottom:0; background:linear-gradient(180deg,#b8fbff,#1278c8); box-shadow:0 0 16px #3ec6ff; }
        .des-foot {
            display:grid; grid-template-columns:1.6fr repeat(3,minmax(0,1fr)); gap:8px;
            padding:10px; background:#061018; border-top:1px solid #39ff1455;
        }
        .des-chip {
            border:1px solid #14566c; border-radius:2px; padding:10px 12px; background:#07141e;
            clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px));
        }
        .des-chip span { display:block; color:#8fd8df; font:700 10px "Orbitron",sans-serif; letter-spacing:1.2px; margin-bottom:2px; }
        .des-chip strong { display:block; color:#f4fbff; font:700 16px "Share Tech Mono",monospace; letter-spacing:.4px; }
        .des-chip.go { border-color:#39ff1466; box-shadow:0 0 14px rgba(57,255,20,.15); }
        .des-chip.go strong { color:#39ff14; text-shadow:0 0 10px rgba(57,255,20,.4); }
        .des-chip.stop strong { color:#ff6b73; }

        @media(max-width:1000px) {
            .ops-mid, .ops-low, .topo-layout, .hab-body, .des-body { grid-template-columns:1fr; }
            .path-stage { height:480px; }
            #topo-canvas { height:420px; }
            .des-gauges { grid-template-rows:none; grid-template-columns:repeat(4,minmax(0,1fr)); min-height:110px; }
            .des-foot { grid-template-columns:1fr 1fr; }
            .screen-nav { grid-template-columns:repeat(3,minmax(0,1fr)); }
        }
"""


def patch_fonts(text: str) -> str:
    old = 'family=Rajdhani:wght@500;600;700&display=swap'
    new = 'family=Rajdhani:wght@500;600;700&family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&display=swap'
    if old in text:
        text = text.replace(old, new, 1)
    return text


def inject_css(text: str) -> str:
    marker = "    </style>\n</head>"
    if "FINAL SCREEN LOOK" in text:
        # Replace existing final block
        start = text.find("        /* ===== FINAL SCREEN LOOK")
        if start < 0:
            start = text.find("/* ===== FINAL SCREEN LOOK")
        end = text.find(marker)
        if start >= 0 and end > start:
            text = text[:start] + FINAL_CSS + "\n" + text[end:]
        return text
    if marker not in text:
        raise SystemExit("style end marker not found")
    text = text.replace(marker, FINAL_CSS + "\n" + marker, 1)
    return text


def patch_nav(text: str) -> str:
    old = """    <nav class="screen-nav" aria-label="Mission screens">
        <button type="button" data-screen="ops" aria-pressed="false">Ops</button>
        <button type="button" data-screen="path" aria-pressed="false">Path</button>
        <button type="button" data-screen="terrain" aria-pressed="false">Terrain</button>
        <button type="button" data-screen="habitat" aria-pressed="false">Habitat</button>
        <button type="button" data-screen="descent" aria-pressed="true">Descent</button>
        <button type="button" id="open-options" aria-expanded="false" aria-controls="options-drawer">Options</button>
    </nav>"""
    new = """    <nav class="screen-nav" aria-label="Mission screens">
        <button type="button" data-screen="ops" aria-pressed="false">Mission &amp; Launch Ops</button>
        <button type="button" data-screen="path" aria-pressed="false">Solar-to-Ice Pathfinder</button>
        <button type="button" data-screen="terrain" aria-pressed="false">3D Topography Inspector</button>
        <button type="button" data-screen="habitat" aria-pressed="false">AI Habitat Scanner</button>
        <button type="button" data-screen="descent" aria-pressed="true">Descent Simulator</button>
        <button type="button" id="open-options" aria-expanded="false" aria-controls="options-drawer">Options</button>
    </nav>"""
    if old not in text:
        # Already patched or slightly different — try softer replace of button labels
        replacements = [
            ('data-screen="ops" aria-pressed="false">Ops</button>',
             'data-screen="ops" aria-pressed="false">Mission &amp; Launch Ops</button>'),
            ('data-screen="path" aria-pressed="false">Path</button>',
             'data-screen="path" aria-pressed="false">Solar-to-Ice Pathfinder</button>'),
            ('data-screen="terrain" aria-pressed="false">Terrain</button>',
             'data-screen="terrain" aria-pressed="false">3D Topography Inspector</button>'),
            ('data-screen="habitat" aria-pressed="false">Habitat</button>',
             'data-screen="habitat" aria-pressed="false">AI Habitat Scanner</button>'),
            ('data-screen="descent" aria-pressed="true">Descent</button>',
             'data-screen="descent" aria-pressed="true">Descent Simulator</button>'),
        ]
        for a, b in replacements:
            text = text.replace(a, b)
        return text
    return text.replace(old, new, 1)


def patch_ops_html(text: str) -> str:
    old = """                    <h2>SITE CALL</h2>
                    <p id="ops-subtitle">Waiting for a site</p>"""
    new = """                    <h2>ZERO-POINT // SITE CALL</h2>
                    <p id="ops-subtitle">Waiting for a site</p>"""
    text = text.replace(old, new, 1)

    old_kickers = [
        ("WHERE THIS SITE SITS", "ORBITAL TRAJECTORY ARC"),
        ("PROS AND CONS OF THIS SITE", "EVENT LOG // SITE CALL"),
        ("WHAT THE OPTIONS CHANGE", "FLIGHT DIRECTOR TELEMETRY"),
        ("ELEVATION AND SLOPE ALONG THE WALK", "ALTITUDE &amp; SLOPE ALONG THE WALK"),
    ]
    for a, b in old_kickers:
        text = text.replace(f'<p class="ops-kicker">{a}</p>', f'<p class="ops-kicker">{b}</p>')
    return text


def patch_topo_html(text: str) -> str:
    text = text.replace("<h2>SLOPE INSPECTOR</h2>", "<h2>3D TOPOGRAPHY &amp; SLOPE INSPECTOR</h2>", 1)
    # User line in topo head — keep dynamic system/utc, drop fictional C.CHEN if present
    old = """            <div><span id="topo-system">SYSTEM WAIT</span> Â· <span id="topo-utc">UTC</span></div>"""
    new = """            <div><span id="topo-system">SYSTEM WAIT</span> · <span id="topo-utc">UTC</span> · <span>ZERO-POINT LUNAR</span></div>"""
    if old in text:
        text = text.replace(old, new, 1)
    else:
        # try UTF-8 middle dot variants already correct
        alt = """            <div><span id="topo-system">SYSTEM WAIT</span> · <span id="topo-utc">UTC</span></div>"""
        if alt in text:
            text = text.replace(alt, new, 1)
        else:
            # mojibake form
            for form in (
                'SYSTEM WAIT</span> Â· <span id="topo-utc">UTC</span></div>',
                'SYSTEM WAIT</span> · <span id="topo-utc">UTC</span></div>',
                'SYSTEM WAIT</span> â€¢ <span id="topo-utc">UTC</span></div>',
            ):
                if form in text:
                    text = text.replace(
                        form,
                        'SYSTEM WAIT</span> · <span id="topo-utc">UTC</span> · <span>ZERO-POINT LUNAR</span></div>',
                        1,
                    )
                    break
    return text


def patch_hab_html(text: str) -> str:
    # Replace NASA meatball with ZPL logo and retitle
    old_brand = """            <div class="hab-brand">
                <svg class="hab-nasa" viewBox="0 0 64 64" aria-hidden="true">
                    <circle cx="32" cy="32" r="30" fill="#0b3d91"/>
                    <circle cx="32" cy="32" r="28" fill="none" stroke="#fff" stroke-width="1.2"/>
                    <path d="M8 40c8-16 40-16 48 0" fill="none" stroke="#fc3d21" stroke-width="4.5" stroke-linecap="round"/>
                    <path d="M14 24l4 2 4-6 4 6 4-2" fill="none" stroke="#fff" stroke-width="1"/>
                    <text x="32" y="28" text-anchor="middle" fill="#fff" font-size="11" font-family="Arial,sans-serif" font-weight="700">NASA</text>
                </svg>
                <span>HABITAT ENVIRONMENT</span>
            </div>"""
    new_brand = """            <div class="hab-brand">
                <img class="hab-nasa" src="{{ url_for('static', filename='zpl-logo.png') }}" alt="Zero-Point Lunar">
                <span>AI HABITAT VIABILITY SCANNER</span>
            </div>"""
    if old_brand in text:
        text = text.replace(old_brand, new_brand, 1)
    else:
        text = text.replace("<span>HABITAT ENVIRONMENT</span>", "<span>AI HABITAT VIABILITY SCANNER</span>", 1)
        # If SVG still present, leave it — logo swap is best-effort

    meta_old = """                <span>// DUST Â· FLARE Â· RADIATION Â· COLD / HOT</span>
                <span>// SITE: <b id="hab-site">WAITING</b></span>
                <span>// SCAN: <b id="hab-cycle">384</b></span>
                <span>// TIME: <b id="hab-clock">14:48:21 UTC</b></span>"""
    meta_new = """                <span>VIABILITY STATUS: <b class="ok" id="hab-status">ACTIVE</b></span>
                <span>MISSION: <b id="hab-site">WAITING</b></span>
                <span>SCAN CYCLE: <b id="hab-cycle">384</b></span>
                <span>TIME: <b id="hab-clock">14:48:21 UTC</b></span>"""
    if meta_old in text:
        text = text.replace(meta_old, meta_new, 1)
    else:
        # softer
        text = text.replace(
            'SITE: <b id="hab-site">WAITING</b>',
            'MISSION: <b id="hab-site">WAITING</b>',
        )
        text = text.replace("SCAN:", "SCAN CYCLE:")
    return text


def patch_descent_html(text: str) -> str:
    # Live label
    text = text.replace(
        '<div class="des-live"><i></i> PLANNING SIMULATION</div>',
        '<div class="des-live"><i></i> LIVE TELEMETRY</div>',
        1,
    )
    # Footer chip labels to match reference wording while keeping ZPL truth in values
    replacements = [
        ("<span>SITE SCREEN</span>", "<span>TOUCHDOWN SCREEN</span>"),
        ("<span>WATER ESTIMATE</span>", "<span>WATER EXTRACTED</span>"),
        ("<span>BASE KIT</span>", "<span>CARGO READY</span>"),
        ("<span>RISK SCREEN</span>", "<span>MISSION STATUS</span>"),
        ("<p>ICE AND WATER PROSPECT</p>", "<p>WATER EXTRACTION</p>"),
        ("<p>SAFE ZONE</p>", "<p>SAFE ZONE · LANDING AREA</p>"),
    ]
    for a, b in replacements:
        text = text.replace(a, b)
    return text


def patch_path_purpose(text: str) -> str:
    # Keep purpose but hide visually under title for cleaner ref look — optional class
    return text


def sync_to_app(template_text: str) -> None:
    app = APP.read_text(encoding="utf-8")
    start = app.index('HTML_TEMPLATE = """') + len('HTML_TEMPLATE = """')
    # Template begins right after opening quotes — usually with newline then <!doctype
    end = app.index('\n"""', start)
    # Keep leading newline if present
    body = template_text
    if not body.startswith("\n"):
        body = "\n" + body
    if not body.endswith("\n"):
        body = body + "\n"
    new_app = app[:start] + body + app[end + 1 :]  # keep closing """
    # Fix: end points at \n""" so we want to keep """
    # Actually app[end:] starts with \n""" — we should keep from """
    new_app = app[:start] + body.rstrip("\n") + "\n" + '"""' + app[end + 4 :]
    APP.write_text(new_app, encoding="utf-8")


def main() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    text = patch_fonts(text)
    text = inject_css(text)
    text = patch_nav(text)
    text = patch_ops_html(text)
    text = patch_topo_html(text)
    text = patch_hab_html(text)
    text = patch_descent_html(text)
    text = patch_path_purpose(text)
    TEMPLATE.write_text(text, encoding="utf-8")
    sync_to_app(text)
    # Verify
    app = APP.read_text(encoding="utf-8")
    assert "FINAL SCREEN LOOK" in text
    assert "FINAL SCREEN LOOK" in app
    assert "AI HABITAT VIABILITY SCANNER" in text
    assert "ZERO-POINT // SITE CALL" in text
    assert 'HTML_TEMPLATE = """' in app
    print("ok: restyled", TEMPLATE.name, "and synced", APP.name)
    print("template lines", text.count("\n") + 1)
    print("app lines", app.count("\n") + 1)


if __name__ == "__main__":
    main()
