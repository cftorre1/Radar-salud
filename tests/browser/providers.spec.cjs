const {test,expect}=require('@playwright/test');
const names=['RedSalud','Bupa Chile','Clínica INDISA','Red Dávila','Andes Salud','Clínicas de Chile A.G.','Pfizer Chile','Clínicas Achs Salud'];
const recovered=['/nueva-unidad-trasplante-medula-osea','/chile-tendra-su-primera-base-genomica-de-referencia-bupa-lanza-1000',
 '/clinica-andes-salud-talca-abre-sus-puertas-y-fortalece-el-acceso-a-salud-de-alta-complejidad-en-el-maule/',
 '/andes-salud-y-metlife-fortalecen-su-alianza-para-acercar-proteccion-financiera-en-salud-a-las-regiones-de-chile/',
 '/centro-medico-andes-salud-puerto-varas-fortalecera-el-acceso-a-salud-en-la-region-de-los-lagos/',
 '/clinicas-de-chile-y-cens-realizan-jornada-sobre-el-nuevo-marco-de-la-salud-digital-en-chile/'];

test('audited providers retain one visible institution and truthful freshness',async({page})=>{
 await page.goto('/');
 await page.locator('#sourcesOpen').click();
 await expect(page.locator('#sourcesList .source-row')).not.toHaveCount(0);
 await page.locator('#sourcesMore').click();
 for(const name of names){
  const row=page.locator('#sourcesList .source-row').filter({has:page.getByText(name,{exact:true})});
  await expect(row).toHaveCount(1);
  await expect(row).toContainText('Última consulta');
  await expect(row).toContainText('Última señal detectada');
  await expect(row).toContainText('Última seleccionada');
 }
 const health=await (await page.request.get('/data/source_health.json')).json();
 expect(health.sources.pfizer_chile.content_freshness).toBe('stale_external_surface');
 expect(health.sources.indisa.coverage_status).toBe('unverified');
 expect(health.sources.indisa.editorial_outcome).toBe('not_evaluated');
 expect(health.sources.indisa.evaluation_performed).toBe(false);
 expect(health.sources.andes_salud.audited_assessment.published).toBe(3);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.screenshot({path:`artifacts/providers-${test.info().project.name}.png`,fullPage:true});
});

test('recovered provider outputs retain source/date and pass feed contract',async({page})=>{
 await page.goto('/');
 const radar=await (await page.request.get('/data/radar_today.json')).json();
 for(const suffix of recovered){
  const rows=radar.signals.filter(s=>s.source_url.endsWith(suffix));
  expect(rows).toHaveLength(1);
  const row=rows[0];expect(row.ingestion_mode).toBe('BACKFILL');
  expect(row.event_date).toMatch(/^2026-\d\d-\d\d$/);
  expect(row.feed_visibility).toBe(true);
  expect(row.editorial_committee.verdict).toBe('PASS');
 }
 expect(radar.signals.some(s=>s.source_url.endsWith('/Memoria-2021-IMPRENTA_compressed.pdf'))).toBe(false);
 expect(radar.signals.some(s=>s.source_url.endsWith('/INFORME_final.pdf'))).toBe(false);
});
