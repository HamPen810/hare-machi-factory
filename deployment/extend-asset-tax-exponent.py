"""Extend asset tax with exponent-linked multiplier for combined holdings.

This updates only code inside the existing ZIP, never player/account data.
"""
from pathlib import Path
from zipfile import ZipFile
import os
import tempfile

archive = Path("hare-machi-render.zip")
with ZipFile(archive) as source:
    entries = [(info, source.read(info.filename)) for info in source.infolist()]

def modify(path, old, new):
    for i, (info, raw) in enumerate(entries):
        if info.filename != path:
            continue
        src = raw.decode("utf-8")
        if old not in src:
            if new in src:
                return
            raise RuntimeError("Unexpected source in " + path)
        if src.count(old) != 1:
            raise RuntimeError("Non-unique replacement in " + path)
        entries[i] = (info, src.replace(old, new).encode("utf-8"))
        return
    raise RuntimeError("File not found: " + path)

before = '''def asset_tax(game, policy, *, apply):
    from market import PRODUCTS'''
after = '''def asset_exponent_multiplier(value):
    """10x additional tax for each complete 10 decimal-exponent levels.

    Example: 1e9 -> 1x, 1e10 -> 10x, 1e20 -> 100x.
    Uses integer arithmetic so very large game amounts do not go through float
    and do not hit Python's int-to-decimal-string conversion limit.
    """
    value = max(0, int(value))
    if value < 10**10:
        return 1
    # Estimate decimal digits from bit length, then correct exact boundaries.
    digits = ((value.bit_length() - 1) * 30103) // 100000 + 1
    if value < 10 ** (digits - 1):
        digits -= 1
    elif value >= 10 ** digits:
        digits += 1
    return 10 ** ((digits - 1) // 10)


def asset_tax(game, policy, *, apply):
    from market import PRODUCTS'''
modify('bank.py',before,after)
old='''    taxes = [(player,exponential_tax_due(max(0,value),policy)) for player,value in assets.items()]'''
new='''    # Both cash (including deposits) and all inventory valued at fixed product
    # list prices contribute to ONE exponent tier. Do not tax twice by asset type.
    taxes = [(player,exponential_tax_due(max(0,value),policy)
              * asset_exponent_multiplier(value)) for player,value in assets.items()]'''
modify('bank.py',old,new)
modify('static/admin.html',
    '実行するたびに、その時点の資産に対して一度課税します。',
    '実行するたびに、その時点の資産に対して一度課税します。さらに、所持金・預金・在庫定価評価額を合算した総資産の指数が10増えるごとに課税額が10倍になります。')

fd,tmp=tempfile.mkstemp(prefix=".asset-tax-",suffix=".zip",dir=".")
os.close(fd)
try:
    with ZipFile(tmp,"w") as out:
        for info,raw in entries:
            out.writestr(info,raw)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
print("Updated combined asset tax exponent multiplier in ZIP")
