"""Permit negative-balance purchases in the browser buy dialog."""
from pathlib import Path
from zipfile import ZipFile
import tempfile,os
zipname=Path('hare-machi-render.zip')
with ZipFile(zipname) as z:items=[(info,z.read(info.filename)) for info in z.infolist()]
for index,(info,raw) in enumerate(items):
    if info.filename=='static/app.js':
        source=raw.decode('utf-8')
        old="buySubmit.disabled=buying||!snapshot||quantity<1n||quantity>available||total>big(snapshot.factory.cash);"
        new="buySubmit.disabled=buying||!snapshot||quantity<1n||quantity>available;"
        if source.count(old)!=1:raise RuntimeError('Market purchase button logic changed unexpectedly')
        items[index]=(info,source.replace(old,new).encode('utf-8'))
        break
else:raise RuntimeError('Missing app.js')
fd,temp=tempfile.mkstemp(prefix='.market-buy-overdraft-ui-',suffix='.zip',dir='.')
os.close(fd)
try:
    with ZipFile(temp,'w') as z:
        for info,data in items:z.writestr(info,data)
    os.replace(temp,zipname)
finally:
    if os.path.exists(temp):os.unlink(temp)
print('Market purchase button no longer requires enough cash.')
