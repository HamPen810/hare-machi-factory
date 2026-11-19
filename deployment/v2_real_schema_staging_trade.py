"""V2 trade settlement against real-shape hare_factory tables; LOCAL STAGING ONLY.

Uses the game's actual economic row keys (factories.player, stock.player/product)
and V2 shadow columns, without changing legacy NUMERIC fields.

This intentionally does not implement the game's order allocator, real market
tax brackets, or production cutover. Its fee is a basis-point TEST fixture.
"""
import hashlib
import json
import os
from sparse_exact_v1 import SparseExact as S
from sparse_exact_division import mul_ratio_floor
from v2_global_operation_registry import initialize as init_registry, check as check_registry, register as register_op
from v2_stage_event_ledger import initialize as init_ledger, emit as emit_event

RECEIPTS = "hare_factory.v2_trade_receipts_stage"
ZERO = S.parse("0")


def _guard(conn):
    host=(conn.info.host or "").split(",")[0]
    db=conn.info.dbname or ""
    if os.environ.get("HARE_V2_LOCAL_STAGING") != "yes":
        raise RuntimeError("Local V2 staging opt-in required")
    if host not in ("127.0.0.1", "localhost") or not db.startswith("hare_v2_stage_"):
        raise RuntimeError("Refusing live or remote database")
    if not conn.autocommit:
        raise RuntimeError("V2 staging trade requires autocommit transactions")


def _decode(value):
    if not isinstance(value, str):
        raise ValueError("V2 shadow missing")
    return S.deserialize(value)


def create_staging_receipts(conn):
    _guard(conn)
    with conn.transaction():
        init_registry(conn)
        init_ledger(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hare_factory.v2_trade_receipts_stage (
                op_id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                buyer TEXT NOT NULL,
                seller TEXT NOT NULL,
                product TEXT NOT NULL,
                quantity_v2 TEXT NOT NULL,
                price_v2 TEXT NOT NULL,
                gross_v2 TEXT NOT NULL,
                fee_v2 TEXT NOT NULL
            )
        """)


def settle(conn, op_id, buyer, seller, product, quantity_text, unit_price_text,
           fee_bps=500, failpoint=None):
    _guard(conn)
    for name, value in (("op_id",op_id),("buyer",buyer),("seller",seller),("product",product)):
        if not isinstance(value,str) or not value.isascii() or not (1<=len(value)<=80):
            raise ValueError("Invalid "+name)
    if len(op_id)<8 or buyer==seller:
        raise ValueError("Invalid operation or participants")
    if not isinstance(quantity_text,str) or not isinstance(unit_price_text,str):
        raise ValueError("Quantities and prices must be decimal strings")
    if type(fee_bps) is not int or not 0<=fee_bps<=10000:
        raise ValueError("Invalid test fee")
    quantity=S.parse(quantity_text)
    price=S.parse(unit_price_text)
    if quantity.sign()<=0 or price.sign()<=0:
        raise ValueError("Positive quantity/price required")

    fingerprint=hashlib.sha256(json.dumps(
        [buyer,seller,product,quantity.serialize(),price.serialize(),fee_bps],
        separators=(",",":"),ensure_ascii=True
    ).encode("ascii")).hexdigest()
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout='6s'")
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",(op_id,))
        registry_replay=check_registry(conn,op_id,"v2_trade",fingerprint)
        old=conn.execute(
            "SELECT fingerprint,gross_v2,fee_v2 FROM "+RECEIPTS+" WHERE op_id=%s",
            (op_id,)).fetchone()
        if old is not None:
            if not registry_replay or old[0]!=fingerprint:
                raise ValueError("Trade receipt does not match global operation registry")
            return {"gross":_decode(old[1]),"fee":_decode(old[2]),"replay":True}
        if registry_replay:
            raise ValueError("Global registry contains trade without receipt")

        accounts=conn.execute(
            "SELECT player,cash_v2 FROM hare_factory.factories "
            "WHERE player=ANY(%s) ORDER BY player FOR UPDATE",
            ([buyer,seller],)).fetchall()
        if len(accounts)!=2:
            raise ValueError("Missing player factory row")
        cash={p:_decode(raw) for p,raw in accounts}
        stocks=conn.execute(
            "SELECT player,quantity_v2 FROM hare_factory.stock "
            "WHERE player=ANY(%s) AND product=%s ORDER BY player,product FOR UPDATE",
            ([buyer,seller],product)).fetchall()
        if len(stocks)!=2:
            raise ValueError("Missing product stock row")
        inventory={p:_decode(raw) for p,raw in stocks}
        available=inventory[seller]-quantity
        if available.sign()<0:
            raise ValueError("Insufficient stock")
        gross=quantity*price
        fee=mul_ratio_floor(gross,fee_bps)
        # Preserve overdraft; fees come from seller, buyer pays only gross.
        next_cash={
            buyer:(cash[buyer]-gross).serialize(),
            seller:(cash[seller]+gross-fee).serialize(),
        }
        next_stock={
            buyer:(inventory[buyer]+quantity).serialize(),
            seller:available.serialize(),
        }
        for player in sorted((buyer,seller)):
            if conn.execute(
                "UPDATE hare_factory.factories SET cash_v2=%s WHERE player=%s",
                (next_cash[player],player)).rowcount!=1:
                raise RuntimeError("Missing cash row")
            if failpoint=="after_first_cash" and player==sorted((buyer,seller))[0]:
                raise RuntimeError("Injected rollback")
        for player in sorted((buyer,seller)):
            if conn.execute(
                "UPDATE hare_factory.stock SET quantity_v2=%s "
                "WHERE player=%s AND product=%s",
                (next_stock[player],player,product)).rowcount!=1:
                raise RuntimeError("Missing stock row")
        emit_event(conn,op_id=op_id,player=buyer,role="buyer",kind="market_buy",
                   product=product,cash=-gross,stock=quantity,expense=gross)
        emit_event(conn,op_id=op_id,player=seller,role="seller",kind="market_sell",
                   product=product,cash=gross-fee,stock=-quantity,revenue=gross)
        register_op(conn,op_id,"v2_trade",fingerprint)
        conn.execute(
            "INSERT INTO "+RECEIPTS+
            "(op_id,fingerprint,buyer,seller,product,quantity_v2,price_v2,gross_v2,fee_v2) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (op_id,fingerprint,buyer,seller,product,quantity.serialize(),
             price.serialize(),gross.serialize(),fee.serialize()))
        if failpoint=="before_commit":
            raise RuntimeError("Injected rollback")
        return {"gross":gross,"fee":fee,"replay":False}


def sum_cash(conn):
    _guard(conn)
    result=ZERO
    for (text,) in conn.execute("SELECT cash_v2 FROM hare_factory.factories"):
        result=result+_decode(text)
    return result


def sum_stock(conn,product):
    _guard(conn)
    result=ZERO
    for (text,) in conn.execute(
        "SELECT quantity_v2 FROM hare_factory.stock WHERE product=%s",(product,)):
        result=result+_decode(text)
    return result
