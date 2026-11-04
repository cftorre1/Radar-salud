const {test,expect}=require('./fixtures.cjs');
const fs=require('node:fs');
const path=require('node:path');

// F2 FEFI v5 (3-nov-2026) at 390 and 1440 px: siniestralidad separada (prestaciones · SIL, this year against the same
// months a year earlier) and the new 'Licencias (SIL)' topic. The card is tests/fixtures/stats_fichas/f2_financieras.card.json,
// built offline from the committed FEFI capture (python tests/stats_ficha_fixtures.py f2).
const SHOTS=process.env.ALICANTO_SHOTS_DIR||'artifacts';
const TABS=['Resultados','Ingresos','Costo de ventas','Gastos de administración','Siniestralidad','Licencias (SIL)'];
const card=()=>JSON.parse(fs.readFileSync('tests/fixtures/stats_fichas/f2_financieras.card.json','utf8'));
const shot=async(page,name)=>{fs.mkdirSync(SHOTS,{recursive:true});await page.screenshot({path:path.join(SHOTS,`f2_${test.info().project.name==='mobile'?390:1440}_${name}.png`),fullPage:false})};
const inside=page=>page.evaluate(()=>[...document.querySelectorAll('#detailBody .sf-tpanel:not([hidden]) svg[role=img], #detailBody .sf-index svg[role=img]')].map(s=>{
 const vb=s.viewBox.baseVal;return {chart:s.closest('[data-chart]')?.dataset.chart||'spark',bad:[...s.querySelectorAll('text')].filter(t=>{const b=t.getBBox();return b.x<-1||b.x+b.width>vb.width+1}).map(t=>t.textContent)}}));
const noOverflow=page=>page.evaluate(()=>{const d=document.getElementById('signalDetail');return document.documentElement.scrollWidth<=innerWidth+1&&d.scrollWidth<=d.clientWidth+1});

test('F2 ficha shows the siniestralidad split and the SIL topic',async({page})=>{
 const c=card(),f=c.stats_ficha;
 await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-10-12',generated_at:'2026-10-12T12:00:00Z',signals:[c]}}));
 await page.goto('/');
 const row=page.locator('article[data-card]').filter({hasText:c.title});
 await expect(row).toHaveCount(1);
 await row.locator('[data-detail]').first().click();
 const body=page.locator('#detailBody');
 await expect(body.locator('.sf-headline')).toHaveText(f.headline);
 expect(await body.locator('.sf-row-label').evaluateAll(xs=>xs.map(x=>x.firstChild.textContent.trim()))).toEqual(TABS);
 expect(await body.locator('.sf-row-line').evaluateAll(xs=>xs.map(x=>x.textContent))).toEqual(f.tabs.map(t=>t.index_line));
 await expect(body.locator('.sf-row-line').first()).toContainText(/con pérdida$/);
 expect(f.kpis.find(k=>k.id==='siniestralidad').lines[0]).toMatch(/^prestaciones \d+,\d% · SIL \d+,\d%$/);
 await expect(body.locator('.sf-reading')).toHaveCount(0);  // Lectura off for F2: no model call
 await expect(body).not.toContainText(/se explica por|debido a|gracias a/i);
 for(const r of await inside(page))expect(r.bad,r.chart).toEqual([]);
 expect(await noOverflow(page)).toBeTruthy();
 await shot(page,'index');
 // Siniestralidad: hero = the two components and the total, dot (this year) vs ring (same months a year earlier).
 await body.locator('.sf-row').nth(4).click();
 await expect(body.locator('.sf-pick-label')).toHaveText('Siniestralidad');
 const panel=body.locator('.sf-tpanel:not([hidden])');
 const hero=panel.locator('[data-chart="f2-siniestralidad-componentes"]');
 await expect(hero).toBeVisible();
 await expect(hero.locator('svg circle')).toHaveCount(6);  // 3 rows × (dot + ring)
 for(const r of await inside(page))expect(r.bad,r.chart).toEqual([]);
 expect(await noOverflow(page)).toBeTruthy();
 await shot(page,'siniestralidad');
 // Per Isapre, prestaciones and SIL side by side in 'Ver datos'.
 const by=panel.locator('[data-chart="f2-siniestralidad-isapres"]');
 await by.locator('summary').click();
 expect(await by.locator('thead th').allTextContents()).toEqual(['Isapre','Prestaciones','SIL','Total','Ingresos (MM$)']);
 await expect(by.locator('tbody tr').last()).toContainText('Sistema sin Esencial');
 expect(await noOverflow(page)).toBeTruthy();
 await by.scrollIntoViewIfNeeded();
 await shot(page,'siniestralidad_tabla');
 // Licencias (SIL): SIL over ingresos by Isapre (dot vs ring) and SIL over cotizaciones with its definition.
 await body.locator('[data-sf-step="1"]').click();
 await expect(body.locator('.sf-pick-label')).toHaveText('Licencias (SIL)');
 await expect(panel.locator('[data-chart="f2-sil-isapres"]')).toBeVisible();
 const cot=panel.locator('[data-chart="f2-sil-cotizaciones"]');
 await expect(cot.locator('.sf-src')).toContainText('cotización legal más cotización adicional voluntaria');
 for(const r of await inside(page))expect(r.bad,r.chart).toEqual([]);
 expect(await noOverflow(page)).toBeTruthy();
 await page.evaluate(()=>{document.getElementById('signalDetail').scrollTop=0});
 await shot(page,'sil');
 await cot.scrollIntoViewIfNeeded();
 await shot(page,'sil_cotizaciones');
});
