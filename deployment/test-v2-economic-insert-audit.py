"""Check all production Python SQL for V2-column-incompatible positional inserts."""
from zipfile import ZipFile
import re
bad=[]
targets={"factories","stock","listings","orders","bank_accounts","bank_contracts",
"sales","market_ticks","market_history","factory_totals","action_spend_totals",
"auto_totals","rare_collection","admin_fund_transfers",
"admin_debt_cancellations","admin_overdraft_cancellations"}
pattern=re.compile(r"(?i)\b(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|REPLACE\s+INTO)\s+([a-z_]+)\s+(?:VALUES|SELECT)\b")
with ZipFile("hare-machi-render.zip") as z:
    for name in z.namelist():
        if not name.endswith(".py"):continue
        text=z.read(name).decode("utf-8")
        for m in pattern.finditer(text):
            if m.group(1).lower() in targets:
                bad.append((name,text.count("\n",0,m.start())+1,m.group(1)))
print("POSITIONAL_INSERT_AUDIT",bad)
if bad:
    raise SystemExit("V2 shadow column migration blocked by positional finance inserts")
print("ALL_PRODUCTION_ECONOMIC_INSERTS_EXPLICIT_COLUMN_SAFE")
