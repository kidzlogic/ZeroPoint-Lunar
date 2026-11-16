from pathlib import Path

root = Path(__file__).resolve().parent
text = (root / "lunar_web_app.py").read_text(encoding="utf-8")
descent = (root / "_descent_block.js").read_text(encoding="utf-8")
path_draw = (root / "_path_draw.js").read_text(encoding="utf-8")

start = text.index("function drawDescentStage(facts, keep) {")
end = text.index("function paintOpsBoard() {")
text = text[:start] + descent + "\n" + text[end:]

marker = "    ensurePathPhoto(pair[0], pair[1], radiusKm);"
path_at = text.index(marker)
interval_at = text.index("\nsetInterval(() => {", path_at)
# Keep the closing brace of drawPathfinder, which sits just before setInterval.
brace_at = text.rfind("\n}", path_at, interval_at)
text = text[:path_at] + path_draw + text[brace_at:]

(root / "lunar_web_app.py").write_text(text, encoding="utf-8")
print("spliced", path_at, brace_at)
