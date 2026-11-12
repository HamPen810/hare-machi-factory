"""Apply tested extreme-integer and connection-pool fixes to the existing ZIP."""
import io
import sys
import zipfile
from pathlib import Path

archive = Path("hare-machi-render.zip")
targets = ("accounts.py", "market.py", "postgres.py", "bank.py",
           "exact.py", "static/numbers.js", "static/app.js", "static/admin.js")
with zipfile.ZipFile(archive) as source:
    original = {name: source.read(name).decode("utf-8").replace("\r\n", "\n") for name in targets}
edited = dict(original)

def replace(name, before, after):
    text = edited[name]
    if text.count(before) != 1:
        raise RuntimeError("Expected exactly one original block in " + name + ": " + before[:60])
    edited[name] = text.replace(before, after)

name = "market.py"
replace(name, "import random\n", "import random\nfrom math import isqrt\n")
start = edited[name].index("def rare_count(units, odds):")
end = edited[name].index("def power(tier):", start)
if "rng.binomialvariate(units, 1 / factor)" not in edited[name][start:end]:
    raise RuntimeError("Unexpected rare_count implementation; refusing deployment")
new_sampler = '''def _binomial_bigint(units, denominator):
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

'''
edited[name] = edited[name][:start] + new_sampler + edited[name][end:]
replace(name, "COALESCE((SELECT SUM(sold_quantity) FROM sales WHERE player_id=?),0)",
        "COALESCE((SELECT bsum(sold_quantity) FROM sales WHERE player_id=?),0)")
replace(name,
"""        income=[{'key':r['product_id'],'amount':r['amount']} for r in self.db.execute('SELECT product_id,SUM(sold_quantity*unit_price) amount FROM sales WHERE player_id=? GROUP BY product_id',(p,))]
        costs={'materials':self.db.execute('SELECT COALESCE(SUM(sold_quantity*unit_cost),0) FROM sales WHERE player_id=?',(p,)).fetchone()[0],'upgrade':0,'unlock':0,'helper':0,'sunpress':0,'islandline':0,'buy_market':0}""",
"""        if self.accounts.postgres:
            income=[{'key':r['product_id'],'amount':r['amount']} for r in self.db.execute('SELECT product_id,SUM(sold_quantity*unit_price) amount FROM sales WHERE player_id=? GROUP BY product_id',(p,))]
            materials=self.db.execute('SELECT COALESCE(SUM(sold_quantity*unit_cost),0) FROM sales WHERE player_id=?',(p,)).fetchone()[0]
        else:
            totals={}; materials=0
            for row in self.db.execute('SELECT product_id,sold_quantity,unit_price,unit_cost FROM sales WHERE player_id=?',(p,)):
                totals[row['product_id']]=totals.get(row['product_id'],0)+row['sold_quantity']*row['unit_price']
                materials+=row['sold_quantity']*row['unit_cost']
            income=[{'key':product,'amount':amount} for product,amount in totals.items()]
        costs={'materials':materials,'upgrade':0,'unlock':0,'helper':0,'sunpress':0,'islandline':0,'buy_market':0}""")
replace(name,
"""    def history(self):
        return [dict(r) for r in self.db.execute('SELECT round,product,offered,sold,sellers,CASE WHEN sold=0 THEN NULL ELSE revenue*1.0/sold END average_price FROM market_history ORDER BY round DESC LIMIT 180')]""",
"""    def history(self):
        if self.accounts.postgres:
            return [dict(r) for r in self.db.execute('SELECT round,product,offered,sold,sellers,CASE WHEN sold=0 THEN NULL ELSE revenue*1.0/sold END average_price FROM market_history ORDER BY round DESC LIMIT 180')]
        rows=self.db.execute('SELECT round,product,offered,sold,sellers,revenue FROM market_history ORDER BY round DESC LIMIT 180')
        return [{**dict(row),'average_price':float(F(row['revenue'],row['sold'])) if row['sold'] else None}
                for row in rows]""")

name = "accounts.py"
replace(name, "if not 0<=quantity<=10**9 or not 1<=price<=99999 or not 0<=cost<=99999:",
        "if not quantity>=0 or not 1<=price<=99999 or not 0<=cost<=99999:")
replace(name,
"""        return [dict(row) for row in self.db.execute('''SELECT product_id,sold_quantity,unit_price,
          sold_quantity*unit_price revenue,sold_quantity*unit_cost material_cost,
          CASE WHEN sold_quantity=0 THEN NULL ELSE (unit_price-unit_cost)*1.0/unit_price END margin,
          accepted_at,settled_at FROM sales WHERE player_id=? ORDER BY settled_at DESC''',(player['id'],))]""",
"""        if not self.postgres:
            return [{**dict(row), 'revenue': row['sold_quantity']*row['unit_price'],
                     'material_cost':row['sold_quantity']*row['unit_cost'],
                     'margin':(row['unit_price']-row['unit_cost'])/row['unit_price']}
                    for row in self.db.execute('''SELECT product_id,sold_quantity,unit_price,unit_cost,
                      accepted_at,settled_at FROM sales WHERE player_id=? ORDER BY settled_at DESC''',(player['id'],))]
        return [dict(row) for row in self.db.execute('''SELECT product_id,sold_quantity,unit_price,
          sold_quantity*unit_price revenue,sold_quantity*unit_cost material_cost,
          CASE WHEN sold_quantity=0 THEN NULL ELSE (unit_price-unit_cost)*1.0/unit_price END margin,
          accepted_at,settled_at FROM sales WHERE player_id=? ORDER BY settled_at DESC''',(player['id'],))]""")

name = "postgres.py"
replace(name,
"""@lru_cache(maxsize=4)
def connection_pool(url, auth_only=False, admin_only=False):
    from psycopg_pool import ConnectionPool""",
"""@lru_cache(maxsize=4)
def _shared_connection_pool(url):
    from psycopg_pool import ConnectionPool""")
replace(name,
"""    return ConnectionPool(
        url, min_size=1, max_size=2 if admin_only else 1 if auth_only else 4, timeout=5, open=True,""",
"""    # Share the pool between auth, admin and market, avoiding Supabase exhaustion.
    return ConnectionPool(
        url, min_size=0, max_size=2, timeout=20, max_idle=20, open=True,""")
replace(name, "\n\nclass Postgres:\n",
""" 

def connection_pool(url, auth_only=False, admin_only=False):
    return _shared_connection_pool(url)


class Postgres:
""")
replace(name, "else float(value) if isinstance(value, Decimal)",
        "else (str(value) if value.adjusted() > 300 else float(value)) if isinstance(value, Decimal)")

name = "exact.py"
replace(name,"import sqlite3\n",
"""import sqlite3
import sys
# Extremely large exact integer counters must remain JSON-serializable.
if hasattr(sys, "set_int_max_str_digits"):
 sys.set_int_max_str_digits(0)
""")
replace("bank.py", "len(value) <= 1010", "len(value) <= 10010")
replace("bank.py", "len(digits) + shift <= 1000", "len(digits) + shift <= 10000")
replace("static/numbers.js", "input.length > 1010", "input.length > 10010")
replace("static/numbers.js", "digits.length + shift <= 1000", "digits.length + shift <= 10000")
replace("static/app.js", "g.inventory=Number(r.inventory);g.inventoryExact=r.inventory;",
        "g.inventory=big(r.inventory);g.inventoryExact=r.inventory;")
replace("static/app.js",
"""const values=countMetric ? counts.map(value => Number(value * 1000000n / maxCount) / 1000000) : shown.map(r=>metric==='price'?(r.sold?Number(r.revenue)/Number(r.sold):null):metric==='margin'?(r.revenue?Number(r.revenue-r.cost)/Number(r.revenue)*100:null):Number(r[metric]));const valid=values.filter(v=>v!==null),unit=metric==='price'?'円':metric==='margin'?'%':'個';""",
"""// Normalize exact integers first, before Number conversion, to avoid Infinity.
 const ratio=(numerator,denominator,precision=1000000n)=>denominator===0n?null:Number(numerator*precision/denominator)/Number(precision);
 const values=countMetric ? counts.map(value => ratio(value,maxCount)) : shown.map(r=>metric==='price'?(r.sold?ratio(r.revenue,r.sold):null):metric==='margin'?(r.revenue?ratio((r.revenue-r.cost)*100n,r.revenue):null):ratio(big(r[metric]),1n));const valid=values.filter(v=>v!==null&&Number.isFinite(v)),unit=metric==='price'?'円':metric==='margin'?'%':'個';""")
replace("static/admin.js", "fmt(Number(r.average_price.toFixed(2)))+'円'",
        "fmt(Number(Number(r.average_price).toFixed(2)))+'円'")

# All checks occur before rewriting the archive: failures leave it unchanged.
import ast
for name in targets:
    if name.endswith(".py"):
        ast.parse(edited[name],filename=name)
out = io.BytesIO()
with zipfile.ZipFile(archive) as source, zipfile.ZipFile(out, "w") as destination:
    destination.comment = source.comment
    for member in source.infolist():
        payload = edited[member.filename].encode("utf-8") if member.filename in edited else source.read(member)
        destination.writestr(member, payload)
with zipfile.ZipFile(io.BytesIO(out.getvalue())) as check:
    assert check.testzip() is None
    for name in targets:
        assert check.read(name).decode("utf-8") == edited[name]
archive.write_bytes(out.getvalue())
print("Extreme number stability fixes successfully applied")
