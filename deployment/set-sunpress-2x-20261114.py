"""Change only the Sunpress per-level tap multiplier from 10x to 2x.
Idempotent, fail-closed, and does not touch DB or unrelated ZIP members.
"""
from pathlib import Path
from zipfile import ZipFile
import io, ast

path=Path("hare-machi-render.zip")
with ZipFile(path) as z:
    entries=[(info,z.read(info.filename)) for info in z.infolist()]
    comment=z.comment
files={info.filename:data for info,data in entries}
market=files["market.py"].decode("utf-8")
changes=[
    ("return 10**(r[0] if r else 0)", "return 2**(r[0] if r else 0)"),
    ("f['tap_power']=power(f['tier'])*10**levels.get('sunpress',0)",
     "f['tap_power']=power(f['tier'])*2**levels.get('sunpress',0)"),
]
for old,new in changes:
    if old in market:
        assert market.count(old)==1,(old,market.count(old))
        market=market.replace(old,new,1)
    elif new not in market:
        raise RuntimeError("Unexpected game version; refusing multiplier patch: "+old)
assert "EQUIPMENT={'sunpress':('おひさまプレス',50000),'islandline':('南風オートライン',250000)}" in market
assert "cost=EQUIPMENT[kind][1]*5**level" in market
ast.parse(market,filename="market.py")
assert "return 2**(r[0] if r else 0)" in market
assert "f['tap_power']=power(f['tier'])*2**levels.get('sunpress',0)" in market
files["market.py"]=market.encode("utf-8")
out=io.BytesIO()
with ZipFile(out,"w") as z:
    z.comment=comment
    for info,_ in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename!="market.py":assert z.read(info.filename)==data,info.filename
if out.getvalue()!=path.read_bytes():
    path.write_bytes(out.getvalue())
print("PASS: Sunpress multiplier changed to 2x; all other ZIP files unchanged")
