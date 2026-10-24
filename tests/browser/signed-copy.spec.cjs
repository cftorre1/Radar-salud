const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
const signed=JSON.parse(fs.readFileSync('tests/fixtures/signed_editorial_v3.json','utf8'));

test('v3 reviewed title survives conflicting legacy copy on every public surface',async({page})=>{
 const unreviewed='Resolución IF/N°1 acoge reposición y levanta la sanción.';
 const signal={...signed,depth_gate:{ok:true},card_what:unreviewed,card_why:unreviewed,what_happened:unreviewed,why_it_matters:unreviewed,normative_subject:unreviewed};
 // Synthetic regression input; the Python companion verifies its unchanged receipt/export.
 await page.clock.install({time:new Date('2026-10-12T15:00:00Z')});
 await page.route('**/data/free_value.json',r=>r.fulfill({json:{}}));
 await page.route('**/data/radar_today.json',r=>r.fulfill({json:{generated_at:'2026-10-12T15:00:00Z',signals:[signal]}}));
 await page.goto('/');
 const card=page.locator('[data-card]');await expect(card).toHaveCount(1);
 await expect(card.locator('.title-open')).toHaveText(signed.title);
 await expect(page.locator('.briefitem strong')).toHaveText(signed.title);
 await expect(page.locator('[data-brief-read]')).toHaveAttribute('aria-label',`Marcar como leído: ${signed.title}`);
 await expect(card.locator('[data-share]')).toHaveAttribute('data-share-title',signed.title);
 await expect(page.locator('main')).not.toContainText(unreviewed);
 await card.locator('.title-open').click();
 await expect(page.locator('#detailTitle')).toHaveText(signed.title);
 await expect(page.locator('#detailBody')).toContainText(signed.detail_body);
 await expect(page.locator('#detailBody')).not.toContainText(unreviewed);
 const titleDetail=await page.locator('#detailBody').textContent();
 await page.keyboard.press('Escape');await card.getByRole('button',{name:'Más info',exact:true}).click();
 await expect(page.locator('#detailBody')).toHaveText(titleDetail);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.screenshot({path:`artifacts/signed-copy-${test.info().project.name}.png`});
});
