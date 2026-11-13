# Huge Number Phase 5 checkpoint — PostgreSQL 17 + lossless NUMERIC backfill

Date: 2026-11-13
Status: CI-verified isolated test only. No production DB migration.

## Verified
- Upgraded disposable GitHub Actions PostgreSQL from 16 to 17.
- All prior synthetic PostgreSQL simultaneous purchase, row locking,
  duplicate key, transaction rollback, shadow DDL, and validation tests passed.
- Added v2_numeric_lossless_backfill.py (pure Python, no DB connection).
- Splits legacy NUMERIC integers into <=900-digit coefficient chunks;
  does not build a single gigantic Python int, avoiding the interpreter's
  4,300-digit int-string conversion guard.
- Recognizes fixed-point NUMERIC and exponent notation only when the
  represented amount is exactly integral. Rejects fractional amounts.
- Tested the full PostgreSQL integer physical limit of 131,072 digits,
  with actual NUMERIC cast and read-back on PostgreSQL 17.
- Tested negative quantities/values, e7600, a 10,000-digit alternating
  pattern, exact Decimal input, roundtrip serialization, and 600 randomized
  comparisons with Python integers.
- GitHub Actions test-v2-postgres-disposable.yml: all tests passed after
  fixing an initially failing reference test that attempted to call
  Python's int() on a 10,000-digit string.

## Scope and limitations
- This is a SOURCE VALUE CONVERTER, not an online migrator. It does not
  write cash_v2 or quantity_v2 to Supabase.
- Full post-backfill reconciliation must be tested with a restored
  production snapshot and all row versions/ongoing writes accounted for.
- No production backup inventory or restoration could be verified using
  the available connected Supabase tools. Supabase Backups dashboard must
  be checked and an independent restore drill performed.
- The current sparse format has a maximum of 2,048 terms, so future
  growth after repeated trade operations still requires maintenance,
  normalization and resource-budget engineering.
- Exact floor division by arbitrary huge non-decimal divisors and game
  market allocator/bank/tax behavior are not production complete.
- Synthetic PostgreSQL tests do not verify actual Supavisor pooling,
  real multi-Render deployments, disaster recovery, or peak load.

## Production cutover gates
1. Verified restorable full backup (DB schema, rows, functions/indexes).
2. Restored PostgreSQL 17 staging DB using real source data.
3. Snapshot consistency and row-wise NUMERIC <-> V2 comparison.
4. Concurrent backfill, live writes reconciliation, and all economic
   game flows through V2 staging.
5. All Render services updated with V2-aware, disabled writers.
6. Coordinated cutover, monitored reconciliation and V2-aware rollback.

Do not alter live NUMERIC columns or activate V2 writers until all
gates pass. All new code in this phase lives under deployment/ only.
