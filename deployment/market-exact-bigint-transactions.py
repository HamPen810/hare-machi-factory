"""Keep enormous market values in scientific notation over HTTP, and use exact integers.

PostgreSQL NUMERIC has a finite physical limit.  The server checks the
quantity*unit-price *before* processing a transaction. No existing game records
or schema are edited. The safe transaction size leaves plenty of headroom for
running totals and the tax engine.
"""
from pathlib import Path
from zipfile import ZipFile
import os,re,tempfile

archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]

def edit(filename,operation):
    for pos,(info,raw) in enumerate(entries):
        if info.filename==filename:
            result=operation(raw.decode('utf-8'))
            if result==raw.decode('utf-8'):raise RuntimeError('No change in '+filename)
            entries[pos]=(info,result.encode('utf-8'))
            return
    raise RuntimeError('Archive member missing: '+filename)

def one(source,old,new):
    if source.count(old)!=1:raise RuntimeError('Expected exact pattern once: '+old[:100])
    return source.replace(old,new)

def client(js):
    # The quantity must be validated locally but must remain e-notation on
    # the wire. Expanding to 4,001 decimal digits exceeds the 4KB POST limit.
    js=one(js,"request.quantity=String(amount);","request.quantity=quantityText(ui('quantity')).trim();")
    js=one(js,"quantity:String(parseWhole(quantityText(buyQuantity)))","quantity:quantityText(buyQuantity).trim()")
    # The market unit price may itself be enormous. Avoid Number() anywhere
    # in the editable price input flow, so integers stay exact.
    js=one(js,"request.price=Number(ui('price').value);","request.price=ui('price').value.trim();")
    js=re.sub(
        r"if\(!Number\.isInteger\(request\.price\)\|\|request\.price<chosen\.cost\+1\|\|request\.price>99999\)return notice\([^;]+;",
        "const exactPrice=parseWhole(request.price);"
        "if(exactPrice===null||exactPrice<BigInt(chosen.cost+1))"
        "return notice('販売価格は製造価格＋1円以上の整数で入力してください（例：1e10）。');"
        "if(kind==='add_listing'&&parseWhole(request.quantity)!==null&&"
        "String(parseWhole(request.quantity)*exactPrice).length>MAX_MARKET_TOTAL_DIGITS)"
        "return notice('数量×販売価格がデータベースの安全範囲を超えています。');",
        js,count=1)
    if "const exactPrice=parseWhole(request.price)" not in js:
        raise RuntimeError('Price validation not found')
    js=one(js,"let piePage=0;","const MAX_MARKET_TOTAL_DIGITS=50000;\nlet piePage=0;")
    js=one(js,"prices[Number(ui('product').value)]=Number(ui('price').value)","prices[Number(ui('product').value)]=ui('price').value")
    # Price quote already arrives as a string for integers above 2^53.
    return js
edit('static/app.js',client)

def html(source):
    source=one(source,'data-ui="price" type="number" min="2" max="99999" step="1" inputmode="numeric"',
        'data-ui="price" type="text" inputmode="text" placeholder="例 1e10"')
    return source
edit('static/index.html',html)

def server(source):
    marker="                if write and self.path=='/api/action':"
    parser='''                if write and self.path=='/api/action':
                    # Both quantities and unit prices are sent as exact decimal
                    # strings (scientific notation is supported). Never use float.
                    for field in ('quantity','price'):
                        if not isinstance(data.get(field),str):
                            continue
                        value=data[field].strip()
                        if len(value)>4096:
                            raise ValueError('入力が長すぎます。指数表記（例：1e4000）を使用してください。')
                        match=re.fullmatch(r'([0-9]+)(?:\\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?',value)
                        if not match:
                            if field=='price':
                                raise ValueError('販売価格は正の整数で入力してください。')
                            continue
                        whole,fraction,exponent_text=match.group(1),match.group(2) or '',match.group(3) or '0'
                        if len(exponent_text.lstrip('+-0'))>6:
                            raise ValueError('指数がデータベースの格納範囲を超えています。')
                        exponent=int(exponent_text)
                        digits=(whole+fraction).lstrip('0')
                        shift=exponent-len(fraction)
                        if not digits:
                            data[field]=0
                        elif shift>=0:
                            if len(digits)+shift>100000:
                                raise ValueError('数値がデータベースの格納範囲を超えています。')
                            data[field]=int(digits+'0'*shift)
                        else:
                            cut=len(digits)+shift
                            if cut<=0 or any(c!='0' for c in digits[cut:]):
                                raise ValueError('個数と販売価格は整数で指定してください。')
                            data[field]=int(digits[:cut])
                    if (data.get('kind') in ('add_listing','ship','edit_shipment','set_price','buy_market')
                        and type(data.get('price')) is int and type(data.get('quantity')) is int
                        and data['price']>0 and data['quantity']>0):
                        # Reserve headroom for sales, banking, and tax arithmetic.
                        # Cost check uses bit lengths first, to avoid building
                        # enormous products solely for rejected requests.
                        if data['price'].bit_length()+data['quantity'].bit_length()>166120:
                            raise ValueError('数量×販売価格がデータベースの安全範囲を超えています。')
                        if len(str(data['price']*data['quantity']))>50000:
                            raise ValueError('数量×販売価格がデータベースの安全範囲を超えています。')
'''
    start=source.index(marker)
    body_start=source.index("                    if isinstance(data.get('quantity'),str):",start)
    end=source.index("                    result=g.act(",body_start)
    return source[:start]+parser+source[end:]
edit('server.py',server)

def market(source):
    # Price floor remains manufacturing cost + 1; remove obsolete 99,999 cap.
    old="type(price) is not int or not PRODUCTS[product][2]+1<=price<=99999"
    new="type(price) is not int or price<PRODUCTS[product][2]+1"
    if source.count(old)!=2:raise RuntimeError('Unexpected number of market price validations')
    source=source.replace(old,new)
    source=source.replace("販売価格は製造価格＋1円（{PRODUCTS[product][2]+1}円）〜99,999円で指定してください。",
                          "販売価格は製造価格＋1円（{PRODUCTS[product][2]+1}円）以上で指定してください。")
    return source
edit('market.py',market)

fd,tmp=tempfile.mkstemp(prefix='.market-bigint-',suffix='.zip',dir='.')
os.close(fd)
try:
    with ZipFile(tmp,'w') as dest:
        for info,data in entries:
            dest.writestr(info,data)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print('Preserved e-notation on the wire, exact unit prices and finite DB safeguards')
