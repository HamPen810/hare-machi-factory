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
            v2_status,v2_page=call("GET","/v2")
            assert v2_status==200 and '超巨大数シミュレーター' in v2_page
            client_status,client_js=call("GET","/v2.js")
            assert client_status==200 and '/api/v2/preview' in client_js
            assert call("GET","/api/site")[0]==200
            assert call("GET","/api/factory")[0]==401
            status,body=call("POST","/api/register",{"name":"TEST","student_id":"2101","password":"123456"})
            assert status==200, (status,body)
            for path in ("/api/factory","/api/data","/api/market","/api/ranks","/api/market-quotes","/api/bank","/api/notices"):
                status,body=call("GET",path)
                assert status==200,(path,status,body)
            v2_status,v2=call("GET","/api/v2/balances")
            assert v2_status==200 and v2["format"]=="S1" and v2["mode"]=="read-only", (v2_status,v2)
            assert v2["cash"].startswith("S1:"),v2
            assert call("POST","/api/v2/balances",{})[0] in (400,404,405)
            preview_status,preview=call("POST","/api/v2/preview",{
                "product":"white","quantity":"1e1000000000",
                "unit_price":"2e1000000000","fee_bps":1250})
            assert preview_status==200, (preview_status,preview)
            assert preview["mode"]=="simulation_only" and not preview["order_placed"]
            assert preview["gross"]=="S1:2@2000000000"
            assert call("POST","/api/v2/preview",{"product":"white","quantity":7,"unit_price":"1"})[0] in (400,422)
            assert call("GET","/api/v2/balances")[1]["cash"]==v2["cash"]
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
