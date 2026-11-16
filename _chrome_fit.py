# -*- coding: utf-8 -*-
"""Hamburger chrome, no-scroll fit layout, richer interactive pathfinder."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "current_template.html"
APP = ROOT / "lunar_web_app.py"

CHROME_CSS = r"""
        /* ===== CHROME + FIT + PATH TOOLS ===== */
        html, body, .shell, .workspace {
            height:100% !important; max-height:100vh !important;
            overflow:hidden !important; margin:0;
        }
        .workspace {
            display:flex !important; flex-direction:column !important;
            gap:0 !important; padding:6px 8px 8px !important; min-height:0 !important;
        }
        .chrome-toggle {
            position:fixed; z-index:80; top:10px; left:10px;
            width:44px; height:40px; padding:9px 10px;
            display:flex; flex-direction:column; justify-content:space-between;
            border:1px solid #5eb4cc; border-radius:8px;
            background:rgba(6,18,28,.96); box-shadow:0 8px 24px #000a;
            cursor:pointer;
        }
        .chrome-toggle span {
            display:block; height:3px; border-radius:2px;
            background:#7af4ff; box-shadow:0 0 8px rgba(122,244,255,.45);
        }
        .chrome-toggle[aria-expanded="true"] {
            border-color:#9af6ff; background:#12384c;
        }
        .chrome-panel {
            position:fixed; z-index:75; top:56px; left:10px;
            width:min(440px, calc(100vw - 20px));
            max-height:calc(100vh - 70px); overflow:auto;
            padding:10px; border:1px solid #5eb4cc; border-radius:12px;
            background:rgba(5,14,22,.98); box-shadow:0 18px 50px #000c;
        }
        .chrome-panel[hidden] { display:none !important; }
        .chrome-panel .console-header {
            position:static !important; flex-wrap:wrap; gap:8px;
            min-height:0; margin:0 0 10px; padding:0 0 10px;
            border-bottom:1px solid #1c6f86; background:transparent;
        }
        .chrome-panel .screen-nav {
            display:grid !important; grid-template-columns:1fr !important;
            gap:8px !important; padding:0 !important;
        }
        .chrome-panel .screen-nav button {
            min-height:42px; text-align:left; padding:10px 12px;
        }
        .chrome-backdrop {
            position:fixed; inset:0; z-index:70; background:rgba(2,8,14,.45);
        }
        .chrome-backdrop[hidden] { display:none !important; }
        .workspace > .console-header,
        .workspace > .screen-nav,
        .workspace > .app-tabs { display:none !important; }

        .screen.is-on {
            display:flex !important; flex-direction:column !important;
            flex:1 1 auto !important; min-height:0 !important;
            height:100% !important; max-height:none !important;
            overflow:hidden !important; margin:0 !important; padding:0 !important;
        }
        .screen .purpose, .screen .ops-note, .path-board > h2,
        .topo-board > .purpose, .hab-board > .purpose { display:none !important; }
        .ops-board.is-on, .path-board.is-on, .topo-board.is-on,
        .hab-board.is-on, .descent-board.is-on {
            overflow:hidden !important; height:100% !important;
        }

        /* Ops fit */
        .ops-board.is-on {
            display:grid !important;
            grid-template-rows:auto minmax(0,1.15fr) minmax(0,.95fr) !important;
            gap:6px !important;
        }
        .ops-top { min-height:0; padding:6px 10px !important; }
        .ops-mid, .ops-low {
            min-height:0 !important; margin:0 6px !important; gap:8px !important;
            grid-template-columns:minmax(0,1.25fr) minmax(0,1fr) !important;
            overflow:hidden !important;
        }
        .ops-low { margin-bottom:6px !important; }
        .ops-pane { min-height:0 !important; overflow:hidden !important; padding:6px 8px !important; }
        .ops-gauges canvas { height:min(14vh,110px) !important; min-height:88px !important; }
        #ops-arc { height:100% !important; min-height:0 !important; }
        #ops-alt, #ops-slope { height:42% !important; min-height:70px !important; }
        .ops-figures { margin-top:4px !important; }
        .ops-figures strong { font-size:16px !important; }
        .pros-cons { max-height:100% !important; overflow:auto !important; }
        .ops-interact {
            display:flex; flex-wrap:wrap; gap:6px; margin:0 6px 4px;
        }
        .ops-interact button {
            min-height:30px; padding:5px 9px; font-size:11px;
            border:1px solid #2a7a96; border-radius:6px;
            background:#0a2230; color:#d7f4ff; cursor:pointer;
        }
        .ops-interact button[aria-pressed="true"] {
            border-color:#7af4ff; background:#12384c; color:#9af6ff;
        }

        /* Path fit + tools */
        .path-board.is-on {
            display:grid !important;
            grid-template-rows:auto minmax(0,1fr) !important;
            gap:6px !important; padding:6px !important;
        }
        .path-tools {
            display:flex; flex-wrap:wrap; align-items:center; gap:6px;
            padding:4px 2px;
        }
        .path-tools button, .path-tools label {
            min-height:30px; border:1px solid #2a7a96; border-radius:6px;
            background:#0a2230; color:#d7f4ff; padding:4px 9px;
            font:700 11px "Share Tech Mono",monospace; cursor:pointer;
        }
        .path-tools button[aria-pressed="true"] {
            border-color:#7af4ff; background:#12384c; color:#9af6ff;
            box-shadow:0 0 10px rgba(122,244,255,.2);
        }
        .path-tools label {
            display:flex; align-items:center; gap:6px; cursor:default;
        }
        .path-tools input[type=range] { width:90px; accent-color:#5eebff; }
        .path-stage {
            display:grid !important;
            grid-template-columns:minmax(180px,220px) minmax(0,1fr) minmax(180px,220px) !important;
            grid-template-rows:minmax(0,1fr) auto !important;
            height:100% !important; min-height:0 !important;
            gap:8px !important; padding:6px !important; overflow:hidden !important;
        }
        .path-card {
            position:static !important; width:auto !important;
            max-height:100%; overflow:auto; font-size:12px !important;
        }
        .path-card-left { grid-column:1; grid-row:1; }
        .path-card-right { grid-column:3; grid-row:1; }
        .path-map-wrap {
            grid-column:2; grid-row:1; position:relative;
            min-height:0 !important; height:100% !important;
            border:1px solid #1c6f86; overflow:hidden; cursor:crosshair;
        }
        .path-map-wrap.is-panning { cursor:grabbing; }
        #path-map { position:absolute !important; inset:0 !important; width:100%; height:100%; }
        .path-legend {
            grid-column:1 / -1; grid-row:2;
            position:static !important; transform:none !important;
            left:auto !important; bottom:auto !important;
            width:auto; max-width:none; margin:0; justify-content:center;
            padding:5px 8px !important; font-size:11px !important;
        }
        .path-probe {
            position:absolute; z-index:5; left:10px; bottom:10px;
            max-width:min(280px,70%); padding:7px 9px;
            border:1px solid #5eb4cc; border-radius:6px;
            background:rgba(4,12,18,.94); color:#e7f7ff;
            font:12px "Share Tech Mono",monospace; pointer-events:none;
        }
        .path-probe[hidden] { display:none !important; }
        .path-probe strong { color:#7af4ff; }

        /* Topo / habitat / descent fill */
        .topo-board.is-on {
            display:grid !important; grid-template-rows:auto minmax(0,1fr) auto !important;
            gap:4px !important; padding:6px !important;
        }
        .topo-layout { min-height:0 !important; height:100% !important; margin:0 !important; }
        #topo-canvas { height:100% !important; min-height:0 !important; }
        .hab-board.is-on {
            display:flex !important; flex-direction:column !important;
            overflow:hidden !important;
        }
        .hab-body { flex:1; min-height:0 !important; height:auto !important; }
        .descent-board.is-on {
            display:flex !important; flex-direction:column !important;
            overflow:hidden !important;
        }
        .des-body { flex:1; min-height:0 !important; overflow:hidden !important; }

        @media(max-width:1100px) {
            .path-stage {
                grid-template-columns:minmax(0,1fr) minmax(0,1fr) !important;
                grid-template-rows:auto minmax(0,1fr) auto !important;
            }
            .path-card-left { grid-column:1; grid-row:1; max-height:120px; }
            .path-card-right { grid-column:2; grid-row:1; max-height:120px; }
            .path-map-wrap { grid-column:1 / -1; grid-row:2; }
            .path-legend { grid-column:1 / -1; grid-row:3; }
            .ops-mid, .ops-low { grid-template-columns:1fr 1fr !important; }
        }
        @media(max-width:800px) {
            .ops-board.is-on { grid-template-rows:auto minmax(0,1fr) minmax(0,1fr) !important; }
            .ops-mid, .ops-low { grid-template-columns:1fr !important; }
            .path-stage {
                grid-template-columns:1fr !important;
                grid-template-rows:auto auto minmax(0,1fr) auto !important;
            }
            .path-card-left, .path-card-right { grid-column:1; max-height:90px; }
            .path-map-wrap { grid-column:1; }
        }
"""

CHROME_JS = r"""
const chromeToggle = document.getElementById("chrome-toggle");
const chromePanel = document.getElementById("chrome-panel");
const chromeBackdrop = document.getElementById("chrome-backdrop");
function setChromeOpen(open) {
    if (!chromePanel || !chromeToggle) return;
    chromePanel.hidden = !open;
    if (chromeBackdrop) chromeBackdrop.hidden = !open;
    chromeToggle.setAttribute("aria-expanded", String(open));
}
if (chromeToggle) {
    chromeToggle.addEventListener("click", () => {
        setChromeOpen(chromePanel.hidden);
    });
}
if (chromeBackdrop) {
    chromeBackdrop.addEventListener("click", () => setChromeOpen(false));
}
document.querySelectorAll(".screen-nav button[data-screen]").forEach(button => {
    button.addEventListener("click", () => setChromeOpen(false));
});
const openOptionsBtn = document.getElementById("open-options");
if (openOptionsBtn) {
    openOptionsBtn.addEventListener("click", () => setChromeOpen(false));
}
document.addEventListener("keydown", event => {
    if (event.key === "Escape") setChromeOpen(false);
});

const pathView = {
    zoom: 1,
    panE: 0,
    panN: 0,
    layers: {route: true, hazards: true, grid: true, labels: true},
    inspect: false,
    probe: null,
    dragging: false,
    lastX: 0,
    lastY: 0,
    project: null
};
function pathLayerPressed() {
    document.querySelectorAll("[data-path-layer]").forEach(btn => {
        const key = btn.dataset.pathLayer;
        btn.setAttribute("aria-pressed", String(Boolean(pathView.layers[key])));
    });
    const inspectBtn = document.getElementById("path-inspect-mode");
    if (inspectBtn) inspectBtn.setAttribute("aria-pressed", String(pathView.inspect));
}
document.querySelectorAll("[data-path-layer]").forEach(btn => {
    btn.addEventListener("click", () => {
        const key = btn.dataset.pathLayer;
        pathView.layers[key] = !pathView.layers[key];
        pathLayerPressed();
        paintOpsBoard();
    });
});
const pathZoomIn = document.getElementById("path-zoom-in");
const pathZoomOut = document.getElementById("path-zoom-out");
const pathReset = document.getElementById("path-reset-view");
const pathInspect = document.getElementById("path-inspect-mode");
const pathClimb = document.getElementById("path-climb-live");
if (pathZoomIn) pathZoomIn.addEventListener("click", () => { pathView.zoom = Math.min(4, pathView.zoom * 1.25); paintOpsBoard(); });
if (pathZoomOut) pathZoomOut.addEventListener("click", () => { pathView.zoom = Math.max(0.7, pathView.zoom / 1.25); paintOpsBoard(); });
if (pathReset) pathReset.addEventListener("click", () => {
    pathView.zoom = 1; pathView.panE = 0; pathView.panN = 0; pathView.probe = null;
    const probe = document.getElementById("path-probe");
    if (probe) probe.hidden = true;
    paintOpsBoard();
});
if (pathInspect) pathInspect.addEventListener("click", () => {
    pathView.inspect = !pathView.inspect;
    pathLayerPressed();
});
if (pathClimb) {
    pathClimb.value = String(document.getElementById("max_slope_degrees").value || 18);
    pathClimb.addEventListener("input", () => {
        document.getElementById("path-climb-read").textContent = pathClimb.value + "°";
    });
    pathClimb.addEventListener("change", () => {
        const slope = document.getElementById("max_slope_degrees");
        const brief = document.getElementById("brief-slope");
        slope.value = pathClimb.value;
        if (brief) brief.value = pathClimb.value;
        document.getElementById("path-climb-read").textContent = pathClimb.value + "°";
        if (typeof reloadMission === "function") reloadMission();
        else paintOpsBoard();
    });
}
const pathMap = document.getElementById("path-map");
const pathWrap = document.querySelector(".path-map-wrap");
if (pathMap && pathWrap) {
    pathMap.addEventListener("wheel", event => {
        event.preventDefault();
        const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
        pathView.zoom = Math.max(0.7, Math.min(4, pathView.zoom * factor));
        paintOpsBoard();
    }, {passive: false});
    pathMap.addEventListener("pointerdown", event => {
        pathView.dragging = true;
        pathView.lastX = event.clientX;
        pathView.lastY = event.clientY;
        pathWrap.classList.add("is-panning");
        pathMap.setPointerCapture(event.pointerId);
    });
    pathMap.addEventListener("pointermove", event => {
        if (!pathView.dragging || !pathView.project) return;
        const dx = event.clientX - pathView.lastX;
        const dy = event.clientY - pathView.lastY;
        pathView.lastX = event.clientX;
        pathView.lastY = event.clientY;
        const scale = pathView.project.kmPerPx / pathView.zoom;
        pathView.panE -= dx * scale;
        pathView.panN += dy * scale;
        paintOpsBoard();
    });
    pathMap.addEventListener("pointerup", event => {
        pathView.dragging = false;
        pathWrap.classList.remove("is-panning");
        try { pathMap.releasePointerCapture(event.pointerId); } catch (err) {}
    });
    pathMap.addEventListener("click", event => {
        if (!pathView.inspect || !pathView.project) return;
        const rect = pathMap.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        const east = pathView.project.vMinE + (x / rect.width) * (pathView.project.vMaxE - pathView.project.vMinE);
        const north = pathView.project.vMaxN - (y / rect.height) * (pathView.project.vMaxN - pathView.project.vMinN);
        let nearest = null;
        let best = Infinity;
        (pathView.project.samples || []).forEach(sample => {
            const d = Math.hypot(sample.e - east, sample.n - north);
            if (d < best) { best = d; nearest = sample; }
        });
        const probe = document.getElementById("path-probe");
        if (!probe) return;
        if (!nearest || best > 3.2) {
            pathView.probe = {e: east, n: north, text: "Probe · E " + east.toFixed(2) + " km · N " + north.toFixed(2) + " km · no hazard sample"};
        } else {
            pathView.probe = nearest;
        }
        probe.hidden = false;
        probe.innerHTML = pathView.probe.text || (
            "<strong>HAZARD SAMPLE</strong><br>Slope " + nearest.slope.toFixed(1) +
            "° · E " + nearest.e.toFixed(2) + " km · N " + nearest.n.toFixed(2) + " km"
        );
        paintOpsBoard();
    });
}
pathLayerPressed();

document.querySelectorAll("[data-ops-action]").forEach(btn => {
    btn.addEventListener("click", () => {
        const action = btn.dataset.opsAction;
        const dest = document.getElementById("plan-destination");
        if (action === "next-site" && dest) {
            dest.selectedIndex = (dest.selectedIndex + 1) % dest.options.length;
            dest.dispatchEvent(new Event("change", {bubbles: true}));
        } else if (action === "prev-site" && dest) {
            dest.selectedIndex = (dest.selectedIndex - 1 + dest.options.length) % dest.options.length;
            dest.dispatchEvent(new Event("change", {bubbles: true}));
        } else if (action === "toggle-shelter") {
            const shelter = document.getElementById("brief-shelter");
            if (shelter) {
                shelter.value = shelter.value === "yes" ? "no" : "yes";
                shelter.dispatchEvent(new Event("change", {bubbles: true}));
            }
        } else if (action === "focus-gauges") {
            document.querySelectorAll(".ops-pane").forEach(pane => pane.classList.remove("is-focus"));
            const gauges = document.querySelector(".ops-low .ops-pane");
            if (gauges) gauges.classList.add("is-focus");
        }
        paintOpsBoard();
    });
});
"""


def sync(text: str) -> None:
    app = APP.read_text(encoding="utf-8")
    start = app.index('HTML_TEMPLATE = """') + len('HTML_TEMPLATE = """')
    end = app.index('"""', start)
    body = text if text.startswith("\n") else "\n" + text
    if not body.endswith("\n"):
        body += "\n"
    APP.write_text(app[:start] + body + '"""' + app[end + 3 :], encoding="utf-8")


def main() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    if "CHROME + FIT + PATH TOOLS" not in text:
        text = text.replace("    </style>", CHROME_CSS + "\n    </style>", 1)
        print("inserted chrome/fit CSS")
    else:
        # replace existing block between markers if re-run
        start = text.index("        /* ===== CHROME + FIT + PATH TOOLS ===== */")
        end = text.index("    </style>", start)
        text = text[:start] + CHROME_CSS.strip("\n") + "\n" + text[end:]
        print("replaced chrome/fit CSS")

    old_top = """    <header id="mission" class="console-header">
        <div class="brand">
            <img class="mission-patch" src="{{ url_for('static', filename='zpl-logo.png') }}" alt="Zero-Point Lunar logo">
            <div><h1>ZERO-POINT LUNAR</h1><div class="subtitle">SHACKLETON TRAVERSE</div></div>
        </div>
        <div class="mission-name"><strong>Site call:</strong> walk, weather, and the touchdown corridor</div>
        <div class="live"><i class="live-dot"></i>NOAA X-RAY · NASA LRO DATA</div>
    </header>

    <nav class="app-tabs" role="tablist" aria-label="Zero-Point Lunar">
        <button id="page-home" type="button" role="tab" aria-selected="true" data-page="home">Home</button>
        <button id="page-simulator" type="button" role="tab" aria-selected="false" data-page="simulator">Simulator</button>
        <button id="page-data" type="button" role="tab" aria-selected="false" data-page="data">Data</button>
    </nav>
    <nav class="screen-nav" aria-label="Mission screens">
        <button type="button" data-screen="ops" aria-pressed="false">Mission &amp; Launch Ops</button>
        <button type="button" data-screen="path" aria-pressed="false">Solar-to-Ice Pathfinder</button>
        <button type="button" data-screen="terrain" aria-pressed="false">3D Topography Inspector</button>
        <button type="button" data-screen="habitat" aria-pressed="false">AI Habitat Scanner</button>
        <button type="button" data-screen="descent" aria-pressed="true">Descent Simulator</button>
        <button type="button" id="open-options" aria-expanded="false" aria-controls="options-drawer">Options</button>
    </nav>"""

    new_top = """    <button type="button" id="chrome-toggle" class="chrome-toggle" aria-expanded="false" aria-controls="chrome-panel" aria-label="Open mission menu">
        <span></span><span></span><span></span>
    </button>
    <div id="chrome-backdrop" class="chrome-backdrop" hidden></div>
    <div id="chrome-panel" class="chrome-panel" hidden>
    <header id="mission" class="console-header">
        <div class="brand">
            <img class="mission-patch" src="{{ url_for('static', filename='zpl-logo.png') }}" alt="Zero-Point Lunar logo">
            <div><h1>ZERO-POINT LUNAR</h1><div class="subtitle">SHACKLETON TRAVERSE</div></div>
        </div>
        <div class="mission-name"><strong>Site call:</strong> walk, weather, and the touchdown corridor</div>
        <div class="live"><i class="live-dot"></i>NOAA X-RAY · NASA LRO DATA</div>
    </header>

    <nav class="app-tabs" role="tablist" aria-label="Zero-Point Lunar">
        <button id="page-home" type="button" role="tab" aria-selected="true" data-page="home">Home</button>
        <button id="page-simulator" type="button" role="tab" aria-selected="false" data-page="simulator">Simulator</button>
        <button id="page-data" type="button" role="tab" aria-selected="false" data-page="data">Data</button>
    </nav>
    <nav class="screen-nav" aria-label="Mission screens">
        <button type="button" data-screen="ops" aria-pressed="false">Mission &amp; Launch Ops</button>
        <button type="button" data-screen="path" aria-pressed="false">Solar-to-Ice Pathfinder</button>
        <button type="button" data-screen="terrain" aria-pressed="false">3D Topography Inspector</button>
        <button type="button" data-screen="habitat" aria-pressed="false">AI Habitat Scanner</button>
        <button type="button" data-screen="descent" aria-pressed="true">Descent Simulator</button>
        <button type="button" id="open-options" aria-expanded="false" aria-controls="options-drawer">Options</button>
    </nav>
    </div>"""

    if 'id="chrome-toggle"' not in text:
        if old_top not in text:
            raise SystemExit("top chrome HTML not found")
        text = text.replace(old_top, new_top, 1)
        print("wrapped chrome panel")
    else:
        print("chrome panel already present")

    ops_insert = """        <p class="purpose" id="ops-purpose"><b>DECIDE THE SITE</b> Pros and cons of this crater for the options you set.</p>
        <div class="ops-interact" aria-label="Ops actions">
            <button type="button" data-ops-action="prev-site">Prev site</button>
            <button type="button" data-ops-action="next-site">Next site</button>
            <button type="button" data-ops-action="toggle-shelter">Toggle shelter</button>
            <button type="button" data-ops-action="focus-gauges">Focus gauges</button>
        </div>
        <div class="ops-mid">"""
    if 'data-ops-action="next-site"' not in text:
        text = text.replace(
            """        <p class="purpose" id="ops-purpose"><b>DECIDE THE SITE</b> Pros and cons of this crater for the options you set.</p>
        <div class="ops-mid">""",
            ops_insert,
            1,
        )
        print("added ops interact controls")

    path_old = """    <section class="path-board screen" id="path-board" data-screen="path" hidden>
        <h2>SOLAR-TO-ICE PROXIMITY PATHFINDER</h2>
        <p class="purpose" id="path-purpose"><b>CAN THE CREW WALK IT</b> Green holds the climb limit. Gold is the power shoulder. Cyan is the cold floor. Red is blocked.</p>
        <div class="path-stage">
            <aside class="path-card path-card-left" id="path-status"></aside>
            <div class="path-map-wrap">
                <canvas id="path-map" role="img" aria-label="Moon photo centered on the walk, colored by slope against the climb limit"></canvas>
            </div>
            <aside class="path-card path-card-right" id="path-nav"></aside>
            <div class="path-legend" aria-label="Path legend">
                <span><i class="good"></i>Good · under the limit</span>
                <span><i class="near"></i>Close · within 3°</span>
                <span><i class="bad"></i>Blocked · at or over</span>
                <span><i class="gold"></i>Shoulder · start</span>
                <span><i class="floor"></i>Floor · low end</span>
            </div>
        </div>
        <p class="ops-note">The walk is centered on the Moon photo. Green is good. Gold is close to the limit. Red is blocked. Dots are steep samples, not ice.</p>
    </section>"""

    path_new = """    <section class="path-board screen" id="path-board" data-screen="path" hidden>
        <h2>SOLAR-TO-ICE PROXIMITY PATHFINDER</h2>
        <p class="purpose" id="path-purpose"><b>CAN THE CREW WALK IT</b> Green holds the climb limit. Gold is the power shoulder. Cyan is the cold floor. Red is blocked.</p>
        <div class="path-tools" aria-label="Pathfinder tools">
            <button type="button" data-path-layer="route" aria-pressed="true">Route</button>
            <button type="button" data-path-layer="hazards" aria-pressed="true">Hazards</button>
            <button type="button" data-path-layer="grid" aria-pressed="true">Grid</button>
            <button type="button" data-path-layer="labels" aria-pressed="true">Labels</button>
            <button type="button" id="path-inspect-mode" aria-pressed="false">Inspect</button>
            <button type="button" id="path-zoom-out" title="Zoom out">−</button>
            <button type="button" id="path-zoom-in" title="Zoom in">+</button>
            <button type="button" id="path-reset-view">Reset view</button>
            <label>Climb <b id="path-climb-read">18°</b><input id="path-climb-live" type="range" min="10" max="28" step="1" value="18"></label>
        </div>
        <div class="path-stage">
            <aside class="path-card path-card-left" id="path-status"></aside>
            <div class="path-map-wrap">
                <canvas id="path-map" role="img" aria-label="Moon photo centered on the walk, colored by slope against the climb limit"></canvas>
                <div class="path-probe" id="path-probe" hidden></div>
            </div>
            <aside class="path-card path-card-right" id="path-nav"></aside>
            <div class="path-legend" aria-label="Path legend">
                <span><i class="good"></i>Good · under the limit</span>
                <span><i class="near"></i>Close · within 3°</span>
                <span><i class="bad"></i>Blocked · at or over</span>
                <span><i class="gold"></i>Shoulder · start</span>
                <span><i class="floor"></i>Floor · low end</span>
            </div>
        </div>
        <p class="ops-note">The walk is centered on the Moon photo. Green is good. Gold is close to the limit. Red is blocked. Dots are steep samples, not ice.</p>
    </section>"""

    if 'id="path-tools"' not in text and "path-tools" not in text:
        if path_old not in text:
            raise SystemExit("path board HTML not found")
        text = text.replace(path_old, path_new, 1)
        print("upgraded path board")
    else:
        print("path tools already present")

    # Patch drawPathfinder viewport to use pathView zoom/pan and layers
    marker = "    halfE *= 1.12;\n    halfN *= 1.12;\n    const vMinE = midE - halfE;\n    const vMaxE = midE + halfE;\n    const vMinN = midN - halfN;\n    const vMaxN = midN + halfN;"
    replacement = """    halfE *= 1.12;
    halfN *= 1.12;
    if (typeof pathView !== "undefined") {
        halfE /= pathView.zoom;
        halfN /= pathView.zoom;
        midE += pathView.panE;
        midN += pathView.panN;
    }
    const vMinE = midE - halfE;
    const vMaxE = midE + halfE;
    const vMinN = midN - halfN;
    const vMaxN = midN + halfN;
    if (typeof pathView !== "undefined") {
        pathView.project = {
            vMinE, vMaxE, vMinN, vMaxN,
            kmPerPx: (vMaxE - vMinE) / Math.max(1, width),
            samples: kept.map(item => ({e: item.km.e, n: item.km.n, slope: item.slope}))
        };
    }"""
    if "pathView.project =" not in text:
        if marker not in text:
            print("WARN: path viewport marker missing")
        else:
            text = text.replace(marker, replacement, 1)
            print("patched path viewport for zoom/pan")

    # Wrap hazard drawing and grid/labels with layer checks - soft approach via CSS/JS flags in draw
    # Insert layer guards before common draw sections by replacing unique comments if present.
    # Safer: after kept samples loop drawing, we already store samples. Patch grid draw.
    grid_marker = None
    # Find a unique line near grid drawing if any; many path drawings are procedural.
    # Add layer short-circuits by patching after context.clear / photo draw for hazards loop.
    hazard_loop = "    kept.forEach(item => {"
    if "pathView.layers.hazards" not in text and hazard_loop in text:
        text = text.replace(
            hazard_loop,
            "    if (typeof pathView === \"undefined\" || pathView.layers.hazards) kept.forEach(item => {",
            1,
        )
        # Need to close the if - the forEach already closes with }); 
        # Actually replacing `kept.forEach` with `if (...) kept.forEach` is fine syntactically.
        print("gated hazard layer")

    # Route polyline often starts with context.strokeStyle for green/cyan - harder.
    # Add after fit established a note in right panel about controls.
    right_status_end = '        "<p>Slope samples: <strong class=\'path-go\'>" + goodSteps + " good</strong> · <strong class=\'path-gold\'>" + nearSteps + " close</strong> · <strong class=\'path-red\'>" + badSteps + " blocked</strong></p>"\n    ].join("");'
    right_extra = '        "<p>Slope samples: <strong class=\'path-go\'>" + goodSteps + " good</strong> · <strong class=\'path-gold\'>" + nearSteps + " close</strong> · <strong class=\'path-red\'>" + badSteps + " blocked</strong></p>",\n        "<p>View: <strong>" + (typeof pathView === "undefined" ? "1.0" : pathView.zoom.toFixed(2)) + "×</strong> · drag pan · wheel zoom · inspect for samples</p>"\n    ].join("");'
    if "wheel zoom" not in text and right_status_end in text:
        text = text.replace(right_status_end, right_extra, 1)
        print("enriched path nav readout")

    # Gate route drawing roughly: look for routeKm.forEach drawing strokes
    # Insert JS before showScreen init
    if "const chromeToggle = document.getElementById(\"chrome-toggle\")" not in text:
        anchor = 'document.querySelectorAll(".app-tabs [role=\'tab\']").forEach(tab => {'
        if anchor not in text:
            raise SystemExit("JS anchor not found")
        text = text.replace(anchor, CHROME_JS + "\n" + anchor, 1)
        print("inserted chrome/path JS")
    else:
        print("chrome JS already present")

    # Soft-gate route/grid by wrapping later unique snippets if available
    # Grid: many files draw with strokeStyle "#1c6f86" loops - skip if fragile.

    # Also patch route drawing with layer check near "PATHFINDING" - find routeKm length draw
    route_draw = "    if (routeKm.length > 1) {"
    if route_draw in text and "pathView.layers.route" not in text:
        text = text.replace(
            route_draw,
            '    if (routeKm.length > 1 && (typeof pathView === "undefined" || pathView.layers.route)) {',
            1,
        )
        print("gated route layer")

    TEMPLATE.write_text(text, encoding="utf-8")
    sync(text)
    print("synced lunar_web_app.py")


if __name__ == "__main__":
    main()
