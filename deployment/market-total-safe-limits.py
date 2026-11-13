"""Enforce safe *total value* sizes at all market transaction entry points.

DB NUMERIC is finite. A 50,000 digit money transaction supports e4000 and
e10000 and leaves room for taxes, aggregate accounts, and purchase history.
Only code in the archive is changed, never stored player data.
"""
from zipfile import ZipFile
from pathlib import Path
import tempfile,os

file=Path("hare-machi-render.zip")
with ZipFile(file) as zipfile:
    entries=[(i,zipfile.read(i.filename)) for i in zipfile.infolist()]

def replacement(data,old,new):
    if data.count(old)!=1:
        if new in data and old not in data:return data
        raise RuntimeError("Not exactly one source occurrence: "+old[:110])
    return data.replace(old,new)

for i,(info,raw) in enumerate(entries):
    if info.filename!="market.py":continue
    data=raw.decode()
    data=replacement(data,
        "PRODUCTS = {'white':",
        '''MARKET_MAX_TOTAL_DIGITS=50000
# The number of bits in a 50,000-digit decimal integer is ~166097.
MARKET_MAX_TOTAL_BITS=166100
def ensure_market_total(quantity,price):
    if type(quantity) is not int or type(price) is not int or quantity<0 or price<0:
        raise ValueError('個数・販売価格を確認してください。')
    if quantity and price:
        # Fast prefilter before building the huge product.
        if quantity.bit_length()+price.bit_length()>MARKET_MAX_TOTAL_BITS+2:
            raise ValueError('数量×販売価格がデータベースの安全範囲を超えています。')
        total=quantity*price
        if total >= 10**MARKET_MAX_TOTAL_DIGITS:
            raise ValueError('数量×販売価格がデータベースの安全範囲を超えています。')

PRODUCTS = {'white':''')
    data=replacement(data,
        "                if kind=='set_price':\n                    if not existing:raise ValueError('販売中の商品がありません。')",
        "                if kind=='set_price':\n                    if not existing:raise ValueError('販売中の商品がありません。')\n                    ensure_market_total(existing['quantity'],price)")
    data=replacement(data,
        "                    total=quantity+(existing['quantity'] if existing else 0)\n                    result=self._reserve_shipment",
        "                    total=quantity+(existing['quantity'] if existing else 0)\n                    ensure_market_total(total,price)\n                    result=self._reserve_shipment")
    data=replacement(data,
        "        spent = quantity * average\n        if self.db.execute",
        "        ensure_market_total(quantity,average)\n        spent = quantity * average\n        if self.db.execute")
    data=replacement(data,
        "                if existing:\n                    self.db.execute('UPDATE stock SET quantity=badd(quantity,?)",
        "                ensure_market_total(quantity,price)\n                if existing:\n                    self.db.execute('UPDATE stock SET quantity=badd(quantity,?)")
    entries[i]=(info,data.encode())
    break
else:raise RuntimeError("market.py missing")

fd,tmp=tempfile.mkstemp(prefix=".safe-market-total-",suffix=".zip",dir=".")
os.close(fd)
try:
    with ZipFile(tmp,"w") as dest:
        for info,raw in entries:dest.writestr(info,raw)
    os.replace(tmp,file)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print("Bounded and checked all exact market transaction totals.")
