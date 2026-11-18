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

old_tail="""                self.db.execute('UPDATE market_cursor SET last=? WHERE id=1',(batch,))
            self.db.commit()"""
new_tail="""                self.db.execute('UPDATE market_cursor SET last=? WHERE id=1',(batch,))
            # PostgreSQL auto-vacuum reuses deleted row space. Keep only 120 rounds.
            if self.accounts.postgres and limit % 10 == 0:
                self.db.execute('DELETE FROM market_ticks WHERE round < ?', (limit-120,))
            self.db.commit()"""
if new_tail not in code:
    if code.count(old_tail)!=1:
        raise RuntimeError("Settlement commit anchor unexpected")
    code=code.replace(old_tail,new_tail,1)

old_early="""                    self.db.execute('UPDATE market_cursor SET last=? WHERE id=1',(last,))
                    self.db.commit()"""
new_early="""                    self.db.execute('UPDATE market_cursor SET last=? WHERE id=1',(last,))
                    if empty_end % 10 == 0:
                        self.db.execute('DELETE FROM market_ticks WHERE round < ?', (empty_end-120,))
                    self.db.commit()"""
if new_early not in code:
    if code.count(old_early)!=1:
        raise RuntimeError("Fast-forward commit anchor unexpected")
    code=code.replace(old_early,new_early,1)

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
