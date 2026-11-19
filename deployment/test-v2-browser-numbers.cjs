'use strict';
const assert=require('node:assert/strict');
require('./v2-browser-numbers.js');
const N=globalThis.TeruV2Number;
assert.equal(N.compact('S1:'),'0');
assert.equal(N.compact('S1:5@0'),'5');
assert.equal(N.compact('S1:-10@0'),'−10');
assert.equal(N.compact('S1:1@1000000000'),'1.0000e+1000000000');
assert.equal(N.compact('S1:1@1000000000,1@0'),'1.0000e+1000000000');
assert.equal(N.compact('S1:1@1000000000,-1@1000000000,27@0'),'27');
assert.equal(N.sign('S1:1@1000000000,-1@1000000000'),0);
assert.equal(N.compare('S1:1@1000000000,1@0','S1:1@1000000000'),1);
assert.equal(N.compare('S1:-1@1000000000','S1:-2@1000000000'),1);
assert.equal(N.compare('S1:1@3,-1@0','S1:999@0'),0);
assert.equal(N.magnitude('S1:1@1000000000'),'1000000000');
assert.equal(N.chartMagnitude('S1:1@1000000000',300),300);
assert.equal(N.chartMagnitude('S1:5@5',300),5);
assert.equal(N.compact('S1:1@30,-1@30,99@0'),'99');
assert.equal(N.compact('S1:12@20'),'1.2000e+21');
for(let i=0;i<500;i++){
 const a=BigInt(Math.floor(Math.random()*2_000_001)-1_000_000);
 const b=BigInt(Math.floor(Math.random()*2_000_001)-1_000_000);
 const sa=a===0n?'S1:':'S1:'+a.toString()+'@0';
 const sb=b===0n?'S1:':'S1:'+b.toString()+'@0';
 assert.equal(N.compare(sa,sb),a<b?-1:a>b?1:0);
 assert.equal(N.sign(sa),a<0n?-1:a>0n?1:0);
 assert.equal(N.compact(sa),a.toLocaleString('ja-JP').replace('-','−'));
}
for(const bad of ['','S1:1@-1','S1:0@0','S1:NaN@3','S1:1@a', 'S1:'+('9'.repeat(10001))+'@0']){
 assert.throws(()=>N.parse(bad));
}
console.log('V2_BROWSER_EXACT_RANKING_AND_CHART_TESTS_PASSED');
