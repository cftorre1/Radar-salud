const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
const recovered=JSON.parse(fs.readFileSync('data/audits/daily_first_20261012/history-new.json','utf8'));

test('Daily First exposes original MINSAL dates and honest public-source coverage',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');
 await expect(page.locator('#meta')).toContainText('Última actualización:');
 const health=(await (await page.request.get('/data/source_health.json')).json()).sources;
 expect(health.minsal.recovery_outcome).toBe('OPERATIVE_DEGRADED');
 expect(health.minsal.coverage_complete).toBe(false);
 expect(health.minsal.items_evaluated).toBe(4);
 expect(health.minsal.published).toBe(3);
 expect(health.minsal.pending).toBe(0);
 expect(health.minsal.last_signal_at).toBe('2026-10-09');
 for(const slug of ['fonasa','fonasa_datos_abiertos','isp_anamed','isp_surveillance']){
  expect(health[slug].recovery_outcome).toBe('EXTERNAL_BLOCKER_PROVEN');
  expect(health[slug].coverage_complete).toBe(false);
  expect(health[slug].items_recent).toBeNull();
 }
 const signals=(await (await page.request.get('/data/radar_today.json')).json()).signals;
 for(const row of recovered){
  const found=signals.filter(s=>s.source_url===row.source_url);
  expect(found).toHaveLength(1);
  expect(found[0].event_date).toBe('2026-10-09');
  expect(found[0].ingestion_mode).toBe('BACKFILL');
  expect(found[0].publication_date_evidence.url).toBe(row.source_url);
 }
 await page.locator('#sourcesOpen').click();
 await expect(page.locator('#sourcesList .source-row').first()).toBeVisible();
 if(await page.locator('#sourcesMore').isVisible())await page.locator('#sourcesMore').click();
 const minsal=page.locator('.source-row').filter({has:page.getByText('Ministerio de Salud',{exact:true})});
 await expect(minsal).toHaveCount(1);
 await expect(minsal).toContainText('Última señal detectada');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 expect(errors).toEqual([]);
 fs.mkdirSync('artifacts',{recursive:true});
 await page.screenshot({path:`artifacts/${test.info().project.name}-daily-first.png`,fullPage:true});
});
