from pathlib import Path
a = Path("lunar_web_app.py").read_text(encoding="utf-8")
# extract showScreen snippet
i = a.index("function showScreen(name)")
snippet = a[i:i+900]
print(snippet[:800])
print("---")
print("broken chrome inside showScreen?", "const chromeToggle" in snippet)
print("applyTerrain in app", "applyTerrain" in a)
print("syncCrater in app", "syncCraterTerrainViews" in a)
