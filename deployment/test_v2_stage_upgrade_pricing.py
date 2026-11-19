"""Exact V2 pricing regression: stage pricing must match deployed game schedule."""
import unittest
from v2_stage_upgrade_pricing import upgrade_price,MAX_EXACT_TIER
from sparse_exact_v1 import SparseExact as S


def legacy_upgrade_cost(tier):
    anchors=[100,600,3000,15000,75000]
    return anchors[tier] if tier<len(anchors) else anchors[-1]*5**(tier-len(anchors)+1)


class V2UpgradePricingTests(unittest.TestCase):
    def test_real_game_price_schedule(self):
        for tier in (0,1,2,3,4,5,6,7,25,100,1000):
            with self.subTest(tier=tier):
                expected=legacy_upgrade_cost(tier)
                self.assertEqual(upgrade_price(tier).compare(S.make([(0,expected)])),0)

    def test_bad_levels_fail_closed(self):
        for tier in (-1,True,None,1.1,MAX_EXACT_TIER+1):
            with self.subTest(tier=tier),self.assertRaises(ValueError):
                upgrade_price(tier)


if __name__=="__main__":
    unittest.main()
