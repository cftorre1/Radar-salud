// Synthetic registry-linkage fixtures only; these tests never prove live Pulso
// discovery, materiality, publication, or date verification.
const {test,expect}=require('@playwright/test');

for(const name of ['Pulso Latercera','Pulso / La Tercera']){
 test(`synthetic Pulso registry fixture links ${name} to canonical publisher selection`,async({page})=>{
  await page.route('**/data/product.json',route=>route.fulfill({json:{sources:{pulso_latercera:{
   name,checked_at:'2026-10-11T05:00:00Z',last_signal_at:'2026-10-10',
  }}}}));
  // This incomplete record supplies only registry identity/date. It cannot
  // pass the card publication contract and is never a synthetic public signal.
  await page.route('**/data/radar_today.json',route=>route.fulfill({json:{
   generated_at:'2026-10-11T05:00:00Z',signals:[{source_name:'Pulso / La Tercera',event_date:'2026-10-10'}],
  }}));
  await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
  await page.locator('#sourcesOpen').click();
  const source=page.locator('#sourcesList .source-row');
  await expect(source).toHaveCount(1);await expect(source.locator('strong')).toHaveText(name);
  await expect(source).toContainText('Última seleccionada');await expect(source).not.toContainText('aún no visible');
  await expect(source.locator('.source-meta span').last()).toContainText('10');
  await expect(source.locator('xpath=ancestor::section[contains(@class,"source-group")]')).toContainText('Noticias y mercado');
  await expect(page.locator('article[data-card]')).toHaveCount(0);
 });
}
