"""Make taxes affect cash only, not expenses or net-profit standings.

Run against the *current* GitHub deployment ZIP. Fail safely if accounting
locations differ instead of replacing older application files.
"""
from pathlib import Path
from zipfile import ZipFile
import io

archive=Path("hare-machi-render.zip")
with ZipFile(archive) as src:
    entries=[(info,src.read(info)) for info in src.infolist()]
    comment=src.comment
contents={info.filename:data for info,data in entries}

def update(name, before, after, expected=1):
    data=contents[name].decode("utf-8")
    n=data.count(before)
    if n!=expected:
        raise RuntimeError(f"{name}: expected {expected} matches, got {n} for {before[:70]!r}")
    contents[name]=data.replace(before,after).encode("utf-8")

# Cumulative net_profit is recomputed from sales and actual purchases.
# Do not deduct the separate bank_accounts.tax cumulative ledger.
update("accounts.py",
"""        for row in self.db.execute('SELECT player,tax FROM bank_accounts'):
            if row['player'] in people:
                people[row['player']]['net_profit'] -= row['tax']
""", "")

# Tax may still be deducted from cash during sale/asset tax as before,
# but it must not be in the expense breakdown returned to charts.
update("market.py",
"""        bank_row = self.db.execute('SELECT tax FROM bank_accounts WHERE player=?',(p,)).fetchone()
        costs['tax'] = bank_row[0] if bank_row else 0
""","")

old="純利益は売上から材料費・強化費・税金などの支出を引いた額です。"
new="純利益は売上から材料費・強化費などの支出を引いた額です。税金は所持金から差し引かれますが、支出額と純利益の集計には含めません。"
update("static/index.html",old,new)
update("rules-default.txt",old,new)

# Avoid unnecessary changes to game logic, persisted data and environments.
with ZipFile(archive,"w") as dst:
    dst.comment=comment
    for info,data in entries:
        dst.writestr(info,contents[info.filename])
with ZipFile(archive) as check:
    assert check.testzip() is None
    for name in contents:
        assert check.read(name)==contents[name]
    for info,data in entries:
        if info.filename not in ("accounts.py","market.py","static/index.html","rules-default.txt"):
            assert check.read(info.filename)==data
print("PASS: tax excluded from expense breakdown and net profit; cash tax collection unchanged.")
