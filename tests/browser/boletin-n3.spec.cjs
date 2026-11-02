const {test,expect,selectPeriod}=require('./fixtures.cjs');
const fs=require('node:fs');
const path=require('node:path');

// Dirección 1-nov-2026. (1) The four loose PDFs of Boletín IP N°3-2026 are ONE card while its figures are verified: the
// ficha says so, links the live F6 ficha (N°2) and lists the PDFs. (2) News fichas carry a compact origin line
// ("SIS · Intendencia de Prestadores · 29 oct 2026 (detección) · Fuente original ↗"). The card mirrors
// sis_bulletins.collapse_loose_bulletins on the four history records (titles and URLs as the SIS listing gives them);
// the F6 card is the committed N°2 fixture.
const SHOTS=process.env.ALICANTO_SHOTS_DIR||'artifacts';
const U='https://www.superdesalud.gob.cl/app/uploads/2026/10/';
const DOCS=[['acreditación','Boletín N°3-2026 Acreditación enero-septiembre 2026','boletin-n3-2026-acreditacion-enero-septiembre-2026-1.pdf'],
 ['mediación','Boletín N°3-2026 Mediación enero-septiembre 2026','boletin-n3-2026-mediacion-enero-septiembre-2026.pdf'],
 ['reclamos','Boletín N°3-2026 Reclamos enero- septiembre 2026','boletin-n3-2026-reclamos-enero-septiembre-2026-1.pdf'],
 ['RNPI','Boletin N°3-2026 RNPI enero- septiembre 2026','boletin-n3-2026-rnpi-enero-septiembre-2026-1.pdf']].map(([label,title,file])=>({label,title:`${title} (PDF)`,url:U+file}));
const TITLE='Boletín Estadístico Informativo IP N°3 · enero–septiembre 2026';
const N3={piece_id:'sis-bulletin:boletin_ip:N3-2026',title:TITLE,display_title:TITLE,source_name:'Superintendencia de Salud · Intendencia de Prestadores',source_type:'official',
 source_url:DOCS[0].url,source_documents:DOCS,event_date:'2026-10-29',first_detected_at:'2026-10-29T23:30:08.542961+00:00',date_basis:'first_detected',publication_date:null,
 data_period:'enero–septiembre 2026',stat_family:'boletin_ip',stat_period:'2026-09',signal_types:['Datos'],scopes:['Prestadores'],category:'Datos sectoriales',radar_score:60,card_why_optional:true,
 what_happened:'La Intendencia de Prestadores de la Superintendencia de Salud tiene disponible el Boletín N°3-2026 (enero–septiembre 2026) en 4 PDF: acreditación, mediación, reclamos y RNPI.',
 bulletin_status:{status:'verifying',period:'2026-09',text:'Alicanto está verificando las cifras de este boletín en los PDF originales. Hasta que pasen la verificación, no se muestran cifras de este boletín.',
  live_ficha:{id:'stats-ficha:F6:2026-06',period:'2026-06',label:'Ver la ficha vigente: Boletín IP N°2-2026 · datos a junio 2026'}},
 editorial_committee:{verdict:'PASS'},feed_visibility:true,editorial_decision:'accept'};
const NEWS={title:'Minsal suma hospitales al consejo sobre eficiencia y déficit',source_name:'Ministerio de Salud',source_url:'https://www.minsal.cl/consejo-eficiencia/',
 event_date:'2026-10-28',publication_date:'2026-10-28',data_period:'2026',signal_types:['Noticias'],scopes:['Prestadores'],card_why_optional:true,what_happened:'El consejo sumó representantes de hospitales y Servicios de Salud en su segunda sesión.',
 editorial_committee:{verdict:'PASS'},feed_visibility:true,radar_score:55};

async function load(page){
 const f6=JSON.parse(fs.readFileSync('tests/fixtures/stats_fichas/f6_prestadores.card.json','utf8'));
 await page.clock.setFixedTime(new Date('2026-11-01T12:00:00-03:00'));
 await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-11-01',generated_at:'2026-11-01T12:00:00Z',signals:[N3,NEWS,f6]}}));
 await page.goto('/');await selectPeriod(page,'90');
 return f6;
}

test('loose N°3 PDFs read as one card whose ficha says the figures are being verified',async({page})=>{
 const f6=await load(page);
 const rows=page.locator('article[data-card]').filter({hasText:/N°3/});
 await expect(rows).toHaveCount(1);await expect(rows.first().locator('h2')).toHaveText(TITLE);
 await rows.first().locator('[data-detail]').first().click();
 const body=page.locator('#detailBody');
 await expect(body.locator('#detailTitle')).toHaveText(TITLE);
 await expect(body.locator('.bulletin-status')).toHaveText(N3.bulletin_status.text);
 expect(await body.locator('.ficha-sources li a').evaluateAll(xs=>xs.map(a=>[a.getAttribute('href'),a.textContent.trim()]))).toEqual(DOCS.map(d=>[d.url,`${d.title} ↗`]));
 await expect(body.locator('.ficha-sources > p.source')).toHaveText(/^SIS · Intendencia de Prestadores · 29 oct\.? 2026 \(detección\) · Fuente original ↗$/);
 await expect(body).not.toContainText(/Período de datos|fecha de publicación no informada|tema: |\d+ prestadores acreditados/);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 expect(await page.evaluate(()=>{const d=document.getElementById('signalDetail');return d.scrollWidth<=d.clientWidth+1})).toBeTruthy();
 fs.mkdirSync(SHOTS,{recursive:true});
 await page.screenshot({path:path.join(SHOTS,`boletin-n3-card-${test.info().project.name}.png`),fullPage:false});
 // The live ficha link opens the F6 ficha (N°2) in place.
 await body.locator('a.bulletin-live').click();
 await expect(body.locator('.sf-headline')).toHaveText(f6.stats_ficha.headline);
});

test('news ficha shows the compact sources line',async({page})=>{
 await load(page);
 const row=page.locator('article[data-card]').filter({hasText:NEWS.title});
 await row.locator('[data-detail]').first().click();
 const line=page.locator('#detailBody .ficha-sources > p.source');
 await expect(line).toHaveText(/^Minsal · 28 oct\.? 2026 \(publicación\) · Fuente original ↗$/);
 await expect(line.locator('a')).toHaveAttribute('href',NEWS.source_url);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 fs.mkdirSync(SHOTS,{recursive:true});
 await page.screenshot({path:path.join(SHOTS,`news-sources-line-${test.info().project.name}.png`),fullPage:false});
});
