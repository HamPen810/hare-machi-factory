"""Verify market history pagination preserves exact rows and chronological boundaries."""
import sqlite3
import market

db=sqlite3.connect(':memory:')
db.row_factory=sqlite3.Row
db.execute("""CREATE TABLE market_ticks (
round INTEGER,product TEXT,player TEXT,sold INTEGER,
revenue INTEGER,inventory INTEGER,cost INTEGER,
PRIMARY KEY(round,product,player))""")
for minute in range(1,701):
    for product in ('white','sea','shisa'):
        db.execute("INSERT INTO market_ticks VALUES(?,?,?,?,?,?,?)",(minute,product,'',minute,minute*8,minute//2,minute))
        if minute%3==0:
            db.execute("INSERT INTO market_ticks VALUES(?,?,?,?,?,?,?)",(minute,product,'p',minute,minute*9,minute//3,minute))
class Identity:
    postgres=False
    def identity(self,token,now):return {'id':'p'}
g=object.__new__(market.Game)
g.db=db
g.accounts=Identity()
g.clock=lambda:700*60000
full={(r['round'],r['product'],r['player']):dict(r) for r in db.execute(
    "SELECT * FROM market_ticks WHERE player IN ('','p')")}
seen={}
before=None
pages=0
while True:
    result=g.timeline('token',before=before)
    entries=result['timeline']
    pages+=1
    assert len(entries)<=1440
    if before is not None:
        assert all(r['round']<before for r in entries)
    for r in entries:
        key=(r['round'],r['product'],r['player'])
        assert key not in seen, (pages,key)
        seen[key]=r
    if not result['timeline_more']:break
    assert entries, "Page cursor did not advance"
    before=min(r['round'] for r in entries)
    assert pages<10
assert seen==full, (len(seen),len(full))

latest=g.timeline('token')
assert min(r['round'] for r in latest['timeline'])==461
assert max(r['round'] for r in latest['timeline'])==700
assert latest['timeline_more']

increment=g.timeline('token',after=699)
assert all(r['round']>=699 for r in increment['timeline'])
assert 'timeline_more' not in increment
assert g.timeline('token',after=701)['timeline']==[]

# Per-player isolation: another user's sales must never appear.
db.execute("INSERT INTO market_ticks VALUES(701,'white','stranger',1,100,0,0)")
assert not any(r['player']=='stranger' for r in g.timeline('token')['timeline'])
print("PASS: all historical rows reachable once, 240-minute pages, incremental refresh and player privacy")
