/* Admin Analytics & Navigation — presentation only.
   Data comes from existing authenticated /api/admin/dashboard response.
   No mutations, no background polling and no extra analytics network calls. */
(()=>{
'use strict';
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
let snapshot=null;
let activeGroup='players';
let marketLimit=60;
const productNames={white:'てるてる坊主',sea:'海坊主',shisa:'シーサー坊主'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function logMagnitude(v){
  let s=String(v??'0').trim().replace(/^\+/,'');
  if(!s||s==='0'||s==='0.0')return 0;
  let negative=s[0]==='-';
  if(negative)s=s.slice(1);
  const match=s.match(/^((?:\d+(?:\.\d*)?|\.\d+))(?:e([+-]?\d+))?$/i);
  if(!match)return 0;
  const body=match[1],exponent=Number(match[2]||0);
  if(!Number.isFinite(exponent))return 0;
  const parts=body.split('.');
  const raw=(parts[0]||'').replace(/^0+/,'');
  let magnitude;
  if(raw.length){
    const sig=raw.slice(0,10);
    magnitude=Math.log10(Number(sig))+raw.length-sig.length;
  }else{
    const fraction=parts[1]||'';
    const nonzero=fraction.search(/[1-9]/);
    if(nonzero<0)return 0;
    const sig=fraction.slice(nonzero,nonzero+10);
    magnitude=Math.log10(Number(sig))-sig.length-(nonzero+1-sig.length);
    // sig starts at fractional decimal position nonzero+1
    magnitude=Math.log10(Number(sig))-(nonzero+sig.length);
  }
  magnitude+=exponent;
  // Signed order-of-magnitude transformed scale, no Infinity for e+10000.
  const value=Math.max(0,Math.log10(1+10**Math.min(6,magnitude)));
  const log = magnitude>6?magnitude: value;
  return negative?-log:log;
}
function safeNumber(v){let n=Number(v);return Number.isFinite(n)?n:0;}
function fmt(v){
  const s=String(v??'0');
  if(s.length>18){const l=logMagnitude(s);return (l<0?'-':'')+'約10^'+Math.abs(l).toFixed(1)}
  return s.replace(/\B(?=(\d{3})+(?!\d))/g,',');
}
function metricLog(value){return logMagnitude(value);}
function median(arr){if(!arr.length)return 0;const a=[...arr].sort((x,y)=>x-y);return (a[Math.floor((a.length-1)/2)]+a[Math.floor(a.length/2)])/2;}
function chartBox(title,caption,svg,description=''){
  const card=document.createElement('article');
  card.className='an-chart';
  const h=document.createElement('h3');h.textContent=title;
  const sub=document.createElement('p');sub.className='an-chart-caption';sub.textContent=caption;
  card.append(h,sub);
  if(svg){card.append(svg);}
  else{const empty=document.createElement('p');empty.className='muted';empty.textContent='表示できるデータがありません。';card.append(empty);}
  if(description){const p=document.createElement('p');p.className='an-chart-foot';p.textContent=description;card.append(p);}
  return card;
}
const NS='http://www.w3.org/2000/svg';
function node(name,attrs={},text=''){
  const el=document.createElementNS(NS,name);
  for(const [key,value] of Object.entries(attrs))el.setAttribute(key,String(value));
  if(text)el.textContent=text;
  return el;
}
function baseSVG(label){
  const svg=node('svg',{viewBox:'0 0 640 260',role:'img','aria-label':label,focusable:'false',preserveAspectRatio:'xMidYMid meet'});
  svg.classList.add('an-svg');
  svg.append(node('rect',{x:0,y:0,width:640,height:260,fill:'transparent'}));
  return svg;
}
function bars(data, label, options={}){
  if(!data.length)return null;
  const svg=baseSVG(label);
  const x0=54,y0=18,w=570,h=198;
  const numeric=data.map(x=>Math.max(0,safeNumber(x.value)));
  const max=Math.max(1,...numeric);
  for(let i=0;i<=4;i++){
    const y=y0+h-i*h/4;
    svg.append(node('line',{x1:x0,y1:y,x2:x0+w,y2:y,stroke:'#dce7e3','stroke-width':1}));
    const t=options.axisFormatter?options.axisFormatter(max*i/4):(max*i/4).toFixed(max<10?1:0);
    svg.append(node('text',{x:x0-8,y:y+4,'text-anchor':'end',fill:'#627974','font-size':11},t));
  }
  const step=w/data.length,bar=Math.max(3,Math.min(42,step*.66));
  data.forEach((r,i)=>{
    const height=Math.max(0,(numeric[i]/max)*h);
    const x=x0+i*step+(step-bar)/2;
    const rect=node('rect',{x,y:y0+h-height,width:bar,height,rx:4,fill:r.color||'#167b74'});
    rect.append(node('title',{},r.label+'：'+(r.tip||r.value)));
    svg.append(rect);
    const shown=options.showAllLabels||data.length<=12||i%(Math.ceil(data.length/10))===0;
    if(shown)svg.append(node('text',{x:x0+(i+.5)*step,y:y0+h+17,'text-anchor':'middle',fill:'#536b68','font-size':data.length>12?9:10},String(r.short||r.label).slice(0,9)));
  });
  return svg;
}
function lines(series,label,options={}){
  if(!series.length||!series.some(s=>s.points.length))return null;
  const svg=baseSVG(label),x0=52,y0=20,w=566,h=188;
  const points=series.flatMap(s=>s.points).map(p=>safeNumber(p.y));
  const max=Math.max(1,...points),min=options.zeroBased?0:Math.min(0,...points);
  const range=max-min||1;
  for(let i=0;i<=4;i++){
    const y=y0+h-i*h/4;
    svg.append(node('line',{x1:x0,y1:y,x2:x0+w,y2:y,stroke:'#dce7e3'}));
    svg.append(node('text',{x:x0-7,y:y+4,'text-anchor':'end',fill:'#627974','font-size':11},(min+range*i/4).toFixed(1)));
  }
  const maxlen=Math.max(2,...series.map(s=>s.points.length));
  for(const s of series){
    if(!s.points.length)continue;
    const poly=s.points.map((p,i)=>[
      x0+(i/(maxlen-1))*w,
      y0+h-((safeNumber(p.y)-min)/range)*h
    ]);
    const path=poly.map(([x,y],i)=>(i?'L':'M')+x.toFixed(1)+','+y.toFixed(1)).join(' ');
    svg.append(node('path',{d:path,fill:'none',stroke:s.color||'#167b74','stroke-width':2.6,'stroke-linecap':'round','stroke-linejoin':'round'}));
  }
  const legend=node('g');
  series.forEach((s,i)=>{
    const x=55+i*183;
    legend.append(node('line',{x1:x,y1:240,x2:x+20,y2:240,stroke:s.color||'#167b74','stroke-width':3}));
    legend.append(node('text',{x:x+26,y:244,fill:'#415f5b','font-size':12},s.name));
  });
  svg.append(legend);
  return svg;
}
function metricCard(name,number,unit=''){
  const c=document.createElement('div');c.className='an-kpi';
  const label=document.createElement('span');label.textContent=name;
  const value=document.createElement('strong');value.textContent=String(number)+unit;
  c.append(label,value);return c;
}
function renderAnalytics(){
  const host=$('#analytics-content');
  if(!host||!snapshot)return;
  host.replaceChildren();
  const players=snapshot.players||[],market=snapshot.market||[];
  const group=activeGroup;
  if(group==='players'){
    const summary=document.createElement('div');summary.className='an-kpis';
    const cash=players.map(p=>metricLog(p.cash));
    const production=players.map(p=>metricLog(p.manufactured));
    summary.append(
      metricCard('集計人数',players.length,'人'),
      metricCard('所持金の中央値（桁）',median(cash).toFixed(1)),
      metricCard('製造数の中央値（桁）',median(production).toFixed(1))
    );
    host.append(summary);
    const layout=document.createElement('div');layout.className='an-grid';
    const cashBins=[
      {label:'0以下',min:-Infinity,max:0},
      {label:'1〜9',min:0,max:1},
      {label:'10〜99',min:1,max:2},
      {label:'10²〜⁵',min:2,max:6},
      {label:'10⁶〜²⁰',min:6,max:21},
      {label:'10²¹〜¹⁰⁰',min:21,max:101},
      {label:'10¹⁰¹〜¹⁰⁰⁰',min:101,max:1001},
      {label:'10¹⁰⁰¹以上',min:1001,max:Infinity}
    ];
    const bins=cashBins.map(b=>({label:b.label,short:b.label,value:cash.filter(x=>x>=b.min&&x<b.max).length,tip:'該当プレイヤー数'}));
    layout.append(chartBox('所持金の分布','人数／対数（所持金の桁数）',bars(bins,'プレイヤーの所持金分布',{showAllLabels:true}), '巨額資産の影響で通常目盛が潰れないよう、金額を桁数に変換しています。'));
    const tierBins=[
     {label:'0',lo:0,hi:1},{label:'1–5',lo:1,hi:6},
     {label:'6–10',lo:6,hi:11},{label:'11–20',lo:11,hi:21},
     {label:'21–50',lo:21,hi:51},{label:'51以上',lo:51,hi:Infinity}
    ];
    layout.append(chartBox('タップ強化段階の分布','人数／現在の基本強化段階',
      bars(tierBins.map(b=>({label:b.label,value:players.filter(p=>safeNumber(p.tier)>=b.lo&&safeNumber(p.tier)<b.hi).length})), '強化段階別のプレイヤー数')));
    const cls=new Map();
    for(const p of players){const k=String(p.class_number||'不明');const entry=cls.get(k)||{n:0,production:[]};entry.n++;entry.production.push(metricLog(p.manufactured));cls.set(k,entry);}
    const classes=[...cls.entries()].sort((a,b)=>safeNumber(a[0])-safeNumber(b[0]));
    layout.append(chartBox('クラス別の参加人数','クラスごとのアカウント数',bars(classes.map(([k,v])=>({label:k+'組',value:v.n})), 'クラス別人数')));
    layout.append(chartBox('クラス別・製造数中央値','log10（個数+1）に近い桁数の中央値',
      bars(classes.map(([k,v])=>({label:k+'組',value:median(v.production),tip:'中央値'})), 'クラス別製造数の中央値')));
    host.append(layout);
  }else if(group==='market'){
    const limited=market.slice(0,marketLimit).reverse();
    const types=['white','sea','shisa'];
    const volume=types.map((type,i)=>({name:productNames[type],color:['#167b74','#dd9b43','#697acb'][i],
      points:limited.filter(r=>r.product===type).map(r=>({y:metricLog(r.sold)}))}));
    const supply=types.map((type,i)=>({name:productNames[type],color:['#167b74','#dd9b43','#697acb'][i],
      points:limited.filter(r=>r.product===type).map(r=>({y:metricLog(r.offered)}))}));
    const prices=types.map((type,i)=>({name:productNames[type],color:['#167b74','#dd9b43','#697acb'][i],
      points:limited.filter(r=>r.product===type).map(r=>({y:safeNumber(r.average_price)}))}));
    const layout=document.createElement('div');layout.className='an-grid';
    layout.append(chartBox('市場販売数の推移','商品別／販売数の桁数（古い順 → 新しい順）',lines(volume,'市場の販売数量推移'),'各商品の精算記録を古い順に表示。単位はlog10です。'));
    layout.append(chartBox('市場供給量の推移','商品別／出品数の桁数',lines(supply,'市場への供給量推移')));
    layout.append(chartBox('平均取引単価の推移','商品別／円（未成立は0として描画）',lines(prices,'市場の平均取引価格',{zeroBased:true})));
    const ratios=types.map((type,i)=>({name:productNames[type],color:['#167b74','#dd9b43','#697acb'][i],
      points:limited.filter(r=>r.product===type).map(r=>{
        const offered=metricLog(r.offered),sold=metricLog(r.sold);
        return {y:offered>0?Math.max(0,Math.min(100,100*10**Math.max(-6,sold-offered))):0};
      })}));
    layout.append(chartBox('売れ行きの目安','推定販売率（%）／大きな数も対数で比較',lines(ratios,'市場の販売率の推移',{zeroBased:true}),'非常に大きい数字は桁数近似のため、比率は参考値です。'));
    host.append(layout);
  }else if(group==='performance'){
    const layout=document.createElement('div');layout.className='an-grid';
    const ranked=[...players].sort((a,b)=>metricLog(b.manufactured)-metricLog(a.manufactured)).slice(0,12);
    layout.append(chartBox('製造数トップ12','製造数の桁数／参加者ごと',bars(ranked.map((p,i)=>({label:p.display_name||'参加者',short:String(i+1)+'位',value:Math.max(0,metricLog(p.manufactured)),tip:p.display_name+'：'+fmt(p.manufactured)})),'製造数ランキング上位12人')));
    const revenues=[...players].sort((a,b)=>metricLog(b.revenue)-metricLog(a.revenue)).slice(0,12);
    layout.append(chartBox('売上トップ12','売上の桁数／参加者ごと',bars(revenues.map((p,i)=>({label:p.display_name||'参加者',short:String(i+1)+'位',value:Math.max(0,metricLog(p.revenue)),tip:p.display_name+'：'+fmt(p.revenue)})),'売上ランキング上位12人')));
    const productTotals=['white','sea','shisa'].map(type=>{
       const qty=players.map(p=>(p.stock||[]).find(x=>x.product===type)?.quantity||'0').map(metricLog);
       return {label:productNames[type],value:median(qty),tip:'プレイヤー別在庫の桁数の中央値'};
    });
    layout.append(chartBox('商品別の倉庫在庫','全員を対象とした、商品別在庫の桁数中央値',bars(productTotals,'商品の在庫量の比較')));
    const profitBins=[
      {label:'マイナス',test:v=>v<0},
      {label:'0',test:v=>v===0},
      {label:'1〜10⁴',test:v=>v>0&&v<5},
      {label:'10⁵〜¹⁰',test:v=>v>=5&&v<11},
      {label:'10¹¹〜¹⁰⁰',test:v=>v>=11&&v<101},
      {label:'10¹⁰¹以上',test:v=>v>=101}
    ];
    const profits=players.map(p=>metricLog(p.net_profit));
    layout.append(chartBox('純利益の分布','負債・赤字を分離して人数を表示',bars(profitBins.map(b=>({label:b.label,value:profits.filter(b.test).length})), '純利益帯ごとのプレイヤー数')));
    host.append(layout);
  }
  const stamp=$('#analytics-stamp');
  if(stamp)stamp.textContent='最終取得 '+new Date(Number(snapshot.now)).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'})+' ／ 管理者データを再利用・追加通信なし';
}
function setGroup(group){
  activeGroup=group;
  $$('.an-subtab').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.group===group)));
  if(snapshot)renderAnalytics();
}
function activateOverview(){
  const btn=$('#tab-overview');
  if(!btn)return;
  for(const b of $$('[data-panel]')){
    const selected=b===btn;
    b.setAttribute('aria-selected',String(selected));
    const section=$('#panel-'+b.dataset.panel);
    if(section)section.hidden=!selected;
  }
}
function init(){
  $$('.an-subtab').forEach(b=>b.addEventListener('click',()=>setGroup(b.dataset.group)));
  const range=$('#an-market-window');
  if(range)range.addEventListener('change',()=>{marketLimit=Number(range.value)||60;if(activeGroup==='market')renderAnalytics();});
  const tabs=$('[role="tablist"]');
  if(tabs){
    tabs.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
      const buttons=$$('[data-panel]'),idx=buttons.indexOf(document.activeElement);
      if(idx<0)return;
      event.preventDefault();
      const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(idx+(event.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length;
      buttons[next].focus();buttons[next].click();
    });
    tabs.addEventListener('click',event=>{
      const tab=event.target.closest('[data-panel]');
      if(!tab)return;
      if(tab.dataset.panel==='overview')renderAnalytics();
      const heading=$('#section-title');
      if(heading)heading.textContent=tab.textContent.trim();
    });
  }
  document.addEventListener('admin-dashboard-ready',event=>{
    snapshot=event.detail;
    const shown=$('#panel-overview')&&!$('#panel-overview').hidden;
    if(shown)renderAnalytics();
  });
  // The dashboard script may finish its first request before this script runs.
  if(window.__adminDashboardSnapshot){
    snapshot=window.__adminDashboardSnapshot;
    renderAnalytics();
  }
  activateOverview();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
else init();
})();
