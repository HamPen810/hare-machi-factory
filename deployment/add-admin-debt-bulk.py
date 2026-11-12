"""Patch production ZIP with administrative debt forgiveness & bulk asset operations."""
from pathlib import Path
from zipfile import ZipFile
import ast,io
archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}
def change(name,old,new):
    body=files[name].decode('utf-8')
    if body.count(old)!=1:
        raise RuntimeError(f'{name}: expected single anchor; found {body.count(old)} {old[:90]!r}')
    files[name]=body.replace(old,new).encode('utf-8')

newmodule=Path('deployment/admin_fund_ops.py').read_bytes()
ast.parse(newmodule.decode())
files['admin_fund_ops.py']=newmodule

# Initialized only at server bootstrap; no migrations destructive to player data.
# admin.py uses CRLF in its legacy sections, so match one line, not its newline.
change('admin.py',
"""            self.initialize_online(self.db)""",
"""            self.initialize_online(self.db)
            from admin_fund_ops import install
            install(self.db)""")

change('server.py',
"""                    if self.path=='/api/admin/funds':
""",
"""                    if self.path=='/api/admin/funds-extra':
                        from admin_fund_ops import perform,history
                        if write:
                            return self.reply(200,perform(admin,data,now))
                        return self.reply(200,{'history':history(a.db)})
                    if self.path=='/api/admin/funds':
""")

change('static/admin.html',
"""<label>操作<select id="funds-kind"><option value="grant">補助金を付与</option><option value="collect">資金を徴収</option></select></label>""",
"""<label>操作<select id="funds-kind"><option value="grant">補助金を付与</option><option value="collect">資金を徴収</option><option value="forgive">借金帳消し</option></select></label>""")
change('static/admin.html',
"""<label>金額（円）<input id="funds-amount" type="text" required placeholder="例 1e+10"></label>""",
"""<label id="funds-amount-label">金額（円）<input id="funds-amount" type="text" required placeholder="例 1e+10"></label>""")
change('static/admin.html',
"""<h3>最近の資金調整履歴</h3>
<div id="funds-history" class="table-wrap"></div>""",
"""<h3>最近の資金調整履歴</h3>
<div id="funds-history" class="table-wrap"></div>
<h3>借金帳消し履歴</h3>
<div id="debt-history" class="table-wrap"></div>
<hr style="border:0;border-top:1px solid #d2ddd1;margin:24px 0">
<h2>財産額による一括資金操作</h2>
<p class="muted">対象は現在の総資産（所持金＋預け入れの満期受取額＋工場・市場在庫の定価評価額）で判定します。借入残高は差し引きません。下限・上限の空欄は制限なしです。</p>
<form id="bulk-funds-form">
<div class="toolbar">
<label>操作<select id="bulk-funds-kind"><option value="grant">補助金を一括付与</option><option value="collect">資金を一括徴収</option><option value="forgive">借金を一括帳消し</option></select></label>
<label>総資産の下限（円）<input id="bulk-assets-min" type="text" placeholder="空欄なら制限なし"></label>
<label>総資産の上限（円）<input id="bulk-assets-max" type="text" placeholder="空欄なら制限なし"></label>
</div>
<div class="toolbar">
<label id="bulk-mode-label">金額の決め方<select id="bulk-amount-mode"><option value="fixed">対象者全員に固定額</option><option value="percent">総資産に対する割合</option></select></label>
<label id="bulk-fixed-label">1人あたりの金額（円）<input id="bulk-fixed-amount" type="text" value="1000" placeholder="例 1e+6"></label>
<label id="bulk-percent-label" hidden>総資産に対する割合（％）<input id="bulk-percent-value" type="text" value="10" placeholder="例 10"></label>
</div>
<label>理由・メモ（任意）<input id="bulk-note" type="text" maxlength="160" placeholder="例 イベント一括報酬"></label>
<button id="bulk-preview" type="submit">対象と金額を試算</button>
</form>
<div id="bulk-review" hidden>
<p id="bulk-summary" role="status"></p>
<div id="bulk-preview-table" class="table-wrap"></div>
<p class="muted">実行時にもう一度資産を確認します。試算後に金額や対象者が変わった場合は実行を止めます。</p>
<div class="toolbar"><button id="bulk-apply" class="primary" type="button">表示内容で一括実行</button><button id="bulk-cancel" type="button">キャンセル</button></div>
</div>
<p id="bulk-status" role="status" aria-live="polite"></p>""")

# Keep the existing individual cash flow untouched; debt is a separate action.
change('static/admin.js',
""" const amount=parseWhole($('#funds-amount').value);
 const kind=$('#funds-kind').value;
 const preview=$('#funds-preview');""",
""" const amount=parseWhole($('#funds-amount').value);
 const kind=$('#funds-kind').value;
 $('#funds-amount-label').hidden=kind==='forgive';
 $('#funds-amount').required=kind!=='forgive';
 const preview=$('#funds-preview');
 if(kind==='forgive'){
  preview.textContent='対象者のすべての銀行借入をゼロにします。所持金・預け入れ・純利益は変わりません。';
  return;
 }""")
change('static/admin.js',
"""  table('#funds-history',['日時','対象','操作','金額','残高変化','理由'],rows);
 }catch(error)""",
"""  table('#funds-history',['日時','対象','操作','金額','残高変化','理由'],rows);
  await loadDebtHistory();
 }catch(error)""")

change('static/admin.js',
"""fundsForm.onsubmit=event=>{
 event.preventDefault();
 if(fundsBusy)return;
 const student_id=fundsTarget.value;""",
"""fundsForm.onsubmit=async event=>{
 event.preventDefault();
 if(fundsBusy)return;
 const student_id=fundsTarget.value;""")
change('static/admin.js',
""" const kind=$('#funds-kind').value;
 if(!/^[0-9]{4}$/.test(student_id)||amount===null||amount<=0n){""",
""" const kind=$('#funds-kind').value;
 if(kind==='forgive'){
  if(!/^[0-9]{4}$/.test(student_id)){
   fundsStatus.textContent='学籍番号4桁を入力してください。';return;
  }
  fundsBusy=true;
  try{
   const result=await api('funds-extra',{action:'preview',scope:'single',kind:'forgive',student_id,note:$('#funds-note').value.trim()});
   fundsPending={action:'apply',scope:'single',kind:'forgive',student_id,
    note:$('#funds-note').value.trim(),preview_digest:result.digest,key:crypto.randomUUID()};
   $('#funds-confirm-message').textContent=student_id+' の銀行借入 '+fmt(result.total)+'円をすべて帳消しにします。所持金は変わりません。実行しますか？';
   $('#funds-confirm').hidden=false;
   fundsStatus.textContent='';
  }catch(error){fundsStatus.textContent=error.message;}
  finally{fundsBusy=false;}
  return;
 }
 if(!/^[0-9]{4}$/.test(student_id)||amount===null||amount<=0n){""")

change('static/admin.js',
"""  const result=await api('funds',request);
  fundsPending=null;
  $('#funds-confirm').hidden=true;
  fundsStatus.textContent=(result.already_applied?'処理済み：':'実行完了：')
   +result.display_name+' · '+(result.kind==='grant'?'補助金':'徴収')
   +' '+fmt(result.amount)+'円 · 残高 '+fmt(result.after_cash)+'円';""",
"""  const result=await api(request.kind==='forgive'?'funds-extra':'funds',request);
  fundsPending=null;
  $('#funds-confirm').hidden=true;
  fundsStatus.textContent=request.kind==='forgive'
   ?(result.already_applied?'処理済み：':'帳消し完了：')+request.student_id+' · 借入 '+fmt(result.total)+'円'
   :(result.already_applied?'処理済み：':'実行完了：')
    +result.display_name+' · '+(result.kind==='grant'?'補助金':'徴収')
    +' '+fmt(result.amount)+'円 · 残高 '+fmt(result.after_cash)+'円';""")

bulk_js=r"""async function loadDebtHistory(){
 try{
  const r=await api('funds-extra');
  table('#debt-history',['日時','学籍番号・名前','帳消し額','理由'],
   (r.history||[]).map(v=>[
    new Date(Number(v.created_at)).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}),
    v.student_id+' · '+v.name,fmt(v.debt)+'円',v.note||'—'
   ]));
 }catch(error){$('#debt-history').textContent='借金の履歴を取得できませんでした：'+error.message;}
}
let bulkPending=null,bulkBusy=false;
function updateBulkControls(){
 const forgive=$('#bulk-funds-kind').value==='forgive';
 $('#bulk-mode-label').hidden=forgive;
 const percent=$('#bulk-amount-mode').value==='percent';
 $('#bulk-fixed-label').hidden=forgive||percent;
 $('#bulk-percent-label').hidden=forgive||!percent;
 $('#bulk-review').hidden=true;
 bulkPending=null;
}
for(const id of ['bulk-funds-kind','bulk-amount-mode','bulk-assets-min','bulk-assets-max',
 'bulk-fixed-amount','bulk-percent-value','bulk-note']){
 $('#'+id).addEventListener('input',updateBulkControls);
}
function bulkParams(){
 const kind=$('#bulk-funds-kind').value;
 const mode=$('#bulk-amount-mode').value;
 const min=$('#bulk-assets-min').value.trim();
 const max=$('#bulk-assets-max').value.trim();
 const parseLimit=text=>{
  if(!text)return '';
  const negative=text[0]==='-';
  const amount=parseWhole(negative?text.slice(1):text);
  if(amount===null)throw Error('財産の下限・上限は整数で入力してください。');
  return (negative?'-':'')+amount.toString();
 };
 const data={scope:'bulk',kind,min_assets:parseLimit(min),max_assets:parseLimit(max),
  note:$('#bulk-note').value.trim()};
 if(kind!=='forgive'){
  data.amount_mode=mode;
  if(mode==='fixed'){
   const amount=parseWhole($('#bulk-fixed-amount').value);
   if(amount===null||amount<1n)throw Error('正の整数金額を入力してください。');
   data.amount=amount.toString();
  }else{
   const bps=parseWhole($('#bulk-percent-value').value,2);
   if(bps===null||bps<1n||bps>10000n)throw Error('割合は0％超〜100％以下で入力してください。');
   data.percentage_bps=Number(bps);
  }
 }
 return data;
}
$('#bulk-funds-form').onsubmit=async event=>{
 event.preventDefault();
 if(bulkBusy)return;
 bulkBusy=true;
 $('#bulk-preview').disabled=true;
 try{
  const params=bulkParams();
  const result=await api('funds-extra',{...params,action:'preview'});
  bulkPending={...params,action:'apply',preview_digest:result.digest,key:crypto.randomUUID()};
  $('#bulk-summary').textContent=(params.kind==='grant'?'補助金':params.kind==='collect'?'徴収':'借金帳消し')
   +' · 対象 '+result.count+'人 · 合計 '+fmt(result.total)+'円。内容を確認して実行してください。';
  table('#bulk-preview-table',['学籍番号','名前','評価総資産','現在の所持金','処理額','処理後の所持金'],
   result.people.map(p=>[p.student_id,p.name,fmt(p.assets)+'円',fmt(p.cash)+'円',
    fmt(p.amount)+'円',fmt(p.after_cash)+'円']));
  $('#bulk-review').hidden=false;
  $('#bulk-status').textContent='';
 }catch(error){$('#bulk-review').hidden=true;bulkPending=null;$('#bulk-status').textContent=error.message;}
 finally{bulkBusy=false;$('#bulk-preview').disabled=false;}
};
$('#bulk-cancel').onclick=()=>{bulkPending=null;$('#bulk-review').hidden=true;};
$('#bulk-apply').onclick=async()=>{
 if(!bulkPending||bulkBusy)return;
 bulkBusy=true;
 $('#bulk-apply').disabled=true;
 $('#bulk-cancel').disabled=true;
 try{
  const request=bulkPending;
  const result=await api('funds-extra',request);
  bulkPending=null;
  $('#bulk-review').hidden=true;
  $('#bulk-status').textContent=(result.already_applied?'処理済み：':'実行完了：')
   +result.count+'人 · 合計 '+fmt(result.total)+'円';
  await loadFundsHistory();
  void refresh(true);
 }catch(error){
  // Keep the same key on retry. Server prevents duplicate financial transfers.
  $('#bulk-status').textContent=error.message;
 }finally{
  bulkBusy=false;
  $('#bulk-apply').disabled=false;
  $('#bulk-cancel').disabled=false;
 }
};
"""
change('static/admin.js',
"""let onlinePoints=[],onlineFetchedAt=0""",
bulk_js+"""let onlinePoints=[],onlineFetchedAt=0""")
for file in ('admin.py','server.py','admin_fund_ops.py'):
    ast.parse(files[file].decode(),filename=file)
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
    z.writestr('admin_fund_ops.py',files['admin_fund_ops.py'])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('admin.py','server.py','static/admin.html','static/admin.js'):
            if info.filename in files:
                assert z.read(info.filename)==data
archive.write_bytes(out.getvalue())
print('PASS: debt cancellation and bulk operations added, original bank/market code preserved')
