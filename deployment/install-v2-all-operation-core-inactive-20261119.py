"""Install the exact V2 multi-operation core into production package, INACTIVE.

The module is not imported by the existing server and has no database access.
No API transaction endpoints, market matching, balance writer, admin writer,
SQL schema, or user-visible gameplay behavior is changed by this install.
"""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import ast,os,tempfile

archive=Path('hare-machi-render.zip')
source=Path('deployment/v2_game_economy_full_reference.py').read_bytes()
ast.parse(source.decode(),filename='v2_game_economy_full_reference.py')
with ZipFile(archive) as z:
    if z.testzip() is not None:raise RuntimeError('Source ZIP failed integrity')
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    before={i.filename:data for i,data in entries}

for required in ('server.py','market.py','admin.py','bank.py','accounts.py',
                 'huge_number_v2.py','sparse_exact_v1.py','sparse_exact_division.py',
                 'v2_purchase_preview.py'):
    if required not in before:raise RuntimeError('Production package missing '+required)

if ('v2_game_economy_full_reference.py' in before and
    before['v2_game_economy_full_reference.py']!=source):
    raise RuntimeError('Existing V2 core differs from reviewed source')
for core in ('server.py','market.py','admin.py','bank.py'):
    code=before[core].decode()
    if 'import v2_game_economy_full_reference' in code:
        raise RuntimeError('Unexpected V2 real-money activation in '+core)

fd,tmp=tempfile.mkstemp(dir='.',suffix='.zip');os.close(fd)
try:
    with ZipFile(tmp,'w') as z:
        for info,data in entries:z.writestr(info,data)
        if 'v2_game_economy_full_reference.py' not in before:
            z.writestr('v2_game_economy_full_reference.py',source,compress_type=ZIP_DEFLATED)
    with ZipFile(tmp) as z:
        if z.testzip() is not None:raise RuntimeError('Result ZIP failed integrity')
        assert z.read('v2_game_economy_full_reference.py')==source
        for name,data in before.items():
            if z.read(name)!=data:raise RuntimeError('Existing game changed: '+name)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):os.remove(tmp)
print('ALL_OPERATION_V2_CORE_INSTALLED_DORMANT')
print('LEGACY_PRODUCTION_MONEY_AND_ASSETS_UNCHANGED')
