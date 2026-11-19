"""Validate V2 stage prices against actual archived production game source.

This is a real compatibility gate: production's UPGRADES and upgrade_cost()
are extracted from the ZIP as AST. No production services or DBs touched.
"""
import ast
import unittest
from zipfile import ZipFile
from v2_stage_upgrade_pricing import upgrade_price
from sparse_exact_v1 import SparseExact as S


def deployed_prices():
    with ZipFile("hare-machi-render.zip") as z:
        source=z.read("market.py").decode("utf-8")
    tree=ast.parse(source,filename="market.py")
    assignment=next(n for n in tree.body if isinstance(n,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id=="UPGRADES" for t in n.targets))
    constants=ast.literal_eval(assignment.value)
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
            and n.name=="upgrade_cost")
    # The only globals in this trusted archived definition are UPGRADES.
    namespace={"UPGRADES":constants}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),"market.py","exec"),namespace)
    return constants,namespace["upgrade_cost"]


class RealProductionPriceParity(unittest.TestCase):
    def test_real_archived_costs_equal_v2_staging(self):
        anchors,deployed=deployed_prices()
        self.assertEqual(anchors,[100,600,3000,15000,75000])
        for tier in (0,1,2,3,4,5,6,7,10,25,100,500,1000):
            with self.subTest(tier=tier):
                expected=S.make([(0,deployed(tier))])
                self.assertEqual(upgrade_price(tier).compare(expected),0)


if __name__=="__main__":
    unittest.main()
