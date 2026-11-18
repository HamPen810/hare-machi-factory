"""Regression tests: exact balances over 7600 digits, no value loss or mutation."""
import sqlite3
import unittest
from v2_balance_read import snapshot
from sparse_exact_v1 import SparseExact as S


class V2ReadProjectionTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
            CREATE TABLE factories(player TEXT PRIMARY KEY,cash TEXT NOT NULL);
            CREATE TABLE stock(player TEXT,product TEXT,quantity TEXT,work TEXT,
                               PRIMARY KEY(player,product));
        """)

    def tearDown(self):
        self.db.close()

    def test_only_authenticated_player_own_data(self):
        self.db.execute("INSERT INTO factories VALUES(?,?)",("a","1.25e7600"))
        self.db.execute("INSERT INTO factories VALUES(?,?)",("b","999999"))
        self.db.execute("INSERT INTO stock VALUES(?,?,?,?)",("a","white","1e7000","5"))
        self.db.execute("INSERT INTO stock VALUES(?,?,?,?)",("b","white","123","456"))
        response=snapshot(self.db,"a")
        self.assertEqual(response["mode"],"read-only")
        self.assertEqual(response["authoritative"],"legacy_numeric")
        self.assertEqual(S.deserialize(response["cash"]).compare(S.parse("1.25e7600")),0)
        self.assertEqual(response["stock"][0]["quantity"],"S1:1@7000")
        self.assertEqual(response["stock"][0]["work"],"S1:5@0")
        self.assertNotIn("999999",str(response))
        self.assertEqual(self.db.execute("SELECT cash FROM factories WHERE player='a'").fetchone()[0],"1.25e7600")

    def test_negative_balance_and_zero_stock(self):
        self.db.execute("INSERT INTO factories VALUES('a','-999e5000')")
        self.db.execute("INSERT INTO stock VALUES('a','sea','0','0')")
        data=snapshot(self.db,"a")
        self.assertEqual(S.deserialize(data["cash"]).compare(S.parse("-999e5000")),0)
        self.assertEqual(data["stock"][0]["quantity"],"S1:")

    def test_strict_fraction_rejected(self):
        self.db.execute("INSERT INTO factories VALUES('a','1.5')")
        with self.assertRaises(ValueError):
            snapshot(self.db,"a")

    def test_uninitialized_and_invalid_identity_rejected(self):
        with self.assertRaises(ValueError):
            snapshot(self.db,"missing")
        with self.assertRaises(ValueError):
            snapshot(self.db,"")


if __name__=="__main__":
    unittest.main()
