"""Lossless PostgreSQL NUMERIC(integer) text -> sparse V2 migration helper.

Stand-alone pure Python module. Never connects to production, never writes to
a database. Validates integer semantics before converting. Large 131072-digit
NUMERIC values are chunked without constructing one Python int or JS BigInt.

Important: a DB numeric may serialize as 1.23e+9, 1000.000 or -1000.
Only exact INTEGERS are accepted for cash, stock and quantities.
A versioned shadow field contains S1:<signed int coefficient>@<exp>,...
This is compatible with the experimental SparseExact parser, subject to
its 2048-term limit.

No claim of production readiness: source-to-shadow integrity needs to be
checked in a restored staging database and under concurrent writes.
"""
import re
from sparse_exact_v1 import SparseExact as S

MAX_LEGACY_DIGITS = 131072
CHUNK_DIGITS = 900
_NUMBER = re.compile(r'([+-]?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?\Z')


def numeric_text_to_sparse(text: str) -> S:
    if not isinstance(text,str) or len(text)>MAX_LEGACY_DIGITS+32:
        raise ValueError('Oversized legacy NUMERIC')
    match = _NUMBER.fullmatch(text)
    if not match:
        raise ValueError('Invalid legacy NUMERIC text')
    sign,whole,frac,exponent_text=match.groups()
    fractional=frac or ''
    # PostgreSQL may choose to print scientific or fixed notation, but the
    # result must be an integer. Never call int() on its entire digit string.
    exponent = int(exponent_text or '0') - len(fractional)
    digits=(whole+fractional).lstrip('0')
    if not digits:
        return S.parse('0')
    if len(digits)>MAX_LEGACY_DIGITS:
        raise ValueError('Oversized legacy NUMERIC mantissa')
    if exponent<0:
        needed=-exponent
        if needed>len(digits) or digits[-needed:]!='0'*needed:
            raise ValueError('Legacy value is not an integer')
        digits=digits[:-needed]
        exponent=0
        if not digits:
            return S.parse('0')
    # Prevent a 100-digit exponent appearing in a stored NUMERIC export from
    # consuming unbounded resources. This helper only accepts physical
    # PostgreSQL-NUMERIC-range numbers, not already-upgraded giant values.
    if len(digits)+exponent>MAX_LEGACY_DIGITS:
        raise ValueError('Legacy value exceeds PostgreSQL NUMERIC capacity')
    mult=-1 if sign=='-' else 1
    parts=[]
    for end in range(len(digits),0,-CHUNK_DIGITS):
        start=max(0,end-CHUNK_DIGITS)
        coefficient=int(digits[start:end])*mult
        if coefficient:
            parts.append((exponent+len(digits)-end,coefficient))
    return S.make(parts)


def sparse_integer_from_legacy_column(value) -> str:
    """For db adapters: preserve the actual DB numeric string representation.

    Never pass the value via float. If a driver returned a Decimal, str()
    preserves its decimal digits; the caller must verify source SQL casts.
    """
    return numeric_text_to_sparse(str(value)).serialize()
