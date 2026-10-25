// Synthetic registry-linkage fixtures only; these tests never prove live Pulso
// discovery, materiality, publication, or date verification.
const {test,expect}=require('./fixtures.cjs');

for(const name of ['Pulso Latercera','Pulso / La Tercera']){
 test(`synthetic Pulso registry fixture links ${name} to canonical publisher selection`,async({page})=>{
  await page.route('**/data/public_sources.json',route=>route.fulfill({json:{sources:[{id:'pulso_latercera',name,group:'Noticias y mercado',url:'https://www.latercera.com/pulso/',description:'Noticias públicas del sector.'}]}}));
  // This incomplete record supplies only registry identity/date. It cannot
  // pass the card publication contract and is never a synthetic public signal.
  await page.route('**/data/radar_today.json',route=>route.fulfill({json:{
   generated_at:'2026-10-11T05:00:00Z',signals:[{source_name:'Pulso / La Tercera',event_date:'2026-10-10'}],
  }}));
  await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
  await page.locator('#sourcesOpen').click();
  const source=page.locator('#sourcesList .source-row');
  await expect(source).toHaveCount(1);await expect(source.getByRole('link')).toContainText(name);
  await expect(source.getByRole('link')).toHaveAttribute('href','https://www.latercera.com/pulso/');await expect(source).not.toContainText('Última seleccionada');
  await expect(source.locator('xpath=ancestor::section[contains(@class,"source-group")]')).toContainText('Noticias y mercado');
  await expect(page.locator('article[data-card]')).toHaveCount(0);
 });
}
