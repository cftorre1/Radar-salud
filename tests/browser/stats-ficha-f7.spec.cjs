const {test,expect,selectPeriod}=require('./fixtures.cjs');
const fs=require('node:fs');
const path=require('node:path');

// F7 Financiamiento público (DIPRES Partida 16) at 390 and 1440 px. The card is built from the committed DIPRES lane
// with the first-review gate opened only for this fixture (tests/fixtures/stats_fichas/f7_financiamiento.card.json).
const SHOTS=process.env.ALICANTO_SHOTS_DIR||'artifacts';
test('f7 ficha opens with its two topics, nominal labels, detection date and no overflow',async({page})=>{
 const card=JSON.parse(fs.readFileSync('tests/fixtures/stats_fichas/f7_financiamiento.card.json','utf8'));
 await page.clock.setFixedTime(new Date('2026-11-04T12:00:00-03:00'));
 await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-11-04',generated_at:'2026-11-04T12:00:00Z',signals:[card]}}));
 await page.goto('/');
 await selectPeriod(page,'90');
 const row=page.locator(`article[data-card="${card.piece_id}"]`);
 await expect(row).toHaveCount(1);
 const name=test.info().project.name;
 fs.mkdirSync(SHOTS,{recursive:true});
 await page.screenshot({path:path.join(SHOTS,`f7_feed-${name}.png`),fullPage:false});
 await row.locator('[data-detail]').first().click();
 const body=page.locator('#detailBody');
 await expect(body.locator('.sf-headline')).toHaveText(await page.evaluate(f=>AlicantoFicha.genericTitle(f,{title:((typeof datosByPiece!=='undefined'&&datosByPiece.get(f.id))||{}).index_title}),card.stats_ficha));
 expect(await body.locator('.sf-row-label').evaluateAll(xs=>xs.map(x=>x.firstChild.textContent.trim()))).toEqual(['Salud (Partida 16)','Fonasa']);
 expect(await body.locator('.sf-row-line').evaluateAll(xs=>xs.map(x=>x.textContent))).toEqual(card.stats_ficha.tabs.map(t=>t.index_line));
 // Cut and detection are two different dates; no publication date is claimed.
 const meta=await body.locator('.sf-meta li').allTextContents();
 expect(meta[0]).toMatch(/^Datos al \d{1,2} \p{L}+ \d{4} \(corte; captura manual, próxima actualización pendiente\)$/u);expect(meta[1]).toMatch(/^Detectado por Alicanto el /);
 await expect(body.locator('.sf-kick')).toContainText('· corte ');
  await expect(body.locator('.sf-headline')).not.toContainText('Fonasa');
 await expect(body).not.toContainText('publicado por DIPRES');
 await expect(body.locator('.sf-reading')).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.screenshot({path:path.join(SHOTS,`f7_index-${name}.png`),fullPage:false});
 const inside=()=>page.evaluate(()=>[...document.querySelectorAll('#detailBody .sf-tpanel:not([hidden]) svg[role=img]')].every(s=>{const vb=s.viewBox.baseVal;return [...s.querySelectorAll('text')].every(t=>{const b=t.getBBox();return b.x>=-1&&b.x+b.width<=vb.width+1})}));
 await body.locator('.sf-row').first().click();
 for(const [i,tab] of ['Salud (Partida 16)','Fonasa'].entries()){
  if(i)await body.locator('[data-sf-step="1"]').click();
  await expect(body.locator('.sf-pick-label')).toHaveText(tab);
  await expect(body.locator('.sf-tpanel:not([hidden]) .sf-chart')).toHaveCount(2);
  expect(await inside(),tab).toBeTruthy();
  await expect.poll(()=>page.evaluate(()=>{const d=document.getElementById('signalDetail');return d.scrollWidth<=d.clientWidth+1}),{timeout:3000}).toBe(true);  // settled layout (a topic switch can overflow for a frame)
  await page.screenshot({path:path.join(SHOTS,`f7_${['salud','fonasa'][i]}-${name}.png`),fullPage:false});
 }
 const chart=body.locator('.sf-tpanel:not([hidden]) .sf-chart').first();
 await chart.locator('summary').click();
 await expect(chart.locator('table tbody tr').first()).toBeVisible();
 await page.screenshot({path:path.join(SHOTS,`f7_datos_tabla-${name}.png`),fullPage:false});
 await body.locator('details.sf-notes summary').click();
 await expect(body.locator('details.sf-notes')).toContainText('No se suman entre meses');
 await page.screenshot({path:path.join(SHOTS,`f7_notas-${name}.png`),fullPage:false});
});
