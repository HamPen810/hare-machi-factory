"""Keep shared Supabase session-pool usage below its 15-client cap.

Existing main Render replica previously allowed 8 pooled connections, which
temporarily doubles during rolling deployments. Four on the primary and one
on each inventory worker leaves room for overlap and optional Oracle worker.
"""
from zipfile import ZipFile
from pathlib import Path
import ast,io

p=Path('hare-machi-render.zip')
with ZipFile(p) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}
name='postgres.py'
code=files[name].decode('utf-8')
old='max_size=(8 if os.environ.get("RENDER_SERVICE_NAME") == "hare-machi-factory-sg" else 1)'
new='max_size=_safe_pool_limit()'
assert code.count(old)==1, 'unexpected upstream PostgreSQL pool configuration'
helper='''def _safe_pool_limit():
    # A session-mode Supabase pooler has a finite concurrent client budget.
    # Render's old + new replicas can overlap during a deployment.
    if os.environ.get("RENDER_SERVICE_NAME") != "hare-machi-factory-sg":
        return 1
    try:
        value = int(os.environ.get("HARE_FACTORY_MAIN_PG_POOL", "4"))
    except (ValueError,TypeError):
        value = 4
    return max(1,min(6,value))


'''
anchor='@lru_cache(maxsize=4)\ndef _shared_connection_pool(url):'
assert code.count(anchor)==1
code=code.replace(anchor,helper+anchor).replace(old,new)
ast.parse(code,filename=name)
files[name]=code.encode('utf8')
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename!=name:
            assert z.read(info.filename)==data
p.write_bytes(out.getvalue())
print('PASS: main PostgreSQL pool capped at 4 by default, B/C/Oracle capped at 1, all other files preserved')
