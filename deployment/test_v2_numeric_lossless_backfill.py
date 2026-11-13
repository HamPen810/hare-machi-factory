"""Tests for exact, bounded migration of PostgreSQL NUMERIC to sparse TEXT."""
from decimal import Decimal
import random
import unittest
from sparse_exact_v1 import SparseExact as S
from v2_numeric_lossless_backfill import numeric_text_to_sparse as parse, sparse_integer_from_legacy_column as encode

class LosslessNumericBackfillTests(unittest.TestCase):
    def test_full_physical_numeric_range(self):
        whole='9'*131072
        x=parse(whole)
        self.assertEqual(x.compare(S.make([(131071,9),(0,9)])),1)
        self.assertEqual(len(x.terms),146)
        self.assertEqual(x.sign(),1)
        self.assertEqual(parse('-'+whole).compare(-x),0)
        self.assertEqual(S.deserialize(x.serialize()).compare(x),0)
        self.assertLess(len(x.serialize()),132500)

    def test_exponent_maximum_and_boundary(self):
        x=parse('1e131071')
        self.assertEqual(x.serialize(),'S1:1@131071')
        with self.assertRaisesRegex(ValueError,'exceeds'):
            parse('1e131072')
        self.assertEqual(parse('1.25e7600').compare(S.parse('1.25e7600')),0)

    def test_decimal_integer_and_noninteger(self):
        fixtures={
            '0':0,'-0.0000':0,'1000.000':1000,'1.25e3':1250,
            '-3.000e2':-300,'9.99e2':999,'000000005':5,'1.000000e0':1,
        }
        for text,expected in fixtures.items():
            with self.subTest(text=text):
                self.assertEqual(parse(text).expand_for_test(),expected)
        for value in ('1.21','-0.00001','1e-1','1.001e2',
                      'NaN','Infinity','1_000','1e500000',''):
            with self.subTest(value=value),self.assertRaises(ValueError):
                parse(value)

    def test_source_decimal_no_float_rounding(self):
        original=Decimal('123456789012345678901234567890123456789012345678901234567890')
        got=S.deserialize(encode(original))
        self.assertEqual(got.expand_for_test(),int(original))
        # Float conversion changes digits: ensure Decimal input does not.
        self.assertNotEqual(int(float(original)),int(original))

    def test_randomized_comparison_with_python_int(self):
        rng=random.Random(7319)
        for _ in range(600):
            x=rng.randrange(-(10**180),10**180)
            v=parse(str(x))
            self.assertEqual(v.expand_for_test(),x)
            n=rng.randint(0,15)
            q=parse(str(x)+'e'+str(n))
            self.assertEqual(q.expand_for_test(),x*10**n)

    def test_10000_digit_mantissa_roundtrip(self):
        n='1234567890'*1000
        self.assertEqual(parse(n).compare(S.parse(n)),0)

if __name__=='__main__':
    unittest.main()
