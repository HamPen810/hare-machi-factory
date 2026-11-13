# Huge Number Phase 4 — Disposable PostgreSQL concurrency and schema tests

Date: 2026-11-13
Status: Passed on isolated GitHub Actions PostgreSQL 16, NOT live production.

## Results verified by CI
- Built a PostgreSQL-only laboratory in deployment/v2_postgres_disposable_lab.py.
- It rejects remote hosts and any database not named hare_v2_ci_*.
- Tests use only synthetic cash, stock, players, and trade identities.
- Exact cash/stock/tax market transfers succeeded for values beyond e1000000000.
- 64 concurrent retries of one operation ID resulted in precisely one receipt.
- 20 simultaneous buyers for 10 in-stock items resulted in exactly 10 successful purchases.
- An injected exception after partial SQL updates rolled back all affected rows.
- Shadow backfill was repeatable and rejected mismatches without overwriting data.
- Same operation ID with a changed payload was rejected.
- Staging-only ALTER TABLE ADD COLUMN IF NOT EXISTS was executed on SYNTHETIC
  PostgreSQL tables mimicking the economic NUMERIC column names. Existing
  NUMERIC types and values were preserved; repeating the DDL was safe.
- CI test workflow: .github/workflows/test-v2-postgres-disposable.yml.
- No Supabase credentials or production player records were used by CI.

## Explicit limits
- PostgreSQL 16 in GitHub Actions is not Supabase's production PostgreSQL 17.
- The test database is not a restored copy of production data.
- Actual Supavisor pooling, network failures, settlement scheduling,
  production indexing and multi-server writes have not been tested.
- Actual PostgreSQL row locking was exercised, but passing a synthetic test
  does not prove that all application SQL is converted correctly.
- The market lab's fee model is simplified and does not replace the actual
  tiered/asset tax, banking, manufacturing or item allocation algorithms.
- Exact sparse numbers remain subject to bounded term counts, representation
  limitations, API payload limits, runtime and storage.
- A full restorable backup of production is still not verified.

## Production protection
- No DDL/DML was issued against production Supabase.
- No existing balance, stock, transaction or player was modified.
- None of the experimental modules are imported by the live game server ZIP.
- Do not enable V2 writes or remove NUMERIC caps yet.

## Next gates
1. Verify a full restorable production backup and stage from a restore.
2. Run the same transactional tests with PostgreSQL 17 and against a restored
   staging schema, including a replica of the production data and constraints.
3. Test real market allocator, banks, manufacturing, taxes, rare drops,
   admins and all worker processes using V2 inputs.
4. Build shadow-column backfill with progress checkpoints and live-update
   conflict checks, then stage application code with V2 writes still off.
5. Coordinate a write freeze, final balance reconciliation and atomic cutover,
   retaining V2-aware rollback and the pre-cutover exact backups.
