"""Read-only regression tests for the experimental huge-number engine."""
import unittest
from huge_number_v2 import HugeNumber as H


class HugeNumberTests(unittest.TestCase):
    def test_massive_exponent_without_expansion(self):
        n = H.parse('1e1000000000')
        self.assertEqual(n.canonical(), '1e1000000000')
        self.assertFalse(n.exact)
        self.assertLess(len(n.wire()), 40)

    def test_exact_small_integers_and_overdraft(self):
        self.assertEqual((H.parse('100')-H.parse('1000')).canonical(), '-9e2')
        self.assertTrue((H.parse('100')-H.parse('1000')).exact)
        self.assertEqual((H.parse('100') + H.parse('1')).canonical(), '1.01e2')

    def test_exact_fractional_scientific(self):
        self.assertEqual(H.parse('2.5e4').canonical(),'2.5e4')
        self.assertEqual(H.parse('2.5e4').wire(), 'E:25e3')

    def test_enormous_product(self):
        self.assertEqual((H.parse('2e1000000')*H.parse('3e500000')).canonical(), '6e1500000')
        self.assertFalse((H.parse('2e1000000')*H.parse('3e500000')).exact)

    def test_sign_and_magnitude_comparison(self):
        self.assertLess(H.parse('-1e999999').compare(H.parse('0')),0)
        self.assertGreater(H.parse('1e1000000').compare(H.parse('9e999999')),0)
        self.assertLess(H.parse('1e1000000').compare(H.parse('2e1000000')),0)

    def test_approximate_small_addition_is_dropped(self):
        n=H.parse('1e1000000')+H.parse('1')
        self.assertEqual(n.canonical(),'1e1000000')
        self.assertFalse(n.exact)

    def test_exact_within_threshold(self):
        n=H.parse('1e7000')*H.parse('2')
        self.assertEqual(n.canonical(),'2e7000')
        self.assertTrue(n.exact)

    def test_exponent_precision(self):
        n=H.parse('1.234567890123456789012345678901234567890e80000')
        self.assertFalse(n.exact)
        self.assertLessEqual(len(str(abs(n.coefficient))),40)

if __name__=='__main__':
    unittest.main()
