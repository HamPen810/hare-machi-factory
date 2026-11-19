"""Add authenticated read-only V2 ranking, data and admin dashboard APIs.

Existing revenue, cash, inventory, market, bank, and admin mutation handlers
remain byte-identical. These endpoints encode authoritative legacy NUMERIC
without precision loss; they do NOT claim V2-native balances are active.
"""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import ast,os,re,tempfile

archive=Path('hare-machi-render.zip')
module=Path('deployment/v2_read_reports.py').read_bytes()
ast.parse(module.decode())
with ZipFile(archive) as zin:
    if zin.testzip() is not None:raise RuntimeError('Corrupt production ZIP')
    entries=[(i,zin.read(i.filename)) for i in zin.infolist()]
    originals={i.filename:data for i,data in entries}
if 'v2_numeric_lossless_backfill.py' not in originals:raise RuntimeError('No V2 converter')
source=originals['server.py'].decode()
old_api="'/api/notices','/api/notices/read','/api/notices/message'"
new_api="'/api/notices','/api/notices/read','/api/notices/message','/api/v2/ranks','/api/v2/data'"
if new_api not in source:
    if source.count(old_api)!=1:raise RuntimeError('API whitelist changed')
    source=source.replace(old_api,new_api,1)
regex=r"(read_only=not write and self.path in \([^\n]+)\)"
m=re.search(regex,source)
if not m:raise RuntimeError('Read-only route classification missing')
if "'/api/v2/ranks'" not in m.group(0):
    source=source[:m.start()]+m.group(1)+",'/api/v2/ranks','/api/v2/data')"+source[m.end():]

# Insert V2 rankings projection after identity has been checked.
anchor="""                if not write and self.path=='/api/v2/balances':
"""
routes="""                if not write and self.path=='/api/v2/ranks':
                    from v2_read_reports import rankings_projection
                    return self.reply(200,rankings_projection(
                        a.rankings_many(('manufactured','net_profit','revenue'))))
"""
if routes not in source:
    if source.count(anchor)!=1:raise RuntimeError('V2 authenticated route anchor moved')
    source=source.replace(anchor,routes+anchor,1)
# The V2 data path operates on exactly the same user-scoped Game object as /api/data.
data_anchor="""                if not write and self.path=='/api/data':
"""
data_route="""                if not write and self.path=='/api/v2/data':
                    from v2_read_reports import data_projection
                    return self.reply(200,data_projection({
                        **g.timeline(token),
                        'breakdown':g.breakdown(token)}))
"""
if data_route not in source:
    if source.count(data_anchor)!=1:raise RuntimeError('Data route anchor moved')
    source=source.replace(data_anchor,data_route+data_anchor,1)
admin_anchor="""                    if not write and self.path=='/api/admin/dashboard':
"""
admin_route="""                    if not write and self.path=='/api/admin/v2/dashboard':
                        from v2_read_reports import dashboard_projection
                        return self.reply(200,dashboard_projection(admin.dashboard(
                            Game(a,clock,opens_at=0 if practice else OPEN_MS,read_only=True))))
"""
if admin_route not in source:
    if source.count(admin_anchor)!=1:raise RuntimeError('Admin auth/dashboard anchor moved')
    source=source.replace(admin_anchor,admin_route+admin_anchor,1)
ast.parse(source,filename='server.py')

if 'v2_read_reports.py' in originals and originals['v2_read_reports.py']!=module:
    raise RuntimeError('Existing V2 report package differs')
fd,tmp=tempfile.mkstemp(dir='.',suffix='.zip');os.close(fd)
try:
    with ZipFile(tmp,'w') as zout:
        for info,data in entries:
            zout.writestr(info,source.encode() if info.filename=='server.py' else data)
        if 'v2_read_reports.py' not in originals:
            zout.writestr('v2_read_reports.py',module,compress_type=ZIP_DEFLATED)
    with ZipFile(tmp) as z:
        if z.testzip() is not None:raise RuntimeError('Patched ZIP corrupt')
        assert z.read('server.py').decode()==source
        assert z.read('v2_read_reports.py')==module
        for name,raw in originals.items():
            if name!='server.py' and z.read(name)!=raw:
                raise RuntimeError('Unexpected economic code change: '+name)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):os.remove(tmp)
print('V2_RANK_DATA_ADMIN_READ_APIS_INSTALLED')
print('ALL_LEGACY_ASSET_WRITERS_UNCHANGED')
