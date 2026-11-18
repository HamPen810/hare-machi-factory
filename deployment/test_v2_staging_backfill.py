"""PostgreSQL 17 integration tests on disposable local hare_v2_stage_* only."""
import os
import unittest

import psycopg
from psycopg.rows import dict_row
from sparse_exact_v1 import SparseExact
from v2_staging_backfill import (
    verify_stage_dsn, backfill_table, verify_table,
)

DSN=os.environ.get("V2_TEST_STAGE_DSN", "")


class StagingBackfillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DSN:
            raise unittest.SkipTest("No disposable PostgreSQL stage configured")
        verify_stage_dsn(DSN)
        cls.db=psycopg.connect(DSN,autocommit=True,row_factory=dict_row)
        cls.db.execute("CREATE SCHEMA IF NOT EXISTS hare_factory")
        for table in ("factories","stock","action_spend_totals"):
            cls.db.execute(f"DROP TABLE IF EXISTS hare_factory.{table}")
        cls.db.execute(
            "CREATE TABLE hare_factory.factories("
            "player TEXT PRIMARY KEY,cash NUMERIC NOT NULL,cash_v2 TEXT)")
        cls.db.execute(
            "CREATE TABLE hare_factory.stock("
            "player TEXT,product TEXT,quantity NUMERIC,work NUMERIC,"
            "quantity_v2 TEXT,work_v2 TEXT,PRIMARY KEY(player,product))")
        cls.db.execute(
            "CREATE TABLE hare_factory.action_spend_totals("
            "player TEXT,kind TEXT,total_spent NUMERIC,total_spent_v2 TEXT,"
            "PRIMARY KEY(player,kind))")
        cls.db.execute(
            "INSERT INTO hare_factory.factories(player,cash) VALUES ('p',%s::numeric),('neg',%s::numeric)",
            ("1.25e7600","-1e4200"))
        cls.db.execute(
            "INSERT INTO hare_factory.stock VALUES ('p','white',%s::numeric,%s::numeric,NULL,NULL)",
            ("3e7000","0"))
        cls.db.execute(
            "INSERT INTO hare_factory.stock VALUES ('p','sea',NULL,NULL,NULL,NULL)")
        cls.db.execute(
            "INSERT INTO hare_factory.action_spend_totals VALUES "
            "('p','upgrade',%s::numeric,NULL)",("2.5e5000",))

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"db"):
            cls.db.close()

    def test_01_legacy_exact_backup_reconciled(self):
        for table,columns,changed,expected in (
            ("factories",("cash",),2,2),
            ("stock",("quantity","work"),1,2),
            ("action_spend_totals",("total_spent",),1,1),
        ):
            self.assertEqual(backfill_table(self.db,table,columns,batch_size=1),changed)
            self.assertEqual(verify_table(self.db,table,columns),expected)
            self.assertEqual(backfill_table(self.db,table,columns),0)
        row=self.db.execute("SELECT cash::text AS source,cash_v2 FROM hare_factory.factories WHERE player='p'").fetchone()
        self.assertEqual(SparseExact.deserialize(row["cash_v2"]).compare(SparseExact.parse("1.25e7600")),0)
        self.assertEqual(row["source"],self.db.execute("SELECT cash::text FROM hare_factory.factories WHERE player='p'").fetchone()["cash"])

    def test_02_tamper_is_detected_without_overwrite(self):
        self.db.execute("UPDATE hare_factory.factories SET cash_v2='S1:9@0' WHERE player='p'")
        with self.assertRaisesRegex(ValueError,"mismatch"):
            verify_table(self.db,"factories",("cash",))
        self.db.execute("UPDATE hare_factory.factories SET cash_v2=NULL WHERE player='p'")
        self.assertEqual(backfill_table(self.db,"factories",("cash",)),1)
        self.assertEqual(verify_table(self.db,"factories",("cash",)),2)

    def test_03_reject_remote_or_live(self):
        for url in (
            "postgresql://example.com/hare_v2_stage_test",
            "postgresql://127.0.0.1/postgres",
            "postgresql://127.0.0.1/hare_factory",
        ):
            with self.assertRaises(RuntimeError):
                verify_stage_dsn(url)


if __name__=="__main__":
    unittest.main()
