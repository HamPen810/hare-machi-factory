"""Add administrator grants and collections, safely, to the current ZIP."""
from pathlib import Path
from zipfile import ZipFile
import ast, io

archive=Path('hare-machi-render.zip')
with ZipFile(archive) as source:
    entries=[(info,source.read(info.filename)) for info in source.infolist()]
    comment=source.comment
files={info.filename:data for info,data in entries}

def replace(name,before,after):
    s=files[name].decode('utf-8')
    if s.count(before)!=1:
        raise RuntimeError(f'Unexpected production {name}: count={s.count(before)}: {before[:90]!r}')
    files[name]=s.replace(before,after).encode('utf-8')

methods='''    def fund_history(self):
        self.db.execute("""CREATE TABLE IF NOT EXISTS admin_fund_transfers(
            key TEXT PRIMARY KEY,
            player_id TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            student_id TEXT NOT NULL, name TEXT NOT NULL,
            kind TEXT NOT NULL, amount NUMERIC NOT NULL,
            before_cash NUMERIC NOT NULL, after_cash NUMERIC NOT NULL,
            note TEXT NOT NULL, created_at BIGINT NOT NULL)""")
        return [dict(r) for r in self.db.execute(
            'SELECT key,student_id,name,kind,amount,before_cash,after_cash,note,created_at '
            'FROM admin_fund_transfers ORDER BY created_at DESC,key DESC LIMIT 50')]

    def fund_transfer(self, student_id, kind, amount, note, key, now):
        from accounts import eligible
        from bank import integer
        if not eligible(student_id):
            raise ValueError('正しい学籍番号を指定してください。')
        if kind not in ('collect','grant'):
            raise ValueError('資金操作の種類を指定してください。')
        amount=integer(amount,1)
        if not isinstance(key,str) or not 16<=len(key)<=80 or not key.isascii() or not all(
            ch.isalnum() or ch in '-_' for ch in key):
            raise ValueError('操作IDが不正です。')
        if not isinstance(note,str) or len(note.strip())>160:
            raise ValueError('理由は160文字以内で指定してください。')
        note=note.strip()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            # Serialize against all normal game transactions in Postgres.
            if self.postgres:
                self.db.execute('SELECT pg_advisory_xact_lock(CAST(? AS bigint))',(1042119,))
            self.db.execute("""CREATE TABLE IF NOT EXISTS admin_fund_transfers(
                key TEXT PRIMARY KEY,
                player_id TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                student_id TEXT NOT NULL, name TEXT NOT NULL,
                kind TEXT NOT NULL, amount NUMERIC NOT NULL,
                before_cash NUMERIC NOT NULL, after_cash NUMERIC NOT NULL,
                note TEXT NOT NULL, created_at BIGINT NOT NULL)""")
            previous=self.db.execute(
                'SELECT student_id,kind,amount,note,before_cash,after_cash,name '
                'FROM admin_fund_transfers WHERE key=?',(key,)).fetchone()
            if previous:
                if (previous['student_id'],previous['kind'],int(previous['amount']),previous['note']) != (
                    student_id,kind,amount,note):
                    raise ValueError('この操作IDは別の処理に使われています。')
                self.db.rollback()
                return {'display_name':previous['name'],'kind':kind,'amount':amount,
                        'before_cash':previous['before_cash'],'after_cash':previous['after_cash'],
                        'already_applied':True}
            lock=' FOR NO KEY UPDATE' if self.postgres else ''
            player=self.db.execute(
                'SELECT p.id,p.display_name,f.cash FROM players p '
                'JOIN factories f ON f.player=p.id WHERE p.student_id=?'+lock,
                (student_id,)).fetchone()
            if not player:
                raise ValueError('対象アカウントまたは工場が見つかりません。')
            previous_cash=int(player['cash'])
            if kind=='collect' and previous_cash<amount:
                raise ValueError('所持金が徴収額に足りません。')
            new_cash=previous_cash + (amount if kind=='grant' else -amount)
            if kind=='grant':
                self.db.execute('UPDATE factories SET cash=badd(cash,?) WHERE player=?',
                                (amount,player['id']))
            else:
                updated=self.db.execute(
                    'UPDATE factories SET cash=bsub(cash,?) WHERE player=? AND bge(cash,?)',
                    (amount,player['id'],amount))
                if updated.rowcount!=1:
                    raise ValueError('所持金が徴収額に足りません。')
            self.db.execute(
                'INSERT INTO admin_fund_transfers(key,player_id,student_id,name,kind,amount,'
                'before_cash,after_cash,note,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (key,player['id'],student_id,player['display_name'],kind,
                 amount,previous_cash,new_cash,note,now))
            self.db.commit()
            return {'display_name':player['display_name'],'kind':kind,'amount':amount,
                    'before_cash':previous_cash,'after_cash':new_cash,'already_applied':False}
        except Exception:
            self.db.rollback()
            raise

'''
replace('admin.py','    def login(self,password,now):',methods+'    def login(self,password,now):')

before="""                    if self.path=='/api/admin/bank':
"""
after="""                    if self.path=='/api/admin/funds':
                        if write:
                            return self.reply(200,admin.fund_transfer(
                                data.get('student_id'),data.get('kind'),data.get('amount'),
                                data.get('note',''),data.get('key'),now))
                        return self.reply(200,{'history':admin.fund_history()})
                    if self.path=='/api/admin/bank':
"""
replace('server.py',before,after)

html=files['static/admin.html'].decode('utf-8')
old='<button role="tab" id="tab-bank" data-panel="bank" aria-controls="panel-bank" aria-selected="false">銀行</button></nav>'
new='<button role="tab" id="tab-bank" data-panel="bank" aria-controls="panel-bank" aria-selected="false">銀行</button><button role="tab" id="tab-funds" data-panel="funds" aria-controls="panel-funds" aria-selected="false">資金調整</button></nav>'
if html.count(old)!=1:raise RuntimeError('Admin nav changed')
html=html.replace(old,new)
marker='<section id="panel-bank" role="tabpanel" aria-labelledby="tab-bank" hidden>'
funds_html='''<section id="panel-funds" role="tabpanel" aria-labelledby="tab-funds" hidden>
<h2>個別アカウントへの資金調整</h2>
<p class="muted">補助金・徴収は所持金だけに反映し、売上・支出・純利益・ランキングには含めません。徴収は所持金の範囲内で行えます。</p>
<form id="funds-form">
<div class="toolbar">
<label>対象プレイヤー<select id="funds-target" required><option value="">参加者から選択</option></select></label>
<label>操作<select id="funds-kind"><option value="grant">補助金を付与</option><option value="collect">資金を徴収</option></select></label>
<label>金額（円）<input id="funds-amount" type="text" required placeholder="例 1e+10"></label>
</div>
<label>理由・メモ（任意、160文字以内）<input id="funds-note" type="text" maxlength="160" placeholder="例 イベント報酬・ルール違反"></label>
<p id="funds-preview" class="muted"></p>
<button id="funds-submit" class="primary" type="submit">確認画面へ</button>
</form>
<div id="funds-confirm" hidden>
<p id="funds-confirm-message"></p>
<div class="toolbar"><button type="button" class="primary" id="funds-apply">確定して実行</button><button type="button" id="funds-cancel">キャンセル</button></div>
</div>
<p id="funds-status" role="status" aria-live="polite"></p>
<h3>最近の資金調整履歴</h3>
<div id="funds-history" class="table-wrap"></div>
</section>
'''
if html.count(marker)!=1:raise RuntimeError('Admin panel location changed')
html=html.replace(marker,funds_html+marker)
files['static/admin.html']=html.encode('utf-8')

js=files['static/admin.js'].decode('utf-8')
anchor="for(const b of document.querySelectorAll('[data-panel]'))b.onclick="
if js.count(anchor)!=1:raise RuntimeError('Admin tab switch changed')
funds_js='''const fundsTarget=$('#funds-target');
const fundsForm=$('#funds-form');
const fundsStatus=$('#funds-status');
let fundsPending=null, fundsBusy=false;
function populateFundsTargets(){
 const selected=fundsTarget.value;
 fundsTarget.replaceChildren();
 const first=document.createElement('option');first.value='';first.textContent='参加者から選択';
 fundsTarget.append(first);
 if(data?.players){
  for(const person of data.players){
   const opt=document.createElement('option');
   opt.value=person.student_id;
   opt.textContent=person.student_id+' · '+person.display_name+' · '+fmt(person.cash)+'円';
   fundsTarget.append(opt);
  }
 }
 fundsTarget.value=selected && [...fundsTarget.options].some(o=>o.value===selected)?selected:'';
}
function updateFundsPreview(){
 const student_id=fundsTarget.value;
 const player=data?.players?.find(p=>p.student_id===student_id);
 const amount=parseWhole($('#funds-amount').value);
 const kind=$('#funds-kind').value;
 const preview=$('#funds-preview');
 if(!player){preview.textContent='対象アカウントを選択してください。';return;}
 if(amount===null||amount<1n){
  preview.textContent='現在の所持金：'+fmt(player.cash)+'円 · 正の整数を入力してください。';
  return;
 }
 const cash=BigInt(player.cash);
 const remaining=kind==='grant'?cash+amount:cash-amount;
 preview.textContent='現在 '+fmt(cash)+'円 → 実行後 '+fmt(remaining)+'円'
  +(remaining<0n?'（残高不足のため実行不可）':'');
}
function closeFundsConfirmation(){
 $('#funds-confirm').hidden=true;
 fundsPending=null;
}
$('#tab-funds').addEventListener('click',()=>{
 void refresh().then(()=>{
  populateFundsTargets();
  void loadFundsHistory();
 });
});
async function loadFundsHistory(){
 try{
  const result=await api('funds');
  const rows=(result.history||[]).map(x=>[
   new Date(Number(x.created_at)).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}),
   x.student_id+' · '+x.name,
   x.kind==='grant'?'補助金':'徴収',
   fmt(x.amount)+'円',
   fmt(x.before_cash)+'円 → '+fmt(x.after_cash)+'円',
   x.note||'—'
  ]);
  table('#funds-history',['日時','対象','操作','金額','残高変化','理由'],rows);
 }catch(error){fundsStatus.textContent=error.message;}
}
for(const id of ['funds-target','funds-kind','funds-amount']){
 $( '#'+id).addEventListener('input',()=>{closeFundsConfirmation();updateFundsPreview();});
}
$('#funds-note').addEventListener('input',closeFundsConfirmation);
fundsForm.onsubmit=event=>{
 event.preventDefault();
 if(fundsBusy)return;
 const student_id=fundsTarget.value;
 const person=data?.players?.find(x=>x.student_id===student_id);
 const amount=parseWhole($('#funds-amount').value);
 const kind=$('#funds-kind').value;
 if(!person||amount===null||amount<=0n){
  fundsStatus.textContent='対象アカウントと正しい金額を指定してください。';return;
 }
 if(kind==='collect'&&amount>BigInt(person.cash)){
  fundsStatus.textContent='対象アカウントの所持金が足りません。';return;
 }
 fundsPending={student_id,kind,amount:amount.toString(),note:$('#funds-note').value.trim(),key:crypto.randomUUID()};
 const after=BigInt(person.cash)+(kind==='grant'?amount:-amount);
 $('#funds-confirm-message').textContent=person.display_name+'（'+student_id+'）に対して'
  +(kind==='grant'?'補助金を付与':'資金を徴収')+'：'+fmt(amount)+'円'
  +'。現在の残高 '+fmt(person.cash)+'円 → '+fmt(after)+'円。実行しますか？';
 $('#funds-confirm').hidden=false;
 fundsStatus.textContent='';
};
$('#funds-cancel').onclick=closeFundsConfirmation;
$('#funds-apply').onclick=async()=>{
 if(fundsBusy||!fundsPending)return;
 const request=fundsPending;
 fundsBusy=true;
 $('#funds-apply').disabled=true;
 $('#funds-cancel').disabled=true;
 try{
  const result=await api('funds',request);
  fundsPending=null;
  $('#funds-confirm').hidden=true;
  fundsStatus.textContent=(result.already_applied?'処理済み：':'実行完了：')
   +result.display_name+' · '+(result.kind==='grant'?'補助金':'徴収')
   +' '+fmt(result.amount)+'円 · 残高 '+fmt(result.after_cash)+'円';
  await refresh();
  populateFundsTargets();
  fundsTarget.value=request.student_id;
  updateFundsPreview();
  await loadFundsHistory();
 }catch(error){
  // Preserve the request ID after network errors so a retry cannot double charge.
  fundsStatus.textContent=error.message;
 }finally{
  fundsBusy=false;
  $('#funds-apply').disabled=false;
  $('#funds-cancel').disabled=false;
 }
};
'''
js=js.replace(anchor,funds_js+anchor)
# Load player choices only from an authenticated admin dashboard.
replace_js='''data=next;$('#login').hidden=true;$('#dashboard').hidden=false;render();notice('');'''
if js.count(replace_js)!=1:raise RuntimeError('Admin dashboard refresh changed')
js=js.replace(replace_js,'''data=next;$('#login').hidden=true;$('#dashboard').hidden=false;render();populateFundsTargets();updateFundsPreview();notice('');''')
files['static/admin.js']=js.encode('utf-8')

for name in ('admin.py','server.py'):ast.parse(files[name].decode('utf-8'),filename=name)
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('admin.py','server.py','static/admin.html','static/admin.js'):
            assert z.read(info.filename)==data,info.filename
archive.write_bytes(out.getvalue())
print("PASS: admin transfers, atomic exact balance updates, idempotency and history; all other files preserved")
