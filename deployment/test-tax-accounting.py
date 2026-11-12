"""Verify tax reduces cash but not ranked net profit or displayed expenses."""
import sqlite3, json
from pathlib import Path
import accounts, market, bank

db=sqlite3.connect(':memory:')
db.row_factory=sqlite3.Row
db.executescript("""
CREATE TABLE players(id TEXT, display_name TEXT, class_number INTEGER);
CREATE TABLE factory_totals(player TEXT, manufactured INTEGER, purchases INTEGER);
CREATE TABLE bank_accounts(player TEXT, tax INTEGER);
CREATE TABLE sales(player_id TEXT, product_id TEXT, sold_quantity INTEGER, unit_price INTEGER, unit_cost INTEGER);
CREATE TABLE actions(player TEXT, payload TEXT, result TEXT);
""")
db.execute("INSERT INTO players VALUES ('p','Player',1)")
db.execute("INSERT INTO factory_totals VALUES ('p',5,7)")
db.execute("INSERT INTO bank_accounts VALUES ('p',45)")
db.execute("INSERT INTO sales VALUES ('p','white',10,10,2)")
db.execute("INSERT INTO actions VALUES ('p',?,?)",
           (json.dumps(['upgrade']),json.dumps({'spent':7})))
identity=object.__new__(accounts.Accounts)
identity.db=db
identity.postgres=False
def rank():
    r=identity.rankings_many(('net_profit',))['net_profit']
    return next(x['net_profit'] for x in r['individual'] if x['id']=='p'), next(x['net_profit'] for x in r['classes'] if x['class_number']==1)
assert rank()==(73,73),rank()
db.execute("UPDATE bank_accounts SET tax=200000 WHERE player='p'")
assert rank()==(73,73),rank()

game=object.__new__(market.Game)
game.db=db
game.accounts=type('Identity',(),{'postgres':False,'identity':lambda self,token,now:{'id':'p'}})()
game.clock=lambda:0
result=game.breakdown('test-token')
assert sum(x['amount'] for x in result['income'])==100,result
assert sum(x['amount'] for x in result['expense'])==27,result
assert not any(x['key']=='tax' for x in result['expense']),result
db.execute("UPDATE bank_accounts SET tax=999999999 WHERE player='p'")
assert sum(x['amount'] for x in game.breakdown('test-token')['expense'])==27

# Tax deductions from actual cash must remain in both source paths.
market_source=Path(market.__file__).read_text()
bank_source=Path(bank.__file__).read_text()
assert 'count * (price - cost) - tax' in market_source
assert 'cash=bsub(cash,?)' in bank_source
print('PASS: tax ledger does not change individual/class net profit or expense charts; cash still taxed.')
