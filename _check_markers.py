from pathlib import Path
t = Path("current_template.html").read_text(encoding="utf-8")
checks = [
 "Nearby crater and the clearest shoulder",
 "LANDING-SITE CONCEPT",
 "SURFACE MAP",
 "function habViewHeight",
 "habTerrainGeometry(180)",
 "roughness: 0.93, metalness: 0.03",
 "HemisphereLight(0xc5d4e4",
 "habViewHeight(x, z) + 0.012",
 "habCraterHeight(wx, wz)",
 "Math.min(150, Math.round(side))",
 'getElementById("hab-purpose")',
 'getElementById("des-caption")',
 "topoPayload = payload;\n        drawTerrain",
 "habCraterView = createCraterView",
 "topoRenderer.outputColorSpace = THREE.SRGBColorSpace;\n        const scene",
]
for c in checks:
    print(t.count(c), "|", c[:60].replace("\n","\\n"))
