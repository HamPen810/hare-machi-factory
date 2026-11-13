"""Increase the asset-tax exponent multiplier's frequency above e1000.

Safely patches only the current deployed ZIP. Does not touch player data.
"""
from pathlib import Path
from zipfile import ZipFile
import os, tempfile

archive=Path("hare-machi-render.zip")
with ZipFile(archive) as src:
    entries=[(info,src.read(info.filename)) for info in src.infolist()]

def patch(name,old,new):
    for i,(info,raw) in enumerate(entries):
        if info.filename!=name: continue
        s=raw.decode("utf-8")
        if new in s and old not in s: return
        if s.count(old)!=1:
            raise RuntimeError("Expected exactly one match in "+name)
        entries[i]=(info,s.replace(old,new).encode("utf-8"))
        return
    raise RuntimeError("Missing "+name)

patch("bank.py",
'''    return 10 ** ((digits - 1) // 10)


def asset_tax(game, policy, *, apply):''',
'''    exponent = digits - 1
    if exponent < 1000:
        tax_power = exponent // 10
    elif exponent < 2000:
        tax_power = 100 + (exponent - 1000) // 5
    else:
        tax_power = 300 + (exponent - 2000) // 2
    return 10 ** tax_power


def asset_tax(game, policy, *, apply):''')
patch("bank.py",
    '"""10x additional tax for each complete 10 decimal-exponent levels.',
    '"""10x tax for each 10 exponent levels, each 5 above e1000 and each 2 above e2000.')
patch("static/admin.html",
    '総資産の指数が10増えるごとに課税額が10倍になります。',
    '総資産の指数が1000未満では10増えるごと、1000以上2000未満では5増えるごと、2000以上では2増えるごとに追加課税倍率が10倍になります。')

fd,tmp=tempfile.mkstemp(prefix=".tax-brackets-",suffix=".zip",dir=".")
os.close(fd)
try:
    with ZipFile(tmp,"w") as z:
        for info,data in entries:
            z.writestr(info,data)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print("Updated progressive exponent brackets for combined assets.")
