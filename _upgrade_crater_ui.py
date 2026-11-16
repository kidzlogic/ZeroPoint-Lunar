# -*- coding: utf-8 -*-
"""Upgrade Habitat/Descent to real LOLA craters, richer info, and stronger 3D graphs."""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "current_template.html"
APP = ROOT / "lunar_web_app.py"

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"MISSING block: {label}")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected 1 match for {label}, found {count}")
    return text.replace(old, new, 1)

def sync_to_app(template_text: str) -> None:
    app = APP.read_text(encoding="utf-8")
    marker = 'HTML_TEMPLATE = """'
    start = app.index(marker) + len(marker)
    end = app.index('"""', start)
    body = template_text if template_text.startswith("\n") else "\n" + template_text
    if not body.endswith("\n"):
        body += "\n"
    APP.write_text(app[:start] + body + '"""' + app[end + 3 :], encoding="utf-8")
    print("Synced HTML_TEMPLATE into lunar_web_app.py")

print("bootstrap ok", ROOT)
