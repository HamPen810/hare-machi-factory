"""Restore only Sunpress per-level 10x tap multiplier; leave upgrade prices and DB intact."""
from pathlib import Path
from zipfile import ZipFile
import io,ast
path=Path("hare-machi-render.zip")
with ZipFile(path) as z:
    entries=[(info,z.read(info.filename)) for info in z.infolist()]
    comment=z.comment
files={info.filename:data for info,data in entries}
m=files["market.py"].decode("utf-8")
changes=[
 ("return 2**(r[0] if r else 0)","return 10**(r[0] if r else 0)"),
 ("f['tap_power']=power(f['tier'])*2**levels.get('sunpress',0)",
  "f['tap_power']=power(f['tier'])*10**levels.get('sunpress',0)")
]
for old,new in changes:
    if old in m:
        if m.count(old)!=1:raise RuntimeError("Ambiguous old expression")
        m=m.replace(old,new,1)
    elif new not in m:raise RuntimeError("Unexpected source; refusing change: "+old)
assert "cost=EQUIPMENT[kind][1]*5**level" in m
assert "EQUIPMENT={'sunpress':('おひさまプレス',50000),'islandline':('南風オートライン',250000)}" in m
ast.parse(m)
files["market.py"]=m.encode("utf-8")
out=io.BytesIO()
with ZipFile(out,"w") as z:
    z.comment=comment
    for info,_ in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename!="market.py": assert z.read(info.filename)==data,info.filename
if out.getvalue()!=path.read_bytes():path.write_bytes(out.getvalue())
print("PASS: Sunpress 10x restored; all other files, prices, player data unchanged")
