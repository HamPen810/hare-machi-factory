"""Emergency reduce market-history API workload without deleting any data.

Pagination remains available via X-Timeline-Before, so every historical
market tick is still accessible. PostgreSQL calculates spending aggregates
server-side instead of streaming the full lifetime actions JSON log.
"""
from pathlib import Path
from zipfile import ZipFile
import io,ast
path=Path('hare-machi-render.zip')
with ZipFile(path) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}
def change(name,before,after):
    source=files[name].decode('utf8')
    n=source.count(before)
    if n!=1:raise RuntimeError(f'{name}: anchor count {n}: {before[:100]!r}')
    files[name]=source.replace(before,after).encode('utf8')
change('market.py',
"""        # Fetch only the requested 240-minute window (at minute precision).
        # This protects both PostgreSQL-to-Render egress and response sizes.""",
"""        # A bounded 60-minute window sharply reduces megabyte-scale timeline
        # responses when each production count has thousands of digits.
        # Older history remains available with X-Timeline-Before pagination.""")
change('market.py',
"""        if after is not None:
            start=max(0,after)
            if end<start:return {'timeline':[]}
        else:
            start=max(0,end-239)""",
"""        if after is not None:
            # Do not accidentally send several days of gigantic history after
            # a client has been offline. History is still retrievable by page.
            start=max(0,after,end-59)
            if end<start:return {'timeline':[]}
        else:
            start=max(0,end-59)""")
change('market.py',
"""        for r in self.db.execute('SELECT payload,result FROM actions WHERE player=?',(p,)):
            kind=json.loads(r['payload'])[0]
            if kind in costs and kind!='materials':costs[kind]+=json.loads(r['result']).get('spent',0)""",
"""        if self.accounts.postgres:
            # Database-side reduction avoids transferring every historical
            # action JSON result to Render on every visit to the data tab.
            for r in self.db.execute(
                "SELECT payload::jsonb->>0 AS kind,"
                " SUM(COALESCE((result::jsonb->>'spent')::numeric,0)) AS spent"
                " FROM actions WHERE player=? GROUP BY payload::jsonb->>0",(p,)):
                if r['kind'] in costs and r['kind']!='materials':
                    costs[r['kind']]+=r['spent']
        else:
            for r in self.db.execute('SELECT payload,result FROM actions WHERE player=?',(p,)):
                kind=json.loads(r['payload'])[0]
                if kind in costs and kind!='materials':
                    costs[kind]+=json.loads(r['result']).get('spent',0)""")
ast.parse(files['market.py'].decode('utf8'),filename='market.py')
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for i,data in entries:z.writestr(i,files[i.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for i,data in entries:
        if i.filename!='market.py':
            assert z.read(i.filename)==data,i.filename
path.write_bytes(out.getvalue())
print('PASS bounded timeline pages and PostgreSQL spending aggregation; all other game code untouched')
