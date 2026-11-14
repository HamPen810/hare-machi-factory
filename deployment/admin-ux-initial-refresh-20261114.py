"""Load the existing admin dashboard once after authenticated entry.

Pure UX improvement: invoke the existing read-only refresh function after login
or restored admin session; leave every financial input and action untouched.
"""
from zipfile import ZipFile
from pathlib import Path
import io,ast
p=Path("hare-machi-render.zip")
with ZipFile(p) as z:
    rows=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
f={i.filename:d for i,d in rows}
s=f['static/admin.js'].decode('utf8')
assert "window.__adminDashboardSnapshot=data" in s
assert "'/admin-ux.js':'admin-ux.js'" in f['server.py'].decode()
updates=[
    ("  await openControls();\n  void loadFundsHistory();\n  notice('');",
     "  await openControls();\n  void loadFundsHistory();\n  void refresh(true);\n  notice('');"),
    ("openControls().then(()=>loadFundsHistory()).catch(()=>{});",
     "openControls().then(()=>{void loadFundsHistory();void refresh(true);}).catch(()=>{});")
]
for a,b in updates:
    if s.count(a)==1:s=s.replace(a,b,1)
    elif s.count(b)==1 and a not in s:pass
    else:raise RuntimeError('Unexpected session refresh hook; refusing to modify')
assert "void refresh(true);" in s
assert "function render(){window.__adminDashboardSnapshot=data" in s
f['static/admin.js']=s.encode('utf8')
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in rows:z.writestr(info,f[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,raw in rows:
        if info.filename!='static/admin.js':assert z.read(info.filename)==raw,info.filename
p.write_bytes(out.getvalue())
print("PASS: one existing read-only refresh after session authorization; all action systems untouched")
