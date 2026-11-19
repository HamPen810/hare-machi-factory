"""Production-shape V2 action tests on LOCAL disposable PostgreSQL 17 only."""
import os,unittest
from concurrent.futures import ThreadPoolExecutor
import psycopg
from sparse_exact_v1 import SparseExact as S
from v2_real_schema_staging_actions import action,initialize_stage
from v2_real_schema_staging_trade import _guard

DSN=os.environ.get('V2_ACTION_STAGE_DSN','')

def compare(raw,other):
    return S.deserialize(raw).compare(S.parse(other))

@unittest.skipUnless(DSN,"Requires isolated hare_v2_stage_* PostgreSQL")
class RealSchemaV2AllActions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=psycopg.connect(DSN,autocommit=True)
        _guard(cls.db)
        cls.db.execute("CREATE SCHEMA IF NOT EXISTS hare_factory")
        cls.db.execute("CREATE TABLE hare_factory.factories("
                       "player TEXT PRIMARY KEY,cash_v2 TEXT NOT NULL,tier INT NOT NULL DEFAULT 1)")
        # Mirror the real production columns and defaults: both legacy
        # quantities remain NUMERIC while V2 shadows are additive TEXT.
        cls.db.execute("CREATE TABLE hare_factory.stock("
                       "player TEXT,product TEXT,"
                       "quantity NUMERIC NOT NULL DEFAULT 0,"
                       "work NUMERIC NOT NULL DEFAULT 0,"
                       "quantity_v2 TEXT,work_v2 TEXT,"
                       "PRIMARY KEY(player,product))")
        cls.db.execute("CREATE TABLE hare_factory.listings("
                       "id TEXT PRIMARY KEY,player TEXT,product TEXT,quantity_v2 TEXT,price_v2 TEXT,"
                       "UNIQUE(player,product))")
        cls.db.execute("CREATE TABLE hare_factory.factory_totals("
                       "player TEXT PRIMARY KEY,manufactured_v2 TEXT,purchases_v2 TEXT)")
        initialize_stage(cls.db)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"db"):cls.db.close()

    def setUp(self):
        with self.db.transaction():
            for tbl in ('v2_action_receipts_stage','v2_bank_contracts_stage',
                        'listings','stock','factory_totals','factories'):
                self.db.execute("TRUNCATE hare_factory."+tbl)
            self.db.execute("INSERT INTO hare_factory.factories VALUES "
                            "('p','S1:1@1000000000',1),('q','S1:',1)")
            self.db.execute("INSERT INTO hare_factory.stock"
                            "(player,product,quantity_v2,work_v2) VALUES "
                            "('p','white','S1:10@700000000','S1:'),"
                            "('q','white','S1:','S1:')")
            self.db.execute("INSERT INTO hare_factory.factory_totals VALUES "
                            "('p','S1:','S1:'),('q','S1:','S1:')")

    def conn(self):
        return psycopg.connect(DSN,autocommit=True)

    def cash(self,player):
        return self.db.execute("SELECT cash_v2 FROM hare_factory.factories WHERE player=%s",
                               (player,)).fetchone()[0]

    def test_large_production_upgrade_and_price_shipping(self):
        a=action(self.db,'produce-v2-test-001','manufacture','p',
                 product='white',quantity='1e800000000')
        self.assertEqual(compare(a['produced'],'1e800000000'),0)
        spent=action(self.db,'upgrade-v2-test-001','upgrade','p',cost='1e900000000')
        self.assertEqual(compare(spent['spent'],'1e900000000'),0)
        ship=action(self.db,'shipment-v2-test-001','ship','p',
                    product='white',quantity='5e799999999',price='1e900000000')
        self.assertEqual(compare(ship['reserved'],'5e799999999'),0)
        price=action(self.db,'reprice-v2-test-001','set_price','p',
                     product='white',price='3e900000000')
        self.assertEqual(compare(price['price'],'3e900000000'),0)
        ret=action(self.db,'cancel-v2-test-001','cancel_shipment','p',product='white')
        self.assertEqual(compare(ret['returned'],'5e799999999'),0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM hare_factory.listings").fetchone()[0],0)
        s=self.db.execute("SELECT quantity_v2 FROM hare_factory.stock "
                          "WHERE player='p'").fetchone()[0]
        self.assertEqual(S.deserialize(s).compare(S.parse('10e700000000')+S.parse('1e800000000')),0)

    def test_server_priced_unlock_is_atomic_and_idempotent(self):
        # The browser cannot change the fixed sea/shisa unlock prices.
        before=self.cash('p')
        unlocked=action(self.db,'unlock-sea-v2-test-001','unlock','p',
                        product='sea',cost='1')
        self.assertEqual(unlocked['unlocked'],'sea')
        self.assertEqual(compare(unlocked['spent'],'300'),0)
        self.assertEqual(
            S.deserialize(self.cash('p')).compare(S.deserialize(before)-S.parse('300')),0)
        quantity,work,legacy_qty,legacy_work=self.db.execute(
            "SELECT quantity_v2,work_v2,quantity,work FROM hare_factory.stock "
            "WHERE player='p' AND product='sea'").fetchone()
        self.assertEqual((quantity,work),('S1:','S1:'))
        self.assertEqual((legacy_qty,legacy_work),(0,0))
        event=self.db.execute(
            "SELECT cash_delta_v2,stock_delta_v2,expense_v2 "
            "FROM hare_factory.v2_economic_events_stage WHERE op_id=%s",
            ('unlock-sea-v2-test-001',)).fetchone()
        self.assertIsNotNone(event)
        self.assertEqual(compare(event[0],'-300'),0)
        self.assertEqual(compare(event[1],'0'),0)
        self.assertEqual(compare(event[2],'300'),0)
        self.assertEqual(action(self.db,'unlock-sea-v2-test-001','unlock','p',
                                product='sea',cost='1'),unlocked)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM hare_factory.v2_action_receipts_stage "
            "WHERE op_id='unlock-sea-v2-test-001'").fetchone()[0],1)
        with self.assertRaisesRegex(ValueError,'already unlocked'):
            action(self.db,'unlock-sea-v2-test-002','unlock','p',product='sea')
        with self.assertRaisesRegex(ValueError,'Insufficient money'):
            action(self.db,'unlock-shisa-v2-001','unlock','q',product='shisa')
        self.assertIsNone(self.db.execute(
            "SELECT quantity_v2 FROM hare_factory.stock "
            "WHERE player='q' AND product='shisa'").fetchone())

    def test_bank_loan_deposit_multiple_contract_repay(self):
        action(self.db,'borrow-v2-test-001','bank_borrow','q',amount='1e900000000',
               interest_bps=100)
        action(self.db,'borrow-v2-test-002','bank_borrow','q',amount='5e800000000',
               interest_bps=200)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM hare_factory.v2_bank_contracts_stage WHERE player='q'"
        ).fetchone()[0],2)
        with self.assertRaises(ValueError):
            action(self.db,'repay-v2-fail-001','bank_repay','p',
                   contract_id='borrow-v2-test-001')
        paid=action(self.db,'repay-v2-test-001','bank_repay','q',
                    contract_id='borrow-v2-test-002')
        self.assertEqual(compare(paid['settled'],'5.1e800000000'),0)
        loan=action(self.db,'deposit-v2-test-001','bank_lend','p',amount='1e800000000',interest_bps=100)
        withdrawal=action(self.db,'withdraw-v2-test-001','bank_withdraw','p',
                          contract_id=loan['contract_id'])
        self.assertEqual(compare(withdrawal['settled'],'1.01e800000000'),0)

    def test_admin_negative_balance_and_forgiveness(self):
        grant=action(self.db,'admin-grant-v2-001','admin_grant','q',amount='1e1000000000')
        self.assertEqual(compare(grant['cash'],'1e1000000000'),0)
        collection=action(self.db,'admin-collect-v2-1','admin_collect','q',
                          amount='1e1000000001')
        self.assertLess(S.deserialize(collection['cash']).sign(),0)
        forgiven=action(self.db,'admin-forgive-v2-1','admin_forgive','q')
        self.assertEqual(compare(forgiven['cash'],'0'),0)
        self.assertEqual(compare(self.cash('q'),'0'),0)

    def test_same_operation_replayed_64_times(self):
        def worker(_):
            with self.conn() as c:
                return action(c,'identical-shipment-001','ship','p',
                              product='white',quantity='10',price='20')
        with ThreadPoolExecutor(max_workers=12) as pool:
            out=list(pool.map(worker,range(64)))
        self.assertTrue(all(x==out[0] for x in out))
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM hare_factory.v2_action_receipts_stage").fetchone()[0],1)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM hare_factory.listings").fetchone()[0],1)
        with self.assertRaisesRegex(ValueError,'(payload mismatch|across different)'):
            action(self.db,'identical-shipment-001','ship','p',
                   product='white',quantity='11',price='20')

    def test_failed_staged_transaction_cannot_change_assets(self):
        old_cash=self.cash('p')
        old_stock=self.db.execute("SELECT quantity_v2 FROM hare_factory.stock "
                                  "WHERE player='p'").fetchone()[0]
        with self.assertRaises(ValueError):
            action(self.db,'invalid-ship-v2-001','ship','p',
                   product='white',quantity='1e1000000000',price='2')
        with self.assertRaises(ValueError):
            action(self.db,'invalid-price-v2-1','set_price','p',
                   product='white',price='1')
        with self.assertRaises(ValueError):
            action(self.db,'invalid-upg-v2-001','upgrade','p',
                   cost='1e1000000001')
        self.assertEqual(self.cash('p'),old_cash)
        self.assertEqual(self.db.execute("SELECT quantity_v2 FROM hare_factory.stock "
                                         "WHERE player='p'").fetchone()[0],old_stock)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM hare_factory.v2_action_receipts_stage").fetchone()[0],0)

if __name__=='__main__':
    unittest.main()
