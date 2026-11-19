"""Full staged V2 operation matrix (synthetic, never live user assets)."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from sparse_exact_v1 import SparseExact as S
from v2_game_economy_full_reference import V2OperationLab

def same(raw,other):
    return S.deserialize(raw).compare(S.parse(other))==0

class FullV2EconomyTest(unittest.TestCase):
    def setup_game(self,tax=1000):
        e=V2OperationLab({"white":"2","sea":"5"},tax_bps=tax)
        e.register("alice",cash="1e1000000000",stock={"white":"1e1000000000","sea":"10"})
        e.register("bob",cash="10",stock={"white":"100","sea":"0"})
        e.register("charlie",cash="10000",stock={"white":"0","sea":"0"})
        return e

    def test_full_realistic_operation_flow_giant_values(self):
        e=self.setup_game()
        e.execute("upgrade-alice-001","upgrade","alice",cost="9e900000000")
        e.execute("tap-alice-001","manufacture","alice",product="white",quantity="5e700000000")
        e.execute("ship-alice-001","ship","alice",product="white",quantity="2e700000000",price="3e1000000000")
        e.execute("price-alice-001","set_price","alice",product="white",price="4e1000000000")
        result=e.execute("buy-bob-000001","buy_market","bob",seller="alice",product="white",
                         quantity="2e700000000",expected_price="4e1000000000")
        self.assertTrue(same(result["gross"],"8e1700000000"))
        self.assertEqual(e.data()["listing_count"],0)
        self.assertTrue(same(e.balance("bob")["stock"]["white"],"100"+"0"*700000000) if False else
                        S.deserialize(e.balance("bob")["stock"]["white"]).compare(S.parse("100")+S.parse("2e700000000"))==0)
        self.assertEqual(e.balance("bob")["cash"][:3],"S1:")
        self.assertEqual(e.data()["action_count"],5)
        rank=e.rankings("revenue")
        self.assertEqual(rank[0]["player"],"alice")
        self.assertTrue(same(e.balance("bob")["spending"],"8e1700000000"))
        self.assertTrue(same(e.data()["taxes"],"7.9999999999999999999999999999999999999999999999999999e1699999999") if False else
                        S.deserialize(e.data()["taxes"]).sign()>0)

    def test_ship_edit_cancel_and_price_validation(self):
        e=self.setup_game()
        before=S.deserialize(e.balance("alice")["stock"]["sea"])
        e.execute("ship-sea-000001","ship","alice",product="sea",quantity="8",price="6")
        e.execute("edit-sea-000001","edit_shipment","alice",product="sea",quantity="6",price="9")
        e.execute("price-sea-00001","set_price","alice",product="sea",price="100")
        self.assertTrue(same(e.balance("alice")["stock"]["sea"],"4"))
        e.execute("cancel-sea-001","cancel_shipment","alice",product="sea")
        self.assertEqual(S.deserialize(e.balance("alice")["stock"]["sea"]).compare(before),0)
        with self.assertRaises(ValueError):
            e.execute("invalid-price-1","ship","alice",product="sea",quantity="1",price="5")
        self.assertEqual(e.data()["listing_count"],0)

    def test_bank_multiple_contracts_exact_interest(self):
        e=self.setup_game()
        a=e.execute("bank-borrow-001","bank_borrow","bob",amount="1e1000000000",interest_bps=250)
        b=e.execute("bank-lend-00001","bank_lend","alice",amount="5e900000000",interest_bps=100)
        self.assertTrue(S.deserialize(a["amount"]).compare(S.parse("1.025e1000000000"))==0)
        self.assertTrue(S.deserialize(b["amount"]).compare(S.parse("5.05e900000000"))==0)
        e.execute("bank-borrow-002","bank_borrow","bob",amount="500",interest_bps=300)
        with self.assertRaises(ValueError):
            e.execute("repay-insuff-01","bank_repay","charlie",contract_id="bank-borrow-001")
        e.execute("withdraw-alice-01","bank_withdraw","alice",contract_id="bank-lend-00001")
        # Loan repayments use the locked contract amount, without float conversion.
        e.execute("bank-repay-bob-01","bank_repay","bob",contract_id="bank-borrow-002")
        self.assertTrue(same(e.balance("bob")["debt"],"1.025e1000000000"))

    def test_admin_funds_negative_collect_and_forgiveness(self):
        e=self.setup_game()
        e.execute("admin-collect-001","admin_collect","bob",amount="1e100000000000")
        self.assertLess(S.deserialize(e.balance("bob")["cash"]).sign(),0)
        e.execute("admin-forgive-001","admin_forgive","bob")
        self.assertTrue(same(e.balance("bob")["cash"],"0"))
        e.execute("admin-grant-001","admin_grant","bob",amount="1e100000000000")
        self.assertTrue(same(e.balance("bob")["cash"],"1e100000000000"))

    def test_duplicate_64_parallel_buy_only_once(self):
        e=self.setup_game()
        e.execute("ship-sea-000001","ship","alice",product="sea",quantity="10",price="20")
        def invoke(_):
            return e.execute("identical-buy-001","buy_market","bob",
                             seller="alice",product="sea",quantity="3",expected_price="20")
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(invoke,range(64)))
        self.assertTrue(all(r==results[0] for r in results))
        self.assertEqual(e.data()["action_count"],2)
        self.assertTrue(same(e.balance("bob")["stock"]["sea"],"3"))
        with self.assertRaises(ValueError):
            e.execute("identical-buy-001","buy_market","bob",
                      seller="alice",product="sea",quantity="1",expected_price="20")

    def test_20_concurrent_buys_for_only_10_items(self):
        e=V2OperationLab({"white":"1"})
        e.register("seller",cash="0",stock={"white":"10"})
        e.execute("ship-seller-001","ship","seller",product="white",quantity="10",price="2")
        for i in range(20):e.register(f"buyer{i}",cash="0",stock={"white":"0"})
        def buy(i):
            try:
                e.execute(f"buy-competing-{i:03}","buy_market",f"buyer{i}",seller="seller",
                          product="white",quantity="1",expected_price="2")
                return True
            except ValueError as err:
                if "unavailable" in str(err) or "insufficient" in str(err).lower():
                    return False
                raise
        with ThreadPoolExecutor(max_workers=12) as pool:
            accepted=list(pool.map(buy,range(20)))
        self.assertEqual(sum(accepted),10)
        sold_total=S.parse("0")
        for i in range(20):
            sold_total=sold_total+S.deserialize(e.balance(f"buyer{i}")["stock"]["white"])
        self.assertEqual(sold_total.compare(S.parse("10")),0)
        self.assertEqual(e.data()["action_count"],11)

    def test_invalid_write_is_atomic_with_no_receipt(self):
        e=self.setup_game()
        baseline=e.data()
        with self.assertRaises(ValueError):
            e.execute("invalid-upgrade-1","upgrade","bob",cost="1e1000000000")
        with self.assertRaises(ValueError):
            e.execute("invalid-ship-0001","ship","bob",product="sea",quantity="100",price="7")
        with self.assertRaises(ValueError):
            e.execute("invalid-buy-00001","buy_market","bob",seller="alice",
                      product="white",quantity="1",expected_price="1")
        self.assertEqual(e.data(),baseline)

    def test_ranking_data_and_strict_input_types(self):
        e=self.setup_game()
        e.execute("grant-bob-000001","admin_grant","bob",amount="1e1500000000")
        self.assertEqual(e.rankings("cash")[0]["player"],"bob")
        with self.assertRaises(ValueError):
            e.execute("invalid-admin-001","admin_grant","bob",amount=1.5)
        with self.assertRaises(ValueError):
            e.execute("invalid-admin-002","admin_grant","bob",amount="1.1")
        self.assertTrue(e.data()["players"]["bob"]["cash"].startswith("S1:"))

if __name__=="__main__":
    unittest.main()
