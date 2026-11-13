# Huge-number migration — Phase 2: exact division and isolated market reference

**Status:** Experimental tests passed on GitHub Actions. No production
database migration, no actual player action, and no change to the live
`hare-machi-render.zip` game source in this stage.

## Added

- `sparse_exact_division.py`: exact floor division and remainder by
  powers of ten (including negative balances), exact basis-point tax
  calculation and exact ceiling for fee/interest rounding.
- `test_sparse_exact_division.py`: randomized differential arithmetic
  tests against Python integers, ultra-large exponent invariants,
  tax rounding and conserved-value identities.
- `economy_v2_reference.py`: in-memory, lock-serialized reference model
  for buying, seller credit, treasury withholding, stock transfer and
  idempotent transaction ID replay.
- `test_economy_v2_reference.py`: concurrent replay (120 requests using
  the same transaction ID), 30 competing buyers for 10 items, negative
  buyer cash, rejected/unchanged failed transactions, and cash/stock
  conservation.
- `.github/workflows/test-economy-v2-reference.yml` runs the earlier
  exact arithmetic suites plus reference-model tests.

## Explicit unresolved risks

1. **No PostgreSQL transaction test.** The in-memory RLock is not an
   implementation of database isolation. Row locks, concurrent writes,
   Supavisor timeouts, automatic settlement and duplicate HTTP retries
   must be tested in an isolated PostgreSQL database.
2. **Not all quotient shapes have compact sparse representations.**
   `10**1000000 // 3` has a long repeating pattern and can require
   enormous expansion. `divmod_bounded` rejects huge non-decimal
   quotients rather than silently approximating. Real game algorithms
   must choose a sound exact division representation or change game
   rules where such divisions are required.
3. **Term growth is bounded.** The sparse format has guardrails
   (`MAX_TERMS=2048`, coefficient length 10000, exponent text 256
   digits). These are provisional operational bounds and not an
   unlimited mathematical representation.
4. **More cross-service testing is required.** Admin funding,
   banking, market allocation, upgrades, production, rare items and
   tax schedules have not been migrated to V2.
5. **Idempotency fingerprint uses serialized sparse terms.** In the
   prototype equivalent numeric expressions can have different
   fingerprints; a final API must canonicalize numerical values or
   fingerprint the unchanged validated original request.

## Mandatory next gate: verified staging and backup

- Verify a restorable snapshot of Supabase project
  `xnqvygduplopkkhnrbis` including `hare_factory`, with all
  dependent sequences, functions, constraints and indexes.
- Create a physically isolated copy; never use the live DB to test
  schema migrations or synthetic transactions.
- Rehearse restoring the data and compare account and stock totals.
- Only then design and test `*_v2` shadow columns in the staging copy.
- Implement SQL transaction idempotency and reconcilable audit journal.
- Deploy new readers behind disabled feature flags before a global
  read/write cutover.

## Production safety statement

This stage only adds files under `deployment/` plus an independent
test workflow. It neither changes the existing production game ZIP
nor runs a write query against Supabase.
