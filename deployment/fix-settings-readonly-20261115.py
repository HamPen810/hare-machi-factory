"""Repair read-only site settings fetch shared by player and admin clients.

The current web handler creates a read_only Accounts connection but calls
Admin.initialize() (which creates tables, ALTERs, and INSERTs), so both
/api/site-settings and admin login fail while DB is read-only.

Admin.settings() reads the already-existing site_settings and posts without
writing anything. This is safe under read-only, and unchanged in healthy DBs.
No gameplay calculations, purchases, transactions, or data are changed.
"""
from zipfile import ZipFile
from pathlib import Path
import io,ast
p=Path('hare-machi-render.zip')
with ZipFile(p) as z:
    rows=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:d for i,d in rows}
source=files['server.py'].decode('utf8')
old="settings_cache=Admin(account).initialize(MAINTENANCE and not practice)"
new="settings_cache=Admin(account).settings()"
if source.count(old)!=1:
    if new in source and old not in source:
        print("Already applied; skipping archive rewrite")
        raise SystemExit(0)
    raise RuntimeError("Unexpected site settings implementation; not patching")
source=source.replace(old,new,1)
assert "account=Accounts(path,read_only=True,admin_only=True)" in source
assert "settings_cache=Admin(account).settings()" in source
files['server.py']=source.encode('utf8')
for name in ('server.py','market.py','admin.py','bank.py','exact.py'):
    ast.parse(files[name].decode('utf8'),filename=name)
admin=files['admin.py'].decode('utf8')
assert "def settings(self):" in admin
assert "SELECT maintenance,announcement,announcement_revision FROM site_settings WHERE id=1" in admin
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,_ in rows:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,b in rows:
        if info.filename!='server.py':assert z.read(info.filename)==b,("unintended modification",info.filename)
p.write_bytes(out.getvalue())
print("PASS: settings now read-only query; all financial + game modules byte-identical")
