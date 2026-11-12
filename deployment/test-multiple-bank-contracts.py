"""Bank multi-contract regression tests: SQLite exact numbers and legacy balances."""
import sqlite3, json
from pathlib import Path
import bank, exact

HOUR=bank.HOUR_MS
NOW=1_800_000_000_000
CLOSE=NOW+10*HOUR

def make():
    db=sqlite3.connect(':memory:')
    exact.setup(db)
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('CREATE TABLE players (id TEXT PRIMARY KEY)')
    db.execute('CREATE TABLE factories (player TEXT PRIMARY KEY, cash NUMERIC)')
    db.execute("INSERT INTO players VALUES('user')")
    db.execute("INSERT INTO factories VALUES('user',?)",(10**380,))
    bank.initialize(db)
    db.execute('INSERT INTO bank_settings VALUES(1,?)',
        (json.dumps({**bank.DEFAULT,'enabled':True,'limit':str(10**370)}),))
    return db

def cash(db):
    return db.execute("SELECT cash FROM factories WHERE player='user'").fetchone()[0]

db=make()
initial=cash(db)
with db:
    d1=bank.player_action(db,'user','bank_lend','1e+340',NOW,CLOSE)
    d2=bank.player_action(db,'user','bank_lend','3e+350',NOW+1000,CLOSE)
    b1=bank.player_action(db,'user','bank_borrow','2e+330',NOW,CLOSE)
    b2=bank.player_action(db,'user','bank_borrow','5e+335',NOW,CLOSE)

state=bank.player_state(db,'user',NOW+1000)
assert len(state['contracts'])==4
assert len([x for x in state['contracts'] if x['kind']=='lend'])==2
assert len([x for x in state['contracts'] if x['kind']=='borrow'])==2
assert state['deposit']==sum(x['amount'] for x in state['contracts'] if x['kind']=='lend')
assert state['debt']==sum(x['amount'] for x in state['contracts'] if x['kind']=='borrow')
assert cash(db)==initial-10**340-3*10**350+2*10**330+5*10**335
assert all(type(x['amount']) is int for x in state['contracts'])

# Individual maturity/withdraw: cannot collect immature deposit.
lend=next(x for x in state['contracts'] if x['id']==d1['contract_ids'][0])
try:
    with db: bank.player_action(db,'user','bank_withdraw',lend['id'],NOW+HOUR-1,CLOSE)
    raise AssertionError('immature deposit was released')
except ValueError: pass

with db: bank.player_action(db,'user','bank_withdraw',lend['id'],NOW+HOUR,CLOSE)
state=bank.player_state(db,'user',NOW+HOUR)
assert len(state['contracts'])==3
assert state['deposit']==next(x['amount'] for x in state['contracts'] if x['kind']=='lend')

# Can settle a single loan without affecting other contracts.
with db: bank.player_action(db,'user','bank_repay',b1['contract_ids'][0],NOW+HOUR,CLOSE)
state=bank.player_state(db,'user',NOW+HOUR)
assert len(state['contracts'])==2 and state['debt']>0

# Repay all remaining loans, withdraw all matured deposits.
with db: bank.player_action(db,'user','bank_repay',None,NOW+HOUR,CLOSE)
assert bank.player_state(db,'user',NOW+HOUR)['debt']==0
with db: bank.player_action(db,'user','bank_withdraw',None,NOW+HOUR+1000,CLOSE)
assert bank.player_state(db,'user',NOW+HOUR+1000)['deposit']==0
assert bank.player_state(db,'user',NOW+HOUR+1000)['contracts']==[]

# Old single-contract balances migrate on the first transactional action.
legacy=make()
legacy.execute("INSERT INTO bank_accounts(player,deposit,matures,debt,tax) VALUES('user',?,?,?,?)",
               (10**330,NOW+HOUR,10**335,900))
view=bank.player_state(legacy,'user',NOW)
assert len(view['contracts'])==2 and view['tax']==900
with legacy:
    bank.player_action(legacy,'user','bank_borrow','100',NOW,CLOSE)
view=bank.player_state(legacy,'user',NOW)
assert len(view['contracts'])==3
assert view['deposit']==10**330
assert view['debt']>10**335 and view['tax']==900
with legacy:
    bank.player_action(legacy,'user','bank_withdraw','legacy-lend-user',NOW+HOUR,CLOSE)
assert bank.player_state(legacy,'user',NOW+HOUR)['deposit']==0

# Cash balance check must still reject overdraw and preserve contracts.
legacy.execute("UPDATE factories SET cash=0 WHERE player='user'")
before=bank.player_state(legacy,'user',NOW+HOUR)
try:
    with legacy: bank.player_action(legacy,'user','bank_lend','100',NOW+HOUR,CLOSE)
    raise AssertionError('deposit without enough cash succeeded')
except ValueError: pass
assert bank.player_state(legacy,'user',NOW+HOUR)['contracts']==before['contracts']

# Tax collection remains separate from contracts.
assert bank.player_state(legacy,'user',NOW+HOUR)['tax']==900
print('PASS: 4 parallel bank contracts, 1e350 balances, independent maturity, individual and bulk settlements, legacy migration and cash checks')
