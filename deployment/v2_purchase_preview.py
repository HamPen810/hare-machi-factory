"""Non-binding V2 purchase arithmetic preview, using actual authenticated balance.

No database writes, no order insertion, no settlement. Exact sparse arithmetic
handles 1e1000000000 without expanding digits or converting through float.
The preview is not an authoritative quote, market order or buying permission.
"""
from sparse_exact_v1 import SparseExact as S
from sparse_exact_division import mul_ratio_floor
from v2_balance_read import snapshot

_MAX_INPUT_BYTES = 12000
_VALID_KEYS = frozenset(("product", "quantity", "unit_price", "fee_bps"))


def purchase_preview(db, player, payload):
    if not isinstance(payload, dict) or set(payload) - _VALID_KEYS:
        raise ValueError("Invalid V2 purchase preview payload")
    product = payload.get("product")
    quantity_raw = payload.get("quantity")
    unit_price_raw = payload.get("unit_price")
    fee_bps = payload.get("fee_bps", 0)

    if not isinstance(product, str) or not 1 <= len(product) <= 80:
        raise ValueError("Invalid product")
    if not isinstance(quantity_raw, str) or not 1 <= len(quantity_raw) <= _MAX_INPUT_BYTES:
        raise ValueError("Quantity must be a decimal/scientific string")
    if not isinstance(unit_price_raw, str) or not 1 <= len(unit_price_raw) <= _MAX_INPUT_BYTES:
        raise ValueError("Unit price must be a decimal/scientific string")
    if type(fee_bps) is not int or not 0 <= fee_bps <= 10000:
        raise ValueError("Fee rate must be an integer from 0 to 10000")

    quantity = S.parse(quantity_raw)
    price = S.parse(unit_price_raw)
    if quantity.sign() <= 0 or price.sign() <= 0:
        raise ValueError("Quantity and unit price must be positive")

    state = snapshot(db, player)
    current_cash = S.deserialize(state["cash"])
    selected = next((item for item in state["stock"] if item["product"] == product), None)
    if selected is None:
        raise ValueError("Product does not exist in authenticated player's stock")

    current_stock = S.deserialize(selected["quantity"])
    gross = quantity * price
    fee = mul_ratio_floor(gross, fee_bps)
    # Preview only: a fee-inclusive buyer debit is an illustrative model.
    # Actual market fees, taxes and selling rules may differ.
    buyer_debit = gross + fee
    future_cash = current_cash - buyer_debit
    future_stock = current_stock + quantity

    return {
        "mode": "simulation_only",
        "authoritative": False,
        "order_placed": False,
        "transaction_saved": False,
        "fee_model": "illustrative_basis_points",
        "format": "S1",
        "product": product,
        "quantity": quantity.serialize(),
        "unit_price": price.serialize(),
        "gross": gross.serialize(),
        "illustrative_fee": fee.serialize(),
        "illustrative_debit": buyer_debit.serialize(),
        "current_cash": current_cash.serialize(),
        "current_stock": current_stock.serialize(),
        "cash_after_preview": future_cash.serialize(),
        "stock_after_preview": future_stock.serialize(),
    }
