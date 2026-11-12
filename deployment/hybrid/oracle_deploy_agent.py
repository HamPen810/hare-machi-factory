"""Oracle webhook for GitHub-triggered, approved production updates.

Network exposed only behind a trusted HTTPS proxy. Run under an unprivileged
account; the deploy command has narrowly scoped sudo permission to restart
only the compute systemd unit.
"""
import hashlib
import hmac
import json
import os
import re
import subprocess
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def serve(host='127.0.0.1',port=8001):
    if host!='127.0.0.1':
        raise ValueError('Deployment webhook must only listen on loopback')
    secret=os.getenv('ORACLE_DEPLOY_SECRET','')
    if len(secret)<32:
        raise ValueError('ORACLE_DEPLOY_SECRET must be 32+ characters')
    nonce_seen={}
    mutex=threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):
            pass
        def reply(self,status,data):
            body=json.dumps(data,separators=(',',':')).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            if self.path!='/internal/deploy':
                return self.reply(404,{'ok':False})
            length=self.headers.get('Content-Length','')
            if not length.isdecimal() or not 1<=int(length)<=2048:
                return self.reply(413,{'ok':False})
            raw=self.rfile.read(int(length))
            timestamp=self.headers.get('X-Hybrid-Timestamp','')
            signature=self.headers.get('X-Hybrid-Signature','')
            if not timestamp.isdecimal() or len(timestamp)>12 or abs(time.time()-int(timestamp))>60:
                return self.reply(403,{'ok':False})
            expected=hmac.new(secret.encode(),timestamp.encode()+b'\n'+raw,
                              hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature,expected):
                return self.reply(403,{'ok':False})
            try:
                data=json.loads(raw)
                sha=data.get('sha')
                nonce=data.get('nonce')
                if not isinstance(sha,str) or not re.fullmatch(r'[a-f0-9]{40}',sha):
                    return self.reply(400,{'ok':False,'error':'bad sha'})
                if not isinstance(nonce,str) or not re.fullmatch(r'[a-f0-9]{32}',nonce):
                    return self.reply(400,{'ok':False,'error':'bad nonce'})
                with mutex:
                    current=time.time()
                    for key,stamp in list(nonce_seen.items()):
                        if current-stamp>300:nonce_seen.pop(key,None)
                    if nonce in nonce_seen:
                        return self.reply(409,{'ok':False,'error':'replay'})
                    nonce_seen[nonce]=current
                # No shell expansion or arbitrary user command arguments.
                result=subprocess.run(['/usr/local/bin/hare-hybrid-deploy',sha],
                                      capture_output=True,text=True,timeout=180)
                if result.returncode:
                    return self.reply(503,{'ok':False,'error':'deployment failed'})
                return self.reply(200,{'ok':True,'sha':sha})
            except (ValueError,TypeError,subprocess.TimeoutExpired):
                return self.reply(503,{'ok':False,'error':'deployment unavailable'})

    return ThreadingHTTPServer((host,port),Handler)

if __name__=='__main__':
    server=serve()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
