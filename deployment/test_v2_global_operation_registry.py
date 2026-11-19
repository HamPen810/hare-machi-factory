"""Global V2 operation-ID registry: cross-feature atomicity tests on local PG17."""
import os,unittest
from concurrent.futures import ThreadPoolExecutor
import psycopg
from v2_real_schema_staging_trade import (
    _guard,create_staging_receipts,settle
)
from v2_real_schema_staging_actions import (
    initialize_stage,action
)
from sparse_exact_v1 import SparseExact as S

DSN=os.environ.get("V2_GLOBAL_STAGE_DSN","")


@unittest.skipUnless(DSN,"Only disposable PostgreSQL stage allowed")
class GlobalOperationRegistryTests(unittest.TestCase):
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
        cls.db.close()

    def setUp(self):
        with self.db.transaction():
            for name in ("v2_operation_registry_stage","v2_action_receipts_stage",
                         "v2_trade_receipts_stage","v2_bank_contracts_stage",
                         "listings","stock","factory_totals","factories"):
                self.db.execute("TRUNCATE hare_factory."+name)
            self.db.execute("INSERT INTO hare_factory.factories VALUES "
                            "('seller','S1:100@0',1),('buyer','S1:10@0',1)")
            self.db.execute("INSERT INTO hare_factory.stock VALUES "
                            "('seller','white','S1:100@0'),('buyer','white','S1:')")
            self.db.execute("INSERT INTO hare_factory.factory_totals VALUES "
                            "('seller','S1:','S1:'),('buyer','S1:','S1:')")

    def test_cross_operation_id_conflict_action_then_trade(self):
        action(self.db,"cross-idempotency-1","manufacture","seller",
               product="white",quantity="2")
        with self.assertRaisesRegex(ValueError,"across different"):
            settle(self.db,"cross-idempotency-1","buyer","seller","white","1","5")
        cash=self.db.execute(
            "SELECT cash_v2 FROM hare_factory.factories WHERE player='seller'"
        ).fetchone()[0]
        self.assertEqual(S.deserialize(cash).compare(S.parse("100")),0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_operation_registry_stage"
        ).fetchone()[0],1)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_trade_receipts_stage"
        ).fetchone()[0],0)

    def test_cross_operation_id_conflict_trade_then_action(self):
        settle(self.db,"cross-idempotency-2","buyer","seller","white","2","5")
        with self.assertRaisesRegex(ValueError,"across different"):
            action(self.db,"cross-idempotency-2","admin_grant","buyer",amount="9")
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_action_receipts_stage"
        ).fetchone()[0],0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_operation_registry_stage"
        ).fetchone()[0],1)

    def test_replay_under_same_scope_returns_saved_result(self):
        x=action(self.db,"same-action-id-01","admin_grant","buyer",amount="2")
        y=action(self.db,"same-action-id-01","admin_grant","buyer",amount="2")
        self.assertEqual(x,y)
        first=settle(self.db,"same-trade-id-01","buyer","seller","white","1","4")
        again=settle(self.db,"same-trade-id-01","buyer","seller","white","1","4")
        self.assertFalse(first["replay"])
        self.assertTrue(again["replay"])
        self.assertEqual(first["gross"].compare(again["gross"]),0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_operation_registry_stage"
        ).fetchone()[0],2)

    def test_failed_write_registers_nothing(self):
        with self.assertRaisesRegex(RuntimeError,"Injected rollback"):
            settle(self.db,"rollback-global-1","buyer","seller","white","1","4",
                   failpoint="after_first_cash")
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_operation_registry_stage"
        ).fetchone()[0],0)
        with self.assertRaisesRegex(ValueError,"Insufficient stock"):
            settle(self.db,"rollback-global-2","buyer","seller","white","100000","4")
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_operation_registry_stage"
        ).fetchone()[0],0)

    def test_race_same_id_different_scope_only_one_succeeds(self):
        def worker(i):
            try:
                with psycopg.connect(DSN,autocommit=True) as conn:
                    if i%2:
                        return ("trade",settle(conn,"cross-race-id-01","buyer",
                                "seller","white","1","4")["replay"])
                    return ("action",action(conn,"cross-race-id-01",
                            "manufacture","seller",product="white",quantity="1"))
            except ValueError as e:
                if "across different" not in str(e):raise
                return ("rejected",None)
        with ThreadPoolExecutor(max_workers=16) as pool:
            result=list(pool.map(worker,range(48)))
        accepted=[x for x in result if x[0]!="rejected"]
        self.assertIn(len(accepted),(24,25))
        self.assertEqual(len([x for x in result if x[0]=="rejected"]),48-len(accepted))
        # Every accepted call is replay or same kind. Only one operation ID exists.
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM hare_factory.v2_operation_registry_stage"
        ).fetchone()[0],1)

if __name__=="__main__":
    unittest.main()
