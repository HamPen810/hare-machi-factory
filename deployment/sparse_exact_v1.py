"""Exact sparse base-10 integer arithmetic: experimental, NOT PRODUCTION WIRED.

Example: 10**1_000_000 + 1 is stored as [(1_000_000,1),(0,1)]
and 10**1_000_000 - 1 as [(1_000_000,1),(0,-1)].

Operations add/subtract/multiply are mathematically exact; they never round.
This is a *sparse expression* representation, not a fully normalized decimal
integer. Equivalent expressions with separate carries may have different
serializations. Comparisons and nonnegative stock checks must be separately
verified before authoritative money/inventory use.

No database operations. Number of input terms, coefficient digits and exponent
text length are limited against resource exhaustion; not an infinite system.
"""
from dataclasses import dataclass
from typing import Tuple
import re

MAX_TERMS=2048
MAX_COEFF_DIGITS=10000
MAX_EXPONENT_TEXT_DIGITS=256
MAX_EXPANSION_DIGITS=20000
_DEC=re.compile(r'([+-]?)(\d+)(?:[eE]([+]?\d+))?\Z')
_TERM=re.compile(r'(-?\d+)@(\d+)\Z')

def _checked_int(s, max_digits):
    digits=s.lstrip('-+')
    if not digits.isascii() or not digits.isdigit() or len(digits)>max_digits:
        raise ValueError('Invalid or oversized integer coefficient/exponent')
    return int(s)

@dataclass(frozen=True)
class SparseExact:
    # Sorted descending (exponent, signed coefficient), unique exponents.
    terms: Tuple[Tuple[int,int], ...]

    def __post_init__(self):
        previous=None
        for exp,coeff in self.terms:
            if type(exp) is not int or type(coeff) is not int or exp<0 or coeff==0:
                raise ValueError('Invalid sparse term')
            if previous is not None and previous<=exp:
                raise ValueError('Sparse terms must be sorted in descending exponent order')
            if len(str(abs(coeff)))>MAX_COEFF_DIGITS:
                raise ValueError('Coefficient too large for safe arithmetic')
            previous=exp
        if len(self.terms)>MAX_TERMS:
            raise ValueError('Too many sparse terms')

    @classmethod
    def make(cls, terms):
        totals={}
        for exp,coeff in terms:
            if type(exp) is not int or type(coeff) is not int or exp<0:
                raise ValueError('Invalid sparse term')
            totals[exp]=totals.get(exp,0)+coeff
            if len(totals)>MAX_TERMS:
                raise ValueError('Too many sparse terms')
            if totals[exp] and len(str(abs(totals[exp])))>MAX_COEFF_DIGITS:
                raise ValueError('Coefficient too large')
        return cls(tuple(sorted(((e,c) for e,c in totals.items() if c),reverse=True)))

    @classmethod
    def parse(cls,text):
        """Only nonnegative integer exponents; no float arithmetic or expansion."""
        if not isinstance(text,str) or len(text)>MAX_COEFF_DIGITS+MAX_EXPONENT_TEXT_DIGITS+5:
            raise ValueError('Input too long')
        match=_DEC.fullmatch(text)
        if not match:
            raise ValueError('Enter a nonnegative integer in decimal or scientific notation')
        sign,digits,exponent=match.groups()
        coeff=_checked_int(('-' if sign=='-' else '')+digits,MAX_COEFF_DIGITS)
        exp=_checked_int(exponent or '0',MAX_EXPONENT_TEXT_DIGITS)
        return cls.make([(exp,coeff)])

    def serialize(self):
        """Canonical-by-term text; accepts exact negative coefficients."""
        return 'S1:'+','.join(str(coeff)+'@'+str(exp) for exp,coeff in self.terms)

    @classmethod
    def deserialize(cls,text):
        if not isinstance(text,str) or not text.startswith('S1:'):
            raise ValueError('Invalid sparse-number serialization')
        value=text[3:]
        if not value:
            return cls(())
        fields=value.split(',')
        if len(fields)>MAX_TERMS:
            raise ValueError('Too many sparse terms')
        terms=[]
        for field in fields:
            match=_TERM.fullmatch(field)
            if not match:
                raise ValueError('Bad sparse term')
            coeff=_checked_int(match.group(1),MAX_COEFF_DIGITS)
            exp=_checked_int(match.group(2),MAX_EXPONENT_TEXT_DIGITS)
            terms.append((exp,coeff))
        return cls(tuple(terms))

    def __neg__(self):
        return SparseExact.make((e,-c) for e,c in self.terms)

    def __add__(self,other):
        if not isinstance(other,SparseExact):
            return NotImplemented
        return SparseExact.make((*self.terms,*other.terms))

    def __sub__(self,other):
        if not isinstance(other,SparseExact):
            return NotImplemented
        return self + -other

    def __mul__(self,other):
        if not isinstance(other,SparseExact):
            return NotImplemented
        if len(self.terms)*len(other.terms)>MAX_TERMS:
            raise ValueError('Too many multiplication terms')
        return SparseExact.make(
            (a_exp+b_exp,a_coeff*b_coeff)
            for a_exp,a_coeff in self.terms for b_exp,b_coeff in other.terms)

    def expand_for_test(self,limit=MAX_EXPANSION_DIGITS):
        """Only for tests and small exact values, never for huge exponents."""
        if self.terms and self.terms[0][0]+len(str(abs(self.terms[0][1])))>limit:
            raise ValueError('Exact value too large to expand')
        return sum(coeff*10**exp for exp,coeff in self.terms)

    def safe_equal(self,other):
        """Sufficient canonical-by-term equality (not complete numeric equality)."""
        return isinstance(other,SparseExact) and self.terms==other.terms

    def sign(self):
        """Exact sign via decimal carry across sparse exponents.

        For each gap, floor-divide the lower signed carry by 10**gap.
        Remainders are nonnegative; only whether any remainder survives
        is needed for final sign when the top carry is exactly zero.
        Large gaps never require constructing the full power of ten.
        """
        if not self.terms:
            return 0
        ordered=iter(reversed(self.terms))
        exponent,carry=next(ordered)
        nonzero_remainder=False
        for next_exp,coeff in ordered:
            gap=next_exp-exponent
            if gap>len(str(abs(carry))):
                quotient=-1 if carry<0 else 0
                remainder_exists=carry!=0
            else:
                quotient,remainder=divmod(carry,10**gap)
                remainder_exists=remainder!=0
            nonzero_remainder |= remainder_exists
            carry=quotient+coeff
            exponent=next_exp
        return (carry>0)-(carry<0) if carry else int(nonzero_remainder)

    def compare(self,other):
        """Exact signed comparison, even for astronomical exponents."""
        if not isinstance(other,SparseExact):
            raise TypeError('Can compare only exact sparse values')
        return (self-other).sign()

    def is_zero(self):
        return self.sign()==0

    def is_syntactic_zero(self):
        """Fast sufficient check for cancellation after term merging."""
        return not self.terms
