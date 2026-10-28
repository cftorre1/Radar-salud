const {test,expect}=require('./fixtures.cjs');
const fs=require('node:fs');

// F1 statistics ficha (Dirección 28-oct-2026) at 390 and 1440 px: Insight A order, tabs, data tables,
// no horizontal overflow, and "Compartir informe" with the copy-link fallback.
test('F1 ficha opens with tabs, readable charts and a share link',async({page})=>{
 const snap=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8'));
 const card=snap.signals.find(s=>s.stats_ficha);
 expect(card.data_period).toBe('2026-08');
 await page.addInitScript(()=>{Object.defineProperty(navigator,'share',{value:undefined,configurable:true});
  window.__copied=[];Object.defineProperty(navigator,'clipboard',{value:{writeText:async t=>{window.__copied.push(t)}},configurable:true})});
 await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-10-12',generated_at:'2026-10-12T12:00:00Z',signals:[card]}}));
 await page.goto('/');
 const row=page.locator('article[data-card]').filter({hasText:card.title});
 await expect(row).toHaveCount(1);
 await expect(row).toContainText('Datos a 2026-08');
 await row.locator('[data-detail]').first().click();
 const body=page.locator('#detailBody');
 await expect(body.locator('.sf-headline')).toHaveText(card.stats_ficha.headline);
 await expect(body.locator('.sf-kpi')).toHaveCount(4);
 await expect(body.locator('[role=tab]')).toHaveCount(5);
 const visibleCharts=body.locator('.sf-panel:not([hidden]) .sf-chart');
 await expect(visibleCharts).toHaveCount(2);
 await expect(visibleCharts.first().locator('svg[role=img]')).toHaveAttribute('aria-label',/Ago −814/);
 await visibleCharts.first().locator('summary').click();
 await expect(visibleCharts.first().locator('table tbody tr')).toHaveCount(8);
 await body.getByRole('tab',{name:'Por Isapre'}).click();
 await expect(body.locator('.sf-panel:not([hidden])')).toContainText('Participación entre las Isapres abiertas');
 await body.getByRole('tab',{name:'Por Isapre'}).press('ArrowRight');
 await expect(body.getByRole('tab',{name:'Cotizantes y cargas'})).toHaveAttribute('aria-selected','true');
 await expect(body.getByRole('tab',{name:'Cotizantes y cargas'})).toBeFocused();
 await body.getByRole('tab',{name:/Regional/}).click();
 await expect(body.locator('.sf-panel:not([hidden]) .sf-links a').first()).toHaveAttribute('href',/a-nivel-regional-agosto-2026/);
 await expect(body.locator('.sf-watch li')).toHaveCount(2);
 await expect(body.locator('.sf-facts')).toHaveCount(0);
 // Notes and sources stay behind one collapsed toggle until opened.
 await expect(body.locator('details.sf-notes')).not.toHaveAttribute('open','');
 await body.locator('details.sf-notes summary').click();
 await expect(body.locator('.sf-notes')).toContainText('denominador');
 // Touch targets for tabs and the share action.
 for(const loc of [body.locator('[role=tab]').first(),body.locator('.sf-share')]){const box=await loc.boundingBox();expect(box.height).toBeGreaterThanOrEqual(44)}
 await body.locator('.sf-share').click();
 await expect(body.locator('.sf-share-status')).toHaveText('Enlace copiado.');
 expect(await page.evaluate(()=>window.__copied[0])).toMatch(/\/data\/fichas\/f1_cartera\.html$/);
 // No horizontal page or dialog overflow (the tab strip scrolls inside itself).
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 expect(await page.evaluate(()=>{const d=document.getElementById('signalDetail');return d.scrollWidth<=d.clientWidth+1})).toBeTruthy();
 await body.getByRole('tab',{name:'Cartera total'}).click();
 await page.screenshot({path:`artifacts/stats-ficha-${test.info().project.name}.png`,fullPage:false});
});

test('the F1 share page redirects to the ficha deep link',async({page})=>{
 const snap=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8'));
 const card=snap.signals.find(s=>s.stats_ficha);
 await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-10-12',generated_at:'2026-10-12T12:00:00Z',signals:[card]}}));
 await page.goto('/data/fichas/f1_cartera.html');
 await page.waitForURL(/index\.html#sig-stats-ficha/);
 await expect(page.locator('article[data-card]').filter({hasText:card.title})).toHaveCount(1);
 // The share link opens the ficha detail, not just the row.
 await expect(page.locator('#signalDetail')).toBeVisible();
 await expect(page.locator('#detailBody .sf-headline')).toHaveText(card.stats_ficha.headline);
 expect(page.url()).not.toContain('abrir=1');
});

test('the withdrawn GES finding shows a dated public correction',async({page})=>{
 const snap=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8'));
 const ges=snap.signals.find(s=>s.statistical_view&&s.statistical_view.correction);
 expect(ges).toBeTruthy();
 // The GES release (14-oct) is after the suite's pinned fixture day; pin the clock to the correction day.
 await page.clock.setFixedTime(new Date('2026-10-28T12:00:00-03:00'));
 await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-10-28',generated_at:'2026-10-28T12:00:00Z',signals:[ges]}}));
 await page.goto('/');
 const row=page.locator('article[data-card]').filter({hasText:ges.title});
 await expect(row.locator('.correction-tag')).toHaveText(/Corregido el 28.oct/);
 await row.locator('[data-detail]').first().click();
 await expect(page.locator('#detailBody .stat-correction')).toContainText('Corregido el 28-oct:');
 await expect(page.locator('#detailBody')).not.toContainText('21 presenta');
});
