import re
from pathlib import Path

text = Path("lunar_web_app.py").read_text(encoding="utf-8")
needle = '<script type="module">'
start = text.index(needle) + len(needle)
end = text.index("</script>", start)
js = text[start:end]
js = re.sub(r"\{%\s*if\b.*?%\}.*?\{%\s*else\s*%\}(.*?)\{%\s*endif\s*%\}", r"\1", js, flags=re.S)
js = re.sub(r"\{\{.*?\}\}", "null", js, flags=re.S)
Path("_syntax_check.mjs").write_text(js, encoding="utf-8")
print("bytes", len(js))
