const {test,expect,selectPeriod,selectLane}=require('./fixtures.cjs');
const fs=require('node:fs');fs.mkdirSync('artifacts',{recursive:true});
const path=require('node:path');
const STATISTICAL_URLS={
 ges:'https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-trimestral-de-casos-ges-auge-de-fonasa-y-sistema-isapre-a-marzo-2026/',
 series:'https://www.superdesalud.gob.cl/biblioteca-digital/series-estadisticas-del-sistema-isapre-1990-2025/',
 bulletin:'https://www.superdesalud.gob.cl/biblioteca-digital/boletin-estadistico-informativo-ip-junio-2026/',
};
let historicalSignals;
function knownHistoricalSignal(predicate){
 historicalSignals ||= JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../data/history/superintendencia_signals.json'),'utf8')).signals;
 const signal=historicalSignals.find(predicate);
 expect(signal,'Known source document must remain in durable history').toBeTruthy();
 return signal;
}
function withinSnapshotHorizon(radar,source){
 const days=historicalSignals.filter(s=>/^\d{4}-\d{2}-\d{2}$/.test(s.event_date||'')).map(s=>Date.parse(s.event_date+'T00:00:00Z'));
 expect(days.length,'Independent durable history needs a dated source to define the rolling window').toBeGreaterThan(0);
 expect(source.event_date,'Known source document needs its original publication date').toMatch(/^\d{4}-\d{2}-\d{2}$/);
 // The window is anchored to the snapshot under test (a dated fixture is curated
 // as of ALICANTO_FIXTURE_AS_OF), not to the newest capture in durable history.
 const asOf=/^\d{4}-\d{2}-\d{2}$/.test(radar?.date||'')?Date.parse(radar.date+'T00:00:00Z'):Math.max(...days);
 const age=(asOf-Date.parse(source.event_date+'T00:00:00Z'))/86400000;
 return age>=0&&age<=90;
}
test('Home V2 loads, filters persist and compact triage remains stable',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 await expect(page.locator('#period')).toHaveValue('30');await expect(page.locator('#sort')).toHaveValue('date');
 // Dirección 27-oct-2026 (Home B): the hero title leaves the visible layout so news reach the first
 // viewport; it stays as the page's only h1 for assistive technology.
 await expect(page.getByRole('heading',{level:1,name:'Encuentra lo que importa',exact:true})).toHaveCount(1);
 await expect(page.locator('h1')).toHaveClass(/sr-only/);
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
 await expect(page.locator('#radarTitle')).toHaveText('Tu bandeja');
 await expect(page.locator('#radarMetrics')).toHaveText(/^(\d+ pendientes|Estás al día)$/);
 const laneCount=async lane=>Number(await page.locator(`[data-lane="${lane}"] span`).innerText());
 const initialMetrics=[await laneCount('t'),await laneCount('p')];
 await expect(page.locator('[data-lane="p"]')).toHaveAttribute('aria-pressed','true');
 await page.locator('#sourcesOpen').click();await expect(page.locator('#sourcesDialog')).toBeVisible();
 await expect.poll(()=>page.locator('#sourcesList .source-row').count()).toBeGreaterThan(0);
 await expect(page.locator('#sourcesDialog')).toContainText('¿Falta una fuente relevante?');
 if(await page.locator('#sourcesMore').isVisible())await expect(page.locator('#sourcesMore')).toBeHidden();
 await expect.poll(()=>page.locator('#sourcesList .source-row').count()).toBeGreaterThan(10);
 await page.getByRole('button',{name:'Cerrar fuentes'}).click();
 await page.locator('#filterDetails summary').click();
 await expect(page.locator('#filterDetails')).toContainText('Tus filtros se guardan automáticamente');
 await expect(page.locator('#period')).toBeVisible();await expect(page.locator('#sort')).toBeVisible();
 const selectTops=await page.locator('.select-grid label').evaluateAll(xs=>xs.map(x=>Math.round(x.getBoundingClientRect().top)));
 expect(new Set(selectTops).size).toBe(1);
 await selectPeriod(page,'90');
 const extendedMetrics=[await laneCount('t'),await laneCount('p')];
 expect(extendedMetrics[0]).toBeGreaterThanOrEqual(initialMetrics[0]);
 // Single inbox: no duplicated brief list; every row is a compact single-column item.
 await expect(page.locator('.briefrow,.briefitem')).toHaveCount(0);
 const visibleTriage=await page.locator('#local .signal.item').count();
 expect(visibleTriage).toBeGreaterThanOrEqual(3);
 await expect(page.locator('article').first()).toBeVisible();
 if(test.info().project.name==='mobile'){
  const cards=await page.locator('article').evaluateAll(xs=>xs.slice(0,3).map(x=>({height:Math.round(x.getBoundingClientRect().height),title:x.querySelector('h2')?.textContent||''})));
  expect(cards.length).toBe(3);expect(Math.max(...cards.map(x=>x.height)),JSON.stringify(cards)).toBeLessThan(600);
 }
 await page.screenshot({path:`artifacts/${test.info().project.name}-browse.png`,fullPage:true});
 const opened=await page.locator('#local article[data-card]').first().getAttribute('data-card');
 await page.locator('#local .title-open').first().click();
 await expect(page.locator(`#local [data-card="${opened}"]`)).toHaveClass(/read/);
 await expect(page.locator('#signalDetail')).toBeVisible();await expect(page.locator('#closeDetail')).toBeFocused();await page.keyboard.press('Escape');
 // Opening counts as reading (Dirección 28-oct, punto 3): no bar under the filters; the row itself says
 // "Leída · Deshacer" for a moment, then leaves Pendientes.
 await expect(page.locator('.undo-bar,#undoBar')).toHaveCount(0);
 await expect(page.locator(`#local [data-card="${opened}"] .row-undo`)).toContainText('Leída');await expect(page.locator(`#local [data-card="${opened}"] .row-undo button`)).toHaveText('Deshacer');
 await expect(page.locator(`#local [data-card="${opened}"]`)).toHaveCount(0,{timeout:12000});
 await selectLane(page,'t');await expect(page.locator(`#local [data-card="${opened}"]`)).toHaveClass(/read/);
 const ids=await page.locator('article').evaluateAll(xs=>xs.map(x=>x.id));expect(new Set(ids).size).toBe(ids.length);
 // In Todas, marking read never reorders: the row folds in place.
 const order=await page.locator('#local article[data-card]').evaluateAll(xs=>xs.map(x=>x.id));
 await page.locator('#local article[data-card]:not(.read)').first().getByRole('button',{name:/Marcar/}).click();
 expect(await page.locator('#local article[data-card]').evaluateAll(xs=>xs.map(x=>x.id))).toEqual(order);
 expect((await page.locator('article').evaluateAll(xs=>xs.map(x=>x.id))).sort()).toEqual(ids.sort());
 await expect(page.locator('article').first().locator('.intel,.related')).toHaveCount(0);
 const withDepth=page.locator('article:has([data-detail])').first();await withDepth.locator('[data-detail]').first().click();
 await expect(page.locator('#signalDetail')).toBeVisible();await page.getByRole('button',{name:'Cerrar ficha'}).click();
 // Choosing a period closes the filters dropdown (Dirección 27-oct 22:44, punto 4): reopen it to pick a topic.
 // Dirección 28-oct (punto 4): only Actores and Temas filter; there is no Formato or Entidades facet.
 await page.locator('#filterDetails summary').click();
 await expect(page.locator('#typeFilters,#entitySearch')).toHaveCount(0);
 await page.locator('#interestFilters [data-interest="normativa"]').click();
 await expect(page.locator('article').first()).toBeVisible();
 expect(await laneCount('t')).toBe(await page.locator('#local article[data-card]').count());
 expect(await laneCount('p')).toBe(await page.locator('#local article[data-card]:not(.read)').count());
 await page.reload();await expect(page.locator('#period')).toHaveValue('90');
 await page.locator('#filterDetails summary').click();
 await expect(page.locator('#interestFilters [data-interest="normativa"]')).toHaveAttribute('aria-pressed','true');
 await page.locator('#interestFilters .tog-all').click();
 const noOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1);expect(noOverflow).toBeTruthy();
 fs.writeFileSync(`artifacts/${test.info().project.name}-home-v2-triage.json`,JSON.stringify({visible_triage_rows:visibleTriage,filter_persisted:true,no_horizontal_overflow:noOverflow},null,2));
 expect(errors).toEqual([]);
 await page.screenshot({path:`artifacts/${test.info().project.name}-radar.png`,fullPage:true});
});
test('Inbox shows every unread signal, supports direct read with undo and persists it',async({page})=>{
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 const rows=page.locator('#local article[data-card]');await expect(rows.first()).toBeVisible();
 const initial=await rows.count();
 // Pendientes is the inbox: every visible unread signal, and only those; big things live outside it.
 expect(initial).toBe(Number(await page.locator('[data-lane="p"] span').innerText()));expect(initial).toBeGreaterThan(4);
 await expect(page.locator('#local article.read')).toHaveCount(0);await expect(page.locator('#local article[data-special]')).toHaveCount(0);
 const first=await rows.first().getAttribute('data-card');
 // Undo lives on the row (Dirección 28-oct, punto 3): it stays in place as read with "Leída · Deshacer".
 await rows.first().locator('[data-read]').click();
 const pill=page.locator(`#local [data-card="${first}"] .row-undo`);await expect(pill).toContainText('Leída');
 await expect(page.locator(`#local [data-card="${first}"]`)).toHaveClass(/read/);await expect(rows).toHaveCount(initial);
 await pill.getByRole('button',{name:'Deshacer'}).click();await expect(pill).toHaveCount(0);await expect(page.locator(`#local [data-card="${first}"]`)).not.toHaveClass(/read/);
 await expect(page.locator(`#local [data-card="${first}"] .title-open`)).toBeFocused();
 await page.locator(`#local [data-card="${first}"] [data-read]`).click();await page.mouse.move(0,0);await page.locator('#lanes .lane.on').focus();await expect(rows).toHaveCount(initial-1,{timeout:12000});
 await page.reload();await expect(page.locator('#meta')).toContainText('Última actualización:');
 await expect(rows).toHaveCount(initial-1);await expect(page.locator(`#local [data-card="${first}"]`)).toHaveCount(0);
 await selectLane(page,'l');await expect(page.locator(`#local [data-card="${first}"]`)).toHaveClass(/read/);
 await selectLane(page,'p');
 await page.locator('#filterDetails summary').click();await selectPeriod(page,'90');
 const deep=await rows.count();expect(deep).toBeGreaterThan(4);
 await page.locator('#markAllRead').click();await expect(rows).toHaveCount(0);await expect(page.locator('#local')).toContainText('Estás al día');
 await expect(page.locator('#local .feed-undo')).toContainText(`${deep} señales marcadas como leídas`);
 await page.locator('#local .feed-undo').getByRole('button',{name:'Deshacer'}).click();await expect(rows).toHaveCount(deep);
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
// Dirección 27-oct-2026 (Home B): Insight and Global are always-present accordion rows. Reading one
// changes its mark (Nuevo → Leído) and keeps it in 'Esta semana'; it no longer moves to the Leídas lane.
test('Big things stay as accordions with a read mark that persists',async({page})=>{
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 const source=await page.request.get('/data/free_value.json'),data=await source.json();
 const hasWeekly=await page.evaluate(w=>weeklyFresh(w),data.weekly_insight);
 const global=page.locator('#bigThings .big-feature.global'),weekly=page.locator('#bigThings .big-feature.weekly');
 await expect(global).toHaveCount(1);await expect(weekly).toHaveCount(hasWeekly?1:0);
 // The week's insight leads; the outside view follows. Neither repeats inside the inbox.
 expect(await page.locator('#bigThings .big-feature').evaluateAll(xs=>xs.map(x=>x.classList.contains('weekly')?'weekly':'global'))).toEqual(hasWeekly?['weekly','global']:['global']);
 await expect(page.locator('#local [data-special]')).toHaveCount(0);await expect(page.locator('.big-anchor')).toHaveCount(0);
 // A Global theme on editorial HOLD (BCBSA) is never promoted.
 await expect(page.locator('[data-special="global:global-ai-coding-payer-cost-2026"]')).toHaveCount(0);
 await expect(page.locator('#bigThings .big-feature .card-meta')).toHaveCount(hasWeekly?2:1);await expect(global.locator('.card-meta')).toContainText('·');
 if(hasWeekly){const n=(data.weekly_insight.sources||[]).filter(x=>/^https:\/\//.test(x.url||'')).length;await expect(weekly.locator('.big-eyebrow')).toHaveText(n>1?`Insight de la semana · ${n} fuentes`:'Insight de la semana');await expect(weekly.locator('.big-eyebrow')).not.toContainText(/cruzad/i)}
 const fills=await page.locator('#bigThings .big-feature').evaluateAll(rows=>rows.map(row=>getComputedStyle(row).backgroundColor));expect(new Set(fills).size).toBe(hasWeekly?2:1);
 const readTargets=await page.locator('#bigThings [data-special-read]').evaluateAll(buttons=>buttons.map(button=>({width:button.getBoundingClientRect().width,height:button.getBoundingClientRect().height})));expect(readTargets.every(({width,height})=>width>=44&&height>=44)).toBeTruthy();
 await expect(page.locator('.hero-purpose')).toHaveText('Señales clave del sector salud, claras y a tiempo.');
 // Collapsed by default: the chevron reveals the teaser without marking it read.
 await expect(global.locator('.acc-state')).toHaveText('Nuevo');await expect(global.locator('.acc-body')).toBeHidden();
 await global.locator('[data-special-toggle]').click();await expect(global.locator('.acc-body')).toBeVisible();await expect(global.locator('[data-special-toggle]')).toHaveAttribute('aria-expanded','true');await expect(global).not.toHaveClass(/read/);
 await global.locator('[data-special-toggle]').click();await expect(global.locator('.acc-body')).toBeHidden();
 if(hasWeekly){await expect(weekly).toContainText(data.weekly_insight.insight_title);await weekly.locator('[data-special-read]').click();await expect(weekly).toHaveClass(/read/);await expect(weekly.locator('.acc-state')).toHaveText('Leído')}
 await global.locator('[data-special-read]').click();await expect(global).toHaveClass(/read/);await expect(global).toHaveCount(1);await expect(global.locator('.acc-state')).toHaveText('Leído');
 await expect(page.locator('#bigThings')).toBeVisible();await expect(global.locator('[data-special-read]')).toBeFocused();
 await selectLane(page,'l');await expect(page.locator('#local [data-special]')).toHaveCount(0);
 if(hasWeekly){await weekly.locator('.title-open').click();await expect(page.locator('#weeklyInsightDialog')).toContainText('Lectura Alicanto');await expect(page.locator('#weeklyInsightDialog .wi-notes a').first()).toHaveAttribute('href',/^https:\/\//);await page.getByRole('button',{name:'Cerrar insight'}).click()}
 await page.reload();await expect(page.locator('#bigThings .big-feature')).toHaveCount(hasWeekly?2:1);await expect(page.locator('#bigThings .big-feature.read')).toHaveCount(hasWeekly?2:1);await expect(page.locator('#bigThings .acc-body:visible')).toHaveCount(0);
 // Marking unread restores the mark.
 await global.locator('[data-special-read]').click();await expect(global).not.toHaveClass(/read/);await expect(global.locator('.acc-state')).toHaveText('Nuevo');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.screenshot({path:`artifacts/${test.info().project.name}-home-v2-final.png`,fullPage:true});
});
test('Expired weekly insight stays hidden while its original signal remains in history',async({page})=>{
 await page.addInitScript(()=>{const NativeDate=Date,fixed=NativeDate.parse('2026-10-11T03:30:00Z');class FixedDate extends NativeDate{constructor(...args){super(...(args.length?args:[fixed]))}static now(){return fixed}}window.Date=FixedDate});
 await page.route('**/data/free_value.json',async route=>{const response=await route.fetch(),data=await response.json();data.weekly_insight={id:'stale-september',editorial_review_pass:true,event_date:'2026-09-14',freshness_anchor_date:'2026-09-14',title:'Expired',source_url:'https://www.superdesalud.gob.cl/normativa/circular-if-n535/'};await route.fulfill({response,json:data})});
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 await expect(page.locator('.big-feature.weekly,.special-row.weekly')).toHaveCount(0);
 await selectPeriod(page,'90');
 await expect(page.locator('.big-feature.weekly,.special-row.weekly')).toHaveCount(0);
 await expect(page.locator('article.signal').filter({hasText:'Circular IF/N°535'})).toHaveCount(1);
});
test('Feed-only share uses Web Share and clipboard fallback without analytics',async({page})=>{
 await page.addInitScript(()=>{window.__shared=[];Object.defineProperty(navigator,'share',{configurable:true,value:payload=>{window.__shared.push(payload);return Promise.resolve()}})});
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 await expect(page.locator('#brief [data-share]')).toHaveCount(0);
 const share=page.locator('#local [data-share]').first();await expect(share).toBeVisible();await expect(share).toHaveAttribute('aria-label',/Compartir:/);
 await expect(share.locator('xpath=ancestor::div[contains(@class,"card-meta")]')).toHaveCount(1);await expect(share.locator('xpath=ancestor::article[1]').locator('[data-read]')).toHaveCount(1);await expect(page.locator('.card-actions [data-share]')).toHaveCount(0);
 const targetSize=await share.evaluate(button=>({width:button.getBoundingClientRect().width,height:button.getBoundingClientRect().height}));expect(targetSize.width).toBeGreaterThanOrEqual(44);expect(targetSize.height).toBeGreaterThanOrEqual(44);
 await share.click();const shared=(await page.evaluate(()=>window.__shared))[0];expect(shared.url).toContain('#');await expect(share.locator('xpath=following-sibling::*[1]')).toHaveText('Compartido');
 await page.evaluate(()=>{delete navigator.share;window.__copied=[];Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:value=>{window.__copied.push(value);return Promise.resolve()}}})});
 await share.click();await expect(share).toHaveAttribute('data-share-result','copied');await expect(share.locator('xpath=following-sibling::*[1]')).toHaveText('Enlace copiado');expect((await page.evaluate(()=>window.__copied))[0]).toContain('#');
 await page.goto(shared.url);await expect(page.locator('#meta')).toContainText('Última actualización:');const target=new URL(shared.url).hash.slice(1),targetCard=page.locator(`[id="${target}"]`);await expect(targetCard).toBeVisible();await expect(targetCard).toBeFocused();await expect(targetCard).not.toHaveClass(/read/);await expect(page).toHaveURL(new RegExp(`#${target.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}$`));
 const specialShare=page.locator('#bigThings .big-feature.global [data-share]');await expect(specialShare).toHaveAttribute('data-share',/^special-/);
 await page.goto('/#%E0%A4%A');await expect(page.locator('#meta')).toContainText('Última actualización:');await expect(page.locator('article').first()).toBeVisible();
});
test('Global read state is shared across Home and the research page',async({page})=>{
 const globalData=JSON.parse(fs.readFileSync('web/data/global_themes.json','utf8')),themeCount=globalData.themes.length,visibleCount=themeCount;
 await page.goto('/');await expect(page.locator('#bigThings .big-feature.global')).toHaveCount(1);
 const free=await (await page.request.get('/data/free_value.json')).json(),teaserId=free.global_teaser.theme_id;
 await page.locator('#bigThings .big-feature.global .title-open[data-special-open]').first().click();
 await expect(page).toHaveURL(/global\.html#theme-/);await expect(page.locator('#globalDetail')).toBeVisible();await page.keyboard.press('Escape');
 await page.locator('#globalPeriod').selectOption('all');
 // Filter its publisher to verify read-state persistence independently of rank.
 const teaser=globalData.themes.find(t=>t.id===teaserId);
 const publisher=teaser.sources.map(s=>s.publisher).sort((a,b)=>globalData.themes.filter(t=>t.sources.some(s=>s.publisher===a)).length-globalData.themes.filter(t=>t.sources.some(s=>s.publisher===b)).length)[0];
 // Global homologated to the Home bar A (Dirección 27-oct 23:13): sources are a multi-select in the filters
 // dropdown and read status is the Pendientes · Leídas · Todas control; Todas lists read and unread rows.
 await page.locator('#globalFilters summary').click();
 await page.locator(`#globalPublisher [data-publisher="${publisher}"]`).click();await page.keyboard.press('Escape');
 await expect(page.locator('#globalFilterLabel')).toHaveText(publisher);
 const publisherCount=globalData.themes.filter(t=>t.sources.some(s=>s.publisher===publisher)).length;
 await expect(page.locator('#globalLanes [data-lane="p"] span')).toHaveText(String(publisherCount-1));
 await expect(page.locator('.theme')).toHaveCount(publisherCount-1);
 await page.locator('#globalLanes [data-lane="t"]').click();
 await expect(page.locator('.theme')).toHaveCount(publisherCount);
 const theme=page.locator(`#theme-${teaserId}`);
 await expect(theme).toHaveClass(/read/);
 await theme.locator('[data-read]').click();await expect(theme).not.toHaveClass(/read/);
 await page.goto('/');await expect(page.locator('#bigThings .big-feature.global')).toHaveCount(1);
 await page.locator('#bigThings .big-feature.global [data-special-read]').click();
 // Dirección 27-oct-2026: a read special stays in place with its read mark; focus stays on its toggle.
 await expect(page.locator('#bigThings .big-feature.global')).toHaveClass(/read/);await expect(page.locator('#bigThings .big-feature.global [data-special-read]')).toBeFocused();
});
// Dirección 27-oct 23:13: Global uses the Home header and bar A; mark-all works on the visible themes with undo.
test('Global shares header, bar A and mark-all with the Home',async({page})=>{
 await page.goto('/global.html');await page.locator('#globalPeriod').selectOption('all');
 for(const [name,href] of [['Chile','index.html'],['Global','global.html'],['Newsletter','subscription.html']])expect(await page.locator(`.topnav a[href="${href}"]`).evaluate(el=>(el.dataset.short||el.textContent).trim())).toBe(name);
 await expect(page.locator('.topnav a[aria-current="page"]')).toHaveAttribute('href','global.html');
 const rows=page.locator('#themes .theme');await expect(rows.first()).toBeVisible();const total=await rows.count();expect(total).toBeGreaterThan(2);
 await expect(page.locator('#globalLanes [data-lane="p"]')).toHaveAttribute('aria-pressed','true');
 await page.locator('#globalMarkAll').click();await expect(rows).toHaveCount(0);await expect(page.locator('#themes .feed-undo')).toContainText(`${total} temas marcados como leídos`);
 await expect(page.locator('#themes')).toContainText('Estás al día');
 await page.locator('#themes .feed-undo').getByRole('button',{name:'Deshacer'}).click();await expect(rows).toHaveCount(total);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});
// Independent review of PR #80 (PASS_WITH_NOTES): header Newsletter opens the dialog, the dropdown closes when
// focus leaves it, controls have 44px touch areas, and at 320px PREMIUM stays whole with a two-line bar.
test('review notes: newsletter dialog, focus-out close, touch areas and 320px bar',async({page})=>{
 await page.goto('/');await expect(page.locator('#local article[data-card]').first()).toBeVisible();
 await page.locator('.topnav .header-newsletter').click();await expect(page.locator('#newsletterDialog')).toBeVisible();expect(page.url()).not.toContain('subscription.html');
 await page.getByRole('button',{name:'Cerrar resumen semanal'}).click();
 await page.locator('#filterDetails summary').click();await expect(page.locator('#filterDetails')).toHaveAttribute('open','');
 const hit=await page.evaluate(()=>{const area=el=>{const r=el.getBoundingClientRect(),a=getComputedStyle(el,'::after'),b=getComputedStyle(el,'::before');const ext=p=>p.content&&p.content!=='none'&&p.position==='absolute'?Math.max(0,-parseFloat(p.top)||0)+Math.max(0,-parseFloat(p.bottom)||0):0;return r.height+Math.max(ext(a),ext(b))};return{period:area(document.querySelector('#period')),summary:area(document.querySelector('#filterDetails summary')),row:area(document.querySelector('#interestFilters .tog[data-interest]:not([data-interest=""])')),reset:area(document.querySelector('#resetFilters')),done:area(document.querySelector('#filterDone'))}});
 for(const [k,v] of Object.entries(hit))expect(v,k).toBeGreaterThanOrEqual(44);
 await page.locator('#markAllRead').focus();await expect(page.locator('#filterDetails')).not.toHaveAttribute('open','');
 await page.setViewportSize({width:320,height:700});
 const bar=await page.evaluate(()=>({h:document.querySelector('.radar-unit').getBoundingClientRect().height,premium:document.querySelector('.premium-access').getBoundingClientRect().right,w:innerWidth}));
 // Two lines with Inter; at most three with wider fallback fonts (CI runners have no Inter) — Dirección/review: 2 or 3 lines.
 expect(bar.premium).toBeLessThanOrEqual(bar.w);expect(bar.h).toBeLessThanOrEqual(140);
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
 await selectPeriod(page,'90');
 // Rights policy (Dirección 28-oct-2026): the Bupa piece is paywalled DF, so the card keeps the
 // publisher headline and public lead only; the editorial rewrite built on the locked body is gone.
 const bupa=page.locator('article').filter({has:page.getByRole('heading',{name:/Bupa acelera inversiones/})});
 await bupa.locator('[data-detail]').first().click();await expect(page.locator('#detailBody')).toContainText('La Dehesa');await expect(page.locator('#detailBody')).toContainText('Clínicas Huinganal');await expect(page.locator('#detailBody')).toContainText('Mindplace en San Damián');
 await expect(page.locator('#detailBody')).toContainText('Mostramos sólo el titular y la bajada pública');
 await expect(bupa).not.toContainText('…');
 await expect(bupa.locator('.card-meta')).toContainText(/\d{1,2} \p{L}+\.? 2026/u);
 for(const derived of ['No es solo expansión física','La Dehesa: inauguración','Clínicas Huinganal: crecimiento mediante adquisición','capacidad nueva, compra y diversificación de servicios','Bupa refuerza su red'])
  await expect(page.locator('#detailBody')).not.toContainText(derived);
 await expect(page.locator('#detailBody')).not.toContainText('Enriquecimiento editorial');
 await page.getByRole('button',{name:'Cerrar ficha'}).click();
 const isapre=page.locator('article').filter({has:page.getByRole('heading',{name:/Pulso Isapre · datos/})});
 await expect(isapre.locator('.card-meta')).toContainText('Datos a 2026-07');
 await expect(isapre.locator('.card-meta')).toContainText('Publicado 07 sept 2026');
 await expect(isapre.locator('.card-meta')).toContainText('Validado 24 sept 2026');
 await isapre.locator('[data-detail]').first().click();
 await expect(page.locator('#detailBody .statistical-calculations .intel').locator('li')).toHaveCount(3);
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
 await expect(page.locator('#detailBody')).toContainText('Publicado 07 sept 2026');
 await expect(page.locator('#detailBody')).toContainText('Validado: 24 sept 2026');
 await page.getByRole('button',{name:'Cerrar ficha'}).click();
 const pulse=page.locator('article').filter({has:page.getByRole('heading',{name:/Pulso de sanciones a Prestadores/})});
 await pulse.locator('[data-detail]').first().click();await expect(page.locator('#detailBody')).toContainText('Resoluciones incluidas en este pulso · 3');
 await expect(page.locator('#detailBody')).toContainText('Clínica Los Carrera · 70 UF · cheque en garantía');
 await expect(page.locator('#detailBody .sourceverify .related-item')).toHaveCount(3);
 await expect(page.locator('#detailBody')).toContainText('Clínica Redsalud Providencia · 200 UF');
 await page.getByRole('button',{name:'Cerrar ficha'}).click();
 const tea=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:/Resolución Exenta IF\/N°11156 · TEA:/i})});
 await tea.locator('[data-detail]').first().click();
 await expect(page.locator('#detailBody')).toContainText('15 días hábiles');
 await expect(page.locator('#detailBody')).toContainText('1 de noviembre de 2026');
 await expect(page.locator('#detailBody')).toContainText('Registro Nacional de Discapacidad');
 await page.getByRole('button',{name:'Cerrar ficha'}).click();
 const circular=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:/Circular IF\/N°535 · Reembolsos a empleadores públicos/i})});
 await circular.locator('[data-detail]').first().click();await expect(page.locator('#detailBody')).toContainText('Circular IF/N°77');
 await page.locator('#detailBody .related').getByText('Normativa relacionada',{exact:false}).click();
 await expect(page.locator('#detailBody')).toContainText('Norma modificada');
 const ref=page.locator('#detailBody .related-item').filter({hasText:'Circular IF/N°77'});
 await expect(ref).toBeVisible();
 await expect(ref.getByText('Norma modificada',{exact:false})).toBeVisible();
 expect(await ref.locator('a').count()===1||await ref.getByText('enlace pendiente de verificación',{exact:false}).count()===1).toBeTruthy();
 await page.screenshot({path:`artifacts/${test.info().project.name}-cards-v2.png`,fullPage:true});
});
test('Global Intelligence mirrors Home while keeping global facts and Chile hypotheses distinct',async({page})=>{
 const globalData=JSON.parse(fs.readFileSync('web/data/global_themes.json','utf8')),themeCount=globalData.themes.length,visibleCount=themeCount;
 await page.goto('/');
 await expect(page.locator('#bigThings .big-feature.global .title-open[data-special-open]')).toBeVisible();
 await page.locator('#bigThings .big-feature.global .title-open[data-special-open]').first().click();
 await expect(page.getByRole('heading',{name:'Global Intelligence',exact:true})).toBeVisible();await expect(page.locator('#globalDetail')).toBeVisible();await page.keyboard.press('Escape');
 await expect(page.getByRole('heading',{name:'Ponte al día en Global Intelligence'})).toBeVisible();
 await expect(page.locator('#globalPeriod')).toHaveValue('30');
 await page.locator('#globalFilters summary').click();
 await expect(page.locator('#globalPublisher')).toBeVisible();
 await expect(page.locator('#globalSort')).toBeVisible();
 await page.locator('#globalPeriod').selectOption('all');await expect(page.locator('#globalFilters')).not.toHaveAttribute('open','');
 // Bar A on Global (Dirección 27-oct 23:13): Todas shows every theme; Pendientes only the unread ones.
 await page.locator('#globalLanes [data-lane="t"]').click();
 await expect(page.locator('.theme')).toHaveCount(visibleCount);
 const initialUnread=visibleCount-await page.locator('.theme.read').count();
 await expect(page.locator('#globalMetrics')).toHaveText(`${visibleCount} temas · no leídos ${initialUnread}`);
 // Open an unread theme that is not under the BCBSA editorial HOLD (its record carries no local-evidence block).
 await page.locator('.theme:not(.read):not(#theme-global-ai-coding-payer-cost-2026) [data-open]').first().click();
 await expect(page.locator('#globalMetrics')).toHaveText(`${visibleCount} temas · no leídos ${initialUnread-1}`);
 const opened=page.locator('#globalDetail');await expect(opened).toBeVisible();await expect(opened).toContainText('Fuentes y evidencia');await expect(opened).not.toContainText(/Qué encontró:|Lectura estratégica|Qué mirar en Chile/);await expect(opened).toContainText('evidencia local');await page.keyboard.press('Escape');
 await page.reload();await expect(page.locator('#globalPeriod')).toHaveValue('all');await expect(page.locator('#globalLanes [data-lane="t"]')).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('.theme')).toHaveCount(visibleCount);
 const visibleIds=await page.locator('.theme').evaluateAll(nodes=>nodes.map(n=>n.id.replace(/^theme-/,'')));expect(visibleIds.length).toBe(themeCount);
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
 await selectPeriod(page,'7');
 await expect(page.locator('#radarMetrics')).toHaveText(/^(\d+ pendientes|Estás al día)$/);
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

// Dirección's rule: a title that is only the act identity (any N°/Nº, dotted number), optionally with
// its emission date, is opaque. A descriptive title may still end in a cited norm ID.
const OPAQUE_ACT_TITLE=/^(Circular|Resolución|Oficio|Decreto)(\s+Exenta)?(\s+(IF|IP|SS)\s*\/?)?\s*(N\s*[°º.]?\s*)?(\d{1,3}(\.\d{3})+|\d+)(\s*[-–,]?\s*(Emisión\s*:?\s*)?(del?\s+)?(\d{1,2}[\/.-]\d{1,2}[\/.-]\d{4}|\d{1,2} de \S+ de \d{4}))?\s*\.?$/i;
test('persistent editorial contract is visible in feed and brief',async({page})=>{
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 await page.locator('#filterDetails summary').click();await selectPeriod(page,'90');
 const pulse=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:/Pulso Isapre/})});
 await expect(pulse).toHaveCount(1);
 // A regional release published after the pulse's own release is new information the pulse does not
 // cover (the pulse only claims releases up to its validation day), so it may appear once; older ones stay folded.
 {const radar=await (await page.request.get('/data/radar_today.json')).json();
  const pulseDay=radar.signals.find(s=>String(s.title).startsWith('Pulso Isapre')).publication_date;
  const regional=radar.signals.filter(s=>String(s.title).includes('Cartera de Beneficiarios del Sistema ISAPRE a Nivel Regional'));
  const newer=regional.filter(s=>String(s.event_date||'')>pulseDay).length;
  await expect(page.locator('article[data-card]').filter({hasText:'Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE a Nivel Regional'})).toHaveCount(Math.min(newer,1));}
 const opaque=page.locator('article[data-card] h2').filter({hasText:OPAQUE_ACT_TITLE});
 await expect(opaque).toHaveCount(0);
 const c533=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:/Circular IF\/N°533 · SIL: actualiza el inventario mensual/})});
 await expect(c533).toHaveCount(1);
 await expect(c533).not.toContainText('Qué pasó:');await c533.locator('[data-detail]').first().click();await expect(page.locator('#detailBody')).toContainText('Circular');await page.keyboard.press('Escape');
 const briefOpaque=page.locator('#local .signal.item h2,#bigThings h2,#brief .anchor-title').filter({hasText:OPAQUE_ACT_TITLE});
 await expect(briefOpaque).toHaveCount(0);
});

test('Pulso Isapre presents stock KPIs with separate contracts and mobility views',async({page})=>{
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 await page.locator('#filterDetails summary').click();await selectPeriod(page,'90');
 await expect(page.locator('article[data-card]').filter({hasText:'Resonancia Magnética del Biobío'})).toHaveCount(0);
 const radar=await (await page.request.get('/data/radar_today.json')).json();
 for(const [needle,copy,url] of [
   ['Estadística Trimestral de Casos GES','casos GES acumulados por problema de salud',STATISTICAL_URLS.ges],
   ['Series Estadísticas del Sistema ISAPRE 1990-2025','promedio anual de beneficiarios Isapre',STATISTICAL_URLS.series],
   ['Boletín Estadístico Informativo IP','cortes de acreditación, mediación, reclamos y RNPI',STATISTICAL_URLS.bulletin],
 ]){
   const signal=radar.signals.find(x=>x.source_url===url);
   const original=knownHistoricalSignal(x=>x.source_url===url);
   if(!withinSnapshotHorizon(radar,original)){
     expect(signal,needle+' must leave the feed when its actual publication date expires').toBeUndefined();
     continue;
   }
   expect(signal,needle+' missing from snapshot').toBeTruthy();
   expect(signal.summary_table?.rows?.length||0,needle+' table').toBeGreaterThan(0);
   const card=page.locator('article[data-card]').filter({hasText:needle});
   if(signal.feed_visibility!==false&&String(signal.editorial_committee?.verdict||'PASS').toUpperCase()==='PASS'){
     if(await card.count()){await card.locator('[data-detail]').first().click();await expect(page.locator('#detailBody')).toContainText(copy);await page.keyboard.press('Escape');}
   }
 }
 const pulse=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:/Pulso Isapre/})});
 await expect(pulse).toHaveCount(1);await pulse.locator('[data-detail]').first().click();
 const detail=page.locator('#detailBody'),table=detail.locator('#entityComparison');
 await expect(table).toBeVisible();
 const stock=radar.signals.find(s=>s.title.startsWith('Pulso Isapre')).statistical_view;
 if(stock.entity_status==='verified')for(const label of ['Beneficiarios','Cotizantes','Cargas'])await expect(table).toContainText(label);
 else{await expect(table).toContainText('desglose no verificado');await expect(table.locator('table')).toHaveCount(0);}
 await expect(detail.locator('.stat-kpis')).toContainText('2.487.497');
 await detail.getByText('Contratos · 2026-07',{exact:true}).click();
 await expect(detail).toContainText('Suscripciones');await expect(detail).toContainText('Desahucios voluntarios');
 await detail.getByText('Movilidad · cortes 2025-07 y 2026-07',{exact:true}).click();
 await expect(detail).toContainText('91.963');await expect(detail).toContainText('109.663');
 await expect(detail).toContainText('diferencia -17.700');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});


test('committee HOLD/REJECT and failed publication contracts do not render as individual feed cards',async({page})=>{
  await page.goto('/');
  const response=await page.request.get('/data/radar_today.json');
  const data=await response.json();
  const hidden=(data.signals||[]).filter(s=>{
    const verdict=String(s.editorial_committee?.verdict||'PASS').toUpperCase();
    const types=Array.isArray(s.signal_types)?s.signal_types.map(x=>String(x).toLowerCase()):[];
    // Mirrors web/app.js publicationContractOk: a paywalled title-only card (rights policy 28-oct)
    // has card_why_optional and no "why"; it is still a valid PASS card. Verdict/visibility checks are unchanged.
    const core=Boolean((s.display_title||s.title)&&s.signal_types?.length&&s.scopes?.length&&s.event_date&&s.source_name&&s.source_url&&(s.card_what||s.what_happened)&&(s.card_why_optional||s.card_why||s.why_it_matters));
    const contract=core&&(!types.includes('normativa')||Boolean(s.normative_document_label));
    return s.feed_visibility===false||['HOLD','REJECT'].includes(verdict)||!contract;
  });
  for(const signal of hidden.slice(0,12)){
    await expect(page.locator('.signal[data-card]').filter({hasText:signal.display_title||signal.title})).toHaveCount(0);
  }
});

// The exporter already drops HOLD/REJECT rows, so the real snapshot rarely contains one. Inject
// redacted (paywalled, title-only) rows carrying committee HOLD/REJECT or feed_visibility=false:
// none may render, while the same row with a PASS verdict does.
test('redacted paywalled rows keep committee HOLD/REJECT out of the feed',async({page})=>{
  const base={paywalled:true,card_why_optional:true,why_it_matters:'',signal_types:['Noticias'],scopes:['Prestadores'],
    event_date:'2026-10-11',source_name:'Diario Financiero',access_policy:'public_teaser_only',analysis_basis:'public_teaser_only',
    what_happened:'Bajada pública de prueba.',radar_score:99};
  const rows=[['PASS','Prueba derechos PASS visible',true],['HOLD','Prueba derechos HOLD oculta',true],
    ['REJECT','Prueba derechos REJECT oculta',true],['PASS','Prueba derechos feed oculta',false]]
    .map(([verdict,title,visible],i)=>({...base,title,id:`rights-gate-${i}`,source_url:`https://www.df.cl/empresas/salud/rights-gate-${i}`,
      feed_visibility:visible,editorial_committee:{verdict,publication_decision:verdict==='REJECT'?'reject':'accept',analysis_basis:'public_teaser_only'}}));
  await page.route('**/data/radar_today.json',async route=>{const response=await route.fetch(),data=await response.json();
    data.signals=[...rows,...(data.signals||[])];await route.fulfill({response,json:data})});
  await page.goto('/');
  await expect(page.locator('.signal[data-card]').filter({hasText:'Prueba derechos PASS visible'})).toHaveCount(1);
  for(const title of ['Prueba derechos HOLD oculta','Prueba derechos REJECT oculta','Prueba derechos feed oculta'])
    await expect(page.locator('.signal[data-card]').filter({hasText:title})).toHaveCount(0);
});


// Dirección 27-oct 22:44 (punto 4) supersedes the 25-oct 'period inside Filtrar': the period opens only itself.
test('period is its own dropdown, never opens the filters, persists and is resettable',async({page})=>{
 await page.goto('/');
 const period=page.locator('#period'),filters=page.locator('#filterDetails');
 await expect(period).toBeVisible();
 expect(await period.locator('xpath=ancestor::details').count()).toBe(0);
 await period.selectOption('90');
 await expect(period).toHaveValue('90');await expect(filters).not.toHaveAttribute('open','');
 await expect(page.locator('#radarMetrics')).not.toContainText('período');
 await page.reload();
 await expect(period).toHaveValue('90');
 await page.locator('#filterDetails summary').click();await expect(filters).toHaveAttribute('open','');
 await page.locator('#resetFilters').click();
 await expect(period).toHaveValue('30');
 await expect(page.locator('#sort')).toHaveValue('date');
 await expect(page.locator('#radarMetrics')).not.toContainText('30 días');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});


test('Home hero is compact, one-line and exposes subscription plus Global Intelligence',async({page})=>{
 await page.goto('/');
 await expect(page.locator('.hero-purpose')).toHaveText('Señales clave del sector salud, claras y a tiempo.');
 await expect(page.locator('.newsletter-strip')).toContainText('Suscríbete para recibir en tu correo las señales más importantes');
 await expect(page.locator('.newsletter-strip #newsletterOpen')).toHaveText('Suscríbete');
 await expect(page.locator('a.header-premium[href="global.html"]')).toHaveAttribute('href','global.html');
 await expect(page.locator('button.premium-access')).toHaveText('Acceso PREMIUM');
 if(test.info().project.name==='mobile'){
   const title=await page.locator('#radarTitle').boundingBox();
   // The pending count now lives in the segmented read status (Dirección 27-oct 22:44, punto 5);
   // #radarMetrics stays as the screen-reader status, so the layout check uses the segmented control.
   const metrics=await page.locator('#lanes [data-lane="p"]').boundingBox();
   const source=await page.locator('#sourcesOpen').boundingBox();
   expect(metrics.y+metrics.height).toBeGreaterThan(title.y);
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

test('Global metadata health stays separate from Chile LIVE coverage',async({page})=>{
 const health=await(await page.request.get('/data/source_health.json')).json();
 const product=await(await page.request.get('/data/product.json')).json();
 for(const key of ['global_who','global_paho','global_reuters']){
  const row=health.sources[key];expect(row.discovery_scope).toBe('global_intelligence');
  expect(row.published).toBe(0);
  if(key==='global_reuters')expect(row.publication_activation).toBe(false);
  else expect(row.publication_activation===false||(row.publication_activation_decision?.earned_evidence_run_ids||[]).length===2).toBe(true);
  expect(product.sources[key]).toEqual(row);
 }
 expect(health.sources.global_reuters.counts).toEqual({'30':null,'90':null});
 expect(health.sources.global_reuters.technical_status).toBe('not_polled_license_hold');
 await page.goto('/');
 const coreHealth={...health,sources:Object.fromEntries(Object.entries(health.sources).filter(([key,s])=>s.discovery_scope!=='global_intelligence'))};
 const coverage=await page.evaluate(data=>coverageText(data),health);
 expect(coverage).toEqual(await page.evaluate(data=>coverageText(data),coreHealth));
 await page.locator('#sourcesOpen').click();
 const catalog=await(await page.request.get('/data/public_sources.json')).json();
 for(const id of ['global_who','global_paho','global_reuters']){
  const source=catalog.sources.find(x=>x.id===id);
  const row=page.locator('.source-row').filter({hasText:health.sources[id].name});
  if(source)await expect(row).toHaveCount(1);else await expect(row).toHaveCount(0);
 }
 await expect(page.locator('#sourcesList')).not.toContainText('Reuters');
});

test('sources are grouped by decision value and expose freshness layers',async({page})=>{
 await page.goto('/');
 await page.locator('#sourcesOpen').click();
 await expect(page.locator('#sourcesList')).toContainText('Organismos públicos y reguladores');
 await expect(page.locator('#sourcesList')).toContainText('Noticias y mercado');
 const first=page.locator('#sourcesList .source-row').first();await expect(first.getByRole('link')).toHaveAttribute('href',/^https:\/\//);await expect(page.locator('#sourcesList')).not.toContainText(/Última consulta|Última señal detectada|Última seleccionada|Reuters|FONASA/);
 await expect(page.locator('#source-suggestion')).toContainText('¿Falta una fuente relevante?');
});


test('priority statistical releases use compact tables and collapsed traceability',async({page})=>{
 await page.goto('/');
 await page.locator('#filterDetails summary').click();
 await selectPeriod(page,'90');
 const radar=await (await page.request.get('/data/radar_today.json')).json();
 const cases=[
  ['Estadística Trimestral de Casos GES',5,STATISTICAL_URLS.ges],
  ['Series Estadísticas del Sistema ISAPRE',2,STATISTICAL_URLS.series],
  ['Boletín Estadístico Informativo IP',6,STATISTICAL_URLS.bulletin],
 ];
 for(const [needle,minRows,url] of cases){
   const s=radar.signals.find(x=>x.source_url===url);
   const original=knownHistoricalSignal(x=>x.source_url===url);
   if(!withinSnapshotHorizon(radar,original)){
     expect(s,needle+' must leave the feed when its actual publication date expires').toBeUndefined();
     continue;
   }
   expect(s,needle+' missing').toBeTruthy();
   expect((s.data_insights||[]).length,needle+' repeated insight list').toBe(0);
   expect(s.summary_table?.rows?.length||0,needle+' table').toBeGreaterThanOrEqual(minRows);
   expect(s.methodology_visibility).toBe('collapsed');
   expect(s.card_why_optional).toBe(true);
   expect(s.incremental_value_gate?.table).toBeTruthy();
   expect(s.data_insight_evidence?.length||0,needle+' evidence').toBeGreaterThan(0);
 }
 const ges=radar.signals.find(x=>x.source_url===STATISTICAL_URLS.ges);
 if(ges){
  expect(ges.summary_table.columns).toEqual(['Problema de salud','Fonasa (casos)','Isapre (casos)','Total (casos)','Isapre (%)']);
  expect(ges.summary_table.rows.every(r=>r.cells?.length===5&&!/^\d+$/.test(r.cells[0]))).toBe(true);
 }
 const series=radar.signals.find(x=>x.source_url===STATISTICAL_URLS.series);
 if(series){
  expect(series.summary_table.rows.map(r=>r.cells[0])).toEqual(['Beneficiarios promedio anual','Casos GES']);
  expect(series.summary_table.rows.every(r=>r.cells[3]+r.cells[5]===r.cells[4])).toBe(true);
 }
 const fin=radar.signals.find(x=>(x.title||'').includes('Estadísticas Financieras del Sistema ISAPRE'));
 if(fin){
   expect(fin.summary_table.columns).toEqual(['Isapre','Ingresos (CLP millones)','Resultado operacional (CLP millones)','Utilidad/pérdida neta (CLP millones)']);
   expect(fin.data_insight_evidence[0].source_url).toContain('finan_ifrs_mar_2026_web_v2.xls');
   const card=page.locator('article[data-card]').filter({hasText:'Estadísticas Financieras del Sistema ISAPRE'});
   await expect(card).not.toContainText('Por qué importa:');
   await card.locator('[data-detail]').first().click();
   const detail=page.locator('#detailBody');
   await expect(detail.locator('.summary-table')).toBeVisible();
   await page.locator('#detailDialog [data-close]').click();
 }
 const bulletin=radar.signals.find(x=>x.source_url===STATISTICAL_URLS.bulletin);
 if(bulletin){
  expect(new Set(bulletin.summary_table.rows.map(r=>r.cells[0]))).toEqual(new Set(['Acreditación','Mediación','Reclamos','RNPI']));
  const bulletinCard=page.locator('article[data-card]').filter({hasText:'Boletín Estadístico Informativo IP'});
  await bulletinCard.locator('[data-detail]').first().click();
  const detail=page.locator('#detailBody');
  await expect(detail.locator('details.statistical-methodology')).not.toHaveAttribute('open','');
  await expect(detail).not.toContainText('Muestra de datos validada');
  await expect(detail.locator('.source')).toContainText('Fuente original');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  await page.getByRole('button',{name:'Cerrar ficha'}).click();
 }
});

test('Normative V2.1 puts document, subject and action in each current headline',async({page})=>{
 await page.goto('/');
 await page.locator('#filterDetails summary').click();
 await selectPeriod(page,'90');
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
  const original=knownHistoricalSignal(x=>x.source_url?.endsWith('n'+number+'/')&&x.signal_types?.includes('Normativa'));
  const signal=radar.signals.find(x=>x.source_url?.endsWith('n'+number+'/')&&x.signal_types?.includes('Normativa'));
  if(!withinSnapshotHorizon(radar,original)){
   expect(signal,number+' must leave the feed when its actual publication date expires').toBeUndefined();
   continue;
  }
  expect(signal,number).toBeTruthy();
  const title=signal.display_title;
  expect(title).toContain(signal.normative_document_label||signal.legal_identity);
  expect(title).toMatch(subject);expect(title).toMatch(action);
  expect(signal.normative_context).toBeTruthy();
  expect(signal.normative_context).not.toContain(title);
  const article=page.locator('article[data-card]').filter({has:page.getByRole('heading',{name:title,exact:true})});
  if(await article.count()){
    await expect(article.locator('.normative-identity')).toHaveCount(0);
    await article.locator('[data-detail]').first().click();
    await expect(page.locator('#detailBody')).toBeVisible();
    await expect(page.locator('#detailBody')).toContainText(signal.normative_context);

    await page.getByRole('button',{name:'Cerrar ficha'}).click();
  }
 }
});


test('source capture errors remain administrative and are excluded from the public catalog',async({page})=>{
 await page.route('**/data/public_sources.json',route=>route.fulfill({json:{sources:[]}}));
 await page.goto('/');await page.locator('#sourcesOpen').click();await expect(page.locator('#sourcesList')).toContainText('No hay fuentes activas verificadas');await expect(page.locator('#sourcesList')).not.toContainText('Fondo Nacional de Salud');
});
test('a shared link is revealed once in a lane that shows it and never rewrites lanes or filters again',async({page})=>{
 await page.goto('/');const rows=page.locator('#local article[data-card]');await expect(rows.first()).toBeVisible();
 const id=await rows.nth(2).getAttribute('data-card');
 await selectLane(page,'l');await expect(page.locator('[data-lane="l"]')).toHaveAttribute('aria-pressed','true');
 await page.goto(`/#sig-${encodeURIComponent(id)}`);await page.reload();
 const card=page.locator(`[id="sig-${id}"]`);await expect(card).toBeVisible();await expect(card).toBeFocused();await expect(card).not.toHaveClass(/read/);
 await selectLane(page,'p');await expect(page.locator('[data-lane="p"]')).toHaveAttribute('aria-pressed','true');
 await card.locator('[data-read]').click();await expect(card.locator('.row-undo')).toBeVisible();await expect(card).toHaveCount(0,{timeout:12000});
 await rows.first().locator('[data-read]').click();await expect(rows.first().locator('.row-undo')).toBeVisible();
 await expect(page.locator('[data-lane="p"]')).toHaveAttribute('aria-pressed','true');await expect(page.locator(`[id="sig-${id}"]`)).toHaveCount(0);
 expect(JSON.parse(await page.evaluate(()=>localStorage.getItem('alicanto_filters'))).lane).toBe('p');
});
// Dirección 28-oct 03:49: a read row keeps source, date and its buttons (link, share, mark unread);
// only tone and weight change. Supersedes 'the dot disappears' of design B.
test('in Todas a read row keeps source, date and buttons, and the dot toggles back',async({page})=>{
 await page.goto('/');await selectLane(page,'t');
 const row=page.locator('#local article[data-card]:not(.read)').first();const id=await row.getAttribute('data-card');const same=page.locator(`#local [data-card="${id}"]`);
 const meta=await same.locator('.meta-text').innerText();expect(meta.trim().length).toBeGreaterThan(4);
 const dot=same.locator('[data-read]');await dot.click();await expect(same).toHaveClass(/read/);
 await expect(dot).toBeVisible();await expect(dot).toBeFocused();await expect(dot).toHaveAttribute('aria-label',/^Marcar como no leído/);
 await expect(same.locator('.card-meta')).toBeVisible();await expect(same.locator('.meta-text')).toHaveText(meta);
 await expect(same.locator('.item-actions a[aria-label="Fuente original"]')).toBeVisible();await expect(same.locator('.item-actions [data-share]')).toBeVisible();
 const size=await same.locator('h2').evaluate(el=>getComputedStyle(el).fontSize);expect(size).toBe(await page.locator('#local article[data-card]:not(.read) h2').first().evaluate(el=>getComputedStyle(el).fontSize));
 await page.reload();await expect(same).toHaveClass(/read/);await expect(same.locator('.meta-text')).toHaveText(meta);await expect(same.locator('[data-read]')).toBeVisible();
 await same.locator('[data-read]').click();await expect(same).not.toHaveClass(/read/);await expect(same.locator('[data-read]')).toHaveAttribute('aria-label',/^Marcar como leído/);
});
test('Global read rows keep publisher and date',async({page})=>{
 await page.goto('/global.html');await page.locator('#globalPeriod').selectOption('all');await page.locator('#globalLanes [data-lane="t"]').click();
 const row=page.locator('#themes .theme:not(.read)').first();const id=await row.getAttribute('data-theme');const same=page.locator(`#theme-${id}`);
 const meta=await same.locator('.meta-text').innerText();
 await same.locator('[data-read]').click();await expect(same).toHaveClass(/read/);
 await expect(same.locator('.meta-text')).toBeVisible();await expect(same.locator('.meta-text')).toHaveText(meta);await expect(same.locator('[data-read]')).toHaveAttribute('aria-label',/^Marcar como no leído/);
});
// Dirección 27-oct 22:44 (puntos 2, 3 y 5) supersede the lanes menu of PR #72 review N1: read status is an
// always-visible segmented control; topics are one compact multi-select dropdown floating over the feed;
// Insight/Global keep their silver/gold tone after reading. Feed titles still clamp to two lines (review N2).
test('segmented read status, floating topics dropdown and toned weekly rows',async({page})=>{
 await page.goto('/');const rows=page.locator('#local article[data-card]');await expect(rows.first()).toBeVisible();
 for(const k of ['p','l','t'])await expect(page.locator(`#lanes [data-lane="${k}"]`)).toBeVisible();
 await expect(page.locator('#laneToggle')).toHaveCount(0);
 await page.locator('[data-lane="t"]').click();await expect(page.locator('[data-lane="t"]')).toHaveAttribute('aria-pressed','true');await expect(page.locator('[data-lane="p"]')).toHaveAttribute('aria-pressed','false');
 await expect(page.locator('#filterLabel')).toHaveText('Todos los temas');
 const before=await rows.first().boundingBox();
 await page.locator('#filterDetails summary').click();await expect(page.locator('#filterDetails .filter-body')).toBeVisible();
 expect(await page.locator('#filterDetails .filter-body').evaluate(el=>getComputedStyle(el).position)).toBe('absolute');
 expect((await rows.first().boundingBox()).y).toBeCloseTo(before.y,0);
 const picks=page.locator('#interestFilters .tog[data-interest]:not([data-interest=""])');
 await picks.nth(0).click();await picks.nth(1).click();
 await expect(page.locator('#filterLabel')).toHaveText('2 temas');await expect(page.locator('#interestFilters .tog-all')).toHaveAttribute('aria-pressed','false');
 await page.locator('#interestFilters .tog-all').click();await expect(page.locator('#filterLabel')).toHaveText('Todos los temas');
 await page.keyboard.press('Escape');await expect(page.locator('#filterDetails')).not.toHaveAttribute('open','');
 const fills=await page.locator('#bigThings .big-feature').evaluateAll(xs=>xs.map(x=>getComputedStyle(x).backgroundImage));
 for(const f of fills)expect(f).toContain('gradient');
 const specialsCount=fills.length;
 for(let i=0;i<specialsCount;i++){await page.locator('#bigThings .big-feature:not(.read) [data-special-read]').first().click();await expect(page.locator('#bigThings .big-feature.read')).toHaveCount(i+1)}
 await expect.poll(()=>page.locator('#bigThings .big-feature').evaluateAll(xs=>xs.map(x=>getComputedStyle(x).backgroundImage))).toEqual(fills);
 const lines=await page.locator('#local .signal.item .title-open').evaluateAll(xs=>xs.map(x=>Math.round(x.getBoundingClientRect().height/parseFloat(getComputedStyle(x).lineHeight))));
 expect(Math.max(...lines)).toBeLessThanOrEqual(2);
});

// Dirección 28-oct (puntos 5, 6 y 7): Premium and Suscribirse open the same dialogs in place on Chile and Global;
// Global never sends the reader back to Chile.
test('Premium and Suscribirse behave the same on Chile and Global and keep the reader in place',async({page})=>{
 for(const path of ['/','/global.html']){
  await page.goto(path);const url=page.url();
  await page.locator('.topnav .premium-access').click();await expect(page.locator('#earlyAccessDialog')).toBeVisible();await expect(page.locator('#earlyAccessDialog')).toContainText('Ve más allá de la señal.');
  expect(page.url()).toBe(url);await page.getByRole('button',{name:'Cerrar acceso Premium'}).click();await expect(page.locator('#earlyAccessDialog')).toBeHidden();
  await page.locator('.topnav .header-newsletter').click();await expect(page.locator('#newsletterDialog')).toBeVisible();expect(page.url()).toBe(url);await page.keyboard.press('Escape');
  const strip=page.locator('.newsletter-strip #newsletterOpen');await expect(strip).toHaveText('Suscríbete');await strip.scrollIntoViewIfNeeded();await strip.click();
  await expect(page.locator('#newsletterDialog')).toBeVisible();expect(page.url()).toBe(url);await page.keyboard.press('Escape');
  await expect(page.locator('a[href="index.html#premium"]')).toHaveCount(0);
 }
 await page.goto('/global.html#premium');await expect(page.locator('#earlyAccessDialog')).toBeVisible();expect(page.url()).toContain('global.html');
});
test('Global rows match Home rows: dot toggle, title opens the ficha, source and share, inline undo',async({page})=>{
 await page.goto('/global.html');await page.locator('#globalPeriod').selectOption('all');
 const row=page.locator('#themes .theme:not(.read)').first();const id=await row.getAttribute('data-theme');const same=page.locator(`#theme-${id}`);
 await expect(same.locator('.item-actions a[aria-label="Fuente original"]')).toHaveAttribute('target','_blank');await expect(same.locator('.item-actions [data-share]')).toBeVisible();
 await expect(page.locator('#globalUndo,.undo-bar')).toHaveCount(0);
 await same.locator('.title-open').click();await expect(page.locator('#globalDetail')).toBeVisible();
 await expect(page.locator('#globalDetail .detail-top #closeGlobalDetail')).toHaveText('Volver');await expect(page.locator('#globalDetailBar [data-share]')).toBeVisible();
 await page.keyboard.press('Escape');
 await expect(same.locator('.row-undo')).toContainText('Leída');await same.locator('.row-undo button').click();await expect(same).not.toHaveClass(/read/);
 await same.locator('[data-read]').click();await expect(same).toHaveClass(/read/);await page.mouse.move(0,0);await page.locator('#globalLanes .lane.on').focus();
 await expect(same).toHaveCount(0,{timeout:12000});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});
test('fichas read straight: why it matters follows what happened with no meta-label',async({page})=>{
 await page.goto('/');await page.locator('#local .title-open').first().click();await expect(page.locator('#signalDetail')).toBeVisible();
 await expect(page.locator('#detailBody')).not.toContainText(/Contexto editorial|Enriquecimiento editorial/);
 expect(await page.locator('#detailBody > p').count()).toBeGreaterThanOrEqual(2);
});
test('the Global teaser in Chile invites to Global Premium without saying limitado',async({page})=>{
 await page.goto('/');const g=page.locator('#bigThings .big-feature.global');await expect(g).toHaveCount(1);
 await expect(g).toContainText('Global Premium');await g.locator('[data-special-toggle]').click();
 await expect(g.locator('.big-invite')).toHaveText('El análisis completo, con sus fuentes, te espera en Global Premium.');await expect(g.locator('.big-cta')).toHaveText('Entrar a Global →');
 await expect(g).not.toContainText(/limitad/i);
});

// Dirección 28-oct (punto 5): the ficha title has one style on Chile and Global.
test('ficha titles share the same font on Chile and Global',async({page})=>{
 const style=sel=>page.locator(sel).evaluate(el=>{const c=getComputedStyle(el);return [c.fontFamily,c.fontWeight,c.fontSize,c.lineHeight].join('|')});
 await page.goto('/');await page.locator('#local .title-open').first().click();await expect(page.locator('#detailTitle')).toBeVisible();const chile=await style('#detailTitle');
 await page.goto('/global.html');await page.locator('#globalPeriod').selectOption('all');await page.locator('#themes .title-open').first().click();await expect(page.locator('#globalDetailTitle')).toBeVisible();
 expect(await style('#globalDetailTitle')).toBe(chile);expect(chile).toMatch(/Georgia/);
});
