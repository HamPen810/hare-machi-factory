"""Relieve market database saturation without modifying any existing records.

1) Market operations no longer perform settlement catch-up inside the player's
   critical action. The dedicated timer is the only settlement worker.
2) The sales-history API pages the latest 60 records instead of returning all
   multi-thousand-digit historic rows every request. Full database is preserved.
3) Cache expensive per-player lifetime revenue for 15 seconds during frequent
   /api/factory polling (cash and actual trade data are NOT cached).
4) Record settlement failure SQLSTATE (not SQL text, credentials or personal data).
"""
from pathlib import Path
from zipfile import ZipFile
import os,tempfile

zipname=Path('hare-machi-render.zip')
with ZipFile(zipname) as z:items=[(info,z.read(info.filename)) for info in z.infolist()]

def change(path,old,new):
    for i,(info,raw) in enumerate(items):
        if info.filename != path:continue
        source=raw.decode('utf-8')
        if source.count(old)!=1:
            if old not in source and new in source:return
            raise RuntimeError(f'{path}: pattern count {source.count(old)} for {old[:100]!r}')
        items[i]=(info,source.replace(old,new).encode('utf-8'))
        return
    raise RuntimeError(f'Archive lacks {path}')

# Market timer performs settlement separately, preserving existing exact
# settlement code, tax rules and database transaction semantics.
change('market.py',
'''        if kind in ('ship','edit_shipment','cancel_shipment','add_listing','set_price','buy_market'):
            self.settle()
        if not isinstance(key,str)''',
'''        # Market settlement belongs to the timer, not the synchronous trade.
        # Otherwise a backlogged settlement holds the global DB writer lock
        # and causes player actions to fail with PoolTimeout.
        if not isinstance(key,str)''')

# Only modify the PostgreSQL branch. The SQLite branch remains unchanged.
change('accounts.py',
'''accepted_at,settled_at FROM sales WHERE player_id=? ORDER BY settled_at DESC''',(player['id'],))]''',
'''accepted_at,settled_at FROM sales WHERE player_id=? ORDER BY settled_at DESC LIMIT 60''',(player['id'],))]''')

# The computed ranking/revenue is non-authoritative UI information. Cache only
# this expensive SQL aggregate, and make the cache bounded and short-lived.
change('server.py',
'''    hybrid=HybridRouter()
    settings_lock=threading.Lock()''',
'''    hybrid=HybridRouter()
    revenue_lock=threading.Lock()
    revenue_cache={}
    def cached_lifetime_revenue(db,player):
        now=time.monotonic()
        with revenue_lock:
            hit=revenue_cache.get(player)
            if hit is not None and now-hit[0]<15:
                return hit[1]
        value=db.execute(
            'SELECT COALESCE(SUM(sold_quantity*unit_price),0) FROM sales WHERE player_id=?',
            (player,)).fetchone()[0]
        with revenue_lock:
            revenue_cache[player]=(now,value)
            if len(revenue_cache)>400:
                stale=[key for key,(t,_) in revenue_cache.items() if now-t>20]
                for key in stale:revenue_cache.pop(key,None)
                if len(revenue_cache)>500:
                    revenue_cache.clear()
        return value
    settings_lock=threading.Lock()''')
change('server.py',
'''revenue=a.db.execute('SELECT COALESCE(SUM(sold_quantity*unit_price),0) FROM sales WHERE player_id=?',(identity['id'],)).fetchone()[0]''',
'''revenue=cached_lifetime_revenue(a.db,identity['id'])''')
change('server.py',
'''logging.warning('Market settlement failed (%s)', type(error.__cause__ or error).__name__)''',
'''logging.warning('Market settlement failed (%s, SQLSTATE %s)',type(error.__cause__ or error).__name__,
                                getattr(error.__cause__ or error,'sqlstate',None))''')

fd,tmp=tempfile.mkstemp(prefix='.market-db-relief-',suffix='.zip',dir='.')
os.close(fd)
try:
    with ZipFile(tmp,'w') as z:
        for info,raw in items:z.writestr(info,raw)
    os.replace(tmp,zipname)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print('Market settlement now independent of player actions; read load reduced.')
