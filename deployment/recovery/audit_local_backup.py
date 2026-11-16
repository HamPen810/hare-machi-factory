"""Safely inspect a verified production backup using LOCAL PostgreSQL only.

Never contacts Supabase/Render. Requires local PostgreSQL >= 17 with pg_restore,
psql, createdb, and pg_isready on PATH; PGHOST must be localhost/127.0.0.1.

Usage:
  python deployment/recovery/audit_local_backup.py "C:/path/to/hare_factory.dump" --sha256 <verified sha>

This creates a fresh database named hare_recovery_audit_<random> and NEVER
drops the database. Review the report and remove the disposable database later.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

EXPECTED_SHA256 = "cc226e9f0246bf41b1c4571ca67694082fb6a09e71bd8d9e444f77604755207e"
SAFE_HOSTS = {"127.0.0.1", "localhost", "::1"}


def run(args, *, text=True):
    result = subprocess.run(args, text=text, capture_output=True, check=False)
    if result.returncode:
        output = ((result.stdout or "") + "\n" + (result.stderr or ""))[-1800:]
        raise RuntimeError(f"Command {args[0]!r} failed (exit {result.returncode}): {output}")
    return result.stdout


def assert_local(host):
    if host not in SAFE_HOSTS:
        raise ValueError("Only loopback PostgreSQL is allowed; remote databases are prohibited")


def verify_backup(path, expected_sha):
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual.lower() != expected_sha.lower():
        raise ValueError(f"SHA256 mismatch: {actual}; refusing restore")
    print(f"BACKUP_SHA256_OK bytes={size} sha256={actual}")
    manifest = run(["pg_restore", "--list", str(path)])
    print(f"RESTORE_MANIFEST_OK entries={sum(1 for line in manifest.splitlines() if re.match(r'^\d+;', line))}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--sha256", default=EXPECTED_SHA256)
    parser.add_argument("--restore", action="store_true", help="Opt-in restore into a NEW LOCAL PostgreSQL database")
    args = parser.parse_args()
    verify_backup(args.backup, args.sha256)
    if not args.restore:
        print("DRY_RUN_ONLY: use --restore to create and restore a NEW disposable LOCAL DB")
        return
    host = os.environ.get("PGHOST", "localhost")
    assert_local(host)
    database = "hare_recovery_audit_" + secrets.token_hex(5)
    assert re.fullmatch(r"hare_recovery_audit_[0-9a-f]{10}", database)
    print("RESTORE_TARGET_NEW_DATABASE", database)
    run(["createdb", "-h", host, database])
    try:
        run(["pg_restore", "-h", host, "--no-owner", "--no-privileges", "--exit-on-error", "-d", database, str(args.backup)])
    except Exception as error:
        print("RESTORE_FAILED database remains for inspection:", database, file=sys.stderr)
        raise
    size=run(["psql", "-h", host, "-d", database, "-X", "-At", "-c",
              "SELECT pg_database_size(current_database())"])
    print("RESTORED_DATABASE_BYTES", size.strip())
    relation_sql = (
        "SELECT relname||'='||pg_total_relation_size(c.oid) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='hare_factory' AND c.relkind='r' "
        "ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 12")
    print("LARGEST_TABLES")
    print(run(["psql", "-h", host, "-d", database, "-X", "-At", "-c", relation_sql]))
    print("LOCAL_RESTORE_COMPLETE_NO_PRODUCTION_CHANGES")
    print("Disposable database left intact:", database)


if __name__ == "__main__":
    main()
