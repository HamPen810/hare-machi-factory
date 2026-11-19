"""Huge Number V2 multi-operation economy reference, staging ONLY.

Pure in-memory transactional reference for migration parity. This is NOT the
production game engine and must not be wired to live money. A single operation
changes a deep-copied state before commit, preventing partial state changes.
"""
from copy import deepcopy
from threading import RLock
import hashlib, json
from sparse_exact_v1 import SparseExact as S
from sparse_exact_division import mul_ratio_floor

Z=S.parse("0")
ONE=S.parse("1")

def exact(value):
    if isinstance(value,S):return value
    if isinstance(value,str):return S.deserialize(value) if value.startswith("S1:") else S.parse(value)
    if type(value) is int:return S.parse(str(value))
    raise ValueError("V2 requires an exact integer string")

def positive(value):
    n=exact(value)
    if n.sign()<=0:raise ValueError("A strictly positive integer is required")
    return n

def nonnegative(value):
    n=exact(value)
    if n.sign()<0:raise ValueError("A nonnegative integer is required")
    return n

def serialize(value):
    return exact(value).serialize()

class V2OperationLab:
    """Test-only atomic economy; accepts S1/scientific notation for every amount."""
    def __init__(self, manufacturing_cost=None, upgrade_cost=None, tax_bps=0):
        if type(tax_bps) is not int or not 0<=tax_bps<=10000:
            raise ValueError("Invalid tax rate")
        self.lock=RLock()
        self.state={
            "players":{}, "listings":{}, "contracts":{}, "sales":[],
            "receipts":{}, "audit":[], "taxes":Z
        }
        self.manufacturing_cost={key:positive(val) for key,val in (manufacturing_cost or {"white":"1"}).items()}
        self.upgrade_cost=upgrade_cost or (lambda tier: exact("10") * exact(5**(tier-1)))
        self.tax_bps=tax_bps

    def register(self,player,cash="0",stock=None,tier=1):
        if type(player) is not str or not player or type(tier) is not int or tier<1:
            raise ValueError("Invalid player")
        with self.lock:
            if player in self.state["players"]:raise ValueError("Duplicate player")
            self.state["players"][player]={
                "cash":exact(cash),"stock":{p:nonnegative(v) for p,v in (stock or {}).items()},
                "tier":tier,"spending":Z,"manufactured":Z,"revenue":Z,"profit":Z,
                "deposits":Z,"debt":Z,"tax_paid":Z
            }

    def _operation(self,op_id,kind,who,data,fn):
        if type(op_id) is not str or not 8<=len(op_id)<=128:
            raise ValueError("Invalid immutable operation ID")
        source=json.dumps([kind,who,data],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        fingerprint=hashlib.sha256(source.encode()).hexdigest()
        with self.lock:
            old=self.state["receipts"].get(op_id)
            if old is not None:
                if old["fingerprint"]!=fingerprint:
                    raise ValueError("Operation ID reused with a different request")
                return deepcopy(old["result"])
            working=deepcopy(self.state)
            result=fn(working)
            working["receipts"][op_id]={"fingerprint":fingerprint,"result":deepcopy(result)}
            working["audit"].append({"op_id":op_id,"kind":kind,"player":who})
            self.state=working
            return deepcopy(result)

    @staticmethod
    def _player(state,who):
        try:return state["players"][who]
        except KeyError:raise ValueError("Unknown player") from None

    def execute(self,op_id,kind,player,**data):
        def run(st):
            p=self._player(st,player)
            if kind in ("tap","manufacture"):
                product=data["product"]
                qty=positive(data["quantity"])
                if product not in p["stock"]:raise ValueError("Product not unlocked")
                p["stock"][product]=p["stock"][product]+qty
                p["manufactured"]=p["manufactured"]+qty
                return {"produced":qty.serialize()}
            if kind=="upgrade":
                cost=positive(data.get("cost",self.upgrade_cost(p["tier"])))
                if p["cash"].compare(cost)<0:raise ValueError("Insufficient funds")
                p["cash"]=p["cash"]-cost
                p["spending"]=p["spending"]+cost
                p["tier"]+=1
                return {"spent":cost.serialize(),"tier":p["tier"]}
            if kind=="unlock":
                product=data["product"]
                cost=positive(data["cost"])
                if product in p["stock"]:raise ValueError("Already unlocked")
                if p["cash"].compare(cost)<0:raise ValueError("Insufficient funds")
                p["cash"]=p["cash"]-cost;p["spending"]=p["spending"]+cost
                p["stock"][product]=Z
                return {"unlocked":product,"spent":cost.serialize()}
            if kind in ("ship","add_listing","edit_shipment"):
                product=data["product"]
                qty=positive(data["quantity"])
                price=positive(data["price"])
                minimum=self.manufacturing_cost.get(product,Z)+ONE
                if price.compare(minimum)<0:raise ValueError("Price below manufacturing cost plus one")
                existing=st["listings"].get((player,product))
                if kind=="edit_shipment" and existing is None:raise ValueError("No active shipment")
                if product not in p["stock"]:raise ValueError("Product not unlocked")
                available=p["stock"][product]+(existing["quantity"] if existing else Z)
                if available.compare(qty)<0:raise ValueError("Insufficient stock")
                p["stock"][product]=available-qty
                st["listings"][(player,product)]={"quantity":qty,"price":price}
                return {"shipment":product,"quantity":qty.serialize(),"price":price.serialize()}
            if kind=="set_price":
                product=data["product"];price=positive(data["price"])
                minimum=self.manufacturing_cost.get(product,Z)+ONE
                if price.compare(minimum)<0:raise ValueError("Price too low")
                listing=st["listings"].get((player,product))
                if listing is None:raise ValueError("No active listing")
                listing["price"]=price
                return {"price":price.serialize()}
            if kind=="cancel_shipment":
                product=data["product"]
                listing=st["listings"].pop((player,product),None)
                if listing is None:raise ValueError("No active shipment")
                p["stock"][product]=p["stock"].get(product,Z)+listing["quantity"]
                return {"returned":listing["quantity"].serialize()}
            if kind in ("buy_market","sell"):
                seller=data.get("seller") if kind=="buy_market" else player
                buyer=player if kind=="buy_market" else data.get("buyer")
                if seller==buyer:raise ValueError("Self trade forbidden")
                sell_acc=self._player(st,seller);buy_acc=self._player(st,buyer)
                product=data["product"];qty=positive(data["quantity"])
                listing=st["listings"].get((seller,product))
                if not listing:raise ValueError("Offer unavailable")
                if listing["quantity"].compare(qty)<0:raise ValueError("Offer insufficient")
                price=listing["price"]
                if "expected_price" in data and exact(data["expected_price"]).compare(price)!=0:
                    raise ValueError("Price changed")
                gross=qty*price
                cost=self.manufacturing_cost.get(product,Z)*qty
                taxable=gross-cost
                tax=mul_ratio_floor(taxable,self.tax_bps) if taxable.sign()>0 else Z
                buy_acc["cash"]=buy_acc["cash"]-gross  # Overdraft allowed
                buy_acc["stock"][product]=buy_acc["stock"].get(product,Z)+qty
                buy_acc["spending"]=buy_acc["spending"]+gross
                sell_acc["cash"]=sell_acc["cash"]+gross-cost-tax
                sell_acc["revenue"]=sell_acc["revenue"]+gross
                sell_acc["profit"]=sell_acc["profit"]+gross-cost  # tax does not affect ranked profit
                sell_acc["tax_paid"]=sell_acc["tax_paid"]+tax
                st["taxes"]=st["taxes"]+tax
                listing["quantity"]=listing["quantity"]-qty
                if listing["quantity"].sign()==0:del st["listings"][(seller,product)]
                sale={"buyer":buyer,"seller":seller,"product":product,
                      "quantity":qty.serialize(),"price":price.serialize(),
                      "gross":gross.serialize(),"materials":cost.serialize(),"tax":tax.serialize()}
                st["sales"].append(sale)
                return sale
            if kind in ("bank_borrow","bank_lend"):
                amt=positive(data["amount"]);interest=int(data.get("interest_bps",0))
                if type(interest) is not int or not 0<=interest<=10000:
                    raise ValueError("Invalid interest")
                final=amt+mul_ratio_floor(amt,interest)
                if kind=="bank_lend":
                    if p["cash"].compare(amt)<0:raise ValueError("Cannot deposit borrowed money")
                    p["cash"]=p["cash"]-amt;p["deposits"]=p["deposits"]+final
                    contract_kind="lend"
                else:
                    p["cash"]=p["cash"]+amt;p["debt"]=p["debt"]+final
                    contract_kind="borrow"
                st["contracts"][op_id]={"player":player,"kind":contract_kind,"amount":final}
                return {"contract_id":op_id,"amount":final.serialize()}
            if kind in ("bank_repay","bank_withdraw"):
                contracts=st["contracts"]
                target=data["contract_id"]
                record=contracts.get(target)
                expected="borrow" if kind=="bank_repay" else "lend"
                if record is None or record["player"]!=player or record["kind"]!=expected:
                    raise ValueError("No matching contract")
                amount=record["amount"]
                if kind=="bank_repay":
                    if p["cash"].compare(amount)<0:raise ValueError("Insufficient repayment cash")
                    p["cash"]=p["cash"]-amount
                    p["debt"]=p["debt"]-amount
                else:
                    p["cash"]=p["cash"]+amount
                    p["deposits"]=p["deposits"]-amount
                del contracts[target]
                return {"settled":amount.serialize()}
            if kind in ("admin_grant","admin_collect"):
                amount=positive(data["amount"])
                p["cash"]=p["cash"]+(amount if kind=="admin_grant" else -amount)
                if kind=="admin_collect":p["spending"]=p["spending"]+amount
                return {"cash_after":p["cash"].serialize()}
            if kind=="admin_forgive":
                p["debt"]=Z
                for contract_id,contract in list(st["contracts"].items()):
                    if contract["player"]==player and contract["kind"]=="borrow":
                        del st["contracts"][contract_id]
                if p["cash"].sign()<0:p["cash"]=Z
                return {"cash_after":p["cash"].serialize(),"debt_after":Z.serialize()}
            raise ValueError("Unsupported operation "+kind)
        return self._operation(op_id,kind,player,data,run)

    def balance(self,player):
        with self.lock:
            p=deepcopy(self._player(self.state,player))
        return {key:({product:serialize(q) for product,q in value.items()} if key=="stock"
                     else serialize(value) if isinstance(value,S) else value)
                for key,value in p.items()}

    def rankings(self,metric="revenue"):
        if metric not in ("revenue","profit","manufactured","cash","spending"):
            raise ValueError("Invalid ranking metric")
        with self.lock:
            rows=[{"player":name,"value":p[metric]} for name,p in self.state["players"].items()]
        # Exact comparisons; never cast to float or JavaScript Number.
        from functools import cmp_to_key
        rows.sort(key=cmp_to_key(lambda a,b:b["value"].compare(a["value"])))
        return [{"player":row["player"],"value":row["value"].serialize(),"rank":index+1}
                for index,row in enumerate(rows)]

    def data(self):
        with self.lock:
            st=deepcopy(self.state)
        result={}
        for key,p in st["players"].items():
            result[key]={"cash":p["cash"].serialize(),
                "inventory":{k:v.serialize() for k,v in p["stock"].items()},
                "revenue":p["revenue"].serialize(),
                "net_profit":p["profit"].serialize(),
                "manufactured":p["manufactured"].serialize(),
                "expenses":p["spending"].serialize(),
                "debt":p["debt"].serialize()}
        return {"players":result,"sales":st["sales"],"taxes":st["taxes"].serialize(),
                "action_count":len(st["receipts"]),"listing_count":len(st["listings"])}
