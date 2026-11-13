"""Fix asset tax bands being 2x while progressive exponent multiplier is 10x.

Only modifies bundled code; leaves the existing saved bank tax policy and all
player data untouched. Sales-tax bands retain their previous behavior.
"""
from pathlib import Path
from zipfile import ZipFile
import os,tempfile
archive=Path('hare-machi-render.zip')
with ZipFile(archive) as src:
    entries=[(info,src.read(info.filename)) for info in src.infolist()]

def replace_once(name,old,new):
    for index,(info,raw) in enumerate(entries):
        if info.filename!=name:continue
        text=raw.decode('utf-8')
        if old not in text and new in text:return
        if text.count(old)!=1:raise RuntimeError(f'Unexpected {name} source for {old[:75]}')
        entries[index]=(info,text.replace(old,new).encode('utf-8'))
        return
    raise RuntimeError('Missing file '+name)

anchor='''def asset_exponent_multiplier(value):'''
addition='''def asset_exponential_tax_due(assets, policy):
    """Asset-only progressive tax: each succeeding band is 10x wider and
    its marginal rate is 10x higher. Saved sales-tax settings are unchanged.
    Every operation is integer-exact; float and str(huge_int) are avoided.
    """
    taxable = max(0, int(assets) - int(policy['threshold']))
    step = int(policy['step'])
    if not taxable:
        return 0
    # Number of completed bands is floor(log10(9*taxable/step+1)).
    level_value = 9 * taxable // step + 1
    power = ((level_value.bit_length()-1) * 30103) // 100000
    while level_value < 10**power:
        power -= 1
    while level_value >= 10**(power+1):
        power += 1
    factor = 10**power
    completed_width = step * (factor-1) // 9
    completed_weighted = step * (factor*factor-1) // 99
    weighted = completed_weighted + (taxable-completed_width)*factor
    return weighted * int(policy['base_bps']) // 10000


def asset_exponent_multiplier(value):'''
replace_once('bank.py',anchor,addition)
replace_once('bank.py',
    'taxes = [(player,exponential_tax_due(max(0,value),policy)\n              * asset_exponent_multiplier(value)) for player,value in assets.items()]',
    'taxes = [(player,asset_exponential_tax_due(max(0,value),policy)\n              * asset_exponent_multiplier(value)) for player,value in assets.items()]')
replace_once('static/admin.html',
    '区分ごとに税率と区分の幅を2倍にする',
    '売上課税（従来方式）：区分ごとに税率と幅を2倍にする')
replace_once('static/admin.html',
    '総資産の指数が1000未満では10増えるごと、1000以上2000未満では5増えるごと、2000以上では2増えるごとに追加課税倍率が10倍になります。',
    '総資産課税は売上課税と異なり、基本の課税区分の幅と税率が段階ごとに10倍になります。さらに総資産の指数が1000未満では10増えるごと、1000以上2000未満では5増えるごと、2000以上では2増えるごとに追加課税倍率が10倍になります。試算を確認してから実行してください。')
fd,tmp=tempfile.mkstemp(prefix='.asset-tax-tens-',suffix='.zip',dir='.')
os.close(fd)
try:
    with ZipFile(tmp,'w') as z:
        for info,raw in entries:z.writestr(info,raw)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print('Fixed 10x asset tax band progression; existing sales-tax regime preserved')
