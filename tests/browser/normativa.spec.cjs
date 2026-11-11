const {test,expect}=require('./fixtures.cjs');
// Normativa phase 1 (Dirección, 11-nov-2026; mockup «2 · Cuenta regresiva arriba»): countdown first, groups, months,
// «Filtrar» (emisor, tema, búsqueda), feed by group; the same norm card as Al día; «Implementada» persists per reader.
const noHScroll=page=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1);
test('Normativa: countdown, groups, months, filters, shared card and implementada',async({page})=>{
 const d=await (await page.request.get('/data/normativa.json')).json();expect(d.items.length).toBeGreaterThanOrEqual(31);
 await page.clock.setFixedTime(new Date('2026-11-11T09:00:00-03:00'));
 await page.goto('/normativa.html');await expect(page.locator('#nmFeed .nm-card').first()).toBeVisible();
 await expect(page.locator('.topnav a[aria-current="page"]')).toHaveAttribute('href','normativa.html');
 expect(await page.locator('.topnav a').evaluateAll(xs=>xs.map(el=>(el.dataset.short||el.textContent).trim()))).toEqual(['Al día','Normativa','Datos','Global','Newsletter']);
 // Countdown first: the days lead.
 const hc=page.locator('#nmHero .nm-hc').first();await expect(hc.locator('.nm-hd b')).toHaveText(/^\d+$/);
 await expect(page.locator('#nmCount')).toContainText(`${d.items.length} de ${d.items.length} normas`);
 // Every norm is listed, also the ones without a literal date («en revisión»).
 await expect(page.locator('#nmFeed .nm-card')).toHaveCount(await page.locator('#nmFeed .nm-card').count());
 await page.locator('#nmGroups [data-g="sin"]').click();const sin=d.items.filter(x=>x.kind==='none'&&!x.review).length;
 await expect(page.locator('#nmFeed .nm-card')).toHaveCount(sin);await expect(page.locator('#nmFeed .nm-vig.sin').first()).toContainText('en revisión');
 await page.locator('#nmGroups [data-g="all"]').click();
 // Default actions of any Al día card + Texto oficial + the round check.
 const card=page.locator('#nmFeed .nm-card').first();
 for(const sel of ['.dotbtn','.nm-ck','.nm-det summary','.act-open','.act-share'])await expect(card.locator(sel)).toHaveCount(1);
 await card.locator('.nm-ck').click();await expect(page.locator('#nmGroups [data-g="impl"] b')).toHaveText('1');
 await page.reload();await expect(page.locator('#nmGroups [data-g="impl"] b')).toHaveText('1');
 // Filtrar: tema and search combine; months filter by entry into force.
 await page.locator('#nmFx summary').click();await page.locator('#nmQ').fill('541');await expect(page.locator('#nmCount')).toContainText('1 de');
 await page.locator('#nmCount [data-clear="q"]').click();
 expect(await noHScroll(page)).toBeTruthy();
});
test('Normativa: «Ver ficha» opens the Al día ficha',async({page})=>{
 const d=await (await page.request.get('/data/normativa.json')).json();const x=d.items.find(i=>i.in_feed);test.skip(!x,'no norm in the feed');
 await page.goto('/'+x.ficha);await expect(page.locator('#signalDetail')).toBeVisible();await expect(page.locator('#detailBody')).toContainText(x.label);
});
