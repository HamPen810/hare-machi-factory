"""Synthetic local-only PostgreSQL compaction verification."""
import base64
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import zlib

import psycopg

module_path = pathlib.Path("deployment/recovery/compact_restored_db.py")
spec = importlib.util.spec_from_file_location("recovery_compactor", module_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

db = "hare_recovery_audit_0123456789"
host = "127.0.0.1"
base = dict(host=host, user="tester", password="tester", connect_timeout=5)
with psycopg.connect(**base, dbname="postgres", autocommit=True) as c:
    c.execute(f"CREATE DATABASE {db}")
with psycopg.connect(**base, dbname=db, autocommit=True) as c:
    c.execute("CREATE SCHEMA hare_factory")
    c.execute("CREATE TABLE hare_factory.players(id text PRIMARY KEY)")
    c.execute("CREATE TABLE hare_factory.factories(player text PRIMARY KEY,cash text)")
    c.execute("CREATE TABLE hare_factory.stock(player text,product text, quantity text)")
    c.execute("CREATE TABLE hare_factory.actions(player text,key text,payload text,result text,PRIMARY KEY(player,key))")
    c.execute("CREATE TABLE hare_factory.market_ticks(round bigint,product text, player text, sold text)")
    c.execute("INSERT INTO hare_factory.players VALUES ('p')")
    c.execute("INSERT INTO hare_factory.factories VALUES ('p','123456789')")
    c.execute("INSERT INTO hare_factory.stock VALUES ('p','white','987654321')")
    large = json.dumps({"taps":[{"produced":"9"*7800,"critical":False}]*10})
    # An existing raw JSON integer with >4,300 digits is not parsed at compression time.
    large_int = '{"taps":[{"produced":'+('8'*8000)+',"critical":false}]}'
    c.execute("INSERT INTO hare_factory.actions VALUES ('p','a1',%s,%s)",
              (json.dumps(["tap_batch","white",20,None]),large))
    c.execute("INSERT INTO hare_factory.actions VALUES ('p','a2',%s,%s)",
              (json.dumps(["tap_batch","white",1,None]),large_int))
    c.execute("INSERT INTO hare_factory.actions VALUES ('p','b1',%s,%s)",
              (json.dumps(["upgrade","white",None,None]),'{"spent":500}'))
    c.execute("INSERT INTO hare_factory.market_ticks VALUES (29909699,'white','', '20')")
    c.execute("INSERT INTO hare_factory.market_ticks VALUES (29909700,'white','', '30')")
    c.execute("INSERT INTO hare_factory.market_ticks VALUES (29909701,'white','', '40')")

def call(*args):
    env=dict(os.environ,PGUSER="tester",PGPASSWORD="tester")
    return subprocess.run([sys.executable,str(module_path),"--host",host,"--db",db,*args],
                          env=env,text=True,capture_output=True,check=True)

before = {}
with psycopg.connect(**base,dbname=db) as c:
    before=dict((key,(payload,result)) for key,payload,result in c.execute(
        "SELECT key,payload,result FROM hare_factory.actions"))
out=call()
assert "DRY_RUN_COMPLETE_NO_WRITES" in out.stdout
with psycopg.connect(**base,dbname=db) as c:
    assert before == dict((key,(payload,result)) for key,payload,result in c.execute(
        "SELECT key,payload,result FROM hare_factory.actions"))
    assert c.execute("SELECT count(*) FROM hare_factory.market_ticks").fetchone()[0]==3

out=call("--apply","--archive-confirmed")
assert "LOCAL_ONLY_COMPACTION_FINISHED" in out.stdout
with psycopg.connect(**base,dbname=db) as c:
    rows=dict((key,(payload,result)) for key,payload,result in c.execute(
        "SELECT key,payload,result FROM hare_factory.actions"))
    assert set(rows)==set(before)
    for k in ("a1","a2"):
        assert rows[k][0] == before[k][0]
        packed=json.loads(rows[k][1])
        assert set(packed)=={m.ENVELOPE_KEY}
        assert zlib.decompress(base64.b64decode(packed[m.ENVELOPE_KEY])).decode() == before[k][1]
        assert len(rows[k][1]) < len(before[k][1])//5
    assert rows["b1"] == before["b1"]
    assert c.execute("SELECT round FROM hare_factory.market_ticks ORDER BY round").fetchall()==[(29909700,),(29909701,)]
    assert c.execute("SELECT cash FROM hare_factory.factories").fetchone()[0]=="123456789"
    assert c.execute("SELECT quantity FROM hare_factory.stock").fetchone()[0]=="987654321"
# Reruns do not change action results or remove additional tick rows.
call("--apply","--archive-confirmed")
with psycopg.connect(**base,dbname=db) as c:
    assert rows==dict((key,(payload,result)) for key,payload,result in c.execute(
        "SELECT key,payload,result FROM hare_factory.actions"))
    assert c.execute("SELECT count(*) FROM hare_factory.market_ticks").fetchone()[0]==2
print("POSTGRES_OFFLINE_COMPACTION_TEST_PASSED")
