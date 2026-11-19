"""Safe offline schema preflight regression tests."""
import unittest
from v2_live_schema_preflight import assess_schema,require_schema_ready,rows_to_columns
from v2_shadow_schema_manifest import ECONOMIC_COLUMNS


class LiveSchemaPreflightTests(unittest.TestCase):
    def complete(self):
        return {(table,name):"numeric" for table,names in ECONOMIC_COLUMNS.items() for name in names} | {
            (table,name+"_v2"):"text" for table,names in ECONOMIC_COLUMNS.items() for name in names
        }

    def test_complete_additive_schema_passes(self):
        self.assertTrue(require_schema_ready(self.complete()))
        self.assertFalse(assess_schema(self.complete()))

    def test_real_legacy_only_schema_blocks(self):
        cols={(table,name):"numeric" for table,names in ECONOMIC_COLUMNS.items() for name in names}
        blockers=assess_schema(cols)
        self.assertEqual(len(blockers),sum(map(len,ECONOMIC_COLUMNS.values())))
        self.assertTrue(all("missing V2 column" in b for b in blockers))
        with self.assertRaisesRegex(RuntimeError,"cutover blocked"):
            require_schema_ready(cols)

    def test_wrong_types_and_missing_legacy_block(self):
        cols=self.complete()
        cols[("factories","cash_v2")]="numeric"
        del cols[("stock","quantity")]
        blockers=assess_schema(cols)
        self.assertTrue(any("V2 column not TEXT" in x for x in blockers))
        self.assertTrue(any("missing legacy column" in x for x in blockers))

    def test_sql_rows_with_duplicate_detection(self):
        self.assertEqual(rows_to_columns([("factories","cash","numeric")]),
                         {("factories","cash"):"numeric"})
        with self.assertRaises(ValueError):
            rows_to_columns([("factories","cash","numeric"),
                             ("factories","cash","numeric")])


if __name__=="__main__":
    unittest.main()
