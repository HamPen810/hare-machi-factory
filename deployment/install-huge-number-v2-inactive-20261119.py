"""Install Huge Number V2 mathematical library into production ZIP, INACTIVE.

This is intentionally NOT a live economy migration. It preserves all server,
market, bank, SQL, and UI files unchanged and keeps existing NUMERIC authoritative.
"""
import ast
import os
import tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

archive=Path("hare-machi-render.zip")
sources={
    "huge_number_v2.py":"deployment/huge_number_v2.py",
    "sparse_exact_v1.py":"deployment/sparse_exact_v1.py",
    "sparse_exact_division.py":"deployment/sparse_exact_division.py",
    "v2_numeric_lossless_backfill.py":"deployment/v2_numeric_lossless_backfill.py",
}
if not archive.is_file():
    raise RuntimeError("Production ZIP not found")
with ZipFile(archive) as original:
    if original.testzip() is not None:
        raise RuntimeError("Original ZIP damaged")
    entries=[(info,original.read(info.filename)) for info in original.infolist()]
    before=dict((info.filename,content) for info,content in entries)

for dest,source in sources.items():
    data=Path(source).read_bytes()
    ast.parse(data.decode("utf-8"),filename=dest)
    if dest in before and before[dest]!=data:
        raise RuntimeError("V2 library differs from expected source: "+dest)
if "action_archive_support.py" not in before:
    raise RuntimeError("Archive support is missing from production ZIP")
if "market.py" not in before or "server.py" not in before or "static/app.js" not in before:
    raise RuntimeError("Production core files missing")

fd,tmp=tempfile.mkstemp(dir=".",suffix=".zip")
os.close(fd)
try:
    with ZipFile(tmp,"w") as out:
        for info,data in entries:
            out.writestr(info,data)
        for dest,source in sources.items():
            if dest not in before:
                out.writestr(dest,Path(source).read_bytes(),compress_type=ZIP_DEFLATED)
    with ZipFile(tmp) as verify:
        if verify.testzip() is not None:
            raise RuntimeError("Result ZIP damaged")
        for dest,source in sources.items():
            assert verify.read(dest)==Path(source).read_bytes()
        for name,data in before.items():
            if name not in sources and verify.read(name)!=data:
                raise RuntimeError("Live game core was modified: "+name)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp): os.unlink(tmp)

print("HUGE_NUMBER_V2_LIBRARY_INSTALLED_INACTIVE")
print("ALL_EXISTING_GAME_FILES_UNCHANGED")
print("PRODUCTION_DATABASE_UNTOUCHED")
