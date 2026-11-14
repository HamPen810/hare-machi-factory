"""Hotfix: bound the initial Data-tab history and allow its slower read API.
Only modifies market.py and static/app.js in the deployed ZIP. Does not write DB.
"""
from pathlib import Path
from zipfile import ZipFile
import io, ast, re

archive = Path("hare-machi-render.zip")
with ZipFile(archive) as source:
    entries = [(item, source.read(item.filename)) for item in source.infolist()]
    comment = source.comment
data = {item.filename: payload for item, payload in entries}

def patch(name, old, new):
    source = data[name].decode("utf-8")
    if old not in source:
        if new in source:
            print(f"Already patched {name}: {old[:50]}")
            return
        raise RuntimeError(f"Required production anchor not found in {name}: {old!r}")
    if source.count(old) != 1:
        raise RuntimeError(f"Ambiguous production anchor {name}: {old!r}")
    data[name] = source.replace(old, new, 1).encode("utf-8")

# Latest 12 minutes is enough for the first chart. Older pages remain available
# using the existing X-Timeline-Before cursor; no historical records are removed.
source = data["market.py"].decode("utf-8")
if "start=max(0,end-59)" in source:
    patch("market.py", "start=max(0,end-59)", "start=max(0,end-11)")
elif "start=max(0,end-239)" in source:
    patch("market.py", "start=max(0,end-239)", "start=max(0,end-11)")
elif "start=max(0,end-11)" not in source:
    raise RuntimeError("Cannot recognize production timeline default window")
source = data["market.py"].decode("utf-8")
if "start=max(0,after,end-59)" in source:
    patch("market.py", "start=max(0,after,end-59)", "start=max(0,after,end-11)")
elif "start=max(0,after)" in source:
    # Existing previous incremental behavior: do not widen historical loads.
    pass
elif "start=max(0,after,end-11)" not in source:
    raise RuntimeError("Cannot recognize production timeline incremental window")

# /api/data is a read-only API. It needs a longer timeout than other UI
# requests when PostgreSQL is busy. Preserve transactional retry semantics.
js = data["static/app.js"].decode("utf-8")
if "transactional?35000:15000" in js:
    patch("static/app.js", "transactional?35000:15000",
          "transactional?35000:(path==='data'?45000:15000)")
elif "transactional?35000:(path==='data'?45000:15000)" not in js:
    raise RuntimeError("Cannot locate UI API timeout for data tab")

# Ensure cursor pagination is implemented before restricting initial history.
server = data["server.py"].decode("utf-8")
assert "X-Timeline-Before" in server, "Old-history pagination is not available; refusing to hide data"
assert "timeline_more" in data["market.py"].decode("utf-8")
assert "loadOlderTimeline" in data["static/app.js"].decode("utf-8")

ast.parse(data["market.py"].decode("utf-8"))
ast.parse(data["server.py"].decode("utf-8"))
if all(data[item.filename] == payload for item, payload in entries):
    print("Already applied; no ZIP changes")
else:
    output = io.BytesIO()
    with ZipFile(output, "w") as dest:
        dest.comment = comment
        for item, _ in entries:
            dest.writestr(item, data[item.filename])
    with ZipFile(io.BytesIO(output.getvalue())) as check:
        assert check.testzip() is None
        for item, payload in entries:
            if item.filename not in {"market.py", "static/app.js"}:
                assert check.read(item.filename) == payload, item.filename
    archive.write_bytes(output.getvalue())
print("PASS: history bounded to 12 minutes, previous pages preserved, data timeout 45s")
