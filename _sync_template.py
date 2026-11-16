# -*- coding: utf-8 -*-
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "current_template.html"
APP = ROOT / "lunar_web_app.py"

text = TEMPLATE.read_text(encoding="utf-8")
app = APP.read_text(encoding="utf-8")
start = app.index('HTML_TEMPLATE = """') + len('HTML_TEMPLATE = """')
end = app.index('"""', start)
body = text if text.startswith("\n") else "\n" + text
if not body.endswith("\n"):
    body += "\n"
APP.write_text(app[:start] + body + '"""' + app[end + 3 :], encoding="utf-8")
print("synced", len(body))
