"""Regressions for live-balance forgiveness and unrelated account isolation."""
import os,sys,sqlite3
if os.environ.get('PRODUCTION_MODULE_DIR'):
    sys.path.insert(0,os.environ['PRODUCTION_MODULE_DIR'])
from types import SimpleNamespace
from exact import setup
from admin_fund_ops import install,perform,history
import bank

db=sqlite3.connect(':memory:')
db.row_factory=sqlite3.Row
setup(db)
db.execute('PRAGMA foreign_keys=ON')
db.executescript("""
CREATE TABLE players(id TEXT PRIMARY KEY,student_id TEXT UNIQUE,display_name TEXT);
CREATE TABLE factories(player TEXT PRIMARY KEY REFERENCES players(id),cash NUMERIC NOT NULL);
CREATE TABLE stock(player TEXT,product TEXT,quantity NUMERIC);
CREATE TABLE listings(player TEXT,product TEXT,quantity NUMERIC);
CREATE TABLE admin_fund_transfers(key TEXT PRIMARY KEY,player_id TEXT,student_id TEXT,name TEXT,
  kind TEXT,amount NUMERIC,before_cash NUMERIC,after_cash NUMERIC,note TEXT,created_at BIGINT);
""")
bank.initialize(db)
install(db)
for pid,sid,cash,debt in [('p','2101',-50,250),('q','2102',-7,0),
                           ('r','2103',80,90),('s','2104',100,0)]:
    db.execute('INSERT INTO players VALUES(?,?,?)',(pid,sid,pid))
    db.execute('INSERT INTO factories VALUES(?,?)',(pid,cash))
    db.execute('INSERT INTO bank_accounts(player,debt) VALUES(?,?)',(pid,debt))
db.execute("INSERT INTO bank_contracts VALUES('borrow-p','p','borrow',200,250,0,0)")
db.execute("INSERT INTO bank_contracts VALUES('borrow-r','r','borrow',80,90,0,0)")
db.commit()
admin=SimpleNamespace(db=db,postgres=False)
now=1794480000000
def preview(payload):return perform(admin,{**payload,'action':'preview'},now)
def apply(payload,pre,key):
    return perform(admin,{**payload,'action':'apply','key':key,
                   'preview_digest':pre['digest']},now)
def balance(player):
    return db.execute('SELECT cash FROM factories WHERE player=?',(player,)).fetchone()[0]
def outstanding(player):
    return db.execute('SELECT debt FROM bank_accounts WHERE player=?',(player,)).fetchone()[0]

# A different current balance and even a different bank contract amount at
# execution MUST NOT cause preview rejection.
payload={'scope':'single','kind':'forgive','student_id':'2101','note':'reset'}
estimated=preview(payload)
assert estimated['cash_restored_total']==50 and estimated['total']==250,estimated
db.execute("UPDATE factories SET cash=-123 WHERE player='p'")
db.execute("UPDATE bank_accounts SET debt=410 WHERE player='p'")
db.execute("UPDATE bank_contracts SET amount=410 WHERE player='p' AND kind='borrow'")
db.commit()
result=apply(payload,estimated,'debt-a-0000000000000000001')
assert (result['total'],result['cash_restored_total'])==(410,123),result
assert balance('p')==0 and outstanding('p')==0
assert db.execute("SELECT COUNT(*) FROM bank_contracts WHERE player='p' AND kind='borrow'").fetchone()[0]==0
assert history(db)[0]['cash_restored']==123
assert apply(payload,estimated,'debt-a-0000000000000000001')['already_applied']
assert balance('p')==0

# Cash-only overdraft remains eligible, with estimates allowed to change.
p2={'scope':'single','kind':'forgive','student_id':'2102','note':'cash-only'}
pre=preview(p2)
assert pre['total']==0 and pre['cash_restored_total']==7
db.execute("UPDATE factories SET cash=-400 WHERE player='q'")
db.commit()
result=apply(p2,pre,'debt-b-0000000000000000002')
assert result['total']==0 and result['cash_restored_total']==400
assert balance('q')==0

# A cash value that has become positive must remain positive.
p3={'scope':'single','kind':'forgive','student_id':'2103','note':''}
pre=preview(p3)
db.execute("UPDATE factories SET cash=999 WHERE player='r'")
db.commit()
result=apply(p3,pre,'debt-c-0000000000000000003')
assert balance('r')==999 and outstanding('r')==0
assert result['cash_restored_total']==0

# Preview becoming irrelevant must finish successfully as a no-op.
db.execute("UPDATE factories SET cash=-18 WHERE player='q'")
db.commit()
pre=preview(p2)
db.execute("UPDATE factories SET cash=0 WHERE player='q'")
db.commit()
result=apply(p2,pre,'debt-d-0000000000000000004')
assert result['count']==0 and result['cash_restored_total']==0

# Batch recalculates negative cash after preview, without touching solvent.
db.execute("UPDATE factories SET cash=-11 WHERE player='p'")
db.execute("UPDATE factories SET cash=-19 WHERE player='q'")
db.commit()
bulk={'scope':'bulk','kind':'forgive','min_assets':'','max_assets':'','note':'batch'}
pre=preview(bulk)
db.execute("UPDATE factories SET cash=-31 WHERE player='p'")
db.execute("UPDATE factories SET cash=-63 WHERE player='q'")
db.commit()
actual=apply(bulk,pre,'debt-e-0000000000000000005')
assert actual['cash_restored_total']==94
assert balance('p')==0 and balance('q')==0
assert balance('r')==999 and balance('s')==100
assert actual['count']==2

print('PASS live stale estimate, fresh bank debt, overdraft-only, positive cash, no-op, idempotency, batch latest balances')
