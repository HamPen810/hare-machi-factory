"""Experimental exponent-number engine for Hare Machi Factory.

Not wired to production yet. Does not migrate or mutate databases.

Two representations:
  E:<signed decimal integer>           fully exact
  X:<signed 40-digit coefficient>e<signed exponent>
                                      approximate (40 significant digits)

Numbers are coefficient * 10**exponent. Exponents are Python arbitrary
precision integers, so e1000000000 works without ever expanding the integer.
40-digit arithmetic is designed for game-scale approximations, NOT for exact
inventory/financial settlement. Such use requires a separately audited ledger
and explicit tolerance policy.
"""
from dataclasses import dataclass
import re

PRECISION = 40
EXACT_DIGIT_THRESHOLD = 10000
_DECIMAL = re.compile(r'([+-]?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?\Z')
_WIRE = re.compile(r'(E:[+-]?\d+|X:[+-]?\d+e[+-]?\d+)\Z')


def _round_div(value, divisor):
    """Round half-to-even, signed."""
    sign = -1 if value < 0 else 1
    v = abs(value)
    q, r = divmod(v, divisor)
    if 2 * r > divisor or (2 * r == divisor and q % 2):
        q += 1
    return sign * q


@dataclass(frozen=True)
class HugeNumber:
    coefficient: int
    exponent: int = 0
    exact: bool = True

    def __post_init__(self):
        if type(self.coefficient) is not int or type(self.exponent) is not int:
            raise TypeError("Exact Python integers required.")
        if not self.coefficient:
            object.__setattr__(self, 'exponent', 0)

    @staticmethod
    def _normalized(coefficient, exponent, exact):
        if coefficient == 0:
            return HugeNumber(0, 0, exact)
        if exact:
            while coefficient % 10 == 0:
                coefficient //= 10
                exponent += 1
            return HugeNumber(coefficient, exponent, True)
        digits = len(str(abs(coefficient)))
        if digits > PRECISION:
            drop = digits - PRECISION
            coefficient = _round_div(coefficient, 10 ** drop)
            exponent += drop
            if len(str(abs(coefficient))) > PRECISION:
                coefficient //= 10
                exponent += 1
        while coefficient % 10 == 0:
            coefficient //= 10
            exponent += 1
        return HugeNumber(coefficient, exponent, False)

    @classmethod
    def parse(cls, source):
        """Never expand a positive exponent into a long string."""
        text = str(source).strip()
        if text.startswith('E:'):
            return cls.parse(text[2:])
        if text.startswith('X:'):
            obj = cls.parse(text[2:])
            return cls._normalized(obj.coefficient, obj.exponent, False)
        match = _DECIMAL.fullmatch(text)
        if not match:
            raise ValueError("Invalid decimal/scientific number")
        sign, whole, fraction, exponent = match.groups()
        coeff = int((whole + (fraction or '')).lstrip('0') or '0')
        if sign == '-':
            coeff = -coeff
        power = int(exponent or '0') - len(fraction or '')
        if not coeff:
            return cls(0)
        magnitude = len(str(abs(coeff))) + power
        exact = abs(magnitude) <= EXACT_DIGIT_THRESHOLD and len(str(abs(coeff))) <= EXACT_DIGIT_THRESHOLD
        return cls._normalized(coeff, power, exact)

    def wire(self):
        prefix = 'E' if self.exact else 'X'
        return f'{prefix}:{self.coefficient}e{self.exponent}' if not self.exact else (
            f'E:{self.coefficient}' if not self.exponent else f'E:{self.coefficient}e{self.exponent}')

    def canonical(self):
        if not self.coefficient:
            return '0'
        c = str(abs(self.coefficient))
        lead = '-' if self.coefficient < 0 else ''
        mantissa = c[0] + ('.' + c[1:] if len(c) > 1 else '')
        return f'{lead}{mantissa}e{self.exponent + len(c) - 1}'

    def sign(self):
        return (self.coefficient > 0) - (self.coefficient < 0)

    def magnitude(self):
        if not self.coefficient:
            return -10**100
        return self.exponent + len(str(abs(self.coefficient))) - 1

    def _approx(self):
        return self._normalized(self.coefficient, self.exponent, False)

    def _maybe_exact(self, result):
        if result.exact and result.magnitude() >= EXACT_DIGIT_THRESHOLD:
            return result._approx()
        return result

    def __neg__(self):
        return HugeNumber(-self.coefficient, self.exponent, self.exact)

    def __add__(self, other):
        if not isinstance(other, HugeNumber):
            return NotImplemented
        if self.coefficient == 0:
            return other
        if other.coefficient == 0:
            return self
        exact = self.exact and other.exact
        if exact:
            delta = abs(self.exponent - other.exponent)
            if delta < EXACT_DIGIT_THRESHOLD:
                k = min(self.exponent, other.exponent)
                return self._maybe_exact(self._normalized(
                    self.coefficient * 10**(self.exponent-k)
                    + other.coefficient * 10**(other.exponent-k), k, True))
        # Alignment is bounded to precision. Tiny terms below our precision
        # may be dropped, and cancellation may lose significant digits.
        a, b = self._approx(), other._approx()
        big = max(a.magnitude(), b.magnitude())
        if big - min(a.magnitude(), b.magnitude()) >= PRECISION + 2:
            return a if a.magnitude() > b.magnitude() else b
        baseline = min(a.exponent, b.exponent)
        if max(a.exponent, b.exponent) - baseline > PRECISION + 2:
            baseline = max(a.exponent, b.exponent) - (PRECISION + 2)
        def align(number):
            shift = number.exponent - baseline
            return number.coefficient * 10**shift if shift >= 0 else _round_div(number.coefficient, 10**(-shift))
        return self._normalized(align(a) + align(b), baseline, False)

    def __sub__(self, other):
        return self + (-other)

    def __mul__(self, other):
        if not isinstance(other, HugeNumber):
            return NotImplemented
        return self._maybe_exact(self._normalized(
            self.coefficient * other.coefficient,
            self.exponent + other.exponent,
            self.exact and other.exact))

    def compare(self, other):
        if not isinstance(other, HugeNumber):
            raise TypeError("Comparison requires HugeNumber")
        if self.sign() != other.sign():
            return (self.sign() > other.sign()) - (self.sign() < other.sign())
        if not self.coefficient:
            return 0
        sign = self.sign()
        m, n = self.magnitude(), other.magnitude()
        if m != n:
            return ((m > n) - (m < n)) * sign
        # At matching magnitude compare at bounded precision; exact mode
        # can compare all digits without expanding their giant exponent.
        a = str(abs(self.coefficient))
        b = str(abs(other.coefficient))
        width = max(len(a), len(b)) if self.exact and other.exact else PRECISION
        ax, bx = (a+'0'*max(0,width-len(a)))[:width], (b+'0'*max(0,width-len(b)))[:width]
        return ((ax > bx) - (ax < bx)) * sign

    def is_negative(self):
        return self.coefficient < 0
