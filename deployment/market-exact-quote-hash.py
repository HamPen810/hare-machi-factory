"""Use a short hash to confirm market quotes without sending 10k-digit prices.

Prices remain arbitrary exact integers on the server; the hash is solely an
equality check against a fresh server-side quote. No monetary amounts are
rounded or truncated, and no persistent user data is changed.
"""
from pathlib import Path
from zipfile import ZipFile
import tempfile,os

archive=Path('hare-machi-render.zip')
with ZipFile(archive) as src:
    files=[(info,src.read(info.filename)) for info in src.infolist()]

def replace(filename,old,new):
    for i,(info,raw) in enumerate(files):
        if info.filename!=filename:continue
        text=raw.decode()
        if text.count(old)!=1:
            if old not in text and new in text:return
            raise RuntimeError(f'Expected once in {filename}: {old[:90]}')
        files[i]=(info,text.replace(old,new).encode())
        return
    raise RuntimeError(f'Missing {filename}')

replace('market.py','import bank\n','import bank\nimport hashlib\n',)
replace('market.py',
    'return {product: self._market_quote(rows) for product, rows in offers.items()}',
    '''quotes={}
        for product,rows in offers.items():
            quote=self._market_quote(rows)
            price=quote['price']
            quote['price_hash']=(hashlib.sha256(str(price).encode()).hexdigest()
                                 if price is not None else None)
            quotes[product]=quote
        return quotes''')
replace('market.py',
    "if type(quantity) is not int or quantity < 1 or type(price) is not int:\n            raise ValueError('購入する個数と価格を確認してください。')",
    """if type(quantity) is not int or quantity < 1 or not (
            type(price) is int or (
                isinstance(price,str) and len(price)==71 and
                price.startswith('sha256:') and all(c in '0123456789abcdef' for c in price[7:])
            )):
            raise ValueError('購入する個数と価格を確認してください。')""")
replace('market.py',
    "if price != average:\n            raise ValueError('平均販売値が変わりました。価格を確認してから購入してください。')",
    """expected_hash='sha256:'+hashlib.sha256(str(average).encode()).hexdigest()
        if not (price == average or (isinstance(price,str) and price==expected_hash)):
            raise ValueError('平均販売値が変わりました。価格を確認してから購入してください。')""")
replace('static/app.js',
    "quantity:quantityText(buyQuantity).trim(),price:buyQuote.price",
    "quantity:quantityText(buyQuantity).trim(),price:buyQuote.price_hash?'sha256:'+buyQuote.price_hash:buyQuote.price")
replace('server.py',
    "                        value=data[field].strip()\n                        if len(value)>4096:",
    """                        value=data[field].strip()
                        if (field=='price' and data.get('kind')=='buy_market'
                            and re.fullmatch(r'sha256:[0-9a-f]{64}',value)):
                            data[field]=value
                            continue
                        if len(value)>4096:""")
fd,tmp=tempfile.mkstemp(prefix='.quote-hash-',suffix='.zip',dir='.')
os.close(fd)
try:
    with ZipFile(tmp,'w') as dest:
        for info,raw in files:dest.writestr(info,raw)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print('Market quotes now use exact price fingerprints for compact purchase requests.')
