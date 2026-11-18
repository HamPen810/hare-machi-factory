"""Expose read-only V2 balances for logged-in users; never enable V2 writes.

Every unmodified production ZIP entry is copied byte-for-byte. This patch must
pass tests before GitHub Actions pushes it to the auto-deployed repository.
"""
import ast
import os
import tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

archive=Path("hare-machi-render.zip")
source=Path("deployment/v2_balance_read.py")
bridge=source.read_bytes()
ast.parse(bridge.decode("utf8"),filename="v2_balance_read.py")

with ZipFile(archive) as zip_in:
    if zip_in.testzip() is not None: raise RuntimeError("Bad production ZIP")
    entries=[(info, zip_in.read(info.filename)) for info in zip_in.infolist()]
    originals={info.filename: raw for info,raw in entries}
    server=originals["server.py"].decode("utf8")

if "v2_numeric_lossless_backfill.py" not in originals:
    raise RuntimeError("V2 lossless number converter is not installed")
if "v2_balance_read.py" in originals and originals["v2_balance_read.py"] != bridge:
    raise RuntimeError("Existing V2 bridge differs; manual review needed")

old_readonly="read_only=not write and self.path in ('/api/data','/api/market','/api/ranks','/api/market-quotes','/api/bank')"
new_readonly="read_only=not write and self.path in ('/api/data','/api/market','/api/ranks','/api/market-quotes','/api/bank','/api/v2/balances')"
if new_readonly not in server:
    if server.count(old_readonly)!=1:raise RuntimeError("Read-only route guard changed")
    server=server.replace(old_readonly,new_readonly,1)

anchor="                g=Game(a,clock,opens_at=0 if practice else OPEN_MS,read_only=read_only or player_only)"
new_handler="""                if not write and self.path=='/api/v2/balances':
                    from v2_balance_read import snapshot as read_v2_balances
                    return self.reply(200,read_v2_balances(a.db,identity['id']))
"""
if new_handler not in server:
    if server.count(anchor)!=1:raise RuntimeError("Authenticated player route anchor changed")
    server=server.replace(anchor,new_handler+anchor,1)
ast.parse(server,filename="server.py")

# Preserve all existing application files and live money/market writer semantics.
if "read_v2_balances" not in server:raise RuntimeError("Missing V2 entrypoint")
for marker in ("if not write and self.path=='/api/v2/balances':",
               "read_only=not write and self.path in"):
    if marker not in server:raise RuntimeError("Missing safety gate: "+marker)

fd,tmp=tempfile.mkstemp(dir=".",suffix=".zip")
os.close(fd)
try:
    with ZipFile(tmp,"w") as out:
        for info,data in entries:
            if info.filename=="server.py": data=server.encode("utf8")
            out.writestr(info,data)
        if "v2_balance_read.py" not in originals:
            out.writestr("v2_balance_read.py",bridge,compress_type=ZIP_DEFLATED)
    with ZipFile(tmp) as check:
        if check.testzip() is not None:raise RuntimeError("Patched ZIP corrupt")
        if check.read("v2_balance_read.py")!=bridge:raise RuntimeError("Bridge content mismatch")
        if check.read("server.py")!=server.encode("utf8"):raise RuntimeError("Server content mismatch")
        for name,data in originals.items():
            if name not in ("server.py","v2_balance_read.py") and check.read(name)!=data:
                raise RuntimeError("Unexpected modification to game economy: "+name)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print("V2_READ_ONLY_ENDPOINT_PATCH_OK")
print("LEGACY_ECONOMY_WRITES_UNCHANGED")
