from pathlib import Path
t = Path("current_template.html").read_text(encoding="utf-8")
app = Path("lunar_web_app.py").read_text(encoding="utf-8")
marker = 'HTML_TEMPLATE = """'
start = app.index(marker) + len(marker)
end = app.index('"""', start)
body = t if t.startswith("\n") else "\n" + t
if not body.endswith("\n"):
    body += "\n"
Path("lunar_web_app.py").write_text(app[:start] + body + '"""' + app[end + 3 :], encoding="utf-8")
import ast
ast.parse(Path("lunar_web_app.py").read_text(encoding="utf-8"))
print("resync ok")
