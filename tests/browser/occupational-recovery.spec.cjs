const {test,expect}=require('./fixtures.cjs');
const fs=require('node:fs');
const lanes=['clinicas_achs_salud','achs_seguro_laboral','mutual_seguridad','ist'];

test('occupational sources expose verified counts and readable source identity on desktop and mobile',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await expect(page.locator('#meta')).toContainText('Última actualización:');
  const health=await (await page.request.get('/data/source_health.json')).json();
  for(const slug of lanes){
    const row=health.sources[slug];
    expect(['OPERATIVE_VALIDATED','OPERATIVE_DEGRADED','EXTERNAL_BLOCKER_PROVEN']).toContain(row.recovery_outcome);
    expect(row.pages_checked).toBeGreaterThan(0);
    expect(row.recent_items['90'].expected_role).toBeGreaterThanOrEqual(row.recent_items['30'].expected_role);
    expect(row.unique_items).toBe(row.recent_items['90'].expected_role);
    if(!row.coverage_completeness)expect(row.status).not.toBe('ok');
  }
  expect(health.sources.clinicas_achs_salud.name).toBe('Achs Salud / Clínicas');
  await page.locator('#sourcesOpen').click();
  await expect(page.locator('#sourcesDialog')).toBeVisible();
  // The source list loads independently from the radar metadata. Wait for its render before inspecting the expansion control.
  await expect(page.locator('#sourcesList .source-row').first()).toBeVisible();
  if(await page.locator('#sourcesMore').isVisible())await page.locator('#sourcesMore').click();
  const catalog=await (await page.request.get('/data/public_sources.json')).json();
  for(const slug of lanes){
    const listed=catalog.sources.find(x=>x.id===slug),row=page.locator('.source-row').filter({hasText:health.sources[slug].name});
    await expect(row).toHaveCount(listed?1:0);
    if(listed)await expect(row).not.toContainText(/Última consulta|2016/);
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  expect(errors).toEqual([]);
  fs.mkdirSync('artifacts',{recursive:true});
  await page.screenshot({path:`artifacts/${test.info().project.name}-occupational-source-recovery.png`,fullPage:true});
});

test('occupational backfills retain their publisher and original publication year in the 90-day radar',async({page})=>{
  const snapshot=await (await page.request.get('/data/radar_today.json')).json();
  await page.clock.install({time:new Date(snapshot.date+'T15:00:00Z')});
  await page.goto('/');
  const recovered=snapshot.signals.filter(s=>(s.watch_tags||[]).some(t=>lanes.includes(t)));
  expect(recovered.length).toBeGreaterThanOrEqual(4);
  await page.locator('#period').selectOption('90');
  for(const signal of recovered){
    expect(signal.ingestion_mode).toBe('BACKFILL');
    expect(signal.event_date).toBe(signal.publication_date);
    expect(signal.editorial_relevance).toBeGreaterThanOrEqual(75);
    const card=page.locator('article.signal').filter({has:page.locator('a').filter({hasText:'Fuente original'}).and(page.locator(`a[href=${JSON.stringify(signal.source_url)}]`))});
    const age=(Date.parse(snapshot.date+'T00:00:00Z')-Date.parse(signal.event_date+'T00:00:00Z'))/86400000;
    if(age<0||age>=90){await expect(card).toHaveCount(0);continue;}
    await expect(card).toHaveCount(1);
    await expect(card.locator('.card-meta')).toContainText(signal.source_name);
    await expect(card.locator('.card-meta')).toContainText('2026');
    await expect(card.locator('.card-meta')).not.toContainText('2025');
    if(signal.market_role==='mutuality')expect(signal.watch_tags).not.toContain('clinicas_achs_salud');
    await expect(card).not.toContainText('aún está abierta');
    if(signal.source_slug==='mutual_seguridad'){
      await card.scrollIntoViewIfNeeded();
      fs.mkdirSync('artifacts',{recursive:true});
      await page.screenshot({path:`artifacts/${test.info().project.name}-occupational-mutual-viewport.png`});
    }
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  fs.mkdirSync('artifacts',{recursive:true});
  await page.screenshot({path:`artifacts/${test.info().project.name}-occupational-recovered-backfills.png`,fullPage:true});
});
