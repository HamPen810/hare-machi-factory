"""Database-backed V2 economy actions with authentic table keys, STAGING ONLY.

All monetary and inventory balances are S1 TEXT. Every mutation, all checks,
and idempotency receipt are inside one PostgreSQL transaction. The old NUMERIC
columns are never changed. Not approved for production cutover.
"""
import hashlib,json
from sparse_exact_v1 import SparseExact as S
from sparse_exact_division import mul_ratio_floor
from v2_real_schema_staging_trade import _guard
from v2_global_operation_registry import initialize as init_registry, check as check_registry, register as register_op

Z=S.parse("0")

def v(raw):
    if type(raw) is not str:raise ValueError("Exact string required")
    return S.deserialize(raw) if raw.startswith("S1:") else S.parse(raw)

def positive(raw):
    n=v(raw)
    if n.sign()<=0:raise ValueError("Positive quantity required")
    return n

def _locked(conn,player):
    row=conn.execute(
        "SELECT cash_v2,tier FROM hare_factory.factories WHERE player=%s FOR UPDATE",
        (player,)).fetchone()
    if row is None or row[0] is None:raise ValueError("Uninitialized V2 balance")
    return v(row[0]),row[1]

def _stock(conn,player,product):
    row=conn.execute("SELECT quantity_v2 FROM hare_factory.stock "
                     "WHERE player=%s AND product=%s FOR UPDATE",
                     (player,product)).fetchone()
    if row is None or row[0] is None:raise ValueError("V2 product not unlocked")
    return v(row[0])

def initialize_stage(conn):
    _guard(conn)
    with conn.transaction():
        init_registry(conn)
        conn.execute("""CREATE TABLE IF NOT EXISTS hare_factory.v2_action_receipts_stage(
          op_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result JSONB NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS hare_factory.v2_bank_contracts_stage(
          op_id TEXT PRIMARY KEY, player TEXT NOT NULL, kind TEXT NOT NULL,
          amount_v2 TEXT NOT NULL)""")

def action(conn,op_id,kind,player,**payload):
    _guard(conn)
    if not isinstance(op_id,str) or not op_id.isascii() or not 8<=len(op_id)<=100:
        raise ValueError("Invalid operation ID")
    if not isinstance(player,str) or not player or len(player)>100:
        raise ValueError("Invalid player")
    supported={"manufacture","upgrade","ship","edit_shipment","cancel_shipment",
      "set_price","admin_grant","admin_collect","admin_forgive",
      "bank_borrow","bank_lend","bank_repay","bank_withdraw"}
    if kind not in supported:raise ValueError("Unsupported V2 action")
    fingerprint=hashlib.sha256(json.dumps(
        [kind,player,payload],sort_keys=True,ensure_ascii=False,
        separators=(",",":")).encode()).hexdigest()
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout='6s'")
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(op_id,))
        registry_replay=check_registry(conn,op_id,"v2_action",fingerprint)
        old=conn.execute("SELECT fingerprint,result FROM hare_factory.v2_action_receipts_stage "
                         "WHERE op_id=%s",(op_id,)).fetchone()
        if old:
            if not registry_replay or old[0]!=fingerprint:
                raise ValueError("Operation ID receipt and registry mismatch")
            return dict(old[1])
        if registry_replay:
            raise ValueError("Registry contains operation without its receipt")
        cash,tier=_locked(conn,player)
        result={}
        if kind in ("manufacture","upgrade","ship","edit_shipment","cancel_shipment","set_price"):
            product=payload.get("product","white")
            if product not in ("white","sea","shisa"):raise ValueError("Invalid product")
        if kind=="manufacture":
            qty=positive(payload["quantity"])
            stock=_stock(conn,player,product)
            conn.execute("UPDATE hare_factory.stock SET quantity_v2=%s WHERE player=%s AND product=%s",
                         ((stock+qty).serialize(),player,product))
            conn.execute("UPDATE hare_factory.factory_totals SET manufactured_v2=%s WHERE player=%s",
                         ((v(conn.execute("SELECT manufactured_v2 FROM hare_factory.factory_totals "
                            "WHERE player=%s FOR UPDATE",(player,)).fetchone()[0])+qty).serialize(),player))
            result={"produced":qty.serialize()}
        elif kind=="upgrade":
            cost=positive(payload["cost"])
            if cash.compare(cost)<0:raise ValueError("Insufficient money")
            conn.execute("UPDATE hare_factory.factories SET cash_v2=%s,tier=tier+1 WHERE player=%s",
                         ((cash-cost).serialize(),player))
            row=conn.execute("SELECT purchases_v2 FROM hare_factory.factory_totals "
                             "WHERE player=%s FOR UPDATE",(player,)).fetchone()
            conn.execute("UPDATE hare_factory.factory_totals SET purchases_v2=%s WHERE player=%s",
                         ((v(row[0])+cost).serialize(),player))
            result={"spent":cost.serialize(),"tier":tier+1}
        elif kind in ("ship","edit_shipment","set_price","cancel_shipment"):
            stock=_stock(conn,player,product)
            listing=conn.execute("SELECT id,quantity_v2,price_v2 FROM hare_factory.listings "
                                 "WHERE player=%s AND product=%s FOR UPDATE",
                                 (player,product)).fetchone()
            if kind in ("set_price","edit_shipment","cancel_shipment") and not listing:
                raise ValueError("No shipment")
            reserved=v(listing[1]) if listing else Z
            if kind=="cancel_shipment":
                conn.execute("UPDATE hare_factory.stock SET quantity_v2=%s "
                             "WHERE player=%s AND product=%s",
                             ((stock+reserved).serialize(),player,product))
                conn.execute("DELETE FROM hare_factory.listings WHERE id=%s",(listing[0],))
                result={"returned":reserved.serialize()}
            else:
                price=positive(payload["price"])
                min_price={"white":2,"sea":5,"shisa":23}[product]
                if price.compare(S.parse(str(min_price)))<0:raise ValueError("Price below minimum")
                if kind=="set_price":
                    conn.execute("UPDATE hare_factory.listings SET price_v2=%s WHERE id=%s",
                                 (price.serialize(),listing[0]))
                    result={"price":price.serialize()}
                else:
                    qty=positive(payload["quantity"])
                    if (stock+reserved).compare(qty)<0:raise ValueError("Insufficient stock")
                    conn.execute("UPDATE hare_factory.stock SET quantity_v2=%s "
                                 "WHERE player=%s AND product=%s",
                                 ((stock+reserved-qty).serialize(),player,product))
                    if listing:
                        conn.execute("UPDATE hare_factory.listings SET quantity_v2=%s,price_v2=%s "
                                     "WHERE id=%s",(qty.serialize(),price.serialize(),listing[0]))
                    else:
                        conn.execute("INSERT INTO hare_factory.listings"
                                     "(id,player,product,quantity_v2,price_v2) VALUES(%s,%s,%s,%s,%s)",
                                     (op_id,player,product,qty.serialize(),price.serialize()))
                    result={"reserved":qty.serialize(),"price":price.serialize()}
        elif kind in ("admin_grant","admin_collect"):
            amt=positive(payload["amount"])
            next_cash=cash+amt if kind=="admin_grant" else cash-amt
            conn.execute("UPDATE hare_factory.factories SET cash_v2=%s WHERE player=%s",
                         (next_cash.serialize(),player))
            result={"cash":next_cash.serialize()}
        elif kind=="admin_forgive":
            conn.execute("DELETE FROM hare_factory.v2_bank_contracts_stage "
                         "WHERE player=%s AND kind='borrow'",(player,))
            if cash.sign()<0:cash=Z
            conn.execute("UPDATE hare_factory.factories SET cash_v2=%s WHERE player=%s",
                         (cash.serialize(),player))
            result={"cash":cash.serialize(),"debt":Z.serialize()}
        elif kind in ("bank_lend","bank_borrow"):
            amt=positive(payload["amount"])
            interest=payload.get("interest_bps",0)
            if type(interest) is not int or not 0<=interest<=10000:
                raise ValueError("Invalid interest")
            due=amt+mul_ratio_floor(amt,interest)
            if kind=="bank_lend" and cash.compare(amt)<0:raise ValueError("Insufficient deposits")
            changed=cash-amt if kind=="bank_lend" else cash+amt
            conn.execute("UPDATE hare_factory.factories SET cash_v2=%s WHERE player=%s",
                         (changed.serialize(),player))
            conn.execute("INSERT INTO hare_factory.v2_bank_contracts_stage VALUES(%s,%s,%s,%s)",
                         (op_id,player,"lend" if kind=="bank_lend" else "borrow",due.serialize()))
            result={"contract_id":op_id,"due":due.serialize(),"cash":changed.serialize()}
        elif kind in ("bank_repay","bank_withdraw"):
            row=conn.execute("SELECT kind,amount_v2 FROM hare_factory.v2_bank_contracts_stage "
                             "WHERE op_id=%s AND player=%s FOR UPDATE",
                             (payload["contract_id"],player)).fetchone()
            expected="borrow" if kind=="bank_repay" else "lend"
            if not row or row[0]!=expected:raise ValueError("Contract missing")
            due=v(row[1])
            if kind=="bank_repay" and cash.compare(due)<0:raise ValueError("Insufficient repayment funds")
            changed=cash-due if kind=="bank_repay" else cash+due
            conn.execute("UPDATE hare_factory.factories SET cash_v2=%s WHERE player=%s",
                         (changed.serialize(),player))
            conn.execute("DELETE FROM hare_factory.v2_bank_contracts_stage WHERE op_id=%s",
                         (payload["contract_id"],))
            result={"settled":due.serialize(),"cash":changed.serialize()}
        register_op(conn,op_id,"v2_action",fingerprint)
        conn.execute("INSERT INTO hare_factory.v2_action_receipts_stage VALUES(%s,%s,%s)",
                     (op_id,fingerprint,json.dumps(result)))
        return result
