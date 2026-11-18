"""Bound PostgreSQL market-tick retention to the last 120 rounds.

Preserves historical sales and market_history, accounts, money, and all action IDs.
Only market_ticks rows older than the retention boundary are pruned.
"""
from pathlib import Path
from zipfile import ZipFile
import ast, os, tempfile

ARCHIVE=Path("hare-machi-render.zip")
with ZipFile(ARCHIVE) as source:
    if source.testzip() is not None: raise RuntimeError("Original ZIP corrupt")
    entries=[(i,source.read(i.filename)) for i in source.infolist()]
    code=source.read("market.py").decode("utf-8")

old_fast="(last+1,empty_end-1)"
new_fast="(max(last+1, empty_end-120),empty_end-1)"
if new_fast not in code:
    if code.count(old_fast)!=1:
        raise RuntimeError("Market fast-forward anchor unexpected")
    code=code.replace(old_fast,new_fast,1)

def insert_before_commit(code, marker, statements):
    lines=code.splitlines(keepends=True)
    locations=[i for i,line in enumerate(lines) if marker in line]
    if len(locations)!=1:
        raise RuntimeError(f"Expected one cursor update for {marker!r}; got {len(locations)}")
    i=locations[0]
    base=len(lines[i])-len(lines[i].lstrip())
    j=None
    for k in range(i+1,min(i+90,len(lines))):
        ln=lines[k]
        if 'self.db.commit()' in ln and len(ln)-len(ln.lstrip())<=base:
            j=k
            break
    if j is None:
        raise RuntimeError(f"Could not locate commit after {marker}")
    indent=lines[j][:len(lines[j])-len(lines[j].lstrip())]
    snippet=''.join(indent+part+'\n' for part in statements)
    lines.insert(j,snippet)
    return ''.join(lines)

if "if self.accounts.postgres and limit % 10 == 0:" not in code:
    code=insert_before_commit(code,
        "UPDATE market_cursor SET last=? WHERE id=1',(batch,))",
        ["# Reuse historical tick storage without losing current game state.",
         "if self.accounts.postgres and limit % 10 == 0:",
         "    self.db.execute('DELETE FROM market_ticks WHERE round < ?', (limit-120,))"])

if "if empty_end % 10 == 0:" not in code:
    code=insert_before_commit(code,
        "UPDATE market_cursor SET last=? WHERE id=1',(last,))",
        ["if empty_end % 10 == 0:",
         "    self.db.execute('DELETE FROM market_ticks WHERE round < ?', (empty_end-120,))"])

if code.count("DELETE FROM market_ticks WHERE round < ?")!=2:
    raise RuntimeError("Missing retention paths")
ast.parse(code, filename="market.py")

fd,tmp=tempfile.mkstemp(dir=".",suffix=".zip")
os.close(fd)
try:
    with ZipFile(tmp,"w") as out:
        for info,raw in entries:
            out.writestr(info,code.encode("utf-8") if info.filename=="market.py" else raw)
    with ZipFile(tmp) as check:
        if check.testzip() is not None:raise RuntimeError("Patched ZIP corrupt")
        if check.read("market.py").decode("utf-8")!=code:raise RuntimeError("Mismatched ZIP content")
        if "action_archive_support.py" not in check.namelist():raise RuntimeError("Archive support missing")
    os.replace(tmp,ARCHIVE)
finally:
    if os.path.exists(tmp): os.remove(tmp)
print("MARKET_RETENTION_PATCH_OK")
