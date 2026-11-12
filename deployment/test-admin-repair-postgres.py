"""PostgreSQL regression for admin extra registration IDs and debt cancellation."""
import os,sys
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
    finally:
        acct.db.close()
finally:
    pool.close()
print('PASS: production PostgreSQL wrapper supports registration ID and debt operations')
