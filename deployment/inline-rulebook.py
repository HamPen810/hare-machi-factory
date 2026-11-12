"""Embed rulebook tab assets directly into the game's HTML.

The game server only serves a fixed allowlist of static URLs, so separate
rulebook JS/CSS URLs returned HTTP 404 even though the files were packaged.
Embedding these small assets avoids a server change and fixes mobile display.
"""
from pathlib import Path
from zipfile import ZipFile
import io
import re

archive = Path("hare-machi-render.zip")
css_paths = [
    Path("deployment/rulebook-tabs.css"),
    Path("deployment/rulebook-custom-tabs.css"),
]
js_paths = [
    Path("deployment/rulebook-tabs.js"),
    Path("deployment/rulebook-custom-tabs.js"),
]
with ZipFile(archive) as original:
    entries = [(member, original.read(member)) for member in original.infolist()]
    comment = original.comment
    html = original.read("static/index.html").decode("utf-8")

assert 'id="tp-page-rules"' in html
assert 'id="rulebook-custom"' in html
assert 'id="rulebook-default"' in html
assert '</head>' in html and '</body>' in html
# Remove the previous unavailable /rulebook-*.js and .css references.
html = re.sub(r'<link\s+rel="stylesheet"\s+href="/rulebook-[^"]+">', '', html)
html = re.sub(r'<script\s+src="/rulebook-[^"]+"\s+defer></script>', '', html)
html = re.sub(r'<!-- RULEBOOK_INLINE_BEGIN -->.*?<!-- RULEBOOK_INLINE_END -->',
              '', html, flags=re.S)
styles = "\n".join(path.read_text(encoding="utf-8") for path in css_paths)
scripts = "\n".join(path.read_text(encoding="utf-8") for path in js_paths)
assert "</style" not in styles.lower() and "</script" not in scripts.lower()
html = html.replace("</head>",
    '<!-- RULEBOOK_INLINE_BEGIN --><style id="rb-inline-styles">\n'
    + styles + '\n</style><!-- RULEBOOK_INLINE_END --></head>', 1)
html = html.replace("</body>",
    '<script id="rb-inline-scripts">\n' + scripts + '\n</script></body>', 1)
payload = html.encode("utf-8")

with ZipFile(archive, "w") as dest:
    dest.comment = comment
    for member, data in entries:
        dest.writestr(member, payload if member.filename == "static/index.html" else data)
with ZipFile(archive) as check:
    assert check.testzip() is None
    latest = check.read("static/index.html").decode("utf-8")
    assert 'id="rb-inline-scripts"' in latest
    assert 'id="rb-inline-styles"' in latest
    assert 'rulebook-tabs.js?v=' not in latest
    assert 'rulebook-custom-tabs.js?v=' not in latest
    assert latest.count('function initRuleTabs') == 0
    assert latest.count('function init()') >= 1
    assert latest.count('function refresh()') >= 1
    for member, data in entries:
        if member.filename != "static/index.html":
            assert check.read(member.filename) == data, member.filename
print("PASS: tab JS/CSS embedded into index.html, with other game files unchanged")
