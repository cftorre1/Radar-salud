const {test,expect}=require('@playwright/test');
const fs=require('node:fs');

test('verified historical bulletin keeps its statistical UI contract after live-window expiry',async({page})=>{
 const verified=JSON.parse(fs.readFileSync('config/statistical_analysis_verified_v1.json','utf8'));
 const [url,analysis]=Object.entries(verified.signals)[0];
 const original=JSON.parse(fs.readFileSync('data/history/superintendencia_signals.json','utf8')).signals.find(s=>s.source_url===url);
 expect(original.event_date).toBe('2026-08-03');
 // Historical clock and test-only routing preserve rendering coverage forever;
 // none of the publisher dates or real current-feed dispositions are changed.
 await page.clock.install({time:new Date('2026-08-04T12:00:00Z')});
 const signal={...original,...analysis,feed_visibility:true,editorial_decision:'group',
   publication_gate_reason:'ok',publication_ready_score:100,editorial_committee:{verdict:'PASS'}};
 await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-08-04',generated_at:'2026-08-04T12:00:00Z',signals:[signal]}}));
 await page.goto('/');
 const card=page.locator('article[data-card]').filter({hasText:'Boletín Estadístico Informativo IP'});
 await expect(card).toHaveCount(1);
 await expect(card).not.toContainText('Por qué importa:');
 await card.locator('[data-detail]').click();
 const detail=page.locator('#detailBody');
 await expect(detail.locator('.summary-table tbody tr')).toHaveCount(6);
 for(const topic of ['Acreditación','Mediación','Reclamos','RNPI'])await expect(detail.locator('.summary-table')).toContainText(topic);
 await expect(detail.locator('details.statistical-methodology')).not.toHaveAttribute('open','');
 for(const source of signal.data_insight_evidence)await expect(detail.locator(`a[href="${source.source_url}"]`).first()).toHaveCount(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.screenshot({path:`artifacts/statistical-contract-${test.info().project.name}.png`,fullPage:true});
});
