"""Lossless, authenticated read-only V2 projection of legacy balances.

For each legacy NUMERIC, SQL casts directly to TEXT before leaving PostgreSQL.
No float, truncation, economic mutation, or V2 write is permitted here.
"""
from v2_numeric_lossless_backfill import numeric_text_to_sparse


def _encode(value):
    # Pure conversion, never numeric arithmetic through a JS/float path.
    exact = numeric_text_to_sparse(value)
    return exact.serialize()


def snapshot(db, player):
    if not isinstance(player, str) or not player:
        raise ValueError("Invalid authenticated player ID")

    # PostgreSQL NUMERIC::text and SQLite CAST both preserve integer decimal
    # representations; driver never sees a Decimal for these columns.
    row = db.execute(
        "SELECT CAST(cash AS TEXT) AS cash_text FROM factories WHERE player=?",
        (player,),
    ).fetchone()
    if row is None:
        raise ValueError("Factory not initialized")

    items = db.execute(
        "SELECT product, CAST(quantity AS TEXT) AS quantity_text, "
        "CAST(work AS TEXT) AS work_text FROM stock "
        "WHERE player=? ORDER BY product",
        (player,),
    ).fetchall()

    return {
        "format": "S1",
        "mode": "read-only",
        "authoritative": "legacy_numeric",
        "cash": _encode(row["cash_text"]),
        "stock": [
            {
                "product": item["product"],
                "quantity": _encode(item["quantity_text"]),
                "work": _encode(item["work_text"]),
            }
            for item in items
        ],
    }
