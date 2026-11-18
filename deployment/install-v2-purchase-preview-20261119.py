"""Patch authenticated V2 preview endpoint into the existing game ZIP.

No changes to the current NUMERIC schema, balances, market, banks, or admin.
"""
import ast, os, tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

archive=Path("hare-machi-render.zip")
module=Path("deployment/v2_purchase_preview.py").read_bytes()
ast.parse(module.decode("utf-8"))
with ZipFile(archive) as original:
    if original.testzip() is not None:
        raise RuntimeError("Production ZIP is corrupt")
    entries=[(info,original.read(info.filename)) for info in original.infolist()]
    files={info.filename:data for info,data in entries}
if "v2_balance_read.py" not in files or "sparse_exact_v1.py" not in files:
    raise RuntimeError("V2 foundation is not installed")
if "v2_purchase_preview.py" in files and files["v2_purchase_preview.py"]!=module:
    raise RuntimeError("Existing preview module differs")

server=files["server.py"].decode("utf-8")
anchor="""                if not write and self.path=='/api/v2/balances':
                    from v2_balance_read import snapshot as read_v2_balances
                    return self.reply(200,read_v2_balances(a.db,identity['id']))
"""
insert="""                if write and self.path=='/api/v2/preview':
                    from v2_purchase_preview import purchase_preview
                    return self.reply(200,purchase_preview(a.db,identity['id'],data))
"""
if insert not in server:
    if server.count(anchor)!=1:
        raise RuntimeError("Authenticated V2 endpoint anchor changed")
    server=server.replace(anchor,anchor+insert,1)
ast.parse(server,filename="server.py")
fd,temp=tempfile.mkstemp(dir=".",suffix=".zip")
os.close(fd)
try:
    with ZipFile(temp,"w") as out:
        for info,data in entries:
            out.writestr(info,server.encode("utf-8") if info.filename=="server.py" else data)
        if "v2_purchase_preview.py" not in files:
            out.writestr("v2_purchase_preview.py",module,compress_type=ZIP_DEFLATED)
    with ZipFile(temp) as verify:
        if verify.testzip() is not None:raise RuntimeError("Patched archive corrupt")
        assert verify.read("v2_purchase_preview.py")==module
        assert verify.read("server.py")==server.encode("utf-8")
        for name,data in files.items():
            if name!="server.py" and verify.read(name)!=data:
                raise RuntimeError("Unexpected change to game file "+name)
    os.replace(temp,archive)
finally:
    if os.path.exists(temp):os.unlink(temp)
print("V2_AUTHENTICATED_PREVIEW_PATCHED_WITHOUT_ECONOMY_MUTATIONS")
