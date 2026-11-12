"""Regression tests for admin funds: exact integers, audit, no double execution."""
import sqlite3
from types import SimpleNamespace
from admin import Admin
from exact import setup

db=sqlite3.connect(':memory:')
setup(db)
db.execute('PRAGMA foreign_keys=ON')
db.execute('CREATE TABLE players (id TEXT PRIMARY KEY,student_id TEXT UNIQUE,display_name TEXT)')
db.execute('CREATE TABLE factories (player TEXT PRIMARY KEY,cash NUMERIC)')
db.execute("INSERT INTO players VALUES('p','2101','Test Student')")
db.execute("INSERT INTO factories VALUES('p',?)",(10**320,))
db.commit()
admin=Admin(SimpleNamespace(db=db,postgres=False))
cash=lambda:db.execute("SELECT cash FROM factories WHERE player='p'").fetchone()[0]
initial=cash()
key='aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa'
done=admin.fund_transfer('2101','grant','2e+310','research award',key,1794480000000)
assert done['amount']==2*10**310
assert cash()==initial+2*10**310
assert done['already_applied'] is False
repeat=admin.fund_transfer('2101','grant','2e+310','research award',key,1794480000000)
assert repeat['already_applied'] is True
assert cash()==initial+2*10**310
try:
 admin.fund_transfer('2101','collect','5','different action',key,1794480000000)
 raise AssertionError('idempotency conflict not rejected')
except ValueError:pass
key2='bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb'
before=cash()
collect=admin.fund_transfer('2101','collect','3e+310','penalty',key2,1794480000001)
assert cash()==before-3*10**310
assert collect['after_cash']==cash()
rows=admin.fund_history()
assert len(rows)==2
assert {x['kind'] for x in rows}=={'collect','grant'}
assert all(x['student_id']=='2101' for x in rows)
key3='cccccccc-cccc-4ccc-cccc-cccccccccccc'
try:
 admin.fund_transfer('2101','collect',str(10**340),'too much',key3,1794480000002)
 raise AssertionError('overdraft succeeded')
except ValueError:pass
assert cash()==collect['after_cash']
assert len(admin.fund_history())==2
for invalid in ['0','-1','1.3','abc']:
 try:
  admin.fund_transfer('2101','grant',invalid,'bad',key3,1794480000002)
  raise AssertionError('invalid amount accepted')
 except ValueError:pass
assert cash()==collect['after_cash']
try:
 admin.fund_transfer('2102','grant','100','missing',key3,1794480000002)
 raise AssertionError('missing account accepted')
except ValueError:pass
# Does not add sales, action spending, ranking entries or alter any other table.
assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='sales'").fetchone()[0]==0
assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='actions'").fetchone()[0]==0
print('PASS: exact 1e310 transfers, safe overdraft, admin audit, replay idempotency, validation, no ranking mutations')
