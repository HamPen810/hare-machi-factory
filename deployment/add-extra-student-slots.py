"""Add admin-managed extra registration slots to current production ZIP.

Extra IDs are exact four-digit numbers outside normal eligibility, with an
explicit assignment to class 1-8 for existing leaderboard compatibility.
Existing players, bank, inventory and financial data are not modified.
"""
from zipfile import ZipFile
from pathlib import Path
import ast,io
archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}

def patch(name,old,new):
    s=files[name].decode('utf8')
    if s.count(old)!=1:raise RuntimeError(f"{name}: anchor count {s.count(old)}: {old[:100]!r}")
    files[name]=s.replace(old,new).encode('utf8')

# Leave normal 21xx-28xx eligibility unchanged. Extra IDs are granted per
# database and must never be globally enabled by a change to the validator.
patch('accounts.py',
"""def eligible(student_id):
    if not isinstance(student_id,str) or len(student_id)!=4 or not student_id.isascii() or not student_id.isdigit():
        return False
    return student_id[0]=='2' and student_id[1] in '12345678' and 1<=int(student_id[2:])<=(41 if student_id[1]=='8' else 40)
""",
"""def eligible(student_id, db=None):
    if not isinstance(student_id,str) or len(student_id)!=4 or not student_id.isascii() or not student_id.isdigit():
        return False
    normal=(student_id[0]=='2' and student_id[1] in '12345678' and
            1<=int(student_id[2:])<=(41 if student_id[1]=='8' else 40))
    if normal:return True
    if db is None:return False
    return db.execute('SELECT 1 FROM admin_extra_slots WHERE student_id=?',
                      (student_id,)).fetchone() is not None

def assigned_class(db,student_id):
    if not eligible(student_id,db):
        raise ValueError('登録対象外の学籍番号です。')
    if eligible(student_id):
        return int(student_id[1])
    row=db.execute('SELECT class_number FROM admin_extra_slots WHERE student_id=?',
                   (student_id,)).fetchone()
    if row is None:raise ValueError('登録対象外の学籍番号です。')
    return int(row['class_number'])
""")
patch('accounts.py',
"""        bank.initialize(self.db)
""",
"""        bank.initialize(self.db)
        self.db.execute('CREATE TABLE IF NOT EXISTS admin_extra_slots('
                        'student_id TEXT PRIMARY KEY,class_number INTEGER NOT NULL '
                        'CHECK(class_number BETWEEN 1 AND 8),created_at BIGINT NOT NULL)')
        self.db.commit()
""")
# Do not create the table only for sqlite: initialize through Admin.setup for
# PostgreSQL once, called by the server's existing settings bootstrap.
patch('accounts.py',
"""        if not eligible(student_id):raise ValueError('登録対象外の学籍番号です。')""",
"""        if not eligible(student_id,self.db):raise ValueError('登録対象外の学籍番号です。')""")
patch('accounts.py',
"""        self.db.execute('INSERT INTO players VALUES(?,?,?,?,?,?,?)',(pid,student_id,name.strip(),int(student_id[1]),salt,digest,now))""",
"""        self.db.execute('INSERT INTO players VALUES(?,?,?,?,?,?,?)',(pid,student_id,name.strip(),assigned_class(self.db,student_id),salt,digest,now))""")
patch('accounts.py',
"""or not eligible(student_id):raise ValueError('ログイン情報を確認してください。')""",
"""or not eligible(student_id,self.db):raise ValueError('ログイン情報を確認してください。')""")

patch('admin.py',
"""            self.db.execute('CREATE TABLE IF NOT EXISTS admin_sessions(token_hash TEXT PRIMARY KEY,expires_at BIGINT NOT NULL)')""",
"""            self.db.execute('CREATE TABLE IF NOT EXISTS admin_sessions(token_hash TEXT PRIMARY KEY,expires_at BIGINT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS admin_extra_slots('
                            'student_id TEXT PRIMARY KEY,class_number INTEGER NOT NULL '
                            'CHECK(class_number BETWEEN 1 AND 8),created_at BIGINT NOT NULL)')""")
patch('admin.py',
"""    def player(self,student_id,operation):""",
"""    def extra_slots(self):
        return [dict(r) for r in self.db.execute(
            'SELECT s.student_id,s.class_number,s.created_at,'
            'p.display_name FROM admin_extra_slots s '
            'LEFT JOIN players p ON p.student_id=s.student_id '
            'ORDER BY s.student_id')]

    def manage_extra_slot(self,student_id,class_number,operation,now):
        from accounts import eligible
        if not isinstance(student_id,str) or len(student_id)!=4 or not student_id.isascii() or not student_id.isdigit():
            raise ValueError('学籍番号は数字4桁で指定してください。')
        if eligible(student_id):
            raise ValueError('通常の登録可能範囲にある番号は、追加枠には登録できません。')
        if operation not in ('add','remove'):
            raise ValueError('操作の種類を確認してください。')
        if operation=='add' and (type(class_number) is not int or not 1<=class_number<=8):
            raise ValueError('所属するクラスは1～8組を選択してください。')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.postgres:
                self.db.execute('SELECT pg_advisory_xact_lock(CAST(? AS bigint))',(1042119,))
            registered=self.db.execute(
                'SELECT 1 FROM players WHERE student_id=?',(student_id,)).fetchone()
            existing=self.db.execute(
                'SELECT class_number FROM admin_extra_slots WHERE student_id=?',
                (student_id,)).fetchone()
            if operation=='add':
                if existing:
                    raise ValueError('この番号は既に追加されています。')
                if registered:
                    raise ValueError('この学籍番号は既に使用されています。')
                self.db.execute(
                    'INSERT INTO admin_extra_slots(student_id,class_number,created_at) '
                    'VALUES(?,?,?)',(student_id,class_number,now))
            else:
                if not existing:
                    raise ValueError('追加枠に存在しない番号です。')
                if registered:
                    raise ValueError('登録済みアカウントがあるため削除できません。')
                self.db.execute('DELETE FROM admin_extra_slots WHERE student_id=?',
                                (student_id,))
            self.db.commit()
            return {'student_id':student_id,'operation':operation,
                    'class_number':class_number if operation=='add' else None}
        except Exception:
            self.db.rollback()
            raise

    def player(self,student_id,operation):""")
# Existing administrative freeze, funds and debt forgiveness must recognize
# explicitly approved new IDs. They still require account existence.
patch('admin.py',
"""if not eligible(student_id) or operation not in ('freeze','unfreeze','reset'):""",
"""if not eligible(student_id,self.db) or operation not in ('freeze','unfreeze','reset'):""")
patch('admin.py',
"""        if not eligible(student_id):
            raise ValueError('正しい学籍番号を指定してください。')""",
"""        if not eligible(student_id,self.db):
            raise ValueError('正しい学籍番号を指定してください。')""")
patch('admin_fund_ops.py',
"""        if not eligible(student):
            raise ValueError('正しい学籍番号4桁を入力してください。')""",
"""        # Extra slots are resolved in plan() against the current database.
        if not isinstance(student,str) or len(student)!=4 or not student.isascii() or not student.isdigit():
            raise ValueError('正しい学籍番号4桁を入力してください。')""")
patch('server.py',
"""                    if write and self.path=='/api/admin/player':""",
"""                    if self.path=='/api/admin/slots':
                        if write:
                            return self.reply(200,admin.manage_extra_slot(
                                data.get('student_id'),data.get('class_number'),
                                data.get('operation'),now))
                        return self.reply(200,{'slots':admin.extra_slots()})
                    if write and self.path=='/api/admin/player':""")

patch('static/admin.html',
""" <form id="player-form">""",
""" <details id="extra-slots-section"><summary>新規登録用の学籍番号を追加する</summary>
 <p class="muted">通常の登録範囲外の数字4桁を、新しいプレイヤー登録枠として許可します。追加した番号はゲーム画面から通常の新規登録ができます。ランキングで使用する所属クラスも指定してください。</p>
 <form id="extra-slot-form">
 <div class="toolbar">
 <label>追加する学籍番号<input id="extra-slot-id" type="text" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" required placeholder="例 2999"></label>
 <label>所属クラス<select id="extra-slot-class"><option value="1">1組</option><option value="2">2組</option><option value="3">3組</option><option value="4">4組</option><option value="5">5組</option><option value="6">6組</option><option value="7">7組</option><option value="8">8組</option></select></label>
 <button type="submit" class="primary">新しい登録枠を追加</button>
 </div></form>
 <p id="extra-slot-status" role="status" aria-live="polite"></p>
 <h3>追加した学籍番号</h3><div id="extra-slot-list" class="table-wrap"></div>
 <button id="extra-slot-reload" type="button">追加枠の一覧を更新</button>
 <p class="muted">未登録の枠は削除できます。すでにプレイヤー登録されている番号は、アカウントを消さない限り削除できません。</p>
 </details>
 <form id="player-form">""")

extra_js=r"""let extraSlotsBusy=false;
async function loadExtraSlots(){
 try{
  const result=await api('slots');
  const root=$('#extra-slot-list');
  root.replaceChildren();
  if(!result.slots?.length){root.textContent='追加された登録枠はありません。';return;}
  const t=document.createElement('table'),th=document.createElement('thead'),hd=document.createElement('tr');
  for(const label of ['学籍番号','所属クラス','状態','操作']){
   const node=document.createElement('th');node.textContent=label;hd.append(node);
  }
  th.append(hd);t.append(th);
  const body=document.createElement('tbody');
  for(const slot of result.slots){
   const tr=document.createElement('tr');
   for(const value of [slot.student_id,slot.class_number+'組',slot.display_name?'登録済み：'+slot.display_name:'登録待ち']){
    const td=document.createElement('td');td.textContent=value;tr.append(td);
   }
   const td=document.createElement('td'),button=document.createElement('button');
   button.type='button';button.textContent='枠を削除';button.disabled=Boolean(slot.display_name);
   button.onclick=async()=>{
    if(!window.confirm(slot.student_id+' の追加登録枠を削除しますか？'))return;
    button.disabled=true;
    try{
     await api('slots',{student_id:slot.student_id,operation:'remove'});
     $('#extra-slot-status').textContent=slot.student_id+' の追加枠を削除しました。';
     await loadExtraSlots();
    }catch(error){$('#extra-slot-status').textContent=error.message;button.disabled=false;}
   };
   td.append(button);tr.append(td);body.append(tr);
  }
  t.append(body);root.append(t);
 }catch(error){$('#extra-slot-status').textContent='追加枠を取得できませんでした：'+error.message;}
}
$('#extra-slot-form').onsubmit=async event=>{
 event.preventDefault();
 if(extraSlotsBusy)return;
 extraSlotsBusy=true;
 const button=event.submitter;
 button.disabled=true;
 try{
  const id=$('#extra-slot-id').value;
  const cls=Number($('#extra-slot-class').value);
  await api('slots',{student_id:id,class_number:cls,operation:'add'});
  $('#extra-slot-status').textContent=id+'（'+cls+'組）の登録枠を追加しました。ゲーム画面から新規登録できます。';
  $('#extra-slot-id').value='';
  await loadExtraSlots();
 }catch(error){$('#extra-slot-status').textContent=error.message;}
 finally{button.disabled=false;extraSlotsBusy=false;}
};
$('#extra-slot-reload').onclick=()=>void loadExtraSlots();
$('#extra-slots-section').addEventListener('toggle',()=>{
 if($('#extra-slots-section').open)void loadExtraSlots();
});
"""
patch('static/admin.js',
"""for(const b of document.querySelectorAll('[data-panel]'))b.onclick=""",
extra_js+"""for(const b of document.querySelectorAll('[data-panel]'))b.onclick=""")

for f in ('accounts.py','admin.py','admin_fund_ops.py','server.py'):
    ast.parse(files[f].decode('utf8'),filename=f)
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('accounts.py','admin.py','admin_fund_ops.py','server.py','static/admin.html','static/admin.js'):
            assert z.read(info.filename)==data
archive.write_bytes(out.getvalue())
print('PASS: admin-managed extra slots, DB-backed enrollment, unchanged built-in eligibility and class mapping')
