"""PostgreSQL-only disposable integration suite: synthetic accounts, no live DB."""
import os
from concurrent.futures import ThreadPoolExecutor
import unittest
from sparse_exact_v1 import SparseExact as S
from v2_postgres_disposable_lab import (
    connect,initialize,shadow_backfill,exact_buy,total_money,total_stock,
    assert_disposable_connection,
)
DSN=os.environ.get('HARE_V2_CI_DSN')

@unittest.skipUnless(DSN,'Requires an explicitly disposable PostgreSQL CI service')
class PostgresShadowLab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert_disposable_connection(DSN)
        initialize(DSN)

    def setUp(self):
        self.db=connect(DSN)
        with self.db.transaction():
            self.db.execute('TRUNCATE trade_receipts, inventories, players RESTART IDENTITY CASCADE')
            self.db.execute("UPDATE settlement_treasury SET tax_v2='S1:' WHERE id=1")
            self.db.execute("INSERT INTO players VALUES('buyer','100',NULL),('seller','1000',NULL)")
            self.db.execute("INSERT INTO inventories VALUES ('buyer','white','7',NULL),('seller','white','3e1000000000',NULL)")
        shadow_backfill(self.db)

    def tearDown(self):
        self.db.close()

    def test_giant_sale_with_negative_cash_and_preserved_legacy(self):
        before=total_money(self.db); count=total_stock(self.db,'white')
        result=exact_buy(self.db,'giant-transaction-001','buyer','seller','white',
                         '2e1000000000','3e2000000000')
        self.assertEqual(result['gross'].compare(S.parse('6e3000000000')),0)
        self.assertEqual(total_money(self.db).compare(before),0)
        self.assertEqual(total_stock(self.db,'white').compare(count),0)
        self.assertEqual(S.deserialize(self.db.execute(
            "SELECT cash_v2 FROM players WHERE id='buyer'").fetchone()[0]).sign(),-1)
        self.assertEqual(self.db.execute(
            "SELECT cash_legacy FROM players WHERE id='buyer'").fetchone()[0],'100')

    def test_64_same_key_requests_one_receipt(self):
        def invoke(_):
            with connect(DSN) as db:
                return exact_buy(db,'duplicate-operation-001','buyer','seller',
                                 'white','200','1000')
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(invoke,range(64)))
        self.assertEqual(sum(not x['already_applied'] for x in results),1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM trade_receipts').fetchone()[0],1)

    def test_20_buyers_for_10_items_concurrent(self):
        with self.db.transaction():
            self.db.execute("UPDATE inventories SET quantity_legacy='10',quantity_v2='S1:10@0' WHERE player='seller' AND product='white'")
            for i in range(20):
                self.db.execute('INSERT INTO players VALUES(%s,%s,%s)',(f'b{i}','0','S1:'))
                self.db.execute('INSERT INTO inventories VALUES(%s,%s,%s,%s)',(f'b{i}','white','0','S1:'))
        before_money=total_money(self.db)
        before_stock=total_stock(self.db,'white')
        def purchase(i):
            try:
                with connect(DSN) as db:
                    exact_buy(db,'competing-purchase-'+str(i).zfill(3),
                              f'b{i}','seller','white','1','50')
                    return True
            except ValueError as error:
                if 'Insufficient stock' not in str(error):
                    raise
                return False
        with ThreadPoolExecutor(max_workers=10) as pool:
            completed=list(pool.map(purchase,range(20)))
        self.assertEqual(sum(completed),10)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM trade_receipts').fetchone()[0],10)
        self.assertEqual(total_stock(self.db,'white').compare(before_stock),0)
        self.assertEqual(total_money(self.db).compare(before_money),0)

    def test_failure_does_not_update_partially_or_log_receipt(self):
        old_money=total_money(self.db)
        old_stock=total_stock(self.db,'white')
        old_cash=self.db.execute('SELECT id,cash_v2 FROM players ORDER BY id').fetchall()
        with self.assertRaisesRegex(RuntimeError,'Injected'):
            exact_buy(self.db,'injected-failure-001','buyer','seller',
                      'white','1e1000','300',failpoint='after_seller_stock')
        self.assertEqual(self.db.execute('SELECT id,cash_v2 FROM players ORDER BY id').fetchall(),old_cash)
        self.assertEqual(total_stock(self.db,'white').compare(old_stock),0)
        self.assertEqual(total_money(self.db).compare(old_money),0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM trade_receipts').fetchone()[0],0)

    def test_backfill_again_is_safe_but_conflict_rejected(self):
        shadow_backfill(self.db)
        self.db.execute("UPDATE players SET cash_v2='S1:900@0' WHERE id='buyer'")
        with self.assertRaisesRegex(ValueError,'mismatch'):
            shadow_backfill(self.db)
        self.assertEqual(self.db.execute(
            "SELECT cash_v2 FROM players WHERE id='buyer'").fetchone()[0],'S1:900@0')

    def test_changed_payload_same_op_key_rejected(self):
        exact_buy(self.db,'reused-key-0001','buyer','seller','white','1','20')
        with self.assertRaisesRegex(ValueError,'different payload'):
            exact_buy(self.db,'reused-key-0001','buyer','seller','white','2','20')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM trade_receipts').fetchone()[0],1)

    def test_staging_only_shadow_ddl_on_synthetic_production_shape(self):
        from v2_shadow_schema_manifest import ECONOMIC_COLUMNS, generate_staging_sql
        # Every table here is SYNTHETIC, in a local disposable database.
        # Roll back all generated DDL at the end of the test.
        with self.db.transaction():
            self.db.execute('CREATE SCHEMA IF NOT EXISTS hare_factory')
            for table,columns in ECONOMIC_COLUMNS.items():
                columns_sql=', '.join('"'+col+'" NUMERIC' for col in columns)
                self.db.execute(
                    'CREATE TABLE hare_factory."'+table+'" ("__id" INT PRIMARY KEY, '
                    +columns_sql+')')
            ddl=generate_staging_sql()
            for sql in ddl.split(';'):
                sql='\n'.join(line for line in sql.splitlines()
                               if not line.lstrip().startswith('--')).strip()
                if sql and sql not in ('BEGIN','COMMIT'):
                    self.db.execute(sql)
            self.db.execute(
                "INSERT INTO hare_factory.factories (__id,cash,cash_v2) VALUES (1,100,'S1:100@0')")
            before=self.db.execute(
                "SELECT cash,cash_v2 FROM hare_factory.factories WHERE __id=1"
            ).fetchone()
            for table,columns in ECONOMIC_COLUMNS.items():
                for column in columns:
                    row=self.db.execute(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_schema='hare_factory' AND table_name=%s AND column_name=%s",
                        (table,column)).fetchone()
                    self.assertEqual(row,('numeric',))
                    row=self.db.execute(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_schema='hare_factory' AND table_name=%s AND column_name=%s",
                        (table,column+'_v2')).fetchone()
                    self.assertEqual(row,('text',))
            self.assertEqual(before,(100,'S1:100@0'))
            # Re-running ADD COLUMN IF NOT EXISTS is safe.
            for sql in ddl.split(';'):
                sql='\n'.join(line for line in sql.splitlines()
                               if not line.lstrip().startswith('--')).strip()
                if sql and sql not in ('BEGIN','COMMIT'):
                    self.db.execute(sql)
            self.assertEqual(self.db.execute(
                "SELECT cash,cash_v2 FROM hare_factory.factories WHERE __id=1"
            ).fetchone(),before)
            # For this isolated schema fixture only; no production DDL.
            self.db.execute('DROP SCHEMA hare_factory CASCADE')

    def test_refuses_any_production_database_uri(self):
        with self.assertRaisesRegex(RuntimeError,'Refusing'):
            assert_disposable_connection('postgresql://u:p@db.xnqvygduplopkkhnrbis.supabase.co/postgres')
        with self.assertRaisesRegex(RuntimeError,'Refusing'):
            assert_disposable_connection('postgresql://u:p@localhost/postgres')

if __name__=='__main__':
    unittest.main()
