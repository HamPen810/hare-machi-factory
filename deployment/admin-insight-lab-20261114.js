/* Insight Lab: on-demand SVG graphs from existing authenticated admin dashboard.
   Zero extra API calls. No persistence, operations, or economic code changes. */
(()=>{
'use strict';
const Q=s=>document.querySelector(s), NS='http://www.w3.org/2000/svg';
const C=['#138e88','#6789cd','#df9e57','#a487cc','#d77d92','#6eaaa4','#9baf68'];
const N=(name,attrs={},str)=>{const e=document.createElementNS(NS,name);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,String(v)));if(str!==undefined)e.textContent=String(str);return e;};
const D=(name,text,cls)=>{const e=document.createElement(name);if(text!==undefined)e.textContent=String(text);if(cls)e.className=cls;return e;};
let state=null,category='assets',page=0;
const numerical=n=>Number.isFinite(Number(n))?Number(n):0;
function signedLog(value){
 let s=String(value??'0').trim(),sign=1;
 if(s[0]==='-'){sign=-1;s=s.slice(1);}
 const m=s.match(/^(\d+(?:\.\d*)?|\.\d+)(?:e([+-]?\d+))?$/i);
 if(!m)return 0;
 const parts=m[1].split('.'),head=parts[0].replace(/^0+/,'');
 let l;
 if(head){const part=head.slice(0,12);l=head.length-part.length+Math.log10(Number(part));}
 else{const f=parts[1]||'',i=f.search(/[1-9]/);if(i<0)return 0;const part=f.slice(i,i+12);l=Math.log10(Number(part))-part.length-i;}
 l+=Number(m[2]||0);
 return sign*(l>8?l:l < -14?0:Math.log10(1+10**l));
}
const ps=()=>Array.isArray(state?.players)?state.players:[];
const ms=()=>Array.isArray(state?.market)?state.market:[];
const datum=(p,k)=>k==='tier'?numerical(p.tier):signedLog(p[k]);
const data=k=>ps().map(p=>datum(p,k));
const clean=a=>a.filter(Number.isFinite).sort((a,b)=>a-b);
function quart(a,p){const x=clean(a);if(!x.length)return 0;const t=(x.length-1)*p,i=Math.floor(t);return x[i]+(x[Math.min(i+1,x.length-1)]-x[i])*(t-i);}
function corr(a){if(a.length<3)return null;let ax=0,ay=0;for(const [x,y] of a){ax+=x;ay+=y;}ax/=a.length;ay/=a.length;let xy=0,xx=0,yy=0;for(const [x,y] of a){xy+=(x-ax)*(y-ay);xx+=(x-ax)**2;yy+=(y-ay)**2;}return xx>1e-12&&yy>1e-12?xy/Math.sqrt(xx*yy):null;}
function ranked(a){const list=a.map((x,i)=>({x,i})).sort((a,b)=>a.x-b.x),out=[];for(let i=0;i<list.length;){let j=i+1;while(j<list.length&&list[j].x===list[i].x)j++;for(let k=i;k<j;k++)out[list[k].i]=(i+j+1)/2;i=j;}return out;}
function rho(a){const x=ranked(a.map(v=>v[0])),y=ranked(a.map(v=>v[1]));return corr(x.map((v,i)=>[v,y[i]]));}
const value=k=>({cash:'所持金',manufactured:'製造数',revenue:'売上',net_profit:'純利益',tier:'強化レベル'})[k]||k;
const pts=(x,y)=>ps().map(p=>[datum(p,x),datum(p,y)]);
const cs=()=>[...new Set(ps().map(p=>String(p.class_number||'不明')))].sort((a,b)=>numerical(a)-numerical(b));
const groups=k=>cs().slice(0,8).map(c=>({label:c==='不明'?'不明':c+'組',values:ps().filter(p=>String(p.class_number||'不明')===c).map(p=>datum(p,k))}));
function svg(title){const v=N('svg',{viewBox:'0 0 760 385',role:'img','aria-label':title,preserveAspectRatio:'xMidYMid meet'});v.classList.add('lab-svg');return v;}
function txt(g,x,y,s,size=15,props={}){g.append(N('text',{x,y,'font-size':size,fill:'#516971',...props},s));}
function axis(g,xs,ys,labels){
 const L=86,R=728,T=33,B=306;
 const lo=(a)=>Math.min(0,...a),hi=a=>Math.max(1,...a);
 let xmin=lo(xs),xmax=hi(xs),ymin=lo(ys),ymax=hi(ys);
 if(xmax-xmin<.001){xmin-=1;xmax+=1;}if(ymax-ymin<.001){ymin-=1;ymax+=1;}
 const X=x=>L+(x-xmin)/(xmax-xmin)*(R-L),Y=y=>B-(y-ymin)/(ymax-ymin)*(B-T);
 for(let i=0;i<=4;i++){let y=T+(B-T)*i/4;g.append(N('line',{x1:L,y1:y,x2:R,y2:y,stroke:'#e5eaed'}));txt(g,L-8,y+4,(ymax-(ymax-ymin)*i/4).toFixed(ymax>100?0:1),12,{'text-anchor':'end'});}
 for(let i=0;i<=5;i++){const x=L+(R-L)*i/5;txt(g,x,B+24,(xmin+(xmax-xmin)*i/5).toFixed(xmax>100?0:1),12,{'text-anchor':'middle'});}
 txt(g,(L+R)/2,372,labels[0],14,{'text-anchor':'middle'});txt(g,22,170,labels[1],14,{'text-anchor':'middle',transform:'rotate(-90 22 170)'});
 return {X,Y,L,R,T,B,xmin,xmax,ymin,ymax};
}
function histogram(a,title){
 const g=svg(title),x=clean(a);if(!x.length)return g;
 let min=x[0],max=x[x.length-1];if(max-min<.001){min-=1;max+=1;}
 const n=12,bins=Array(n).fill(0);
 x.forEach(z=>bins[Math.min(n-1,Math.floor((z-min)/(max-min)*n))]++);
 const p=axis(g,[min,max],[0,...bins],['金額の桁数（符号付き対数）','人数']);
 bins.forEach((count,i)=>{const x1=p.X(min+(max-min)*i/n),x2=p.X(min+(max-min)*(i+1)/n),r=N('rect',{x:x1+2,y:p.Y(count),width:x2-x1-4,height:Math.max(0,p.Y(0)-p.Y(count)),fill:'#138e88',rx:3});r.append(N('title',{},count+'人'));g.append(r);});return g;
}
function donut(items,title){
 const g=svg(title),arr=items.filter(v=>v.n>0),total=arr.reduce((s,v)=>s+v.n,0);
 if(!total){txt(g,300,200,'データなし');return g;}
 let a=-Math.PI/2;const cx=260,cy=190,ro=130,ri=82;
 const pt=(r,t)=>[cx+r*Math.cos(t),cy+r*Math.sin(t)];
 arr.forEach((p,i)=>{
  const d=2*Math.PI*p.n/total,b=a+d,large=d>Math.PI?1:0,start=pt(ro,a),end=pt(ro,b),innerEnd=pt(ri,b),innerStart=pt(ri,a);
  const path=N('path',{d:'M'+start+' A'+ro+' '+ro+' 0 '+large+' 1 '+end+' L'+innerEnd+' A'+ri+' '+ri+' 0 '+large+' 0 '+innerStart+' Z',fill:C[i%C.length]});
  path.append(N('title',{},p.label+'：'+p.n+'人（'+(p.n/total*100).toFixed(1)+'%）'));g.append(path);a=b;
 });
 txt(g,cx,194,total+'人',29,{'font-weight':800,'text-anchor':'middle',fill:'#24434b'});
 arr.forEach((p,i)=>{const y=74+i*36;g.append(N('rect',{x:458,y:y-12,width:16,height:16,rx:3,fill:C[i%C.length]}));txt(g,484,y,p.label+' '+p.n+'人',14);});
 return g;
}
function scatter(xy,title,xlabel,ylabel){
 const g=svg(title),p=axis(g,xy.map(v=>v[0]),xy.map(v=>v[1]),[xlabel,ylabel]);
 xy.forEach(([x,y],i)=>{const dot=N('circle',{cx:p.X(x),cy:p.Y(y),r:4.6,fill:C[i%2],opacity:.58});dot.append(N('title',{},x.toFixed(1)+' / '+y.toFixed(1)));g.append(dot);});
 const r=corr(xy);
 if(r!=null){let mx=0,my=0;xy.forEach(([x,y])=>{mx+=x;my+=y;});mx/=xy.length;my/=xy.length;let num=0,den=0;xy.forEach(([x,y])=>{num+=(x-mx)*(y-my);den+=(x-mx)**2;});const slope=num/den,base=my-slope*mx;g.append(N('line',{x1:p.X(p.xmin),y1:p.Y(slope*p.xmin+base),x2:p.X(p.xmax),y2:p.Y(slope*p.xmax+base),stroke:'#e19a55','stroke-width':2.5,'stroke-dasharray':'8 5'}));}
 txt(g,727,20,'r='+(r===null?'算出不可':r.toFixed(3))+'　ρ='+(rho(xy)===null?'算出不可':rho(xy).toFixed(3))+'　n='+xy.length,15,{'text-anchor':'end','font-weight':800,fill:'#188c83'});
 return g;
}
function boxes(sets,title){
 const g=svg(title),valid=sets.filter(s=>s.values.length);if(!valid.length)return g;
 const p=axis(g,[0,valid.length+1],valid.flatMap(x=>x.values),['所属クラス','値の桁数']);
 valid.forEach((s,i)=>{
  const a=clean(s.values),x=p.X(i+1),low=a[0],high=a[a.length-1],q1=quart(a,.25),q2=quart(a,.5),q3=quart(a,.75),color=C[i%C.length];
  g.append(N('line',{x1:x,y1:p.Y(low),x2:x,y2:p.Y(high),stroke:color,'stroke-width':2}));
  g.append(N('rect',{x:x-22,y:p.Y(q3),width:44,height:Math.max(3,p.Y(q1)-p.Y(q3)),fill:color,'fill-opacity':.20,stroke:color,'stroke-width':2}));
  g.append(N('line',{x1:x-22,y1:p.Y(q2),x2:x+22,y2:p.Y(q2),stroke:color,'stroke-width':3}));
  txt(g,x,349,s.label,14,{'text-anchor':'middle'});
 });return g;
}
function line(series,title,axisY){
 const g=svg(title),all=series.flatMap(s=>s.y.map((z,i)=>[i,z]));
 if(!all.length)return g;
 const p=axis(g,all.map(v=>v[0]),all.map(v=>v[1]),['精算履歴（古い→新しい）',axisY]);
 series.forEach((s,i)=>{
  if(!s.y.length)return;
  g.append(N('path',{d:s.y.map((y,j)=>(j?'L':'M')+p.X(j).toFixed(2)+','+p.Y(y).toFixed(2)).join(' '),fill:'none',stroke:C[i],'stroke-width':3,'stroke-linecap':'round'}));
  g.append(N('rect',{x:110+i*190,y:5,width:13,height:13,rx:3,fill:C[i]}));txt(g,131+i*190,17,s.name,14);
 });return g;
}
function heatmap(keys){
 const g=svg('経営指標の相関行列'),L=285,T=75,sz=61;
 const names=keys.map(value);
 keys.forEach((k,i)=>{txt(g,L+sz*i+sz/2,54,names[i],13,{'text-anchor':'middle'});txt(g,L-10,T+sz*i+38,names[i],13,{'text-anchor':'end'});});
 keys.forEach((a,i)=>keys.forEach((b,j)=>{
  const r=corr(pts(a,b)),color=r==null?'#f2f5f4':r>=0?'rgba(19,142,136,'+(.14+.75*Math.abs(r))+')':'rgba(219,129,97,'+(.14+.75*Math.abs(r))+')';
  g.append(N('rect',{x:L+j*sz,y:T+i*sz,width:sz-5,height:sz-5,rx:5,fill:color}));
  txt(g,L+j*sz+(sz-5)/2,T+i*sz+35,r==null?'—':r.toFixed(2),13,{'text-anchor':'middle',fill:'#203b43','font-weight':800});
 }));
 txt(g,370,370,'Pearson の r ／ 各指標を符号付き対数で変換',14,{'text-anchor':'middle'});return g;
}
function dotplot(a,title){
 const g=svg(title),p=axis(g,[0,a.length+1],a.map(x=>x.y),['製造数上位プレイヤー','売上の桁数']);
 a.forEach((v,i)=>{const x=p.X(i+1),y=p.Y(v.y);g.append(N('line',{x1:x,y1:p.Y(0),x2:x,y2:y,stroke:'#b8dbd7','stroke-width':2}));const c=N('circle',{cx:x,cy:y,r:8,fill:C[i%C.length]});c.append(N('title',{},v.name+'　'+v.y.toFixed(1)+'桁'));g.append(c);txt(g,x,347,(i+1)+'位',13,{'text-anchor':'middle'});});return g;
}
function radar(){
 const g=svg('クラス別経営スコア'),group=cs().slice(0,4),keys=['cash','manufactured','revenue','net_profit','tier'],cx=367,cy=189,r=128;
 const medians=group.map(c=>keys.map(k=>quart(ps().filter(p=>String(p.class_number||'不明')===c).map(p=>datum(p,k)),.5)));
 for(let ring=1;ring<=4;ring++){const poly=keys.map((_,i)=>[cx+Math.sin(i*2*Math.PI/5)*r*ring/4,cy-Math.cos(i*2*Math.PI/5)*r*ring/4]);g.append(N('polygon',{points:poly.map(x=>x.join(',')).join(' '),fill:'none',stroke:'#dae7e8'}));}
 keys.forEach((k,i)=>{const x=Math.sin(i*2*Math.PI/5),y=-Math.cos(i*2*Math.PI/5);g.append(N('line',{x1:cx,y1:cy,x2:cx+r*x,y2:cy+r*y,stroke:'#e2ebed'}));txt(g,cx+(r+30)*x,cy+(r+21)*y,value(k),14,{'text-anchor':'middle'});});
 medians.forEach((med,j)=>{
  const p=med.map((n,i)=>{const rank=ranked(medians.map(v=>v[i]))[j];const score=group.length>1?(10+90*(rank-1)/(group.length-1)):50;return [cx+Math.sin(i*2*Math.PI/5)*r*score/100,cy-Math.cos(i*2*Math.PI/5)*r*score/100];});
  g.append(N('polygon',{points:p.map(x=>x.join(',')).join(' '),fill:C[j],'fill-opacity':.10,stroke:C[j],'stroke-width':3}));
  g.append(N('rect',{x:580,y:105+j*34,width:14,height:14,rx:3,fill:C[j]}));txt(g,606,118,group[j]+'組',15);
 });return g;
}
function cumulative(a){
 const x=clean(a),g=svg('累積分布曲線');if(!x.length)return g;
 const p=axis(g,x,[0,100],['所持金の桁数','累積人数（%）']);
 g.append(N('path',{d:x.map((v,i)=>(i?'L':'M')+p.X(v).toFixed(2)+','+p.Y(100*(i+1)/x.length).toFixed(2)).join(' '),stroke:C[0],'stroke-width':3,fill:'none'}));txt(g,665,55,'中央値 '+quart(x,.5).toFixed(1)+' 桁',16,{'text-anchor':'end','font-weight':800});return g;
}
function productShare(){
 const g=svg('在庫保有者の比較'),products=['white','sea','shisa'],labels=['てるてる','海坊主','シーサー'],groups=cs().slice(0,8);
 groups.forEach((cls,i)=>{
  const members=ps().filter(p=>String(p.class_number||'不明')===cls);
  txt(g,82,60+i*35,cls+'組',14,{'text-anchor':'end'});
  let pos=110;
  products.forEach((prod,j)=>{
   const n=members.filter(p=>(p.stock||[]).some(s=>s.product===prod&&signedLog(s.quantity)>0)).length;
   const rate=members.length?n/members.length:0,w=rate*150;
   const rect=N('rect',{x:pos,y:41+i*35,width:w,height:22,fill:C[j],rx:3});rect.append(N('title',{},labels[j]+'：'+n+' / '+members.length+'人'));g.append(rect);pos+=w+5;
  });
 });
 labels.forEach((n,i)=>{g.append(N('rect',{x:120+i*210,y:353,width:14,height:14,fill:C[i],rx:3}));txt(g,142+i*210,366,n,14);});return g;
}
function charts(){
 const all=ps(),arr=data('cash');
 const pairs=[['cash','manufactured'],['manufactured','revenue'],['tier','manufactured'],['cash','net_profit']];
 const products=['white','sea','shisa'],productsName=['てるてる','海坊主','シーサー'];
 const series=k=>products.map((id,i)=>({name:productsName[i],y:ms().filter(v=>v.product===id).slice(-48).map(v=>signedLog(v[k]))}));
 const details=(x,y)=>{const points=pts(x,y),p=corr(points),s=rho(points);return 'Pearson r='+(p==null?'算出不可':p.toFixed(3))+'、Spearman ρ='+(s==null?'算出不可':s.toFixed(3))+'、n='+points.length+'。相関は因果関係を示しません。';};
 const wealth=[
  ['所持金のヒストグラム','ヒストグラム',()=>histogram(arr,'所持金のヒストグラム'),'資産の桁数別に人数を表示。数値は符号付き対数変換。'],
  ['資産階層の構成比','ドーナツグラフ',()=>donut([['マイナス',v=>datum(v,'cash')<0],['ゼロ',v=>datum(v,'cash')===0],['1〜10桁',v=>datum(v,'cash')>0&&datum(v,'cash')<10],['11〜100桁',v=>datum(v,'cash')>=10&&datum(v,'cash')<100],['101〜1000桁',v=>datum(v,'cash')>=100&&datum(v,'cash')<1000],['1001桁以上',v=>datum(v,'cash')>=1000]].map(([label,fn])=>({label,n:all.filter(fn).length})),'資産階層の構成比'),'資産の分布を段階別に集計。'],
  ['クラス別の資産分布','箱ひげ図',()=>boxes(groups('cash'),'クラス別の資産分布'),'箱は四分位範囲、線は中央値、ひげは最小・最大。'],
  ['累積資産分布','累積折れ線',()=>cumulative(arr),'資産が一定水準以下のプレイヤーが何%かを表示。'],
  ['所持金と製造数','散布図',()=>scatter(pts('cash','manufactured'),'所持金と製造数','所持金（桁）','製造数（桁）'),details('cash','manufactured')],
  ['主要経営指標の相関','相関行列',()=>heatmap(['cash','manufactured','revenue','net_profit']),'符号付き対数で算出したPearson相関。値の絶対値が大きいほど色が濃い。']
 ];
 const business=[
  ['製造数と売上','散布図',()=>scatter(pts('manufactured','revenue'),'製造数と売上','製造数（桁）','売上（桁）'),details('manufactured','revenue')],
  ['強化レベルと製造数','散布図',()=>scatter(pts('tier','manufactured'),'強化レベルと製造数','強化Lv','製造数（桁）'),details('tier','manufactured')],
  ['所持金と純利益','散布図',()=>scatter(pts('cash','net_profit'),'所持金と純利益','所持金（桁）','純利益（桁）'),details('cash','net_profit')],
  ['クラス別の純利益','箱ひげ図',()=>boxes(groups('net_profit'),'クラス別純利益'),'純利益の四分位範囲を比較。赤字は負の対数値で表示。'],
  ['クラス別の経営力','レーダーチャート',radar,'クラス別中央値の相対的な順位スコア。絶対的な能力値ではありません。'],
  ['製造トップの売上','ドットプロット',()=>dotplot([...all].sort((a,b)=>datum(b,'manufactured')-datum(a,'manufactured')).slice(0,10).map(p=>({name:p.display_name,y:Math.max(0,datum(p,'revenue'))})),'製造トップの売上'),'製造数上位10名の売上規模をドットで比較。']
 ];
 const market=[
  ['市場の価格推移','折れ線',()=>line(series('average_price'),'市場の平均価格','平均価格（桁）'),'商品別・直近48回の精算の平均価格。'],
  ['市場の販売数推移','折れ線',()=>line(series('sold'),'市場の販売数','販売数（桁）'),'巨大な数値は対数表示。商品別の精算順を描画。'],
  ['商品保有者の内訳','ドーナツグラフ',()=>donut(products.map((k,i)=>({label:productsName[i],n:all.filter(p=>(p.stock||[]).some(s=>s.product===k&&signedLog(s.quantity)>0)).length})),'商品保有者の内訳'),'複数商品を保有する場合は重複計上。'],
  ['クラス別の商品保有率','横棒グラフ',productShare,'複数商品の保有率を横並びに表示。重複保有があるため合計100%にはなりません。']
 ];
 return {assets:wealth,business,market};
}
function init(){
 const panel=Q('#panel-analysis');if(!panel)return;
 const root=D('div',undefined,'lab-stage');root.id='insight-lab';
 const header=D('div',undefined,'lab-head'),title=D('div');
 title.append(D('small','INSIGHT LAB','lab-kicker'),D('h2','数字の奥にある物語。','lab-title'));
 const allCount=D('span','', 'lab-all-count');header.append(title,allCount);
 const tabs=D('div',undefined,'lab-tabs'),chart=D('div',undefined,'lab-card'),notes=D('p','','lab-note'),footer=D('div',undefined,'lab-nav');
 const count=D('span','','lab-counter');
 const render=()=>{
  for(const b of tabs.children)b.setAttribute('aria-pressed',String(b.dataset.category===category));
  if(!state){chart.replaceChildren(D('p','分析データを読み込み中…'));return;}
  const arr=charts()[category];page=(page+arr.length)%arr.length;
  const [label,kind,draw,detail]=arr[page];
  try{const head=D('div',undefined,'lab-card-head');head.append(D('h3',label),D('span',kind,'lab-chart-kind'));chart.replaceChildren(head,draw());notes.textContent=detail;}
  catch(e){console.warn('Graph rendering failed',e);chart.replaceChildren(D('p','このグラフは表示できませんでした。'));notes.textContent='';}
  count.textContent=(page+1)+' / '+arr.length;allCount.textContent=Object.values(charts()).reduce((a,b)=>a+b.length,0)+' グラフ';
 };
 [['assets','資産と格差'],['business','経営・相関'],['market','市場・流通']].forEach(([id,label])=>{
  const b=D('button',label,'lab-tab');b.type='button';b.dataset.category=id;b.onclick=()=>{category=id;page=0;render();};tabs.append(b);
 });
 const prev=D('button','← 前','lab-nav-btn'),next=D('button','次 →','lab-nav-btn');prev.type=next.type='button';
 prev.onclick=()=>{page--;render();};next.onclick=()=>{page++;render();};
 footer.append(prev,count,next);root.append(header,tabs,chart,notes,footer);panel.append(root);
 document.addEventListener('admin-dashboard-ready',e=>{state=e.detail;render();});
 if(window.__adminDashboardSnapshot)state=window.__adminDashboardSnapshot;
 Q('[data-panel="analysis"]')?.addEventListener('click',()=>requestAnimationFrame(render));
 render();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();