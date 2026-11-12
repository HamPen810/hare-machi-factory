"""Regression tests for concurrent loan and deposit contract states."""
import importlib.util
import sqlite3
import sys
import zipfile
from pathlib import Path

with zipfile.ZipFile('hare-machi-render.zip') as z:
    for name in ('bank.py', 'exact.py'):
        Path(name).write_bytes(z.read(name))
sys.path.insert(0,'.')
import bank
import exact

def make():
    db=sqlite3.connect(':memory:')
    exact.setup(db)
    db.execute('CREATE TABLE players(id TEXT PRIMARY KEY)')
    db.execute('CREATE TABLE factories(player TEXT PRIMARY KEY, cash BLOB)')
    db.execute("INSERT INTO players VALUES('tester')")
    db.execute("INSERT INTO factories VALUES('tester',?)",(10**310,))
    bank.initialize(db)
    db.execute("INSERT INTO bank_settings(id,config) VALUES(1,?)",(__import__('json').dumps(
        dict(bank.DEFAULT,enabled=True,limit=str(10**309))),))
    return db

now=1000000000
close=now+10*bank.HOUR_MS
db=make()
loan=bank.player_action(db,'tester','bank_borrow',str(10**309),now,close)
assert loan['cash_change']==10**309
deposit=bank.player_action(db,'tester','bank_lend',str(10**309),now,close)
assert deposit['cash_change']==-(10**309)
s=bank.player_state(db,'tester',now)
assert s['deposit']>0 and s['debt']>0
for kind in ('bank_borrow','bank_lend'):
    try:
        bank.player_action(db,'tester',kind,str(1),now,close)
        raise AssertionError(f'duplicate active contract accepted: {kind}')
    except ValueError:
        pass
bank.player_action(db,'tester','bank_withdraw',None,now+bank.HOUR_MS,close)
assert bank.player_state(db,'tester',now)['debt']>0
bank.player_action(db,'tester','bank_repay',None,now+bank.HOUR_MS,close)
assert bank.player_state(db,'tester',now)['debt']==0
db=make()
bank.player_action(db,'tester','bank_lend','100',now,close)
bank.player_action(db,'tester','bank_borrow','200',now,close)
assert bank.player_state(db,'tester',now)['debt']>0
print('PASS: borrow/deposit in both orders, independent maturity/repayment, huge integers and duplicate prevention')
