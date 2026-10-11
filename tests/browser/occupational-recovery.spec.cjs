const {test,expect}=require('@playwright/test');
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
  if(await page.locator('#sourcesMore').isVisible())await page.locator('#sourcesMore').click();
  for(const slug of lanes){
    const row=page.locator('.source-row').filter({has:page.getByText(health.sources[slug].name,{exact:true})});
    await expect(row).toHaveCount(1);
    await expect(row).toContainText('Última consulta');
    await expect(row).not.toContainText('2016');
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  expect(errors).toEqual([]);
  fs.mkdirSync('artifacts',{recursive:true});
  await page.screenshot({path:`artifacts/${test.info().project.name}-occupational-source-recovery.png`,fullPage:true});
});
