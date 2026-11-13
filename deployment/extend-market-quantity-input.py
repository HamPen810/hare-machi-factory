"""Patch the currently deployed archive without changing user data."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import os, tempfile

archive=Path('hare-machi-render.zip')
with ZipFile(archive) as original:
    items={item.filename:(item,original.read(item.filename)) for item in original.infolist()}

def replace_once(name,old,new):
    item,data=items[name]
    source=data.decode('utf-8')
    if old not in source:
        if new in source:
            return
        raise RuntimeError(f'Expected pattern absent from {name}: {old[:70]}')
    if source.count(old)!=1:
        raise RuntimeError(f'Ambiguous replacement in {name}')
    items[name]=(item,source.replace(old,new).encode('utf-8'))

replace_once('static/numbers.js',
'''  function parseWhole(input, scale = 0) {
    const match = /^([0-9]+)(?:\\.([0-9]+))?(?:[eE]([+-]?[0-9]{1,4}))?$/.exec(input.trim());
    if (!match || input.length > 10010) return null;
    const [, whole, fraction = '', exponent = '0'] = match;
    const digits = (whole + fraction).replace(/^0+/, '');
    if (!digits) return 0n;
    const shift = Number(exponent) - fraction.length + scale;
    if (shift >= 0) return digits.length + shift <= 10000 ? BigInt(digits + '0'.repeat(shift)) : null;
    if (-shift >= digits.length || /[1-9]/.test(digits.slice(shift))) return null;
    return BigInt(digits.slice(0,shift));
  }''',
'''  // PostgreSQL NUMERIC supports at most 131072 digits before the decimal.
  // Leave headroom for monetary multiplication and running totals.
  const MAX_INTEGER_DIGITS = 100000;
  function parseWhole(input, scale = 0) {
    const source = String(input ?? '').trim();
    if (source.length > 4096) return null;
    const match = /^([0-9]+)(?:\\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?$/.exec(source);
    if (!match) return null;
    const [, whole, fraction = '', exponent = '0'] = match;
    const digits = (whole + fraction).replace(/^0+/, '');
    if (!digits) return 0n;
    if (exponent.replace(/^[+-]?0*/, '').length > 6) return null;
    const shift = Number(exponent) - fraction.length + scale;
    if (!Number.isSafeInteger(shift)) return null;
    if (shift >= 0) {
      if (digits.length + shift > MAX_INTEGER_DIGITS) return null;
      return BigInt(digits + '0'.repeat(shift));
    }
    const cut = digits.length + shift;
    if (cut <= 0 || /[1-9]/.test(digits.slice(cut))) return null;
    return BigInt(digits.slice(0, cut));
  }''')
replace_once('static/app.js',
"if(kind==='add_listing'&&(!/^[0-9]+$/.test(request.quantity)||big(request.quantity)<1n||big(request.quantity)>big(stock?.quantity||0)))return notice('在庫の範囲内で出荷数を指定してください。');",
"if(kind==='add_listing'){const amount=parseWhole(request.quantity);if(amount===null||amount<1n)return notice('出荷数は1以上の整数で入力してください（例：1e6）。');if(amount>big(stock?.quantity||0))return notice('在庫の範囲内で出荷数を指定してください。');request.quantity=String(amount);}")
replace_once('static/app.js',
"const value=/^[0-9]+$/.test(exact)?big(exact):0n;",
"const value=parseWhole(exact)??0n;")
replace_once('static/index.html',
'data-ui="quantity" type="text" pattern="[0-9]+" inputmode="numeric"',
'data-ui="quantity" type="text" inputmode="decimal" placeholder="例 1e6"')
old='''                    if isinstance(data.get('quantity'),str):
                        quantity_text=data['quantity'].strip()
                        if len(quantity_text)>10010:
                            raise ValueError('個数が大きすぎます。')
                        match=re.fullmatch(r'([0-9]+)(?:\\.([0-9]+))?(?:[eE]([+-]?[0-9]{1,4}))?',quantity_text)
                        if match:
                            whole,fraction,exponent=match.group(1),match.group(2) or '',int(match.group(3) or '0')
                            digits=(whole+fraction).lstrip('0')
                            shift=exponent-len(fraction)
                            if not digits:parsed=0
                            elif shift>=0 and len(digits)+shift<=10000:
                                parsed=int(digits+'0'*shift)
                            elif shift<0 and -shift<len(digits) and not any(c!='0' for c in digits[shift:]):
                                parsed=int(digits[:shift])
                            else:parsed=None
                            if parsed is not None:data['quantity']=parsed
'''
new='''                    if isinstance(data.get('quantity'),str):
                        quantity_text=data['quantity'].strip()
                        if len(quantity_text)>4096:
                            raise ValueError('個数の入力文字列が長すぎます。指数表記を利用してください。')
                        match=re.fullmatch(r'([0-9]+)(?:\\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?',quantity_text)
                        if match:
                            whole,fraction=match.group(1),match.group(2) or ''
                            exponent_text=match.group(3) or '0'
                            normalized=exponent_text.lstrip('+-0')
                            if len(normalized)>6:
                                raise ValueError('この数量はデータベースで表現できる範囲を超えています。')
                            exponent=int(exponent_text)
                            digits=(whole+fraction).lstrip('0')
                            shift=exponent-len(fraction)
                            if not digits:
                                data['quantity']=0
                            elif shift>=0:
                                if len(digits)+shift>100000:
                                    raise ValueError('この数量はデータベースで表現できる範囲を超えています。')
                                data['quantity']=int(digits+'0'*shift)
                            else:
                                cut=len(digits)+shift
                                if cut>0 and not any(c!='0' for c in digits[cut:]):
                                    data['quantity']=int(digits[:cut])
'''
replace_once('server.py',old,new)
fd,tmp=tempfile.mkstemp(suffix='.zip',dir='.')
os.close(fd)
try:
    with ZipFile(tmp,'w') as output:
        for name,(info,data) in items.items():
            output.writestr(info,data)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print('Patched market/shipment exact-integer input in production ZIP')
