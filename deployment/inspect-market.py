"""Shared transactional game domain. Call only from a trusted server adapter."""
import bank
import random
from math import isqrt
import json
import secrets
import time
from fractions import Fraction as F
from accounts import CLOSE_MS
from event import OPEN_MS,DEPARTURE_MS

PRODUCTS = {'white': (1,8,1,140,0), 'sea': (3,15,4,70,300), 'shisa': (12,60,22,30,1000)}
POWERS = [1,5,20,100,500,2000]
RARES = [('rainbow','三日坊主',10**6),('sand','小山坊主',100*10**8),('pearl','山田坊主',100*10**16),('gold','寺本坊主',100*10**28)]
UPGRADES = [100,600,3000,15000,75000]

def _binomial_bigint(units, denominator):
    """A bounded-time, integer-only sampler for extremely large populations.

    For small inputs, draws are exact; astronomical inputs use an integer
    normal approximation. Population totals are never rounded or capped.
    """
    if not units or denominator == 1:
        return units
    if units < 10000:
        return sum(secrets.randbelow(denominator) == 0 for _ in range(units))
    if units < 10**15 and units // denominator < 10000:
        return random.SystemRandom().binomialvariate(units, 1 / denominator)
    mean, remainder = divmod(units, denominator)
    sigma = isqrt(units * (denominator - 1)) // denominator
    scale = 1 << 24
    z = sum(secrets.randbelow(scale) for _ in range(12)) - 6 * (scale - 1)
    noise = sigma * z // scale
    rounded = int(secrets.randbelow(denominator) < remainder)
    return max(0, min(units, mean + noise + rounded))

def rare_count(units, odds):
    """Sample rarities without converting huge production counts to floats."""
    if units < 0 or odds < 1:
        raise ValueError("Invalid rarity inputs")
    remaining = odds
    while remaining > 1 and units:
        factor = min(remaining, 10**6)
        if remaining % factor:
            factor = remaining
        units = _binomial_bigint(units, factor)
        remaining //= factor
    return units

def power(tier):return POWERS[tier] if tier<len(POWERS) else POWERS[-1]*5**(tier-len(POWERS)+1)
def upgrade_cost(tier):return UPGRADES[tier] if tier<len(UPGRADES) else UPGRADES[-1]*5**(tier-len(UPGRADES)+1)
EQUIPMENT={'sunpress':('おひさまプレス',50000),'islandline':('南風オートライン',250000)}
def allocate_hourly(offers, sold_this_hour, elapsed_minutes, demand_bps=2500):
    """Spread the hourly quota over 60 ticks, with integer carry between ticks."""
    total = sum(quantity for quantity, _ in offers)
    target = (total + sold_this_hour) * elapsed_minutes * demand_bps // 600000
    if demand_bps and elapsed_minutes == 60 and 0 < total + sold_this_hour < 4:
        target = 1
    remaining = min(total, max(0, target - sold_this_hour))
    if not remaining:
        return [0] * len(offers)

    average = F(sum(price for _, price in offers), len(offers))
    # The price deviation score is monotonic in price for this same group.
    # Equal price gaps therefore tie on the deviation score as well.
    priority = sorted(range(len(offers)), key=lambda i: (
        -(average - offers[i][1]), -offers[i][0], i))
    sales = [0] * len(offers)
    for i in priority:
        sales[i] = min(remaining, offers[i][0])
        remaining -= sales[i]
        if not remaining:
            break
    return sales


def allocate(offers, standard, demand):
    """Exact rational allocation; input order breaks equal fractional remainders."""
    if not offers: return []
    n=len(offers); total=sum(q for q,p in offers)
    blend=min(F(max(n-3,0),3),1)
    mean=sum(min(max(F(p),F(standard,2)),2*standard) for q,p in offers)/n
    reference=(1-blend)*standard+blend*mean
    weights=[q*min(max((reference/p)**2,F(1,20)),2) for q,p in offers]
    target=min(total,int(demand*sum(weights)/total))
    result=[F(0) for _ in offers]; active=set(range(n)); left=F(target)
    while active and left:
        weight=sum(weights[i] for i in active)
        capped=[i for i in active if left*weights[i]/weight>=offers[i][0]]
        if not capped:
            for i in active: result[i]=left*weights[i]/weight
            break
        for i in capped:
            result[i]=F(offers[i][0]); left-=result[i]; active.remove(i)
    sold=[int(x) for x in result]
    order=sorted(range(n),key=lambda i: (-(result[i]-sold[i]),i))
    for i in order[:target-sum(sold)]: sold[i]+=1
    return sold

class Game:
    active_helpers_query = '''SELECT player FROM factories
                WHERE helper_product IS NOT NULL AND helper_tick < helper_until
                UNION SELECT player FROM helpers
                UNION SELECT player FROM autolines'''

    def __init__(self, accounts, clock=None, opens_at=OPEN_MS, *, read_only=False):
        self.accounts=accounts; self.db=accounts.db
        self.clock=clock or (lambda: int(time.time()*1000))
        self.opens_at=opens_at
        if accounts.postgres:
            if read_only:
                return
            if self.db.execute('SELECT 1 FROM market_cursor WHERE id=1').fetchone():
                return
            with self.db:
                self.db.execute('INSERT INTO market_cursor VALUES(1,?) ON CONFLICT (id) DO NOTHING',(self.clock()//60000-1,))
            return
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS auto_totals(player TEXT,product TEXT,quantity INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(player,product));
        CREATE TABLE IF NOT EXISTS helpers(id TEXT PRIMARY KEY,player TEXT,product TEXT,until INTEGER,tick INTEGER,rate INTEGER);
        CREATE TABLE IF NOT EXISTS equipment(player TEXT,kind TEXT,level INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(player,kind));
        CREATE TABLE IF NOT EXISTS autolines(player TEXT PRIMARY KEY,product TEXT,tick INTEGER);
        CREATE TABLE IF NOT EXISTS listings(id TEXT PRIMARY KEY,player TEXT,product TEXT,quantity INTEGER,price INTEGER,accepted INTEGER,round INTEGER,UNIQUE(player,product));
        CREATE TABLE IF NOT EXISTS market_ticks(round INTEGER,product TEXT,player TEXT,sold INTEGER,revenue INTEGER,inventory INTEGER,cost INTEGER,PRIMARY KEY(round,product,player));
        CREATE TABLE IF NOT EXISTS market_cursor(id INTEGER PRIMARY KEY,last INTEGER);
        CREATE TABLE IF NOT EXISTS rare_firsts(id INTEGER PRIMARY KEY AUTOINCREMENT, player TEXT, rare TEXT, seen INTEGER NOT NULL DEFAULT 0, UNIQUE(player,rare));
        CREATE TABLE IF NOT EXISTS rare_collection(player TEXT REFERENCES players(id), rare TEXT, quantity INTEGER NOT NULL, discovered INTEGER NOT NULL, PRIMARY KEY(player,rare));
        CREATE TABLE IF NOT EXISTS factories(player TEXT PRIMARY KEY REFERENCES players(id), cash INTEGER NOT NULL DEFAULT 500, tier INTEGER NOT NULL DEFAULT 0, last_tap INTEGER NOT NULL DEFAULT 0, helper_product TEXT, helper_until INTEGER NOT NULL DEFAULT 0, helper_tick INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS stock(player TEXT REFERENCES players(id), product TEXT, quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0), work INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(player,product));
        CREATE TABLE IF NOT EXISTS actions(player TEXT, key TEXT, payload TEXT, result TEXT, PRIMARY KEY(player,key));
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, player TEXT REFERENCES players(id), product TEXT, quantity INTEGER, price INTEGER, accepted INTEGER, round INTEGER, UNIQUE(player,product,round));
        CREATE TABLE IF NOT EXISTS rounds(id INTEGER PRIMARY KEY, settled INTEGER);
        CREATE TABLE IF NOT EXISTS market_history(round INTEGER, product TEXT, offered INTEGER, sold INTEGER, revenue INTEGER, sellers INTEGER, PRIMARY KEY(round,product));
        ''')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO rare_firsts(player,rare) SELECT player,rare FROM rare_collection ORDER BY discovered,player,rare')
        with self.db:
            if not self.db.execute('SELECT 1 FROM market_cursor').fetchone():
                self.db.execute('INSERT INTO listings SELECT id,player,product,bsum(quantity),price,MIN(accepted),MIN(round) FROM orders WHERE round NOT IN (SELECT id FROM rounds) GROUP BY player,product')
                self.db.execute('DELETE FROM orders WHERE round NOT IN (SELECT id FROM rounds)')
                self.db.execute('INSERT INTO market_cursor VALUES(1,?)',(self.clock()//60000-1,))
        # Migrate existing local prototypes once, without counting returned stock twice.
        with self.db:
            for f in self.db.execute('SELECT player FROM factories WHERE player NOT IN (SELECT player FROM factory_totals)').fetchall():
                p=f['player']
                manufactured=self.db.execute('''SELECT
                  COALESCE((SELECT bsum(quantity) FROM stock WHERE player=?),0)+
                  COALESCE((SELECT bsum(quantity) FROM listings WHERE player=?),0)+
                  COALESCE((SELECT bsum(sold_quantity) FROM sales WHERE player_id=?),0)''',(p,p,p)).fetchone()[0]
                purchases=sum(json.loads(r[0]).get('spent',0) for r in self.db.execute('SELECT result FROM actions WHERE player=?',(p,)))
                self.db.execute('INSERT OR IGNORE INTO factory_totals VALUES(?,?,?)',(p,manufactured,purchases))

    def _factory(self,p):
        row=self.db.execute('''SELECT f.* FROM factories f
            JOIN stock s ON s.player=f.player AND s.product='white'
            JOIN factory_totals t ON t.player=f.player WHERE f.player=?''',(p,)).fetchone()
        if row is not None:
            return row
        self.db.execute('INSERT OR IGNORE INTO factories(player) VALUES(?)',(p,))
        self.db.execute("INSERT OR IGNORE INTO stock(player,product) VALUES(?,'white')",(p,))
        self.db.execute('INSERT OR IGNORE INTO factory_totals(player) VALUES(?)',(p,))
        return self.db.execute('SELECT * FROM factories WHERE player=?',(p,)).fetchone()

    def _work(self,p,product,work,automatic=False):
        row=self.db.execute('SELECT * FROM stock WHERE player=? AND product=?',(p,product)).fetchone()
        if not row: raise ValueError('この坊主は未解放です。')
        units,remainder=divmod(row['work']+work,PRODUCTS[product][0])
        self.db.execute('UPDATE stock SET quantity=badd(quantity,?),work=? WHERE player=? AND product=?',(units,remainder,p,product))
        self.db.execute('UPDATE factory_totals SET manufactured=badd(manufactured,?) WHERE player=?',(units,p))
        if automatic and units:
            self.db.execute('INSERT INTO auto_totals VALUES(?,?,?) ON CONFLICT(player,product) DO UPDATE SET quantity=badd(auto_totals.quantity,excluded.quantity)',(p,product,units))
        for rare,name,odds in RARES:
            found=rare_count(units,odds)
            if found:
                self.db.execute('INSERT OR IGNORE INTO rare_firsts(player,rare) VALUES(?,?)',(p,rare))
                self.db.execute('INSERT INTO rare_collection VALUES(?,?,?,?) ON CONFLICT(player,rare) DO UPDATE SET quantity=badd(rare_collection.quantity,excluded.quantity)',(p,rare,found,self.clock()))
        return units

    def _lock_factory(self,p):
        if self.accounts.postgres:
            self.db.execute('SELECT id FROM players WHERE id=? FOR NO KEY UPDATE',(p,))

    def _helper(self,p,now, *, locked=False):
        if self.accounts.postgres and not locked:
            self.db.execute('BEGIN IMMEDIATE')
            self._lock_factory(p)
        f=self._factory(p); end=min(now,f['helper_until'],CLOSE_MS)
        ticks=max(0,(end-f['helper_tick'])//1000)
        if ticks and f['helper_product']:
            self._work(p,f['helper_product'],ticks*20,automatic=True)
            self.db.execute('UPDATE factories SET helper_tick=helper_tick+? WHERE player=?',(ticks*1000,p))

        for h in self.db.execute('SELECT * FROM helpers WHERE player=?',(p,)).fetchall():
            ticks=max(0,(min(now,h['until'],CLOSE_MS)-h['tick'])//1000)
            if ticks:self._work(p,h['product'],ticks*h['rate'],automatic=True);self.db.execute('UPDATE helpers SET tick=tick+? WHERE id=?',(ticks*1000,h['id']))
            if now>=h['until']:self.db.execute('DELETE FROM helpers WHERE id=?',(h['id'],))
        line=self.db.execute('SELECT * FROM autolines WHERE player=?',(p,)).fetchone()
        if line:
            level=self.db.execute("SELECT level FROM equipment WHERE player=? AND kind='islandline'",(p,)).fetchone()[0]
            ticks=max(0,(min(now,CLOSE_MS)-line['tick'])//1000)
            if ticks:self._work(p,line['product'],ticks*10000*5**(level-1),automatic=True);self.db.execute('UPDATE autolines SET tick=tick+? WHERE player=?',(ticks*1000,p))

        return f

    def _multiplier(self,p):
        r=self.db.execute("SELECT level FROM equipment WHERE player=? AND kind='sunpress'",(p,)).fetchone()
        return 10**(r[0] if r else 0)

    def act(self,token,key,kind,product='white',quantity=None,price=None,target_id=None):
        now=self.clock(); p=self.accounts.identity(token,now//1000)['id']
        if kind in ('ship','edit_shipment','cancel_shipment','add_listing','set_price','buy_market'):
            self.settle()
        if not isinstance(key,str) or not 1<=len(key)<=80: raise ValueError('操作IDが必要です。')
        if product not in PRODUCTS: raise ValueError('商品が不正です。')
        payload=json.dumps([kind,product,quantity,price],ensure_ascii=False)
        if target_id is not None: payload=json.dumps([kind,product,quantity,price,target_id],ensure_ascii=False)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self._lock_factory(p)
            now=self.clock()
            old=self.db.execute('SELECT * FROM actions WHERE player=? AND key=?',(p,key)).fetchone()
            if old:
                if old['payload']!=payload: raise ValueError('操作IDが重複しています。')
                self.db.commit(); return json.loads(old['result'])
            if kind=='ack_rare':
                if type(quantity) is not int or not 0<=quantity<len(RARES): raise ValueError('図鑑番号が不正です。')
                self.db.execute('UPDATE rare_firsts SET seen=1 WHERE player=? AND rare=?',(p,RARES[quantity][0]))
                self.db.commit(); return {'acknowledged':True}
            if now>=CLOSE_MS: raise ValueError('イベントは終了しました。')
            if now<self.opens_at: raise ValueError('まだ開催前です。登録して開始を待ちましょう。')
            f=self._helper(p,now,locked=True); result={}
            if kind in ('tap','tap_batch'):
                if now-f['last_tap']<50: raise ValueError('タップ間隔が短すぎます。')
                count=1 if kind=='tap' else quantity
                if type(count) is not int or not 1<=count<=20:
                    raise ValueError('タップ数が範囲外です。')
                work=power(f['tier'])*self._multiplier(p)
                stock=self.db.execute('SELECT work FROM stock WHERE player=? AND product=?',(p,product)).fetchone()
                if stock is None: raise ValueError('この坊主は未解放です。')
                remainder=stock['work']; total_work=0
                results=[]
                for _ in range(count):
                    critical=secrets.randbelow(10)==0
                    effort=work*(5 if critical else 1)
                    total_work+=effort
                    units,remainder=divmod(remainder+effort,PRODUCTS[product][0])
                    results.append({'produced':units,'critical':critical})
                self._work(p,product,total_work)
                result=results[0] if kind=='tap' else {'taps':results}
                if kind=='tap_batch':
                    result['stock']=dict(self.db.execute(
                        'SELECT product,quantity,work FROM stock WHERE player=? AND product=?',
                        (p,product)).fetchone())
                self.db.execute('UPDATE factories SET last_tap=? WHERE player=?',(now,p))
            elif kind in EQUIPMENT:
                level=self.db.execute('SELECT level FROM equipment WHERE player=? AND kind=?',(p,kind)).fetchone();level=level[0] if level else 0
                cost=EQUIPMENT[kind][1]*5**level
                if f['cash']<cost:raise ValueError('所持金が足りません。')
                if kind=='islandline' and not self.db.execute('SELECT 1 FROM stock WHERE player=? AND product=?',(p,product)).fetchone():raise ValueError('この坊主は未解放です。')
                self.db.execute('UPDATE factories SET cash=bsub(cash,?) WHERE player=?',(cost,p));self.db.execute('UPDATE factory_totals SET purchases=badd(purchases,?) WHERE player=?',(cost,p))
                self.db.execute('INSERT INTO equipment VALUES(?,?,1) ON CONFLICT(player,kind) DO UPDATE SET level=equipment.level+1',(p,kind))
                if kind=='islandline':self.db.execute('INSERT INTO autolines VALUES(?,?,?) ON CONFLICT(player) DO UPDATE SET product=excluded.product,tick=excluded.tick',(p,product,now))
                result={'spent':cost}
            elif kind in ('upgrade','unlock','helper'):
                if kind=='upgrade':
                    cost=upgrade_cost(f['tier'])
                elif kind=='unlock':
                    if self.db.execute('SELECT 1 FROM stock WHERE player=? AND product=?',(p,product)).fetchone(): raise ValueError('解放済みです。')
                    cost=PRODUCTS[product][4]
                else:
                    if not self.db.execute('SELECT 1 FROM stock WHERE player=? AND product=?',(p,product)).fetchone(): raise ValueError('未解放です。')
                    cost=150
                if f['cash']<cost: raise ValueError('所持金が足りません。')
                self.db.execute('UPDATE factories SET cash=bsub(cash,?) WHERE player=?',(cost,p))
                self.db.execute('UPDATE factory_totals SET purchases=badd(purchases,?) WHERE player=?',(cost,p))
                if kind=='upgrade': self.db.execute('UPDATE factories SET tier=tier+1 WHERE player=?',(p,))
                elif kind=='unlock': self.db.execute('INSERT INTO stock(player,product) VALUES(?,?)',(p,product))
                else:self.db.execute('INSERT INTO helpers VALUES(?,?,?,?,?,?)',(secrets.token_hex(16),p,product,now+20000,now,20))
                result={'spent':cost}
            elif kind in ('bank_lend','bank_borrow','bank_withdraw','bank_repay'):
                result=bank.player_action(self.db,p,kind,quantity,now,CLOSE_MS)
            elif kind=='buy_market':
                result=self._buy_market(p,product,quantity,price,now)
            elif kind in ('add_listing','set_price'):
                existing=self.db.execute('SELECT * FROM listings WHERE player=? AND product=?',(p,product)).fetchone()
                if type(price) is not int or not 1<=price<=99999:raise ValueError('販売価格は1〜99,999円で指定してください。')
                if kind=='set_price':
                    if not existing:raise ValueError('販売中の商品がありません。')
                    self.db.execute('UPDATE listings SET price=? WHERE id=?',(price,existing['id']))
                    result={'updated':existing['id']}
                else:
                    if type(quantity) is not int or quantity<1:raise ValueError('追加する個数を入力してください。')
                    total=quantity+(existing['quantity'] if existing else 0)
                    result=self._reserve_shipment(p,product,total,price,now,existing)
            elif kind in ('ship','edit_shipment','cancel_shipment'):
                existing=None
                if kind!='ship':
                    existing=self.db.execute('SELECT * FROM listings WHERE id=? AND player=? AND product=?',(target_id,p,product)).fetchone()
                    if not existing: raise ValueError('変更できる出荷がありません。売り切れ、または回収済みです。')
                if kind=='cancel_shipment':
                    self.db.execute('UPDATE stock SET quantity=badd(quantity,?) WHERE player=? AND product=?',(existing['quantity'],p,product))
                    self.db.execute('DELETE FROM listings WHERE id=?',(existing['id'],))
                    result={'cancelled':existing['id']}
                else:
                    result=self._reserve_shipment(p,product,quantity,price,now,existing)
            else: raise ValueError('操作が不正です。')
            self.db.execute('INSERT INTO actions VALUES(?,?,?,?)',(p,key,payload,json.dumps(result)))
            self.db.commit(); return result
        except Exception:
            self.db.rollback(); raise

    @staticmethod
    def _market_purchase_rows(rows):
        """Skip the cheapest quarter of units; keep exact boundary quantities."""
        skip = sum(row['quantity'] for row in rows) // 4
        eligible = []
        for row in sorted(rows, key=lambda row: (row['price'], row.get('accepted', 0), row.get('id', ''))):
            excluded = min(skip, row['quantity'])
            skip -= excluded
            available = row['quantity'] - excluded
            if available:
                eligible.append((row, available))
        return eligible

    @staticmethod
    def _market_quote(rows):
        total = sum(row['quantity'] for row in rows)
        if not total:
            return {'quantity': 0, 'price': None}
        value = sum(row['quantity'] * row['price'] for row in rows)
        price = (2 * value + total) // (2 * total)
        return {'quantity': total - total // 4,
                'price': price}

    def market_quotes(self, player):
        offers = {product: [] for product in PRODUCTS}
        for row in self.db.execute('SELECT product,quantity,price FROM listings WHERE player<>?', (player,)):
            offers[row['product']].append(row)
        return {product: self._market_quote(rows) for product, rows in offers.items()}

    def _credit_sale(self, row, count, cost, now, sale_id, config):
        player = row['player']
        if player == bank.BANK:
            return
        self._lock_factory(player)
        price = row['price']
        tax = bank.record_tax(self.db, player, count * price, config)
        self.db.execute('INSERT INTO sales VALUES(?,?,?,?,?,?,?,?)',
                        (sale_id, player, row['product'], count, price, cost, row['accepted'], now))
        self.db.execute('UPDATE factories SET cash=badd(cash,?) WHERE player=?',
                        (count * (price - cost) - tax, player))

    def _buy_market(self, player, product, quantity, price, now):
        if type(quantity) is not int or quantity < 1 or type(price) is not int:
            raise ValueError('購入する個数と価格を確認してください。')
        rows = self.db.execute('''SELECT id,player,product,quantity,price,accepted FROM listings
            WHERE product=? AND player<>? ORDER BY price,accepted,id''', (product, player)).fetchall()
        quote = self._market_quote(rows)
        average = quote['price']
        if quantity > quote['quantity']:
            raise ValueError('購入対象の個数が不足しています。もう一度確認してください。')
        if price != average:
            raise ValueError('平均販売値が変わりました。価格を確認してから購入してください。')
        if not self.db.execute('SELECT 1 FROM stock WHERE player=? AND product=?', (player, product)).fetchone():
            raise ValueError('先に強化画面でこの坊主を解放してください。')
        spent = quantity * average
        if self.db.execute('UPDATE factories SET cash=bsub(cash,?) WHERE player=? AND bge(cash,?)',
                           (spent, player, spent)).rowcount != 1:
            raise ValueError('所持金が足りません。')

        remaining = quantity
        cost = PRODUCTS[product][2]
        config = bank.settings(self.db)
        for row, available in self._market_purchase_rows([dict(row) for row in rows]):
            sold = min(remaining, available)
            self._credit_sale(row, sold, cost, now, secrets.token_hex(16), config)
            if sold == row['quantity']:
                self.db.execute('DELETE FROM listings WHERE id=?', (row['id'],))
            else:
                self.db.execute('UPDATE listings SET quantity=bsub(quantity,?) WHERE id=?', (sold, row['id']))
            remaining -= sold
            if not remaining:
                break
        self.db.execute('UPDATE stock SET quantity=badd(quantity,?) WHERE player=? AND product=?', (quantity, player, product))
        self.db.execute('UPDATE factory_totals SET purchases=badd(purchases,?) WHERE player=?', (spent, player))
        return {'spent': spent, 'bought': quantity, 'price': average}

    def _reserve_shipment(self,p,product,quantity,price,now,existing):
                if type(quantity) is not int or quantity<1 or type(price) is not int or not 1<=price<=99999: raise ValueError('数量・価格が範囲外です。')
                if existing:
                    self.db.execute('UPDATE stock SET quantity=badd(quantity,?) WHERE player=? AND product=?',(existing['quantity'],p,product))
                if self.db.execute('UPDATE stock SET quantity=bsub(quantity,?) WHERE player=? AND product=? AND bge(quantity,?)',(quantity,p,product,quantity)).rowcount!=1: raise ValueError('在庫が足りません。')
                if existing:
                    self.db.execute('UPDATE listings SET quantity=?,price=? WHERE id=?',(quantity,price,existing['id']))
                    return {'shipment_id':existing['id']}
                order=secrets.token_hex(16)
                self.db.execute('INSERT INTO listings VALUES(?,?,?,?,?,?,?)',(order,p,product,quantity,price,now,now//60000))
                return {'shipment_id':order}

    def settle(self, *, background=False):
        now=self.clock()
        end=min(now,CLOSE_MS)//60000
        last=self.db.execute('SELECT last FROM market_cursor WHERE id=1').fetchone()[0]
        if last>=end-1:
            return
        self.db.execute('BEGIN IMMEDIATE')
        try:
            last=self.db.execute('SELECT last FROM market_cursor WHERE id=1').fetchone()[0]
            if self.accounts.postgres:
                first_listing = self.db.execute('SELECT MIN(round) FROM listings').fetchone()[0]
                empty_end = min(end, first_listing) if first_listing is not None else end
                if empty_end > last + 1:
                    self.db.execute('''INSERT INTO market_ticks
                        SELECT minute, product, '', 0, 0, 0, 0
                        FROM generate_series(CAST(? AS bigint), CAST(? AS bigint)) AS minute
                        CROSS JOIN (VALUES ('white'), ('sea'), ('shisa')) AS products(product)
                        ON CONFLICT DO NOTHING''',(last+1,empty_end-1))
                    last=empty_end-1
                    self.db.execute('UPDATE market_cursor SET last=? WHERE id=1',(last,))
                    self.db.commit()
                    if last>=end-1:
                        return False
                    self.db.execute('BEGIN IMMEDIATE')
            limit = min(end,last+2) if self.accounts.postgres else end
            config = bank.settings(self.db)
            for batch in range(last+1,limit):
                for product,(_,_,cost,_,_) in PRODUCTS.items():
                    rows=self.db.execute('SELECT * FROM listings WHERE product=? AND round<=? ORDER BY accepted,id',(product,batch)).fetchall()
                    elapsed = batch % 60 + 1
                    sold_this_hour = sum(row[0] for row in self.db.execute(
                        "SELECT sold FROM market_ticks WHERE player='' AND product=? AND round>=? AND round<?",
                        (product,batch-elapsed+1,batch))) if rows and elapsed>1 else 0
                    sold=allocate_hourly([(r['quantity'],r['price']) for r in rows],sold_this_hour,elapsed,config['demand_bps'])
                    for r,count in zip(rows,sold):
                        if count:
                            self._credit_sale(r,count,cost,(batch+1)*60000,r['id']+':'+str(batch),config)
                        remaining=r['quantity']-count
                        self.db.execute('INSERT INTO market_ticks VALUES(?,?,?,?,?,?,?)',(batch,product,r['player'],count,count*r['price'],remaining,count*cost))
                        if remaining:self.db.execute('UPDATE listings SET quantity=? WHERE id=?',(remaining,r['id']))
                        else:self.db.execute('DELETE FROM listings WHERE id=?',(r['id'],))
                    if rows:self.db.execute('INSERT OR REPLACE INTO market_history VALUES(?,?,?,?,?,?)',(batch,product,sum(r['quantity'] for r in rows),sum(sold),sum(r['price']*n for r,n in zip(rows,sold)),len(rows)))
                    self.db.execute('INSERT INTO market_ticks VALUES(?,?,?,?,?,?,?)',(batch,product,'',sum(sold),sum(r['price']*n for r,n in zip(rows,sold)),sum(r['quantity']-n for r,n in zip(rows,sold)),sum(sold)*cost))
                self.db.execute('UPDATE market_cursor SET last=? WHERE id=1',(batch,))
            self.db.commit()
            if self.accounts.postgres and limit<end:
                if not background:
                    raise ValueError('市場を更新中です。少し待ってから出荷または価格変更をお試しください。')
                return True
            return False
        except Exception:
            self.db.rollback();raise

    def breakdown(self,token):
        p=self.accounts.identity(token,self.clock()//1000)['id']
        if self.accounts.postgres:
            income=[{'key':r['product_id'],'amount':r['amount']} for r in self.db.execute('SELECT product_id,SUM(sold_quantity*unit_price) amount FROM sales WHERE player_id=? GROUP BY product_id',(p,))]
            materials=self.db.execute('SELECT COALESCE(SUM(sold_quantity*unit_cost),0) FROM sales WHERE player_id=?',(p,)).fetchone()[0]
        else:
            totals={}; materials=0
            for row in self.db.execute('SELECT product_id,sold_quantity,unit_price,unit_cost FROM sales WHERE player_id=?',(p,)):
                totals[row['product_id']]=totals.get(row['product_id'],0)+row['sold_quantity']*row['unit_price']
                materials+=row['sold_quantity']*row['unit_cost']
            income=[{'key':product,'amount':amount} for product,amount in totals.items()]
        costs={'materials':materials,'upgrade':0,'unlock':0,'helper':0,'sunpress':0,'islandline':0,'buy_market':0}
        for r in self.db.execute('SELECT payload,result FROM actions WHERE player=?',(p,)):
            kind=json.loads(r['payload'])[0]
            if kind in costs and kind!='materials':costs[kind]+=json.loads(r['result']).get('spent',0)
        return {'income':income,'expense':[{'key':k,'amount':v} for k,v in costs.items()]}

    def timeline(self,token):
        p=self.accounts.identity(token,self.clock()//1000)['id']
        return [dict(r) for r in self.db.execute("SELECT * FROM market_ticks WHERE player IN ('',?) ORDER BY round DESC LIMIT 130000",(p,))]

    def state(self,token, *, sync_inventory=True):
        now=self.clock(); p=self.accounts.identity(token,now//1000)['id']
        if sync_inventory:
            with self.db: self._helper(p,now)
        f=dict(self._factory(p)); self.db.commit(); f.pop('player')
        f['stock']=[dict(r) for r in self.db.execute('SELECT product,quantity,work FROM stock WHERE player=?',(p,))]
        f['shipments']=[dict(r) for r in self.db.execute('SELECT id,product,quantity,price,round FROM listings WHERE player=?',(p,))]
        discoveries={r['rare']:dict(r) for r in self.db.execute('''
            SELECT c.rare,c.quantity,c.discovered,f.seen,
              CASE WHEN f.id IS NOT NULL THEN
                (SELECT COUNT(*) FROM rare_firsts WHERE rare=f.rare AND id<=f.id)
              END AS discovery_rank
            FROM rare_collection c LEFT JOIN rare_firsts f
              ON f.player=c.player AND f.rare=c.rare WHERE c.player=?''',(p,))}
        f['collection']=[]
        for rid,name,odds in RARES:
            found=discoveries.get(rid,{})
            f['collection'].append({'id':rid,'name':name,'odds':odds,
                'quantity':found.get('quantity',0),'discovered':found.get('discovered'),
                'unseen':found.get('seen')==0,'discovery_rank':found.get('discovery_rank')})
        levels={r['kind']:r['level'] for r in self.db.execute('SELECT kind,level FROM equipment WHERE player=?',(p,))}
        f['tap_power']=power(f['tier'])*10**levels.get('sunpress',0)
        f['upgrade_cost']=upgrade_cost(f['tier'])
        f['auto_totals']={r['product']:r['quantity'] for r in self.db.execute('SELECT product,quantity FROM auto_totals WHERE player=?',(p,))}
        f['helpers']=[dict(r) for r in self.db.execute('SELECT product,until,rate FROM helpers WHERE player=?',(p,))]
        line=self.db.execute('SELECT product FROM autolines WHERE player=?',(p,)).fetchone();f['auto_product']=line[0] if line else None
        f['equipment']=[]
        for kind,(name,base) in EQUIPMENT.items():
            level=levels.get(kind,0)
            f['equipment'].append({'kind':kind,'name':name,'level':level,'cost':base*5**level,'rate':(10000*5**(level-1) if level and kind=='islandline' else 0)})
        return f

    def event(self):
        now=self.clock()
        return {'opens_at':self.opens_at,'departure_day':DEPARTURE_MS,'closes_at':CLOSE_MS,
                'phase':'before' if now<self.opens_at else 'closed' if now>=CLOSE_MS else 'open',
                'practice':self.opens_at==0}

    def history(self):
        if self.accounts.postgres:
            return [dict(r) for r in self.db.execute('SELECT round,product,offered,sold,sellers,CASE WHEN sold=0 THEN NULL ELSE revenue*1.0/sold END average_price FROM market_history ORDER BY round DESC LIMIT 180')]
        rows=self.db.execute('SELECT round,product,offered,sold,sellers,revenue FROM market_history ORDER BY round DESC LIMIT 180')
        return [{**dict(row),'average_price':float(F(row['revenue'],row['sold'])) if row['sold'] else None}
                for row in rows]

    def rankings(self,metric='manufactured', *, settle=True):
        return self.rankings_many((metric,), settle=settle)[metric]

    def rankings_many(self,metrics, *, settle=True):
        # Catch up EVERY helper, including factories whose owners are offline.
        if settle:
            self.settle()
        now=self.clock()
        for row in self.db.execute(self.active_helpers_query).fetchall():
            with self.db:
                self._helper(row['player'],now)
        return self.accounts.rankings_many(metrics)
