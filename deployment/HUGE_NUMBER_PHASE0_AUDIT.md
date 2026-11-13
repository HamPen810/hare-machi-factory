# Huge-number cutover: Phase 0 safety audit
Date: 2026-11-13
Status: READ-ONLY AUDIT. No DB writes, no Render production bundle edits.

## Verified database facts
- Supabase project: hare-machi-factory (PostgreSQL 17, schema `hare_factory`)
- 41 game application tables.
- `NUMERIC` economic fields exist in `factories.cash`, `stock.quantity`,
  `listings.quantity/price`, `orders.quantity/price`,
  `sales.sold_quantity/unit_price/unit_cost`, `bank_accounts.*`,
  `bank_contracts.*`, `market_ticks.*`, `market_history.*`,
  `factory_totals.*`, `auto_totals.quantity`, `rare_collection.quantity`,
  `admin_fund_transfers.*` and related records.
- SQL functions `hare_factory.badd`, `bsub` and `bge` accept NUMERIC
  arguments; they must not silently operate on V2 TEXT fields.
- Estimated row counts from PostgreSQL planner statistics:
  `actions` ~246k; `market_ticks` ~240k; `sales` ~32k;
  `market_history` ~13k. These are estimates, not audited exact counts.
- Supabase branches: none. NO isolated staging environment is confirmed.
- A verified, restorable production backup is NOT yet confirmed.
- Existing `deployment/huge_number_v2.py` has 40 significant-digit
  approximations. It is NOT safe as authoritative inventory/cash ledger.
- Current Render instances use the same production database. All writers
  including periodic settlement, admin operations, and auxiliary inventory
  workers must be V2 compatible before a cutover.

## Critical safety rules
1. Production NUMERIC remains authoritative until a real restore drill,
   authoritative-latest backfill, and concurrent transaction tests pass.
2. Never overwrite or drop existing economic columns during early stages.
3. No dual authoritative writers. A single transaction determines the
   authoritative version and cash/stock updates together.
4. Every purchase, seller credit, refund, grant, tax and settlement must
   remain idempotent and auditable.
5. Do not use a finite-precision mantissa for quantities or money without
   a formally defined rounding policy and item-conservation proof.
6. Giant numbers cannot be represented by Python int, JavaScript BigInt,
   or Postgres NUMERIC by expanding digits; work on a canonical compact
   representation.
7. There is never a truly infinite numerical range on finite hardware.
   Bound input length, exponent length, time and memory for abuse resistance,
   but ensure limits are much higher than gameplay needs and report them.

## Recommended storage and arithmetic
- Authoritative fields use versioned compact TEXT/JSONB representations,
  preserving sign, coefficient, exponent and exactness metadata.
- EXACT mode keeps complete integer value; support sparse terms or
  ledger-based representation for `10^(large)+1`, without rounding away
  the 1. Before shipping, mathematically verify canonical add/subtract.
- APPROX mode is for presentation/analytics only unless explicit economic
  rules have been approved and tested.
- Canonical numeric library must cover parse, serialize, compare, add, sub,
  mul, floor division, tax rounding and overflow checks in both Python
  and JS display. No floating-point intermediate in monetary paths.
- For performance, avoid scanning or reserializing full market history on
  every player action. Separate real-time balances from historic aggregates.

## Ordered gates
G0. Backup and actual restoration tested on staging DB; read-only
    production inventory completed.
G1. Canonical encoding and arithmetic property tests, including negative,
    zero, cancellation, huge exponents, one-unit differences.
G2. All economic call sites inventoried: admin, bank, market, settlement,
    rare drops, manufacturing, upgrades, audit/history.
G3. Shadow schema added in staging ONLY, with backfill and exact comparison.
G4. Concurrent and replayed-transaction tests prove no duplication/loss.
G5. Deploy V2 readers to all Render nodes with feature flags OFF.
G6. Short global write-freeze; consistency checkpoint; atomic writer switch.
G7. Monitor and rehearse rollback using V2-compatible code and event log.

## Forbidden until G0-G4 pass
- Change production `cash`, `quantity`, `price` types
- Call `apply_migration` on the production project
- Turn on V2 writes or migrate player balances
- Add an untested automatic rollback that converts a post-cutover
  giant number back into NUMERIC

## Next decision
Confirm a separate *restored* staging database and backup plan. A Supabase
development branch may incur additional charges and may not contain production
data; do not assume it is a backup or request its creation automatically.
