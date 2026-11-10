const {test,expect}=require('./fixtures.cjs');
// Datos v2 mockup (staging only): real data from web/data, filters by Isapre / región / período, no horizontal scroll.
const noHScroll=page=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1);
test('Datos v2 mockup: KPIs, filters, comparator, profile, series and fichas',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto('/datos-v2.html');
 await expect(page.locator('#v2Kpis .v2-kpi')).toHaveCount(6);
 await expect(page.locator('#v2Kpis .v2-kpi[data-fam="F1"] .val')).toHaveText('2.486.683');
 await expect(page.locator('#seriesLargas .sl-chart svg')).toBeVisible();
 await expect(page.locator('#v2Fichas .v2-f-card')).toHaveCount(7);
 await expect(page.locator('#v2Fichas .v2-soon-r')).toHaveCount(2);
 expect(await noHScroll(page)).toBeTruthy();
 await page.selectOption('#fIsapre','Banmédica');
 await expect(page.locator('#v2Chips .v2-chip')).toContainText('Banmédica');
 await expect(page.locator('#v2Comp tr.sel th')).toHaveText('Banmédica');
 await expect(page.locator('#v2Prof h3')).toHaveText('Banmédica');
 await expect(page.locator('#seriesLargas .sl-cap strong')).toHaveText('Banmédica');
 await expect(page.locator('#v2Fichas .v2-f-card:visible')).toHaveCount(4);
 await page.locator('#v2Chips .v2-chip').click();
 await expect(page.locator('#v2Prof')).toHaveCount(0);
 await page.selectOption('#fRegion','Valparaíso');await page.selectOption('#fPeriodo','10');
 await expect(page.locator('#v2Comp [data-view="region"]')).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('#seriesLargas [data-range="10"]')).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('#v2Fichas .v2-f-card:visible')).toHaveCount(2);
 expect(await noHScroll(page)).toBeTruthy();
 expect(errors).toEqual([]);
});
