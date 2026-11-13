# Huge number migration — Phase 1 exact-arithmetic checkpoint

**Status:** Experimental isolated prototype. **No changes to production DB data,
API formats, active market settlement, or player balances.**

## Completed and verified

- `deployment/sparse_exact_v1.py`: representation of an integer as signed
  base-10 power terms `coefficient × 10^exponent`, with sparse storage.
- Supports decimal and scientific input (including e.g. `1.25e7600`), provided
  the resulting quantity is an integer.
- Exact addition, subtraction and multiplication without floating-point
  rounding; exact sign, zero, and less/equal/greater comparisons by decimal
  carry even across huge exponent gaps.
- The representation of `10^1000000000 + 1` is compact and does not lose
  the added 1. This demonstrates preservation of tiny increments, unlike the
  approximate `huge_number_v2.py` prototype.
- Automated unit tests include negative balances, big exponents, seller/buyer
  conservation identities, roundtrip serialization, 350 randomized basic
  arithmetic tests and 500 randomized exact comparisons. Test workflow:
  `.github/workflows/test-sparse-exact-v1.yml`.

## Limits and blockers

- This is **not yet a complete production ledger**. Representations may be
  mathematically equivalent without being byte-identical. `safe_equal`
  checks structural equality only. Use `compare(other) == 0` for numeric
  equality.
- Repeated operations can grow the number of terms, which is currently
  bounded at 2048. Coefficient digits and incoming exponent text also have
  resource-safety limits.
- Integer floor division, tax rounding, allocating demand across multiple
  listings, serialization from all existing schema data, multi-row atomicity,
  idempotency, and live UI conversion are **not implemented** here.
- Neither the additive trade-conservation identity test nor the random tests
  establish database transaction atomicity. Concurrent buyers, market
  settlements and refunds remain to be tested on an isolated database.
- PostgreSQL TEXT cannot store mathematical infinity; there will always be
  practical storage/memory/time limits.

## Still required before production cutover

1. Verify a restorable full production backup, with an isolated staging
   database. No staging branch exists as of the phase-0 audit.
2. Develop a versioned authoritative TEXT encoding, canonical consistency
   checker, operation budgets, floor division / remainder / tax rules and
   exact numeric ordering in the database transaction boundary.
3. Create shadow columns on the **staging** DB and run backfill; check every
   row and support in-flight updates.
4. Simulate concurrent trade, negative cash, stale market quotes, repayments,
   rare items, automatic manufacturing, duplicate request IDs and settlement.
5. Publish V2-aware code to all Render nodes with writers disabled, then
   coordinate one authoritative switch during a controlled write freeze.

Do not migrate the production database or raise its physical NUMERIC cap
based solely on this Phase-1 prototype.
