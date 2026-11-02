const {test,expect,selectPeriod}=require('./fixtures.cjs');
const fs=require('node:fs');
const path=require('node:path');

// F4 (GES) and F6 (Boletín IP) fichas at 390 and 1440 px: Option-B row actions, themed tabs, collapsed notes,
// 'Compartir informe' deep link, no horizontal overflow. Cards come from tests/fixtures/stats_fichas (fixture hashes;
// F4 values are synthetic test values, F6 values are the verified N°2-2026 reading).
const SHOTS=process.env.ALICANTO_SHOTS_DIR||'artifacts';
for(const [slug,tabs,kpis] of [['f4_ges',['Totales','Top problemas','Fonasa vs Isapre','Tendencia trimestral'],0],
                               ['f6_prestadores',['Acreditación','Mediación','Reclamos','RNPI'],0]]){
 test(`${slug} ficha opens with tabs, charts and a share link`,async({page})=>{
  const card=JSON.parse(fs.readFileSync(`tests/fixtures/stats_fichas/${slug}.card.json`,'utf8'));
  await page.clock.setFixedTime(new Date('2026-10-29T12:00:00-03:00'));
  await page.addInitScript(()=>{Object.defineProperty(navigator,'share',{value:undefined,configurable:true});
   window.__copied=[];Object.defineProperty(navigator,'clipboard',{value:{writeText:async t=>{window.__copied.push(t)}},configurable:true})});
  await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-10-29',generated_at:'2026-10-29T12:00:00Z',signals:[card]}}));
  await page.goto('/');
  await selectPeriod(page,'90');  // the Boletín (3 ago) is older than the default 30-day window
  const row=page.locator('article[data-card]').filter({hasText:card.title});
  await expect(row).toHaveCount(1);
  expect(await row.locator('.row-acts .act').evaluateAll(xs=>xs.map(a=>a.textContent.trim()))).toEqual(['Ver ficha','Fuente original','Compartir']);
  await expect(row.locator('.act-share')).toHaveAttribute('data-share-url',card.share_url);
  await row.locator('[data-detail]').first().click();
  const body=page.locator('#detailBody');
  await expect(body.locator('.sf-headline')).toHaveText(card.stats_ficha.headline);
  // Index → topic (Dirección 29-oct, generic for every family): one row per topic with the builder's index line.
  await expect(body.locator('.sf-index')).toBeVisible();await expect(body.locator('.sf-kpi:visible')).toHaveCount(kpis);
  expect(await body.locator('.sf-row-label').evaluateAll(xs=>xs.map(x=>x.firstChild.textContent.trim()))).toEqual(tabs);
  expect(await body.locator('.sf-row-line').evaluateAll(xs=>xs.map(x=>x.textContent))).toEqual(card.stats_ficha.tabs.map(t=>t.index_line));
  await expect(body.locator('details.sf-notes')).not.toHaveAttribute('open','');
  await expect(body.locator('.sf-reading')).toHaveCount(0);  // no Lectura without a model run
  await expect(body).not.toContainText('Por qué importa');
  // Every topic opens (› steps through them) and every SVG label stays inside its viewBox (no clipped values at 390 px).
  const inside=()=>page.evaluate(()=>[...document.querySelectorAll('#detailBody .sf-tpanel:not([hidden]) svg[role=img]')].every(s=>{const vb=s.viewBox.baseVal;return [...s.querySelectorAll('text')].every(t=>{const b=t.getBBox();return b.x>=-1&&b.x+b.width<=vb.width+1})}));
  await body.locator('.sf-row').first().click();
  for(const [i,name] of tabs.entries()){if(i)await body.locator('[data-sf-step="1"]').click();await expect(body.locator('.sf-pick-label')).toHaveText(name);await expect(body.locator('.sf-tpanel:not([hidden])')).toBeVisible();expect(await inside(),name).toBeTruthy()}
  await body.locator('.sf-pick').click();await body.locator('[role=option]').nth(1).click();
  await expect(body.locator('.sf-pick-label')).toHaveText(tabs[0]);
  const charts=body.locator('.sf-tpanel:not([hidden]) .sf-chart');
  expect(await charts.count()).toBeGreaterThan(0);
  await charts.first().locator('summary').click();
  await expect(charts.first().locator('table tbody tr').first()).toBeVisible();
  await charts.first().locator('summary').click();
  // Header as in the approved mockup (Dirección 29-oct): share icon in the top bar, no follow chips, source and read
  // toggle at the foot, and the bar's back button reads 'Todos los temas' in topic mode.
  const share=page.locator('#signalDetail .detail-top .sf-share');
  await expect(share).toHaveAttribute('aria-label','Compartir informe');await expect(body.locator('.sf-share')).toHaveCount(0);
  await expect(page.locator('#signalDetail .follow-chip')).toHaveCount(0);await expect(page.locator('#detailActs .act')).toHaveCount(0);
  await expect(page.locator('#closeDetail')).toContainText('Todos los temas');
  await expect(body.locator('#detailFoot #detailRead')).toHaveText('Marcar no leída');
  expect(await body.locator('#detailFoot').locator('a,button').evaluateAll(xs=>xs.map(x=>x.textContent.trim()))).toEqual(['Fuente original ↗','Marcar no leída']);
  expect(await body.locator('.sf-meta li').count()).toBe(2);
  for(const loc of [body.locator('.sf-pick'),share]){const box=await loc.boundingBox();expect(box.height).toBeGreaterThanOrEqual(44)}
  await share.click();
  await expect(page.locator('#signalDetail .sf-share-status')).toHaveText('Enlace copiado.');
  expect(await page.evaluate(()=>window.__copied[0])).toMatch(new RegExp(`/data/fichas/${slug}\\.html$`));
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  expect(await page.evaluate(()=>{const d=document.getElementById('signalDetail');return d.scrollWidth<=d.clientWidth+1})).toBeTruthy();
  fs.mkdirSync(SHOTS,{recursive:true});
  await page.screenshot({path:path.join(SHOTS,`${slug}-${test.info().project.name}.png`),fullPage:false});
  await page.screenshot({path:path.join(SHOTS,`${slug}-${test.info().project.name}-topic.png`),fullPage:false});
 });
}

// 320 px (smallest supported phone): every tab fits, SVG labels stay inside their viewBox and x-axis labels never overlap.
for(const [slug,tabs] of [['f4_ges',['Totales','Top problemas','Fonasa vs Isapre','Tendencia trimestral']],
                          ['f6_prestadores',['Acreditación','Mediación','Reclamos','RNPI']]]){
 test(`${slug} ficha fits a 320 px screen`,async({page})=>{
  test.skip(test.info().project.name!=='mobile','320 px runs once, in the mobile project');
  await page.setViewportSize({width:320,height:700});
  const card=JSON.parse(fs.readFileSync(`tests/fixtures/stats_fichas/${slug}.card.json`,'utf8'));
  await page.clock.setFixedTime(new Date('2026-10-29T12:00:00-03:00'));
  await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-10-29',generated_at:'2026-10-29T12:00:00Z',signals:[card]}}));
  await page.goto('/');
  await selectPeriod(page,'90');
  const row=page.locator('article[data-card]').filter({hasText:card.title});
  await expect(row).toHaveCount(1);
  await row.locator('[data-detail]').first().click();
  const body=page.locator('#detailBody');
  await expect(body.locator('.sf-headline')).toHaveText(card.stats_ficha.headline);
  const check=()=>page.evaluate(()=>[...document.querySelectorAll('#detailBody .sf-tpanel:not([hidden]) svg[role=img]')].map(s=>{
   const vb=s.viewBox.baseVal,texts=[...s.querySelectorAll('text')],inside=texts.every(t=>{const b=t.getBBox();return b.x>=-1&&b.x+b.width<=vb.width+1});
   const xl=[...s.querySelectorAll('text.sf-xlab')].map(t=>t.getBBox()).sort((a,b)=>a.x-b.x);
   return {inside,overlap:xl.some((b,i)=>i&&b.x<xl[i-1].x+xl[i-1].width)}}));
  await body.locator('.sf-row').first().click();
  for(const [i,name] of tabs.entries()){
   if(i)await body.locator('[data-sf-step="1"]').click();await expect(body.locator('.sf-pick-label')).toHaveText(name);await expect(body.locator('.sf-tpanel:not([hidden])')).toBeVisible();
   for(const r of await check()){expect(r.inside,name).toBeTruthy();expect(r.overlap,name).toBeFalsy()}
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  expect(await page.evaluate(()=>{const d=document.getElementById('signalDetail');return d.scrollWidth<=d.clientWidth+1})).toBeTruthy();
  fs.mkdirSync(SHOTS,{recursive:true});
  await page.screenshot({path:path.join(SHOTS,`${slug}-320.png`),fullPage:false});
 });
}

// Compact header at 390×844 with DejaVu Sans, generic for every family: the first two index rows above the fold, and
// the first topic's hero chart top half above the fold even with the ficha at its top.
for(const slug of ['f4_ges','f6_prestadores']){
 test(`${slug} compact header shows index rows and the hero chart above the fold at 390×844`,async({page})=>{
  test.skip(test.info().project.name!=='mobile','390×844 runs once, in the mobile project');
  await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:'reduce'});
  const card=JSON.parse(fs.readFileSync(`tests/fixtures/stats_fichas/${slug}.card.json`,'utf8'));
  await page.clock.setFixedTime(new Date('2026-10-29T12:00:00-03:00'));
  await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-10-29',generated_at:'2026-10-29T12:00:00Z',signals:[card]}}));
  await page.goto('/');await selectPeriod(page,'90');
  await page.addStyleTag({content:'*,svg text{font-family:"DejaVu Sans",sans-serif!important}'});
  await page.locator('article[data-card]').filter({hasText:card.title}).locator('[data-detail]').first().click();
  const body=page.locator('#detailBody');await expect(body.locator('.sf-index')).toBeVisible();
  const m=sel=>page.evaluate(sel=>{const d=document.getElementById('signalDetail'),bottom=Math.min(innerHeight,d.getBoundingClientRect().bottom);
   return {bottom,scroll:d.scrollTop,bar:d.querySelector('.detail-top').getBoundingClientRect().height,els:[...document.querySelectorAll(sel)].filter(e=>e.offsetParent).map(e=>{const b=e.getBoundingClientRect();return {bottom:b.bottom,mid:b.top+b.height/2}})}},sel);
  const ix=await m('#detailBody .sf-row');
  expect(ix.scroll).toBe(0);expect(ix.bar).toBeLessThanOrEqual(52);for(const r of ix.els)expect(r.bottom).toBeLessThanOrEqual(ix.bottom);
  await body.locator('.sf-row').first().click();await expect(body.locator('.sf-topic')).toBeVisible();
  await page.evaluate(()=>{document.getElementById('signalDetail').scrollTop=0});
  const t=await m('#detailBody .sf-tpanel:not([hidden]) .sf-hero .sf-chart');
  expect(t.scroll).toBe(0);expect(t.els[0].mid).toBeLessThanOrEqual(t.bottom);
 });
}
