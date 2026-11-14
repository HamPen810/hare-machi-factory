/* Hare-Machi Command Deck: UI-only navigation, pagination, inbox reader, charts. */
(()=>{
'use strict';
const q=s=>document.querySelector(s),qa=s=>Array.from(document.querySelectorAll(s));
let snapshot=null,chartPage=0,activeGroup='players';
const tablePage=new WeakMap(),tablePager=new WeakMap();
const letters={posts:[],messages:[]},letterPage={posts:0,messages:0},letterSelected={posts:0,messages:0},bodyPage={posts:0,messages:0};
const mobile=()=>matchMedia('(max-width:740px)').matches;
const E=(tag,cls,text)=>{let n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
const B=(text,fn)=>{const n=E('button','',text);n.type='button';n.addEventListener('click',fn);return n;};
const stamp=v=>Number(v)>0?new Date(Number(v)).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}):'日時不明';
function magnitude(input){
 let str=String(input??'0').trim(),sign=str.startsWith('-')?-1:1;
 if(sign<0)str=str.slice(1);
 const m=str.match(/^(\d+(?:\.\d*)?|\.\d+)(?:[eE]([+-]?\d+))?$/);
 if(!m)return 0;
 const pair=m[1].split('.'),whole=pair[0].replace(/^0+/,'');
 let num=0;
 if(whole){const s=whole.slice(0,12);num=whole.length-s.length+Math.log10(Number(s));}
 else{const frac=pair[1]||'',i=frac.search(/[1-9]/);if(i<0)return 0;const s=frac.slice(i,i+12);num=Math.log10(Number(s))-s.length-i;}
 const ex=Number(m[2]||0);
 return Number.isFinite(num+ex)?sign*(num+ex):0;
}
function navigate(name){q('[data-panel="'+name+'"]')?.click();}
function overview(){
 const root=q('#overview-brief');if(!root)return;
 root.replaceChildren();
 const hero=E('div','console-hero'),left=E('div');
 left.append(E('small','','HARE-MACHI OPERATIONS CENTER'),
             E('strong','','ゲームの今を、ひと目で。'),
             E('small','',snapshot?'更新 '+stamp(snapshot.now)+' ／ 手動更新式':'読み込み中'));
 hero.append(left,E('span','hero-icon','☀'));root.append(hero);
 if(!snapshot)return;
 const list=E('div','console-kpi-tiles'),players=snapshot.players||[],s=snapshot.summary||{};
 const metrics=[
  ['参加者',String(s.players??players.length)+'人','登録済み'],
  ['強化済み',String(players.filter(p=>Number(p.tier)>0).length)+'人','タップ強化Lv.1以上'],
  ['市場出荷',String(s.pending_shipments||0)+'件','現在の出荷'],
  ['精算済み',String(s.settled_rounds||0)+'回','市場精算回'],
  ['最大製造規模',Math.max(0,...players.map(p=>magnitude(p.manufactured))).toFixed(0)+'桁','製造累計の最高値'],
  ['最大売上規模',Math.max(0,...players.map(p=>magnitude(p.revenue))).toFixed(0)+'桁','売上累計の最高値']
 ];
 metrics.forEach(a=>{const c=E('article');c.append(E('span','metric-label',a[0]),E('strong','',a[1]),E('span','metric-help',a[2]));list.append(c);});
 root.append(list);
}
function activate(name){
 q('#admin-mobile-nav')&&(q('#admin-mobile-nav').value=name);
 if(name==='overview')overview();
 if(name==='analysis')setTimeout(chartPaging,0);
 if(name==='notices'||name==='messages')drawInbox(name==='notices'?'posts':'messages');
}
function nav(){
 const sel=q('#admin-mobile-nav');
 if(sel)sel.onchange=()=>navigate(sel.value);
 q('[role=tablist]')?.addEventListener('click',ev=>{
  const b=ev.target.closest('[data-panel]');
  if(b)queueMicrotask(()=>activate(b.dataset.panel));
 });
 qa('[data-goto]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.goto)));
 const dash=q('#dashboard');
 const state=()=>document.body.classList.toggle('console-active',!dash.hidden);
 new MutationObserver(state).observe(dash,{attributes:true,attributeFilter:['hidden']});state();
}
function tableRows(root){return qaTable(root,'table tbody tr');}
function qaTable(root,selector){return Array.from(root.querySelectorAll(selector));}
function pageTable(root,reset=false){
 if(!root||root.id.startsWith('bulletin-admin-'))return;
 const rows=tableRows(root),old=tablePager.get(root);
 if(!rows.length){if(old)old.hidden=true;return;}
 const per=mobile()?Math.max(2,Math.min(4,Math.floor((innerHeight-320)/46))):Math.max(3,Math.min(9,Math.floor((innerHeight-300)/38)));
 const total=Math.max(1,Math.ceil(rows.length/per));
 let index=reset?0:(tablePage.get(root)||0);index=Math.min(total-1,index);
 tablePage.set(root,index);
 rows.forEach((row,i)=>{
  row.hidden=i<index*per||i>=(index+1)*per;
  if(!row.dataset.detailHook){
   row.dataset.detailHook='1';row.tabIndex=0;
   row.addEventListener('click',ev=>{if(!ev.target.closest('button,a,input,select'))recordDetails(row);});
   row.addEventListener('keydown',ev=>{if(ev.key==='Enter'&&ev.target===row){ev.preventDefault();recordDetails(row);}});
  }
 });
 let pager=old;
 if(!pager){pager=E('div','console-pager');root.after(pager);tablePager.set(root,pager);}
 pager.hidden=total<=1;
 if(total>1){
  pager.replaceChildren(B('← 前',()=>{tablePage.set(root,index-1);pageTable(root);}),E('small','',String(index+1)+' / '+total+' ページ · '+rows.length+'件'),B('次 →',()=>{tablePage.set(root,index+1);pageTable(root);}));
  pager.firstChild.disabled=index<=0;pager.lastChild.disabled=index>=total-1;
 }
}
function recordDetails(row){
 const modal=q('#console-record-dialog'),content=q('#console-record-fields');
 if(!modal||!content)return;
 const h=Array.from(row.closest('table').querySelectorAll('thead th')).map(x=>x.textContent.trim());
 content.replaceChildren();
 Array.from(row.children).forEach((c,i)=>content.append(E('span','console-field-label',h[i]||'項目'+(i+1)),E('span','console-field-value',c.textContent.trim()||'—')));
 modal.hidden=false;q('#console-record-close').focus();
}
function tables(){
 const obs=new MutationObserver(changes=>{
  const targets=new Set();
  changes.forEach(x=>{if(x.target.classList?.contains('table-wrap'))targets.add(x.target);});
  targets.forEach(x=>pageTable(x,true));
 });
 qa('.table-wrap').forEach(root=>{
  if(root.id.startsWith('bulletin-admin-'))return;
  obs.observe(root,{childList:true});pageTable(root);
 });
 window.addEventListener('resize',()=>{qa('.table-wrap').forEach(root=>pageTable(root));chartPaging();});
 const modal=q('#console-record-dialog');
 q('#console-record-close').onclick=()=>modal.hidden=true;
 modal.addEventListener('click',ev=>{if(ev.target===modal)modal.hidden=true;});
 document.addEventListener('keydown',ev=>{if(ev.key==='Escape'){modal.hidden=true;qa('.console-inbox').forEach(x=>x.classList.remove('console-reading'));}});
}
function views(panel,parts,labels){
 if(!panel||!parts.length)return;
 const n=E('div','console-switcher');
 parts.forEach((part,i)=>{
  part.classList.add('console-page');part.dataset.index=String(i);part.classList.toggle('console-visible',i===0);
  const b=B(labels[i]||'操作'+(i+1),()=>{
   panel.querySelectorAll(':scope>.console-page').forEach(v=>v.classList.toggle('console-visible',Number(v.dataset.index)===i));
   n.querySelectorAll('button').forEach((x,j)=>x.setAttribute('aria-pressed',String(j===i)));
  });
  b.setAttribute('aria-pressed',String(i===0));n.append(b);
 });
 n.append(E('span','console-switcher-status','画面切替'));
 panel.prepend(n);parts.forEach(p=>panel.append(p));
}
function paneDiv(){return E('div','console-page');}
function panels(){
 const bank=q('#panel-bank');
 if(bank){
  const chunks=Array.from(bank.children).filter(x=>x.matches('details'));
  if(chunks.length>=3){
   const p=chunks.slice(0,3).map(()=>paneDiv());
   chunks.forEach((x,i)=>{x.open=true;p[Math.min(i,2)].append(x);});
   Array.from(bank.children).forEach(x=>{if(!x.matches('h2')&&!x.classList.contains('console-page'))p[0].prepend(x);});
   views(bank,p,['銀行・税率','資産課税','市場買い取り']);
   bankSteps();
  }
 }
 const advanced=q('#panel-advanced');
 if(advanced){
  const items=Array.from(advanced.children).filter(x=>x.matches('details,form'));
  if(items.length){
   const p=items.map(()=>paneDiv());
   items.forEach((x,i)=>{if(x.matches('details'))x.open=true;p[i].append(x);});
   views(advanced,p,['ルールブック','登録枠','登録管理']);
  }
 }
 const funds=q('#panel-funds');
 if(funds){
  const p=[paneDiv(),paneDiv(),paneDiv()];let group=0;
  Array.from(funds.children).forEach(x=>{
   const label=x.matches('h2,h3')?x.textContent.trim():'';
   if(x.id.startsWith('bulk-')||/一括|複数/.test(label))group=1;
   if(x.id==='funds-history'||x.id==='debt-history'||/履歴/.test(label))group=2;
   if(['funds-form','funds-confirm','funds-status','funds-preview'].includes(x.id))group=0;
   p[group].append(x);
  });
  views(funds,p,['個別調整','一括調整','操作履歴']);
 }
 const market=q('#panel-market');
 if(market){
  const p=[paneDiv(),paneDiv()];let group=0;
  Array.from(market.children).forEach(x=>{
   if(x.id==='market-table'||(x.matches('h2,h3')&&/精算/.test(x.textContent)))group=1;
   p[group].append(x);
  });
  views(market,p,['出荷中','精算履歴']);
 }
 const analysis=q('#panel-analysis');
 if(analysis){
  const bar=analysis.querySelector('.an-subtabs');
  if(bar)for(const [key,label] of [['market-plus','市場構造'],['finance-plus','経営比較']]){
   const b=B(label,()=>{});b.className='an-subtab';b.dataset.group=key;b.setAttribute('aria-pressed','false');bar.append(b);
  }
  const pager=E('div','console-pager');pager.id='console-chart-pager';analysis.append(pager);
  bar?.addEventListener('click',ev=>{
   const b=ev.target.closest('[data-group]');if(!b)return;
   activeGroup=b.dataset.group;chartPage=0;
   queueMicrotask(()=>{if(['market-plus','finance-plus'].includes(activeGroup))extraCharts(activeGroup);chartPaging();});
  });
  const content=q('#analytics-content');if(content)new MutationObserver(()=>chartPaging()).observe(content,{childList:true});
 }
}
function bankSteps(){
 const f=q('#bank-config');if(!f)return;
 const steps=[E('div','console-bank-stage'),E('div','console-bank-stage')];
 let n=0,submit;
 Array.from(f.children).forEach(x=>{
  if(x.matches('button[type=submit]')){submit=x;return;}
  if(x.matches('fieldset')||(x.matches('label')&&x.querySelector('textarea'))||(x.matches('p')&&/累進|税率/.test(x.textContent)))n=1;
  steps[n].append(x);
 });
 const nav=E('div','console-switcher');
 const buttons=['利用・利率','税率・指数課税'].map((name,i)=>B(name,()=>{
  steps.forEach((s,j)=>s.hidden=j!==i);
  buttons.forEach((b,j)=>b.setAttribute('aria-pressed',String(j===i)));
 }));
 buttons.forEach((b,i)=>{b.setAttribute('aria-pressed',String(i===0));nav.append(b);});
 f.append(nav,...steps);steps[1].hidden=true;if(submit)f.append(submit);
}
function chartPaging(){
 const host=q('#analytics-content'),pager=q('#console-chart-pager');if(!host||!pager)return;
 const cards=Array.from(host.querySelectorAll('.an-chart')),per=mobile()?1:(innerHeight<790?1:2);
 const total=Math.max(1,Math.ceil(cards.length/per));chartPage=Math.min(chartPage,total-1);
 cards.forEach((c,i)=>c.hidden=i<chartPage*per||i>=(chartPage+1)*per);
 pager.hidden=total<=1;
 if(total>1){
  pager.replaceChildren(B('← 前のグラフ',()=>{chartPage--;chartPaging();}),E('small','',String(chartPage+1)+' / '+total+' · 全'+cards.length+'グラフ'),B('次のグラフ →',()=>{chartPage++;chartPaging();}));
  pager.firstChild.disabled=chartPage<=0;pager.lastChild.disabled=chartPage>=total-1;
 }
}
function chart(title,subtitle,rows){
 const card=E('article','an-chart');
 card.append(E('h3','',title),E('p','an-chart-caption',subtitle));
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
 svg.setAttribute('viewBox','0 0 600 230');svg.setAttribute('role','img');svg.setAttribute('aria-label',title);svg.classList.add('an-svg');
 const make=(tag,attrs,t)=>{
  const x=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>x.setAttribute(k,String(v)));if(t!==undefined)x.textContent=String(t);return x;
 };
 const max=Math.max(1,...rows.map(x=>x.value||0)),step=520/Math.max(1,rows.length);
 for(let i=0;i<=4;i++){const y=188-i*42;svg.append(make('line',{x1:48,x2:575,y1:y,y2:y,stroke:'#dceae4'}));}
 rows.forEach((r,i)=>{
  const x=50+step*i+step*.17,h=160*(r.value||0)/max;
  const rect=make('rect',{x,y:188-h,height:h,width:Math.max(6,step*.65),rx:4,fill:['#15ae91','#4ba0c4','#ebae57','#7f8cc9'][i%4]});
  rect.append(make('title',{},r.label+'：'+(r.note??r.value)));
  svg.append(rect,make('text',{x:x+step*.32,y:210,'text-anchor':'middle',fill:'#47665f','font-size':rows.length>8?9:12},String(r.label).slice(0,9)));
 });
 card.append(svg);return card;
}
function extraCharts(group){
 if(!snapshot)return;
 const host=q('#analytics-content'),g=E('div','an-grid');
 if(!host)return;
 const players=snapshot.players||[],market=snapshot.market||[],products=['white','sea','shisa'],labels=['標準','海坊主','シーサー'];
 if(group==='market-plus'){
  g.append(chart('商品別の保有者数','現在の在庫が1個以上の参加者',products.map((id,i)=>({label:labels[i],value:players.filter(p=>(p.stock||[]).some(s=>s.product===id&&!/^0(?:\\.0*)?(?:e[+-]?\\d+)?$/i.test(String(s.quantity||'0')))).length}))));
  g.append(chart('出荷中の商品','現在の出品レコード件数',products.map((id,i)=>({label:labels[i],value:(snapshot.pending||[]).filter(p=>p.product===id).length}))));
  g.append(chart('市場の参加店舗','精算1回あたりの平均出店数',products.map((id,i)=>{const vals=market.filter(p=>p.product===id);return {label:labels[i],value:vals.length?vals.reduce((a,b)=>a+Number(b.sellers||0),0)/vals.length:0};})));
  g.append(chart('販売成立率','販売成立した精算回の割合（％）',products.map((id,i)=>{const vals=market.filter(p=>p.product===id);return {label:labels[i],value:vals.length?vals.filter(x=>Number(x.sold)>0||magnitude(x.sold)>0).length*100/vals.length:0};})));
 }else{
  const sorted=players.slice().sort((a,b)=>magnitude(a.cash)-magnitude(b.cash));
  g.append(chart('資産階層と強化段階','所持金の下位から5分割／平均強化Lv.',[0,1,2,3,4].map(i=>{const list=sorted.slice(Math.floor(i*sorted.length/5),Math.floor((i+1)*sorted.length/5));return {label:'階層'+(i+1),value:list.length?list.reduce((s,p)=>s+Number(p.tier||0),0)/list.length:0};})));
  const classes=[...new Set(players.map(p=>p.class_number))].sort((a,b)=>Number(a)-Number(b));
  g.append(chart('クラス別の売上規模','売上桁数の中央値',classes.map(c=>{const a=players.filter(p=>p.class_number===c).map(p=>Math.max(0,magnitude(p.revenue))).sort((x,y)=>x-y);return {label:String(c)+'組',value:a.length?a[Math.floor(a.length/2)]:0};})));
  const levels=[[0,0],[1,5],[6,20],[21,100],[101,1e9]];
  g.append(chart('強化段階と売上','強化レベル帯別の売上桁数中央値',levels.map(([lo,hi])=>{const a=players.filter(p=>Number(p.tier)>=lo&&Number(p.tier)<=hi).map(p=>Math.max(0,magnitude(p.revenue))).sort((x,y)=>x-y);return {label:lo===0?'未強化':lo+'～',value:a.length?a[Math.floor(a.length/2)]:0};})));
  const amounts=[0,10,100,1000,5000];
  g.append(chart('製造規模と純利益','製造数の桁数区間で比較',amounts.map((lo,i)=>{const hi=amounts[i+1]??Infinity;const a=players.filter(p=>magnitude(p.manufactured)>=lo&&magnitude(p.manufactured)<hi).map(p=>Math.max(0,magnitude(p.net_profit))).sort((x,y)=>x-y);return {label:'10^'+lo,value:a.length?a[Math.floor(a.length/2)]:0};})));
 }
 host.replaceChildren(g);chartPage=0;chartPaging();
}
function enhance(kind){
 const source=q('#bulletin-admin-'+kind);if(!source)return;
 const rows=Array.from(source.querySelectorAll(':scope>article'));
 if(!rows.length&&!source.textContent.includes('ありません'))return;
 letters[kind]=rows.map(article=>({meta:article.querySelector('small')?.textContent||'',text:article.querySelector('p')?.textContent||'',remove:article.querySelector('button')}));
 source.replaceChildren();letterPage[kind]=0;letterSelected[kind]=0;bodyPage[kind]=0;
 inboxDraw(kind);
}
function drawInbox(kind){inboxDraw(kind);}
function inboxDraw(kind){
 const prefix=kind==='posts'?'notice':'message',list=q('#'+prefix+'-list'),root=q('#'+prefix+'-inbox');
 if(!list||!root)return;
 const rows=letters[kind],per=mobile()?4:5,total=Math.max(1,Math.ceil(rows.length/per));
 letterPage[kind]=Math.min(total-1,letterPage[kind]);list.replaceChildren();
 if(!rows.length){list.append(E('p','muted',kind==='posts'?'配信履歴はありません。':'メッセージはありません。'));q('#'+prefix+'-detail').replaceChildren(E('p','muted','一覧から選択すると本文を表示します。'));return;}
 rows.slice(letterPage[kind]*per,(letterPage[kind]+1)*per).forEach((x,i)=>{
  const index=letterPage[kind]*per+i;
  const b=B('',()=>{letterSelected[kind]=index;bodyPage[kind]=0;inboxDraw(kind);root.classList.add('console-reading');});
  b.setAttribute('aria-current',String(letterSelected[kind]===index));
  const labels=E('span','console-mail-summary');
  labels.append(E('strong','',x.text.replace(/\s+/g,' ').slice(0,54)||'本文なし'),E('small','',x.meta));
  b.append(E('span','console-mail-icon',kind==='posts'?'☀':'✉'),labels);list.append(b);
 });
 const bar=E('div','console-pager'),prev=B('← 前',()=>{letterPage[kind]--;inboxDraw(kind);}),next=B('次 →',()=>{letterPage[kind]++;inboxDraw(kind);});
 prev.disabled=letterPage[kind]===0;next.disabled=letterPage[kind]>=total-1;
 bar.append(prev,E('small','',String(letterPage[kind]+1)+' / '+total+' · '+rows.length+'件'),next);list.append(bar);
 readLetter(kind);
}
function readLetter(kind){
 const prefix=kind==='posts'?'notice':'message',target=q('#'+prefix+'-detail'),current=letters[kind][letterSelected[kind]];
 if(!target||!current)return;
 target.replaceChildren();
 const back=B('← 一覧に戻る',()=>q('#'+prefix+'-inbox').classList.remove('console-reading'));
 back.className='console-mobile-back';target.append(back);
 target.append(E('strong','console-letter-title',kind==='posts'?'お知らせの本文':'メッセージの本文'),E('small','console-letter-meta',current.meta));
 const chars=Array.from(current.text),per=mobile()?200:520,total=Math.max(1,Math.ceil(chars.length/per));
 bodyPage[kind]=Math.min(total-1,bodyPage[kind]);
 target.append(E('p','console-letter-body',chars.slice(bodyPage[kind]*per,(bodyPage[kind]+1)*per).join('')));
 const bar=E('div','console-pager'),prev=B('← 本文前',()=>{bodyPage[kind]--;readLetter(kind);}),next=B('本文次 →',()=>{bodyPage[kind]++;readLetter(kind);});
 prev.disabled=bodyPage[kind]===0;next.disabled=bodyPage[kind]>=total-1;
 bar.append(prev,E('small','',String(bodyPage[kind]+1)+' / '+total),next);target.append(bar);
 if(current.remove)target.append(current.remove);
}
function bulletin(){
 const refresh=q('#notice-refresh-proxy');
 if(refresh)refresh.addEventListener('click',()=>q('#bulletin-refresh')?.click());
 document.addEventListener('admin-bulletin-ready',()=>{enhance('posts');enhance('messages');});
 for(const kind of ['posts','messages']){
  if(q('#bulletin-admin-'+kind)?.querySelector('article'))enhance(kind);
 }
 qa('.console-compose-tab').forEach(b=>b.addEventListener('click',()=>{
  const compose=b.dataset.compose==='yes';
  q('#notice-compose-area').hidden=!compose;
  q('#notice-inbox-area').hidden=compose;
  qa('.console-compose-tab').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
 }));
}
function init(){
 nav();panels();tables();bulletin();
 document.addEventListener('admin-dashboard-ready',ev=>{snapshot=ev.detail;overview();if(activeGroup==='market-plus'||activeGroup==='finance-plus')extraCharts(activeGroup);});
 if(window.__adminDashboardSnapshot){snapshot=window.__adminDashboardSnapshot;overview();}
 const current=q('[data-panel][aria-selected=true]');activate(current?.dataset.panel||'overview');
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
