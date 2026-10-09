const {test,expect}=require('@playwright/test');
const fs=require('node:fs');fs.mkdirSync('artifacts',{recursive:true});
test('Home V2 loads, filters persist and compact triage remains stable',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 await expect(page.locator('#period')).toHaveValue('14');await expect(page.locator('#sort')).toHaveValue('date');
 await expect(page.getByRole('heading',{name:'Encuentra lo que importa',exact:true})).toBeVisible();
 expect(await page.getByRole('heading',{name:'Encuentra lo que importa',exact:true}).evaluate(el=>el.getBoundingClientRect().height/parseFloat(getComputedStyle(el).lineHeight))).toBeLessThan(1.1);
 await expect(page.locator('#filterDetails')).not.toHaveAttribute('open','');
 await expect(page.locator('.coverage,.toolbar,.weekly-cta,.preferences-panel')).toHaveCount(0);
 await expect(page.getByText('Personalizar mi radar',{exact:true})).toHaveCount(0);
 await expect(page.getByText(/Ingresar|Registrarse/)).toHaveCount(0);
 await expect(page.locator('#earlyAccessOpen')).toHaveText('Acceso PREMIUM');
 await page.locator('#earlyAccessOpen').click();await expect(page.locator('#earlyAccessDialog')).toBeVisible();
 await expect(page.locator('#earlyAccessDialog')).toContainText('Ve más allá de la señal.');
 await expect(page.locator('#earlyAccessDialog')).toContainText('Inscríbete al acceso anticipado');
 await page.getByRole('button',{name:'Cerrar acceso Premium'}).click();
 await page.locator('#newsletterOpen').click();await expect(page.locator('#newsletterDialog')).toBeVisible();
 await expect(page.locator('#homeEmail')).toBeDisabled();
 await expect(page.locator('#newsletterDialog')).toContainText('Lo importante de la semana, directo a tu correo.');
 await page.getByRole('button',{name:'Cerrar resumen semanal'}).click();
 await expect(page.locator('#radarTitle')).toHaveText('Ponte al día en 30 segundos');
 await expect(page.locator('#radarMetrics')).toHaveText(/^\d+ tarjetas · no leídos \d+$/);
 const initialMetrics=(await page.locator('#radarMetrics').innerText()).match(/\d+/g).map(Number);
 await page.locator('#sourcesOpen').click();await expect(page.locator('#sourcesDialog')).toBeVisible();
 await expect.poll(()=>page.locator('#sourcesList .source-row').count()).toBeGreaterThan(6);
 await expect(page.locator('#sourcesDialog')).toContainText('¿Falta una fuente relevante?');
 if(await page.locator('#sourcesMore').isVisible())await page.locator('#sourcesMore').click();
 await expect.poll(()=>page.locator('#sourcesList .source-row').count()).toBeGreaterThan(10);
 await page.getByRole('button',{name:'Cerrar fuentes'}).click();
 await page.locator('#filterDetails summary').click();
 await expect(page.locator('#filterDetails')).toContainText('Tus filtros se guardan automáticamente');
 await expect(page.locator('#period')).toBeVisible();await expect(page.locator('#sort')).toBeVisible();
 const selectTops=await page.locator('.select-grid label').evaluateAll(xs=>xs.map(x=>Math.round(x.getBoundingClientRect().top)));
 expect(new Set(selectTops).size).toBe(1);
 await page.locator('#period').selectOption('90');
 const extendedMetrics=(await page.locator('#radarMetrics').innerText()).match(/\d+/g).map(Number);
 expect(extendedMetrics[0]).toBeGreaterThanOrEqual(initialMetrics[0]);
 const visibleTriage=await page.locator('.briefrow').evaluateAll(rows=>{const host=rows[0]?.parentElement?.getBoundingClientRect();return host?rows.filter(row=>{const r=row.getBoundingClientRect();return r.top>=host.top-1&&r.bottom<=host.bottom+1}).length:0});
 // Mobile deliberately avoids an inner scroll: two complete rows plus the explicit expand/feed controls remain readable.
 expect(visibleTriage).toBeGreaterThanOrEqual(test.info().project.name==='mobile'?2:3);
 await expect(page.locator('article').first()).toBeVisible();
 if(test.info().project.name==='mobile'){
  const cards=await page.locator('article').evaluateAll(xs=>xs.slice(0,3).map(x=>({height:Math.round(x.getBoundingClientRect().height),title:x.querySelector('h2')?.textContent||''})));
  expect(cards.length).toBe(3);expect(Math.max(...cards.map(x=>x.height)),JSON.stringify(cards)).toBeLessThan(600);
 }
 await page.screenshot({path:`artifacts/${test.info().project.name}-browse.png`,fullPage:true});
 await page.locator('.briefitem').filter({hasNot:page.locator('.brief-kind')}).first().click();
 await expect(page.locator('article.read').first()).toBeVisible();
 expect(await page.evaluate(()=>document.activeElement?.tagName)).toBe('ARTICLE');
 await expect(page.locator('article.read').first().getByRole('button',{name:'Volver arriba'})).toBeVisible();
 await page.locator('article.read').first().getByRole('button',{name:'Volver arriba'}).click();
 expect(await page.evaluate(()=>document.activeElement?.tagName)).toBe('MAIN');
 const ids=await page.locator('article').evaluateAll(xs=>xs.map(x=>x.id));expect(new Set(ids).size).toBe(ids.length);
 await page.locator('article[data-card]').first().getByRole('button',{name:/Marcar/}).click();
 expect((await page.locator('article').evaluateAll(xs=>xs.map(x=>x.id))).sort()).toEqual(ids.sort());
 await expect(page.locator('article').first().locator('.intel,.related')).toHaveCount(0);
 const withDepth=page.locator('article:has([data-detail])').first();await withDepth.locator('[data-detail]').click();
 await expect(page.locator('#signalDetail')).toBeVisible();await page.getByRole('button',{name:'Cerrar resumen'}).click();
 await page.locator('#typeFilters').getByRole('button',{name:'Fiscalización',exact:true}).click();
 await expect(page.locator('article').first()).toBeVisible();
 const filteredMetrics=(await page.locator('#radarMetrics').innerText()).match(/\d+/g).map(Number);
 expect(filteredMetrics[0]).toBe(await page.locator('article').count());
 expect(filteredMetrics[1]).toBe(await page.locator('article:not(.read)').count());
 await page.reload();await expect(page.locator('#period')).toHaveValue('90');
 await page.locator('#filterDetails summary').click();
 await expect(page.locator('#typeFilters').getByRole('button',{name:'Fiscalización',exact:true})).toHaveClass(/active/);
 await page.locator('#typeFilters').getByRole('button',{name:'Todos',exact:true}).click();
 const noOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1);expect(noOverflow).toBeTruthy();
 fs.writeFileSync(`artifacts/${test.info().project.name}-home-v2-triage.json`,JSON.stringify({visible_triage_rows:visibleTriage,filter_persisted:true,no_horizontal_overflow:noOverflow},null,2));
 expect(errors).toEqual([]);
 await page.screenshot({path:`artifacts/${test.info().project.name}-radar.png`,fullPage:true});
});
test('Inbox shows every unread signal, supports direct read and persists it',async({page})=>{
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 const initial=await page.locator('.briefitem').count();
 const freeValue=await (await page.request.get('/data/free_value.json')).json();
 const radar=await (await page.request.get('/data/radar_today.json')).json();
 const weeklyRendered=await page.locator('article[data-special].weekly:not(.read)').count()>0;
 const dedupedInsightBase=weeklyRendered&&freeValue.weekly_insight&&radar.signals.some(s=>s.source_url===freeValue.weekly_insight.source_url)?1:0;
 const expected=await page.locator('article[data-card]:not(.read)').count()+await page.locator('article[data-special]:not(.read)').count()-dedupedInsightBase;
 expect(initial).toBe(expected);expect(initial).toBeGreaterThan(4);
 const first=await page.locator('.briefitem').first().getAttribute('data-brief');
 await page.locator('[data-brief-read]').first().click();
 expect(await page.evaluate(()=>document.activeElement?.hasAttribute('data-brief-read'))).toBeTruthy();
 await expect(page.locator('.briefitem')).toHaveCount(initial-1);
 expect(await page.locator(`article[data-card="${first}"],article[data-special="${first}"]`).count()).toBeGreaterThan(0);expect(await page.locator(`article[data-card="${first}"],article[data-special="${first}"]`).evaluateAll(xs=>xs.every(x=>x.classList.contains('read')))).toBeTruthy();
 await page.reload();await expect(page.locator('#meta')).toContainText('Última actualización:');
 await expect(page.locator('.briefitem')).toHaveCount(initial-1);
 expect(await page.locator(`article[data-card="${first}"],article[data-special="${first}"]`).count()).toBeGreaterThan(0);expect(await page.locator(`article[data-card="${first}"],article[data-special="${first}"]`).evaluateAll(xs=>xs.every(x=>x.classList.contains('read')))).toBeTruthy();
 await page.locator('#filterDetails summary').click();
 await page.locator('#period').selectOption('90');
 const inbox=page.locator('.brief-list');
 const deepCount=await page.locator('[data-brief-read]').count();
 expect(deepCount).toBeGreaterThan(4);
 if(test.info().project.name==='mobile'){
  await expect(page.locator('[data-brief-expand]')).toBeVisible();
  expect(await inbox.evaluate(el=>getComputedStyle(el).overflowY)).toBe('hidden');
  await page.locator('[data-brief-expand]').click();
  await expect(inbox).toHaveClass(/expanded/);
 }else{
  await inbox.evaluate(el=>el.scrollTop=el.scrollHeight);
  expect(await inbox.evaluate(el=>el.scrollTop)).toBeGreaterThan(0);
 }
 await page.locator('[data-brief-read]').last().click();
 if(test.info().project.name!=='mobile')expect(await inbox.evaluate(el=>el.scrollTop)).toBeGreaterThan(0);
 expect(await page.evaluate(()=>document.activeElement?.hasAttribute('data-brief-read'))).toBeTruthy();
});
test('operations dashboard loads without inventing measurements',async({page})=>{
 await page.goto('/admin/product.html');await expect(page.locator('#status')).toContainText('Actualizado:');
 await expect(page.getByRole('heading',{name:'Control de producto'})).toBeVisible();
 await expect(page.getByRole('table',{name:'Cobertura por segmento'})).toBeVisible();
 await expect(page.locator('#coverageSegments tr')).toHaveCount(4);
 await expect(page.locator('#coverageSegments')).toContainText('Prestadores');
 await expect(page.locator('#coverageSegments')).toContainText('Fonasa / Sistema público');
 await expect(page.locator('#metrics')).toContainText('LIVE pending');
 await expect(page.locator('#usage')).toContainText('Costo USD: no disponible');
 await expect(page.locator('#featureUsage tr')).toHaveCount(12);
 await expect(page.locator('#featureUsage')).toContainText('Global Intelligence');
 await expect(page.locator('#featureUsage')).toContainText('Insight Alicanto de la semana');
 await expect(page.locator('#featureUsage')).toContainText('No disponible');
 await expect(page.locator('#featureUsage')).toContainText('Total acumulado');
 await expect(page.locator('#featureSummary')).toContainText('output determinístico trazable');
 await expect(page.locator('#featureSummary')).toContainText('costo/output No disponible');
 await expect(page.locator('#readiness')).toContainText('Beta cerrada');
 await expect(page.locator('#requirementProgress')).toContainText('requisitos validados con evidencia');
 await expect(page.locator('#externalObservations')).toContainText('Validado técnicamente / pendiente observación externa');
 await expect(page.locator('#externalObservations')).toContainText('No bloquea los demás bloques MVP');
 const report=await (await page.request.get('/data/product.json')).json();
 await expect(page.locator('#blocks .block')).toHaveCount(report.pmo.blocks.length);
 for(const failure of (report.pmo.open_failures||[]))await expect(page.locator('#failures')).toContainText(failure.description);
 await expect(page.locator('#deployments')).toContainText('Producción: último SHA comprobado');
 await expect(page.locator('thead th').filter({hasText:'Última consulta'})).toBeVisible();
 expect(await page.locator('thead th').filter({hasText:'Última consulta'}).getAttribute('scope')).toBe('col');
 await expect(page.locator('#sources tr').first()).toContainText('2026');
 await expect(page.locator('#excelValidation')).toContainText('2025-07 → 2026-07');
 await expect(page.locator('#excelValidation')).toContainText('desahucios voluntarios');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(test.info().project.use.viewport.width+1);
 const response=await page.request.get('/data/excel_diagnostics.csv');expect(response.ok()).toBeTruthy();
 await page.screenshot({path:`artifacts/${test.info().project.name}-product.png`,fullPage:true});
});
test('Home V2 places unread Global and Insight in the brief, then retains subdued feed cards',async({page})=>{
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 const source=await page.request.get('/data/free_value.json'),data=await source.json();
 const ageDays=raw=>{if(!raw)return Infinity;const d=/^\\d{4}-\\d{2}-\\d{2}$/.test(raw)?new Date(raw+'T00:00:00Z'):new Date(raw);const now=new Date(),today=Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate());return Math.max(0,Math.floor((today-d.getTime())/86400000))};
 const hasWeekly=Boolean(data.weekly_insight)&&ageDays(data.weekly_insight.event_date)<=14;
 const global=page.locator('.signal.special.global'),weekly=page.locator('.signal.special.weekly');
 await expect(global).toHaveCount(1);await expect(weekly).toHaveCount(hasWeekly?1:0);
 await expect(page.locator('.brief-global')).toHaveCount(1);await expect(page.locator('.brief-weekly')).toHaveCount(hasWeekly?1:0);
 await expect(page.locator('.briefrow').nth(0)).toHaveClass(/brief-global/);if(hasWeekly){await expect(page.locator('.briefrow').nth(1)).toHaveClass(/brief-weekly/);await expect(page.locator('.brief-weekly .brief-meta')).toContainText('·')}
 await expect(page.locator('.brief-global .brief-meta')).toContainText('·');
 const firstKinds=await page.locator('.briefrow').evaluateAll((rows,count)=>rows.slice(0,count).map(row=>row.classList.contains('brief-weekly')?'weekly':row.classList.contains('brief-global')?'global':'ordinary'),hasWeekly?2:1);expect(firstKinds).toEqual(hasWeekly?['global','weekly']:['global']);
 await expect(page.locator('.briefrow .brief-meta')).toHaveCount(await page.locator('.briefrow').count());
 const fills=await page.locator('.signal.special').evaluateAll(rows=>rows.map(row=>getComputedStyle(row).backgroundColor));expect(new Set(fills).size).toBe(hasWeekly?2:1);
 const readTargets=await page.locator('.briefread').evaluateAll((buttons,count)=>buttons.slice(0,count).map(button=>({width:button.getBoundingClientRect().width,height:button.getBoundingClientRect().height})),hasWeekly?2:1);expect(readTargets.every(({width,height})=>width>=44&&height>=44)).toBeTruthy();
 await expect(page.locator('.hero-purpose')).toHaveText('Señales clave del sector salud, claras y a tiempo.');
 if(hasWeekly){await expect(weekly).toContainText(data.weekly_insight.insight_title);await page.locator('.brief-weekly [data-brief-read]').click();await expect(page.locator('.brief-weekly')).toHaveCount(0);await expect(weekly).toHaveClass(/read/);await weekly.getByRole('button',{name:/Ver insight/}).click();await expect(page.locator('#weeklyInsightDialog')).toContainText('Lectura Alicanto:');await expect(page.locator('#weeklyInsightDialog').getByRole('link',{name:/Revisar fuente original/})).toHaveAttribute('href',/^https:\/\//);await page.getByRole('button',{name:'Cerrar insight'}).click()}
 await page.locator('.brief-global [data-brief-read]').click();
 await expect(page.locator('.brief-global')).toHaveCount(0);await expect(global).toHaveClass(/read/);
 await page.reload();await expect(page.locator('.brief-global,.brief-weekly')).toHaveCount(0);
 await expect(page.locator('.signal.special.read')).toHaveCount(hasWeekly?2:1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.screenshot({path:`artifacts/${test.info().project.name}-home-v2-final.png`,fullPage:true});
});
test('Date-only signals remain inside the 14-day window across UTC midnight',async({page})=>{
 await page.addInitScript(()=>{const NativeDate=Date,fixed=NativeDate.parse('2026-09-28T23:59:00Z');class FixedDate extends NativeDate{constructor(...args){super(...(args.length?args:[fixed]))}static now(){return fixed}}window.Date=FixedDate});
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 const data=await (await page.request.get('/data/free_value.json')).json();
 expect(data.weekly_insight?.event_date).toBe('2026-09-14');
 await expect(page.locator('#period')).toHaveValue('14');
 await expect(page.locator('.signal.special.weekly')).toHaveCount(1);
 await expect(page.locator('.brief-weekly')).toHaveCount(1);
});
test('Feed-only share uses Web Share and clipboard fallback without analytics',async({page})=>{
 await page.addInitScript(()=>{window.__shared=[];Object.defineProperty(navigator,'share',{configurable:true,value:payload=>{window.__shared.push(payload);return Promise.resolve()}})});
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 await expect(page.locator('#brief [data-share]')).toHaveCount(0);
 const share=page.locator('#local [data-share]').first();await expect(share).toBeVisible();await expect(share).toHaveAttribute('aria-label',/Compartir:/);
 await expect(share.locator('xpath=..')).toHaveClass(/card-status-actions/);await expect(share.locator('xpath=..').locator('[data-read],[data-special-read]')).toHaveCount(1);await expect(page.locator('.card-actions [data-share]')).toHaveCount(0);
 const targetSize=await share.evaluate(button=>({width:button.getBoundingClientRect().width,height:button.getBoundingClientRect().height}));expect(targetSize.width).toBeGreaterThanOrEqual(44);expect(targetSize.height).toBeGreaterThanOrEqual(44);
 await share.click();const shared=(await page.evaluate(()=>window.__shared))[0];expect(shared.url).toContain('#');await expect(share.locator('xpath=following-sibling::*[1]')).toHaveText('Compartido');
 await page.evaluate(()=>{delete navigator.share;window.__copied=[];Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:value=>{window.__copied.push(value);return Promise.resolve()}}})});
 await share.click();await expect(share).toHaveAttribute('data-share-result','copied');await expect(share.locator('xpath=following-sibling::*[1]')).toHaveText('Enlace copiado');expect((await page.evaluate(()=>window.__copied))[0]).toContain('#');
 await page.goto(shared.url);await expect(page.locator('#meta')).toContainText('Última actualización:');const target=new URL(shared.url).hash.slice(1),targetCard=page.locator(`[id="${target}"]`);await expect(targetCard).toBeVisible();await expect(targetCard).toBeFocused();await expect(targetCard).not.toHaveClass(/read/);await expect(page).toHaveURL(new RegExp(`#${target.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}$`));
 const specialShare=page.locator('.signal.special.global [data-share]');await expect(specialShare).toHaveAttribute('data-share',/^special-/);
 await page.goto('/#%E0%A4%A');await expect(page.locator('#meta')).toContainText('Última actualización:');await expect(page.locator('article').first()).toBeVisible();
});
test('Global read state is shared across Home and the research page',async({page})=>{
 const globalData=JSON.parse(fs.readFileSync('web/data/global_themes.json','utf8')),themeCount=globalData.themes.length,visibleCount=Math.min(themeCount,10);
 await page.goto('/');await expect(page.locator('.brief-global')).toHaveCount(1);
 const free=await (await page.request.get('/data/free_value.json')).json(),teaserId=free.global_teaser.theme_id;
 await page.locator('.signal.special.global [data-special-open]').click();
 await expect(page).toHaveURL(/global\.html#theme-/);
 await page.locator('#globalPeriod').selectOption('all');
 await expect(page.locator('#globalInbox .inbox-row')).toHaveCount(visibleCount-1);
 const theme=page.locator(`#theme-${teaserId}`);
 await expect(theme).toHaveClass(/read/);
 await theme.locator('[data-read]').click();await expect(theme).not.toHaveClass(/read/);
 await page.goto('/');await expect(page.locator('.brief-global')).toHaveCount(1);
 await page.locator('.signal.special.global [data-special-read]').click();
 await expect(page.locator('.signal.special.global [data-special-read]')).toBeFocused();
});
test('source suggestion is visible, concise and fail-closed without provider',async({page})=>{
 let captured;
 await page.route('**/api/source-suggestions',async route=>{
  captured=route.request().postDataJSON();
  await route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({id:`src_${'a'.repeat(32)}`,status:'received',message:'Gracias. Guardamos tu sugerencia para revisión.'})});
 });
 await page.goto('/');
 await page.locator('#sourcesOpen').click();
 const cta=page.locator('#source-suggestion');
 await expect(cta).toBeVisible();
 await expect(cta).toContainText('¿Falta una fuente relevante?');
 const open=page.getByRole('button',{name:'Sugerir fuente'});
 await open.focus();
 await expect(open).toBeFocused();
 await page.keyboard.press('Enter');
 const dialog=page.locator('#sourceSuggestionDialog');
 await expect(dialog).toBeVisible();
 await dialog.locator('[name="source_name"]').fill('Observatorio de Salud');
 await dialog.locator('[name="source_url"]').fill('https://example.org/publicaciones');
 await dialog.locator('[name="comment"]').fill('Revisar los informes trimestrales.');
 await dialog.getByRole('button',{name:'Enviar sugerencia'}).click();
 await expect(dialog.locator('#sourceSuggestionFeedback')).toContainText('Guardamos tu sugerencia para revisión');
 expect(Object.keys(captured).sort()).toEqual(['comment','source_name','source_url','started_at','website']);
 expect(captured.website).toBe('');

 await page.unroute('**/api/source-suggestions');
 await page.route('**/api/source-suggestions',route=>route.fulfill({status:200,contentType:'application/json',body:'{}'}));
 await dialog.locator('[name="source_name"]').fill('Otra fuente');
 await dialog.getByRole('button',{name:'Enviar sugerencia'}).click();
 await expect(dialog.locator('#sourceSuggestionFeedback')).toContainText('El envío aún no está habilitado. No guardamos tu sugerencia.');
 await page.unroute('**/api/source-suggestions');
 await page.route('**/api/source-suggestions',route=>route.fulfill({status:204,body:''}));
 await dialog.getByRole('button',{name:'Enviar sugerencia'}).click();
 await expect(dialog.locator('#sourceSuggestionFeedback')).toContainText('El envío aún no está habilitado. No guardamos tu sugerencia.');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.screenshot({path:`artifacts/${test.info().project.name}-source-suggestion.png`,fullPage:true});
});
test('source suggestion never falls back to URL serialization without JavaScript',async({browser})=>{
 const context=await browser.newContext({javaScriptEnabled:false});
 const page=await context.newPage();
 await page.goto('/');
 const form=page.locator('#sourceSuggestionForm');
 await expect(form).toHaveAttribute('method','post');
 await expect(form).toHaveAttribute('action','/api/source-suggestions');
 await expect(form.locator('button[type="submit"]')).toBeDisabled();
 expect(await page.content()).toContain('El envío requiere JavaScript y todavía no está habilitado en este navegador. No se enviaron datos.');
 expect(page.url()).not.toContain('source_name=');
 await context.close();
});
test('Cards V2 keep Bupa, sanctions and reviewed Circular 535 copy understandable',async({page})=>{
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 await page.locator('#filterDetails summary').click();
 await page.locator('#period').selectOption('90');
 const bupa=page.locator('article').filter({has:page.getByRole('heading',{name:/Bupa refuerza su red/})});
 await expect(bupa).toContainText('La Dehesa');await expect(bupa).toContainText('Clínicas Huinganal');await expect(bupa).toContainText('Mindplace en San Damián');
 await expect(bupa).toContainText('No es solo expansión física');
 await expect(bupa).not.toContainText('…');
 await expect(bupa.locator('.card-meta')).toContainText('Publicado');
 await bupa.locator('[data-detail]').click();
 await expect(page.locator('#detailBody')).toContainText('La Dehesa: inauguración');
 await expect(page.locator('#detailBody')).toContainText('Clínicas Huinganal: crecimiento mediante adquisición');
 await expect(page.locator('#detailBody')).toContainText('Mindplace San Damián');
 await expect(page.locator('#detailBody')).toContainText('capacidad nueva, compra y diversificación de servicios');
 await expect(page.locator('#detailBody')).not.toContainText('Enriquecimiento editorial');
 await page.getByRole('button',{name:'Cerrar resumen'}).click();
 const isapre=page.locator('article').filter({has:page.getByRole('heading',{name:/Pulso Isapre · datos/})});
 await expect(isapre.locator('.card-meta')).toContainText('Datos a 2026-07');
 await expect(isapre.locator('.card-meta')).toContainText('Publicado 07 sept 2026');
 await expect(isapre.locator('.card-meta')).toContainText('Validado 24 sept 2026');
 await isapre.locator('[data-detail]').click();
 await expect(page.locator('#detailBody .intel').filter({hasText:'Muestra de datos validada'}).locator('li')).toHaveCount(5);
 await expect(page.locator('#detailBody')).toContainText('2026-01 → 2026-07');
 await expect(page.locator('#detailBody')).toContainText('0.615 → 0.605');
 await expect(page.locator('#detailBody')).toContainText('72.9%');
 await expect(page.locator('#detailBody')).toContainText('cotizantes');
 await expect(page.locator('#detailBody')).toContainText('brecha acumulada');
 await expect(page.locator('#detailBody')).toContainText('No es variación mensual');
 await expect(page.locator('#detailBody .intel a').first()).toHaveAttribute('href',/superdesalud\.gob\.cl/);
 await expect(page.locator('#detailBody .sourceverify .related-item')).toHaveCount(3);
 await expect(page.locator('#detailBody .sourceverify')).toContainText('Publicado 07 sept 2026');
 await expect(page.locator('#detailBody')).toContainText('Período de datos: 2026-07');
 await expect(page.locator('#detailBody')).toContainText('Fecha de publicación: 07 sept 2026');
 await expect(page.locator('#detailBody')).toContainText('Validado: 24 sept 2026');
 await page.getByRole('button',{name:'Cerrar resumen'}).click();
 const pulse=page.locator('article').filter({has:page.getByRole('heading',{name:/Pulso de sanciones a Prestadores/})});
 await expect(pulse).toContainText('Clínica Los Carrera · 70 UF · cheque en garantía');
 await pulse.locator('[data-detail]').click();await expect(page.locator('#detailBody')).toContainText('Resoluciones incluidas en este pulso · 3');
 const sourceBeforeDetails=await page.locator('#detailBody').evaluate(el=>el.querySelector('.sourceverify').compareDocumentPosition(el.querySelector('.intel'))&Node.DOCUMENT_POSITION_FOLLOWING);
 expect(sourceBeforeDetails).toBeTruthy();
 await expect(page.locator('#detailBody .sourceverify .related-item')).toHaveCount(3);
 await expect(page.locator('#detailBody')).toContainText('Clínica Redsalud Providencia · 200 UF');
 await page.getByRole('button',{name:'Cerrar resumen'}).click();
 const tea=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:/Resolución Exenta IF\/N°11156 · TEA:/i})});
 await expect(tea).toContainText('RND');
 await tea.locator('[data-detail]').click();
 await expect(page.locator('#detailBody .normative-context')).toContainText('Contexto de la señal');
 await expect(page.locator('#detailBody .normative-context')).toContainText('15 días hábiles');
 await expect(page.locator('#detailBody .normative-context')).toContainText('1 de noviembre de 2026');
 await expect(page.locator('#detailBody')).toContainText('Registro Nacional de Discapacidad');
 await page.getByRole('button',{name:'Cerrar resumen'}).click();
 const circular=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:/Circular IF\/N°535 · Reembolsos a empleadores públicos/i})});
 await circular.locator('[data-detail]').click();await expect(page.locator('#detailBody')).toContainText('Circular IF/N°77');
 await page.locator('#detailBody .related').getByText('Normativa relacionada',{exact:false}).click();
 await expect(page.locator('#detailBody')).toContainText('Norma modificada');
 const ref=page.locator('#detailBody .related-item').filter({hasText:'Circular IF/N°77'});
 await expect(ref).toBeVisible();
 await expect(ref.getByText('Norma modificada',{exact:false})).toBeVisible();
 expect(await ref.locator('a').count()===1||await ref.getByText('enlace pendiente de verificación',{exact:false}).count()===1).toBeTruthy();
 await page.screenshot({path:`artifacts/${test.info().project.name}-cards-v2.png`,fullPage:true});
});
test('Global Intelligence mirrors Home while keeping global facts and Chile hypotheses distinct',async({page})=>{
 const globalData=JSON.parse(fs.readFileSync('web/data/global_themes.json','utf8')),themeCount=globalData.themes.length,visibleCount=Math.min(themeCount,10);
 await page.goto('/');
 await expect(page.locator('.signal.special.global [data-special-open]')).toBeVisible();
 await page.locator('.signal.special.global [data-special-open]').click();
 await expect(page.getByRole('heading',{name:'Global Intelligence',exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Ponte al día en Global Intelligence'})).toBeVisible();
 await expect(page.locator('#globalPeriod')).toHaveValue('30');
 await page.locator('#globalFilters summary').click();
 await expect(page.locator('#globalPublisher')).toBeVisible();
 await expect(page.locator('#globalSort')).toBeVisible();
 await page.locator('#globalPeriod').selectOption('all');
 await expect(page.locator('#globalMetrics')).toHaveText(`${visibleCount} temas · no leídos ${visibleCount-1}`);
 await expect(page.locator('.theme')).toHaveCount(visibleCount);
 await page.locator('[data-open]').first().click();
 await expect(page.locator('#globalMetrics')).toHaveText(`${visibleCount} temas · no leídos ${visibleCount-2}`);
 const opened=page.locator('.theme').filter({has:page.locator('details[open]')});
 await expect(opened).toContainText('Qué mirar en Chile');
 await expect(opened).toContainText('Lectura estratégica');
 await expect(opened).toContainText('Resumen ejecutivo');
 await expect(opened).toContainText('Hallazgos clave');
 await expect(opened).toContainText('Metodología y alcance');
 await expect(opened).toContainText('Hipótesis Chile');
 await expect(opened).toContainText('señales locales compatibles verificadas: 0');
 await expect(opened.getByRole('button',{name:'Volver a Ponte al día ↑'})).toBeVisible();
 const toggle=opened.locator('[data-read]');
 await toggle.click();await expect(opened.locator('details')).toHaveAttribute('open','');
 await toggle.click();await expect(opened.locator('details')).toHaveAttribute('open','');
 await opened.getByRole('button',{name:'Volver a Ponte al día ↑'}).click();
 await expect(page.locator('#globalInbox')).toBeFocused();
 await page.reload();await expect(page.locator('#globalPeriod')).toHaveValue('all');
 await expect(page.locator('.theme')).toHaveCount(visibleCount);
 await expect(page.locator('.source a').filter({hasText:'PwC'})).toHaveAttribute('href',/^https:\/\/www\.pwc\.com\//);
 await expect(page.locator('.source a[href="https://www.who.int/publications/i/item/9789240122925"]')).toContainText(/^WHO ·/);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(test.info().project.use.viewport.width+1);
 await page.screenshot({path:`artifacts/${test.info().project.name}-global-intelligence.png`,fullPage:true});
});
test('Weekly email capture requires consent and stays closed without approved provider',async({page})=>{
 await page.goto('/');
 await page.locator('#newsletterOpen').click();
 await page.getByRole('link',{name:'Cómo funciona la suscripción →'}).click();
 await expect(page.getByRole('heading',{name:'Lo importante de la semana, sin ruido.'})).toBeVisible();
 await expect(page.locator('#email')).toBeDisabled();
 await expect(page.locator('#consent')).toBeDisabled();
 await expect(page.getByRole('button',{name:'Suscribirme'})).toBeDisabled();
 await expect(page.locator('#status')).toContainText('Abriremos las suscripciones muy pronto.');
 await expect(page.getByText('Una vez por semana · solo cuando haya material relevante · puedes darte de baja cuando quieras.')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(test.info().project.use.viewport.width+1);
 await page.screenshot({path:`artifacts/${test.info().project.name}-subscription.png`,fullPage:true});
});
test('analytics never sends without explicit privacy approval even if a key is present',async({page})=>{
 let attempts=0;
 await page.route('**/data/analytics.json',route=>route.fulfill({status:200,contentType:'application/json',
   body:JSON.stringify({enabled:true,privacy_approved:false,provider:'posthog',
     project_key:'public-test-key',host:'https://us.i.posthog.com'})}));
 await page.route('https://us.i.posthog.com/**',route=>{attempts++;return route.abort()});
 await page.goto('/');
 await page.locator('#filterDetails summary').click();
 await page.locator('#period').selectOption('7');
 await expect(page.locator('#radarMetrics')).toHaveText(/^\d+ tarjetas · no leídos \d+$/);
 expect(attempts).toBe(0);
});
test('authorized analytics fixture emits only anonymous event fields',async({page})=>{
 const payloads=[];
 await page.route('**/data/analytics.json',route=>route.fulfill({status:200,contentType:'application/json',
   body:JSON.stringify({enabled:true,privacy_approved:true,provider:'posthog',
     project_key:'public-test-key',host:'https://us.i.posthog.com'})}));
 await page.route('https://us.i.posthog.com/capture/',route=>{
   payloads.push(JSON.parse(route.request().postData()));
   return route.fulfill({status:200,body:'{}'});
 });
 await page.goto('/');
 await page.locator('#filterDetails summary').click();
 await expect.poll(()=>payloads.some(p=>p.event==='filters_open')).toBe(true);
 expect(payloads.some(p=>p.event==='visit'&&typeof p.properties.returning==='boolean')).toBe(true);
 expect(new Set(payloads.map(p=>p.distinct_id)).size).toBe(payloads.length);
 for(const payload of payloads){
   expect(payload.api_key).toBe('public-test-key');
   expect(Object.keys(payload).sort()).toEqual(['api_key','distinct_id','event','properties']);
   expect(Object.keys(payload.properties).every(key=>['returning','$geoip_disable','$process_person_profile','dimension','hidden'].includes(key))).toBe(true);
   expect(JSON.stringify(payload)).not.toMatch(/source_url|email|title|https:\/\/cftorre1/);
 }
});

test('persistent editorial contract is visible in feed and brief',async({page})=>{
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 await page.locator('#filterDetails summary').click();await page.locator('#period').selectOption('90');
 const pulse=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:/Pulso Isapre/})});
 await expect(pulse).toHaveCount(1);
 await expect(page.locator('article[data-card]').filter({hasText:'Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE a Nivel Regional'})).toHaveCount(0);
 const opaque=page.locator('article[data-card] h2').filter({hasText:/^(Circular|Resolución|Oficio|Decreto).*N°\d+$/});
 await expect(opaque).toHaveCount(0);
 const c533=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:/Circular IF\/N°533 · SIL: actualiza el inventario mensual/})});
 await expect(c533).toHaveCount(1);
 await expect(c533).toContainText('Qué pasó:');
 const briefOpaque=page.locator('.briefitem strong').filter({hasText:/^(Circular|Resolución|Oficio|Decreto).*N°\d+$/});
 await expect(briefOpaque).toHaveCount(0);
});

test('Pulso Isapre leads with executive table and statistics use the value ladder',async({page})=>{
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 await page.locator('#filterDetails summary').click();await page.locator('#period').selectOption('90');
 await expect(page.locator('article[data-card]').filter({hasText:'Resonancia Magnética del Biobío'})).toHaveCount(0);
 const radar=await (await page.request.get('/data/radar_today.json')).json();
 for(const [needle,copy] of [
   ['Estadística Trimestral de Casos GES','casos GES acumulados por problema de salud'],
   ['Series Estadísticas del Sistema ISAPRE 1990-2025','promedio anual de beneficiarios Isapre'],
   ['Boletín Estadístico Informativo IP','cortes de acreditación, mediación, reclamos y RNPI'],
 ]){
   const signal=radar.signals.find(x=>(x.title||'').includes(needle));
   expect(signal,needle+' missing from snapshot').toBeTruthy();
   const age=Math.floor((Date.now()-Date.parse(signal.event_date+'T00:00:00Z'))/86400000);
   const card=page.locator('article[data-card]').filter({hasText:needle});
   if(age<=91){await expect(card).toHaveCount(1);await expect(card).toContainText(copy)}
   else await expect(card).toHaveCount(0);
 }
 const pulse=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:/Pulso Isapre/})});
 await expect(pulse).toHaveCount(1);await pulse.locator('[data-detail]').click();
 const table=page.locator('#detailBody .summary-table');
 await expect(table).toBeVisible();
 await expect(table).toContainText('Resumen ejecutivo Isapre');
 for(const label of ['Beneficiarios','Cotizantes','Cargas','Suscripciones','Desahucios voluntarios','Movilidad'])await expect(table).toContainText(label);
 await expect(table).toContainText('2.487.497');await expect(table).toContainText('-17.700');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});


test('committee HOLD/REJECT and failed publication contracts do not render as individual feed cards',async({page})=>{
  await page.goto('/');
  const response=await page.request.get('/data/radar_today.json');
  const data=await response.json();
  const hidden=(data.signals||[]).filter(s=>{
    const verdict=String(s.editorial_committee?.verdict||'PASS').toUpperCase();
    const types=Array.isArray(s.signal_types)?s.signal_types.map(x=>String(x).toLowerCase()):[];
    const core=Boolean((s.display_title||s.title)&&s.signal_types?.length&&s.scopes?.length&&s.event_date&&s.source_name&&s.source_url&&(s.card_what||s.what_happened)&&(s.card_why||s.why_it_matters));
    const contract=core&&(!types.includes('normativa')||Boolean(s.normative_document_label));
    return s.feed_visibility===false||['HOLD','REJECT'].includes(verdict)||!contract;
  });
  for(const signal of hidden.slice(0,12)){
    await expect(page.locator('.signal[data-card]').filter({hasText:signal.display_title||signal.title})).toHaveCount(0);
  }
});


test('period is visible outside filters, persisted without duplicating metric copy, and resettable',async({page})=>{
 await page.goto('/');
 const period=page.locator('#period');
 await expect(period).toBeVisible();
 await expect(period.locator('xpath=ancestor::details')).toHaveCount(0);
 await period.selectOption('90');
 await expect(period).toHaveValue('90');
 await expect(page.locator('#radarMetrics')).not.toContainText('período');
 await page.reload();
 await expect(period).toHaveValue('90');
 await expect(page.locator('#radarMetrics')).not.toContainText('período');
 await page.locator('#filterDetails summary').click();
 await page.locator('#resetFilters').click();
 await expect(period).toHaveValue('14');
 await expect(page.locator('#sort')).toHaveValue('date');
 await expect(page.locator('#radarMetrics')).not.toContainText('14 días');
 const box=await period.boundingBox();expect(box.width).toBeLessThanOrEqual(test.info().project.name==='mobile'?110:150);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});


test('Home hero is compact, one-line and exposes subscription plus Global Intelligence',async({page})=>{
 await page.goto('/');
 await expect(page.locator('.hero-purpose')).toHaveText('Señales clave del sector salud, claras y a tiempo.');
 await expect(page.locator('.newsletter-strip')).toContainText('Suscríbete para recibir en tu correo las señales más importantes');
 await expect(page.locator('.newsletter-strip #newsletterOpen')).toHaveText('Suscríbete');
 await expect(page.locator('a.header-premium')).toHaveAttribute('href','global.html');
 await expect(page.locator('button.premium-access')).toHaveText('Acceso PREMIUM');
 if(test.info().project.name==='mobile'){
   const title=await page.locator('#radarTitle').boundingBox();
   const metrics=await page.locator('#radarMetrics').boundingBox();
   const source=await page.locator('#sourcesOpen').boundingBox();
   expect(metrics.y).toBeGreaterThan(title.y);
   expect(source.y).toBeGreaterThan(metrics.y);
   expect(await page.locator('.hero-purpose').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBeTruthy();
 }
});

test('conversion surfaces lead with value and hide internal implementation status',async({page})=>{
 await page.goto('/');
 await page.locator('#earlyAccessOpen').click();
 await expect(page.locator('#earlyAccessDialog')).toContainText('Ve más allá de la señal.');
 await expect(page.locator('#earlyAccessDialog')).toContainText('Inscríbete al acceso anticipado');
 await expect(page.locator('#earlyAccessDialog')).not.toContainText('todavía no hay cuentas ni pagos');
 await page.getByRole('button',{name:'Cerrar acceso Premium'}).click();
 await page.locator('#newsletterOpen').click();
 await expect(page.locator('#newsletterDialog')).toContainText('Lo importante de la semana, directo a tu correo.');
 await expect(page.locator('#newsletterDialog')).not.toContainText('proveedor');
});

test('sources are grouped by decision value and expose freshness layers',async({page})=>{
 await page.goto('/');
 await page.locator('#sourcesOpen').click();
 await expect(page.locator('#sourcesList')).toContainText('Organismos públicos y reguladores');
 await expect(page.locator('#sourcesList')).toContainText('Noticias y mercado');
 const first=page.locator('#sourcesList .source-row').first();
 await expect(first).toContainText('Última consulta');
 await expect(first).toContainText('Última señal detectada');
 await expect(first).toContainText('Última seleccionada');
 await expect(page.locator('#source-suggestion')).toContainText('¿Falta una fuente relevante?');
});


test('priority statistical releases use compact tables and collapsed traceability',async({page})=>{
 await page.goto('/');
 await page.locator('#filterDetails summary').click();
 await page.locator('#period').selectOption('90');
 const radar=await (await page.request.get('/data/radar_today.json')).json();
 const cases=[
  ['Estadística Trimestral de Casos GES',5],
  ['Series Estadísticas del Sistema ISAPRE',2],
  ['Boletín Estadístico Informativo IP',6],
 ];
 for(const [needle,minRows] of cases){
   const s=radar.signals.find(x=>(x.title||'').includes(needle));
   expect(s,needle+' missing').toBeTruthy();
   expect((s.data_insights||[]).length,needle+' repeated insight list').toBe(0);
   expect(s.summary_table?.rows?.length||0,needle+' table').toBeGreaterThanOrEqual(minRows);
   expect(s.methodology_visibility).toBe('collapsed');
   expect(s.card_why_optional).toBe(true);
   expect(s.incremental_value_gate?.table).toBeTruthy();
   expect(s.data_insight_evidence?.length||0,needle+' evidence').toBeGreaterThan(0);
 }
 const ges=radar.signals.find(x=>(x.title||'').includes('Estadística Trimestral de Casos GES'));
 expect(ges.summary_table.columns).toEqual(['Problema de salud','Fonasa (casos)','Isapre (casos)','Total (casos)','Isapre (%)']);
 expect(ges.summary_table.rows.every(r=>r.cells?.length===5&&!/^\d+$/.test(r.cells[0]))).toBe(true);
 const series=radar.signals.find(x=>(x.title||'').includes('Series Estadísticas del Sistema ISAPRE'));
 expect(series.summary_table.rows.map(r=>r.cells[0])).toEqual(['Beneficiarios promedio anual','Casos GES']);
 expect(series.summary_table.rows.every(r=>r.cells[3]+r.cells[5]===r.cells[4])).toBe(true);
 const fin=radar.signals.find(x=>(x.title||'').includes('Estadísticas Financieras del Sistema ISAPRE'));
 if(fin){
   expect(fin.summary_table.columns).toEqual(['Isapre','Ingresos (CLP millones)','Resultado operacional (CLP millones)','Utilidad/pérdida neta (CLP millones)']);
   expect(fin.data_insight_evidence[0].source_url).toContain('finan_ifrs_mar_2026_web_v2.xls');
   const card=page.locator('article[data-card]').filter({hasText:'Estadísticas Financieras del Sistema ISAPRE'});
   await expect(card).not.toContainText('Por qué importa:');
   await card.locator('[data-detail]').click();
   const detail=page.locator('#detailBody');
   await expect(detail.locator('.summary-table')).toBeVisible();
   await page.locator('#detailDialog [data-close]').click();
 }
 const bulletin=radar.signals.find(x=>(x.title||'').includes('Boletín Estadístico Informativo IP'));
 expect(new Set(bulletin.summary_table.rows.map(r=>r.cells[0]))).toEqual(new Set(['Acreditación','Mediación','Reclamos','RNPI']));
 const bulletinCard=page.locator('article[data-card]').filter({hasText:'Boletín Estadístico Informativo IP'});
 await bulletinCard.locator('[data-detail]').click();
 const detail=page.locator('#detailBody');
 await expect(detail.locator('details.statistical-methodology')).not.toHaveAttribute('open','');
 await expect(detail).not.toContainText('Muestra de datos validada');
 await expect(detail.locator('.source')).toContainText('Fuente original');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.getByRole('button',{name:'Cerrar resumen'}).click();
});

test('Normative V2.1 puts document, subject and action in each current headline',async({page})=>{
 await page.goto('/');
 await page.locator('#filterDetails summary').click();
 await page.locator('#period').selectOption('90');
 const radar=await (await page.request.get('/data/radar_today.json')).json();
 const expected=[
  ['11156',/TEA/i,/acoge|mantiene|proh[ií]be/i],
  ['10670',/Metas EMP/i,/rechaza|vigente/i],
  ['10615',/Plan MAS2026/i,/acoge|ajusta/i],
  ['535',/reembolsos|empleadores públicos/i,/proh[ií]be|compensar/i],
  ['534',/bonos/i,/aceptar/i],
  ['533',/SIL|inventario/i,/actualiza/i],
  ['9994',/afiliación electrónica/i,/rechaza|suspender/i],
  ['532',/afiliación electrónica/i,/refuerza|controles/i],
  ['531',/Metas EMP/i,/traslada/i],
  ['8760',/CAEC/i,/suspende|pausa/i],
  ['530',/contralores médicos/i,/exige|informar/i],
  ['529',/CAEC/i,/vincula|cobertura/i]
 ];
 for(const [number,subject,action] of expected){
  const signal=radar.signals.find(x=>x.source_url?.includes('n'+number)&&x.signal_types?.includes('Normativa'));
  expect(signal,number).toBeTruthy();
  const title=signal.display_title;
  expect(title).toContain(signal.normative_document_label||signal.legal_identity);
  expect(title).toMatch(subject);expect(title).toMatch(action);
  expect(signal.normative_context).toBeTruthy();
  expect(signal.normative_context).not.toContain(title);
  const article=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:title,exact:true})});
  const age=Math.floor((Date.now()-Date.parse(signal.event_date+'T00:00:00Z'))/86400000);
  if(age<=91){
    await expect(article).toHaveCount(1);
    await expect(article.locator('.normative-identity')).toHaveCount(0);
    await article.locator('[data-detail]').click();
    await expect(page.locator('#detailBody .normative-context')).toBeVisible();
    await expect(page.locator('#detailBody .normative-context')).toContainText('Contexto de la señal');
    await expect(page.locator('#detailBody .normative-context')).not.toContainText(title);
    await page.getByRole('button',{name:'Cerrar resumen'}).click();
  } else await expect(article).toHaveCount(0);
 }
});
