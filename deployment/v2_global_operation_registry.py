"""Shared operation-ID conflict barrier for all staging V2 asset writers.

Requires an already-open transaction and an acquired advisory lock on op_id.
Does not replace per-operation receipts (which retain original result bodies).
"""
from __future__ import annotations


def initialize(conn):
    """Staging-only DDL, called while the caller's local-only guard is active."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hare_factory.v2_operation_registry_stage (
          op_id TEXT PRIMARY KEY,
          scope TEXT NOT NULL,
          fingerprint TEXT NOT NULL
        )
    """)


def check(conn, op_id, scope, fingerprint):
    """Must run after pg_advisory_xact_lock(hashtextextended(op_id,0))."""
    if not isinstance(op_id,str) or not 8<=len(op_id)<=128:
        raise ValueError("Invalid V2 operation ID")
    if scope not in ("v2_action","v2_trade"):
        raise ValueError("Invalid V2 operation scope")
    if not isinstance(fingerprint,str) or len(fingerprint)!=64:
        raise ValueError("Invalid V2 fingerprint")
    row=conn.execute(
        "SELECT scope,fingerprint FROM hare_factory.v2_operation_registry_stage "
        "WHERE op_id=%s",
        (op_id,)
    ).fetchone()
    if row is None:
        return False
    if row[0]!=scope or row[1]!=fingerprint:
        raise ValueError("Operation ID reused across different V2 transactions")
    return True


def register(conn,op_id,scope,fingerprint):
    """Commit with the money/stock/receipt transaction, never separately."""
    cur=conn.execute(
        "INSERT INTO hare_factory.v2_operation_registry_stage(op_id,scope,fingerprint) "
        "VALUES(%s,%s,%s)",
        (op_id,scope,fingerprint)
    )
    if cur.rowcount!=1:
        raise RuntimeError("V2 operation registry insert failed")
