"""Check unique-user presence, 2-minute window and history storage."""
import sqlite3
from exact import setup
from admin import Admin
db=sqlite3.connect(':memory:')
setup(db)
db.execute('PRAGMA foreign_keys=ON')
db.execute('CREATE TABLE players(id TEXT PRIMARY KEY)')
db.execute("INSERT INTO players VALUES('p1')")
db.execute("INSERT INTO players VALUES('p2')")
db.execute("INSERT INTO players VALUES('p3')")
Admin.initialize_online(db)
now=1794480000000
Admin.note_online(db,'p1',now-90000)
Admin.note_online(db,'p2',now-30000)
Admin.note_online(db,'p3',now-140000)
Admin.note_online(db,'p1',now-10000)
db.commit()
count=Admin.sample_online(db,now)
assert count==2,count
db.commit()
from types import SimpleNamespace
admin=Admin(SimpleNamespace(db=db,postgres=False))
stats=admin.online_stats(now)
assert stats['online']==2
assert stats['window_seconds']==120
assert stats['samples'][-1]['count']==2
Admin.note_online(db,'p2',now-150000)
db.commit()
assert Admin.sample_online(db,now+1000)==1
assert len(admin.online_stats(now+1000)['samples'])==1
assert admin.online_stats(now+1000)['samples'][0]['count']==1
Admin.sample_online(db,now+180000)
assert admin.online_stats(now+180000)['online']==0
# Read-only online view does not fabricate extra samples.
length=len(admin.online_stats(now+180000)['samples'])
admin.online_stats(now+180000)
assert len(admin.online_stats(now+180000)['samples'])==length
# Data is bounded to 48 hours.
assert all(row['minute']>=(now+180000)//60000-2880 for row in
           db.execute('SELECT minute FROM online_samples'))
print('PASS: deduplicated users, 120-second live window, online samples and gaps')
