# Huge Number V2: safe introduction plan (NOT ACTIVE)

This repository includes an **experimental**, independently tested exponent engine in
\`deployment/huge_number_v2.py\`. It is not imported by \`app/server.py\` or live
market / bank modules. Committing these files does not change any player balance,
inventory, listings, or database schema.

## Current cap
- Postgres \`NUMERIC\`: up to 131072 decimal digits to the left of the decimal.
- Live \`hare_factory\` money and quantity columns still use \`NUMERIC\`.
- Increasing the JavaScript or Python parsing digit limit cannot surpass
  PostgreSQL's physical type restriction.

## Future representation
- Ordinary exact values: \`E:<integer>\` or \`E:<coefficient>e<exponent>\`.
- Astronomical values: \`X:<signed 40-digit coefficient>e<exponent>\`.
- The exponent is an arbitrary-length signed decimal *string*, not a float.
- \`1e1000000000\` is a compact number of bytes instead of a billion-digit
  expanded string.
- There is no mathematically unlimited storage: memory and PostgreSQL TEXT
  field size still apply.

## Safety blocker before enabling trading
Finite precision is **not** safe as a source of truth for the exact number of
individual items or transaction balances. For example,
\`1e1000000 + 1 == 1e1000000\` at 40 significant digits. Using this arithmetic
without an accounting policy permits item disappearance, apparent free
purchases, or double spending.

Resolve this with one of:
1. A separate append-only exact transaction ledger with identity and
   idempotency keys, proving no item creation across market trade.
2. A game-rule change that explicitly makes quantities approximately divisible
   in large denominations; document and test the rounding semantics.

**Do not** silently activate this 40-digit engine for inventory accounting.

## Migration (after verified backup, on a restored staging database)
1. Capture full backup and perform a restore to a separate staging project.
2. Inventory all monetary and quantity NUMERIC columns, relevant CHECKs and
   references (factories, stock, listings, orders, sales, bank_accounts,
   bank_contracts, market_ticks, market_history, administrative funds).
3. Add nullable \`*_v2 TEXT\` shadow columns without dropping old NUMERIC values.
4. Dual-read and backfill exact values from the old NUMERIC columns; compare
   source and target row counts and exact amounts. Identify in-flight writes.
5. Test transaction correctness across purchase, sale, refund, shipment,
   creation, rare items, bank, debts, taxes, and admins. Simulate concurrent
   purchases and retry the same request id to assert idempotency.
6. Deploy V2-aware code to all three Render services but leave V2 read/write
   flags **disabled**, ensuring all nodes have compatible serializers.
7. In a short write freeze: drain jobs and market settlement; apply final
   delta; checkpoint balances and inventory; atomically switch the
   authoritative format and activate new writers together.
8. Continue reconciliation and monitor slow queries / invalid conversions.
9. Preserve the legacy columns and full event log for recovery. Rollback of
   post-cutover giant values requires a V2-capable rollback version; never
   point the old NUMERIC-only app at V2-only data.

### Out-of-scope for current commit
- No schema migration has been executed.
- No production market or admin input cap has been increased.
- No player balances or inventories have been changed.
- No new numeric format is currently supported by the live API.

Test locally: \`cd deployment && python -m unittest -v test_huge_number_v2.py\`.
