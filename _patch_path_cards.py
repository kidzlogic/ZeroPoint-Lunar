# -*- coding: utf-8 -*-
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "current_template.html"
APP = ROOT / "lunar_web_app.py"

text = TEMPLATE.read_text(encoding="utf-8")
start = text.index("    const leftStatus = [")
end = text.index('        "<h3>NAVIGATION PANEL</h3>" + rightStatus;', start)
end = text.index("\n", end) + 1

new = r'''    const leftStatus = [
        "<p>Mission Status: <strong class='" + walkClass + "'>" + (opsTerrain ? (cleared ? "ACTIVE" : "HOLD") : "STANDBY") + "</strong></p>",
        "<p>Vehicle: <strong>" + who + "</strong></p>",
        "<p>Battery: <strong>" + (batteryPct == null ? "—" : batteryPct + "%") + "</strong></p>",
        "<p>Location: <strong>" + (Number.isFinite(locLat) ? locLat.toFixed(2) : pair[0].toFixed(2)) + "°, " +
        (Number.isFinite(locLon) ? locLon.toFixed(1) : pair[1].toFixed(1)) + "°</strong></p>",
        "<p>Walk call: <strong class='" + walkClass + "'>" + walkLabel + "</strong></p>"
    ].join("");
    const rightStatus = [
        "<p>Target B: <strong>" + place.toUpperCase() + "</strong></p>",
        "<p>Dist to Go: <strong>" + (km != null ? Number(km).toFixed(1) + " km" : "—") + "</strong></p>",
        "<p>ETA: <strong>" + etaText + "</strong></p>",
        "<p>Mode: <strong class='" + (opsTerrain ? walkClass : "path-gold") + "'>" + (opsTerrain ? "PATHFINDING ACTIVE" : "WAITING FOR TERRAIN") + "</strong></p>",
        "<p>Hazardous Terrain Avoided: <strong>" + kept.length + " samples</strong></p>",
        "<p>Slope samples: <strong class='path-go'>" + goodSteps + " good</strong> · <strong class='path-gold'>" + nearSteps + " close</strong> · <strong class='path-red'>" + badSteps + " blocked</strong></p>"
    ].join("");
    document.getElementById("path-status").innerHTML =
        "<h3>MISSION STATUS</h3>" + leftStatus;
    document.getElementById("path-nav").innerHTML =
        "<h3>NAVIGATION PANEL</h3>" + rightStatus;
'''

text = text[:start] + new + text[end:]
TEMPLATE.write_text(text, encoding="utf-8")

app = APP.read_text(encoding="utf-8")
a0 = app.index('HTML_TEMPLATE = """') + len('HTML_TEMPLATE = """')
a1 = app.index('"""', a0)
body = text if text.startswith("\n") else "\n" + text
if not body.endswith("\n"):
    body += "\n"
APP.write_text(app[:a0] + body + '"""' + app[a1 + 3 :], encoding="utf-8")
print("path cards patched + synced")
print("PATHFINDING ACTIVE" in text)
