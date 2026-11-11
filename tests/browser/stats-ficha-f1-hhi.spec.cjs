const {test,expect}=require('./fixtures.cjs');
const fs=require('node:fs');
const path=require('node:path');

// F1 v9 (3-nov-2026) at 390 and 1440 px: the 'Concentración' topic (HHI of the open Isapres, then each Isapre's part).
// The card is tests/fixtures/stats_fichas/f1_cartera.card.json, built offline from the committed cartera capture
// (stats_ficha_fixtures.write_f1_fixture).
const SHOTS=process.env.ALICANTO_SHOTS_DIR||'artifacts';
const card=()=>JSON.parse(fs.readFileSync('tests/fixtures/stats_fichas/f1_cartera.card.json','utf8'));
const shot=async(page,name)=>{fs.mkdirSync(SHOTS,{recursive:true});await page.screenshot({path:path.join(SHOTS,`f1_${test.info().project.name==='mobile'?390:1440}_${name}.png`),fullPage:false})};
const inside=page=>page.evaluate(()=>[...document.querySelectorAll('#detailBody .sf-tpanel:not([hidden]) svg[role=img], #detailBody .sf-index svg[role=img]')].map(s=>{
 const vb=s.viewBox.baseVal,xl=[...s.querySelectorAll('text.sf-xlab')].map(t=>t.getBBox()).sort((a,b)=>a.x-b.x);
 return {chart:s.closest('[data-chart]')?.dataset.chart||'spark',bad:[...s.querySelectorAll('text')].filter(t=>{const b=t.getBBox();return b.x<-1||b.x+b.width>vb.width+1}).map(t=>t.textContent),
  overlap:xl.some((b,i)=>i&&b.x<xl[i-1].x+xl[i-1].width)}}));
const noOverflow=page=>page.evaluate(()=>{const d=document.getElementById('signalDetail');return document.documentElement.scrollWidth<=innerWidth+1&&d.scrollWidth<=d.clientWidth+1});

test('F1 ficha has a Concentración topic with the HHI series and each Isapre part',async({page})=>{
 const c=card(),f=c.stats_ficha;
 await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-10-12',generated_at:'2026-10-12T12:00:00Z',signals:[c]}}));
 await page.goto('/');
 const row=page.locator(`article[data-card="${c.piece_id}"]`);
 await expect(row).toHaveCount(1);
 await row.locator('[data-detail]').first().click();
 const body=page.locator('#detailBody');
 await expect(body.locator('.sf-headline')).toHaveText(f.headline);
 const labels=await body.locator('.sf-row-label').evaluateAll(xs=>xs.map(x=>x.firstChild.textContent.trim()));
 expect(labels).toContain('Concentración');
 expect(labels.indexOf('Concentración')).toBe(labels.indexOf('Regional')-1);
 const i=labels.indexOf('Concentración');
 await expect(body.locator('.sf-row-line').nth(i)).toHaveText(/^HHI \d{1,2}\.\d{3} puntos · /);
 await expect(body).not.toContainText(/moderadamente concentrad|altamente concentrad/i);
 for(const r of await inside(page))expect(r.bad,r.chart).toEqual([]);
 await expect.poll(()=>noOverflow(page),{timeout:3000}).toBe(true);
 await shot(page,'index');
 await body.locator('.sf-row').nth(i).click();
 await expect(body.locator('.sf-pick-label')).toHaveText('Concentración');
 const panel=body.locator('.sf-tpanel:not([hidden])');
 await expect(panel.locator('[data-chart="f1-hhi"]')).toBeVisible();
 for(const r of await inside(page)){expect(r.bad,r.chart).toEqual([]);expect(r.overlap,r.chart).toBeFalsy()}
 await expect.poll(()=>noOverflow(page),{timeout:3000}).toBe(true);
 await shot(page,'concentracion');
 const parts=panel.locator('[data-chart="f1-hhi-aporte"]');
 await expect(parts.locator('svg rect')).toHaveCount(7);  // only the 7 open Isapres
 await parts.locator('summary').click();
 expect(await parts.locator('thead th').allTextContents()).toEqual(['Isapre','Participación','Aporte al HHI']);
 await expect(parts.locator('tbody tr').last()).toContainText('HHI abiertas');
 for(const n of ['Isalud','Fundación','Cruz del Norte'])await expect(parts).not.toContainText(n);
 await expect.poll(()=>noOverflow(page),{timeout:3000}).toBe(true);
 await parts.scrollIntoViewIfNeeded();
 await shot(page,'concentracion_aporte');
 // Notas: the HHI by controlling group is pending; no interpretation thresholds.
 const notes=body.locator('details.sf-notes');
 await notes.locator('summary').click();
 await expect(notes).toContainText('el HHI por grupo controlador queda pendiente');
});
