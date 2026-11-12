"""Integrate opt-in hybrid compute into the CURRENT deployed application ZIP.

Keeps all state-changing endpoints, session authentication, database structure,
gameplay and existing URLs unchanged. Only /api/ranks is eligible to offload.
"""
from pathlib import Path
from zipfile import ZipFile
import ast,io

archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}
def replace(name,before,after):
    s=files[name].decode('utf-8')
    if s.count(before)!=1:
        raise RuntimeError(f'{name}: anchor occurrences {s.count(before)} for {before[:100]!r}')
    files[name]=s.replace(before,after).encode('utf-8')

replace('server.py',
"""from inventory_cluster import InventoryCluster""",
"""from inventory_cluster import InventoryCluster
from hybrid_router import HybridRouter""")

replace('server.py',
"""    settings_lock=threading.Lock()""",
"""    hybrid=HybridRouter()
    settings_lock=threading.Lock()""")

replace('server.py',
"""        def process(self,write):
            started=time.monotonic()
            try:
                self.route(write)
            finally:
                elapsed=time.monotonic()-started""",
"""        def process(self,write):
            started=time.monotonic()
            hybrid.started()
            try:
                self.route(write)
            finally:
                elapsed=time.monotonic()-started
                hybrid.finished(elapsed)""")

replace('server.py',
"""                    if not write and self.path=='/api/admin/dashboard':""",
"""                    if not write and self.path=='/api/admin/hybrid':
                        return self.reply(200,hybrid.stats())
                    if not write and self.path=='/api/admin/dashboard':""")

replace('server.py',
"""                if not write and self.path=='/api/ranks':
                    return self.reply(200,{'rankings':a.rankings_many(('manufactured','net_profit','revenue'))})""",
"""                if not write and self.path=='/api/ranks':
                    def local_rankings():
                        return {'rankings':a.rankings_many(('manufactured','net_profit','revenue'))}
                    def isolated_local_rankings():
                        # Dedicated read-only DB handle for speculative execution.
                        separate=Accounts(path,read_only=True)
                        try:
                            return {'rankings':separate.rankings_many(
                                ('manufactured','net_profit','revenue'))}
                        finally:
                            separate.db.close()
                    return self.reply(200,hybrid.calculate(
                        'rankings',local_rankings,isolated_local_rankings))""")

for f in ('server.py',):
    ast.parse(files[f].decode('utf8'),filename=f)
for mod in ('hybrid_router.py','hybrid_worker.py','oracle_deploy_agent.py'):
    code=Path('deployment/hybrid/'+mod).read_bytes()
    ast.parse(code.decode('utf8'),filename=mod)
    if mod in files:raise RuntimeError(f'{mod} already in archive; inspect before patching')
    files[mod]=code

out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:
        z.writestr(info,files[info.filename])
    for mod in ('hybrid_router.py','hybrid_worker.py','oracle_deploy_agent.py'):
        z.writestr(mod,files[mod])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename!='server.py':
            assert z.read(info.filename)==data,info.filename
archive.write_bytes(out.getvalue())
print('PASS: opt-in hybrid routing attached only to authenticated /api/ranks; all game state logic untouched')
