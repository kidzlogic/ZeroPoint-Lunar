# -*- coding: utf-8 -*-
from pathlib import Path

t = Path("current_template.html").read_text(encoding="utf-8")
a = Path("lunar_web_app.py").read_text(encoding="utf-8")
start = a.index('HTML_TEMPLATE = """') + len('HTML_TEMPLATE = """')
end = a.index('"""', start)
body = a[start:end]
tb = t if t.startswith("\n") else "\n" + t
if not tb.endswith("\n"):
    tb += "\n"
print("match", body == tb)
print("tmpl", len(t), "body", len(body))
print("Orbitron link", "Orbitron" in t[:8000])
print("flameOffsets", "flameOffsets" in t and "flameOffsets" in a)
print("SUCCESS status", 'open ? "SUCCESS"' in t)

# Resync if needed
if body != tb:
    Path("lunar_web_app.py").write_text(a[:start] + tb + '"""' + a[end + 3 :], encoding="utf-8")
    print("resync done")
