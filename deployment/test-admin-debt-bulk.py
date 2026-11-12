import os,sys
if os.environ.get('PRODUCTION_MODULE_DIR'):
    sys.path.insert(0,os.environ['PRODUCTION_MODULE_DIR'])
"""Regression tests: wealth-based grants, overdraft collections and debt forgiveness."""
import sqlite3
from types import SimpleNamespace
from exact import setup
from admin_fund_ops import install, perform, history
from accounts import Accounts
import bank

db=sqlite3.connect(':memory:')
setup(db)
db.execute('PRAGMA foreign_keys=ON')
db.execute('CREATE TABLE players(id TEXT PRIMARY KEY,student_id TEXT,display_name TEXT,class_number INTEGER)')
db.execute('CREATE TABLE factories(player TEXT PRIMARY KEY,cash NUMERIC)')
db.execute('CREATE TABLE stock(player TEXT,product TEXT,quantity NUMERIC)')
db.execute('CREATE TABLE listings(player TEXT,product TEXT,quantity NUMERIC)')
db.execute('CREATE TABLE factory_totals(player TEXT,manufactured NUMERIC,purchases NUMERIC)')
db.execute('CREATE TABLE sales(player_id TEXT,sold_quantity NUMERIC,unit_price NUMERIC,unit_cost NUMERIC)')
db.execute('CREATE TABLE admin_fund_transfers(key TEXT PRIMARY KEY,player_id TEXT,student_id TEXT,name TEXT,kind TEXT,amount NUMERIC,before_cash NUMERIC,after_cash NUMERIC,note TEXT,created_at BIGINT)')
bank.initialize(db)
install(db)
db.execute("INSERT INTO players VALUES('p','2101','Player A',1)")
db.execute("INSERT INTO players VALUES('q','2102','Player B',1)")
db.execute("INSERT INTO players VALUES('r','2103','Player C',1)")
db.execute("INSERT INTO factories VALUES('p',100)")
db.execute("INSERT INTO factories VALUES('q',500)")
db.execute("INSERT INTO factories VALUES('r',50)")
db.execute("INSERT INTO stock VALUES('p','white',20)")
db.execute("INSERT INTO stock VALUES('q','sea',100)")
db.execute("INSERT INTO bank_accounts(player,deposit,debt) VALUES('p',150,300)")
db.execute("INSERT INTO bank_accounts(player,deposit,debt) VALUES('q',20,700)")
db.execute("INSERT INTO bank_contracts VALUES('loan-p','p','borrow',250,300,0,0)")
db.execute("INSERT INTO bank_contracts VALUES('loan-q','q','borrow',600,700,0,0)")
db.execute("INSERT INTO bank_contracts VALUES('deposit-p','p','lend',100,150,10000,0)")
db.execute("INSERT INTO factory_totals VALUES('p',0,0)")
db.execute("INSERT INTO factory_totals VALUES('q',0,0)")
db.execute("INSERT INTO factory_totals VALUES('r',0,0)")
db.commit()
admin=SimpleNamespace(db=db,postgres=False)
now=1794480000000
key=lambda n:str(n)*16

def preview(payload):
 return perform(admin,{**payload,'action':'preview'},now)
def apply(payload,view,k):
 return perform(admin,{**payload,'action':'apply','preview_digest':view['digest'],'key':k},now)
def cash(pid):
 return db.execute('SELECT cash FROM factories WHERE player=?',(pid,)).fetchone()[0]

# Listed asset valuation: P cash100 + deposit150 + stock20*8=410,
# Q cash500 + deposit20 + stock100*15=2020, R=50.
payload={'scope':'bulk','kind':'grant','min_assets':'400','max_assets':'500','amount_mode':'fixed','amount':'90','note':'award'}
view=preview(payload)
assert view['count']==1 and view['people'][0]['student_id']=='2101',view
done=apply(payload,view,'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa')
assert cash('p')==190 and cash('q')==500
repeat=apply(payload,view,'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa')
assert repeat['already_applied'] and cash('p')==190
assert len(db.execute('SELECT * FROM admin_fund_transfers').fetchall())==1

# Percentage 50% of gross assets P now 500: collection250 even if cash190.
collect={'scope':'bulk','kind':'collect','min_assets':'400','max_assets':'600',
         'amount_mode':'percent','percentage_bps':5000,'note':'tax'}
v=preview(collect)
assert v['total']==250
assert apply(collect,v,'bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb')['count']==1
assert cash('p')==-60
# Stored old state no longer valid: forbid applying without fresh preview.
try:
 apply(collect,v,'cccccccc-cccc-4ccc-cccc-cccccccccccc')
 raise AssertionError('stale preview applied')
except ValueError as e:assert 'もう一度試算' in str(e)
assert cash('p')==-60

# Debt cancellation across all eligible accounts. Deposits remain.
forgive={'scope':'bulk','kind':'forgive','min_assets':'','max_assets':'','note':'amnesty'}
v=preview(forgive)
assert v['count']==2 and v['total']==1000,v
result=apply(forgive,v,'dddddddd-dddd-4ddd-dddd-dddddddddddd')
assert result['total']==1000
assert cash('p')==0 and cash('q')==500
assert result['cash_restored_total']==60
assert db.execute("SELECT deposit,debt FROM bank_accounts WHERE player='p'").fetchone()[0]==150
assert db.execute("SELECT debt FROM bank_accounts WHERE player='p'").fetchone()[0]==0
assert db.execute("SELECT debt FROM bank_accounts WHERE player='q'").fetchone()[0]==0
assert db.execute("SELECT COUNT(*) FROM bank_contracts WHERE kind='borrow'").fetchone()[0]==0
assert db.execute("SELECT COUNT(*) FROM bank_contracts WHERE kind='lend'").fetchone()[0]==1
assert len(history(db))==2
assert apply(forgive,v,'dddddddd-dddd-4ddd-dddd-dddddddddddd')['already_applied']
assert len(history(db))==2
assert len(db.execute('SELECT * FROM admin_fund_transfers').fetchall())==2

# Legacy debt without matching bank_contract is also forgiven.
db.execute("INSERT INTO bank_accounts(player,debt) VALUES('r',123)")
db.commit()
single={'scope':'single','kind':'forgive','student_id':'2103','note':'legacy'}
v=preview(single)
assert v['total']==123
apply(single,v,'eeeeeeee-eeee-4eee-eeee-eeeeeeeeeeee')
assert db.execute("SELECT debt FROM bank_accounts WHERE player='r'").fetchone()[0]==0
assert cash('r')==50

# Existing leaderboard net-profit includes only collections, not grants or forgiveness.
acc=object.__new__(Accounts)
acc.db=db;acc.postgres=False
ranking=acc.rankings_many(('net_profit','revenue'))
scores={r['display_name']:r['net_profit'] for r in ranking['net_profit']['individual']}
assert scores['Player A']==-250 and scores['Player B']==0 and scores['Player C']==0,scores

# No partial payouts after stale preview; same key cannot mutate different payload.
try:
 apply({'scope':'bulk','kind':'grant','min_assets':'','max_assets':'',
        'amount_mode':'fixed','amount':'99','note':'different'},view,
        'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa')
 raise AssertionError('different replay allowed')
except ValueError:pass

print('PASS: asset thresholds, percent/fixed, negative cash, idempotency, stale preview, deposits, legacy debt and profit ranking')
