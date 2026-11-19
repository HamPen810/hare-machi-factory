"""Staging-only V2 exact event ledger for balances, charts, and rankings.

Each economic event is written within the SAME PostgreSQL transaction
as its balance/stock mutation and immutable operation receipt. Never use
float or PostgreSQL NUMERIC for huge V2 ledger entries.
"""
from __future__ import annotations
from functools import cmp_to_key
from sparse_exact_v1 import SparseExact as S

ZERO=S.parse("0")
FIELDS=("cash_delta_v2","stock_delta_v2","gross_revenue_v2",
        "manufactured_v2","expense_v2")


def initialize(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hare_factory.v2_economic_events_stage (
          op_id TEXT NOT NULL,
          player TEXT NOT NULL,
          actor_role TEXT NOT NULL,
          kind TEXT NOT NULL,
          product TEXT,
          cash_delta_v2 TEXT NOT NULL,
          stock_delta_v2 TEXT NOT NULL,
          gross_revenue_v2 TEXT NOT NULL,
          manufactured_v2 TEXT NOT NULL,
          expense_v2 TEXT NOT NULL,
          event_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
          PRIMARY KEY(op_id,player,actor_role)
        )
    """)


def _exact(value):
    if isinstance(value,S):
        return value.serialize()
    if isinstance(value,str):
        return S.deserialize(value).serialize() if value.startswith("S1:") else S.parse(value).serialize()
    raise ValueError("Non-exact economic event value")


def emit(conn,*,op_id,player,role,kind,product=None,
         cash=ZERO,stock=ZERO,revenue=ZERO,manufactured=ZERO,expense=ZERO):
    if role not in ("actor","buyer","seller"):
        raise ValueError("Invalid event role")
    if not isinstance(op_id,str) or not isinstance(player,str) or not isinstance(kind,str):
        raise ValueError("Invalid economic event identity")
    values=tuple(_exact(x) for x in (cash,stock,revenue,manufactured,expense))
    cursor=conn.execute("""
        INSERT INTO hare_factory.v2_economic_events_stage
        (op_id,player,actor_role,kind,product,cash_delta_v2,stock_delta_v2,
         gross_revenue_v2,manufactured_v2,expense_v2)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """,(op_id,player,role,kind,product,*values))
    if cursor.rowcount!=1:
        raise RuntimeError("V2 event ledger insert failed")


def metrics(conn):
    """Return all-player exact aggregate and rankings without float conversions."""
    rows=conn.execute("""
        SELECT player,gross_revenue_v2,manufactured_v2,expense_v2,cash_delta_v2
        FROM hare_factory.v2_economic_events_stage ORDER BY event_at,op_id
    """).fetchall()
    totals={}
    for player,revenue,manufactured,expense,cash in rows:
        row=totals.setdefault(player,{
            "revenue":ZERO,"manufactured":ZERO,"expenses":ZERO,"cash_change":ZERO})
        row["revenue"]=row["revenue"]+S.deserialize(revenue)
        row["manufactured"]=row["manufactured"]+S.deserialize(manufactured)
        row["expenses"]=row["expenses"]+S.deserialize(expense)
        row["cash_change"]=row["cash_change"]+S.deserialize(cash)
    results={k:{m:v.serialize() for m,v in data.items()} for k,data in totals.items()}
    ranked=sorted(totals,key=cmp_to_key(
        lambda a,b:totals[b]["revenue"].compare(totals[a]["revenue"]) or (a>b)-(a<b)
    ))
    return {"format":"S1","authoritative":"v2_staging_event_ledger",
            "players":results,"revenue_rank":[
                {"player":player,"rank":idx+1,"revenue":totals[player]["revenue"].serialize()}
                for idx,player in enumerate(ranked)]}


def timeline(conn,player=None,limit=300):
    if type(limit) is not int or not 1<=limit<=1000:
        raise ValueError("Invalid timeline limit")
    sql=("SELECT op_id,player,actor_role,kind,product,cash_delta_v2,stock_delta_v2,"
         "gross_revenue_v2,manufactured_v2,expense_v2 "
         "FROM hare_factory.v2_economic_events_stage")
    if player is not None:
        if not isinstance(player,str) or not player:
            raise ValueError("Invalid user identity")
        sql+=" WHERE player=%s ORDER BY event_at DESC,op_id LIMIT %s"
        params=(player,limit)
    else:
        sql+=" ORDER BY event_at DESC,op_id LIMIT %s"
        params=(limit,)
    rows=conn.execute(sql,params).fetchall()
    names=("op_id","player","role","kind","product",*FIELDS)
    return [dict(zip(names,row)) for row in rows]
