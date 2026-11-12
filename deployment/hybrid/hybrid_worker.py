"""Oracle-only read-compute HTTP service, no frontend or game write APIs.

Bind to 127.0.0.1 behind a trusted HTTPS reverse proxy on port 25565.
The worker NEVER receives player cookies or their authentication data.
"""
import argparse
import hashlib
import hmac
import json
import os
import time
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from accounts import Accounts
from exact import wire

def create_worker(db_url,secret,host='127.0.0.1',port=8000,now=None):
    if not isinstance(secret,str) or len(secret)<32:
        raise ValueError('HYBRID_SHARED_SECRET must be at least 32 characters')
    if host not in ('127.0.0.1','::1'):
        raise ValueError('Oracle application must bind only to loopback')
    time_now = now or time.time

    class Worker(BaseHTTPRequestHandler):
        server_version='HareHybrid/1'
        def log_message(self,*args):
            pass
        def send_json(self,status,data):
            raw=json.dumps(wire(data),ensure_ascii=False,separators=(',',':')).encode('utf8')
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            if self.path!='/health':
                return self.send_json(404,{'error':'not found'})
            a=None
            try:
                a=Accounts(db_url,read_only=True)
                a.db.execute('SELECT 1').fetchone()
                return self.send_json(200,{'ok':True,'role':'oracle'})
            except Exception:
                return self.send_json(503,{'ok':False})
            finally:
                if a:a.db.close()
        def do_POST(self):
            if self.path!='/internal/compute':
                return self.send_json(404,{'error':'not found'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 1<=size<=4096:
                    return self.send_json(413,{'error':'invalid size'})
                body=self.rfile.read(size)
                timestamp=self.headers.get('X-Hybrid-Timestamp','')
                signature=self.headers.get('X-Hybrid-Signature','')
                if (not timestamp.isascii() or not timestamp.isdecimal() or len(timestamp)>12
                    or abs(time_now()-int(timestamp))>30 or len(signature)!=64):
                    return self.send_json(403,{'error':'authentication failed'})
                expected=hmac.new(secret.encode('utf8'),timestamp.encode('ascii')+b'\n'+body,
                                  hashlib.sha256).hexdigest()
                if not hmac.compare_digest(signature,expected):
                    return self.send_json(403,{'error':'authentication failed'})
                request=json.loads(body)
                if not isinstance(request,dict) or request.get('op')!='rankings':
                    return self.send_json(400,{'error':'unsupported compute operation'})
                if not isinstance(request.get('request_id'),str) or len(request['request_id'])>60:
                    return self.send_json(400,{'error':'invalid request id'})
                a=None
                try:
                    a=Accounts(db_url,read_only=True)
                    board=a.rankings_many(('manufactured','net_profit','revenue'))
                finally:
                    if a:a.db.close()
                return self.send_json(200,{'operation':'rankings','rankings':board})
            except (ValueError,TypeError,json.JSONDecodeError):
                return self.send_json(400,{'error':'malformed request'})
            except Exception:
                logging.exception('Oracle read compute failed')
                return self.send_json(503,{'error':'compute unavailable'})

    return ThreadingHTTPServer((host,port),Worker)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    secret=os.environ.get('HYBRID_SHARED_SECRET','')
    db=os.environ.get('HARE_FACTORY_DATABASE_URL','')
    if not db.startswith(('postgresql://','postgres://')):
        parser.error('A single authoritative PostgreSQL URL is required')
    httpd=create_worker(db,secret,args.host,args.port)
    print('Oracle private compute service ready on loopback',flush=True)
    try:httpd.serve_forever()
    except KeyboardInterrupt:pass
    finally:httpd.server_close()

if __name__=='__main__':
    main()
