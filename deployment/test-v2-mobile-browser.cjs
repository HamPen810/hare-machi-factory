/* End-to-end browser simulation for mobile V2 read/preview UI. No real users or DB. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base='http://127.0.0.1:8769/v2.html';
const balances={format:'S1',mode:'read-only',authoritative:'legacy_numeric',cash:'S1:1@7600',
 stock:[{product:'white',quantity:'S1:3@0',work:'S1:'},{product:'sea',quantity:'S1:1@5000',work:'S1:'}]};
const preview={mode:'simulation_only',authoritative:false,order_placed:false,transaction_saved:false,
 fee_model:'illustrative_basis_points',format:'S1',product:'white',quantity:'S1:1@1000000000',
 unit_price:'S1:2@1000',gross:'S1:2@1000001000',illustrative_fee:'S1:2500@1000000996',
 illustrative_debit:'S1:2@1000001000,2500@1000000996',
 current_cash:'S1:1@7600',current_stock:'S1:3@0',
 cash_after_preview:'S1:1@7600,-2@1000001000,-2500@1000000996',
 stock_after_preview:'S1:1@1000000000,3@0'};
async function main(){
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const errors=[];
 try{
  for(const viewport of [{width:390,height:844},{width:360,height:640},{width:1280,height:900}]){
   const page=await browser.newPage({viewport});
   page.on('pageerror',e=>errors.push(viewport.width+':'+e.message));
   const calls=[];
   await page.route('**/api/v2/**',async route=>{
    const req=route.request();
    calls.push({url:req.url(),method:req.method(),body:req.postData()});
    if(req.url().endsWith('/balances')){
     return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(balances)});
    }
    if(req.url().endsWith('/preview')){
     return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(preview)});
    }
    return route.fulfill({status:404,contentType:'application/json',body:'{}'});
   });
   await page.goto(base,{waitUntil:'domcontentloaded'});
   await page.locator('#cash').waitFor({state:'visible',timeout:10000});
   assert.ok((await page.locator('#cash').textContent()).includes(balances.cash));
   assert.ok((await page.locator('#v2-stock-chart .v2-stock-entry').count())===2,'Stock magnitude chart displayed');
   const products=await page.locator('#product option').allTextContents();
   assert.deepEqual(products,['white','sea']);
   assert.equal(await page.locator('#submit').isDisabled(),false);
   await page.locator('#quantity').fill('1e1000000000');
   await page.locator('#unit-price').fill('2e1000');
   await page.locator('#fee').fill('12.50');
   await page.locator('#submit').click();
   await page.locator('#results:not([hidden])').waitFor({timeout:10000});
   const posted=calls.filter(x=>x.method==='POST');
   assert.equal(posted.length,1,'One simulated POST, no actual trade endpoint');
   assert.ok(posted[0].url.endsWith('/api/v2/preview'));
   assert.deepEqual(JSON.parse(posted[0].body),{
      product:'white',quantity:'1e1000000000',unit_price:'2e1000',fee_bps:1250
   });
   assert.ok((await page.locator('#results').textContent()).includes('S1:2@1000001000'));
   assert.ok((await page.locator('body').textContent()).includes('試算専用'));
   const geometry=await page.evaluate(()=>({width:document.documentElement.scrollWidth,inner:innerWidth}));
   assert.ok(geometry.width<=geometry.inner+2,'Unwanted horizontal scrolling: '+JSON.stringify({viewport,geometry}));
   await page.screenshot({path:'/tmp/v2-ui-'+viewport.width+'.png',fullPage:true});
   await page.close();
  }
  const unauth=await browser.newPage({viewport:{width:390,height:844}});
  unauth.on('pageerror',e=>errors.push('unauth:'+e.message));
  await unauth.route('**/api/v2/balances',route=>route.fulfill({
   status:401,contentType:'application/json',body:JSON.stringify({error:'ログインしてください。'})
  }));
  await unauth.goto(base,{waitUntil:'domcontentloaded'});
  await unauth.locator('#error:not([hidden])').waitFor({timeout:10000});
  assert.ok((await unauth.locator('#error').textContent()).includes('ログイン'));
  assert.equal(await unauth.locator('#submit').isDisabled(),true);
  await unauth.close();
  assert.deepEqual(errors,[],errors.join('\n'));
  console.log('V2_MOBILE_CHROMIUM_BROWSER_SIMULATION_PASSED');
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
