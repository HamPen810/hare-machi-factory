"""Standalone exact tax/division tests, no production integration."""
import random
import unittest
from sparse_exact_v1 import SparseExact as S
from sparse_exact_division import (
    divmod_power_of_ten, mul_ratio_floor, mul_ratio_ceil, divmod_bounded
)

class SparseExactDivisionTests(unittest.TestCase):
    def test_billion_exponent_minus_one_tax_remains_exact(self):
        n=S.parse('1e1000000000')-S.parse('1')
        q,r=divmod_power_of_ten(n,4)
        self.assertEqual(q.serialize(),'S1:1@999999996,-1@0')
        self.assertEqual(r,9999)
        self.assertEqual((q*S.parse('10000')+S.parse(str(r))).compare(n),0)
        self.assertLess(len(q.serialize()),45)

    def test_tax_can_remain_compact_beyond_numeric(self):
        n=S.parse('1.25e7600')
        tax=mul_ratio_floor(n,1250,10000)
        self.assertEqual(tax.serialize(),'S1:156250@7594')
        # 1.25e7600 * (12.5%) = 1.5625e7599
        self.assertEqual(tax.compare(S.parse('1.5625e7599')),0)
        self.assertLess(len(tax.serialize()),35)

    def test_zero_tax_and_negative_balance(self):
        self.assertTrue(mul_ratio_floor(S.parse('1e1000000000'),0).is_zero())
        neg=S.parse('0')-S.parse('1e1000000000')-S.parse('1')
        q,r=divmod_power_of_ten(neg,4)
        self.assertEqual(r,9999)
        self.assertEqual((q*S.parse('10000')+S.parse(str(r))).compare(neg),0)
        self.assertEqual(mul_ratio_floor(S.parse('-1'),2500).expand_for_test(),-1)
        self.assertEqual(mul_ratio_ceil(S.parse('-1'),2500).expand_for_test(),0)

    def test_buy_sell_conservation_with_tax(self):
        seller=S.parse('1000')
        buyer=S.parse('10')
        goods=S.parse('2e1000000000')
        price=S.parse('3e2000000000')
        charge=goods*price
        withholding=mul_ratio_floor(charge,500,10000)
        balance_seller=seller+charge-withholding
        balance_buyer=buyer-charge
        tax_account=withholding
        self.assertEqual((balance_seller+balance_buyer+tax_account).compare(seller+buyer),0)
        stock_seller=S.parse('3e1000000000')
        stock_buyer=S.parse('7')
        remaining=stock_seller-goods
        received=stock_buyer+goods
        self.assertEqual((remaining+received).compare(stock_seller+stock_buyer),0)
        self.assertEqual(remaining.sign(),1)

    def test_divisor_fail_closed_when_non_decimal_huge(self):
        with self.assertRaisesRegex(ValueError,'not supported'):
            divmod_bounded(S.parse('1e1000000'),3)
        with self.assertRaisesRegex(ValueError,'Only decimal'):
            mul_ratio_floor(S.parse('1e1000000'),1,3)
        with self.assertRaises(ValueError):
            divmod_power_of_ten(S.parse('1'),1000000)
        with self.assertRaises(ValueError):
            divmod_bounded(S.parse('10'),0)
        q,r=divmod_bounded(S.parse('100'),3)
        self.assertEqual(q.expand_for_test(),33)
        self.assertEqual(r,1)

    def test_ordinary_randomized_tax_and_division(self):
        rng=random.Random(902410)
        for _ in range(650):
            x=rng.randint(-10**75,10**75)
            n=S.parse(str(x))
            places=rng.randint(0,20)
            d=10**places
            q,r=divmod_power_of_ten(n,places)
            self.assertEqual(q.expand_for_test(),x//d)
            self.assertEqual(r,x%d)
            self.assertEqual(q.expand_for_test()*d+r,x)
            bps=rng.randint(0,10000)
            floor=mul_ratio_floor(n,bps)
            ceil=mul_ratio_ceil(n,bps)
            self.assertEqual(floor.expand_for_test(),x*bps//10000)
            self.assertEqual(ceil.expand_for_test(),-(-x*bps//10000))
            self.assertIn(ceil.expand_for_test()-floor.expand_for_test(),(0,1))

    def test_sparse_randomized_near_100k_exp(self):
        rng=random.Random(907)
        for _ in range(120):
            terms=[(rng.randint(0,100000),rng.randint(-10**8,10**8)) for _ in range(8)]
            value=S.make(terms)
            q,r=divmod_power_of_ten(value,4)
            self.assertEqual((q*S.parse('10000')+S.parse(str(r))).compare(value),0)
            self.assertTrue(0<=r<10000)

if __name__=='__main__':
    unittest.main()
