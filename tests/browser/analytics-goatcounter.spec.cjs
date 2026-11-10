const {test,expect}=require('./fixtures.cjs');
// Analytics proposal (10-nov-2026): GoatCounter behind data/analytics.json; nothing loads unless enabled AND
// privacy_approved AND the endpoint is https://<code>.goatcounter.com/count. Only the path (no query, no hash) and
// fixed event names are ever handed to the counter.
const cfg=extra=>({enabled:true,privacy_approved:true,provider:'goatcounter',goatcounter_endpoint:'https://alicanto.goatcounter.com/count',project_key:'',host:'https://us.i.posthog.com',...extra});
async function watch(page,config){
 const hits=[];
 if(config)await page.route('**/data/analytics.json',r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(config)}));
 // Stub count.js: records the path the page would count and every event, without any network beyond the stub.
 await page.route('https://gc.zgo.at/count.js',r=>{hits.push({script:r.request().url()});return r.fulfill({status:200,contentType:'text/javascript',
  body:"window.__gc=[];var s=window.goatcounter||{};window.__gc.push({pageview:typeof s.path==='function'?s.path():location.pathname,endpoint:document.currentScript&&document.currentScript.dataset.goatcounter});s.count=function(o){window.__gc.push(o)};window.goatcounter=s;"})});
 await page.route(/goatcounter\.com/,r=>{hits.push({counter:r.request().url()});return r.abort()});
 return hits;
}
test('committed config keeps analytics off: no counter script, no requests',async({page})=>{
 const c=await (await page.request.get('/data/analytics.json')).json();
 expect(c.enabled).toBe(false);expect(c.privacy_approved).toBe(false);expect(c.goatcounter_endpoint).toBe('');
 const hits=await watch(page,null);
 await page.goto('/datos.html');await expect(page.locator('#datosList .dx-row').first()).toBeVisible();
 await page.locator('[data-open-premium]').first().click();
 expect(hits).toEqual([]);
});
test('enabled without privacy approval, or with a foreign endpoint, never loads the counter',async({page})=>{
 for(const c of [cfg({privacy_approved:false}),cfg({goatcounter_endpoint:'https://evil.example.com/count'}),cfg({goatcounter_endpoint:'http://alicanto.goatcounter.com/count'})]){
  await page.unrouteAll({behavior:'ignoreErrors'});
  const hits=await watch(page,c);
  await page.goto('/datos.html?abrir=1#sig-x');await expect(page.locator('#datosList .dx-row').first()).toBeVisible();
  expect(hits).toEqual([]);
 }
});
test('approved config counts the path without query or hash and only fixed event names',async({page})=>{
 const hits=await watch(page,cfg());
 await page.goto('/datos.html?abrir=1&desde=x#sig-secret');
 await expect.poll(()=>page.evaluate(()=>(window.__gc||[]).length)).toBeGreaterThan(0);
 const first=(await page.evaluate(()=>window.__gc))[0];
 expect(first).toEqual({pageview:'/datos.html',endpoint:'https://alicanto.goatcounter.com/count'});
 await page.locator('[data-open-premium]').first().click();
 await expect.poll(()=>page.evaluate(()=>window.__gc.filter(x=>x.event).map(x=>x.path))).toContain('evento/premium_cta');
 for(const e of (await page.evaluate(()=>window.__gc)).filter(x=>x.event)){
  expect(Object.keys(e).sort()).toEqual(['event','path','title']);expect(e.path).toMatch(/^evento\/[a-z_]+$/);
 }
 expect(hits.filter(h=>h.counter)).toEqual([]);
 expect(hits.map(h=>h.script)).toEqual(['https://gc.zgo.at/count.js']);
});
