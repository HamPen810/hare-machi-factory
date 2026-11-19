"""Stage-only V2 server-owned pricing parity for the actual game.

No user-supplied upgrade costs may be authoritative. Tier is a trusted,
row-locked database value. Fail closed if exact exponentiation would exceed
the current sparse exact coefficient budget; never round into a float.
"""
from sparse_exact_v1 import SparseExact as S

UPGRADE_COSTS=(100,600,3000,15000,75000)
MAX_EXACT_TIER=5000


def upgrade_price(tier):
    if type(tier) is not int or tier < 0:
        raise ValueError("Invalid stored upgrade tier")
    if tier > MAX_EXACT_TIER:
        raise ValueError("Tier exceeds current exact pricing coefficient limit")
    # Matches market.py: UPGRADES[tier] for first five tiers, then
    # UPGRADES[-1]*5**(tier-len(UPGRADES)+1).
    cost=(UPGRADE_COSTS[tier] if tier<len(UPGRADE_COSTS)
          else UPGRADE_COSTS[-1]*pow(5,tier-len(UPGRADE_COSTS)+1))
    return S.make(((0,cost),))
