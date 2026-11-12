"""Hybrid router+worker safety tests; no public production traffic."""
import hashlib
import hmac
import http.client
import json
import threading
import time
from hybrid_router import HybridRouter
from hybrid_worker import create_worker
import hybrid_worker

board={k:{'individual':[],'classes':[]} for k in ('manufactured','net_profit','revenue')}
secret='test-secret-'+'0'*50
now=int(time.time())

class FakeDB:
    def execute(self,*args):
        return self
    def fetchone(self):
        return (1,)
    def close(self):
        pass

class FakeAccounts:
    def __init__(self,*a,**kw):
        self.db=FakeDB()
    def rankings_many(self,metrics):
        assert tuple(metrics)==('manufactured','net_profit','revenue')
        return board

original=hybrid_worker.Accounts
hybrid_worker.Accounts=FakeAccounts
worker=create_worker(':memory:',secret,port=0)
port=worker.server_address[1]
thread=threading.Thread(target=worker.serve_forever,daemon=True)
thread.start()

def request(path,body,signature='',stamp=None,method='POST'):
    c=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
    stamp=str(now if stamp is None else stamp)
    c.request(method,path,body=body,headers={
        'Content-Type':'application/json',
        'X-Hybrid-Timestamp':stamp,
        'X-Hybrid-Signature':signature})
    res=c.getresponse()
    data=json.loads(res.read())
    c.close()
    return res.status,data

try:
    payload=json.dumps({'op':'rankings','request_id':'unit-test'},separators=(',',':')).encode()
    signature=hmac.new(secret.encode(),str(now).encode()+b'\n'+payload,
                       hashlib.sha256).hexdigest()
    status,data=request('/internal/compute',payload,signature)
    assert status==200 and data['rankings']==board,(status,data)
    assert request('/internal/compute',payload,'0'*64)[0]==403
    assert request('/internal/compute',payload,signature,stamp=now-1000)[0]==403
    assert request('/api/action',payload,signature)[0]==404
    bad=json.dumps({'op':'action','request_id':'x'}).encode()
    sig=hmac.new(secret.encode(),str(now).encode()+b'\n'+bad,hashlib.sha256).hexdigest()
    assert request('/internal/compute',bad,sig)[0]==400
    assert request('/health',b'',method='GET')[0]==200
finally:
    worker.shutdown()
    worker.server_close()
    hybrid_worker.Accounts=original

calls={'local':0,'remote':0}
def local():
    calls['local']+=1
    return {'rankings':board}
def remote(body):
    calls['remote']+=1
    return {'operation':'rankings','rankings':board}
r=HybridRouter(endpoint='https://oracle.example:25565',secret=secret,enabled=True,
               transport=remote,timeout=0.3)
assert r.mode()=='normal'
assert r.calculate('rankings',local)=={'rankings':board}
assert calls['remote']==0
r.mode_setting='offload'
assert r.calculate('rankings',local)=={'rankings':board}
assert calls['remote']==1
r.mode_setting='speculative'
result=r.calculate('rankings',local,local_parallel=local)
assert result['rankings']==board
r.pool.shutdown(wait=True)

def failed(body):
    raise TimeoutError('worker unavailable')
r=HybridRouter(endpoint='https://oracle.example:25565',secret=secret,enabled=True,
               transport=failed,timeout=0.3)
r.mode_setting='offload'
for i in range(3):
    assert r.calculate('rankings',local)=={'rankings':board}
assert r.stats()['circuit_open']
assert r.mode()=='normal'
assert r.stats()['metrics']['fallback']==3
r.pool.shutdown(wait=True)

# Fail closed with an untrusted URL or missing configured secret.
for u in ('http://192.9.170.181:25565','https://u:p@oracle.example',
          'https://oracle.example/internal/write'):
    r=HybridRouter(endpoint=u,secret=secret,enabled=True,transport=remote)
    assert not r.ready
    assert r.mode()=='normal'
    r.pool.shutdown(wait=True)
print('PASS: authenticated Oracle-only worker, 403 malformed signatures, read-only allow-list, normal/speculative/offload, circuit breaker and fallback')
