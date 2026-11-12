(()=>{
const $=s=>document.querySelector(s), ui=s=>$('[data-ui="'+s+'"]'), act=s=>$('[data-act="'+s+'"]');
const products=[{id:'white',name:'てるてる坊主',work:1,price:8,cost:1,unlock:0},{id:'sea',name:'海坊主',work:3,price:15,cost:4,unlock:300},{id:'shisa',name:'シーサー坊主',work:12,price:60,cost:22,unlock:1000}];
const {big,fmt,isLarge,parseWhole}=window.TeruNumber;
let piePage=0;let marketMode='add';let rankPage=0;let snapshot=null, page='factory', polling=false, generation=0,prices=[8,15,60];
const p=()=>products[Number(ui('product').value)];
ui('notice').hidden=true;
const banner=document.createElement('div');banner.id='event-banner';banner.className='tp-note';banner.style.cssText='padding:4px 16px;background:var(--tp-soft)';$('#who').after(banner);
const controls=document.createElement('div');controls.className='tp-inline';
for(const [id,label]of [['load-shipment','店頭の数量・価格を読み込む'],['cancel-shipment','残りを工場へ回収']]){const b=document.createElement('button');b.id=id;b.className='tp-small';b.textContent=label;controls.append(b);}ui('pending').before(controls);
let refreshQueued=false;
let factoryRevision=0;
let pendingAction=null;
const detailUpdated=new Map();
const detailPending=new Map();
let tapRefreshTimer;
function scheduleTapRefresh(){
 if(tapRefreshTimer!==undefined)return;
 tapRefreshTimer=setTimeout(()=>{
  tapRefreshTimer=undefined;
  if(snapshot&&!document.hidden)refresh();
 },5000);
}
function pending(factory=snapshot?.factory){return factory?.shipments.find(x=>x.product===p().id);}
function notice(s){$('#global-notice').textContent=s;}
async function api(path,data){
 const requestGeneration=generation;
 const transactional=path==='action' && typeof data?.key==='string' && data.key.length>0;
 const attempts=transactional?2:1;
 for(let attempt=0;attempt<attempts;attempt++){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),transactional?35000:15000);
  try{
   const response=await fetch('/api/'+path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined,credentials:'same-origin',signal:controller.signal});
   const body=await response.json().catch(()=>{throw Error('サーバーから応答がありません。少し待ってお試しください。');});
   if(!response.ok){
    if(body.maintenance){
     generation++;snapshot=null;pendingAction=null;tapQueue.length=0;
     $('#game').hidden=true;$('#auth').hidden=false;$('#auth-form').hidden=true;$('#maintenance-note').hidden=false;
    }
    if(response.status===401&&requestGeneration===generation){$('#game').hidden=true;$('#auth').hidden=false;snapshot=null;}
    if(transactional&&attempt+1<attempts&&[502,503,504].includes(response.status)&&!body.maintenance)continue;
    throw Object.assign(Error(body.error||'通信に失敗しました。'),{status:response.status});
   }
   return body;
  }catch(error){
   if(transactional&&attempt+1<attempts&&(!error.status||[502,503,504].includes(error.status)))continue;
   if(controller.signal.aborted)throw Error('応答に時間がかかっています。画面を確認してから再度お試しください。');
   throw error;
  }finally{clearTimeout(timer);}
 }
 throw Error('通信に失敗しました。');
}
function choosePage(next){notice('');page=next;if(page==='market'&&pending())ui('price').value=pending().price;$('#teru-playtest').dataset.page=page;$('.tp-product-picker').hidden=['ranks','collection','rules','announcements'].includes(page);for(const b of document.querySelectorAll('.tp-navigation [data-page]')){const active=b.dataset.page===page;b.setAttribute('aria-selected',String(active));$('#tp-page-'+b.dataset.page).hidden=!active;}placePicker();if(page==='announcements'){renderAnnouncements();void refreshSite();}if(snapshot)render();}
for(const b of document.querySelectorAll('.tp-navigation [data-page]'))b.onclick=()=>{choosePage(b.dataset.page);if(['market','data','ranks'].includes(page))refreshDetails(page);};
function effect(text,critical=false,helper=false){window.TeruFX?.tap(text,critical,helper);}
async function refresh(){if(pendingAction||buying)return;if(polling){refreshQueued=true;return;}polling=true;const gen=generation,revision=factoryRevision;try{
 const next=await api('factory');if(gen!==generation||revision!==factoryRevision)return;
 const old=snapshot;snapshot={...old,...next};showRareDiscovery();$('#auth').hidden=true;$('#game').hidden=false;
 if(old&&old.identity.id===next.identity.id&&page==='factory'&&!rareDialog.open){
  for(const product of products){const count=big(next.factory.auto_totals?.[product.id]||0)-big(old.factory.auto_totals?.[product.id]||0);if(count>0n&&product.id===p().id)window.TeruFX?.automatic(count);}
 }

 render();
 $('#auth-error').textContent='';
 $('#auth-form').elements.password.value='';
 }catch(e){if(gen===generation){if(snapshot){if(e.status!==503)notice(e.message);}else if($('#auth-error').textContent==='ゲームを読み込み中…')$('#auth-error').textContent='ゲームを読み込めませんでした。'+e.message;}}finally{polling=false;if(refreshQueued){refreshQueued=false;refresh();}}}
async function refreshDetails(tab){
 if(!snapshot||!['market','data','ranks'].includes(tab))return;
 const gen=generation;
 if(detailPending.get(tab)===gen)return;
 const refreshInterval=tab==='market'?60_000:600_000;
 const lastUpdated=detailUpdated.get(tab);
 if(lastUpdated!==undefined&&Date.now()-lastUpdated<refreshInterval)return;
 const rankList=tab==='ranks'&&!snapshot.rankings?$('#rank-list'):null;
 const chartSummary=tab==='data'&&!snapshot.timeline?$('#chart-summary'):null;
 if(chartSummary)chartSummary.textContent='市場の記録を読み込み中…';
 if(rankList)rankList.textContent='ランキングを読み込み中…';
 detailPending.set(tab,gen);
 try{
  const detail=await api(tab);
  if(gen!==generation||!snapshot)return;
  detailUpdated.set(tab,Date.now());
  Object.assign(snapshot,detail);
  if(page===tab)render();
 }catch(error){
  if(gen===generation&&page===tab){
   if(rankList)rankList.textContent='ランキングを読み込めませんでした。再度タブを開くと再試行します。';
   if(chartSummary)chartSummary.textContent='市場の記録を読み込めませんでした。';
   notice(error.message);
  }
 }finally{
  if(detailPending.get(tab)===gen)detailPending.delete(tab);
 }
}
function render(){
 const f=previewAction(snapshot.factory,pendingAction),product=p(),stock=f.stock.find(s=>s.product===product.id),now=snapshot.now;
 ui('cash').textContent=fmt(f.cash)+'円';document.querySelectorAll('[data-panel-cash]').forEach(el=>el.textContent='所持金 '+fmt(f.cash)+'円');const own=snapshot.rankings?.revenue.individual.find(r=>r.id===snapshot.identity.id);ui('revenue').textContent=fmt(snapshot.revenue??own?.revenue??0)+'円';
 $('#who').textContent=snapshot.identity.class_number+'組 · '+snapshot.identity.display_name+'工場';
 const e=snapshot.event;
 $('#open-market-buy').disabled=e.phase!=='open'||Boolean(pendingAction)||buying;
 const japanDay=t=>Math.floor((t+9*3600000)/86400000);
 const days=japanDay(e.departure_day)-japanDay(now);
 banner.textContent=(e.practice?'練習データ · ':'')+(e.phase==='before'?'開催まで '+Math.ceil((e.opens_at-now)/3600000)+'時間':e.phase==='closed'?'大会終了 · 最終成績':days>0?'修学旅行まで あと'+days+'日':'修学旅行期間！')+' · 集計 11/19 20:00';
 drawTapStock(stock,product,f.tap_power);ui('progress').textContent=(stock?.work||0)+' / '+product.work;
 ui('progress-bar').style.width=((stock?.work||0)/product.work*100)+'%';act('upgrade').closest('.upgrade-card').querySelector('p').textContent='現在 1タップ '+fmt(f.tap_power)+'作業';ui('power').textContent='1タップ '+fmt(f.tap_power)+'作業 · おひさまボーナスで5倍';ui('power').title='おひさまボーナス：タップごとに10％の確率で作業量が5倍になります。';
 act('tap').disabled=!stock;if(!stock)ui('gain').textContent='「強化」でこの坊主を解放しよう';act('upgrade').textContent='タップ強化 Lv.'+(f.tier+1)+' · '+fmt(f.upgrade_cost)+'円';act('upgrade').disabled=big(f.cash)<big(f.upgrade_cost);for(const item of f.equipment||[]){act(item.kind).textContent='Lv.'+item.level+' → 強化 '+fmt(item.cost)+'円';if(item.kind==='islandline'&&item.level)act(item.kind).textContent+=' · '+products.find(x=>x.id===f.auto_product)?.name+' '+fmt(item.rate)+'作業/秒';act(item.kind).disabled=big(f.cash)<big(item.cost)||snapshot.event.phase!=='open';}
 act('unlock').hidden=!!stock;act('unlock').textContent=product.name+'を解放 · '+fmt(product.unlock)+'円';act('unlock').disabled=big(f.cash)<BigInt(product.unlock);
 const count=(f.helpers||[]).length+(f.helper_until>now?1:0);const active=count>0;act('helper').disabled=!stock||big(f.cash)<150n;ui('helper-scene').hidden=!active;ui('helper-scene').dataset.teams=count;ui('helper').textContent='稼働中 '+count+'隊 · 追加OK · 各隊20秒／毎秒20作業';
 ui('cost').textContent='材料費 '+product.cost+'円／販売個';ui('market').textContent='定価 '+product.price+'円 · 材料費 '+product.cost+'円／販売個';ui('pending').textContent='次の精算まで '+Math.ceil((60000-now%60000)/1000)+'秒 · 販売中 '+f.shipments.length+'件';
 const shipment=pending(f);$('#market-stock').textContent=fmt(stock?.quantity||0)+'個';$('#market-listed').textContent=fmt(shipment?.quantity||0)+'個';$('#market-help').textContent=marketMode==='add'?'工場から店頭へ追加します。価格は販売中の全数に適用。':'販売中の個数はそのまま、価格だけ変更します。';ui('quantity').parentElement.hidden=marketMode==='price';act('all').parentElement.hidden=marketMode==='price';
 act('ship').disabled=marketMode==='price'?!shipment:!stock?.quantity;act('ship').textContent=marketMode==='price'?'販売価格を変更する':'この個数を追加出荷する';
 controls.hidden=!shipment;
 if(pendingAction){for(const kind of ['upgrade','helper','unlock','ship','sunpress','islandline'])act(kind).disabled=true;}
 $('#cancel-shipment').disabled=Boolean(pendingAction);
 if(shipment)ui('pending').textContent+=' · 店頭在庫 '+fmt(shipment.quantity)+'個 × '+fmt(shipment.price)+'円';
 if(e.phase!=='open'){for(const kind of ['tap','upgrade','helper','unlock','ship','sunpress','islandline'])act(kind).disabled=true;controls.hidden=true;ui('pending').textContent=e.phase==='closed'?'出荷受付は終了しました。':'開催前です。開始後に出荷できます。';}
 ui('results').replaceChildren();for(const r of (snapshot.own||[]).filter(r=>r.product_id===product.id).slice(0,1)){const li=document.createElement('li');li.textContent=fmt(r.sold_quantity)+'個販売 · 売上 '+fmt(r.revenue)+'円 · 出荷利益率 '+(r.margin===null?'—':(r.margin*100).toFixed(1)+'%');ui('results').append(li);}if(!ui('results').children.length)ui('results').textContent='この商品の販売結果はまだありません。';
 $('#teru-playtest').style.setProperty('--tp-doll',product.id==='sea'?'#c1edf0':product.id==='shisa'?'#ecc49b':'#fffdf0');
 const art={white:'/assets/teru-painted.png',sea:'/assets/sea-yokai.png',shisa:'/assets/shisa-doll.png'};$('.tp-sea .tp-doll img').src=art[product.id];window.TeruFX?.state(snapshot,product.id);if(page==='ranks'&&snapshot.rankings)renderRanks();if(page==='data'&&snapshot.timeline)renderChart();if(page==='collection')renderCollection();fitSheets();
}
function renderRanks(){if(!snapshot?.rankings)return;const metric=$('#rank-metric').value,scope=$('#rank-scope').value,rows=snapshot.rankings[metric][scope],unit=metric==='manufactured'?'個':'円';
 const people=snapshot.rankings.manufactured.individual;
 const counts=Array(8).fill(0);
 for(const person of people)counts[Number(person.class_number)-1]++;
 $('#rank-class-counts').replaceChildren(...counts.map((count,i)=>{
  const item=document.createElement('li');
  item.textContent=(i+1)+'組 '+fmt(count)+'人';
  return item;
 }));
 $('#rank-total-people').textContent=fmt(people.length)+'人';$('#rank-total-made').textContent=fmt(people.reduce((sum,r)=>sum+big(r.manufactured),0n))+'個';$('#rank-total-sales').textContent=fmt(snapshot.rankings.revenue.individual.reduce((sum,r)=>sum+big(r.revenue),0n))+'円';const perPage=window.innerHeight<650?3:5;
 $('#rank-definition').textContent={manufactured:'完成した坊主の累計。売っても減りません。',net_profit:'売上 − 材料費 − 強化・解放・応援隊代。初期支給金は除外。',revenue:'販売が確定した累計売上。'}[metric];$('#rank-list').replaceChildren();
 rankPage=Math.min(rankPage,Math.max(0,Math.ceil(rows.length/perPage)-1));$('#rank-page-label').textContent=(rankPage+1)+' / '+Math.max(1,Math.ceil(rows.length/perPage));$('#rank-prev').disabled=rankPage===0;$('#rank-next').disabled=(rankPage+1)*perPage>=rows.length;$('#my-rank').textContent='まだ記録がありません';for(const r of rows){const mine=scope==='individual'?r.id===snapshot.identity.id:r.class_number===snapshot.identity.class_number;const li=document.createElement('li');if(mine)li.className='mine';for(const [tag,text] of [['b',r.rank+'位'],['span',scope==='classes'?r.class_number+'組':r.display_name],['strong',fmt(r[metric])+unit]]){const el=document.createElement(tag);el.textContent=text;li.append(el);}if(rows.indexOf(r)>=rankPage*perPage&&rows.indexOf(r)<(rankPage+1)*perPage)$('#rank-list').append(li);if(mine)$('#my-rank').textContent=(scope==='classes'?'自分のクラス':'あなた')+'：'+r.rank+'位 · '+fmt(r[metric])+unit;}
}
let chartOffset=0;
function renderPie(metric){
 const names={white:'てるてる坊主',sea:'海坊主',shisa:'シーサー坊主',buy_market:'市場での購入',materials:'販売分の材料費',tax:'税金',upgrade:'タップ強化',unlock:'新商品の開発費',helper:'シーサー応援隊',sunpress:'おひさまプレス',islandline:'南風オートライン'},colors=['#259caa','#ebaa48','#e77980','#8f7db5','#69914d','#c37e50','#5f7ba1','#ac718d'];
 const rows=(snapshot.breakdown?.[metric]||[]).filter(r=>r.amount>0),total=rows.reduce((a,r)=>a+big(r.amount),0n);$('#chart').replaceChildren();$('#chart-summary').textContent='累計'+(metric==='income'?'収入':'支出')+'：'+fmt(total)+'円';ui('chart-state').textContent='自分の店・全商品・全期間（初期支給金は含めません）';
 $('#chart-prev').textContent='‹ 内訳';$('#chart-next').textContent='内訳 ›';piePage=Math.max(0,Math.min(piePage,Math.ceil(rows.length/4)-1));$('#chart-prev').disabled=piePage===0;$('#chart-next').disabled=(piePage+1)*4>=rows.length;$('#chart-latest').disabled=piePage===0;$('#chart-latest').textContent='内訳 '+(piePage+1)+' / '+Math.max(1,Math.ceil(rows.length/4));
 if(!total){$('#chart').textContent='まだ記録がありません。';return;}
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 340 220');svg.setAttribute('role','img');svg.setAttribute('aria-label',metric==='income'?'収入の内訳':'支出の内訳');let angle=-Math.PI/2;
 rows.forEach((r,i)=>{const next=angle+Number(big(r.amount)*1000000n/total)/1000000*Math.PI*2;const shape=document.createElementNS(ns,rows.length===1?'circle':'path');if(rows.length===1){shape.setAttribute('cx',92);shape.setAttribute('cy',100);shape.setAttribute('r',70);}else{shape.setAttribute('d',`M92 100 L${92+70*Math.cos(angle)} ${100+70*Math.sin(angle)} A70 70 0 ${next-angle>Math.PI?1:0} 1 ${92+70*Math.cos(next)} ${100+70*Math.sin(next)} Z`);}shape.setAttribute('fill',colors[i%colors.length]);svg.append(shape);if(i< piePage*4||i>=piePage*4+4){angle=next;return;}const legendIndex=i-piePage*4;const swatch=document.createElementNS(ns,'rect');swatch.setAttribute('x',166);swatch.setAttribute('y',25+legendIndex*44);swatch.setAttribute('width',7);swatch.setAttribute('height',10);swatch.setAttribute('rx',2);swatch.setAttribute('fill',colors[i%colors.length]);svg.append(swatch);const text=document.createElementNS(ns,'text');text.setAttribute('x',178);text.setAttribute('y',34+legendIndex*44);text.setAttribute('font-size',11);text.setAttribute('fill',colors[i%colors.length]);text.style.fill=colors[i%colors.length];text.textContent=names[r.key];svg.append(text);const value=document.createElementNS(ns,'text');value.setAttribute('x',175);value.setAttribute('y',51+legendIndex*44);value.setAttribute('font-size',11);value.textContent=fmt(r.amount)+'円 · '+(Number(big(r.amount)*1000000n/total)/1000000*100).toFixed(1)+'%';svg.append(value);angle=next;});$('#chart').append(svg);
}
function renderChart(){
 if(!snapshot?.timeline)return;
 const pie=['income','expense'].includes(ui('metric').value);if(ui('metric').value==='margin')$('#chart-scope').value='mine';
 for(const id of ['chart-scope','chart-interval'])$('#'+id).parentElement.hidden=pie;
 $('#chart-prev').parentElement.hidden=false;$('.tp-product-picker').hidden=pie;
 $('#chart-filter').hidden=pie;$('#chart-filter').textContent=p().name+' · '+($('#chart-scope').value==='mine'?'自分':'全体')+' · '+$('#chart-interval').selectedOptions[0].textContent+'　⚙';$('#chart-scope').querySelector('[data-value=all]').disabled=ui('metric').value==='margin';if(pie){renderPie(ui('metric').value);return;}

 if(ui('metric').value==='margin')$('#chart-scope').value='mine';
 $('#chart-latest').textContent='最新へ';$('#chart-prev').textContent='‹ 過去';$('#chart-next').textContent='次へ ›';
 const metric=ui('metric').value,own=metric==='margin'||$('#chart-scope').value==='mine',step=Number($('#chart-interval').value),product=p().id;
 const all=(snapshot.timeline||[]).filter(r=>r.product===product),market=all.filter(r=>r.player==='');
 const mine=new Map(all.filter(r=>r.player===snapshot.identity.id).map(r=>[r.round,r]));const groups=new Map();
 for(const m of market){const r=own?(mine.get(m.round)||{sold:0,revenue:0,inventory:0,cost:0}):m;const key=Math.floor(m.round/step)*step;let g=groups.get(key);if(!g){g={key,sold:0n,revenue:0n,cost:0n,inventory:0,last:-1};groups.set(key,g);}g.sold+=big(r.sold);g.revenue+=big(r.revenue);g.cost+=big(r.cost);if(m.round>g.last){g.last=m.round;g.inventory=big(r.inventory);g.inventoryExact=r.inventory;}}
 const records=[...groups.values()].sort((a,b)=>a.key-b.key);chartOffset=Math.min(chartOffset,Math.max(0,records.length-1));const end=records.length-chartOffset,shown=records.slice(Math.max(0,end-12),end);
 $('#chart-prev').disabled=end<=12;$('#chart-next').disabled=chartOffset===0;$('#chart-latest').disabled=chartOffset===0;
 const countMetric = metric === 'inventory' || metric === 'sold';
 const counts = countMetric ? shown.map(r => big(metric === 'inventory' ? r.inventoryExact : r.sold)) : [];
 const maxCount = counts.reduce((max, value) => value > max ? value : max, 1n);
 // Normalize exact integers first, before Number conversion, to avoid Infinity.
 const ratio=(numerator,denominator,precision=1000000n)=>denominator===0n?null:Number(numerator*precision/denominator)/Number(precision);
 const values=countMetric ? counts.map(value => ratio(value,maxCount)) : shown.map(r=>metric==='price'?(r.sold?ratio(r.revenue,r.sold):null):metric==='margin'?(r.revenue?ratio((r.revenue-r.cost)*100n,r.revenue):null):ratio(big(r[metric]),1n));const valid=values.filter(v=>v!==null&&Number.isFinite(v)),unit=metric==='price'?'円':metric==='margin'?'%':'個';
 $('#chart').replaceChildren();ui('chart-state').textContent=p().name+' · '+(own?'自分の店':'市場全体')+' · '+step+'分集計（端の区間は記録済み分）';
 if(!shown.length){$('#chart-summary').textContent='最初の記録を待っています' ;return;}
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 340 220');svg.setAttribute('role','img');svg.setAttribute('aria-label',ui('metric').selectedOptions[0].textContent+'の時系列グラフ');
 const min=Math.min(0,...valid),max=countMetric?1:Math.max(1,...valid),y=v=>175-(v-min)/(max-min)*145,x=i=>50+i*265/Math.max(1,shown.length-1);
 const add=(tag,attrs,text)=>{const el=document.createElementNS(ns,tag);for(const[k,v]of Object.entries(attrs))el.setAttribute(k,v);if(text!==undefined)el.textContent=text;svg.append(el);return el;};
 for(let i=0;i<3;i++){const v=min+(max-min)*i/2;add('line',{x1:45,x2:330,y1:y(v),y2:y(v),stroke:'#d2ddd1'});add('text',{x:40,y:y(v)+4,'text-anchor':'end','font-size':10},fmt(countMetric ? maxCount*BigInt(i)/2n : Number(v.toFixed(1))));}
 const pointLabel = (v,i) => fmt(countMetric ? counts[i] : Number(v.toFixed(1)));
 let previous=null;values.forEach((v,i)=>{if(v===null){previous=null;return;}if(previous!==null)add('line',{x1:x(previous),y1:y(values[previous]),x2:x(i),y2:y(v),stroke:'#167464','stroke-width':3});add('circle',{cx:x(i),cy:y(v),r:4,fill:'#167464'});const hit=add('circle',{cx:x(i),cy:y(v),r:12,fill:'transparent',tabindex:0,role:'button','aria-label':new Date(shown[i].key*60000).toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit'})+' '+pointLabel(v,i)+unit});const inspect=()=>{$('#chart-summary').textContent=new Date(shown[i].key*60000).toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit'})+' · '+pointLabel(v,i)+unit;};hit.onclick=inspect;hit.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();inspect();}};previous=i;});
 const time=r=>new Date(r.key*60000).toLocaleString('ja-JP',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});add('text',{x:45,y:203,'font-size':9},time(shown[0]));add('text',{x:330,y:203,'text-anchor':'end','font-size':9},time(shown.at(-1)));$('#chart').append(svg);
 $('#chart-summary').textContent='直近 ' +(values.at(-1)===null?'販売なし':pointLabel(values.at(-1),values.length-1)+unit)+(metric==='inventory'?'（区間末の残数）':'');
}
function previewAction(factory,request){
 if(!request)return factory;
 const {kind,product,price,quantity}=request;
 const stock=factory.stock.find(row=>row.product===product);
 const listing=factory.shipments.find(row=>row.product===product);
 if(kind==='add_listing'||kind==='set_price'){
  const added=kind==='add_listing'?big(quantity):0n;
  return {...factory,stock:factory.stock.map(row=>row===stock?{...row,quantity:big(row.quantity)-added}:row),
   shipments:[...factory.shipments.filter(row=>row!==listing),{...listing,product,price,quantity:big(listing?.quantity||0)+added}]};
 }
 if(kind==='upgrade'){
  const tier=Number(factory.tier)+1;
  const powers=[1n,5n,20n,100n,500n,2000n];
  const costs=[100n,600n,3000n,15000n,75000n];
  const powerAt=t=>powers[t]??powers.at(-1)*5n**BigInt(t-powers.length+1);
  return {...factory,tier,cash:big(factory.cash)-big(factory.upgrade_cost),
   tap_power:big(factory.tap_power)/powerAt(tier-1)*powerAt(tier),
   upgrade_cost:costs[tier]??costs.at(-1)*5n**BigInt(tier-costs.length+1)};
 }
 const item=factory.equipment?.find(row=>row.kind===kind);
 if(item){
  const updated={...item,level:Number(item.level)+1,cost:big(item.cost)*5n};
  if(kind==='islandline')updated.rate=big(item.rate)?big(item.rate)*5n:10000n;
  return {...factory,cash:big(factory.cash)-big(item.cost),equipment:factory.equipment.map(row=>row===item?updated:row),
   tap_power:kind==='sunpress'?big(factory.tap_power)*10n:factory.tap_power,
   auto_product:kind==='islandline'?product:factory.auto_product};
 }
 if(kind==='unlock'&&!stock){
  return {...factory,cash:big(factory.cash)-BigInt(products.find(row=>row.id===product).unlock),
   stock:[...factory.stock,{product,quantity:0,work:0}]};
 }
 return factory;
}
async function action(kind){
 if(!snapshot||pendingAction||buying||rareDialog.open)return;
 const chosen=p(),shipment=pending(),gen=generation;
 if(kind==='ship')kind=marketMode==='price'?'set_price':'add_listing';
 const request={key:crypto.randomUUID(),kind,product:chosen.id};
 if(kind==='add_listing'||kind==='set_price'){
  request.quantity=quantityText(ui('quantity'));
  request.price=Number(ui('price').value);
  if(!Number.isInteger(request.price)||request.price<1||request.price>99999)return notice('販売価格は1〜99,999円で指定してください。');
  const stock=snapshot.factory.stock.find(row=>row.product===chosen.id);
  if(kind==='add_listing'&&(!/^[0-9]+$/.test(request.quantity)||big(request.quantity)<1n||big(request.quantity)>big(stock?.quantity||0)))return notice('在庫の範囲内で出荷数を指定してください。');
 }
 if(kind==='cancel_shipment')request.target_id=shipment?.id;
 pendingAction=request;
 factoryRevision++;
 notice('反映を確認中…');
 render();
 let confirmed=false;
 try{
  const result=await api('action',request);
  if(gen!==generation||!snapshot)return;
  confirmed=true;
  const f=snapshot.factory;
  if(Object.hasOwn(result,'listing')){
   if(result.stock)f.stock=f.stock.map(stock=>stock.product===chosen.id?result.stock:stock);
   f.shipments=f.shipments.filter(row=>row.product!==chosen.id);
   if(result.listing)f.shipments.push(result.listing);
  }else{
   const projected=previewAction(f,request);
   if(projected!==f&&Object.hasOwn(result,'spent'))snapshot.factory={...projected,cash:big(f.cash)-big(result.spent)};
  }
  window.TeruFX?.success(kind);
  notice({add_listing:'店頭に追加しました。',set_price:'販売価格を変更しました。',cancel_shipment:'出荷を取り消し、在庫を戻しました。',sunpress:'タップ生産力が10倍になりました！',islandline:'自動ラインを強化しました！',helper:'シーサー応援隊が到着！',upgrade:'タップを強化しました。',unlock:'新しい坊主を解放しました。'}[kind]);
 }catch(error){
  if(gen===generation)notice(error.message);
 }finally{
  pendingAction=null;
  if(snapshot){
   render();
   if(!confirmed||kind==='helper')void refresh();
   else scheduleTapRefresh();
  }
 }
}
const bankDialog = $('#bank-dialog');
const bankAmount = $('#bank-amount');
const bankButtons = [...bankDialog.querySelectorAll('[data-bank]')];
let bankState, bankBusy = false, pendingBankAction;
const bankContractList = document.createElement('div');
bankContractList.id = 'bank-contract-list';
bankContractList.setAttribute('aria-label', '銀行の契約一覧');
bankContractList.style.cssText = 'display:grid;gap:10px;margin:14px 0';
$('#bank-terms').insertAdjacentElement('afterend',bankContractList);
bankButtons.find(b=>b.dataset.bank==='bank_withdraw').textContent='満期分を一括受取';
bankButtons.find(b=>b.dataset.bank==='bank_repay').textContent='借入を一括返済';

function bankDate(millis) {
 return new Date(Number(millis)).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'});
}
function renderBank() {
 if (!bankState) return;
 const {enabled, limit, lend_bps, borrow_bps, deposit, debt, matures} = bankState;
 const amount = parseWhole(bankAmount.value) ?? 0n;
 const payout = amount + amount * big(lend_bps) / 10000n;
 const repayment = amount + (amount * big(borrow_bps) + 9999n) / 10000n;
 const contracts = bankState.contracts || [];
 $('#bank-balance').textContent = '預け入れ満期受取額の合計 '+fmt(deposit)+'円 · 借入返済額の合計 '+fmt(debt)+'円 · 累計税額 '+fmt(bankState.tax)+'円';
 $('#bank-terms').textContent = (enabled ? '1契約あたりの上限 '+fmt(limit)+'円' : '新規契約は停止中')
  + ' · 預け入れ利率 '+(lend_bps/100)+'％（1時間）／借入利率 '+(borrow_bps/100)+'％（契約時に確定）'
  + (amount > 0n ? ' · 今回の満期受取 '+fmt(payout)+'円／借入返済 '+fmt(repayment)+'円' : '');
 const valid = enabled && amount>0n && amount<=big(limit);
 const canWithdraw=contracts.some(c=>c.kind==='lend' && Date.now()>=Number(c.matures));
 for(const button of bankButtons) {
  const kind=button.dataset.bank;
  const allowed=kind==='bank_withdraw' ? canWithdraw
   : kind==='bank_repay' ? big(debt)>0n
   : kind==='bank_lend' ? valid && (Date.now()+3600000 < Number(bankState.closes_at || Infinity))
   : kind==='bank_borrow' ? valid : false;
  button.disabled = bankBusy || !allowed;
 }
 bankContractList.replaceChildren();
 const heading=document.createElement('h4');
 heading.textContent='契約一覧（'+contracts.length+'件）';
 heading.style.cssText='margin:4px 0 0;font-size:16px';
 bankContractList.append(heading);
 if (!contracts.length) {
  const empty=document.createElement('p');empty.textContent='契約はありません。';
  bankContractList.append(empty);
 }
 contracts.forEach((c,index)=>{
  const card=document.createElement('div');
  card.style.cssText='padding:12px 14px;border:1px solid #cbd9c9;border-radius:12px;background:#fffdf5;display:grid;gap:7px';
  const label=document.createElement('strong');
  label.textContent=(c.kind==='lend'?'預け入れ':'借入')+' '+(index+1)+' · '+fmt(c.amount)+'円';
  const detail=document.createElement('span');
  detail.style.cssText='font-size:13px;line-height:1.65';
  detail.textContent=c.kind==='lend' ? '満期 '+bankDate(c.matures)+' · 預入元金 '+fmt(c.principal)+'円' : '元金 '+fmt(c.principal)+'円 · 返済額 '+fmt(c.amount)+'円';
  const action=document.createElement('button');
  action.className='tp-small';
  const withdraw=c.kind==='lend';
  action.textContent=withdraw?'この満期金を受け取る':'この借入を返済する';
  action.disabled=bankBusy || (withdraw && Date.now()<Number(c.matures));
  action.onclick=()=>performBankAction(withdraw?'bank_withdraw':'bank_repay',c.id);
  card.append(label,detail,action);
  bankContractList.append(card);
 });
}

async function loadBank() {
 bankState=await api('bank');
 renderBank();
}

$('#open-bank').onclick=async()=>{
 $('#bank-status').textContent='銀行の情報を取得中…';
 bankButtons.forEach(button=>button.disabled=true);
 bankDialog.showModal();
 try{await loadBank();$('#bank-status').textContent='';}
 catch(error){$('#bank-status').textContent=error.message;}
};
bankAmount.addEventListener('input',renderBank);

async function performBankAction(kind,quantity) {
 if(bankBusy)return;
 if(!pendingBankAction || pendingBankAction.kind!==kind || pendingBankAction.quantity!==quantity) {
  pendingBankAction={key:crypto.randomUUID(),kind,quantity};
 }
 bankBusy=true;renderBank();
 try{
  await api('action',pendingBankAction);
  pendingBankAction=null;
  await Promise.all([loadBank(),refresh()]);
  $('#bank-status').textContent='取引が完了しました。';
 }catch(error){$('#bank-status').textContent=error.message;}
 finally{bankBusy=false;renderBank();}
}
for(const button of bankButtons)button.onclick=()=>{
 const kind=button.dataset.bank;
 const quantity=['bank_lend','bank_borrow'].includes(kind)?bankAmount.value:null;
 void performBankAction(kind,quantity);
};

const buyDialog=$('#market-buy-dialog');
const buyForm=$('#market-buy-form');
const buyQuantity=$('#market-buy-quantity');
const quantityFields = [ui('quantity'), buyQuantity];
const exactQuantities = new WeakMap();

function quantityText(field) {
 const saved = exactQuantities.get(field);
 return saved && field.value === saved.label ? saved.exact : field.value;
}

function displayQuantity(field, quantity) {
 const exact = String(quantity);
 const label = /^[0-9]+$/.test(exact) && isLarge(big(exact)) ? fmt(exact) : exact;
 exactQuantities.set(field, {exact, label});
 field.value = label;
}

for (const field of quantityFields) {
 field.removeAttribute('pattern');
 field.addEventListener('focus', () => {
  field.value = quantityText(field);
  exactQuantities.delete(field);
 });
 field.addEventListener('blur', () => displayQuantity(field, quantityText(field)));
}
const buySubmit=buyForm.querySelector('button[type="submit"]');
let buyProduct,buyQuote,buying=false;
function renderBuyQuote(){
 const exact = quantityText(buyQuantity);
 const quantity=/^[0-9]+$/.test(exact)?big(exact):0n;
 const available=big(buyQuote?.quantity||0);
 const total=quantity*big(buyQuote?.price||0);
 $('#market-buy-quote').textContent=buyQuote
  ? buyProduct.name+' · '+(available>0n?'平均 '+fmt(buyQuote.price)+'円／個 · 購入可能 '+fmt(available)+'個':'購入できる出品はありません。')
  : '平均販売値を取得中…';
 $('#market-buy-total').textContent=available>0n?'合計 '+fmt(total)+'円':'';
 buySubmit.disabled=buying||!snapshot||quantity<1n||quantity>available||total>big(snapshot.factory.cash);
}
async function loadBuyQuote(){
 buyQuote=null;
 renderBuyQuote();
 try{
  buyQuote=(await api('market-quotes')).quotes[buyProduct.id];
  renderBuyQuote();
 }catch(error){$('#market-buy-status').textContent=error.message;}
}
$('#open-market-buy').onclick=()=>{
 if(!snapshot||pendingAction)return;
 buyProduct=p();
 if(!snapshot.factory.stock.some(row=>row.product===buyProduct.id)){
  notice('先に強化画面でこの坊主を解放してください。');
  return;
 }
 $('#market-buy-status').textContent='';
 displayQuantity(buyQuantity, 1);
 buyDialog.showModal();
 void loadBuyQuote();
};
$('#close-market-buy').onclick=()=>{if(!buying)buyDialog.close();};
buyDialog.addEventListener('cancel',event=>{if(buying)event.preventDefault();});
buyQuantity.oninput=renderBuyQuote;
buyForm.onsubmit=async event=>{
 event.preventDefault();
 if(buySubmit.disabled||pendingAction)return;
 const gen=generation;
 buying=true;
 factoryRevision++;
 renderBuyQuote();
 $('#market-buy-status').textContent='購入を確認中…';
 try{
  const result=await api('action',{key:crypto.randomUUID(),kind:'buy_market',product:buyProduct.id,quantity:quantityText(buyQuantity),price:buyQuote.price});
  if(gen!==generation||!snapshot)return;
  factoryRevision++;
  const factory=snapshot.factory;
  factory.cash=result.cash;
  factory.stock=factory.stock.map(row=>row.product===result.stock.product?result.stock:row);
  render();
  buyDialog.close();
  notice(fmt(result.bought)+'個を購入しました。');
 }catch(error){
  $('#market-buy-status').textContent=error.message;
  if(gen===generation&&snapshot)await loadBuyQuote();
 }finally{
  buying=false;
  if(snapshot){render();renderBuyQuote();scheduleTapRefresh();}
 }
};
const tapQueue=[];
function pendingTaps(product){
 return tapQueue.filter(batch=>batch.product===product&&batch.generation===generation)
  .reduce((sum,batch)=>sum+BigInt(batch.count),0n);
}
function drawTapStock(stock,product,power){
 const extra=stock?(big(stock.work||0)+pendingTaps(product.id)*big(power))/BigInt(product.work):0n;
 ui('stock').textContent=fmt(big(stock?.quantity||0)+extra);
}
let tapFlushTimer, sendingTaps=false;
function scheduleTapBatch(delay=220){
 if(sendingTaps||tapFlushTimer!==undefined||!tapQueue.length)return;
 tapFlushTimer=setTimeout(()=>{tapFlushTimer=undefined;void sendTapBatch();},delay);
}
async function sendTapBatch(){
 if(!snapshot){tapQueue.length=0;return;}
 while(tapQueue.length&&tapQueue[0].generation!==generation)tapQueue.shift();
 if(!tapQueue.length)return;
 const batch=tapQueue[0];
 batch.key??=crypto.randomUUID();
 sendingTaps=true;
 try{
  const response=await api('action',{kind:'tap_batch',product:batch.product,quantity:batch.count,key:batch.key});
  if(batch.generation!==generation)return;
  tapQueue.shift();
  if(response.stock&&snapshot){
   factoryRevision++;
   const stocks=snapshot.factory.stock;
   const index=stocks.findIndex(stock=>stock.product===batch.product);
   if(index>=0)stocks[index]=response.stock;
   render();
  }
  notice('');
  for(const result of response.taps){
   if(page==='factory'&&p().id===batch.product){
    if(result.critical)window.TeruFX?.produced(result.produced,true);
    if(result.critical)effect('おひさまボーナス',true);
    ui('gain').textContent=big(result.produced)>0n?'＋'+fmt(result.produced)+'個':'仕上げ中';
   }
  }
  scheduleTapRefresh();
 }catch(e){
  if(batch.generation!==generation)return;
  notice(e.message);
  ui('gain').textContent=e.message;
  if(++batch.attempts>=3||!snapshot){tapQueue.shift();if(snapshot)render();}
 }finally{
  sendingTaps=false;
  scheduleTapBatch(batch.attempts?500:220);
 }
}
act('tap').onclick=()=>{
 if(!snapshot||buying||rareDialog.open)return;
 const product=p().id;
 if(!snapshot.factory.stock.some(row=>row.product===product))return;
 window.TeruFX?.press();
 const stock=snapshot.factory.stock.find(s=>s.product===product);
 const queued=pendingTaps(product);
 const power=big(snapshot.factory.tap_power), required=BigInt(p().work);
 const before=big(stock?.work||0)+queued*power;
 const units=(before+power)/required-before/required;
 if(units>0n)effect('＋'+fmt(units));
 else effect('作業＋'+fmt(power));
 const tail=tapQueue.at(-1);
 if(tail&&!tail.key&&tail.product===product&&tail.generation===generation&&tail.count<20)tail.count++;
 else tapQueue.push({product,count:1,generation,attempts:0});
 drawTapStock(stock,p(),power);
 scheduleTapBatch();
};
for(const kind of ['upgrade','helper','unlock','ship','sunpress','islandline'])act(kind).onclick=()=>action(kind);
for(const mode of ['add','price'])$('#mode-'+mode).onclick=()=>{marketMode=mode;for(const m of ['add','price'])$('#mode-'+m).setAttribute('aria-pressed',String(m===mode));if(pending())ui('price').value=pending().price;render();};for(const n of [10,100])$('#quantity-'+n).onclick=()=>{const limit=big(snapshot.factory.stock.find(s=>s.product===p().id)?.quantity||0);const exact=quantityText(ui('quantity'));const value=/^[0-9]+$/.test(exact)?big(exact):0n;displayQuantity(ui('quantity'),value+BigInt(n)>limit?limit:value+BigInt(n));};
$('#load-shipment').onclick=()=>{const s=pending();if(s){displayQuantity(ui('quantity'),s.quantity);ui('price').value=s.price;}};$('#cancel-shipment').onclick=()=>action('cancel_shipment');
act('all').onclick=()=>{displayQuantity(ui('quantity'),snapshot.factory.stock.find(s=>s.product===p().id)?.quantity||0);};
ui('product').onchange=()=>{ui('price').value=pending()?.price??prices[Number(ui('product').value)];ui('gain').textContent='タップして、晴れをつくろう';render();};ui('price').value=8;ui('price').oninput=()=>prices[Number(ui('product').value)]=Number(ui('price').value);
for(const id of ['rank-metric','rank-scope'])$('#'+id).onchange=()=>{rankPage=0;renderRanks();fitSheets();};ui('metric').onchange=()=>{piePage=0;chartOffset=0;renderChart();fitSheets();};
$('.tp-sea').append(ui('helper-scene'));
const nameDialog=$('#name-dialog'),nameForm=$('#name-form');
$('#open-name').onclick=()=>{
 if(!snapshot)return;
 nameForm.elements.name.value=snapshot.identity.display_name;
 $('#name-status').textContent='';
 nameDialog.showModal();
};
$('#close-name').onclick=()=>nameDialog.close();
nameForm.onsubmit=async event=>{
 event.preventDefault();
 const button=event.submitter,gen=generation;
 button.disabled=true;
 $('#name-status').textContent='保存中…';
 try{
  const result=await api('name',{name:nameForm.elements.name.value});
  if(gen!==generation||!snapshot)return;
  factoryRevision++;
  snapshot.identity.display_name=result.display_name;
  for(const ranking of Object.values(snapshot.rankings||{})){
   const row=ranking.individual.find(entry=>entry.id===snapshot.identity.id);
   if(row)row.display_name=result.display_name;
  }
  render();
  nameDialog.close();
  notice('表示名を変更しました。');
 }catch(error){
  $('#name-status').textContent=error.message;
 }finally{
  button.disabled=false;
 }
};
const authForm=$('#auth-form');
authForm.onsubmit=async event=>{
 event.preventDefault();
 const buttons=[...authForm.querySelectorAll('button[type="submit"], button[name="mode"]')];
 if (buttons.some(button=>button.disabled)) return;
 const data=Object.fromEntries(new FormData(authForm));
 const status=$('#auth-error');
 buttons.forEach(button=>button.disabled=true);
 status.textContent='確認中…';
 try {
  await api(event.submitter?.value || 'login',data);
  generation++;
  detailUpdated.clear();
  status.textContent='ゲームを読み込み中…';
  await refresh();
 } catch(error) { status.textContent=error.message; }
 finally { buttons.forEach(button=>button.disabled=false); }
};
$('#logout').onclick=async()=>{try{await api('logout',{});generation++;snapshot=null;$('#game').hidden=true;$('#auth').hidden=false;notice('');}catch(e){notice(e.message);}};
const rareArt={gold:'/assets/teramoto-bozu.png',rainbow:'/assets/mikka-bozu.png',sand:'/assets/koyama-bozu.png',pearl:'/assets/yamada-bozu.png'};
const rareOdds={rainbow:'100万',sand:'100億',pearl:'100京',gold:'100穣'};
const rareDialog=document.createElement('dialog');rareDialog.className='rare-discovery';rareDialog.setAttribute('aria-label','レア坊主を初発見');document.body.append(rareDialog);let activeRare=null;
rareDialog.addEventListener('cancel',e=>e.preventDefault());
function showRareDiscovery(){if(rareDialog.open||activeRare)return;const index=snapshot.factory.collection.findIndex(r=>r.unseen);if(index<0)return;const r=snapshot.factory.collection[index];activeRare=r.id;rareDialog.replaceChildren();
 const beam=document.createElement('div');beam.className='rare-beam';beam.setAttribute('aria-hidden','true');
 const body=document.createElement('div');body.className='rare-discovery-body';
 for(const [tag,text] of [['small','FIRST DISCOVERY'],['div','✦'],['h2',r.name],['p','初めての出会い！'],['h3','この種類の発見者 · 全体 '+fmt(r.discovery_rank)+'番目'],['p','完成1個あたり '+rareOdds[r.id]+'分の1'],['small','キャラクター画像は準備中']]){const el=document.createElement(tag);if(rareArt[r.id]&&text==='キャラクター画像は準備中')continue;if(rareArt[r.id]&&tag==='div'){const img=document.createElement('img');img.src=rareArt[r.id];img.alt=r.name;img.className='rare-character-art';body.append(img);}else{el.textContent=text;body.append(el);}}
 const close=document.createElement('button');close.textContent='図鑑に記録して戻る';close.onclick=async()=>{close.disabled=true;try{await api('action',{key:crypto.randomUUID(),kind:'ack_rare',quantity:index});r.unseen=false;rareDialog.close();activeRare=null;await refresh();}catch(e){close.textContent='再試行：'+e.message;close.disabled=false;}};body.append(close);rareDialog.append(beam,body);rareDialog.showModal();close.focus();
}
for(const id of ['chart-scope','chart-interval'])$('#'+id).onchange=()=>{chartOffset=0;renderChart();fitSheets();};$('#chart-prev').onclick=()=>{if(['income','expense'].includes(ui('metric').value))piePage--;else chartOffset+=12;renderChart();};$('#chart-next').onclick=()=>{if(['income','expense'].includes(ui('metric').value))piePage++;else chartOffset=Math.max(0,chartOffset-12);renderChart();};$('#chart-latest').onclick=()=>{piePage=0;chartOffset=0;renderChart();};
let rarePage=0;
function renderCollection(){
 const rows=snapshot.factory.collection||[],card=$('#rare-card');card.replaceChildren();card.className='collection-shelf';
 rows.forEach((r,i)=>{const button=document.createElement('button');button.type='button';button.className='shelf-doll '+(r.quantity?'found':'unknown');button.setAttribute('aria-label',r.quantity?r.name+' '+fmt(r.quantity)+'個':'未発見の坊主 '+(i+1));button.setAttribute('aria-pressed',String(i===rarePage));
 const doll=document.createElement('span');doll.className='shelf-figure';doll.setAttribute('aria-hidden','true');if(rareArt[r.id]){doll.classList.add('illustrated');const img=document.createElement('img');img.src=rareArt[r.id];img.alt='';doll.append(img);}else{const head=document.createElement('i');const cloth=document.createElement('b');doll.append(head,cloth);}
 const name=document.createElement('span');name.className='shelf-name';name.textContent=r.quantity?r.name:'まだ見ぬ仲間';const count=document.createElement('small');count.textContent=r.quantity?fmt(r.quantity)+' 個':'？';button.append(doll,name,count);button.onclick=()=>{rarePage=i;renderCollection();fitSheets();};card.append(button);});
 const r=rows[rarePage];if(!r)return;$('#rare-page').textContent=r.quantity?r.name+' · 初発見 '+new Date(r.discovered).toLocaleDateString('ja-JP'):'棚に並ぶ日を、お楽しみに';$('#rare-prev').hidden=true;$('#rare-next').hidden=true;
 let detail=$('#collection-detail');if(!detail){detail=document.createElement('p');detail.id='collection-detail';$('#rare-page').parentElement.after(detail);}detail.textContent='出現確率 '+rareOdds[r.id]+'分の1'+(r.quantity?' · 全体 '+fmt(r.discovery_rank)+'番目の発見':'')+(rareArt[r.id]?'':'　※姿は仮の飾りです');
}

$('#rare-prev').onclick=()=>{rarePage--;renderCollection();fitSheets();};$('#rare-next').onclick=()=>{rarePage++;renderCollection();fitSheets();};
const picker=$('.tp-product-picker');
for(const panel of document.querySelectorAll('.sheet')){const content=document.createElement('div');content.className='sheet-content';content.append(...panel.childNodes);panel.append(content);const heading=content.querySelector('h3');if(heading){const title=document.createElement('div');title.className='island-page-title';title.append(heading);panel.prepend(title);}}
const marketDetails=document.createElement('dialog');marketDetails.className='island-dialog market-dialog';marketDetails.setAttribute('aria-label','販売の状況と直近の実績');const marketTitle=document.createElement('h3');marketTitle.textContent='港の販売記録';marketDetails.append(marketTitle,ui('pending'),$('.tp-results-title'),ui('results'),$('#cancel-shipment'));const marketClose=document.createElement('button');marketClose.type='button';marketClose.className='dialog-done';marketClose.textContent='市場へ戻る';marketClose.onclick=()=>marketDetails.close();marketDetails.append(marketClose);document.body.append(marketDetails);const marketOpen=document.createElement('button');marketOpen.type='button';marketOpen.className='market-records';marketOpen.textContent='販売記録・在庫の回収を見る';marketOpen.onclick=()=>marketDetails.showModal();$('#tp-page-market .sheet-content').append(marketOpen);
const chartContent=$('#tp-page-data .sheet-content');
const chartOptions=document.createElement('dialog');chartOptions.className='chart-options island-dialog';chartOptions.setAttribute('aria-label','グラフの表示設定');
const settingsTitle=document.createElement('h3');settingsTitle.textContent='どの記録を見る？';chartOptions.append(settingsTitle);
for(const field of [...chartContent.querySelectorAll('.choice-field')])if(!field.contains(ui('metric')))chartOptions.append(field);
const filterButton=document.createElement('button');filterButton.id='chart-filter';filterButton.type='button';filterButton.setAttribute('aria-haspopup','dialog');filterButton.onclick=()=>chartOptions.showModal();
ui('metric').parentElement.after(filterButton);const done=document.createElement('button');done.type='button';done.className='dialog-done';done.textContent='この表示で見る';done.onclick=()=>chartOptions.close();chartOptions.append(done);document.body.append(chartOptions);
chartContent.append(ui('chart-state'));ui('chart-state').classList.add('chart-caption');
const shortMetrics={sold:'販売個数',inventory:'流通量',price:'平均価格',margin:'利益率',income:'収入内訳',expense:'支出内訳'};
for(const button of ui('metric').children)button.textContent=shortMetrics[button.dataset.value];
$('#chart').before($('#chart-summary'));
// Keep purchases large: two equipment choices per page.
const upgrades=$('#tp-page-upgrades .sheet-content'),upgradeTabs=document.createElement('div');upgradeTabs.className='upgrade-pages';upgradeTabs.setAttribute('role','tablist');upgradeTabs.setAttribute('aria-label','強化の種類');
const upgradeCards=[...upgrades.querySelectorAll('.upgrade-card')];
['タップ・応援','大型設備'].forEach((label,index)=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.setAttribute('role','tab');b.setAttribute('aria-selected',String(index===0));b.onclick=()=>{upgradeCards.forEach((card,i)=>card.hidden=Math.floor(i/2)!==index);[...upgradeTabs.children].forEach((tab,i)=>tab.setAttribute('aria-selected',String(i===index)));fitSheets();};upgradeTabs.append(b);});
upgrades.querySelector('[data-panel-cash]').after(upgradeTabs);upgradeCards.forEach((card,i)=>card.hidden=i>=2);
const rankOverview=document.createElement('div');rankOverview.className='rank-overview';rankOverview.setAttribute('aria-label','全参加者の累計');rankOverview.innerHTML='<div><span>参加人数</span><strong id="rank-total-people"></strong></div><div><span>総生産量</span><strong id="rank-total-made"></strong></div><div><span>全体の売上</span><strong id="rank-total-sales"></strong></div>';$('#tp-page-ranks .sheet-content').prepend(rankOverview);
const classCounts=document.createElement('ul');classCounts.id='rank-class-counts';classCounts.setAttribute('aria-label','クラス別の参加人数');rankOverview.after(classCounts);
const pager=document.createElement('div');pager.className='rank-pager';pager.innerHTML='<button id="rank-prev" type="button">‹ 前へ</button><span id="rank-page-label"></span><button id="rank-next" type="button">次へ ›</button>';$('#rank-list').after(pager);
$('#rank-prev').onclick=()=>{rankPage--;renderRanks();fitSheets();};$('#rank-next').onclick=()=>{rankPage++;renderRanks();fitSheets();};
function placePicker(){if(page==='factory')$('#game').append(picker);else if(page==='data')$('.chart-options').insertBefore(picker,done);else if(!['ranks','collection','rules','announcements'].includes(page))$('#tp-page-'+page+' .sheet-content').prepend(picker);}
function fitSheets(){requestAnimationFrame(()=>{for(const panel of document.querySelectorAll('.sheet:not([hidden])')){const content=panel.querySelector('.sheet-content');content.style.zoom=1;if(panel.id==='tp-page-data')continue;const available=panel.clientHeight-panel.querySelector('.island-page-title').offsetHeight-12;const needed=content.scrollHeight;content.style.zoom=Math.min(1,available/Math.max(1,needed));}});}
document.fonts.ready.then(fitSheets);
new ResizeObserver(fitSheets).observe($('#teru-playtest'));
const announcementDialog=$('#announcement-dialog');
let announcement={text:'',key:'',history:[]};
const announcementStorageKey='hare-machi:read-announcement';
let readAnnouncement='';
try{readAnnouncement=localStorage.getItem(announcementStorageKey)||'';}catch{}
function renderAnnouncements(){
 if(announcement.text&&((snapshot&&page==='announcements')||announcementDialog.open)){
  readAnnouncement=announcement.key;
  try{localStorage.setItem(announcementStorageKey,readAnnouncement);}catch{}
 }
 const unread=Boolean(announcement.text&&announcement.key!==readAnnouncement);
 for(const body of document.querySelectorAll('[data-announcement]')){
  const entries = announcement.history;
  if (!entries.length) {
   body.textContent=announcement.text||'現在のお知らせはありません。';
  } else {
   body.replaceChildren(...entries.map(({body:text})=>{
    const item=document.createElement('p');
    item.textContent=text;
    return item;
   }));
  }
 }
 for(const button of document.querySelectorAll('.announcement-tab')){
  button.querySelector('.announcement-dot').hidden=!unread;
  button.setAttribute('aria-label',unread?'お知らせ（未読あり）':'お知らせ');
 }
}
$('#auth-announcements').onclick=()=>{
 announcementDialog.showModal();
 renderAnnouncements();
 void refreshSite();
};
async function refreshSite(){
 try{
  const settings=await api('site');
  announcement={text:settings.announcement,key:String(settings.announcement_revision??settings.announcement),history:settings.announcements||[]};
  const customRules=$('#rulebook-custom');
  customRules.textContent=settings.rulebook||'';
  customRules.hidden=!settings.rulebook;
  $('#rulebook-default').hidden=Boolean(settings.rulebook);
  renderAnnouncements();
  $('#maintenance-note').hidden=!settings.maintenance;
  $('#auth-form').hidden=settings.maintenance;
  if(settings.maintenance&&snapshot){
   generation++;
   snapshot=null;
   pendingAction=null;
   tapQueue.length=0;
   $('#game').hidden=true;
   $('#auth').hidden=false;
  }
 }catch{}
}
function scheduleBackgroundRefresh(){
 setTimeout(()=>{
  if(!document.hidden)void refreshSite();
  if(snapshot&&!document.hidden){
   refresh();
   refreshDetails(page);
  }
  scheduleBackgroundRefresh();
 },25000+Math.random()*10000);
}
scheduleBackgroundRefresh();
void refreshSite();
document.addEventListener('visibilitychange',()=>{
 if(snapshot&&!document.hidden){refresh();refreshDetails(page);}
});
document.addEventListener("visibilitychange",()=>{if(snapshot&&!document.hidden)refresh();});
refresh();
})();

setInterval(()=>{
 const pending=document.querySelector('[data-ui="pending"]');
 if(!pending||pending.closest('[hidden]'))return;
 pending.textContent=pending.textContent.replace(/次の精算まで \d+秒/,
  '次の精算まで '+Math.ceil((60000-Date.now()%60000)/1000)+'秒');
},1000);
