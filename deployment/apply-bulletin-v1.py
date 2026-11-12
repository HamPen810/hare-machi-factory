#!/usr/bin/env python3
"""Apply the verified bulletin feature patch to the existing production archive."""
import base64
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import zlib

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "hare-machi-render.zip"
PAYLOAD = ROOT / "deployment/bulletin-patch-v1.b64"
EXPECTED_BLOB = "7a60b09890ab0348277ceda95ed13b86ce013c3c"

raw = ARCHIVE.read_bytes()
blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
with ZipFile(ARCHIVE) as old:
    if "bulletin.py" in old.namelist() and b"def player_posts" in old.read("bulletin.py"):
        print("Bulletin patch is already installed")
        raise SystemExit(0)
if blob != EXPECTED_BLOB:
    raise SystemExit(f"Archive changed; refusing unsafe patch. Expected {EXPECTED_BLOB}; found {blob}")

patches = json.loads(zlib.decompress(base64.b64decode(PAYLOAD.read_text())))
temp = ARCHIVE.with_suffix(".zip.tmp")
with ZipFile(ARCHIVE) as source, ZipFile(temp, "w") as output:
    for info in source.infolist():
        name = info.filename
        contents = source.read(name)
        if name in patches:
            original = contents.decode("utf-8")
            modified = original
            for start, end, replacement in reversed(patches[name]):
                modified = modified[:start] + replacement + modified[end:]
            contents = modified.encode("utf-8")
        output.writestr(info, contents)
    if "bulletin.py" not in source.namelist():
        contents = ""
        for start, end, replacement in reversed(patches["bulletin.py"]):
            contents = contents[:start] + replacement + contents[end:]
        output.writestr("bulletin.py", contents.encode(), compress_type=ZIP_DEFLATED)
with ZipFile(temp) as check:
    assert check.testzip() is None
    assert len(check.namelist()) == 49
    assert b"def player_posts" in check.read("bulletin.py")
temp.replace(ARCHIVE)
print("Bulletin feature patch installed safely.")
