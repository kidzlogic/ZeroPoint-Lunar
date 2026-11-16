from pathlib import Path

ROOT = Path(".")
TEMPLATE = ROOT / "current_template.html"
APP = ROOT / "lunar_web_app.py"

text = TEMPLATE.read_text(encoding="utf-8")
text = text.replace("N â†‘", "N ↑").replace("Loadingâ€¦", "Loading…").replace("kmÂ²", "km²")
TEMPLATE.write_text(text, encoding="utf-8")

app = APP.read_text(encoding="utf-8")
marker = 'HTML_TEMPLATE = """'
start = app.index(marker) + len(marker)
end = app.index('"""', start)
body = text if text.startswith("\n") else "\n" + text
if not body.endswith("\n"):
    body += "\n"
APP.write_text(app[:start] + body + '"""' + app[end + 3 :], encoding="utf-8")

# verify
import ast
ast.parse(APP.read_text(encoding="utf-8"))
checks = [
    "buildLolaHeightField",
    "applyTerrain",
    "syncCraterTerrainViews",
    "hab-hud",
    "des-hud",
    "LOLA DEM · LIVE",
    "ACESFilmicToneMapping",
    "siteSurfaceHeight",
]
t = TEMPLATE.read_text(encoding="utf-8")
for c in checks:
    print(("OK" if c in t else "MISS"), c)
print("showScreen intact", "openOptions(false);" in t[t.index("function showScreen"):t.index("function showScreen")+900])
print("synced bytes", len(body))
