"""Reduce redundant zero-value tick writes during inactive market minutes.

This is a source-to-source ZIP patch. It never connects to the production
database. The retained market_cursor advances through idle minutes exactly as
before. Existing market_ticks and every market settlement record remain intact.
"""
from pathlib import Path
from zipfile import ZipFile
import os
import tempfile

ARCHIVE = Path("hare-machi-render.zip")

OLD_IDLE = """                    self.db.execute('''INSERT INTO market_ticks
                        SELECT minute, product, '', 0, 0, 0, 0
                        FROM generate_series(CAST(? AS bigint), CAST(? AS bigint)) AS minute
                        CROSS JOIN (VALUES ('white'), ('sea'), ('shisa')) AS products(product)
                        ON CONFLICT DO NOTHING''',(last+1,empty_end-1))
"""
NEW_IDLE = """                    # No live listings: advance the cursor without writing
                    # three redundant zero-value rows for every elapsed minute.
                    # Actual trading periods still produce normal market ticks.
"""

OLD_AGG = """                    self.db.execute('INSERT INTO market_ticks VALUES(?,?,?,?,?,?,?)',(batch,product,'',sum(sold),sum(r['price']*n for r,n in zip(rows,sold)),sum(r['quantity']-n for r,n in zip(rows,sold)),sum(sold)*cost))
"""
NEW_AGG = """                    if rows or not self.accounts.postgres:
                        # Skip zero-value aggregate rows when no PostgreSQL listings exist.
                        self.db.execute('INSERT INTO market_ticks VALUES(?,?,?,?,?,?,?)',(batch,product,'',sum(sold),sum(r['price']*n for r,n in zip(rows,sold)),sum(r['quantity']-n for r,n in zip(rows,sold)),sum(sold)*cost))
"""

with ZipFile(ARCHIVE) as archive:
    info_content = [(entry, archive.read(entry.filename)) for entry in archive.infolist()]
assert any(i.filename == "market.py" for i, _ in info_content), "market.py is absent"

changed = []
for entry, raw in info_content:
    if entry.filename != "market.py":
        changed.append((entry, raw))
        continue
    text = raw.decode("utf-8")
    for old, new, label in ((OLD_IDLE, NEW_IDLE, "idle minute"), (OLD_AGG, NEW_AGG, "empty aggregate")):
        if new in text:
            continue  # Already patched; checked BEFORE searching for old inside new.
        if text.count(old) != 1:
            raise RuntimeError(f"Unexpected {label} source: no changes written")
        text = text.replace(old, new)
    compile(text, "market.py", "exec")
    assert "UPDATE market_cursor SET last=? WHERE id=1" in text
    assert "sold_this_hour" in text
    changed.append((entry, text.encode("utf-8")))
fd, temp = tempfile.mkstemp(prefix=".storage-idle-", suffix=".zip", dir=".")
os.close(fd)
try:
    with ZipFile(temp, "w") as output:
        for entry, data in changed:
            output.writestr(entry, data)
    with ZipFile(temp) as check:
        assert check.testzip() is None
    os.replace(temp, ARCHIVE)
finally:
    if os.path.exists(temp):
        os.unlink(temp)
print("PATCHED_NO_DB_WRITES: preserve active settlement, skip idle market tick rows")
