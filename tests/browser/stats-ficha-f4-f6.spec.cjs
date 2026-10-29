const {test,expect,selectPeriod}=require('./fixtures.cjs');
const fs=require('node:fs');
const path=require('node:path');

// F4 (GES) and F6 (Boletín IP) fichas at 390 and 1440 px: Option-B row actions, themed tabs, collapsed notes,
// 'Compartir informe' deep link, no horizontal overflow. Cards come from tests/fixtures/stats_fichas (fixture hashes;
// F4 values are synthetic test values, F6 values are the verified N°2-2026 reading).
const SHOTS=process.env.ALICANTO_SHOTS_DIR||'artifacts';
for(const [slug,tabs,kpis] of [['f4_ges',['Totales','Top problemas','Fonasa vs Isapre','Tendencia trimestral'],4],
                               ['f6_prestadores',['Acreditación','Mediación','Reclamos','RNPI'],4]]){
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
  await expect(body.locator('.sf-kpi')).toHaveCount(kpis);
  expect(await body.locator('[role=tab]').evaluateAll(xs=>xs.map(x=>x.textContent.trim()))).toEqual(tabs);
  await expect(body.locator('details.sf-notes')).not.toHaveAttribute('open','');
  await expect(body.locator('.sf-reading')).toHaveCount(0);  // no Lectura without a model run
  await expect(body).not.toContainText('Por qué importa');
  // Every tab opens and every SVG label stays inside its viewBox (no clipped values at 390 px).
  const inside=()=>page.evaluate(()=>[...document.querySelectorAll('#detailBody .sf-panel:not([hidden]) svg')].every(s=>{const vb=s.viewBox.baseVal;return [...s.querySelectorAll('text')].every(t=>{const b=t.getBBox();return b.x>=-1&&b.x+b.width<=vb.width+1})}));
  for(const name of tabs){await body.getByRole('tab',{name}).click();await expect(body.locator('.sf-panel:not([hidden])')).toBeVisible();expect(await inside(),name).toBeTruthy()}
  await body.getByRole('tab',{name:tabs[0]}).click();
  const charts=body.locator('.sf-panel:not([hidden]) .sf-chart');
  expect(await charts.count()).toBeGreaterThan(0);
  await charts.first().locator('summary').click();
  await expect(charts.first().locator('table tbody tr').first()).toBeVisible();
  await charts.first().locator('summary').click();
  for(const loc of [body.locator('[role=tab]').first(),body.locator('.sf-share')]){const box=await loc.boundingBox();expect(box.height).toBeGreaterThanOrEqual(44)}
  await body.locator('.sf-share').click();
  await expect(body.locator('.sf-share-status')).toHaveText('Enlace copiado.');
  expect(await page.evaluate(()=>window.__copied[0])).toMatch(new RegExp(`/data/fichas/${slug}\\.html$`));
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  expect(await page.evaluate(()=>{const d=document.getElementById('signalDetail');return d.scrollWidth<=d.clientWidth+1})).toBeTruthy();
  fs.mkdirSync(SHOTS,{recursive:true});
  await page.screenshot({path:path.join(SHOTS,`${slug}-${test.info().project.name}.png`),fullPage:false});
  await body.locator('.sf-tabs').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(SHOTS,`${slug}-${test.info().project.name}-tabs.png`),fullPage:false});
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
  const check=()=>page.evaluate(()=>[...document.querySelectorAll('#detailBody .sf-panel:not([hidden]) svg')].map(s=>{
   const vb=s.viewBox.baseVal,texts=[...s.querySelectorAll('text')],inside=texts.every(t=>{const b=t.getBBox();return b.x>=-1&&b.x+b.width<=vb.width+1});
   const xl=[...s.querySelectorAll('text.sf-xlab')].map(t=>t.getBBox()).sort((a,b)=>a.x-b.x);
   return {inside,overlap:xl.some((b,i)=>i&&b.x<xl[i-1].x+xl[i-1].width)}}));
  for(const name of tabs){
   await body.getByRole('tab',{name}).click();await expect(body.locator('.sf-panel:not([hidden])')).toBeVisible();
   for(const r of await check()){expect(r.inside,name).toBeTruthy();expect(r.overlap,name).toBeFalsy()}
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  expect(await page.evaluate(()=>{const d=document.getElementById('signalDetail');return d.scrollWidth<=d.clientWidth+1})).toBeTruthy();
  fs.mkdirSync(SHOTS,{recursive:true});
  await page.screenshot({path:path.join(SHOTS,`${slug}-320.png`),fullPage:false});
 });
}
