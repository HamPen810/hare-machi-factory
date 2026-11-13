"""PostgreSQL-only, disposable CI laboratory for V2 shadow balances.

NEVER use against live Supabase or any existing schema. Requires an explicitly
named ephemeral database starting with 'hare_v2_ci_' and creates its own schema.
This code exists only to test PostgreSQL locking/rollback and is NOT deployed
as game transaction code.

Intentionally synthetic players. No real player identifiers, credentials,
balances, or production data are accessed.
"""
import hashlib
import json
import os
from urllib.parse import urlparse
import psycopg
from sparse_exact_v1 import SparseExact as S
from sparse_exact_division import mul_ratio_floor

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
 id TEXT PRIMARY KEY, cash_legacy TEXT NOT NULL, cash_v2 TEXT
);
CREATE TABLE IF NOT EXISTS inventories (
 player TEXT NOT NULL REFERENCES players(id), product TEXT NOT NULL,
 quantity_legacy TEXT NOT NULL, quantity_v2 TEXT,
 PRIMARY KEY(player,product)
);
CREATE TABLE IF NOT EXISTS settlement_treasury (
 id INTEGER PRIMARY KEY CHECK(id=1), tax_v2 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trade_receipts (
 op_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
 buyer TEXT NOT NULL, seller TEXT NOT NULL, product TEXT NOT NULL,
 qty_v2 TEXT NOT NULL, unit_price_v2 TEXT NOT NULL,
 gross_v2 TEXT NOT NULL, tax_v2 TEXT NOT NULL
);
INSERT INTO settlement_treasury VALUES (1,'S1:')
 ON CONFLICT (id) DO NOTHING;
"""


def assert_disposable_connection(dsn):
    """Fail closed: running on an existing or remote database is prohibited."""
    if not dsn or os.environ.get('HARE_V2_EPHEMERAL_CI')!='yes':
        raise RuntimeError('Disposable CI-only environment flag is required')
    parsed=urlparse(dsn)
    if (parsed.scheme not in ('postgres','postgresql')
        or parsed.hostname not in ('localhost','127.0.0.1')
        or not (parsed.path or '').lstrip('/').startswith('hare_v2_ci_')):
        raise RuntimeError('Refusing connection to non-local / non-CI database')
    return True


def connect(dsn):
    assert_disposable_connection(dsn)
    return psycopg.connect(dsn,autocommit=True,connect_timeout=5)


def initialize(dsn):
    with connect(dsn) as conn:
        for query in SCHEMA.strip().split(';'):
            if query.strip():
                conn.execute(query)


def shadow_backfill(conn):
    """Idempotent, locked staging backfill, rejects mismatch without overwriting."""
    with conn.transaction():
        for identity,legacy,v2 in conn.execute(
            'SELECT id,cash_legacy,cash_v2 FROM players ORDER BY id FOR UPDATE'
        ).fetchall():
            value=S.parse(legacy)
            if v2 is None:
                conn.execute('UPDATE players SET cash_v2=%s WHERE id=%s',
                             (value.serialize(),identity))
            elif S.deserialize(v2).compare(value)!=0:
                raise ValueError('Shadow cash mismatch')
        for identity,product,legacy,v2 in conn.execute(
            'SELECT player,product,quantity_legacy,quantity_v2 FROM inventories ORDER BY player,product FOR UPDATE'
        ).fetchall():
            value=S.parse(legacy)
            if value.sign()<0:
                raise ValueError('Negative legacy inventory')
            if v2 is None:
                conn.execute('UPDATE inventories SET quantity_v2=%s WHERE player=%s AND product=%s',
                             (value.serialize(),identity,product))
            elif S.deserialize(v2).compare(value)!=0:
                raise ValueError('Shadow inventory mismatch')


def _required(raw):
    if raw is None:
        raise ValueError('Missing shadow value')
    return S.deserialize(raw)


def exact_buy(conn,op_id,buyer,seller,product,quantity_input,price_input,
              fee_bps=500,failpoint=None):
    """Transactional reference only. All row locks are acquired in stable order.

    Operation-specific advisory lock closes the race where duplicate op IDs
    concurrently find no existing receipt. Buyer/seller and inventory rows are
    locked in deterministic order, treasury locked last.

    The server-validated original payload and fee are fingerprinted to make
    duplicate retries safe; different payloads with same op ID are rejected.
    """
    if (not isinstance(op_id,str) or not 8<=len(op_id)<=80
        or not op_id.isascii()):
        raise ValueError('Invalid operation key')
    if not isinstance(buyer,str) or not isinstance(seller,str) or buyer==seller:
        raise ValueError('Invalid participants')
    if not isinstance(product,str) or not product:
        raise ValueError('Invalid product')
    if type(fee_bps) is not int or not 0<=fee_bps<=10000:
        raise ValueError('Invalid fee')
    quantity,price=S.parse(quantity_input),S.parse(price_input)
    if quantity.sign()<=0 or price.sign()<=0:
        raise ValueError('Quantity/price must be positive')
    fingerprint=hashlib.sha256(json.dumps(
        [buyer,seller,product,quantity_input,price_input,fee_bps],
        ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(op_id,))
        previous=conn.execute(
            'SELECT fingerprint,gross_v2,tax_v2 FROM trade_receipts WHERE op_id=%s',
            (op_id,)).fetchone()
        if previous is not None:
            if previous[0]!=fingerprint:
                raise ValueError('Operation ID reused with different payload')
            return {'gross':S.deserialize(previous[1]),
                    'fee':S.deserialize(previous[2]),'already_applied':True}

        rows=conn.execute(
            'SELECT id,cash_v2 FROM players WHERE id=ANY(%s) ORDER BY id FOR UPDATE',
            ([buyer,seller],)).fetchall()
        if len(rows)!=2:
            raise ValueError('Missing buyer or seller')
        cash={identity:_required(raw) for identity,raw in rows}
        rows=conn.execute(
            'SELECT player,quantity_v2 FROM inventories '
            'WHERE player=ANY(%s) AND product=%s ORDER BY player,product FOR UPDATE',
            ([buyer,seller],product)).fetchall()
        if len(rows)!=2:
            raise ValueError('Missing product inventory')
        stock={identity:_required(raw) for identity,raw in rows}
        remaining=stock[seller]-quantity
        if remaining.sign()<0:
            raise ValueError('Insufficient stock')
        gross=quantity*price
        fee=mul_ratio_floor(gross,fee_bps)
        tax_row=conn.execute(
            'SELECT tax_v2 FROM settlement_treasury WHERE id=1 FOR UPDATE'
        ).fetchone()
        tax=_required(tax_row[0] if tax_row else None)
        updates=[
            ('UPDATE players SET cash_v2=%s WHERE id=%s',
             ( (cash[buyer]-gross).serialize(),buyer)),
            ('UPDATE players SET cash_v2=%s WHERE id=%s',
             ( (cash[seller]+gross-fee).serialize(),seller)),
            ('UPDATE inventories SET quantity_v2=%s WHERE player=%s AND product=%s',
             (remaining.serialize(),seller,product)),
            ('UPDATE inventories SET quantity_v2=%s WHERE player=%s AND product=%s',
             ((stock[buyer]+quantity).serialize(),buyer,product)),
            ('UPDATE settlement_treasury SET tax_v2=%s WHERE id=1',
             ((tax+fee).serialize(),)),
        ]
        for index,(sql,params) in enumerate(updates):
            if conn.execute(sql,params).rowcount!=1:
                raise ValueError('Missing ledger row during settlement')
            if failpoint=='after_seller_stock' and index==2:
                raise RuntimeError('Injected failure')
        conn.execute(
            'INSERT INTO trade_receipts VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (op_id,fingerprint,buyer,seller,product,quantity.serialize(),
             price.serialize(),gross.serialize(),fee.serialize()))
        return {'gross':gross,'fee':fee,'already_applied':False}


def total_money(conn):
    tax=_required(conn.execute('SELECT tax_v2 FROM settlement_treasury WHERE id=1').fetchone()[0])
    for (raw,) in conn.execute('SELECT cash_v2 FROM players'):
        tax=tax+_required(raw)
    return tax


def total_stock(conn,product):
    total=S.parse('0')
    for (raw,) in conn.execute('SELECT quantity_v2 FROM inventories WHERE product=%s',(product,)):
        total=total+_required(raw)
    return total
