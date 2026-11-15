"""Compact a VERIFIED, RESTORED local HareMachi PostgreSQL database.

This script NEVER connects to production. It only accepts a database named
hare_recovery_audit_<10 lowercase hex> on localhost/127.0.0.1/::1.

Safe behavior:
- --plan (default): summary only, no writes.
- --apply: compress large tap_batch result JSON as a reversible envelope.
- Preserve every action key, payload and non-tap result.
- Remove ONLY authorized historic market_ticks rounds (<29909700).
- Do NOT touch market_history, sales, financial/account/stock/leaderboard data.
- Do not automatically VACUUM FULL: it needs additional free disk and a table lock.
- Original production database must remain unchanged and separately backed up.
The matching app patch is deployment/reduce-tap-result-size.py.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import zlib

EXPECTED_PREFIX = "hare_recovery_audit_"
ROUND_CUTOFF = 29909700
ENVELOPE_KEY = "_tap_batch_zlib_v1"


def guard(host: str, dbname: str):
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("REMOTE CONNECTION BLOCKED")
    if re.fullmatch(r"hare_recovery_audit_[0-9a-f]{10}", dbname) is None:
        raise ValueError("NON-DISPOSABLE DATABASE BLOCKED")


def codec(raw: str) -> str:
    """Losslessly compress raw result text; never parse gigantic integer JSON."""
    if len(raw) < 4096 or raw.startswith('{"_tap_batch_zlib_v1":'):
        return raw
    original = raw.encode("utf-8")
    payload = base64.b64encode(zlib.compress(original, 6)).decode("ascii")
    packed = json.dumps({ENVELOPE_KEY: payload})
    if len(packed.encode("utf-8")) >= len(original):
        return raw
    decoded = zlib.decompress(base64.b64decode(json.loads(packed)[ENVELOPE_KEY]))
    if hashlib.sha256(decoded).digest() != hashlib.sha256(original).digest():
        raise AssertionError("Failed compression roundtrip")
    return packed


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", required=True, help="EXISTING new local restored audit database name")
    cli.add_argument("--host", default="localhost")
    cli.add_argument("--apply", action="store_true")
    cli.add_argument("--archive-confirmed", action="store_true",
                     help="Only valid with --apply: confirm restored DB is independently backed up")
    cli.add_argument("--batch", type=int, default=128)
    args = cli.parse_args()
    guard(args.host, args.db)
    if args.batch < 1 or args.batch > 1024:
        raise ValueError("Invalid batch size")
    if args.apply and not args.archive_confirmed:
        raise ValueError("--apply needs --archive-confirmed")
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError("Install psycopg[binary] on your local PC") from e
    target = dict(host=args.host, dbname=args.db, connect_timeout=5)
    with psycopg.connect(**target) as conn:
        conn.execute("SET search_path TO hare_factory, pg_catalog")
        names = {r[0] for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='hare_factory'")}
        if not {"actions", "market_ticks", "players", "factories", "stock"}.issubset(names):
            raise RuntimeError("Expected restored game schema missing")
        summary = conn.execute(
            "SELECT pg_database_size(current_database()), "
            "pg_total_relation_size('hare_factory.actions'), "
            "pg_total_relation_size('hare_factory.market_ticks')").fetchone()
        print("LOCAL_DB_BYTES", *summary)
        print("PLAN: retain all action identity keys and non-tap results.")
        print("PLAN: remove only market_ticks where round <", ROUND_CUTOFF)
        if not args.apply:
            print("DRY_RUN_COMPLETE_NO_WRITES")
            return

    totals = {"scanned": 0, "compressed": 0, "saved_text_bytes": 0}
    # Independent reader and writer: reader cursor snapshot remains stable while
    # the writer batches changed records on this fresh, offline restoration.
    with psycopg.connect(**target) as reader, psycopg.connect(**target, autocommit=True) as writer:
        reader.execute("SET search_path TO hare_factory, pg_catalog")
        writer.execute("SET search_path TO hare_factory, pg_catalog")
        with reader.cursor(name="tap_result_read") as cur:
            cur.itersize = args.batch
            cur.execute(
                "SELECT player,key,result FROM hare_factory.actions "
                "WHERE left(payload, 12) = '[\"tap_batch\"' "
                "ORDER BY player,key")
            while rows := cur.fetchmany(args.batch):
                updates=[]
                for player, key, raw in rows:
                    totals["scanned"] += 1
                    encoded = codec(raw)
                    if encoded == raw:
                        continue
                    updates.append((encoded, player, key))
                    totals["saved_text_bytes"] += len(raw.encode("utf8"))-len(encoded.encode("utf8"))
                    totals["compressed"] += 1
                with writer.transaction():
                    for result,player,key in updates:
                        writer.execute(
                            "UPDATE hare_factory.actions SET result=%s "
                            "WHERE player=%s AND key=%s",
                            (result,player,key))
                if totals["scanned"] % (args.batch * 50) < args.batch:
                    print("PROGRESS", json.dumps(totals))
    print("ACTION_COMPRESSION", json.dumps(totals))

    with psycopg.connect(**target, autocommit=True) as conn:
        with conn.transaction():
            # For the explicitly authorized old rounds only.
            deleted = conn.execute(
                "DELETE FROM hare_factory.market_ticks WHERE round < %s",
                (ROUND_CUTOFF,))
            print("MARKET_TICKS_DELETED", deleted.rowcount)
    print("LOCAL_ONLY_COMPACTION_FINISHED")
    print("NEXT: check free disk, VACUUM FULL actions and market_ticks on this local copy,")
    print("then verify database size <500MB, game regressions and replay before migration.")


if __name__ == "__main__":
    main()
