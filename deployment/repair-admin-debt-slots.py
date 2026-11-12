"""Repair admin UI: surface slot management, preserve financial success status.

The tested PostgreSQL backend already supports both features. The browser
integration test found that successful debt cancellations lose their status
as soon as transaction history refreshes. Also show additional registration
slots without requiring a hidden disclosure action.
"""
from pathlib import Path
from zipfile import ZipFile
import ast,io

archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}
def replace(name,old,new):
    data=files[name].decode('utf-8')
    n=data.count(old)
    if n!=1:raise RuntimeError(f'{name}: unexpected anchor count {n}: {old[:110]!r}')
    files[name]=data.replace(old,new).encode('utf-8')

# Make administrator-created registration slots clearly visible from the top
# of the game operations panel; the optional list is loaded at login.
replace('static/admin.html',
"""<details id="extra-slots-section"><summary>新規登録用の学籍番号を追加する</summary>""",
"""<details id="extra-slots-section" open><summary>追加プレイヤー登録枠の作成・管理</summary>""")
replace('static/admin.html',
""" <p class="muted">通常の登録範囲外の数字4桁を、新しいプレイヤー登録枠として許可します。追加した番号はゲーム画面から通常の新規登録ができます。ランキングで使用する所属クラスも指定してください。</p>""",
""" <p class="muted">通常の登録範囲外の数字4桁を追加すると、その番号でプレイヤーが新規登録できます。番号と所属クラス（1～8組）を設定してください。登録枠の作成だけではプレイヤーアカウントは作られません。</p>""")

# Fundamental bug: apply() wrote "success" but loadFundsHistory()
# immediately overwrote it with loading and then an empty string.
replace('static/admin.js',
"""  fundsStatus.textContent='アカウントを読み込み中…';
  const result=await api('funds');""",
"""  const result=await api('funds');""")
replace('static/admin.js',
"""  populateFundsTargets();
  updateFundsPreview();
  fundsStatus.textContent='';
  const rows=(result.history||[]).map(x=>[""",
"""  populateFundsTargets();
  updateFundsPreview();
  const rows=(result.history||[]).map(x=>[""")

# Give clear feedback when there is no debt to forgive, rather than an
# ambiguous "no matching recipients" error.
replace('admin_fund_ops.py',
"""        if not players: raise ValueError('対象のアカウントがありません。')
    else:""",
"""        if not players: raise ValueError('対象のアカウントがありません。')
        if payload['kind']=='forgive' and not any(p['debt']>0 for p in players):
            raise ValueError('このアカウントに帳消しできる借入残高はありません。')
    else:""")

# Ensure a slot-creation request can always be submitted from browser
# form submit or Enter key (some keyboard submissions lack event.submitter).
replace('static/admin.js',
"""$('#extra-slot-form').onsubmit=async event=>{
 event.preventDefault();
 if(extraSlotsBusy)return;
 extraSlotsBusy=true;
 const button=event.submitter;
 button.disabled=true;""",
"""$('#extra-slot-form').onsubmit=async event=>{
 event.preventDefault();
 if(extraSlotsBusy)return;
 extraSlotsBusy=true;
 const button=event.submitter||$('#extra-slot-form button[type="submit"]');
 button.disabled=true;""")
# Do not replace a successful create message with a subsequent failed list GET.
replace('static/admin.js',
""" }catch(error){$('#extra-slot-status').textContent='追加枠を取得できませんでした：'+error.message;}
}""",
""" }catch(error){$('#extra-slot-list').textContent='登録枠の一覧を取得できませんでした：'+error.message;}
}""")
# Load once the administrator session is authenticated; details is open.
replace('static/admin.js',
"""async function openControls(){
 const settings=await api('settings');
 $('#login').hidden=true;
 $('#dashboard').hidden=false;
 renderSettings(settings);
}""",
"""async function openControls(){
 const settings=await api('settings');
 $('#login').hidden=true;
 $('#dashboard').hidden=false;
 renderSettings(settings);
 if($('#extra-slots-section').open)void loadExtraSlots();
}""")

for f in ('admin_fund_ops.py',):
    ast.parse(files[f].decode('utf-8'),filename=f)
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('static/admin.html','static/admin.js','admin_fund_ops.py'):
            assert z.read(info.filename)==data,info.filename
archive.write_bytes(out.getvalue())
print('PASS: debt success status persists; slot management visible and auto-loaded, back-end financial logic unchanged')
