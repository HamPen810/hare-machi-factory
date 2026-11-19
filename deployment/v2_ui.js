'use strict';
const $=id=>document.getElementById(id);
let state=null;
const fields=[
 ['gross','合計購入額'],
 ['illustrative_fee','参考手数料'],
 ['illustrative_debit','参考引落額'],
 ['current_cash','現在の所持金'],
 ['cash_after_preview','試算後の所持金'],
 ['current_stock','現在の在庫'],
 ['stock_after_preview','試算後の在庫']
];
function setError(message){$('error').textContent=message||'';$('error').hidden=!message;}
async function request(path,body){
 const opts={credentials:'same-origin',cache:'no-store',headers:{'Accept':'application/json'}};
 if(body!==undefined){opts.method='POST';opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body);}
 const response=await fetch(path,opts);
 let data;
 try{data=await response.json();}catch(_){throw Error('サーバーの応答を読み取れませんでした。');}
 if(response.status===401){$('status').textContent='ログインが必要です。';throw Error('ゲームに戻ってログインしてください。');}
 if(!response.ok)throw Error(data.error||'API通信に失敗しました (HTTP '+response.status+')');
 return data;
}
async function refresh(){
 $('refresh').disabled=true;$('status').textContent='資産を確認中です。';setError('');
 try{
  const next=await request('/api/v2/balances');
  if(next.mode!=='read-only'||next.format!=='S1'||!Array.isArray(next.stock))throw Error('V2資産情報の形式が異なります。');
  state=next;$('cash').textContent=next.cash;$('balance').hidden=false;
  const select=$('product');const selected=select.value;select.replaceChildren();
  for(const item of next.stock){if(!item.product)continue;const opt=document.createElement('option');opt.value=item.product;opt.textContent=item.product;select.appendChild(opt);}
  if([...select.options].some(o=>o.value===selected))select.value=selected;
  select.disabled=!select.options.length;
  $('submit').disabled=!select.options.length;
  $('status').textContent='ログイン済み。現在の所持金と在庫を読み取りました。';
 }catch(e){state=null;$('submit').disabled=true;$('status').textContent='資産を取得できませんでした。';setError(e.message);}
 finally{$('refresh').disabled=false;}
}
async function preview(e){
 e.preventDefault();
 if(!state)return;
 $('submit').disabled=true;$('results').hidden=true;setError('');
 try{
  const feeNumber=Number($('fee').value);
  if(!Number.isFinite(feeNumber)||feeNumber<0||feeNumber>100)throw Error('参考手数料率は0～100%で指定してください。');
  const bps=Math.round(feeNumber*100);
  const payload={product:$('product').value,quantity:$('quantity').value.trim(),
       unit_price:$('unit-price').value.trim(),fee_bps:bps};
  const response=await request('/api/v2/preview',payload);
  if(response.mode!=='simulation_only'||response.transaction_saved!==false||response.order_placed!==false)
    throw Error('試算用API以外の応答を受信しました。');
  $('results').replaceChildren();
  for(const [key,label] of fields){
   const line=document.createElement('p');line.className='result';
   const header=document.createElement('strong');header.textContent=label;
   const out=document.createElement('output');out.textContent=String(response[key]??'');
   line.append(header,out);$('results').appendChild(line);
  }
  $('results').hidden=false;
 }catch(e){setError(e.message);}
 finally{$('submit').disabled=!state;}
}
$('refresh').addEventListener('click',refresh);
$('preview-form').addEventListener('submit',preview);
refresh();
