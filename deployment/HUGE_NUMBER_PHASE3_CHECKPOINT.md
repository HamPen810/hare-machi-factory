# Phase 3 checkpoint — isolated SQL transaction laboratory and staging manifest

**Status:** Complete as independent proof-of-concept, **not production-enabled**.
Date: 2026-11-13. Never execute shadow DDL against production without a
verified backup and a restored PostgreSQL staging environment.

## Delivered and CI-verified

- v2_sqlite_shadow_lab.py / test_v2_sqlite_shadow_lab.py
  - Isolated SQLite schema with legacy string fields and shadow *_v2 TEXT.
  - Idempotent exact backfill from legacy fixtures, rejecting mismatches.
  - One atomic transaction transferring exact cash, taxes and inventory.
  - No overdraft prohibition; buyer cash can become negative.
  - Immutable operation IDs: 60 simultaneous duplicate requests update once.
  - 25 competing buyers for 10 stock units: exactly 10 purchases succeed.
  - Injected failure after partial SQL updates rolls back all row changes.
  - Local file-backup/restore rehearsal succeeded; this is NOT a backup
    or restore test of the actual Supabase production database.
  - Cash+treasury and item conservation verified with exact sparse arithmetic.

- v2_shadow_schema_manifest.py / test_v2_shadow_schema_manifest.py
  - Whitelist of economic NUMERIC fields from read-only review of actual
    PostgreSQL schema (factories, stock, listings, orders, bank, sales,
    market history/ticks, totals, rare collection, admin audit).
  - Generates nullable shadow columns for staging only.
  - Does NOT run generated SQL or connect to DB.
  - Does not replace/drop original economic fields; audit tests block
    destructive SQL and mistaken timestamp/identifier conversion.
  - Drift detection fails closed when a live source column is no longer NUMERIC.

- All tests pass on GitHub Actions workflows:
  - .github/workflows/test-v2-sqlite-shadow-lab.yml
  - .github/workflows/test-v2-shadow-schema-manifest.yml

## Remaining hard blockers before production activation

1. Verified production backup: none confirmed restorable for Supabase
   project x nqvygduplopkkhnrbis (project ID without the display space:
   xnqvygduplopkkhnrbis). SQLite fixtures are insufficient.
2. Isolated PostgreSQL environment: Supabase development branches list
   was empty. Creating a branch may cost money and is not equivalent to
   restoring a production-data backup.
3. Backend migration: live game ZIP still uses PostgreSQL NUMERIC
   operations, market settlement, taxes, banks, manufacturing, rare items
   and admin grants. None has been switched to V2.
4. Real PostgreSQL race testing: SQLite BEGIN IMMEDIATE serializes the
   entire database, unlike PostgreSQL row locks and Supavisor pooling.
5. Sparse representation limits: a finite number of terms/coefficients;
   not all integer divisions compress to a compact expression.
6. Backfill and cutover: need durable ordered backfill, live-write catch-up,
   all-node reader compatibility, write freeze, reconciliation and a
   V2-compatible rollback.
7. API/UI integration: clients, admin forms, huge number formatting and
   request-size checks have not been migrated.

## Safety state

No production table altered, no player account modified, no synthetic
purchase posted to live game. Only independent code, tests and schema
plan files committed to GitHub. Live NUMERIC limit is unchanged.

Next gate: obtain independently restored PostgreSQL staging, run shadow
DDL, exact backfill, real concurrent settlement and recovery drills there.
