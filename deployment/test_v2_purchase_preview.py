"""Exact and safe V2 simulation tests, no production data."""
import sqlite3
import unittest
from sparse_exact_v1 import SparseExact as S
from v2_purchase_preview import purchase_preview

class PreviewTest(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.execute("CREATE TABLE factories(player TEXT PRIMARY KEY,cash TEXT NOT NULL)")
        self.db.execute("CREATE TABLE stock(player TEXT,product TEXT,quantity TEXT,work TEXT)")
        self.db.execute("INSERT INTO factories VALUES('a','20')")
        self.db.execute("INSERT INTO factories VALUES('b','987654')")
        self.db.execute("INSERT INTO stock VALUES('a','white','3','0')")
        self.db.execute("INSERT INTO stock VALUES('b','white','444','0')")

    def tearDown(self):
        self.db.close()

    def test_huge_exact_cash_and_stock_deltas(self):
        out=purchase_preview(self.db,'a',{
            "product":"white","quantity":"1e1000000000",
            "unit_price":"2e500000000","fee_bps":1250
        })
        self.assertEqual(out["mode"],"simulation_only")
        self.assertFalse(out["authoritative"])
        self.assertFalse(out["order_placed"])
        self.assertEqual(out["gross"],"S1:2@1500000000")
        self.assertEqual(out["illustrative_fee"],"S1:25@1499999998")
        self.assertEqual(S.deserialize(out["stock_after_preview"]).compare(S.parse("1e1000000000")+S.parse("3")),0)
        self.assertEqual(S.deserialize(out["cash_after_preview"]).compare(
            S.parse("20")-S.parse("2e1500000000")-S.parse("2.5e149999999")),0)
        self.assertEqual(self.db.execute("SELECT cash FROM factories WHERE player='a'").fetchone()[0],"20")
        self.assertEqual(self.db.execute("SELECT quantity FROM stock WHERE player='a'").fetchone()[0],"3")
        self.assertNotIn("987654",str(out))

    def test_buyer_overdraft_no_float_and_no_write(self):
        out=purchase_preview(self.db,'a',{
            "product":"white","quantity":"3","unit_price":"10"
        })
        self.assertEqual(out["cash_after_preview"],"S1:-1@1")
        self.assertEqual(out["stock_after_preview"],"S1:6@0")
        self.assertEqual(out["illustrative_fee"],"S1:")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM stock").fetchone()[0],2)

    def test_reject_unsafe_inputs(self):
        valid={"product":"white","quantity":"1","unit_price":"5"}
        cases=[dict(valid,quantity=1),dict(valid,quantity="-1"),
               dict(valid,unit_price="1.1"),dict(valid,unit_price=2.0),
               dict(valid,product="unknown"),dict(valid,fee_bps=True),
               dict(valid,fee_bps=10001),dict(valid,quantity="1"*12001),
               dict(valid, unexpected=1)]
        for payload in cases:
            with self.subTest(payload=str(payload)[:80]):
                with self.assertRaises((TypeError,ValueError)):
                    purchase_preview(self.db,"a",payload)

if __name__=="__main__":
    unittest.main()
