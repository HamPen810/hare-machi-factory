"""Allow large exact administrator grants without changing player data.

The admin funding form currently sends expanded exact integers, e.g.
1e7600 becomes 7601 decimal digits. The /api/admin/funds endpoint
incorrectly uses the generic 4096-byte request cap.

Increase only the intended authenticated funding endpoints' limits.
Actual grant/collection authorization and PostgreSQL NUMERIC checks remain
unchanged. This changes only the production ZIP source, not the database.
"""
from pathlib import Path
from zipfile import ZipFile
import os, tempfile

archive=Path('hare-machi-render.zip')
with ZipFile(archive) as original:
    files=[(info,original.read(info.filename)) for info in original.infolist()]

old="(262144 if self.path=='/api/action' else 60000 if self.path=='/api/admin/settings' else 4096)"
new="(262144 if self.path=='/api/action' else 65536 if self.path in ('/api/admin/funds','/api/admin/funds-extra') else 60000 if self.path=='/api/admin/settings' else 4096)"
for i,(info,raw) in enumerate(files):
    if info.filename!='server.py': continue
    source=raw.decode('utf-8')
    if source.count(old)!=1:
        if new in source and old not in source:
            print('Admin funds cap already patched')
            break
        raise RuntimeError('Unexpected server request body limit; refusing unsafe patch')
    if "/api/admin/funds" not in source:
        raise RuntimeError('Admin funding endpoint not found')
    files[i]=(info,source.replace(old,new).encode('utf-8'))
    break
else:
    raise RuntimeError('server.py missing')

fd,temp=tempfile.mkstemp(prefix='.admin-funds-size-',suffix='.zip',dir='.')
os.close(fd)
try:
    with ZipFile(temp,'w') as output:
        for info,raw in files:output.writestr(info,raw)
    os.replace(temp,archive)
finally:
    if os.path.exists(temp):os.unlink(temp)
print('Expanded admin funding request limit to 65536 bytes')
