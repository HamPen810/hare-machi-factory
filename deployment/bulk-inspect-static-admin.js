(()=>{const $=s=>document.querySelector(s),{fmt,parseWhole}=window.TeruNumber,names={white:'てるてる坊主',sea:'海坊主',shisa:'シーサー坊主'};let data=null,busy=false,version=0;
function notice(t){$('#notice').textContent=t;}
async function api(path,body){const r=await fetch('/api/admin/'+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,credentials:'same-origin'});const d=await r.json();if(!r.ok){if(r.status===401){data=null;$('#dashboard').hidden=true;$('#login').hidden=false;}throw Error(d.error||'通信できませんでした。');}return d;}
function table(target,headers,rows){const parent=$(target);parent.replaceChildren();if(!rows.length){parent.textContent='該当するデータはありません。';return;}const t=document.createElement('table'),head=document.createElement('thead'),tr=document.createElement('tr');for(const text of headers){const th=document.createElement('th');th.scope='col';th.textContent=text;tr.append(th);}head.append(tr);t.append(head);const body=document.createElement('tbody');for(const row of rows){const tr=document.createElement('tr');for(const text of row){const td=document.createElement('td');td.className='name';td.textContent=text;tr.append(td);}body.append(tr);}t.append(body);parent.append(t);}
function render(){const s=data.summary;$('#event').textContent=(data.event.practice?'練習データ · ':'大会データ · ')+{before:'開催前',open:'開催中',closed:'終了'}[data.event.phase]+' · 締切 11/19 20:00';$('#updated').textContent='最終更新 '+new Date(data.now).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'})+'（日本時間）';$('#stats').replaceChildren();for(const [label,value]of [['参加者',fmt(s.players)+'人'],['累計製造',fmt(s.manufactured)+'個'],['累計売上',fmt(s.revenue)+'円'],['累計純利益',fmt(s.net_profit)+'円'],['受付中の出荷',fmt(s.pending_shipments)+'件'],['精算済み',fmt(s.settled_rounds)+'回']]){const card=document.createElement('div');card.className='stat';const small=document.createElement('span'),large=document.createElement('strong');small.textContent=label;large.textContent=value;card.append(small,large);$('#stats').append(card);}renderPlayers();renderRanks();table('#pending-table',['学籍番号','名前','商品','数量','価格'],data.pending.map(r=>[r.student_id,r.display_name,names[r.product],fmt(r.quantity)+'個',fmt(r.price)+'円']));table('#market-table',['精算回の終了時刻','商品','流通量','販売数','平均価格','店舗数'],data.market.map(r=>[new Date((r.round+1)*60000).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}),names[r.product],fmt(r.offered),fmt(r.sold),r.average_price===null?'販売なし':fmt(Number(Number(r.average_price).toFixed(2)))+'円',r.sellers]));}
function renderPlayers(){if(!data)return;const query=$('#search').value.trim(),cls=$('#class').value,rows=data.players.filter(p=>(!cls||String(p.class_number)===cls)&&(!query||p.student_id.includes(query)||p.display_name.includes(query)));$('#count').textContent=rows.length+'人 / 全'+data.players.length+'人';table('#players-table',['学籍番号','名前','所持金','製造数','純利益','売上','強化段階','倉庫在庫'],rows.map(p=>[p.student_id,p.display_name,fmt(p.cash)+'円',fmt(p.manufactured)+'個',fmt(p.net_profit)+'円',fmt(p.revenue)+'円',p.tier,p.stock.map(s=>names[s.product]+' '+fmt(s.quantity)+'個').join(' / ')||'なし']));}
function renderRanks(){if(!data)return;const m=$('#metric').value,scope=$('#scope').value;table('#rankings-table',['順位',scope==='individual'?'名前':'クラス',$('#metric').selectedOptions[0].textContent],data.rankings[m][scope].map(r=>[r.rank+'位',scope==='individual'?r.display_name:r.class_number+'組',fmt(r[m])+(m==='manufactured'?'個':'円')]));}
async function refresh(silent=false){if(busy)return;busy=true;const v=version;try{const next=await api('dashboard');if(v!==version)return;data=next;$('#login').hidden=true;$('#dashboard').hidden=false;render();notice('');}catch(e){if(!silent)notice(e.message);}finally{busy=false;}}
function renderSettings(settings){
 $('#maintenance-state').textContent=settings.maintenance?'サーバーメンテナンス中':'ゲーム稼働中';
 $('#pause-game').disabled=settings.maintenance;
 $('#resume-game').disabled=!settings.maintenance;
 if (settings.default_rulebook !== undefined || settings.rulebook) {
  $('#rulebook-editor').value=settings.rulebook || settings.default_rulebook;
 }
}
async function openControls(){
 const settings=await api('settings');
 $('#login').hidden=true;
 $('#dashboard').hidden=false;
 renderSettings(settings);
}
async function updateSetting(button,field,value){
 button.disabled=true;
 try{
  renderSettings(await api('settings',{field,value}));
  notice('設定を反映しました。');
 }catch(error){
  button.disabled=false;
  notice(error.message);
 }finally{
  if(field==='announcement'||field==='rulebook')button.disabled=false;
 }
}
$('#pause-game').onclick=event=>updateSetting(event.currentTarget,'maintenance',true);
$('#resume-game').onclick=event=>updateSetting(event.currentTarget,'maintenance',false);
$('#rulebook-form').onsubmit=event=>{
 event.preventDefault();
 void updateSetting(event.submitter,'rulebook',$('#rulebook-editor').value);
};
$('#announcement-form').onsubmit=event=>{
 event.preventDefault();
 void updateSetting(event.submitter,'announcement',$('#announcement').value);
};
$('#player-form').onsubmit=async event=>{
 event.preventDefault();
 const button=event.submitter,operation=button.value,student_id=$('#target-student').value;
 if(operation==='reset'&&!window.confirm(student_id+' の登録情報とゲーム進捗を削除します。続けますか？'))return;
 button.disabled=true;
 try{
  const result=await api('player',{student_id,operation});
  notice(result.display_name+' の'+{freeze:'凍結',unfreeze:'凍結解除',reset:'リセット'}[operation]+'を反映しました。');
 }catch(error){notice(error.message);}
 finally{button.disabled=false;}
};
$('#login-form').onsubmit=async event=>{
 event.preventDefault();
 const button=event.submitter;
 button.disabled=true;
 try{
  await api('login',{password:$('#password').value});
  $('#password').value='';
  version++;
  await openControls();
  void loadFundsHistory();
  notice('');
 }catch(error){notice(error.message);}
 finally{button.disabled=false;}
};
$('#logout').onclick=async()=>{try{await api('logout',{});version++;data=null;fundsPlayers=[];populateFundsTargets();$('#dashboard').hidden=true;$('#login').hidden=false;$('#stats').replaceChildren();for(const s of ['#players-table','#rankings-table','#pending-table','#market-table'])$(s).replaceChildren();notice('ログアウトしました。');}catch(e){notice(e.message);}};
$('#refresh').onclick=()=>refresh();$('#search').oninput=renderPlayers;$('#class').onchange=renderPlayers;$('#metric').onchange=renderRanks;$('#scope').onchange=renderRanks;
const bankConfig = $('#bank-config');
const bankMarket = $('#bank-market');
const bankStatus = $('#admin-bank-status');
const bankControls = [...$('#panel-bank').querySelectorAll('button')];
let bankWorking = false;
let bankPending;
async function loadBankAdmin() {
 const {settings,offers} = await api('bank');
 const f = bankConfig.elements;
 f.enabled.checked = settings.enabled;
 f.demand.value = settings.demand_bps / 100;
 f.lend.value = settings.lend_bps / 100;
 f.borrow.value = settings.borrow_bps / 100;
 f.limit.value = settings.limit;
 const exp = settings.exponential;
 f.use_exponential.checked = Boolean(exp);
 if (exp) {
  f.tax_start.value = exp.threshold;
  f.tax_step.value = exp.step;
  f.tax_base.value = exp.base_bps / 100;
 }
 f.brackets.value = settings.brackets.map(([threshold,rate])=>threshold+','+rate/100).join('\n');
 $('#bank-offers').textContent = offers.map(r=>names[r.product]+' '+fmt(r.quantity)+'個 × '+fmt(r.price)+'円').join(' ／ ') || '銀行の出品はありません。';
}
async function bankAdminRequest(payload) {
 if (bankWorking) return;
 const signature = JSON.stringify(payload);
 if (!bankPending || bankPending.signature !== signature) bankPending = {signature,key:crypto.randomUUID()};
 bankWorking = true;
 bankControls.forEach(b=>b.disabled=true);
 try {
  const result = await api('bank', {...payload,key:bankPending.key});
  bankPending = null;
  if (result.asset_tax !== undefined) {
   const summary=fmt(result.players)+'人 · 合計 '+fmt(result.asset_tax)+'円';
   $('#asset-tax-review').hidden=result.applied;
   $('#asset-tax-summary').textContent='試算 '+summary+'。実行時に再計算します。';
   bankStatus.textContent=result.applied ? '総資産への課税を実行しました。'+summary : '';
   return;
  }
  $('#asset-tax-review').hidden=true;
  bankStatus.textContent = result.spent !== undefined ? '買い取り完了 · 売上総額 '+fmt(result.spent)+'円' : payload.kind==='offer' ? (BigInt(result.quantity)===0n ? '銀行の出品を取り下げました。' : '出品しました。市場に '+fmt(result.quantity)+'個を掲載中です。') : '保存しました。';
  await loadBankAdmin();
 } catch(error) { bankStatus.textContent = error.message; }
 finally { bankWorking=false; bankControls.forEach(b=>b.disabled=false); }
}
function basisPoints(value) {
 const points = parseWhole(value,2);
 if (points === null || points > 10000n) throw Error('率は0〜100％の範囲で小数第2位まで指定してください。');
 return Number(points);
}
function bankInteger(value) {
 const result = parseWhole(value);
 if (result === null) throw Error('整数になる数値を入力してください（例 1.25e+4）。');
 return result.toString();
}
$('#tab-bank').addEventListener('click', async () => {
 bankControls.forEach(b=>b.disabled=true);
 try { await loadBankAdmin(); bankControls.forEach(b=>b.disabled=false); }
 catch(error) { bankStatus.textContent=error.message; }
});
bankConfig.onsubmit = event => {
 event.preventDefault();
 const f = bankConfig.elements;
 try {
  const brackets = f.brackets.value.split(/\r?\n/).filter(line=>line.trim()).map(line=>{
   const parts = line.split(',').map(part=>part.trim());
   if (parts.length!==2) throw Error('税率の行は「売上の下限, 税率％」で入力してください。');
   return [bankInteger(parts[0]),basisPoints(parts[1])];
  });
  const exponential = f.use_exponential.checked ? {
   threshold:bankInteger(f.tax_start.value),step:bankInteger(f.tax_step.value),
   base_bps:basisPoints(f.tax_base.value)
  } : null;
  void bankAdminRequest({kind:'configure',enabled:f.enabled.checked,limit:bankInteger(f.limit.value),exponential,
   demand_bps:basisPoints(f.demand.value),lend_bps:basisPoints(f.lend.value),borrow_bps:basisPoints(f.borrow.value),brackets});
 } catch(error) { bankStatus.textContent=error.message; }
};
$('#asset-tax-preview').onclick=()=>bankAdminRequest({kind:'asset_tax_preview'});
$('#asset-tax-apply').onclick=()=>bankAdminRequest({kind:'asset_tax_apply'});
const marketConfirm = $('#bank-market-confirm');
let marketOrder;
bankMarket.onsubmit = event => {
 event.preventDefault();
 const kind = event.submitter?.value;
 if (!kind || bankWorking) return;
 const f = bankMarket.elements;
 try {
  const quantity = bankInteger(f.quantity.value);
  const price = kind==='offer' && BigInt(quantity)>0n ? bankInteger(f.price.value) : '1';
  marketOrder = {kind,product:$('#bank-market-product').value,quantity,price};
  $('#bank-market-confirm-text').textContent = names[marketOrder.product]+' '+fmt(quantity)+'個'
   +(kind==='buyout' ? 'を安い出品から買い取ります。' : BigInt(quantity)===0n ? '。銀行の出品を取り下げます。' : 'を単価 '+fmt(price)+'円で出品します。');
  marketConfirm.hidden = false;
  $('#bank-market-apply').focus();
 } catch(error) { bankStatus.textContent=error.message; }
};
$('#bank-market-apply').onclick = () => {
 if (!marketOrder || bankWorking) return;
 marketConfirm.hidden=true;
 void bankAdminRequest(marketOrder);
};
$('#bank-market-cancel').onclick = () => {
 marketOrder=null;
 marketConfirm.hidden=true;
};
const fundsTarget=$('#funds-target');
const fundsForm=$('#funds-form');
const fundsStatus=$('#funds-status');
let fundsPending=null, fundsBusy=false, fundsPlayers=[];
function populateFundsTargets(){
 const options=$('#funds-options');
 options.replaceChildren();
 for(const person of fundsPlayers){
  const opt=document.createElement('option');
  opt.value=person.student_id;
  opt.label=person.display_name+' · '+fmt(person.cash)+'円';
  options.append(opt);
 }
}
function updateFundsPreview(){
 const student_id=fundsTarget.value;
 const player=fundsPlayers.find(p=>p.student_id===student_id);
 const amount=parseWhole($('#funds-amount').value);
 const kind=$('#funds-kind').value;
 const preview=$('#funds-preview');
 if(!player){
  preview.textContent=/^[0-9]{4}$/.test(student_id)
   ?'入力された学籍番号で実行できます。残高は実行時にサーバーで確認します。'
   :'学籍番号4桁を入力してください。候補が表示されれば選択もできます。';
  return;
 }
 if(amount===null||amount<1n){
  preview.textContent='現在の所持金：'+fmt(player.cash)+'円 · 正の整数を入力してください。';
  return;
 }
 const cash=BigInt(player.cash);
 const remaining=kind==='grant'?cash+amount:cash-amount;
 preview.textContent='現在 '+fmt(cash)+'円 → 実行後 '+fmt(remaining)+'円'
  +(remaining<0n?'（マイナス残高）':'');
}
function closeFundsConfirmation(){
 $('#funds-confirm').hidden=true;
 fundsPending=null;
}
$('#tab-funds').addEventListener('click',()=>{
 void loadFundsHistory();
});
async function loadFundsHistory(){
 try{
  fundsStatus.textContent='アカウントを読み込み中…';
  const result=await api('funds');
  fundsPlayers=result.players||[];
  populateFundsTargets();
  updateFundsPreview();
  fundsStatus.textContent='';
  const rows=(result.history||[]).map(x=>[
   new Date(Number(x.created_at)).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}),
   x.student_id+' · '+x.name,
   x.kind==='grant'?'補助金':'徴収',
   fmt(x.amount)+'円',
   fmt(x.before_cash)+'円 → '+fmt(x.after_cash)+'円',
   x.note||'—'
  ]);
  table('#funds-history',['日時','対象','操作','金額','残高変化','理由'],rows);
 }catch(error){fundsStatus.textContent='参加者一覧を取得できませんでした。学籍番号を直接入力して操作できます。'+error.message;}
}
for(const id of ['funds-target','funds-kind','funds-amount']){
 $( '#'+id).addEventListener('input',()=>{closeFundsConfirmation();updateFundsPreview();});
}
$('#funds-note').addEventListener('input',closeFundsConfirmation);
fundsForm.onsubmit=event=>{
 event.preventDefault();
 if(fundsBusy)return;
 const student_id=fundsTarget.value;
 const person=fundsPlayers.find(x=>x.student_id===student_id);
 const amount=parseWhole($('#funds-amount').value);
 const kind=$('#funds-kind').value;
 if(!/^[0-9]{4}$/.test(student_id)||amount===null||amount<=0n){
  fundsStatus.textContent='学籍番号4桁と正しい金額を指定してください。';return;
 }
 fundsPending={student_id,kind,amount:amount.toString(),note:$('#funds-note').value.trim(),key:crypto.randomUUID()};
 const after=person?BigInt(person.cash)+(kind==='grant'?amount:-amount):null;
 $('#funds-confirm-message').textContent=(person?.display_name||'学籍番号 '+student_id)+'（'+student_id+'）に対して'
  +(kind==='grant'?'補助金を付与':'資金を徴収')+'：'+fmt(amount)+'円'
  +(person?'。現在の残高 '+fmt(person.cash)+'円 → '+fmt(after)+'円。':'。対象の登録状態と残高は実行時に確認します。')
  +'実行しますか？';
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
  await loadFundsHistory();
  fundsTarget.value=request.student_id;
  updateFundsPreview();
  // Refresh heavyweight dashboard separately; a chart failure must not
  // disable player selection or transaction history.
  void refresh(true);
 }catch(error){
  // Preserve the request ID after network errors so a retry cannot double charge.
  fundsStatus.textContent=error.message;
 }finally{
  fundsBusy=false;
  $('#funds-apply').disabled=false;
  $('#funds-cancel').disabled=false;
 }
};
let onlinePoints=[],onlineFetchedAt=0,onlineActive=false,onlineTimer=null,onlineBusy=false;
function renderOnlineGraph(){
 const range=Number($('#online-range').value);
 const last=Math.floor(onlineFetchedAt/60000);
 const first=last-range;
 const points=onlinePoints.filter(p=>p.minute>=first&&p.minute<=last);
 const maximum=points.reduce((m,p)=>Math.max(m,p.count),0);
 $('#online-peak').textContent=points.length?maximum+'人':'—';
 const graph=$('#online-graph');
 graph.replaceChildren();
 const ns='http://www.w3.org/2000/svg';
 const svg=document.createElementNS(ns,'svg');
 svg.setAttribute('viewBox','0 0 760 250');
 svg.setAttribute('width','100%');
 svg.setAttribute('role','img');
 svg.setAttribute('aria-label','過去'+(range===60?'1':range===360?'6':'24')+'時間のオンライン人数');
 svg.style.minWidth='320px';
 const add=(tag,attrs,text)=>{
  const node=document.createElementNS(ns,tag);
  for(const [k,v] of Object.entries(attrs))node.setAttribute(k,String(v));
  if(text!==undefined)node.textContent=text;
  svg.append(node);return node;
 };
 const left=46,right=744,top=18,bottom=211;
 const height=Math.max(1,maximum);
 const x=m=>left+(m-first)/range*(right-left);
 const y=count=>bottom-count/height*(bottom-top);
 for(let i=0;i<=4;i++){
  const count=Math.ceil(maximum*i/4);
  const yy=y(count);
  add('line',{x1:left,y1:yy,x2:right,y2:yy,stroke:'#d2ddd1','stroke-width':1});
  add('text',{x:left-7,y:yy+4,'text-anchor':'end','font-size':12,fill:'#526e68'},count);
 }
 for(let i=0;i<=4;i++){
  const tick=first+range*i/4;
  add('text',{x:x(tick),y:236,'text-anchor':i===0?'start':i===4?'end':'middle','font-size':11,fill:'#526e68'},
   new Date(tick*60000).toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit'}));
 }
 let segment=[];
 const drawSegment=()=>{
  if(!segment.length)return;
  if(segment.length>1)add('polyline',{points:segment.map(p=>x(p.minute)+','+y(p.count)).join(' '),
   fill:'none',stroke:'#167464','stroke-width':2.5,'stroke-linejoin':'round','stroke-linecap':'round'});
  else add('circle',{cx:x(segment[0].minute),cy:y(segment[0].count),r:3,fill:'#167464'});
  segment=[];
 };
 for(let i=0;i<points.length;i++){
  if(i>0&&points[i].minute-points[i-1].minute>1)drawSegment();
  segment.push(points[i]);
 }
 drawSegment();
 graph.append(svg);
 $('#online-description').textContent=points.length?
  '計測 '+points.length+'点 · 最大 '+maximum+'人 · '+new Date(onlineFetchedAt).toLocaleString('ja-JP')+' 時点'
  :'この期間にはまだ計測記録がありません。';
}
async function loadOnline(){
 if(onlineBusy)return;
 onlineBusy=true;
 try{
  const result=await api('online');
  onlinePoints=(result.samples||[]).map(p=>({minute:Number(p.minute),count:Number(p.count)}));
  onlineFetchedAt=Number(result.sampled_at)||Date.now();
  $('#online-count').textContent=Number(result.online)+'人';
  $('#online-updated').textContent=new Date(onlineFetchedAt).toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit'});
  renderOnlineGraph();
 }catch(error){
  $('#online-description').textContent='人数の取得に失敗しました：'+error.message;
 }finally{onlineBusy=false;}
}
$('#online-range').onchange=renderOnlineGraph;
$('#online-refresh').onclick=()=>void loadOnline();
$('#tab-online').addEventListener('click',()=>{
 onlineActive=true;
 void loadOnline();
});
for(const tab of document.querySelectorAll('[data-panel]')){
 if(tab.id!=='tab-online')tab.addEventListener('click',()=>{onlineActive=false;});
}
onlineTimer=setInterval(()=>{
 if(onlineActive&&!document.hidden&&$('#dashboard')&&!$('#dashboard').hidden)void loadOnline();
},60000);
for(const b of document.querySelectorAll('[data-panel]'))b.onclick=()=>{for(const t of document.querySelectorAll('[data-panel]')){const active=t===b;t.setAttribute('aria-selected',String(active));$('#panel-'+t.dataset.panel).hidden=!active;}};
openControls().then(()=>loadFundsHistory()).catch(()=>{});
})();
