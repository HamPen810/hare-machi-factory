"""Remove arbitrary game trading caps and permit market overdraft purchases.

The only remaining transaction-size boundary is PostgreSQL NUMERIC's physical
131072 decimal-digit storage limit. Huge integers stay exact (no Infinity,
float, truncation or saturation). No player records are migrated or modified.
"""
from zipfile import ZipFile
from pathlib import Path
import tempfile,os

path=Path('hare-machi-render.zip')
with ZipFile(path) as archive:
    entries=[(info,archive.read(info.filename)) for info in archive.infolist()]

def change(name,old,new,expected=1):
    for i,(info,raw) in enumerate(entries):
        if info.filename!=name:continue
        source=raw.decode('utf-8')
        if source.count(old)!=expected:
            raise RuntimeError(f'{name}: expected {expected} occurrences of {old[:120]!r}, found {source.count(old)}')
        entries[i]=(info,source.replace(old,new).encode('utf-8'))
        return
    raise RuntimeError('Missing '+name)

# Purchases may cross zero and leave negative balance. Locking, available
# inventory checks, quote validation and seller settlement stay unchanged.
change('market.py',
    """        if self.db.execute('UPDATE factories SET cash=bsub(cash,?) WHERE player=? AND bge(cash,?)',
                           (spent, player, spent)).rowcount != 1:
            raise ValueError('所持金が足りません。')""",
    """        if self.db.execute('UPDATE factories SET cash=bsub(cash,?) WHERE player=?',
                           (spent, player)).rowcount != 1:
            raise ValueError('購入者の所持金更新に失敗しました。')""")

# Drop the arbitrary 50k-digit market cap. Keep a protection tied to the
# actual column type, to avoid writing invalid NUMERIC values.
change('market.py',
'''MARKET_MAX_TOTAL_DIGITS=50000
# The number of bits in a 50,000-digit decimal integer is ~166097.
MARKET_MAX_TOTAL_BITS=166100''',
'''# Actual PostgreSQL NUMERIC storage limit (digits before decimal).
MARKET_MAX_TOTAL_DIGITS=131072
# Conservatively pre-filter impossibly large products by bit-length.
MARKET_MAX_TOTAL_BITS=435414''')

# Remove the redundant 50k client-side cap: server determines storage safety.
change('static/app.js',
'''if(kind==='add_listing'&&parseWhole(request.quantity)!==null&&String(parseWhole(request.quantity)*exactPrice).length>MAX_MARKET_TOTAL_DIGITS)return notice('数量×販売価格がデータベースの安全範囲を超えています。');''',
'''// The server checks the physical NUMERIC storage limit; do not cap the trade in the UI.''')
change('static/app.js','const MAX_MARKET_TOTAL_DIGITS=50000;\n','')

# Expand both parsers to PostgreSQL's physical limit.
change('static/numbers.js','const MAX_INTEGER_DIGITS = 100000;','const MAX_INTEGER_DIGITS = 131072;')
change('server.py',
    """if len(digits)+shift>100000:
                                raise ValueError('数値がデータベースの格納範囲を超えています。')""",
    """if len(digits)+shift>131072:
                                raise ValueError('PostgreSQL NUMERICの物理的な格納範囲を超えています。')""")
change('server.py',
'''                    if (data.get('kind') in ('add_listing','ship','edit_shipment','set_price','buy_market')
                        and type(data.get('price')) is int and type(data.get('quantity')) is int
                        and data['price']>0 and data['quantity']>0):
                        # Reserve headroom for sales, banking, and tax arithmetic.
                        # Cost check uses bit lengths first, to avoid building
                        # enormous products solely for rejected requests.
                        if data['price'].bit_length()+data['quantity'].bit_length()>166120:
                            raise ValueError('数量×販売価格がデータベースの安全範囲を超えています。')
                        if len(str(data['price']*data['quantity']))>50000:
                            raise ValueError('数量×販売価格がデータベースの安全範囲を超えています。')
''','')

fd,tmp=tempfile.mkstemp(prefix='.unlimited-market-',suffix='.zip',dir='.')
os.close(fd)
try:
    with ZipFile(tmp,'w') as output:
        for info,data in entries:output.writestr(info,data)
    os.replace(tmp,path)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print('Removed arbitrary market caps; overdraft purchases allowed; exact numeric storage limits retained.')
