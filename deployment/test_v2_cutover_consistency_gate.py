"""Pure, isolated regression tests for the V2 cutover consistency gate."""
import unittest
from v2_cutover_consistency_gate import inspect_shadow_consistency, require_cutover_ready


class FakeCursor:
    def __init__(self,rows):
        self.rows=list(rows)
    def fetchmany(self,n):
        result=self.rows[:n]
        self.rows=self.rows[n:]
        return result


class FakeConn:
    def __init__(self,tables):
        self.tables=tables
        self.queries=[]
    def execute(self,query):
        self.queries.append(query)
        for table,rows in self.tables.items():
            if 'FROM "hare_factory"."'+table+'"' in query:
                return FakeCursor(rows)
        raise ValueError("Unexpected query")


class CutoverGateTests(unittest.TestCase):
    def test_exact_equivalent_not_just_text_equal(self):
        c=FakeConn({"factories":[
            ("1e10000","S1:1@10000"),
            ("1000.000","S1:1@3"),
            ("-100000000","S1:-1@8"),
            ("0","S1:"),
        ]})
        summary=inspect_shadow_consistency(c,{"factories":("cash",)},batch_size=2)
        self.assertEqual((summary.rows,summary.values_checked),(4,4))
        self.assertIn('"cash"::text',c.queries[0])

    def test_multiple_columns(self):
        c=FakeConn({"stock":[
            ("100", "S1:100@0", "4e5", "S1:4@5"),
            ("0", "S1:", "1", "S1:1@0"),
        ]})
        summary=inspect_shadow_consistency(c,{"stock":("quantity","work")})
        self.assertEqual((summary.rows,summary.columns,summary.values_checked),(2,1,4))

    def test_both_null_is_valid_historical_empty_cell(self):
        c=FakeConn({"stock":[(None,None,"0","S1:")]})
        summary=inspect_shadow_consistency(c,{"stock":("quantity","work")})
        self.assertEqual(summary.values_checked,2)

    def test_block_drift_and_nulls(self):
        for wrong,error in [("S1:2@1","drift"),(None,"missing"),("oops","invalid")]:
            c=FakeConn({"factories":[("10",wrong)]})
            with self.assertRaisesRegex(RuntimeError,error):
                inspect_shadow_consistency(c,{"factories":("cash",)})

    def test_no_unsafe_sql_identifiers(self):
        with self.assertRaises(ValueError):
            inspect_shadow_consistency(FakeConn({}),{"players; DROP TABLE players":("cash",)})
        with self.assertRaises(ValueError):
            inspect_shadow_consistency(FakeConn({}),{"factories":("cash)--",)})

    def test_fail_closed_without_backup_and_freeze(self):
        c=FakeConn({"factories":[("10","S1:1@1")]})
        for kwargs in ({},{"backup_restored":True},
                       {"backup_restored":True,"legacy_writers_frozen":True}):
            with self.assertRaises(RuntimeError):
                require_cutover_ready(c,{"factories":("cash",)},**kwargs)
        self.assertEqual(c.queries,[])

    def test_requires_stable_count(self):
        c=FakeConn({"factories":[("10","S1:1@1")]})
        with self.assertRaisesRegex(RuntimeError,"row count"):
            require_cutover_ready(c,{"factories":("cash",)},
                                 backup_restored=True,
                                 legacy_writers_frozen=True,expected_rows=2)
        c=FakeConn({"factories":[("10","S1:1@1")]})
        summary=require_cutover_ready(c,{"factories":("cash",)},
                                      backup_restored=True,
                                      legacy_writers_frozen=True,expected_rows=1)
        self.assertEqual(summary.rows,1)


if __name__=="__main__":
    unittest.main()
