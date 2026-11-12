"""Regression: forgive bank loan and negative cash together, exactly once."""
import sqlite3
from types import SimpleNamespace
from exact import setup
from admin_fund_ops import install,perform,history
import bank

db=sqlite3.connect(':memory:')
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
for pid,student,name,cash,debt in (
    ('p','2101','Overdrawn loan',-500,300),
    ('q','2102','Cash only',-70,0),
    ('r','2103','Positive cash',400,200),
    ('s','2104','Solvent',100,0),
):
    db.execute('INSERT INTO players VALUES(?,?,?)',(pid,student,name))
    db.execute('INSERT INTO factories VALUES(?,?)',(pid,cash))
    db.execute('INSERT INTO bank_accounts(player,deposit,debt) VALUES(?,?,?)',
               (pid,150 if pid=='p' else 0,debt))
db.execute("INSERT INTO bank_contracts VALUES('b1','p','borrow',220,260,0,0)")
db.execute("INSERT INTO bank_contracts VALUES('b2','p','borrow',30,40,0,0)")
db.execute("INSERT INTO bank_contracts VALUES('d1','p','lend',100,150,9999,0)")
db.execute("INSERT INTO bank_contracts VALUES('b3','r','borrow',180,200,0,0)")
db.commit()
admin=SimpleNamespace(db=db,postgres=False)
now=1794480000000
def cash(pid):
    return int(db.execute('SELECT cash FROM factories WHERE player=?',(pid,)).fetchone()[0])
def debt(pid):
    return int(db.execute('SELECT debt FROM bank_accounts WHERE player=?',(pid,)).fetchone()[0])
def view(p):
    return perform(admin,{**p,'action':'preview'},now)
def run(p,v,key):
    return perform(admin,{**p,'action':'apply','preview_digest':v['digest'],'key':key},now)

# Positive loan and negative cash, with preserved deposit.
p={'scope':'single','kind':'forgive','student_id':'2101','note':'full relief'}
v=view(p)
assert v['count']==1 and v['total']==300 and v['cash_restored_total']==500,v
assert v['people'][0]['after_cash']==0
out=run(p,v,'abcd-0000000000000001')
assert out['total']==300 and out['cash_restored_total']==500,out
assert cash('p')==0 and debt('p')==0
assert db.execute("SELECT COUNT(*) FROM bank_contracts WHERE player='p' AND kind='borrow'").fetchone()[0]==0
assert db.execute("SELECT COUNT(*) FROM bank_contracts WHERE player='p' AND kind='lend'").fetchone()[0]==1
assert db.execute("SELECT deposit FROM bank_accounts WHERE player='p'").fetchone()[0]==150
assert run(p,v,'abcd-0000000000000001')['already_applied']
assert cash('p')==0 and len(history(db))==1
assert history(db)[0]['cash_restored']==500

# Overdraft-only player must be eligible even with bank debt already zero.
q={'scope':'single','kind':'forgive','student_id':'2102','note':'overdraft'}
v=view(q)
assert v['total']==0 and v['cash_restored_total']==70 and v['people'][0]['after_cash']==0,v
run(q,v,'abcd-0000000000000002')
assert cash('q')==0 and debt('q')==0
assert history(db)[0]['cash_restored']==70 and history(db)[0]['debt']==0

# Positive cash unchanged, bank debt cancelled.
r={'scope':'single','kind':'forgive','student_id':'2103','note':'loan only'}
v=view(r)
assert v['total']==200 and v['cash_restored_total']==0
run(r,v,'abcd-0000000000000003')
assert cash('r')==400 and debt('r')==0

# Nonnegative cash and zero bank debt must not create an audit entry.
s={'scope':'single','kind':'forgive','student_id':'2104','note':''}
try:
    view(s)
    raise AssertionError('forgave an account with no debt or overdraft')
except ValueError as exc:
    assert '銀行借入もマイナス残高もありません' in str(exc)
assert cash('s')==100

# A bulk operation can include overdraft-only players too.
db.execute("UPDATE factories SET cash=-9 WHERE player='q'")
db.execute("UPDATE factories SET cash=-6 WHERE player='p'")
db.execute("UPDATE bank_accounts SET debt=10 WHERE player='p'")
db.execute("INSERT INTO bank_contracts VALUES('b4','p','borrow',9,10,0,0)")
db.commit()
bulk={'scope':'bulk','kind':'forgive','min_assets':'','max_assets':'','note':'bulk relief'}
v=view(bulk)
assert v['count']==2 and v['total']==10 and v['cash_restored_total']==15,v
assert all(x['after_cash']==0 for x in v['people'])
run(bulk,v,'abcd-0000000000000004')
assert (cash('p'),cash('q'),cash('r'),cash('s'))==(0,0,400,100)
assert debt('p')==0
assert db.execute("SELECT COUNT(*) FROM admin_overdraft_cancellations").fetchone()[0]==5

# Stale preview cannot overwrite a balance changed by another action.
db.execute("UPDATE factories SET cash=-22 WHERE player='q'")
db.commit()
v=view(q)
db.execute("UPDATE factories SET cash=-23 WHERE player='q'")
db.commit()
try:
    run(q,v,'abcd-0000000000000005')
    raise AssertionError('stale forgiveness applied')
except ValueError as exc:
    assert 'もう一度試算' in str(exc)
assert cash('q')==-23

print('PASS: loan and overdraft relief, cash-only overdraft, positive cash protected, deposit preserved, bulk, audit, idempotence, stale preview')
