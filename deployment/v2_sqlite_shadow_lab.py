"""Isolated SQLite shadow-column and transactional market prototype.

FOR TESTS ONLY. Not imported by the live server. No Supabase/Render access.

This tests orchestration and migration concepts independently of PostgreSQL:
- legacy exact decimal TEXT -> v2 sparse TEXT shadow backfill
- transaction-atomic buyer/seller/treasury/inventory transfers
- immutable idempotency operation keys
- optimistic two-way reconciliation against recorded journal for transfers
- failpoints that must roll back every row changed.

It does NOT establish PostgreSQL locking, query performance, recovery,
security, market demand allocation or production integration.
"""
import hashlib
import json
import sqlite3
import time
from sparse_exact_v1 import SparseExact as S
from sparse_exact_division import mul_ratio_floor

ZERO=S.parse('0')
SCHEMA="""
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    cash_legacy TEXT NOT NULL,
    cash_v2 TEXT
);
CREATE TABLE IF NOT EXISTS inventories (
    player TEXT NOT NULL REFERENCES players(id),
    product TEXT NOT NULL,
    quantity_legacy TEXT NOT NULL,
    quantity_v2 TEXT,
    PRIMARY KEY(player,product)
);
CREATE TABLE IF NOT EXISTS settlement_treasury (
    id INTEGER PRIMARY KEY CHECK(id=1), tax_v2 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trade_receipts (
    op_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    buyer TEXT NOT NULL,
    seller TEXT NOT NULL,
    product TEXT NOT NULL,
    qty_v2 TEXT NOT NULL,
    unit_price_v2 TEXT NOT NULL,
    gross_v2 TEXT NOT NULL,
    tax_v2 TEXT NOT NULL
);
INSERT OR IGNORE INTO settlement_treasury (id,tax_v2) VALUES(1,'S1:');
"""


def connect(path):
    db=sqlite3.connect(path, timeout=10, isolation_level=None,
                       check_same_thread=False)
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    db.executescript(SCHEMA)
    return db


def _value(row):
    if row is None:
        raise ValueError('Account or inventory missing')
    return S.deserialize(row[0])


def backfill_legacy_shadow(db):
    """Atomic idempotent backfill, never replaces legacy columns.

    This routine is permitted ONLY on standalone restored/staging fixtures.
    A production online backfill requires write coordination/CDC beyond this
    toy routine.
    """
    db.execute('BEGIN IMMEDIATE')
    try:
        for player, old, new in db.execute(
            'SELECT id,cash_legacy,cash_v2 FROM players'
        ).fetchall():
            parsed=S.parse(old)
            if new is None:
                db.execute('UPDATE players SET cash_v2=? WHERE id=?',
                           (parsed.serialize(),player))
            elif S.deserialize(new).compare(parsed)!=0:
                raise ValueError('Existing shadow cash differs from legacy')
        for player, product, old, new in db.execute(
            'SELECT player,product,quantity_legacy,quantity_v2 FROM inventories'
        ).fetchall():
            parsed=S.parse(old)
            if parsed.sign()<0:
                raise ValueError('Legacy stock cannot be negative')
            if new is None:
                db.execute(
                    'UPDATE inventories SET quantity_v2=? WHERE player=? AND product=?',
                    (parsed.serialize(),player,product))
            elif S.deserialize(new).compare(parsed)!=0:
                raise ValueError('Existing shadow stock differs from legacy')
        db.execute('COMMIT')
    except BaseException:
        db.execute('ROLLBACK')
        raise


def _update_v2(db,table,column,where,params,value):
    sql=f'UPDATE {table} SET {column}=? WHERE {where}'
    updated=db.execute(sql,(value.serialize(),*params))
    if updated.rowcount!=1:
        raise ValueError('Missing row during settlement')


def exact_buy(db,op_id,buyer,seller,product,quantity_text,price_text,
              fee_bps=500,failpoint=None):
    """Single SQL transaction, unlike the former in-memory RLock simulation.

    The caller provides a stable ASCII request ID. The validated original
    strings are hashed, so its retransmission can never be applied twice.
    Numerically equivalent but differently written values with the same
    ID are rejected. This avoids ambiguous sparse serialization identity.
    """
    if not isinstance(op_id,str) or not 8<=len(op_id)<=80 or not op_id.isascii():
        raise ValueError('Invalid operation ID')
    if not isinstance(buyer,str) or not isinstance(seller,str) or buyer==seller:
        raise ValueError('Invalid participants')
    if not isinstance(product,str) or not product:
        raise ValueError('Invalid product')
    if type(fee_bps) is not int or not 0<=fee_bps<=10000:
        raise ValueError('Invalid tax rate')
    quantity=S.parse(quantity_text)
    price=S.parse(price_text)
    if quantity.sign()<=0 or price.sign()<=0:
        raise ValueError('Quantity and unit price must be positive')
    fingerprint=hashlib.sha256(json.dumps(
        [buyer,seller,product,quantity_text,price_text,fee_bps],
        ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

    db.execute('BEGIN IMMEDIATE')
    try:
        receipt=db.execute(
            'SELECT fingerprint,gross_v2,tax_v2 FROM trade_receipts WHERE op_id=?',
            (op_id,)).fetchone()
        if receipt is not None:
            if receipt[0]!=fingerprint:
                raise ValueError('Operation ID used for different payload')
            db.execute('COMMIT')
            return {'gross':S.deserialize(receipt[1]),
                    'tax':S.deserialize(receipt[2]),'already_applied':True}
        buyer_cash=_value(db.execute('SELECT cash_v2 FROM players WHERE id=?',
                                     (buyer,)).fetchone())
        seller_cash=_value(db.execute('SELECT cash_v2 FROM players WHERE id=?',
                                      (seller,)).fetchone())
        buyer_stock=_value(db.execute(
            'SELECT quantity_v2 FROM inventories WHERE player=? AND product=?',
            (buyer,product)).fetchone())
        seller_stock=_value(db.execute(
            'SELECT quantity_v2 FROM inventories WHERE player=? AND product=?',
            (seller,product)).fetchone())
        remaining=seller_stock-quantity
        if remaining.sign()<0:
            raise ValueError('Insufficient stock')
        total=quantity*price
        fee=mul_ratio_floor(total,fee_bps)
        treasury=_value(db.execute(
            'SELECT tax_v2 FROM settlement_treasury WHERE id=1').fetchone())
        # Compute first, then atomically write; overdraft purchase is allowed.
        _update_v2(db,'players','cash_v2','id=?',(buyer,),buyer_cash-total)
        _update_v2(db,'players','cash_v2','id=?',(seller,),seller_cash+total-fee)
        _update_v2(db,'inventories','quantity_v2',
                   'player=? AND product=?',(seller,product),remaining)
        if failpoint=='after_seller_stock':
            raise RuntimeError('Injected transaction failure')
        _update_v2(db,'inventories','quantity_v2',
                   'player=? AND product=?',(buyer,product),buyer_stock+quantity)
        _update_v2(db,'settlement_treasury','tax_v2','id=?',(1,),treasury+fee)
        db.execute("""INSERT INTO trade_receipts
            (op_id,fingerprint,buyer,seller,product,qty_v2,unit_price_v2,
             gross_v2,tax_v2) VALUES(?,?,?,?,?,?,?,?,?)""",
            (op_id,fingerprint,buyer,seller,product,
             quantity.serialize(),price.serialize(),total.serialize(),fee.serialize()))
        db.execute('COMMIT')
        return {'gross':total,'tax':fee,'already_applied':False}
    except BaseException:
        db.execute('ROLLBACK')
        raise


def total_cash_including_treasury(db):
    value=_value(db.execute('SELECT tax_v2 FROM settlement_treasury WHERE id=1').fetchone())
    for (raw,) in db.execute('SELECT cash_v2 FROM players'):
        value=value+S.deserialize(raw)
    return value


def total_stock(db,product):
    value=ZERO
    for (raw,) in db.execute(
        'SELECT quantity_v2 FROM inventories WHERE product=?',(product,)):
        value=value+S.deserialize(raw)
    return value
