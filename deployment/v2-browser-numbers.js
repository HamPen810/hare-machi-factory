/* Exact sparse V2 numbers for browser tables, rankings, and chart axes.
   Does NOT change writes or convert astronomical amounts to Number. */
(function(root){
'use strict';
const MAX_TERMS=2048, MAX_COEFF_DIGITS=10000, MAX_EXPONENT_DIGITS=256;
function abs(x){return x<0n?-x:x;}
function digits(x){return abs(x).toString().length;}
function parse(wire){
 if(typeof wire!=='string'||!wire.startsWith('S1:'))throw Error('V2数値形式が不正です');
 const raw=wire.slice(3);if(!raw)return [];
 const parts=raw.split(',');if(parts.length>MAX_TERMS)throw Error('V2数値の項数が多すぎます');
 const terms=new Map();
 for(const part of parts){
  const m=/^(-?\d+)@(\d+)$/.exec(part);if(!m||m[1].replace('-','').length>MAX_COEFF_DIGITS||m[2].length>MAX_EXPONENT_DIGITS)throw Error('V2数値の形式が不正です');
  const exp=BigInt(m[2]),coeff=BigInt(m[1]);if(coeff===0n)throw Error('ゼロ係数は禁止です');
  const key=exp.toString();terms.set(key,(terms.get(key)||0n)+coeff);
 }
 const result=[...terms].filter(p=>p[1]!==0n).map(([e,c])=>[BigInt(e),c]);
 result.sort((a,b)=>a[0]<b[0]?-1:a[0]>b[0]?1:0);
 if(result.length>MAX_TERMS)throw Error('V2数値の項数が多すぎます');
 return result;
}
function combine(a,b,subtract=false){
 const merged=new Map();
 for(const [e,c] of a)merged.set(e.toString(),(merged.get(e.toString())||0n)+c);
 for(const [e,c] of b)merged.set(e.toString(),(merged.get(e.toString())||0n)+(subtract?-c:c));
 return [...merged].filter(x=>x[1]!==0n).map(([e,c])=>[BigInt(e),c]).sort((x,y)=>x[0]<y[0]?-1:x[0]>y[0]?1:0);
}
function sign(terms){
 if(!terms.length)return 0;
 let exponent=terms[0][0],carry=terms[0][1],nonzero=false;
 for(let i=1;i<terms.length;i++){
  const next=terms[i];const gap=next[0]-exponent;let quotient,remainderExists;
  if(gap>BigInt(digits(carry))){
   quotient=carry<0n?-1n:0n;remainderExists=carry!==0n;
  }else{
   const base=10n**gap;
   // floor division for negative coefficients (JS division truncates toward zero).
   quotient=carry/base;let remainder=carry%base;
   if(remainder<0n){quotient-=1n;remainder+=base;}
   remainderExists=remainder!==0n;
  }
  nonzero=nonzero||remainderExists;carry=quotient+next[1];exponent=next[0];
 }
 return carry>0n?1:carry<0n?-1:nonzero?1:0;
}
function compare(a,b){return sign(combine(parse(a),parse(b),true));}
function magnitude(terms){
 if(!terms.length||sign(terms)===0)return null;
 const positive=sign(terms)<0?terms.map(([e,c])=>[e,-c]):terms;
 let high=0n;
 for(const [e,c] of positive){const limit=e+BigInt(digits(c));if(limit>high)high=limit;}
 const ge=(e)=>sign(combine(positive,[[e,1n]],true))>=0;
 let lo=0n,hi=high;
 while(lo<hi){const middle=(lo+hi+1n)/2n;if(ge(middle))lo=middle;else hi=middle-1n;}
 return lo;
}
function compact(wire,precision=5){
 const terms=parse(wire),polarity=sign(terms);
 if(polarity===0)return '0';
 const absolute=polarity<0?terms.map(([e,c])=>[e,-c]):terms;
 const power=magnitude(terms);
 const prefix=polarity<0?'−':'';
 if(power<=14n){
  let n=0n;
  for(const [e,c] of absolute)n+=c*10n**e;
  return prefix+n.toLocaleString('ja-JP');
 }
 const count=Math.max(1,Math.min(8,Math.trunc(precision)));
 let coeff=0n;
 for(let index=0;index<count;index++){
  const place=power-BigInt(index);
  if(place<0n)break;
  let lo=0n,hi=9n;
  while(lo<hi){
   const mid=(lo+hi+1n)/2n;
   const proposed=(coeff*10n+mid)*10n**place;
   if(sign(combine(absolute,[[0n,proposed]],true))>=0)lo=mid;
   else hi=mid-1n;
  }
  coeff=coeff*10n+lo;
 }
 const raw=coeff.toString().padStart(count,'0');
 return prefix+raw[0]+(raw.length>1?'.'+raw.slice(1):'')+'e+'+power.toString();
}
function chartMagnitude(wire,max=300){
 const p=magnitude(parse(wire));if(p===null)return 0;
 // Explicitly log-scaled. A bounded double is for rendering only, never settlement.
 const ceiling=BigInt(Math.max(1,Math.trunc(max)));
 return Number(p>ceiling?ceiling:p);
}
root.TeruV2Number={parse,sign:(wire)=>sign(parse(wire)),compare,compact,chartMagnitude,magnitude:(wire)=>{const m=magnitude(parse(wire));return m===null?null:m.toString();}};
})(typeof window==='object'?window:globalThis);
