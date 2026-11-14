/* Browser smoke test of existing admin logic plus the new responsive cockpit.\n   Re-run for minimal IslandRound/IslandHand visual redesign. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');

const now=Date.now();
const players=[
 {id:'1',student_id:'2101',display_name:'テスト工場長',class_number:1,
  cash:'1e+120',tier:10,manufactured:'1e+200',revenue:'1e+110',net_profit:'1e+80',
  stock:[{product:'white',quantity:'99'}]},
 {id:'2',student_id:'2102',display_name:'次の工場長',class_number:2,
  cash:'750000',tier:3,manufactured:'15000',revenue:'3000',net_profit:'1500',stock:[]}
];
const boards={individual:[],classes:[]};
const dashboard={
 now,summary:{players:players.length,manufactured:'1e+200',revenue:'1e+110',net_profit:'1e+80',pending_shipments:0,settled_rounds:3},
 players,pending:[],rankings:{manufactured:boards,revenue:boards,net_profit:boards},
 market:[
  {product:'white',round:Math.floor(now/60000)-2,offered:'150',sold:'120',average_price:10,sellers:2},
  {product:'sea',round:Math.floor(now/60000)-2,offered:'40',sold:'25',average_price:40,sellers:1},
  {product:'white',round:Math.floor(now/60000)-1,offered:'200',sold:'180',average_price:12,sellers:3},
  {product:'shisa',round:Math.floor(now/60000),offered:'100',sold:'95',average_price:65,sellers:2}
 ],event:{phase:'open',practice:false}
};
const payload={
 dashboard,
 settings:{maintenance:false,announcement:'',rulebook:'',default_rulebook:'',announcement_revision:1,announcements:[]},
 notices:{posts:[
 {id:'p1',body:'管理者からのお知らせ。配信本文を一覧から選択して読めます。',student_id:null,display_name:null,created_at:now-100000,read_count:2}
 ],messages:[
 {id:'m1',body:'プレイヤーからのメッセージ本文です。管理者が全文を読めるようにしてください。',student_id:'2101',display_name:'テスト工場長',class_number:1,created_at:now-30000}
 ]},
 funds:{players,history:[]},
 'extra-slots':{slots:[]},
 'tap-monitor':{players:[]},
 'tap-monitor-events':{events:[]},
 online:{current:0,samples:[],peak:0},
 hybrid:{},
 bank:{settings:{enabled:false,demand_bps:500,lend_bps:500,borrow_bps:500,limit:'10000',brackets:[],exponential:null},offers:[]}
};
const errors=[];
(async()=>{
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
try{
 for(const viewport of [{width:1440,height:900},{width:390,height:844},{width:360,height:640}]){
  const page=await browser.newPage({viewport});
  page.on('pageerror',e=>errors.push(viewport.width+': '+e.message));
  page.on('dialog',d=>d.dismiss());
  const posted=[];
  await page.route('**/api/admin/**',async route=>{
   const request=route.request();
   const name=request.url().split('/api/admin/')[1].split('?')[0];
   if(request.method()==='POST'){
    let body={};
    try{body=request.postDataJSON();}catch(e){}
    posted.push({name,body});
    if(name==='funds'){
     return await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
      display_name:'テスト工場長',kind:body.kind,student_id:body.student_id,
      amount:body.amount,before_cash:'1000',after_cash:body.amount,
      already_applied:false
     })});
    }
   }
   await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload[name]||{})});
  });
  await page.goto('http://127.0.0.1:8768/admin.html',{waitUntil:'domcontentloaded'});
  await page.waitForSelector('#dashboard:not([hidden])',{timeout:15000});
  await page.waitForFunction(()=>Boolean(window.__adminDashboardSnapshot),{timeout:10000});
  const metrics=async()=>page.evaluate(()=>({
    doc:document.documentElement.scrollHeight,
    body:document.body.scrollHeight,
    view:window.innerHeight,
    panel:Math.ceil(document.querySelector('#panel-overview').getBoundingClientRect().bottom),
    active:document.body.classList.contains('console-active')
  }));
  const initial=await metrics();
  assert.equal(initial.active,true,'Dashboard fixed-viewport mode activated');
  assert.ok(initial.doc<=initial.view+3,JSON.stringify({viewport,initial}));
  assert.ok(initial.body<=initial.view+3,JSON.stringify({viewport,initial}));
  const goto=async name=>{
   if(viewport.width<=740){
    await page.click('#admin-mobile-toggle');
    await page.click('#admin-mobile-options [data-mobile-target="'+name+'"]');
   }
   else await page.click('[data-panel="'+name+'"]');
   await page.waitForFunction(name=>{
     const p=document.querySelector('#panel-'+name);
     return p&&!p.hidden;
   },name);
  };
  await goto('analysis');
  assert.ok(await page.locator('#analytics-content .an-chart').count()>=2,'Charts loaded on first analysis view');
  assert.ok(await page.locator('#insight-lab .lab-svg').count()===1,'One large insight chart visible');
  await page.locator('#insight-lab .lab-tab[data-category="market"]').click();
  assert.equal(await page.locator('.lab-timeline').isVisible(),true,'Historical market slider available');
  const timeBefore=await page.locator('.lab-time-label').innerText();
  await page.locator('.lab-slider').evaluate(e=>{e.value='0';e.dispatchEvent(new Event('input',{bubbles:true}));});
  const timeAfter=await page.locator('.lab-time-label').innerText();
  assert.notEqual(timeBefore,timeAfter,'Historical slider moves to earlier settlement');
  await page.locator('.lab-play').click();
  assert.ok((await page.locator('.lab-play').innerText()).includes('停止'),'Animation playback starts');
  await page.locator('.lab-play').click();
  assert.ok((await page.locator('.lab-play').innerText()).includes('再生'),'Animation can be paused');
  await page.locator('#insight-lab .lab-tab[data-category="assets"]').click();
  assert.equal(await page.locator('.lab-timeline').isVisible(),false,'Current-state analytics do not falsely show history');
  const chartScroll=await page.evaluate(()=>document.documentElement.scrollHeight);
  assert.ok(chartScroll<=viewport.height+3);
  await goto('messages');
  await page.locator('#message-list button').first().click();
  assert.ok((await page.locator('#message-detail').innerText()).includes('プレイヤーからのメッセージ本文'),'Full message readable');
  await goto('notices');
  await page.locator('#notice-list button').first().click();
  assert.ok((await page.locator('#notice-detail').innerText()).includes('配信本文'),'Notice text readable');
  await page.locator('[data-compose=yes]').click();
  assert.equal(await page.locator('#announcement-form textarea').count(),1);
  await goto('funds');
  assert.equal(await page.locator('#funds-form #funds-amount').count(),1,'Original funding input preserved');
  await page.locator('#funds-amount').fill('1e1000');
  assert.equal(await page.locator('#funds-amount').inputValue(),'1e1000','Large amount accepts original notation');
  await page.locator('#funds-target').fill('2101');
  await page.locator('#funds-form button[type="submit"]').click();
  assert.equal(await page.locator('#funds-confirm').isVisible(),true,'Original confirmation opens');
  assert.ok((await page.locator('#funds-confirm-message').innerText()).includes('10'),'Huge exponent represented in confirmation');
  await page.locator('#funds-apply').click();
  await page.waitForFunction(()=>document.querySelector('#funds-status')?.textContent?.includes('実行完了'));
  const request=posted.find(x=>x.name==='funds');
  assert.ok(request,'Original funds processing endpoint received POST');
  assert.equal(request.body.student_id,'2101','Student selection unchanged');
  assert.equal(request.body.amount,'1'+'0'.repeat(1000),'Exact 10^1000 amount survived UI to API without rounding');
  assert.ok(typeof request.body.key==='string'&&request.body.key.length>10,'Idempotency key included');
  await goto('bank');
  assert.equal(await page.locator('#bank-config [name=limit]').count(),1);
  await goto('operations');
  assert.equal(await page.locator('#pause-game').count(),1);
  await goto('advanced');
  assert.equal(await page.locator('#player-form').count(),1);
  assert.equal(await page.locator('#extra-slot-form').count(),1);
  await page.screenshot({path:'/tmp/admin-'+viewport.width+'x'+viewport.height+'.png',fullPage:false});
  const last=await metrics();
  assert.ok(last.doc<=last.view+3,JSON.stringify({viewport,last}));
  console.log('PASS '+viewport.width+'x'+viewport.height+' main viewport fixed, charts, inboxes, finance, bank, operations');
  await page.close();
 }
 if(errors.length)throw Error('Browser runtime errors: '+errors.join(' | '));
 console.log('PASS: no browser runtime errors in tested responsive viewports');
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
