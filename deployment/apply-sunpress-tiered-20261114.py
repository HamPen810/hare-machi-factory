"""Stage-based Sunpress pricing; preserve existing players' next old-price purchase.

Postgres migration of sunpress_price_anchors must be applied and backfilled
before deploying this archive. No cash or equipment levels are changed here.
"""
from pathlib import Path
from zipfile import ZipFile
import ast,io

archive=Path("hare-machi-render.zip")
with ZipFile(archive) as z:
    entries=[(info,z.read(info.filename)) for info in z.infolist()]
    comment=z.comment
files={info.filename:data for info,data in entries}

def replace(name,old,new):
    s=files[name].decode("utf-8")
    if s.count(old)!=1:
        if new in s and old not in s:
            return
        raise RuntimeError(f"{name}: expected exactly one anchor, found {s.count(old)}: {old[:80]!r}")
    files[name]=s.replace(old,new,1).encode("utf-8")

MARKER="EQUIPMENT={'sunpress':('おひさまプレス',50000),'islandline':('南風オートライン',250000)}"
FN="""def sunpress_step(level):
    # Price growth for the NEXT level after buying at current level.
    return 5 if level < 500 else 10 if level < 2000 else 12 if level < 5000 else 15

def sunpress_price(level, anchor_level=None):
    # No migration anchor: new player starts on the complete tiered schedule.
    # Existing player: one old-price purchase at their captured anchor level.
    # Following prices increase from that old base without repricing history.
    level=int(level)
    if level < 0:
        raise ValueError('Invalid Sunpress level')
    if anchor_level is None:
        anchor=0
        base=50000
    else:
        anchor=int(anchor_level)
        if anchor < 0:
            raise ValueError('Invalid Sunpress migration anchor')
        if level <= anchor:
            return 50000 * 5**level
        base=50000 * 5**anchor
    def count(lo,hi):
        return max(0,min(level,hi)-max(anchor,lo))
    return (base * 5**count(0,500)
            * 10**count(500,2000)
            * 12**count(2000,5000)
            * 15**max(0,level-max(anchor,5000)))

"""
replace('market.py',MARKER+"\n",MARKER+"\n"+FN)
replace('market.py',
"""    def _multiplier(self,p):""",
"""    def _sunpress_anchor(self,p):
        # A separate immutable migration snapshot protects one legacy-price purchase.
        if not self.accounts.postgres:
            return None
        row=self.db.execute(
            'SELECT anchor_level FROM sunpress_price_anchors WHERE player=?',(p,)
        ).fetchone()
        return row[0] if row else None

    def _multiplier(self,p):""")
replace('market.py',
"""                cost=EQUIPMENT[kind][1]*5**level""",
"""                cost=(sunpress_price(level,self._sunpress_anchor(p)) if kind=='sunpress'
                      else EQUIPMENT[kind][1]*5**level)""")
replace('market.py',
"""        f['equipment']=[]
        for kind,(name,base) in EQUIPMENT.items():
            level=levels.get(kind,0)
            f['equipment'].append({'kind':kind,'name':name,'level':level,'cost':base*5**level,'rate':(10000*5**(level-1) if level and kind=='islandline' else 0)})""",
"""        f['equipment']=[]
        press_anchor=self._sunpress_anchor(p)
        for kind,(name,base) in EQUIPMENT.items():
            level=levels.get(kind,0)
            item={'kind':kind,'name':name,'level':level,
                  'cost':(sunpress_price(level,press_anchor) if kind=='sunpress'
                          else base*5**level),
                  'rate':(10000*5**(level-1) if level and kind=='islandline' else 0)}
            if kind=='sunpress':
                item['next_growth']=sunpress_step(level)
            f['equipment'].append(item)""")
replace('static/app.js',
"""const updated={...item,level:Number(item.level)+1,cost:big(item.cost)*5n};""",
"""const updated={...item,level:Number(item.level)+1,
   cost:big(item.cost)*(kind==='sunpress'?BigInt(item.next_growth||5):5n)};
  if(kind==='sunpress'){
   const after=updated.level;
   updated.next_growth=after<500?5:after<2000?10:after<5000?12:15;
  }""")
for n in ['market.py','server.py']:
    ast.parse(files[n].decode("utf-8"),filename=n)
m=files['market.py'].decode()
assert "return 10**(r[0] if r else 0)" in m
assert "f['tap_power']=power(f['tier'])*10**levels.get('sunpress',0)" in m
assert "cost=(sunpress_price(level,self._sunpress_anchor(p)) if kind=='sunpress'" in m
assert "else EQUIPMENT[kind][1]*5**level" in m
assert "item['next_growth']=sunpress_step(level)" in m
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,_ in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in {'market.py','static/app.js'}:
            assert z.read(info.filename)==data,info.filename
if out.getvalue()!=archive.read_bytes():
    archive.write_bytes(out.getvalue())
print('PASS: 5,5,10,12,15 stages, original 10x tap power, migration anchor, UI prices, no DB data change')
