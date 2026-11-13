"""Isolated SQLite integration tests. All files are temporary fixtures.

No real players, Supabase, Render, or other infrastructure is contacted.
"""
from concurrent.futures import ThreadPoolExecutor
import os
import sqlite3
import tempfile
import unittest
from sparse_exact_v1 import SparseExact as S
from v2_sqlite_shadow_lab import (
    connect,backfill_legacy_shadow,exact_buy,total_cash_including_treasury,total_stock
)

class ShadowSqlIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='v2-economy-staging-')
        self.path=os.path.join(self.temp.name,'isolated.sqlite3')
        self.db=connect(self.path)
        self.db.execute("INSERT INTO players (id,cash_legacy) VALUES ('buyer','100')")
        self.db.execute("INSERT INTO players (id,cash_legacy) VALUES ('seller','1000')")
        self.db.execute("INSERT INTO inventories VALUES('buyer','white','7',NULL)")
        self.db.execute("INSERT INTO inventories VALUES('seller','white','3e1000000000',NULL)")
        backfill_legacy_shadow(self.db)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_atomic_giant_value_and_negative_cash(self):
        cash=total_cash_including_treasury(self.db)
        stock=total_stock(self.db,'white')
        receipt=exact_buy(self.db,'tx-giant-0001','buyer','seller','white',
                          '2e1000000000','3e2000000000')
        self.assertEqual(receipt['gross'].compare(S.parse('6e3000000000')),0)
        self.assertEqual(total_cash_including_treasury(self.db).compare(cash),0)
        self.assertEqual(total_stock(self.db,'white').compare(stock),0)
        result=S.deserialize(self.db.execute(
            "SELECT cash_v2 FROM players WHERE id='buyer'").fetchone()[0])
        self.assertLess(result.sign(),0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM trade_receipts').fetchone()[0],1)
        # Legacy columns remain unchanged for rollback rehearsal only.
        self.assertEqual(self.db.execute(
            "SELECT cash_legacy FROM players WHERE id='buyer'").fetchone()[0],'100')

    def test_exactly_once_when_60_duplicate_http_requests_arrive_together(self):
        def buy(_):
            d=connect(self.path)
            try:
                return exact_buy(d,'tx-concurrent-00001','buyer','seller','white',
                                 '1e10','25')
            finally:
                d.close()
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(buy,range(60)))
        self.assertEqual(sum(not r['already_applied'] for r in results),1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM trade_receipts').fetchone()[0],1)

    def test_concurrent_buyers_no_oversell(self):
        self.db.execute("UPDATE inventories SET quantity_legacy='10',quantity_v2='S1:10@0' WHERE player='seller' AND product='white'")
        for i in range(25):
            self.db.execute('INSERT INTO players (id,cash_legacy,cash_v2) VALUES(?,?,?)',
                            (f'buyer{i}','0','S1:'))
            self.db.execute('INSERT INTO inventories VALUES(?,?,?,?)',
                            (f'buyer{i}','white','0','S1:'))
        before=total_stock(self.db,'white')
        def buy(i):
            d=connect(self.path)
            try:
                try:
                    exact_buy(d,'tx-competitor-'+str(i).zfill(3),
                              f'buyer{i}','seller','white','1','50')
                    return True
                except ValueError as e:
                    if 'Insufficient stock' not in str(e):raise
                    return False
            finally:
                d.close()
        with ThreadPoolExecutor(max_workers=15) as pool:
            successes=list(pool.map(buy,range(25)))
        self.assertEqual(sum(successes),10)
        self.assertEqual(total_stock(self.db,'white').compare(before),0)

    def test_failpoint_rolls_back_every_affected_row(self):
        before_money=total_cash_including_treasury(self.db)
        before_stock=total_stock(self.db,'white')
        before_rows=list(self.db.execute('SELECT id,cash_v2 FROM players ORDER BY id'))
        with self.assertRaisesRegex(RuntimeError,'Injected'):
            exact_buy(self.db,'tx-failpoint-001','buyer','seller','white',
                      '1e1000000','8',failpoint='after_seller_stock')
        self.assertEqual(before_rows,list(self.db.execute('SELECT id,cash_v2 FROM players ORDER BY id')))
        self.assertEqual(total_cash_including_treasury(self.db).compare(before_money),0)
        self.assertEqual(total_stock(self.db,'white').compare(before_stock),0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM trade_receipts').fetchone()[0],0)

    def test_backfill_twice_and_conflict_fails_without_partial_changes(self):
        backfill_legacy_shadow(self.db)
        self.db.execute("UPDATE players SET cash_v2='S1:999@0' WHERE id='buyer'")
        with self.assertRaisesRegex(ValueError,'differs'):
            backfill_legacy_shadow(self.db)
        self.assertEqual(self.db.execute(
            "SELECT cash_v2 FROM players WHERE id='buyer'").fetchone()[0],'S1:999@0')

    def test_replayed_key_with_different_payload_rejected(self):
        exact_buy(self.db,'tx-diff-payload','buyer','seller','white','10','12')
        with self.assertRaisesRegex(ValueError,'different payload'):
            exact_buy(self.db,'tx-diff-payload','buyer','seller','white','11','12')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM trade_receipts').fetchone()[0],1)

    def test_backup_restore_rehearsal_of_isolated_fixture(self):
        backup_path=os.path.join(self.temp.name,'snapshot.sqlite3')
        backup=sqlite3.connect(backup_path)
        try:
            self.db.backup(backup)
        finally:
            backup.close()
        original_cash=total_cash_including_treasury(self.db)
        exact_buy(self.db,'tx-after-backup','buyer','seller','white','20','30')
        restored=connect(backup_path)
        try:
            self.assertEqual(total_cash_including_treasury(restored).compare(original_cash),0)
            self.assertEqual(restored.execute('SELECT COUNT(*) FROM trade_receipts').fetchone()[0],0)
            self.assertEqual(restored.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        finally:
            restored.close()

if __name__=='__main__':
    unittest.main()
