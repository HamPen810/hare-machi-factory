"""PostgreSQL 17 real-schema V2 trade integration: synthetic local staging only."""
from concurrent.futures import ThreadPoolExecutor
import os
import unittest
import psycopg

from sparse_exact_v1 import SparseExact as S
from v2_real_schema_staging_trade import (
    create_staging_receipts, settle, sum_cash, sum_stock, _guard,
)

DSN=os.environ.get("V2_REAL_STAGE_DSN", "")


@unittest.skipUnless(DSN,"Requires disposable PostgreSQL 17 CI service")
class RealSchemaStagingTradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=psycopg.connect(DSN,autocommit=True)
        _guard(cls.db)
        cls.db.execute("CREATE SCHEMA IF NOT EXISTS hare_factory")
        cls.db.execute("CREATE TABLE IF NOT EXISTS hare_factory.factories "
                       "(player TEXT PRIMARY KEY,cash NUMERIC NOT NULL,cash_v2 TEXT)")
        cls.db.execute("CREATE TABLE IF NOT EXISTS hare_factory.stock "
                       "(player TEXT,product TEXT,quantity NUMERIC,quantity_v2 TEXT,"
                       "PRIMARY KEY(player,product))")
        create_staging_receipts(cls.db)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"db"):cls.db.close()

    def setUp(self):
        with self.db.transaction():
            self.db.execute("TRUNCATE hare_factory.v2_trade_receipts_stage,"
                            "hare_factory.stock,hare_factory.factories")
            self.db.execute(
                "INSERT INTO hare_factory.factories VALUES "
                "('buyer',100,'S1:100@0'),('seller',1000,'S1:1000@0')")
            self.db.execute(
                "INSERT INTO hare_factory.stock VALUES "
                "('buyer','white',7,'S1:7@0'),"
                "('seller','white',3,'S1:3@1000000000')")

    def fresh(self):
        return psycopg.connect(DSN,autocommit=True)

    def test_01_exact_giant_trade_and_legacy_columns_preserved(self):
        cash_before=sum_cash(self.db)
        stock_before=sum_stock(self.db,'white')
        trade=settle(self.db,"giant-settle-0001","buyer","seller","white",
                     "2e1000000000","3e2000000000",1250)
        self.assertEqual(trade["gross"].compare(S.parse("6e3000000000")),0)
        self.assertEqual(trade["fee"].compare(S.parse("7.5e2999999999")),0)
        self.assertEqual(sum_stock(self.db,"white").compare(stock_before),0)
        self.assertEqual((sum_cash(self.db)+trade["fee"]).compare(cash_before),0)
        cash=self.db.execute(
            "SELECT cash::text,cash_v2 FROM hare_factory.factories WHERE player='buyer'"
        ).fetchone()
        self.assertEqual(cash[0],"100")
        self.assertLess(S.deserialize(cash[1]).sign(),0)
        stocks=self.db.execute(
            "SELECT quantity::text FROM hare_factory.stock WHERE player='seller'"
        ).fetchone()
        self.assertEqual(stocks[0],"3")

    def test_02_simultaneous_same_key_once(self):
        def job(_):
            with self.fresh() as conn:
                return settle(conn,"same-key-00001","buyer","seller","white",
                              "2","6",500)
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(job,range(64)))
        self.assertEqual(sum(not x["replay"] for x in results),1)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_trade_receipts_stage"
        ).fetchone()[0],1)

    def test_03_concurrent_stock_cannot_be_oversold(self):
        with self.db.transaction():
            self.db.execute(
                "UPDATE hare_factory.stock SET quantity_v2='S1:10@0' "
                "WHERE player='seller' AND product='white'")
            for i in range(20):
                self.db.execute("INSERT INTO hare_factory.factories VALUES "
                                "(%s,0,'S1:')",(f"b{i}",))
                self.db.execute("INSERT INTO hare_factory.stock VALUES "
                                "(%s,'white',0,'S1:')",(f"b{i}",))
        prior_stock=sum_stock(self.db,"white")
        prior_cash=sum_cash(self.db)
        def job(i):
            try:
                with self.fresh() as conn:
                    settle(conn,f"stock-competitor-{i:03}","b"+str(i),
                           "seller","white","1","50",500)
                    return True
            except ValueError as e:
                if "Insufficient stock" not in str(e):raise
                return False
        with ThreadPoolExecutor(max_workers=10) as pool:
            flags=list(pool.map(job,range(20)))
        self.assertEqual(sum(flags),10)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_trade_receipts_stage"
        ).fetchone()[0],10)
        self.assertEqual(sum_stock(self.db,"white").compare(prior_stock),0)
        paid=sum((S.deserialize(x[0]) for x in self.db.execute(
            "SELECT fee_v2 FROM hare_factory.v2_trade_receipts_stage")),S.parse("0"))
        self.assertEqual((sum_cash(self.db)+paid).compare(prior_cash),0)

    def test_04_injected_failure_rolls_back_every_table(self):
        before_cash=self.db.execute("SELECT * FROM hare_factory.factories ORDER BY player").fetchall()
        before_stock=self.db.execute("SELECT * FROM hare_factory.stock ORDER BY player").fetchall()
        for fail in ("after_first_cash","before_commit"):
            with self.assertRaisesRegex(RuntimeError,"Injected rollback"):
                settle(self.db,f"rollback-test-{fail}","buyer","seller","white",
                       "1","999",failpoint=fail)
            self.assertEqual(self.db.execute(
                "SELECT * FROM hare_factory.factories ORDER BY player").fetchall(),before_cash)
            self.assertEqual(self.db.execute(
                "SELECT * FROM hare_factory.stock ORDER BY player").fetchall(),before_stock)
            self.assertEqual(self.db.execute(
                "SELECT count(*) FROM hare_factory.v2_trade_receipts_stage").fetchone()[0],0)

    def test_05_same_key_altered_payload_is_rejected(self):
        settle(self.db,"immutability-key-1","buyer","seller","white","1","22")
        with self.assertRaisesRegex(ValueError,"altered payload"):
            settle(self.db,"immutability-key-1","buyer","seller","white","2","22")
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_trade_receipts_stage").fetchone()[0],1)

    def test_06_invalid_quantity_and_remote_prohibited(self):
        for qty in ("0","-10","1.5","Infinity"):
            with self.subTest(qty=qty):
                with self.assertRaises(ValueError):
                    settle(self.db,"invalid-quantity-key","buyer","seller","white",qty,"1")
        with self.assertRaises(RuntimeError):
            prior=os.environ.pop("HARE_V2_LOCAL_STAGING",None)
            try: _guard(self.db)
            finally:
                if prior is not None:os.environ["HARE_V2_LOCAL_STAGING"]=prior


if __name__=="__main__":
    unittest.main()
