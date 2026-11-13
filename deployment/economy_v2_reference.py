"""Isolated, *in-memory only* exact-number market settlement reference model.

Not production code and not a database migration.

A single lock protects the toy journal to emulate a serializable transaction.
Do not assume this proves PostgreSQL atomicity, locking or durability.
For production the transaction ID, request fingerprint and all 5 financial/
inventory deltas MUST commit in the same database transaction.
"""
from dataclasses import dataclass,field
from threading import RLock
import hashlib,json
from sparse_exact_v1 import SparseExact as S
from sparse_exact_division import mul_ratio_floor

ZERO=S.parse('0')

@dataclass
class Account:
    cash:S=ZERO
    stock:dict=field(default_factory=dict)

class ExactMarketReference:
    def __init__(self,fee_bps:int=500):
        if type(fee_bps) is not int or not 0<=fee_bps<=10000:
            raise ValueError('Invalid fee in basis points')
        self.fee_bps=fee_bps
        self.lock=RLock()
        self.accounts={}
        self.treasury=ZERO
        self.ledger={}
        self.accepted=0

    def add_account(self,identity,cash='0',stock=None):
        with self.lock:
            if identity in self.accounts:
                raise ValueError('Duplicate identity')
            inventory={k:S.parse(v) for k,v in (stock or {}).items()}
            if any(n.sign()<0 for n in inventory.values()):
                raise ValueError('Negative initial inventory')
            self.accounts[identity]=Account(S.parse(cash),inventory)

    def buy(self,tx_id,buyer,seller,product,quantity,unit_price):
        """Exact transfer, allowing overdraft, rejecting negative stock.

        Operation IDs are immutable: a replay of a different payload is an
        error, while the exact same operation returns its original result.
        """
        if not isinstance(tx_id,str) or not 8<=len(tx_id)<=128:
            raise ValueError('Invalid transaction ID')
        if buyer==seller or buyer not in self.accounts or seller not in self.accounts:
            raise ValueError('Invalid account')
        if not isinstance(product,str) or not product:
            raise ValueError('Invalid product')
        if not isinstance(quantity,S) or not isinstance(unit_price,S):
            raise TypeError('Market values must be exact sparse integers')
        if quantity.sign()<=0 or unit_price.sign()<=0:
            raise ValueError('Quantity and unit price must be positive')
        fingerprint=hashlib.sha256(json.dumps(
            [buyer,seller,product,quantity.serialize(),unit_price.serialize()],
            separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()
        with self.lock:
            old=self.ledger.get(tx_id)
            if old is not None:
                if old[0]!=fingerprint:
                    raise ValueError('Operation ID reused for a different trade')
                return old[1]
            from_account=self.accounts[seller]
            to_account=self.accounts[buyer]
            remaining=from_account.stock.get(product,ZERO)-quantity
            if remaining.sign()<0:
                raise ValueError('Insufficient inventory')
            gross=quantity*unit_price
            fee=mul_ratio_floor(gross,self.fee_bps)
            # Compute the entire result before altering any account/ledger.
            next_seller_cash=from_account.cash+gross-fee
            next_buyer_cash=to_account.cash-gross
            next_buyer_stock=to_account.stock.get(product,ZERO)+quantity
            next_treasury=self.treasury+fee
            result={'gross':gross,'fee':fee,'sold':quantity}
            from_account.stock[product]=remaining
            to_account.stock[product]=next_buyer_stock
            from_account.cash=next_seller_cash
            to_account.cash=next_buyer_cash
            self.treasury=next_treasury
            self.ledger[tx_id]=(fingerprint,result)
            self.accepted+=1
            return result

    def total_money(self):
        with self.lock:
            total=self.treasury
            for a in self.accounts.values():
                total=total+a.cash
            return total

    def total_stock(self,product):
        with self.lock:
            result=ZERO
            for a in self.accounts.values():
                result=result+a.stock.get(product,ZERO)
            return result
