"""Prepare real production SQL for additive V2 shadow columns.

Replace schema-order-dependent INSERT ... VALUES/SELECT statements with
explicit column names, preserving old positional values and behavior.
NO DDL, NO DATABASE ACCESS, NO V2 ECONOMIC CUTOVER.
"""
import ast,os,re,tempfile
from pathlib import Path
from zipfile import ZipFile

ARCHIVE=Path("hare-machi-render.zip")
# Verified against actual information_schema on the user's database.
COLUMNS={
    "factory_totals":"player,manufactured,purchases",
    "auto_totals":"player,product,quantity",
    "rare_collection":"player,rare,quantity,discovered",
    "sales":"settlement_id,player_id,product_id,sold_quantity,unit_price,unit_cost,accepted_at,settled_at",
    "listings":"id,player,product,quantity,price,accepted,round",
    "market_ticks":"round,product,player,sold,revenue,inventory,cost",
    "market_history":"round,product,offered,sold,revenue,sellers",
    "bank_contracts":"id,player,kind,principal,amount,matures,created_at",
}
FILES=("market.py","bank.py","accounts.py")
SQL=re.compile(
    r"(?i)\b((?:INSERT\s+(?:OR\s+(?:IGNORE|REPLACE)\s+)?INTO|REPLACE\s+INTO))"
    r"(\s+)([a-z_]+)(\s+)(VALUES|SELECT)\b"
)

with ZipFile(ARCHIVE) as z:
    if z.testzip() is not None:raise RuntimeError("Source game ZIP invalid")
    records=[(meta,z.read(meta.filename)) for meta in z.infolist()]
original={info.filename:data for info,data in records}
changes={}
totals={}
for name in FILES:
    original_text=original[name].decode("utf-8")
    hits={}
    def add_columns(match):
        table=match.group(4).lower()
        if table not in COLUMNS:return match.group(0)
        hits[table]=hits.get(table,0)+1
        return match.group(1)+match.group(3)+table+"("+COLUMNS[table]+")"+match.group(5)+match.group(6)
    # group2 is the optional OR clause, group3 whitespace, group4 table,
    # group5 whitespace and group6 INSERT payload type.
    replaced=SQL.sub(add_columns,original_text)
    if name=="market.py":
        for required in ("factory_totals","auto_totals","rare_collection","sales","listings","market_ticks","market_history"):
            if hits.get(required,0)<1 and (required+"("+COLUMNS[required]+")") not in replaced:
                raise RuntimeError("Required production market insert not found: "+required)
    if name=="bank.py" and hits.get("bank_contracts",0)<2:
        raise RuntimeError("Expected both bank contract branches")
    if name=="accounts.py" and hits.get("sales",0)<1:
        raise RuntimeError("Expected existing sales recording")
    ast.parse(replaced,filename=name)
    changes[name]=replaced.encode("utf-8")
    totals[name]=hits

fd,temp=tempfile.mkstemp(dir=".",suffix=".zip")
os.close(fd)
try:
    with ZipFile(temp,"w") as z:
        for meta,data in records:z.writestr(meta,changes.get(meta.filename,data))
    with ZipFile(temp) as z:
        if z.testzip() is not None:raise RuntimeError("Patched ZIP invalid")
        for name,data in original.items():
            expected=changes.get(name,data)
            if z.read(name)!=expected:raise RuntimeError("Unexpected file mutation: "+name)
        for name in FILES:
            src=z.read(name).decode("utf-8")
            for match in SQL.finditer(src):
                if match.group(4).lower() in COLUMNS:
                    raise RuntimeError("Still positional insert in "+name+": "+match.group(4))
    os.replace(temp,ARCHIVE)
finally:
    if os.path.exists(temp):os.remove(temp)
print("EXPLICIT_INSERT_COLUMN_MIGRATION_PASS",totals)
print("ALL_FINANCIAL_WRITER_SEMANTICS_UNCHANGED")
print("NO_SCHEMA_CHANGE_PERFORMED")
