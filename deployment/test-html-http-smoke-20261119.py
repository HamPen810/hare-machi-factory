"""Isolated HTTP smoke test against a throwaway SQLite game, never production."""
import os, tempfile, threading, json, sys
from pathlib import Path
from urllib.request import build_opener, HTTPCookieProcessor, Request, HTTPErrorProcessor
from urllib.error import HTTPError
from http.cookiejar import CookieJar

os.environ["HARE_FACTORY_MAINTENANCE"]="0"
from server import make_server
from accounts import Accounts
from admin import Admin
from event import OPEN_MS

def run():
    with tempfile.TemporaryDirectory(prefix="hare-html-http-") as folder:
        db=str(Path(folder)/"smoke.sqlite")
        a=Accounts(db)
        Admin(a).initialize(False)
        a.db.close()
        srv=make_server(db,port=0,clock=lambda: OPEN_MS+60_000,practice=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        origin=f"http://127.0.0.1:{srv.server_port}"
        opener=build_opener(HTTPCookieProcessor(CookieJar()))
        def call(method,path,payload=None,form=False):
            data=(__import__("urllib.parse",fromlist=["urlencode"]).urlencode(payload).encode() if form else json.dumps(payload).encode()) if payload is not None else None
            headers={"Origin":origin,"Content-Type":"application/x-www-form-urlencoded" if form else "application/json"} if data else {}
            req=Request(origin+path,data=data,headers=headers,method=method)
            try: response=opener.open(req,timeout=12);status=response.status;raw=response.read()
            except HTTPError as error:status=error.code;raw=error.read()
            try: parsed=json.loads(raw)
            except (ValueError,UnicodeDecodeError):parsed=raw.decode("utf-8","replace")
            return status,parsed
        try:
            status,body=call("GET","/")
            assert status==200 and "<!doctype html>" in body
            assert call("GET","/api/site")[0]==200
            assert call("GET","/api/factory")[0]==401
            status,body=call("POST","/api/register",{"name":"TEST","student_id":"2101","password":"123456"})
            assert status==200, (status,body)
            for path in ("/api/factory","/api/data","/api/market","/api/ranks","/api/market-quotes","/api/bank","/api/notices"):
                status,body=call("GET",path)
                assert status==200,(path,status,body)
            action={"kind":"tap","key":"integration-fixed-tap","product":"white","quantity":1}
            status,first=call("POST","/api/action",action)
            status2,again=call("POST","/api/action",action)
            assert status==status2==200 and first==again
            assert call("POST","/api/notices/message",{"body":"Isolated test message"})[0]==200
            assert call("POST","/api/name",{"name":"TEST2"})[0]==200
            assert call("POST","/api/logout",{})[0]==200
            assert call("GET","/api/factory")[0]==401
            assert call("POST","/api/login",{"student_id":"2101","password":"123456"})[0]==200
            assert call("GET","/api/factory")[0]==200
            print("ISOLATED_HTML_HTTP_API_SMOKE_PASSED")
        finally:
            srv.shutdown();srv.server_close()

if __name__=="__main__":
    run()
