# -*- coding: utf-8 -*-
"""Fix overlapping UI: side panels off the map, gauge text, habitat spacing, scroll."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "current_template.html"
APP = ROOT / "lunar_web_app.py"

LAYOUT_CSS = r"""
        /* ===== NO-OVERLAP LAYOUT FIX ===== */
        html, body { height:100%; overflow:hidden; }
        .workspace { overflow:hidden; }
        .screen.is-on {
            display:flex; flex-direction:column; flex:1; min-height:0;
            overflow:auto; margin:0 10px 10px;
        }
        .ops-board.is-on, .path-board.is-on, .topo-board.is-on,
        .hab-board.is-on, .descent-board.is-on {
            overflow:auto;
        }

        /* Ops: room for dials + figures, no clipped stacks */
        .ops-gauges { gap:10px; align-items:stretch; }
        .ops-gauges canvas {
            width:100%; height:148px; min-height:148px;
            border:1px solid #1a4a5c; border-radius:4px;
            background:radial-gradient(circle at 50% 55%,#0e2430,#050a0e);
        }
        .ops-figures {
            display:grid; grid-template-columns:repeat(3,minmax(0,1fr));
            gap:10px; margin-top:10px; flex:none;
        }
        .ops-figures div {
            padding:8px 6px 6px; border-top:1px solid #1c6f86;
            min-width:0;
        }
        .ops-figures span {
            display:block; color:#8fd8df; font-size:10px;
            letter-spacing:1.2px; font-family:"Orbitron",sans-serif;
            margin-bottom:2px;
        }
        .ops-figures strong {
            display:block; color:#00e5ff;
            font:700 20px/1.2 "Share Tech Mono",monospace;
            word-break:break-word;
        }
        .ops-low { align-items:start; }
        .ops-pane { overflow:auto; }
        .pros-cons { max-height:none; overflow:visible; }
        .purpose {
            white-space:normal; overflow-wrap:anywhere; line-height:1.4;
        }

        /* Pathfinder: cards beside the map, legend under it */
        .path-stage {
            display:grid !important;
            grid-template-columns:minmax(200px,240px) minmax(0,1fr) minmax(200px,240px);
            grid-template-rows:minmax(320px,1fr) auto;
            gap:10px; padding:10px;
            position:relative; min-height:0;
            height:clamp(480px,62vh,780px);
            overflow:hidden;
            border-top:1px solid rgba(51,121,146,.95);
            background:#040a0f;
        }
        .path-map-wrap {
            grid-column:2; grid-row:1; position:relative;
            min-width:0; min-height:0; overflow:hidden;
            border:1px solid rgba(51,121,146,.7); background:#02070d;
        }
        #path-map {
            position:absolute !important; inset:0 !important;
            display:block; width:100%; height:100%; min-height:0;
            background:#040a0f;
        }
        .path-card {
            position:static !important; top:auto !important;
            left:auto !important; right:auto !important;
            z-index:auto; width:auto !important;
            max-width:none; align-self:stretch;
            overflow:auto; max-height:100%;
        }
        .path-card-left { grid-column:1; grid-row:1; }
        .path-card-right { grid-column:3; grid-row:1; }
        .path-legend {
            grid-column:1 / -1; grid-row:2;
            position:static !important; left:auto !important; bottom:auto !important;
            transform:none !important; z-index:auto;
            width:auto; max-width:none; margin:0;
            justify-content:center;
        }

        /* Habitat: stop overlays eating the drawing / columns */
        .hab-board.is-on { overflow:auto; }
        .hab-body {
            flex:1; min-height:min(72vh,820px);
            align-items:stretch;
        }
        .hab-left, .hab-center, .hab-right {
            min-height:0; overflow:auto;
            display:flex; flex-direction:column; gap:8px;
        }
        .hab-pane { overflow:auto; }
        .hab-crater {
            flex:1.4; min-height:280px; position:relative;
            overflow:hidden; padding:0;
        }
        .hab-concept {
            position:absolute; top:10px; left:10px; z-index:4;
            width:min(280px,46%); max-height:42%;
            overflow:auto; border:1px solid #54bfd1;
            background:rgba(4,10,16,.94); color:#e7f7ff;
            box-shadow:0 8px 22px #0008;
        }
        .hab-concept[open] { max-height:min(58%,320px); }
        .hab-base-line {
            position:absolute; left:8px; right:8px; bottom:8px; z-index:3;
            margin:0; padding:7px 8px; max-height:28%; overflow:auto;
            border:1px solid #1c8eaa; background:rgba(4,10,16,.9);
            color:#e7f7ff; font-size:12px; line-height:1.35;
        }
        .hab-badges { z-index:4; }
        .hab-thermal { flex:0 0 auto; min-height:210px; }
        .hab-ice-side p {
            display:flex; flex-direction:column; gap:2px;
            margin:4px 0 0; color:#9fd4e2; font-size:11px; line-height:1.25;
        }
        .hab-ice-side strong { display:block; color:#f4fbff; font-size:13px; }
        .hab-bar p {
            display:flex; justify-content:space-between; align-items:baseline;
            gap:10px; margin:0 0 3px;
        }
        .hab-bar p > span:last-child {
            flex:none; text-align:right; color:#f4fbff; white-space:nowrap;
        }
        .hab-geo { overflow:auto; }
        .hab-briefs p { margin:0 0 6px; }

        /* Descent overlays: keep readable, don't cover the whole stage */
        .des-concept {
            max-width:min(260px,40%); max-height:30%; overflow:auto;
        }
        .des-caption {
            max-width:min(55%,420px); max-height:22%; overflow:auto;
        }
        .des-body { overflow:auto; }
        .des-stage { min-height:300px; }

        /* Topo chips / fact card stay clear of the compass */
        .topo-fact { max-width:min(280px,42%); }
        .topo-legend { max-width:min(200px,40%); }

        @media(max-width:1100px) {
            .path-stage {
                grid-template-columns:1fr 1fr !important;
                grid-template-rows:auto minmax(300px,1fr) auto !important;
                height:auto; min-height:560px;
            }
            .path-card-left { grid-column:1; grid-row:1; }
            .path-card-right { grid-column:2; grid-row:1; }
            .path-map-wrap { grid-column:1 / -1; grid-row:2; min-height:360px; }
            .path-legend { grid-column:1 / -1; grid-row:3; }
            .hab-body { grid-template-columns:1fr; min-height:0; }
            .hab-crater { min-height:320px; }
        }
        @media(max-width:700px) {
            .path-stage { grid-template-columns:1fr !important; }
            .path-card-left, .path-card-right { grid-column:1; grid-row:auto; max-height:160px; }
            .path-map-wrap { grid-column:1; grid-row:auto; min-height:300px; }
            .ops-gauges { grid-template-columns:1fr 1fr; }
            .ops-gauges canvas { height:132px; min-height:132px; }
        }
"""

GAUGE_OLD = '''function opsGauge(canvas, fraction, caption, label, color) {
    const fit = opsFit(canvas);
    if (!fit) return;
    const {context, width, height} = fit;
    const cx = width / 2;
    const cy = height * 0.52;
    const radius = Math.min(width, height) * 0.36;
    const start = Math.PI * 0.75;
    const sweep = Math.PI * 1.5;
    const clamped = Math.max(0, Math.min(1, fraction));
    context.clearRect(0, 0, width, height);
    context.beginPath();
    context.arc(cx, cy, radius + 8, 0, Math.PI * 2);
    context.strokeStyle = "#12384a";
    context.lineWidth = 1;
    context.stroke();
    context.lineWidth = 10;
    context.strokeStyle = "#102833";
    context.beginPath();
    context.arc(cx, cy, radius, start, start + sweep);
    context.stroke();
    context.strokeStyle = color;
    context.shadowColor = color;
    context.shadowBlur = 12;
    context.beginPath();
    context.arc(cx, cy, radius, start, start + sweep * clamped);
    context.stroke();
    context.shadowBlur = 0;
    context.strokeStyle = "#8fd8df";
    context.lineWidth = 1;
    for (let tick = 0; tick <= 8; tick += 1) {
        const angle = start + sweep * (tick / 8);
        context.beginPath();
        context.moveTo(cx + Math.cos(angle) * (radius - 14), cy + Math.sin(angle) * (radius - 14));
        context.lineTo(cx + Math.cos(angle) * (radius - 6), cy + Math.sin(angle) * (radius - 6));
        context.stroke();
    }
    const needle = start + sweep * clamped;
    context.strokeStyle = "#f4fbff";
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(cx, cy);
    context.lineTo(cx + Math.cos(needle) * (radius - 16), cy + Math.sin(needle) * (radius - 16));
    context.stroke();
    context.fillStyle = color;
    context.beginPath();
    context.arc(cx, cy, 4, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#f4fbff";
    context.textAlign = "center";
    context.font = "700 17px Share Tech Mono, monospace";
    context.fillText(caption, cx, cy + radius * 0.48);
    context.fillStyle = "#8fd8df";
    context.font = "700 10px Orbitron, Rajdhani, sans-serif";
    context.fillText(label, cx, height - 8);
}'''

GAUGE_NEW = '''function opsGauge(canvas, fraction, caption, label, color) {
    const fit = opsFit(canvas);
    if (!fit) return;
    const {context, width, height} = fit;
    const cx = width / 2;
    const cy = height * 0.46;
    const radius = Math.min(width * 0.38, height * 0.32);
    const start = Math.PI * 0.75;
    const sweep = Math.PI * 1.5;
    const clamped = Math.max(0, Math.min(1, fraction));
    context.clearRect(0, 0, width, height);
    context.beginPath();
    context.arc(cx, cy, radius + 8, 0, Math.PI * 2);
    context.strokeStyle = "#12384a";
    context.lineWidth = 1;
    context.stroke();
    context.lineWidth = 10;
    context.strokeStyle = "#102833";
    context.beginPath();
    context.arc(cx, cy, radius, start, start + sweep);
    context.stroke();
    context.strokeStyle = color;
    context.shadowColor = color;
    context.shadowBlur = 12;
    context.beginPath();
    context.arc(cx, cy, radius, start, start + sweep * clamped);
    context.stroke();
    context.shadowBlur = 0;
    context.strokeStyle = "#8fd8df";
    context.lineWidth = 1;
    for (let tick = 0; tick <= 8; tick += 1) {
        const angle = start + sweep * (tick / 8);
        context.beginPath();
        context.moveTo(cx + Math.cos(angle) * (radius - 12), cy + Math.sin(angle) * (radius - 12));
        context.lineTo(cx + Math.cos(angle) * (radius - 5), cy + Math.sin(angle) * (radius - 5));
        context.stroke();
    }
    const needle = start + sweep * clamped;
    context.strokeStyle = "#f4fbff";
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(cx, cy);
    context.lineTo(cx + Math.cos(needle) * (radius - 14), cy + Math.sin(needle) * (radius - 14));
    context.stroke();
    context.fillStyle = color;
    context.beginPath();
    context.arc(cx, cy, 4, 0, Math.PI * 2);
    context.fill();
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillStyle = "#f4fbff";
    const valueSize = Math.max(13, Math.min(18, Math.floor(width * 0.12)));
    context.font = "700 " + valueSize + "px Share Tech Mono, monospace";
    context.fillText(String(caption), cx, cy + 2);
    context.textBaseline = "alphabetic";
    context.fillStyle = "#8fd8df";
    context.font = "700 10px Orbitron, Rajdhani, sans-serif";
    context.fillText(String(label), cx, Math.min(height - 10, cy + radius + 22));
}'''


def fix_mojibake(text: str) -> str:
    replacements = {
        "Â·": "·",
        "Â°": "°",
        "Âµ": "µ",
        "Ã—": "×",
        "â€”": "—",
        "â€“": "–",
        "â€™": "'",
        "â€˜": "'",
        "â€œ": '"',
        "â€": '"',
        "â—Ž": "◇",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def main() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    if "NO-OVERLAP LAYOUT FIX" not in text:
        if "    </style>" not in text:
            raise SystemExit("style end not found")
        text = text.replace("    </style>", LAYOUT_CSS + "\n    </style>", 1)
        print("inserted layout CSS")
    else:
        print("layout CSS already present")

    path_old = """        <div class="path-stage">
            <canvas id="path-map" role="img" aria-label="Moon photo centered on the walk, colored by slope against the climb limit"></canvas>
            <aside class="path-card path-card-left" id="path-status"></aside>
            <aside class="path-card path-card-right" id="path-nav"></aside>
            <div class="path-legend" aria-label="Path legend">"""
    path_new = """        <div class="path-stage">
            <aside class="path-card path-card-left" id="path-status"></aside>
            <div class="path-map-wrap">
                <canvas id="path-map" role="img" aria-label="Moon photo centered on the walk, colored by slope against the climb limit"></canvas>
            </div>
            <aside class="path-card path-card-right" id="path-nav"></aside>
            <div class="path-legend" aria-label="Path legend">"""
    if path_old in text:
        text = text.replace(path_old, path_new, 1)
        print("wrapped path map")
    elif "path-map-wrap" in text:
        print("path map already wrapped")
    else:
        print("WARN: path stage HTML not matched")

    ice_old = '<p id="hab-ice-side-note">Low floor samples over the limit<strong id="hab-floor-count">'
    ice_new = '<p id="hab-ice-side-note">Low floor samples over the limit <strong id="hab-floor-count">'
    if ice_old in text:
        text = text.replace(ice_old, ice_new, 1)
        print("fixed habitat floor note spacing")

    # Descent should start hidden like the other boards
    des_old = '<section class="descent-board screen is-on" id="descent-board" data-screen="descent">'
    des_new = '<section class="descent-board screen" id="descent-board" data-screen="descent" hidden>'
    if des_old in text:
        text = text.replace(des_old, des_new, 1)
        print("normalized descent board hidden state")

    if GAUGE_OLD in text:
        text = text.replace(GAUGE_OLD, GAUGE_NEW, 1)
        print("updated opsGauge layout")
    elif "cy + radius + 22" in text:
        print("opsGauge already updated")
    else:
        print("WARN: opsGauge block not matched")

    text = fix_mojibake(text)
    print("normalized encoding artifacts")

    TEMPLATE.write_text(text, encoding="utf-8")

    # Sync into Flask app HTML_TEMPLATE
    app = APP.read_text(encoding="utf-8")
    start = app.index('HTML_TEMPLATE = """') + len('HTML_TEMPLATE = """')
    end = app.index('"""', start)
    body = text if text.startswith("\n") else "\n" + text
    if not body.endswith("\n"):
        body += "\n"
    APP.write_text(app[:start] + body + '"""' + app[end + 3 :], encoding="utf-8")
    print("synced lunar_web_app.py")


if __name__ == "__main__":
    main()
