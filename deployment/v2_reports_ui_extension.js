/* V2 rankings and historical chart rendering: authenticated, read-only. */
const ranksForm=$('v2-rank-form');
ranksForm.addEventListener('submit',async event=>{
 event.preventDefault();
 const target=$('v2-rank-result');
 target.textContent='ランキングを取得中…';
 try{
  const json=await request('/api/v2/ranks');
  if(json.format!=='S1'||json.authoritative!=='legacy_numeric')throw Error('V2ランキング形式が不正です');
  const metric=$('v2-rank-metric').value,scope=$('v2-rank-scope').value;
  const rows=json.rankings?.[metric]?.[scope];
  if(!Array.isArray(rows))throw Error('ランキングの取得結果が不正です');
  target.replaceChildren();
  const table=document.createElement('table');
  const head=document.createElement('tr');
  for(const caption of ['順位','対象','数値']){
   const th=document.createElement('th');th.textContent=caption;head.appendChild(th);
  }
  table.appendChild(head);
  for(const row of rows.slice(0,60)){
   const tr=document.createElement('tr');
   const values=[String(row.rank)+'位',
     scope==='individual'?String(row.display_name):String(row.class_number)+'組',
     window.TeruV2Number.compact(row[metric])];
   for(const value of values){
    const td=document.createElement('td');td.textContent=value;
    td.style.cssText='padding:7px;border-bottom:1px solid #455670;overflow-wrap:anywhere';
    tr.appendChild(td);
   }
   table.appendChild(tr);
  }
  table.style.width='100%';table.style.borderCollapse='collapse';
  target.append(table);
 }catch(error){target.textContent=error.message;}
});

$('v2-data-load').addEventListener('click',async ()=>{
 const target=$('v2-data-result');
 target.textContent='データ履歴を取得中…';
 try{
  const json=await request('/api/v2/data');
  if(json.format!=='S1'||!Array.isArray(json.timeline))throw Error('V2履歴の形式が不正です');
  const rows=json.timeline.slice(-100).filter(row=>row.revenue?.startsWith('S1:'));
  target.replaceChildren();
  if(rows.length===0){target.textContent='履歴はありません。';return;}
  const ns='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(ns,'svg');
  svg.setAttribute('viewBox','0 0 600 230');
  svg.setAttribute('role','img');
  svg.setAttribute('aria-label','市場売上の桁数推移。対数目盛');
  const values=rows.map(row=>{
   const digits=window.TeruV2Number.magnitude(row.revenue);
   if(digits===null)return 0;
   const n=BigInt(digits);
   return Number(n>1000000n?1000000n:n);
  });
  const max=Math.max(1,...values);
  const pts=values.map((v,i)=>[
    40+i*530/Math.max(1,values.length-1),
    190-155*v/max
  ]);
  const axis=document.createElementNS(ns,'line');
  axis.setAttribute('x1','40');axis.setAttribute('y1','190');
  axis.setAttribute('x2','570');axis.setAttribute('y2','190');
  axis.setAttribute('stroke','#8faac5');svg.appendChild(axis);
  const path=document.createElementNS(ns,'polyline');
  path.setAttribute('points',pts.map(p=>p.join(',')).join(' '));
  path.setAttribute('fill','none');path.setAttribute('stroke','#7ad8be');
  path.setAttribute('stroke-width','2.8');svg.appendChild(path);
  const caption=document.createElementNS(ns,'text');
  caption.setAttribute('x','40');caption.setAttribute('y','216');
  caption.setAttribute('fill','#dde9ff');caption.setAttribute('font-size','13');
  caption.textContent='最近の履歴 '+rows.length+'件／縦軸は売上の桁数（上限100万桁）';
  svg.appendChild(caption);
  target.appendChild(svg);
  const latest=document.createElement('p');
  latest.className='muted';
  latest.textContent='最新の売上：'+window.TeruV2Number.compact(rows.at(-1).revenue)+'（'+rows.at(-1).revenue+'）';
  target.append(latest);
 }catch(error){target.textContent=error.message;}
});
