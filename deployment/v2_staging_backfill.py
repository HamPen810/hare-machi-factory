"""Lossless V2 backfill into staging-only TEXT shadow columns.

FAIL CLOSED: accepts only explicitly named local PostgreSQL STAGING databases.
Run only after restoring a verified backup and applying the separate shadow
schema manifest. Never copies, alters, or drops legacy NUMERIC columns.
"""
import os
import sys
from urllib.parse import urlparse

from v2_shadow_schema_manifest import ECONOMIC_COLUMNS, q
from v2_numeric_lossless_backfill import sparse_integer_from_legacy_column
from sparse_exact_v1 import SparseExact


def verify_stage_dsn(dsn):
    parsed=urlparse(dsn or "")
    name=(parsed.path or "").lstrip("/")
    if os.environ.get("HARE_V2_LOCAL_STAGING")!="yes":
        raise RuntimeError("Explicit local staging opt-in required")
    if parsed.scheme not in ("postgres","postgresql"):
        raise RuntimeError("PostgreSQL URL required")
    if parsed.hostname not in ("127.0.0.1","localhost"):
        raise RuntimeError("Remote databases are forbidden")
    if not name.startswith("hare_v2_stage_"):
        raise RuntimeError("Database must start with hare_v2_stage_")
    return name


def backfill_table(conn, table, columns, batch_size=100):
    if table not in ECONOMIC_COLUMNS or tuple(columns)!=tuple(ECONOMIC_COLUMNS[table]):
        raise ValueError("Table/column whitelist mismatch")
    if not 1<=batch_size<=1000:
        raise ValueError("Invalid staging batch size")

    relation=q("hare_factory")+"."+q(table)
    refs=[(q(col),q(col+"_v2")) for col in columns]
    where=" OR ".join(f"({col} IS NOT NULL AND {shadow} IS NULL)" for col,shadow in refs)
    select_fields=", ".join(
        [f"CAST({col} AS TEXT) AS {q('source_'+str(i))}" for i,(col,_) in enumerate(refs)]
        +[f"{shadow} AS {q('target_'+str(i))}" for i,(_,shadow) in enumerate(refs)])
    updated=0
    while True:
        with conn.transaction():
            # The staging application is not live; serialise migration table
            # batches and reject concurrent writers with a short lock timeout.
            conn.execute("SET LOCAL lock_timeout='2s'")
            conn.execute(f"LOCK TABLE {relation} IN SHARE ROW EXCLUSIVE MODE")
            rows=conn.execute(
                f"SELECT ctid::text AS locator,{select_fields} FROM {relation} "
                f"WHERE {where} ORDER BY ctid LIMIT %s FOR UPDATE",
                (batch_size,)).fetchall()
            if not rows:
                break
            for row in rows:
                changes={}
                for i,(col,shadow) in enumerate(refs):
                    source=row["source_"+str(i)]
                    target=row["target_"+str(i)]
                    if source is None:
                        if target is not None:
                            raise ValueError("Shadow value for NULL legacy source")
                        continue
                    canonical=sparse_integer_from_legacy_column(source)
                    if target is None:
                        changes[shadow]=canonical
                    elif SparseExact.deserialize(target).compare(SparseExact.deserialize(canonical))!=0:
                        raise ValueError("Existing shadow differs from original")
                if not changes:
                    raise AssertionError("Selected staging row has no pending changes")
                updates=", ".join(f"{shadow}=%s" for shadow in changes)
                cur=conn.execute(
                    f"UPDATE {relation} SET {updates} WHERE ctid=%s::tid",
                    [*changes.values(),row["locator"]])
                if cur.rowcount!=1:
                    raise RuntimeError("Staging row changed during backfill")
                updated+=1
    return updated


def verify_table(conn, table, columns):
    if table not in ECONOMIC_COLUMNS or tuple(columns)!=tuple(ECONOMIC_COLUMNS[table]):
        raise ValueError("Invalid staging table")
    relation=q("hare_factory")+"."+q(table)
    fields=", ".join(f"CAST({q(c)} AS TEXT) AS {q('src'+str(i))}, "
                      f"{q(c+'_v2')} AS {q('dst'+str(i))}"
                      for i,c in enumerate(columns))
    checked=0
    with conn.transaction():
        cursor=conn.execute(f"SELECT {fields} FROM {relation}")
        for row in cursor:
            for i in range(len(columns)):
                src=row["src"+str(i)]
                dst=row["dst"+str(i)]
                if src is None and dst is None:continue
                if src is None or dst is None:
                    raise ValueError("Legacy/shadow NULL mismatch")
                expected=sparse_integer_from_legacy_column(src)
                if SparseExact.deserialize(expected).compare(SparseExact.deserialize(dst))!=0:
                    raise ValueError("Legacy/shadow exact-value mismatch")
            checked+=1
    return checked


def main(dsn):
    verify_stage_dsn(dsn)
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn,autocommit=True,row_factory=dict_row,connect_timeout=5) as conn:
        for table,cols in ECONOMIC_COLUMNS.items():
            n=backfill_table(conn,table,cols)
            checked=verify_table(conn,table,cols)
            print(f"{table}: backfilled={n}, verified={checked}")
    print("V2_LOCAL_STAGE_BACKFILL_VERIFIED")


if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: HARE_V2_LOCAL_STAGING=yes python v2_staging_backfill.py LOCAL_STAGING_DSN")
    main(sys.argv[1])
