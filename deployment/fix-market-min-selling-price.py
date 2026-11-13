"""Enforce manufacturing cost + 1 yen as minimum market selling price.

Patches only source files in the existing Render archive. Existing listings
and player balances are not changed retroactively.
"""
from pathlib import Path
from zipfile import ZipFile
import os, tempfile

archive=Path("hare-machi-render.zip")
with ZipFile(archive) as source:
    entries=[(info,source.read(info.filename)) for info in source.infolist()]

def replace_once(filename,old,new):
    for i,(info,data) in enumerate(entries):
        if info.filename!=filename: continue
        text=data.decode("utf-8")
        if old not in text and new in text:return
        if text.count(old)!=1:
            raise RuntimeError(f"Expected one match in {filename}: {old[:95]}")
        entries[i]=(info,text.replace(old,new).encode("utf-8"))
        return
    raise RuntimeError("Missing archive member: "+filename)

# Server authority: neither new listings nor edits nor the legacy shipment
# route may bypass the per-product manufacturing-price floor.
replace_once("market.py",
    "if type(price) is not int or not 1<=price<=99999:raise ValueError('販売価格は1〜99,999円で指定してください。')",
    "if type(price) is not int or not PRODUCTS[product][2]+1<=price<=99999:raise ValueError(f'販売価格は製造価格＋1円（{PRODUCTS[product][2]+1}円）〜99,999円で指定してください。')")
replace_once("market.py",
    "if type(quantity) is not int or quantity<1 or type(price) is not int or not 1<=price<=99999: raise ValueError('数量・価格が範囲外です。')",
    "if type(quantity) is not int or quantity<1 or type(price) is not int or not PRODUCTS[product][2]+1<=price<=99999: raise ValueError(f'数量・価格が範囲外です。最低販売価格は{PRODUCTS[product][2]+1}円です。')")

# Frontend: use the same local product cost metadata, for useful immediate
# validation and a product-specific native number input minimum.
replace_once("static/app.js",
    "if(!Number.isInteger(request.price)||request.price<1||request.price>99999)return notice('販売価格は1〜99,999円で指定してください。');",
    "if(!Number.isInteger(request.price)||request.price<chosen.cost+1||request.price>99999)return notice('販売価格は製造価格＋1円（'+(chosen.cost+1)+'円）〜99,999円で指定してください。');")
replace_once("static/app.js",
    "ui('product').onchange=()=>{ui('price').value=pending()?.price??prices[Number(ui('product').value)];",
    "ui('product').onchange=()=>{ui('price').min=String(p().cost+1);ui('price').value=pending()?.price??prices[Number(ui('product').value)];")
replace_once("static/app.js",
    "ui('price').value=8;ui('price').oninput=",
    "ui('price').min=String(p().cost+1);ui('price').value=8;ui('price').oninput=")
replace_once("static/index.html",
    '<label>販売価格<input data-ui="price" type="number" min="1" max="99999"',
    '<label>販売価格（製造価格＋1円以上）<input data-ui="price" type="number" min="2" max="99999"')

fd,tmp=tempfile.mkstemp(prefix=".min-market-price-",suffix=".zip",dir=".")
os.close(fd)
try:
    with ZipFile(tmp,"w") as output:
        for info,data in entries:
            output.writestr(info,data)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print("Market prices restricted to manufacturing cost + 1 yen.")
