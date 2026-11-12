"""Loopback-only development server. Not a production Internet server."""
from exact import wire
import bank
import argparse
import gzip
import hashlib
import json
import logging
import sqlite3
import os
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from functools import lru_cache
from pathlib import Path
from accounts import Accounts
from market import Game
from event import OPEN_MS
from admin import Admin
from weather import forecast
from inventory_cluster import InventoryCluster

STATIC=Path(__file__).with_name('static')
STATIC_ASSET_CACHE='public, max-age=3600, must-revalidate'
STATIC_CODE_CACHE='public, no-cache'
MAINTENANCE=os.environ.get('HARE_FACTORY_MAINTENANCE','1')!='0'
API_PATHS={'/api/login','/api/register','/api/logout','/api/name','/api/action','/api/snapshot',
           '/api/factory','/api/ranks','/api/data','/api/market','/api/market-quotes','/api/bank'}

def make_server(path,port=8766,clock=None,practice=False,public_origin=None,bind="127.0.0.1", cluster=None):
    if public_origin:
        from urllib.parse import urlsplit
        u=urlsplit(public_origin)
        if u.scheme!="https" or not u.hostname or u.path or u.query or u.fragment:raise ValueError("Exact HTTPS public origin required")
    settings_lock=threading.Lock()
    settings_cache=None

    def site_settings():
        nonlocal settings_cache
        with settings_lock:
            if settings_cache is None:
                account=Accounts(path,read_only=True,admin_only=True)
                try:
                    settings_cache=Admin(account).initialize(MAINTENANCE and not practice)
                finally:
                    account.db.close()
            return settings_cache

    @lru_cache(maxsize=40)
    def static_etag(relative_path, mtime_ns, size):
        """ETag is content-based; mtime and size invalidate this process's cache."""
        data=(STATIC/relative_path).read_bytes()
        return 'W/"'+hashlib.sha256(data).hexdigest()+'"'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,status,body,cookie=None,kind='application/json; charset=utf-8',
                  cache_control='no-store',etag=None):
            data=json.dumps(wire(body),ensure_ascii=False).encode() if kind.startswith('application/json') else body
            compressed=False
            compressible=kind.startswith(('application/json','text/'))
            if status==200 and compressible and len(data)>=1024:
                accept=self.headers.get('Accept-Encoding','')
                for option in accept.split(','):
                    parts=[part.strip().lower() for part in option.split(';')]
                    if parts[0]!='gzip':
                        continue
                    quality=1.0
                    for part in parts[1:]:
                        if part.startswith('q='):
                            try:quality=float(part[2:])
                            except ValueError:quality=0.0
                    if not quality>0:
                        break
                    zipped=gzip.compress(data,compresslevel=5,mtime=0)
                    if len(zipped)<len(data):
                        data=zipped
                        compressed=True
                    break
            self.send_response(status)
            if status!=304:
                self.send_header('Content-Type',kind)
                self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control',cache_control)
            if etag:self.send_header('ETag',etag)
            if compressible:self.send_header('Vary','Accept-Encoding')
            if compressed:self.send_header('Content-Encoding','gzip')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' https://api.open-meteo.com; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if cookie:self.send_header('Set-Cookie',cookie+('; Secure' if public_origin else ''))
            self.end_headers()
            if status!=304:self.wfile.write(data)

        def static_reply(self,relative_path,kind,cache_control):
            file=STATIC/relative_path
            stat=file.stat()
            etag=static_etag(relative_path,stat.st_mtime_ns,stat.st_size)
            if self.headers.get('If-None-Match','')==etag:
                return self.reply(304,b'',kind=kind,cache_control=cache_control,etag=etag)
            return self.reply(200,file.read_bytes(),kind=kind,cache_control=cache_control,etag=etag)
        def process(self,write):
            started=time.monotonic()
            try:
                self.route(write)
            finally:
                elapsed=time.monotonic()-started
                if self.path in API_PATHS and elapsed>=1:
                    logging.warning('Slow request %s %.3fs',self.path,elapsed)

        def route(self,write):
            origin=public_origin or f'http://127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host')!=origin.split('://',1)[1]:
                return self.reply(403,{'error':'このサーバーはローカル専用です。'})
            if write and self.headers.get('Origin')!=origin:
                return self.reply(403,{'error':'別サイトからの操作を拒否しました。'})
            if cluster and not write and self.path == '/health':
                return self.reply(200, {'ok': True})
            if cluster and cluster.role != 'A':
                return self.reply(404, {'error':'見つかりません。'})
            admin_route=self.path.startswith('/api/admin/')
            if self.path=='/' or self.path.startswith('/api/'):
                try:
                    settings=site_settings()
                except sqlite3.Error:
                    return self.reply(503,{'error':'設定を読み込めませんでした。'})
                if not write and self.path=='/api/site':
                    return self.reply(200,settings)
                if settings['maintenance'] and self.path.startswith('/api/') and not admin_route:
                    return self.reply(503,{'maintenance':True,'error':'サーバーメンテナンス中です。再開までお待ちください。'})
            if not write and self.path == '/api/weather':return self.reply(200,forecast())
            if not write and self.path == '/fonts/Yomogi-Regular.ttf':
                return self.static_reply('fonts/Yomogi-Regular.ttf','font/ttf',STATIC_ASSET_CACHE)
            assets={'/assets/teramoto-bozu.png':'teramoto-bozu.png','/assets/mikka-bozu.png':'mikka-bozu.png','/assets/koyama-bozu.png':'koyama-bozu.png','/assets/yamada-bozu.png':'yamada-bozu.png','/assets/sea-yokai.png':'sea-yokai.png','/assets/shisa-doll.png':'shisa-doll.png','/assets/island-background.png':'island-background.png','/assets/teru-painted.png':'teru-painted.png','/assets/shisa-painted.png':'shisa-painted.png'}
            if not write and self.path in assets:
                return self.static_reply('assets/'+assets[self.path],'image/png',STATIC_ASSET_CACHE)
            if not write and self.path in ('/','/weather.js','/app.js','/numbers.js','/polish.css','/island.css','/tabs.js','/polish.js','/admin','/admin/','/admin.js'):
                file={'/weather.js':'weather.js','/':'index.html','/app.js':'app.js','/numbers.js':'numbers.js','/polish.css':'polish.css','/island.css':'island.css','/tabs.js':'tabs.js','/polish.js':'polish.js','/admin':'admin.html','/admin/':'admin.html','/admin.js':'admin.js'}[self.path]
                kind='text/html; charset=utf-8' if file.endswith('html') else 'text/css; charset=utf-8' if file.endswith('css') else 'text/javascript; charset=utf-8'
                if file.endswith('html'):
                    payload=(STATIC/file).read_bytes()
                    if file=='index.html' and not settings['maintenance']:
                        payload=payload.replace(b'id="maintenance-note"',b'id="maintenance-note" hidden').replace(b'action="/api/login" hidden',b'action="/api/login"')
                    return self.reply(200,payload,kind=kind)
                return self.static_reply(file,kind,STATIC_CODE_CACHE)
            a=None
            try:
                data={}
                if write:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=(60000 if self.path=='/api/admin/settings' else 4096): return self.reply(413,{'error':'送信内容が大きすぎます。'})
                    data=json.loads(self.rfile.read(size))
                    if not isinstance(data,dict): raise ValueError('入力形式が不正です。')
                cookies=SimpleCookie(); cookies.load(self.headers.get('Cookie',''))
                token=cookies['session'].value if 'session' in cookies else ''
                if self.path in API_PATHS - {'/api/login','/api/register'} and not token:
                    return self.reply(401,{'error':'ログインしてください。'})
                read_only=not write and self.path in ('/api/data','/api/market','/api/ranks','/api/market-quotes','/api/bank')
                player_only = (write and self.path == '/api/name') or (not write and self.path == '/api/factory') or (
                    write and self.path == '/api/action' and
                    data.get('kind') not in ('ship','edit_shipment','cancel_shipment','add_listing','set_price','buy_market'))
                a=Accounts(path, auth_only=write and self.path in ('/api/login','/api/register','/api/logout'),
                           read_only=read_only or player_only or admin_route,admin_only=admin_route)
                now=clock() if clock else int(time.time()*1000)
                if self.path.startswith('/api/admin/'):
                    admin=Admin(a)
                    admin_token=cookies['admin_session'].value if 'admin_session' in cookies else ''
                    if write and self.path=='/api/admin/login':
                        admin_token=admin.login(data.get('password'),now//1000)
                        return self.reply(200,{'ok':True},f'admin_session={admin_token}; HttpOnly; SameSite=Strict; Path=/api/admin; Max-Age=3600')
                    if not admin.authorized(admin_token,now//1000):return self.reply(401,{'error':'管理者ログインが必要です。'})
                    if write and self.path=='/api/admin/logout':
                        admin.logout(admin_token)
                        return self.reply(200,{'ok':True},'admin_session=; HttpOnly; SameSite=Strict; Path=/api/admin; Max-Age=0')
                    if not write and self.path=='/api/admin/settings':
                        return self.reply(200,{**site_settings(),'default_rulebook':Path(__file__).with_name('rules-default.txt').read_text(encoding='utf8')})
                    if write and self.path=='/api/admin/settings':
                        nonlocal settings_cache
                        with settings_lock:
                            settings_cache=admin.update_settings(data.get('field'),data.get('value'))
                            updated=settings_cache
                        return self.reply(200,updated)
                    if write and self.path=='/api/admin/player':
                        if not a.postgres and data.get('operation')=='reset':
                            Game(a,clock,opens_at=0 if practice else OPEN_MS)
                        return self.reply(200,admin.player(data.get('student_id'),data.get('operation')))
                    if self.path=='/api/admin/bank':
                        if not write:
                            offers=[dict(row) for row in a.db.execute(
                                'SELECT product,quantity,price FROM listings WHERE player=?',(bank.BANK,))]
                            return self.reply(200,{'settings':bank.settings(a.db),'offers':offers})
                        return self.reply(200,bank.admin_action(Game(a,clock,opens_at=0 if practice else OPEN_MS,read_only=True),data))
                    if not write and self.path=='/api/admin/dashboard':
                        return self.reply(200,admin.dashboard(Game(a,clock,opens_at=0 if practice else OPEN_MS,read_only=True)))
                    return self.reply(404,{'error':'見つかりません。'})
                if write and self.path=='/api/register':
                    a.register(data.get('name'),data.get('student_id'),data.get('password'),now//1000)
                    token=a.login(data['student_id'],data['password'],now//1000)
                    return self.reply(200,{'ok':True},f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400')
                if write and self.path=='/api/login':
                    token=a.login(data.get('student_id'),data.get('password'),now//1000)
                    return self.reply(200,{'ok':True},f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400')
                try: identity=a.identity(token,now//1000)
                except ValueError: return self.reply(401,{'error':'ログインしてください。'})
                if write and self.path=='/api/logout':
                    a.logout(token)
                    return self.reply(200,{'ok':True},'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                if write and self.path=='/api/name':
                    name=data.get('name')
                    if not isinstance(name,str) or not 1<=len(name.strip())<=40:
                        raise ValueError('名前は1〜40文字です。')
                    with a.db:
                        a.db.execute('UPDATE players SET display_name=? WHERE id=?',(name.strip(),identity['id']))
                    return self.reply(200,{'display_name':name.strip()})
                g=Game(a,clock,opens_at=0 if practice else OPEN_MS,read_only=read_only or player_only)
                if write and self.path=='/api/action':
                    if isinstance(data.get('quantity'),str) and data['quantity'].isdigit():data['quantity']=int(data['quantity'])
                    result=g.act(token,data.get('key'),data.get('kind'),data.get('product','white'),data.get('quantity'),data.get('price'),data.get('target_id'))
                    if data.get('kind') in ('ship','edit_shipment','cancel_shipment','add_listing','set_price'):
                        product=data.get('product','white')
                        player=identity['id']
                        stock=a.db.execute('SELECT product,quantity,work FROM stock WHERE player=? AND product=?',(player,product)).fetchone()
                        listing=a.db.execute('SELECT id,product,quantity,price,round FROM listings WHERE player=? AND product=?',(player,product)).fetchone()
                        result={**result,'stock':dict(stock) if stock else None,'listing':dict(listing) if listing else None}
                    if data.get('kind')=='buy_market':
                        player=identity['id']
                        stock=a.db.execute('SELECT product,quantity,work FROM stock WHERE player=? AND product=?',
                                           (player,data.get('product','white'))).fetchone()
                        cash=a.db.execute('SELECT cash FROM factories WHERE player=?',(player,)).fetchone()[0]
                        result={**result,'stock':dict(stock),'cash':cash,'quotes':g.market_quotes(player)}
                    return self.reply(200,result)
                if not write and self.path=='/api/bank':
                    return self.reply(200,bank.player_state(a.db,identity['id'],now))
                if not write and self.path=='/api/market-quotes':
                    return self.reply(200,{'quotes':g.market_quotes(identity['id'])})
                if not write and self.path=='/api/snapshot':
                    metrics=('manufactured','net_profit','revenue')
                    rankings=a.rankings_many(metrics) if cluster else g.rankings_many(metrics)
                    return self.reply(200,{'identity':identity,'factory':g.state(token, sync_inventory=not cluster),'rankings':rankings,'market':g.history(),'timeline':g.timeline(token),'breakdown':g.breakdown(token),'own':a.own_history(token,now//1000),'now':now,'event':g.event()})
                if not write and self.path=='/api/factory':
                    if a.postgres:
                        revenue=a.db.execute('SELECT COALESCE(SUM(sold_quantity*unit_price),0) FROM sales WHERE player_id=?',(identity['id'],)).fetchone()[0]
                    else:
                        revenue=sum(row[0]*row[1] for row in a.db.execute(
                            'SELECT sold_quantity,unit_price FROM sales WHERE player_id=?',(identity['id'],)))
                    return self.reply(200,{'identity':identity,'factory':g.state(token, sync_inventory=not cluster),'revenue':revenue,
                                           'now':now,'event':g.event()})
                if not write and self.path=='/api/ranks':
                    return self.reply(200,{'rankings':a.rankings_many(('manufactured','net_profit','revenue'))})
                if not write and self.path=='/api/data':
                    return self.reply(200,{'timeline':g.timeline(token),'breakdown':g.breakdown(token)})
                if not write and self.path=='/api/market':
                    return self.reply(200,{'own':a.own_history(token,now//1000)})
                return self.reply(404,{'error':'見つかりません。'})
            except json.JSONDecodeError: self.reply(400,{'error':'送信内容の形式が不正です。'})
            except ValueError as error: self.reply(400,{'error':str(error)})
            except (TypeError,KeyError): self.reply(400,{'error':'入力または操作を確認してください。'})
            except sqlite3.IntegrityError: self.reply(409,{'error':'この精算回では出荷済みです。次の回に出荷できます。'})
            except sqlite3.OperationalError as error:
                cause=error.__cause__
                logging.warning('Database failure on %s (%s, SQLSTATE %s)',
                                self.path if self.path in API_PATHS else 'unknown route',
                                type(cause or error).__name__,getattr(cause,'sqlstate',None))
                self.reply(503,{'error':'処理結果を確認できませんでした。画面を更新して結果を確認してください。'})
            finally:
                if a: a.db.close()
        def do_GET(self): self.process(False)
        def do_POST(self): self.process(True)
    class GameHTTPServer(ThreadingHTTPServer):
        request_queue_size=128

    server=GameHTTPServer((bind,port),Handler)
    server.site_settings=site_settings
    return server

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8766')))
    parser.add_argument('--bind',default='127.0.0.1');parser.add_argument('--public-origin',default=os.environ.get('HARE_FACTORY_PUBLIC_ORIGIN'));parser.add_argument('--db');parser.add_argument('--practice',action='store_true')
    args=parser.parse_args()
    args.db=args.db or os.environ.get('HARE_FACTORY_DATABASE_URL') or str(Path(__file__).with_name('practice-game.sqlite' if args.practice else 'local-game.sqlite'))
    if args.bind != '127.0.0.1' and (not args.public_origin or args.practice or not args.db.startswith(('postgresql://','postgres://'))):
        parser.error('Public binding requires HTTPS origin and PostgreSQL, with practice disabled.')
    role = os.environ.get('HARE_FACTORY_INVENTORY_ROLE')
    if role and args.practice:
        parser.error('Inventory cluster cannot run in practice mode.')
    cluster = InventoryCluster(args.db, role) if role else None
    server=make_server(args.db,args.port,practice=args.practice,public_origin=args.public_origin,bind=args.bind,cluster=cluster)
    stop=threading.Event()
    def timer():
        refresh_helpers_at = time.monotonic() + 600
        interval=1
        while not stop.wait(interval):
            interval=60
            try:
                if server.site_settings()['maintenance']:
                    continue
            except sqlite3.Error:
                logging.warning('Site settings unavailable; market timer skipped')
                continue
            a=None
            try:
                a=Accounts(args.db)
                if Game(a).settle(background=True):
                    interval=1
            except sqlite3.Error as error:
                logging.warning('Market settlement failed (%s)', type(error.__cause__ or error).__name__)
            finally:
                if a: a.db.close()
            if cluster or time.monotonic() < refresh_helpers_at:
                continue
            refresh_helpers_at = time.monotonic() + 600 + 600
            try:
                a=Accounts(args.db,read_only=True)
                try:
                    players=a.db.execute(Game.active_helpers_query).fetchall()
                finally:
                    a.db.close()
                for row in players:
                    if stop.is_set():
                        return
                    a=Accounts(args.db,read_only=True)
                    try:
                        game=Game(a,read_only=True)
                        with a.db:
                            game._helper(row['player'],game.clock())
                    finally:
                        a.db.close()
            except sqlite3.Error as error:
                logging.warning('Background production failed (%s)', type(error.__cause__ or error).__name__)
    def inventory_timer():
        while not stop.is_set():
            try:
                cluster.pulse()
                if cluster.ready and cluster.play_enabled:
                    cluster.sync(lambda: not stop.is_set() and cluster.play_enabled
                                 and (role != 'A' or not server.site_settings()['maintenance']))
            except sqlite3.Error as error:
                cluster.ready_until = 0
                logging.warning('Inventory cluster cycle failed (%s)', type(error.__cause__ or error).__name__)
            stop.wait(5)

    if not cluster or role == 'A':
        threading.Thread(target=timer,daemon=True).start()
    if cluster:
        threading.Thread(target=inventory_timer,daemon=True).start()
    if cluster and role == 'A' and args.public_origin == 'https://hare-machi-factory-sg.onrender.com':
        # Free Render workers suspend without inbound HTTP. Probe them separately
        # from the heartbeat loop so a cold start cannot delay A's own heartbeat.
        from urllib.request import urlopen

        def monitor_worker(url):
            while not stop.is_set():
                try:
                    if not server.site_settings()['maintenance']:
                        with urlopen(url, timeout=8) as response:
                            response.read(256)
                except (OSError, sqlite3.Error) as error:
                    logging.info('Inventory worker probe pending: %s', type(error).__name__)
                # PostgreSQL heartbeats remain the authoritative readiness check.
                stop.wait(240 if cluster.ready else 15)

        for worker in ('b', 'c'):
            url = f'https://hare-machi-inventory-{worker}.onrender.com/health'
            threading.Thread(target=monitor_worker, args=(url,), daemon=True).start()
    print(f'Local game: http://127.0.0.1:{server.server_port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: stop.set(); server.server_close()

if __name__=='__main__': main()