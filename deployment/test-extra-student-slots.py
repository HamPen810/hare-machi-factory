"""Regression: extra IDs are opt-in and survive normal auth/financial controls."""
import sqlite3,tempfile,os
from accounts import Accounts,eligible,assigned_class
from admin import Admin

with tempfile.TemporaryDirectory() as td:
 p=os.path.join(td,'game.sqlite')
 a=Accounts(p)
 admin=Admin(a,credential={'password_hash':'notused'})
 admin.initialize(False)
 assert eligible('2101') and eligible('2841') and not eligible('2999')
 assert not eligible('2999',a.db)
 assert not eligible('99999',a.db)
 try:
  a.register('Unauthorised','2999','123456',now=1794480000)
  raise AssertionError('unapproved extra ID registered')
 except ValueError:pass
 result=admin.manage_extra_slot('2999',3,'add',1794480000000)
 assert result['class_number']==3
 assert eligible('2999',a.db) and assigned_class(a.db,'2999')==3
 assert len(admin.extra_slots())==1
 try:
  admin.manage_extra_slot('2999',3,'add',1794480000000)
  raise AssertionError('duplicate extra ID added')
 except ValueError:pass
 try:
  admin.manage_extra_slot('2101',1,'add',1794480000000)
  raise AssertionError('standard ID inserted as extra')
 except ValueError:pass
 a.register('New Player','2999','123456',now=1794480000)
 row=a.db.execute("SELECT class_number FROM players WHERE student_id='2999'").fetchone()
 assert row['class_number']==3
 token=a.login('2999','123456',now=1794480001)
 assert a.identity(token,1794480001)['class_number']==3
 try:
  admin.manage_extra_slot('2999',0,'remove',1794480000002)
  raise AssertionError('registered slot removed')
 except ValueError:pass
 # Normal class is unaffected.
 a.register('Existing','2101','654321',now=1794480000)
 assert assigned_class(a.db,'2101')==1
 assert a.db.execute("SELECT class_number FROM players WHERE student_id='2101'").fetchone()['class_number']==1
 # After a valid account is removed, its reserved slot may be revoked.
 a.db.execute("DELETE FROM sessions WHERE player_id=(SELECT id FROM players WHERE student_id='2999')")
 a.db.execute("DELETE FROM players WHERE student_id='2999'")
 a.db.commit()
 admin.manage_extra_slot('2999',0,'remove',1794480000003)
 assert not eligible('2999',a.db)
 try:
  a.login('2999','123456',now=1794480004)
  raise AssertionError('revoked slot login')
 except ValueError:pass
 a.db.close()
print('PASS: explicit extra 4-digit IDs, class mapping, registration, login, revoked/duplicate slot safety')
