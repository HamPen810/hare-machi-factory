"""Verify admin collections can overdraw and count in expenses and net profit."""
import sqlite3
from types import SimpleNamespace
from admin import Admin
from accounts import Accounts
from market import Game
from exact import setup

db=sqlite3.connect(':memory:')
setup(db)
db.execute('PRAGMA foreign_keys=ON')
db.execute('CREATE TABLE players (id TEXT PRIMARY KEY,student_id TEXT UNIQUE,display_name TEXT,class_number INTEGER)')
db.execute('CREATE TABLE factories (player TEXT PRIMARY KEY,cash NUMERIC)')
db.execute('CREATE TABLE factory_totals (player TEXT PRIMARY KEY,manufactured NUMERIC,purchases NUMERIC)')
db.execute('CREATE TABLE sales (player_id TEXT,sold_quantity NUMERIC,unit_price NUMERIC,unit_cost NUMERIC,product_id TEXT)')
db.execute('CREATE TABLE actions (player TEXT,payload TEXT,result TEXT)')
db.execute("INSERT INTO players VALUES('p','2101','User A',1)")
db.execute("INSERT INTO players VALUES('q','2102','User B',1)")
db.execute("INSERT INTO factories VALUES('p',100)")
db.execute("INSERT INTO factories VALUES('q',1000)")
db.execute("INSERT INTO factory_totals VALUES('p',10,20)")
db.execute("INSERT INTO factory_totals VALUES('q',10,20)")
db.execute("INSERT INTO sales VALUES('p',10,10,2,'white')")
db.execute("INSERT INTO sales VALUES('q',10,10,2,'white')")
db.commit()
account=object.__new__(Accounts)
account.db=db
account.postgres=False
account.identity=lambda token,now:{'id':'p'}
admin=Admin(SimpleNamespace(db=db,postgres=False))
admin.fund_history()
base=account.rankings_many(('net_profit','revenue','manufactured'))
ranking=lambda data,name:next(r for r in data['net_profit']['individual'] if r['display_name']==name)['net_profit']
assert ranking(base,'User A')==60
assert ranking(base,'User B')==60

grant=admin.fund_transfer('2101','grant','3e+200','grant','aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',1794480000000)
assert grant['after_cash']==100+3*10**200
assert ranking(account.rankings_many(('net_profit',)),'User A')==60
collect=admin.fund_transfer('2101','collect','4e+200','collect','bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb',1794480000001)
assert collect['after_cash']==100-10**200 < 0
assert db.execute("SELECT cash FROM factories WHERE player='p'").fetchone()[0] == 100-10**200
assert ranking(account.rankings_many(('net_profit',)),'User A')==60-4*10**200
assert ranking(account.rankings_many(('net_profit',)),'User B')==60
repeat=admin.fund_transfer('2101','collect','4e+200','collect','bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb',1794480000001)
assert repeat['already_applied']
assert ranking(account.rankings_many(('net_profit',)),'User A')==60-4*10**200

g=object.__new__(Game)
g.db=db
g.accounts=account
g.clock=lambda:1794480000002
d=g.breakdown('token')
expenses={v['key']:v['amount'] for v in d['expense']}
assert expenses['admin_collect']==4*10**200
assert expenses['materials']==20
assert all(v['key']!='admin_collect' for v in d['income'])
assert sum(v['amount'] for v in d['expense'])==20+4*10**200

# Existing ledger collection must count retroactively, without a second debit.
db.execute("""INSERT INTO admin_fund_transfers
 (key,player_id,student_id,name,kind,amount,before_cash,after_cash,note,created_at)
 VALUES('cccccccc-cccc-4ccc-cccc-cccccccccccc','p','2101','User A','collect',30,30,0,'legacy',1794480000003)""")
db.commit()
assert ranking(account.rankings_many(('net_profit',)),'User A')==30-4*10**200
assert {v['key']:v['amount'] for v in g.breakdown('token')['expense']}['admin_collect']==4*10**200+30
assert db.execute("SELECT cash FROM factories WHERE player='p'").fetchone()[0]==100-10**200
print("PASS: negative cash, exact giant collection, audit replay, grant excluded, collection expense + net profit including past history")
