"""Property/regression tests for isolated exact sparse integer arithmetic."""
import random
import unittest
from sparse_exact_v1 import SparseExact as S

class SparseExactTests(unittest.TestCase):
    def test_billion_exponent_plus_one_without_expansion(self):
        giant=S.parse('1e1000000000')
        plus=giant+S.parse('1')
        self.assertLess(len(plus.serialize()),48)
        self.assertEqual(plus.serialize(),'S1:1@1000000000,1@0')
        self.assertTrue((plus-giant).safe_equal(S.parse('1')))
        self.assertTrue(((giant-S.parse('1'))+S.parse('1')).safe_equal(giant))
        self.assertTrue((S.parse('0')-giant+giant).is_syntactic_zero())

    def test_full_purchase_seller_balance_conservation_symbolically(self):
        quantity=S.parse('3e1000000000')
        price=S.parse('2e2000000000')
        spend=quantity*price
        self.assertEqual(spend.serialize(),'S1:6@3000000000')
        buyer_before=S.parse('100')
        seller_before=S.parse('17')
        buyer_after=buyer_before-spend
        seller_after=seller_before+spend
        self.assertTrue((buyer_after+seller_after).safe_equal(buyer_before+seller_before))
        self.assertLess(len(buyer_after.serialize()),70)

    def test_decimal_scientific_integer_input(self):
        self.assertEqual(S.parse('1.25e7600').serialize(),'S1:125@7598')
        self.assertEqual(S.parse('2.500e1').serialize(),'S1:2500@-2' if False else 'S1:25@0')
        self.assertEqual(S.parse('1.25e3').expand_for_test(),1250)
        with self.assertRaises(ValueError):S.parse('1.25e0')

    def test_cancellation_and_negative(self):
        one=S.parse('1')
        giant=S.parse('1e1000000')
        self.assertTrue(((giant-one)*one+one-giant).is_syntactic_zero())
        self.assertEqual((S.parse('100')-S.parse('1000')).expand_for_test(),-900)
        self.assertEqual((S.parse('1e4000')*S.parse('3e2500')).serialize(),'S1:3@6500')

    def test_roundtrip_and_rejections(self):
        n=S.parse('2e1000000')-S.parse('7e100')
        self.assertTrue(S.deserialize(n.serialize()).safe_equal(n))
        with self.assertRaises(ValueError):S.parse('1e-3')
        with self.assertRaises(ValueError):S.deserialize('S1:1@0,1@2')
        with self.assertRaises(ValueError):S.deserialize('S1:1@4,1@4')
        with self.assertRaises(ValueError):S.parse('1e'+'9'*300)
        with self.assertRaises(ValueError):S.parse('1.5e0')
        with self.assertRaises(ValueError):S.parse('1e-1000')
        with self.assertRaises(ValueError):S.parse('1e1000000000').expand_for_test()

    def test_differential_small_integer_randomized(self):
        r=random.Random(5831)
        for _ in range(350):
            a=r.randint(-10**60,10**60)
            b=r.randint(-10**60,10**60)
            x=S.parse(str(a))
            y=S.parse(str(b))
            self.assertEqual((x+y).expand_for_test(),a+b)
            self.assertEqual((x-y).expand_for_test(),a-b)
            self.assertEqual((x*y).expand_for_test(),a*b)
            self.assertEqual(S.deserialize(x.serialize()).expand_for_test(),a)

    def test_exact_compare_over_unbounded_decimal_gaps(self):
        huge=S.parse('1e1000000000')
        one=S.parse('1')
        self.assertEqual((huge-one).sign(),1)
        self.assertEqual((one-huge).sign(),-1)
        self.assertEqual((huge+one).compare(huge),1)
        self.assertEqual((huge-one).compare(huge),-1)
        self.assertEqual((huge-one+one).compare(huge),0)
        self.assertTrue((S.make([(1,1),(0,-10)])).is_zero())
        self.assertFalse((huge-one).is_zero())
        self.assertEqual((S.parse('0')-S.parse('1')).sign(),-1)

    def test_compare_randomized_against_python_int(self):
        r=random.Random(1755)
        for _ in range(500):
            terms=[(r.randint(0,100),r.randint(-10**30,10**30)) for _ in range(10)]
            value=sum(coeff*10**exp for exp,coeff in terms)
            n=S.make(terms)
            self.assertEqual(n.sign(),(value>0)-(value<0))
            other=r.randint(-10**50,10**50)
            self.assertEqual(n.compare(S.parse(str(other))),(value>other)-(value<other))

    def test_input_length_and_term_budget(self):
        with self.assertRaises(ValueError):S.parse('1'*10001)
        with self.assertRaises(ValueError):
            S.make((i,1) for i in range(2049))

if __name__=='__main__':
    unittest.main()
