const { chromium } = require('/workspace/work/codex-h/implementation/node_modules/playwright');
const fs=require('node:fs'),crypto=require('node:crypto');
const repo='/workspace/work/codex-h/implementation',dir='/workspace/work/codex-h/reviewer';
const snapshot=JSON.parse(fs.readFileSync(repo+'/web/data/radar_today.json','utf8'));
const official=snapshot.signals.find(s=>s.source_url.includes('circular-if-n534'));
function fixture(extra={}){return {...official,event_date:'2026-10-12',source_url:'https://example.invalid/news/a',title:'Hecho independiente A',display_title:'Hecho independiente A',...extra}}
const findings=[];
function capture(name,x){ findings.push({name,...x});console.log(JSON.stringify(findings.at(-1))); }
(async()=>{
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
async function setup(signals,free={}){const ctx=await browser.newContext({viewport:{width:1440,height:900}}),page=await ctx.newPage(); await page.clock.install({time:new Date('2026-10-12T15:00:00Z')});await page.route('**/data/radar_today.json',r=>r.fulfill({json:{...snapshot,signals:typeof signals==='function'?signals():signals}}));await page.route('**/data/free_value.json',r=>r.fulfill({json:free}));await page.goto('http://127.0.0.1:8773/');await page.locator('[data-card]').first().waitFor();await page.evaluate(()=>AlicantoRead.ready);return {ctx,page}}
const hashes=Object.fromEntries(['web/read-state.js','web/app.js','web/public-sources.js','web/global.js'].map(p=>[p,crypto.createHash('sha256').update(fs.readFileSync(repo+'/'+p)).digest('hex')]));capture('source_hashes',{hashes});
{
 let signals=[fixture()];const {ctx,page}=await setup(()=>signals);const oldId=await page.locator('[data-card]').getAttribute('data-card');await page.evaluate(id=>AlicantoRead.set(id,true),oldId);signals=[fixture({event_date:'2026-10-11',read_aliases:[oldId]})];await page.reload();await page.locator('[data-card]').waitFor();const now=await page.locator('[data-card]').getAttribute('data-card');capture('corrected_date_alias',{oldId,newId:now,oldRead:await page.evaluate(id=>AlicantoRead.readSet.has(id),oldId),newRead:await page.evaluate(id=>AlicantoRead.readSet.has(id),now),briefCount:await page.locator('[data-brief-read]').count()});await ctx.close();
}
{
 const {ctx,page}=await setup([fixture(),fixture({source_url:'https://example.invalid/news/b',title:'Hecho independiente B',display_title:'Hecho independiente B'})]);const before=await page.locator('[data-brief-read]').count();await page.locator('[data-brief-read]').first().click();await page.waitForFunction(()=>document.querySelectorAll('[data-brief-read]').length===1);capture('envelope_focus',{before,after:await page.locator('[data-brief-read]').count(),active:await page.evaluate(()=>({tag:document.activeElement.tagName,id:document.activeElement.id,dataset:{...document.activeElement.dataset}}))});await ctx.close();
}
{
 const {ctx,page}=await setup([fixture(),fixture({source_url:'https://example.invalid/news/b',title:'Hecho independiente B',display_title:'Hecho independiente B'})]);await page.locator('[data-brief]').first().click();await page.locator('#signalDetail').waitFor({state:'visible'});await page.waitForFunction(()=>document.querySelectorAll('[data-brief-read]').length===1);await page.keyboard.press('Escape');await page.waitForTimeout(100);capture('detail_close_focus',{active:await page.evaluate(()=>({tag:document.activeElement.tagName,id:document.activeElement.id,dataset:{...document.activeElement.dataset}}))});await ctx.close();
}
{
 const w={id:'new-edition',approved_version_id:'approved-2',title:'Análisis editorial nuevo',insight_title:'Análisis editorial nuevo',event_date:'2026-10-12',freshness_anchor_date:'2026-10-12',expires_on:'2026-10-19',editorial_review_pass:true,source_name:'Fuente',source_url:'https://example.invalid/news/a',summary:'Análisis adicional material',read_aliases:[]};const {ctx,page}=await setup([fixture()],{weekly_insight:w});await page.waitForFunction(()=>document.querySelector('[data-special]'));const baseId=await page.locator('[data-card]').getAttribute('data-card');capture('weekly_independent_pending',{feedUnread:await page.locator('[data-card]:not(.read)').count(),basePending:await page.locator('[data-brief-read]').evaluateAll((xs,id)=>xs.filter(x=>x.dataset.briefRead===id).length,baseId),weeklyPending:await page.locator('[data-brief-read]').evaluateAll(xs=>xs.map(x=>x.dataset.briefRead))});await ctx.close();
}
{
 const {ctx,page}=await setup([fixture()]);await page.evaluate(()=>{HTMLDialogElement.prototype.showModal=function(){throw Error('blocked')}});await page.locator('[data-brief]').first().click();capture('failure_does_not_read',{read:await page.locator('[data-card]').evaluate(e=>e.classList.contains('read')),status:await page.locator('#readStatus').textContent()});await ctx.close();
}
{
 const ctx=await browser.newContext(),page=await ctx.newPage();await page.goto('http://127.0.0.1:8773/sources.html');await page.locator('.source-group').first().waitFor();capture('catalog_sanitized',{payload:await page.evaluate(async()=>{const p=await(await fetch('data/public_sources.json')).json();return {hasSourceError:p.sources.some(s=>s.error),sampleKeys:Object.keys(p.sources[0])}})});await ctx.close();
}
{
 const {ctx,page}=await setup([fixture()]);capture('backtop_at_top',{visible:await page.locator('#backTop').isVisible(),scrollY:await page.evaluate(()=>scrollY)});await ctx.close();
}
fs.writeFileSync(dir+'/ux-probe-results-'+(process.argv[2]||'initial')+'.json',JSON.stringify(findings,null,2));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
