"""In-memory market reference tests; never touches live player accounts."""
from concurrent.futures import ThreadPoolExecutor
import unittest
from sparse_exact_v1 import SparseExact as S
from economy_v2_reference import ExactMarketReference

class ReferenceLedgerTests(unittest.TestCase):
    def factory(self):
        m=ExactMarketReference(fee_bps=500)
        m.add_account('buyer','1',stock={'white':'0'})
        m.add_account('seller','1000',stock={'white':'3e1000000000'})
        return m

    def test_giant_transfer_exact_fee_and_inventory(self):
        m=self.factory()
        cash_before=m.total_money()
        stock_before=m.total_stock('white')
        count=S.parse('2e1000000000')
        price=S.parse('3e2000000000')
        outcome=m.buy('trade-00000001','buyer','seller','white',count,price)
        self.assertEqual(outcome['gross'].serialize(),'S1:6@3000000000')
        self.assertEqual(outcome['fee'].compare(S.parse('3e2999999999')),0)
        self.assertEqual(m.accounts['buyer'].cash.sign(),-1)
        self.assertEqual(m.accounts['seller'].stock['white'].compare(S.parse('1e1000000000')),0)
        self.assertEqual(m.total_stock('white').compare(stock_before),0)
        self.assertEqual(m.total_money().compare(cash_before),0)
        self.assertEqual(m.accepted,1)

    def test_duplicate_retries_applied_once(self):
        m=self.factory()
        original_money=m.total_money()
        original_stock=m.total_stock('white')
        q=S.parse('10')
        p=S.parse('100')
        def invoke(_):
            return m.buy('same-operation-555','buyer','seller','white',q,p)
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(invoke,range(120)))
        self.assertEqual(m.accepted,1)
        self.assertEqual(len(m.ledger),1)
        self.assertEqual(len(results),120)
        self.assertEqual(m.accounts['buyer'].cash.expand_for_test(),-999)
        self.assertEqual(m.total_stock('white').compare(original_stock),0)
        self.assertEqual(m.total_money().compare(original_money),0)

    def test_multiple_competing_buyers_with_finite_inventory(self):
        m=ExactMarketReference(fee_bps=250)
        m.add_account('seller','0',stock={'white':'10'})
        for i in range(30):m.add_account('buyer'+str(i),'0')
        orig=m.total_money()
        def buy(i):
            try:
                m.buy('tx-'+str(i).zfill(10),'buyer'+str(i),'seller','white',S.parse('1'),S.parse('50'))
                return True
            except ValueError as e:
                if 'Insufficient inventory' not in str(e):raise
                return False
        with ThreadPoolExecutor(max_workers=24) as pool:
            outcome=list(pool.map(buy,range(30)))
        self.assertEqual(sum(outcome),10)
        self.assertEqual(m.accepted,10)
        self.assertTrue(m.accounts['seller'].stock['white'].is_zero())
        self.assertEqual(m.total_stock('white').expand_for_test(),10)
        self.assertEqual(m.total_money().compare(orig),0)

    def test_reused_transaction_id_with_changed_payload_rejected(self):
        m=self.factory()
        first=m.buy('trade-1234567','buyer','seller','white',S.parse('1'),S.parse('20'))
        with self.assertRaisesRegex(ValueError,'reused'):
            m.buy('trade-1234567','buyer','seller','white',S.parse('2'),S.parse('20'))
        self.assertEqual(m.accepted,1)
        self.assertEqual(first['gross'].expand_for_test(),20)

    def test_failed_trade_is_atomic_in_memory(self):
        m=self.factory()
        money=m.total_money()
        stock=m.total_stock('white')
        with self.assertRaisesRegex(ValueError,'Insufficient inventory'):
            m.buy('trade-bad-0001','buyer','seller','white',S.parse('4e1000000000'),S.parse('100'))
        self.assertEqual(m.total_money().compare(money),0)
        self.assertEqual(m.total_stock('white').compare(stock),0)
        self.assertEqual(m.accepted,0)

if __name__=='__main__':
    unittest.main()
