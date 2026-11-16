# -*- coding: utf-8 -*-
from pathlib import Path

app = Path("lunar_web_app.py").read_text(encoding="utf-8")
t = Path("current_template.html").read_text(encoding="utf-8")
start = app.index('HTML_TEMPLATE = """')
end = app.index('"""', start + len('HTML_TEMPLATE = """'))
print("template start", start, "end", end, "len", end - start)
print("next after template:", repr(app[end : end + 50]))
checks = [
    "FINAL SCREEN LOOK",
    "ZERO-POINT // SITE CALL",
    "AI HABITAT VIABILITY SCANNER",
    "3D TOPOGRAPHY",
    "LIVE TELEMETRY",
    "Mission &amp; Launch Ops",
    "Solar-to-Ice Pathfinder",
    "WATER EXTRACTION",
    "TOUCHDOWN SCREEN",
    "ORBITAL TRAJECTORY ARC",
]
for c in checks:
    print(f"{c!r}: tmpl={c in t} app={c in app}")
hab = t[t.find("hab-board") : t.find("hab-board") + 1200]
print("zpl logo in hab:", "zpl-logo.png" in hab)
print("nasa svg still:", "<svg class=\"hab-nasa\"" in hab)
print("hab snippet:\n", hab[:500])
