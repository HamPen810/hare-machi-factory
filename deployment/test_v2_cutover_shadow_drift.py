"""Detect real-game legacy writes which leave V2 shadow balances stale.

This is an isolated regression test against a disposable SQLite database.
A test PASS intentionally means the cutover gate correctly detects the
known dual-write gap; it does NOT certify live V2 trading.
"""
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import (
    HTTPCookieProcessor, Request, build_opener,
)
from urllib.error import HTTPError

from accounts import Accounts
from admin import Admin
from event import OPEN_MS
from server import make_server
from sparse_exact_v1 import SparseExact as S
from v2_numeric_lossless_backfill import numeric_text_to_sparse


class RealLegacyGameShadowDriftTests(unittest.TestCase):
    def test_upgrade_mutates_legacy_but_not_shadow(self):
        with tempfile.TemporaryDirectory(prefix="hare-v2-write-gap-") as folder:
            path=str(Path(folder)/"game.sqlite")
            a=Accounts(path)
            Admin(a).initialize(False)
            a.db.close()
            server=make_server(path,port=0,clock=lambda:OPEN_MS+60000,practice=True)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            base=f"http://127.0.0.1:{server.server_port}"
            opener=build_opener(HTTPCookieProcessor(CookieJar()))

            def request(method,endpoint,body=None):
                raw=None if body is None else json.dumps(body).encode()
                headers={"Origin":base,"Content-Type":"application/json"} if body is not None else {}
                req=Request(base+endpoint,data=raw,method=method,headers=headers)
                try:
                    resp=opener.open(req,timeout=12);status=resp.status;obj=json.loads(resp.read())
                except HTTPError as e:
                    status=e.code;obj=json.loads(e.read())
                return status,obj

            try:
                status,registered=request("POST","/api/register",{
                    "student_id":"2101","name":"V2 test","password":"123456"})
                self.assertEqual(status,200,registered)
                status,factory=request("GET","/api/factory")
                self.assertEqual(status,200,factory)

                with sqlite3.connect(path) as db:
                    db.execute("ALTER TABLE factories ADD COLUMN cash_v2 TEXT")
                    db.execute("ALTER TABLE stock ADD COLUMN quantity_v2 TEXT")
                    db.execute("UPDATE factories SET cash_v2='S1:500@0' WHERE player IN "
                               "(SELECT id FROM players WHERE student_id='2101')")
                    db.execute("UPDATE stock SET quantity_v2='S1:' WHERE player IN "
                               "(SELECT id FROM players WHERE student_id='2101')")

                status,result=request("POST","/api/action",{
                    "kind":"upgrade","key":"v2-gap-upgrade-001","product":"white"})
                self.assertEqual(status,200,result)
                with sqlite3.connect(path) as db:
                    legacy,shadow=db.execute(
                        "SELECT cash,cash_v2 FROM factories WHERE player IN "
                        "(SELECT id FROM players WHERE student_id='2101')"
                    ).fetchone()
                    self.assertNotEqual(
                        S.deserialize(shadow).compare(numeric_text_to_sparse(str(legacy))),0,
                        "Legacy upgrade unexpectedly keeps V2 shadow synchronized"
                    )
                print("REAL_GAME_V2_DUAL_WRITE_GAP_DETECTED_AS_EXPECTED")
                print("V2_CUTOVER_REMAINS_BLOCKED")
            finally:
                server.shutdown()
                server.server_close()


if __name__=="__main__":
    unittest.main()
