"""V2 ledger consistency, rankings and timeline on disposable PostgreSQL 17."""
import os,unittest
import psycopg
from sparse_exact_v1 import SparseExact as S
from v2_real_schema_staging_actions import initialize_stage,action
from v2_real_schema_staging_trade import create_staging_receipts,settle,_guard
from v2_stage_event_ledger import metrics,timeline

DSN=os.environ.get("V2_EVENT_STAGE_DSN","")


def assert_amount(test,actual,expected):
    test.assertEqual(S.deserialize(actual).compare(S.parse(expected)),0)


@unittest.skipUnless(DSN,"Requires disposable PostgreSQL")
class V2LedgerAtomicityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=psycopg.connect(DSN,autocommit=True)
        _guard(cls.db)
        cls.db.execute("CREATE SCHEMA IF NOT EXISTS hare_factory")
        cls.db.execute("""CREATE TABLE hare_factory.factories(
          player TEXT PRIMARY KEY,cash_v2 TEXT NOT NULL,tier INT NOT NULL DEFAULT 1)""")
        cls.db.execute("""CREATE TABLE hare_factory.stock(
          player TEXT,product TEXT,quantity_v2 TEXT NOT NULL,
          PRIMARY KEY(player,product))""")
        cls.db.execute("""CREATE TABLE hare_factory.listings(
          id TEXT PRIMARY KEY,player TEXT,product TEXT,quantity_v2 TEXT,
          price_v2 TEXT,UNIQUE(player,product))""")
        cls.db.execute("""CREATE TABLE hare_factory.factory_totals(
          player TEXT PRIMARY KEY,manufactured_v2 TEXT,purchases_v2 TEXT)""")
        initialize_stage(cls.db)
        create_staging_receipts(cls.db)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"db"):cls.db.close()

    def setUp(self):
        with self.db.transaction():
            for table in (
                "v2_economic_events_stage","v2_operation_registry_stage",
                "v2_action_receipts_stage","v2_trade_receipts_stage",
                "v2_bank_contracts_stage","listings","stock","factory_totals","factories"):
                self.db.execute("TRUNCATE hare_factory."+table)
            self.db.execute("INSERT INTO hare_factory.factories VALUES "
                            "('seller','S1:100@0',1),('buyer','S1:10@0',1)")
            self.db.execute("INSERT INTO hare_factory.stock VALUES "
                            "('seller','white','S1:10@0'),('buyer','white','S1:')")
            self.db.execute("INSERT INTO hare_factory.factory_totals VALUES "
                            "('seller','S1:','S1:'),('buyer','S1:','S1:')")

    def test_ship_upgrades_bank_admin_and_market_ledger_match_balances(self):
        action(self.db,"ledger-manufacture-1","manufacture","seller",
               product="white",quantity="1e1000000000")
        action(self.db,"ledger-upgrade-001","upgrade","seller",cost="20")
        action(self.db,"ledger-grant-0001","admin_grant","buyer",amount="1e1000000000")
        action(self.db,"ledger-shipment-01","ship","seller",
               product="white",quantity="1e1000000000",price="3")
        trade=settle(self.db,"ledger-trade-0001",
                     "buyer","seller","white","2","3",500)
        assert_amount(self,trade["gross"].serialize(),"6")
        leaderboard=metrics(self.db)
        self.assertEqual(leaderboard["revenue_rank"][0]["player"],"seller")
        assert_amount(self,leaderboard["players"]["seller"]["revenue"],"6")
        assert_amount(self,leaderboard["players"]["buyer"]["expenses"],"6")
        assert_amount(self,leaderboard["players"]["seller"]["manufactured"],"1e1000000000")
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_economic_events_stage"
        ).fetchone()[0],6)
        # Staging shipment reservation is a separate stock movement from sale.
        timeline_seller=timeline(self.db,"seller",30)
        self.assertEqual(len(timeline_seller),4)
        self.assertTrue(all(event["player"]=="seller" for event in timeline_seller))
        cash_before=self.db.execute(
            "SELECT cash_v2 FROM hare_factory.factories WHERE player='buyer'"
        ).fetchone()[0]
        settle(self.db,"ledger-trade-0001","buyer","seller","white","2","3",500)
        cash_after=self.db.execute(
            "SELECT cash_v2 FROM hare_factory.factories WHERE player='buyer'"
        ).fetchone()[0]
        self.assertEqual(cash_before,cash_after)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_economic_events_stage"
        ).fetchone()[0],6)

    def test_market_fee_conservation_and_no_float_conversion(self):
        result=settle(self.db,"ledger-trade-0002","buyer","seller","white",
                      "3","1e1000000000",1250)
        ledger=metrics(self.db)
        buyer=S.deserialize(ledger["players"]["buyer"]["cash_change"])
        seller=S.deserialize(ledger["players"]["seller"]["cash_change"])
        self.assertEqual((buyer+seller+result["fee"]).sign(),0)
        self.assertEqual(result["gross"].compare(S.parse("3e1000000000")),0)
        assert_amount(self,ledger["players"]["seller"]["revenue"],"3e1000000000")
        self.assertGreater(S.deserialize(ledger["players"]["buyer"]["expenses"]).sign(),0)

    def test_rollback_leaves_no_ghost_ledger_or_global_id(self):
        for fail in ("after_first_cash","before_commit"):
            with self.assertRaisesRegex(RuntimeError,"Injected rollback"):
                settle(self.db,"ledger-failure-"+fail,
                       "buyer","seller","white","1","4",
                       failpoint=fail)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_economic_events_stage"
        ).fetchone()[0],0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_operation_registry_stage"
        ).fetchone()[0],0)

    def test_negative_admin_cash_delta_preserved(self):
        action(self.db,"ledger-admin-collect-1","admin_collect","buyer",amount="1e1000000000")
        response=metrics(self.db)["players"]["buyer"]
        assert_amount(self,response["cash_change"],"-1e1000000000")
        assert_amount(self,response["expenses"],"1e1000000000")

if __name__=="__main__":
    unittest.main()
