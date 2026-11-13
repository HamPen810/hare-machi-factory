"""Staging-only manifest tests; no DB connections."""
import unittest
from v2_shadow_schema_manifest import ECONOMIC_COLUMNS, generate_staging_sql, verify_live_schema

class MigrationManifestTests(unittest.TestCase):
    def test_schema_whitelist_is_tight_and_unique(self):
        pairs=[(t,c) for t,cols in ECONOMIC_COLUMNS.items() for c in cols]
        self.assertEqual(len(pairs),len(set(pairs)))
        for expected in [
            ('factories','cash'),('stock','quantity'),('listings','price'),
            ('orders','quantity'),('bank_accounts','debt'),
            ('sales','sold_quantity'),('admin_fund_transfers','amount')
        ]:
            self.assertIn(expected,pairs)
        self.assertNotIn(('factories','last_tap'),pairs)
        self.assertNotIn(('sales','settled_at'),pairs)
        self.assertNotIn(('players','created_at'),pairs)

    def test_ddl_preserves_existing_numeric_and_rolls_up(self):
        sql=generate_staging_sql()
        statements=[x for x in sql.splitlines() if x.startswith('ALTER TABLE')]
        pairs=[(t,c) for t,cols in ECONOMIC_COLUMNS.items() for c in cols]
        self.assertEqual(len(statements),len(pairs))
        self.assertIn('ADD COLUMN IF NOT EXISTS "cash_v2" TEXT',sql)
        self.assertIn('ADD COLUMN IF NOT EXISTS "quantity_v2" TEXT',sql)
        self.assertIn('BEGIN;',sql)
        self.assertIn('COMMIT;',sql)
        upper=sql.upper()
        for forbidden in ('DROP TABLE','DROP COLUMN','ALTER COLUMN','UPDATE ','DELETE ','TRUNCATE','INSERT INTO'):
            self.assertNotIn(forbidden,upper)

    def test_schema_drift_fails_closed(self):
        values={(t,c):'numeric' for t,cs in ECONOMIC_COLUMNS.items() for c in cs}
        self.assertTrue(verify_live_schema(values))
        del values[('stock','quantity')]
        with self.assertRaisesRegex(ValueError,'Missing'):
            verify_live_schema(values)
        values[('stock','quantity')]='double precision'
        with self.assertRaisesRegex(ValueError,'unexpected'):
            verify_live_schema(values)

if __name__=='__main__':
    unittest.main()
