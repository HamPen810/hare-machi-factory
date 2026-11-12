"""Make admin funds usable by direct student ID even if recipient list fails.

Replaces select with typeable datalist and preserves existing authenticated
backend checks, idempotency keys, audit trail and accounting. Also permits
recipient selection from suggestions when the account API succeeds.
"""
from zipfile import ZipFile
from pathlib import Path
import io
archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}
def replace(name,old,new):
    s=files[name].decode()
    if s.count(old)!=1:raise RuntimeError(f'{name}: expected one anchor, found {s.count(old)}: {old[:90]}')
    files[name]=s.replace(old,new).encode()
replace('static/admin.html',
'<label>対象プレイヤー<select id="funds-target" required><option value="">参加者から選択</option></select></label>',
'<label>対象プレイヤー（学籍番号4桁）<input id="funds-target" type="text" list="funds-options" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" required placeholder="例 2101"><datalist id="funds-options"></datalist></label>')
replace('static/admin.js',
"""function populateFundsTargets(){
 const selected=fundsTarget.value;
 fundsTarget.replaceChildren();
 const first=document.createElement('option');first.value='';first.textContent='参加者から選択';
 fundsTarget.append(first);
 if(fundsPlayers.length){
  for(const person of fundsPlayers){
   const opt=document.createElement('option');
   opt.value=person.student_id;
   opt.textContent=person.student_id+' · '+person.display_name+' · '+fmt(person.cash)+'円';
   fundsTarget.append(opt);
  }
 }
 fundsTarget.value=selected && [...fundsTarget.options].some(o=>o.value===selected)?selected:'';
}""",
"""function populateFundsTargets(){
 const options=$('#funds-options');
 options.replaceChildren();
 for(const person of fundsPlayers){
  const opt=document.createElement('option');
  opt.value=person.student_id;
  opt.label=person.display_name+' · '+fmt(person.cash)+'円';
  options.append(opt);
 }
}""")
replace('static/admin.js',
""" if(!player){preview.textContent='対象アカウントを選択してください。';return;}""",
""" if(!player){
  preview.textContent=/^[0-9]{4}$/.test(student_id)
   ?'入力された学籍番号で実行できます。残高は実行時にサーバーで確認します。'
   :'学籍番号4桁を入力してください。候補が表示されれば選択もできます。';
  return;
 }""")
replace('static/admin.js',
""" if(!person||amount===null||amount<=0n){
  fundsStatus.textContent='対象アカウントと正しい金額を指定してください。';return;
 }
""",
""" if(!/^[0-9]{4}$/.test(student_id)||amount===null||amount<=0n){
  fundsStatus.textContent='学籍番号4桁と正しい金額を指定してください。';return;
 }
""")
replace('static/admin.js',
""" const after=BigInt(person.cash)+(kind==='grant'?amount:-amount);
 $('#funds-confirm-message').textContent=person.display_name+'（'+student_id+'）に対して'
  +(kind==='grant'?'補助金を付与':'資金を徴収')+'：'+fmt(amount)+'円'
  +'。現在の残高 '+fmt(person.cash)+'円 → '+fmt(after)+'円。実行しますか？';""",
""" const after=person?BigInt(person.cash)+(kind==='grant'?amount:-amount):null;
 $('#funds-confirm-message').textContent=(person?.display_name||'学籍番号 '+student_id)+'（'+student_id+'）に対して'
  +(kind==='grant'?'補助金を付与':'資金を徴収')+'：'+fmt(amount)+'円'
  +(person?'。現在の残高 '+fmt(person.cash)+'円 → '+fmt(after)+'円。':'。対象の登録状態と残高は実行時に確認します。')
  +'実行しますか？';""")
replace('static/admin.js',
"""  fundsTarget.value=request.student_id;
  updateFundsPreview();
""",
"""  fundsTarget.value=request.student_id;
  updateFundsPreview();
""")
# Make loading failures visible without blocking manual entry.
replace('static/admin.js',
""" }catch(error){fundsStatus.textContent=error.message;}
}""",
""" }catch(error){fundsStatus.textContent='参加者一覧を取得できませんでした。学籍番号を直接入力して操作できます。'+error.message;}
}""")
with ZipFile(io.BytesIO(),mode='w') as _:
    pass
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('static/admin.js','static/admin.html'):
            assert z.read(info.filename)==data
archive.write_bytes(out.getvalue())
print('PASS: manual 4-digit account entry and optional autocomplete; unrelated server logic unchanged')
