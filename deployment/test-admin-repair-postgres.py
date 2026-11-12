"""PostgreSQL regression for admin extra registration IDs and debt cancellation."""
import os,sys
# Always import the extracted *production ZIP* code, not the checked-in
# deployment/ source templates. The two versions can differ after patches.
sys.path.insert(0,os.environ.get('PG_PRODUCTION_DIR','/tmp/admin-repair-pg'))
from psycopg_pool import ConnectionPool
from psycopg.rows import tuple_row
from postgres import row_factory
from accounts import Accounts
from admin import Admin
from admin_fund_ops import perform,history
from bank import initialize as initialize_bank

import postgres
dsn=os.getenv('PG_TEST_DSN','postgresql://tester:tester@127.0.0.1:5432/testdb')
def configure(conn):
    conn.execute('SET search_path TO hare_factory, pg_catalog')
pool=ConnectionPool(dsn,min_size=0,max_size=4,open=True,
                    configure=configure,kwargs={'autocommit':True,'row_factory':row_factory})
postgres._shared_connection_pool=lambda url:pool
try:
    with pool.connection() as conn:
        conn.execute('CREATE SCHEMA IF NOT EXISTS hare_factory')
        conn.execute('SET search_path TO hare_factory, pg_catalog')
        conn.execute('''CREATE TABLE players(id text PRIMARY KEY,student_id text NOT NULL UNIQUE,
                        display_name text NOT NULL,class_number integer NOT NULL,
                        salt bytea NOT NULL,password_hash bytea NOT NULL,created_at BIGINT NOT NULL)''')
        conn.execute('''CREATE TABLE factories(player text PRIMARY KEY REFERENCES players(id),
                        cash NUMERIC NOT NULL)''')
        conn.execute('CREATE TABLE frozen_players(player_id text PRIMARY KEY REFERENCES players(id))')
        conn.execute('CREATE TABLE auth_attempts(student_id text PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, blocked_until BIGINT NOT NULL DEFAULT 0)')
        conn.execute('CREATE TABLE sessions(token_hash text PRIMARY KEY,player_id text REFERENCES players(id),expires_at BIGINT)')
        conn.execute('CREATE TABLE stock(player text,product text,quantity NUMERIC)')
        conn.execute('CREATE TABLE listings(player text,product text,quantity NUMERIC)')
    acct=Accounts(dsn,read_only=True,admin_only=True)
    try:
        initialize_bank(acct.db)
        admin=Admin(acct)
        admin.initialize(False)
        print('BOOTSTRAP PASSED')
        result=admin.manage_extra_slot('2999',3,'add',1794480000000)
        assert result['class_number']==3
        print('EXTRA_SLOT_ADD PASSED',result)
        assert admin.extra_slots()[0]['student_id']=='2999'
        print('EXTRA_SLOT_LIST PASSED')
    finally:
        acct.db.close()
    account=Accounts(dsn)
    try:
        account.register('Sample','2999','123456',now=1794480000)
        assert account.login('2999','123456',now=1794480001)
        print('REGISTER_LOGIN PASSED')
        p=account.db.execute("SELECT id FROM players WHERE student_id='2999'").fetchone()[0]
        account.db.execute('INSERT INTO factories(player,cash) VALUES(?,?)',(p,100))
        account.db.execute('INSERT INTO bank_accounts(player,debt) VALUES(?,?)',(p,300))
        account.db.execute('INSERT INTO bank_contracts VALUES(?,?,?,?,?,?,?)',('loan',p,'borrow',270,300,0,0))
        account.db.commit()
    finally:
        account.db.close()
    acct=Accounts(dsn,read_only=True,admin_only=True)
    try:
        admin=Admin(acct)
        payload={'scope':'single','kind':'forgive','student_id':'2999','note':'check'}
        import admin_fund_ops
        print('DEBUG_STUDENT',repr(payload.get('student_id')), type(payload.get('student_id')), len(payload['student_id']),payload['student_id'].isascii(),payload['student_id'].isdigit(),flush=True)
        print('DEBUG_VALIDATE_SOURCE',admin_fund_ops.__file__,flush=True)
        print('DEBUG_VALIDATE',admin_fund_ops.validate(payload),flush=True)
        preview=perform(admin,{**payload,'action':'preview'},1794480000000)
        assert preview['total']==300,preview
        print('DEBT_PREVIEW PASSED')
        result=perform(admin,{**payload,'action':'apply','key':'abcd1234abcd1234abcd1234',
                'preview_digest':preview['digest']},1794480000000)
        assert result['total']==300,result
        assert acct.db.execute('SELECT debt FROM bank_accounts WHERE player=?',(p,)).fetchone()[0]==0
        assert history(acct.db)[0]['student_id']=='2999'
        print('DEBT_APPLY PASSED')
        # Simulate an old preview followed by a changed negative balance.
        acct.db.execute('UPDATE factories SET cash=-500 WHERE player=?',(p,))
        acct.db.commit()
        new_preview=perform(admin,{**payload,'action':'preview'},1794480000001)
        acct.db.execute('UPDATE factories SET cash=-999 WHERE player=?',(p,))
        acct.db.commit()
        changed=perform(admin,{**payload,'action':'apply',
            'key':'abcd1234abcd1234abcd1235',
            'preview_digest':new_preview['digest']},1794480000002)
        assert changed['cash_restored_total']==999,changed
        assert acct.db.execute('SELECT cash FROM factories WHERE player=?',
                               (p,)).fetchone()[0]==0
        print('CHANGED_BALANCE_CLEARED PASSED')
        # A transaction locking another player's factory must not hold up
        # forgiveness for this player. Former full-player FOR UPDATE did.
        acct.db.execute("INSERT INTO players(id,student_id,display_name,class_number,salt,password_hash,created_at) "
                        "VALUES('unrelated','2101','Other',1,?,?,0)",(b'0123456789abcdef',b'passwordhash'))
        acct.db.execute("INSERT INTO factories(player,cash) VALUES('unrelated',99)")
        acct.db.execute('UPDATE factories SET cash=-78 WHERE player=?',(p,))
        acct.db.commit()
        fresh_preview=perform(admin,{**payload,'action':'preview'},1794480000003)
        import time
        with pool.connection() as blocker:
            blocker.execute('BEGIN')
            blocker.execute("SELECT player FROM factories WHERE player='unrelated' FOR UPDATE")
            start=time.monotonic()
            final=perform(admin,{**payload,'action':'apply',
                'key':'abcd1234abcd1234abcd1236',
                'preview_digest':fresh_preview['digest']},1794480000004)
            duration=time.monotonic()-start
            assert duration<4.0,('unrelated player lock blocked forgiveness',duration)
            assert final['cash_restored_total']==78,final
            blocker.rollback()
        print('UNRELATED_PLAYER_LOCK_NO_LONGER_BLOCKS PASSED')
    finally:
        acct.db.close()
finally:
    pool.close()
print('PASS: production PostgreSQL wrapper supports registration ID and debt operations')
