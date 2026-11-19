"""V2 read-only rankings/admin/data exact regression tests."""
import unittest
from sparse_exact_v1 import SparseExact as S
from v2_read_reports import rankings_projection,dashboard_projection,data_projection

def correct(s,expected):
    return S.deserialize(s).compare(S.parse(expected))==0

class V2ReadReports(unittest.TestCase):
    def setUp(self):
        self.rankings={}
        for metric in ("manufactured","revenue","net_profit"):
            self.rankings[metric]={"metric":metric,"individual":[
              {"id":"alice","rank":1,"display_name":"A","class_number":1,metric:"1.25e7600"},
              {"id":"bob","rank":2,"display_name":"B","class_number":2,metric:"-1e5000"}],
              "classes":[{"class_number":1,"rank":1,metric:"1.25e7600"},
                         {"class_number":2,"rank":2,metric:"-1e5000"}]}
        self.dashboard={"players":[
            {"id":"alice","student_id":"2101","cash":"1e7600","manufactured":"2e6900",
             "revenue":"1.25e7600","net_profit":"1e5000","tier":10,
             "stock":[{"product":"white","quantity":"4e6900"}]}],
            "pending":[{"product":"white","quantity":"2e6900","price":"1e7100"}],
            "summary":{"players":1,"manufactured":"2e6900","revenue":"1.25e7600",
                       "net_profit":"1e5000","pending_shipments":1,"settled_rounds":5},
            "rankings":self.rankings,
            "market":[{"product":"white","round":100,"offered":"2e6900",
                       "sold":"1e6900","revenue":"1e7100","sellers":1}],
            "now":1790000000000,"event":{"phase":"open"}}

    def test_private_ranking_values_never_coerced_to_number(self):
        projected=rankings_projection(self.rankings)
        self.assertEqual(projected["authoritative"],"legacy_numeric")
        self.assertTrue(correct(projected["rankings"]["revenue"]["individual"][0]["revenue"],"1.25e7600"))
        self.assertTrue(correct(projected["rankings"]["net_profit"]["individual"][1]["net_profit"],"-1e5000"))
        self.assertEqual(projected["rankings"]["revenue"]["individual"][0]["rank"],1)

    def test_admin_all_money_fields_and_history_exact(self):
        projected=dashboard_projection(self.dashboard)
        self.assertTrue(correct(projected["players"][0]["cash"],"1e7600"))
        self.assertTrue(correct(projected["players"][0]["stock"][0]["quantity"],"4e6900"))
        self.assertTrue(correct(projected["pending"][0]["price"],"1e7100"))
        self.assertTrue(correct(projected["market"][0]["revenue"],"1e7100"))
        self.assertEqual(projected["players"][0]["tier"],10)
        self.assertEqual(projected["market"][0]["sellers"],1)
        self.assertEqual(projected["summary"]["settled_rounds"],5)
        self.assertTrue(correct(projected["summary"]["net_profit"],"1e5000"))

    def test_data_chart_sources_and_expenses(self):
        result=data_projection({"timeline":[
            {"round":200,"product":"white","sold":"1e5000","revenue":"2e7000","inventory":"3e8000","cost":"1e3000"}],
            "timeline_more":False,
            "breakdown":{"income":[{"key":"white","amount":"2e7000"}],
                         "expense":[{"key":"upgrade","amount":"-1e2000"}]}})
        self.assertTrue(correct(result["timeline"][0]["revenue"],"2e7000"))
        self.assertTrue(correct(result["breakdown"]["expense"][0]["amount"],"-1e2000"))
        self.assertFalse(result["timeline_more"])

    def test_missing_metric_and_fraction_fail_closed(self):
        with self.assertRaises(ValueError):
            rankings_projection({"revenue":self.rankings["revenue"]})
        source=dict(self.dashboard)
        source["players"]=[{**self.dashboard["players"][0],"cash":3.14159}]
        with self.assertRaises(ValueError):
            dashboard_projection(source)

if __name__=="__main__":
    unittest.main()
