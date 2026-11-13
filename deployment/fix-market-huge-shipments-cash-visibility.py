"""Fix full-stock shipping over 4096 digits and invisible small sale proceeds.

The previous all-stock handler deliberately preserved an EXACT integer, but
both browser parseWhole and the HTTP route still rejected decimal strings
longer than 4096 bytes. Keep exact integers and permit a full PostgreSQL
NUMERIC-sized value (up to 131072 decimal digits); do not substitute
rounded e-notation.  Make full cash balances inspectable from the game UI.

Only ZIP code is patched.  There are no database writes or account changes.
"""
from zipfile import ZipFile
from pathlib import Path
import os,tempfile

archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    items=[(i,z.read(i.filename)) for i in z.infolist()]

def replace(filename,old,new,*,optional=False):
    for index,(info,raw) in enumerate(items):
        if info.filename!=filename:continue
        source=raw.decode('utf-8')
        if source.count(old)==0 and optional:return
        if source.count(old)!=1:
            raise RuntimeError(f'Expected one match in {filename}, found {source.count(old)}: {old[:80]}')
        items[index]=(info,source.replace(old,new).encode('utf-8'))
        return
    raise RuntimeError('Missing archive member '+filename)

# Client accepts the same exact decimal quantity that "全部" displays. Small
# scientific inputs (e.g. 2.6813e+4737) continue to work unchanged.
replace('static/numbers.js',
    'if (source.length > 4096) return null;',
    'if (source.length > 131072) return null;')

# The old 4096-byte general API cap was much lower than the existing
# PostgreSQL NUMERIC storage limit. Enlarge it only for /api/action; still
# bound requests to protect Render from arbitrarily large uploads.
replace('server.py',
    "(60000 if self.path=='/api/admin/settings' else 4096)",
    "(262144 if self.path=='/api/action' else 60000 if self.path=='/api/admin/settings' else 4096)")
replace('server.py',
    'if len(value)>4096:',
    'if len(value)>131072:')
# Also support the old parser if this ZIP variant still uses quantity_text.
replace('server.py',
    'if len(quantity_text)>4096:',
    'if len(quantity_text)>131072:',optional=True)

# The old JS shipping action already keeps the exact decimal value rather
# than a rounded label; the request can now carry it without being rejected.
# Make balances inspectable: the usual five-significant-digit UI hides a
# 1e14 sale when current cash is already near 4.1e18.
cash_line="ui('cash').textContent=fmt(f.cash)+'円';"
replacement="""ui('cash').textContent=fmt(f.cash)+'円';
 ui('cash').title='タップすると所持金の正確な値を表示します';
 ui('cash').style.cursor='pointer';"""
replace('static/app.js',cash_line,replacement)
# Install the click behavior once, not once per render, so it remains stable.
anchor="function choosePage(next){"
handler="""function showExactCash(){
 if(!snapshot)return;
 const exact=String(snapshot.factory.cash??0);
 const shown=exact.length<=150
   ? BigInt(exact).toLocaleString('ja-JP')+'円'
   : exact.slice(0,30)+'…（'+exact.replace(/^-/, '').length+'桁、画面表示は概数）';
 notice('現在の所持金（'+(exact.length<=150?'正確な値':'先頭30桁')+'）：'+shown);
}
ui('cash').addEventListener('click',showExactCash);
for(const element of document.querySelectorAll('[data-panel-cash]')){
 element.style.cursor='pointer';
 element.addEventListener('click',showExactCash);
}
function choosePage(next){"""
replace('static/app.js',anchor,handler)
fd,tmp=tempfile.mkstemp(prefix='.exact-shipping-',suffix='.zip',dir='.')
os.close(fd)
try:
    with ZipFile(tmp,'w') as dest:
        for info,content in items:dest.writestr(info,content)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print('Expanded exact shipping input/HTTP limits and added precise cash inspection.')
