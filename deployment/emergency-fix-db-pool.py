"""Emergency response to production pool starvation.

- Return read-only connections BEFORE JSON serialization, gzip, and HTTP send.
  Previously 30-50MB timeline responses held PostgreSQL connections until the
  client finished downloading, causing PoolTimeout on unrelated requests.
- Increase main pool from 4 to 6 (maximum remains 6), inventory stays 1 each.
- Never change game data, money handling, schema, auth, or environment values.
"""
from pathlib import Path
from zipfile import ZipFile
import io,ast
path=Path("hare-machi-render.zip")
with ZipFile(path) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}

def change(name,old,new):
    s=files[name].decode('utf-8')
    count=s.count(old)
    if count!=1:raise RuntimeError(f"{name}: expected exactly 1 anchor, got {count}: {old[:100]!r}")
    files[name]=s.replace(old,new).encode('utf-8')

change('postgres.py',
"""value = int(os.environ.get("HARE_FACTORY_MAIN_PG_POOL", "4"))""",
"""value = int(os.environ.get("HARE_FACTORY_MAIN_PG_POOL", "6"))""")
change('postgres.py',
"""        value = 4
    return max(1,min(6,value))""",
"""        value = 6
    return max(1,min(6,value))""")

# Only the explicitly read-only endpoints are fast-released. All stateful
# requests (including game snapshot and writes) retain original transaction
# lifecycle, and the existing finally-close remains idempotent for Postgres.
change('server.py',
"""        def reply(self,status,body,cookie=None,kind='application/json; charset=utf-8',
                  cache_control='no-store',etag=None):
            data=json.dumps(wire(body),ensure_ascii=False).encode() if kind.startswith('application/json') else body""",
"""        def reply(self,status,body,cookie=None,kind='application/json; charset=utf-8',
                  cache_control='no-store',etag=None):
            # Returning a read-only database handle to the pool BEFORE a
            # potentially enormous JSON encoding/gzip/socket write prevents
            # slow clients from starving all other game requests.
            read_db=getattr(self,'_read_response_db',None)
            if read_db is not None:
                self._read_response_db=None
                read_db.close()
            data=json.dumps(wire(body),ensure_ascii=False).encode() if kind.startswith('application/json') else body""")

change('server.py',
"""                a=Accounts(path, auth_only=write and self.path in ('/api/login','/api/register','/api/logout'),
                           read_only=read_only or player_only or admin_route,admin_only=admin_route)
                now=clock() if clock else int(time.time()*1000)""",
"""                a=Accounts(path, auth_only=write and self.path in ('/api/login','/api/register','/api/logout'),
                           read_only=read_only or player_only or admin_route,admin_only=admin_route)
                # The read-only endpoints below never mutate game state.
                # They may release their DB connection before serializing a
                # large HTTP reply; all other paths retain normal lifecycle.
                if a.postgres and not write and read_only:
                    self._read_response_db=a.db
                now=clock() if clock else int(time.time()*1000)""")
for name in ('server.py','postgres.py'):
    ast.parse(files[name].decode('utf-8'),filename=name)
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('server.py','postgres.py'):
            assert z.read(info.filename)==data,info.filename
path.write_bytes(out.getvalue())
print('PASS read-only connections released before response serialization; main pool capped at 6; all other ZIP entries unchanged')
