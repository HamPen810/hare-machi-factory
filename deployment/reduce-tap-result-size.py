"""Safely shrink *future* tap_batch idempotency payloads in production ZIP.

Existing action rows are neither modified nor deleted. Only tap_batch responses
are compressed when the compressed envelope is smaller; other operation
records remain byte-for-byte compatible with existing SQL accounting.
"""
from pathlib import Path
from zipfile import ZipFile
import os, tempfile

ARCHIVE=Path('hare-machi-render.zip')
HELPERS = '''
# Stored action result codec v1: JSON envelope keeps SQL JSON casts safe.
def _store_action_result(kind, result):
    import json
    plain = json.dumps(result)
    if kind != 'tap_batch' or len(plain) < 4096:
        return plain
    import zlib, base64
    encoded = base64.b64encode(zlib.compress(plain.encode('utf-8'), level=6)).decode('ascii')
    wrapped = json.dumps({'_tap_batch_zlib_v1': encoded})
    return wrapped if len(wrapped) < len(plain) else plain

def _load_action_result(raw):
    import json
    result = json.loads(raw)
    if isinstance(result, dict) and set(result) == {'_tap_batch_zlib_v1'}:
        import zlib, base64
        encoded = result['_tap_batch_zlib_v1']
        result = json.loads(zlib.decompress(base64.b64decode(encoded)).decode('utf-8'))
    return result

'''
OLD_REPEAT="self.db.commit(); return json.loads(old['result'])"
NEW_REPEAT="self.db.commit(); return _load_action_result(old['result'])"
OLD_STORE="self.db.execute('INSERT INTO actions VALUES(?,?,?,?)',(p,key,payload,json.dumps(result)))"
NEW_STORE="self.db.execute('INSERT INTO actions VALUES(?,?,?,?)',(p,key,payload,_store_action_result(kind,result)))"

with ZipFile(ARCHIVE) as z:
    entries=[(item,z.read(item.filename)) for item in z.infolist()]
patched=[]
for info,raw in entries:
    if info.filename!='market.py':
        patched.append((info,raw));continue
    src=raw.decode('utf-8')
    if '_tap_batch_zlib_v1' not in src:
        if src.count('class Game:')!=1:
            raise RuntimeError('Expected Game class location not found')
        src=src.replace('class Game:',HELPERS+'class Game:',1)
    for old,new in ((OLD_REPEAT,NEW_REPEAT),(OLD_STORE,NEW_STORE)):
        if new in src:
            continue
        if src.count(old)!=1:
            raise RuntimeError('Unexpected market.py source; refusing to modify ZIP')
        src=src.replace(old,new)
    compile(src,'market.py','exec')
    patched.append((info,src.encode('utf-8')))
fd,tmp=tempfile.mkstemp(prefix='.tap-codec-',suffix='.zip',dir='.')
os.close(fd)
try:
    with ZipFile(tmp,'w') as out:
        for info,raw in patched:
            out.writestr(info,raw)
    with ZipFile(tmp) as check:
        assert check.testzip() is None
    os.replace(tmp,ARCHIVE)
finally:
    if os.path.exists(tmp):os.remove(tmp)
print('ACTION_CODEC_PATCH_OK')
