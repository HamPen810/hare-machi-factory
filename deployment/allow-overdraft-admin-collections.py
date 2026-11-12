"""Treat admin cash collection as expense, including legacy collected funds.

Grants remain excluded from financial rankings. Collections may make cash
negative. All other account, market and banking behavior is unchanged.
"""
from pathlib import Path
from zipfile import ZipFile
import ast, io
archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    entries=[(info,z.read(info.filename)) for info in z.infolist()]
    comment=z.comment
files={info.filename:data for info,data in entries}
def substitute(filename,before,after):
    source=files[filename].decode('utf-8')
    n=source.count(before)
    if n!=1:raise RuntimeError(f'Unexpected {filename} layout: {n} occurrences of {before[:85]!r}')
    files[filename]=source.replace(before,after).encode('utf-8')

# Remove overdraft restriction, but retain atomic deduction and audit record.
substitute('admin.py',
"""            if kind=='collect' and previous_cash<amount:
                raise ValueError('所持金が徴収額に足りません。')
""",
'')
substitute('admin.py',
"""            else:
                updated=self.db.execute(
                    'UPDATE factories SET cash=bsub(cash,?) WHERE player=? AND bge(cash,?)',
                    (amount,player['id'],amount))
                if updated.rowcount!=1:
                    raise ValueError('所持金が徴収額に足りません。')
""",
"""            else:
                # Admin collection is allowed to overdraw; one atomic debit.
                updated=self.db.execute(
                    'UPDATE factories SET cash=bsub(cash,?) WHERE player=?',
                    (amount,player['id']))
                if updated.rowcount!=1:
                    raise ValueError('対象工場が見つかりません。')
""")

# The table must exist before normal player statistics are queried, even
# if an administrator has never used fund adjustment before.
substitute('admin.py',
"""            self.db.execute('CREATE TABLE IF NOT EXISTS site_rulebook(id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
""",
"""            self.db.execute('CREATE TABLE IF NOT EXISTS site_rulebook(id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
            self.db.execute(\"\"\"CREATE TABLE IF NOT EXISTS admin_fund_transfers(
                key TEXT PRIMARY KEY,
                player_id TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                student_id TEXT NOT NULL, name TEXT NOT NULL,
                kind TEXT NOT NULL, amount NUMERIC NOT NULL,
                before_cash NUMERIC NOT NULL, after_cash NUMERIC NOT NULL,
                note TEXT NOT NULL, created_at BIGINT NOT NULL)\"\"\")
""")

# Apply collection expense to net-profit ranking in both SQLite and PostgreSQL.
# Tax ledger and grants remain excluded.
substitute('accounts.py',
"""        if self.postgres:
            sales = self.db.execute(""",
"""        if self.postgres:
            for row in self.db.execute(
                "SELECT player_id,SUM(amount) AS total FROM admin_fund_transfers "
                "WHERE kind='collect' GROUP BY player_id"):
                if row['player_id'] in people:
                    people[row['player_id']]['net_profit'] -= row['total']
            sales = self.db.execute(""")
substitute('accounts.py',
"""        for row in self.db.execute('SELECT player_id,sold_quantity,unit_price,unit_cost FROM sales'):
""",
"""        # SQLite exact NUMERIC values may be stored as BigInt blobs; sum in
        # Python to avoid SQLite's 64-bit SUM restriction.
        for row in self.db.execute(
            "SELECT player_id,amount FROM admin_fund_transfers WHERE kind='collect'"):
            if row['player_id'] in people:
                people[row['player_id']]['net_profit'] -= row['amount']
        for row in self.db.execute('SELECT player_id,sold_quantity,unit_price,unit_cost FROM sales'):
""")

# The expense pie shows collections as a separate labelled line. Historical
# collections are included; there is no duplicate action-ledger spending.
substitute('market.py',
"""        costs={'materials':materials,'upgrade':0,'unlock':0,'helper':0,'sunpress':0,'islandline':0,'buy_market':0}
""",
"""        costs={'materials':materials,'upgrade':0,'unlock':0,'helper':0,'sunpress':0,
               'islandline':0,'buy_market':0,'admin_collect':0}
        for row in self.db.execute(
            "SELECT amount FROM admin_fund_transfers WHERE player_id=? AND kind='collect'",(p,)):
            costs['admin_collect']+=row['amount']
""")
substitute('static/app.js',
"buy_market:'市場での購入',",
"buy_market:'市場での購入',admin_collect:'管理者による徴収',")

substitute('static/admin.js',
""" if(kind==='collect'&&amount>BigInt(person.cash)){
  fundsStatus.textContent='対象アカウントの所持金が足りません。';return;
 }
""",
"")
substitute('static/admin.html',
"""補助金・徴収は所持金だけに反映し、売上・支出・純利益・ランキングには含めません。徴収は所持金の範囲内で行えます。""",
"""補助金は所持金だけに反映されます。徴収は支出・純利益に反映され、残高がマイナスになる場合も実行できます。""")

for name in ('admin.py','accounts.py','market.py'):
    ast.parse(files[name].decode(),filename=name)
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('admin.py','accounts.py','market.py','static/app.js','static/admin.js','static/admin.html'):
            assert z.read(info.filename)==data, info.filename
archive.write_bytes(out.getvalue())
print('PASS: admin collections debit below zero; historical collections included in expense and net profit; grants excluded')
