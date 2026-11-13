"""Audited-design prototype: exact sparse integer / decimal-power division.

DO NOT IMPORT INTO PRODUCTION YET. No DB/network operations.

The exact quotient of (10**1_000_000 - 1) // 10000 is represented as
10**999996 - 1; the remainder is 9999. Neither operand is expanded.

Dividing an arbitrary large sparse expression by a non-decimal divisor
(e.g. 10**1_000_000 // 3) can produce a quotient with a million digits of
repeating digits. This module deliberately refuses that operation rather
than silently rounding or allocating unbounded memory.

The economic tax primitive multiplies the full exact integer before doing
an exact floor/ceil division by 10000. It preserves signs and remainders.
"""
from sparse_exact_v1 import SparseExact as S

MAX_DECIMAL_DIVISOR_EXPONENT = 128
MAX_SMALL_DIVISOR = 10**9


def divmod_power_of_ten(value: S, places: int):
    """Exact Python-style floor quotient/remainder for positive 10**places.

    The remainder is always in [0, 10**places), even if value is negative.
    Input integers need not have canonical digit-by-digit representation.
    """
    if not isinstance(value,S):
        raise TypeError('Expected exact sparse value')
    if type(places) is not int or not 0<=places<=MAX_DECIMAL_DIVISOR_EXPONENT:
        raise ValueError('Decimal divisor exponent outside tested range')
    if places==0:
        return value,0
    base=10**places
    high=[]
    low=0
    for exponent,coefficient in value.terms:
        if exponent>=places:
            high.append((exponent-places,coefficient))
        else:
            low += coefficient * 10**exponent
    quotient_low,remainder=divmod(low,base)
    if quotient_low:
        high.append((0,quotient_low))
    quotient=S.make(high)
    return quotient,remainder


def mul_ratio_floor(value: S, numerator: int, denominator: int=10000):
    """Exactly floor(value*numerator/denominator) for power-of-10 denominator.

    Intended for tax basis-point computations; no floating point.
    """
    if type(numerator) is not int or not 0<=numerator<=1000000:
        raise ValueError('Invalid nonnegative rate numerator')
    if type(denominator) is not int or denominator<1:
        raise ValueError('Invalid denominator')
    power=0
    reduced=denominator
    while reduced>1 and reduced%10==0:
        reduced//=10
        power+=1
    if reduced!=1 or power>MAX_DECIMAL_DIVISOR_EXPONENT:
        raise ValueError('Only decimal power divisors supported for huge sums')
    return divmod_power_of_ten(value*S.parse(str(numerator)),power)[0]


def mul_ratio_ceil(value: S, numerator: int, denominator: int=10000):
    """Exactly ceil(value*numerator/denominator), for lending/fees.

    Round toward positive infinity, including negative values.
    """
    if type(numerator) is not int or not 0<=numerator<=1000000:
        raise ValueError('Invalid nonnegative rate numerator')
    if type(denominator) is not int or denominator<1:
        raise ValueError('Invalid denominator')
    power=0
    reduced=denominator
    while reduced>1 and reduced%10==0:
        reduced//=10
        power+=1
    if reduced!=1 or power>MAX_DECIMAL_DIVISOR_EXPONENT:
        raise ValueError('Only decimal power divisors supported for huge sums')
    q,r=divmod_power_of_ten(value*S.parse(str(numerator)),power)
    return q + (S.parse('1') if r else S.parse('0'))


def divmod_bounded(value: S, divisor: int):
    """Fallback generic exact division, refusing huge expanded quotients.

    Use only for small ordinary operands. Huge non-decimal division would
    need a rational or compressed quotient representation, not this API.
    """
    if not isinstance(value,S):
        raise TypeError('Expected exact sparse value')
    if type(divisor) is not int or not 1<=divisor<=MAX_SMALL_DIVISOR:
        raise ValueError('Divisor outside tested range')
    if divisor==1:
        return value,0
    if divisor in (10,100,1000,10000,100000,1000000):
        return divmod_power_of_ten(value,len(str(divisor))-1)
    try:
        number=value.expand_for_test(limit=10000)
    except ValueError as exc:
        raise ValueError('Exact non-decimal quotient would require expansion; not supported') from exc
    q,r=divmod(number,divisor)
    return S.parse(str(q)),r
