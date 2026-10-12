// Scoped QA of real exported Pulso rows only. No network fixtures or row injection.
const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
const path=require('node:path');
const ROOT=process.env.PULSO_QA_ROOT||path.resolve(__dirname,'..');
const history=JSON.parse(fs.readFileSync(path.join(ROOT,'data/history/superintendencia_signals.json'),'utf8')).signals;
const queuePayload=JSON.parse(fs.readFileSync(path.join(ROOT,'data/state/pending_queue.json'),'utf8'));
const queue=Object.values(queuePayload.items||queuePayload);
const PUBLISHER='Pulso / La Tercera';
async function sourceRows(page){
 const payload=await(await page.request.get('/data/radar_today.json')).json();
 const rows=(payload.signals||[]).filter(row=>row.source_name===PUBLISHER);
 expect(rows.length,'Real core publications must exist before UI publication QA can PASS; never fabricate rows').toBeGreaterThan(0);
 return rows;
}
async function showNews(page){
 await page.goto('/');await expect(page.locator('#meta')).toContainText('Última actualización:');
 await page.locator('#filterDetails summary').click();await page.locator('#period').selectOption('90');
 await page.locator('#typeFilters [data-v="Noticias"]').click();
}
function cardFor(page,row){return page.locator('article[data-card]').filter({has:page.locator(`a[href="${row.source_url}"]`)});}
test('real Pulso news preserves source, dates, attribution and metadata in desktop/mobile feed',async({page})=>{
 await showNews(page);const rows=await sourceRows(page);
 for(const row of rows){
  expect(row.evidence_maturity).toBe('media_reported');
  expect(row.source_type).toBe('press_high_trust');
  expect(row.publication_date_source).toBeTruthy();
  expect(row.publication_date).toBe(row.event_date);
  expect(row.editorial_relevance).toBeGreaterThanOrEqual(72);
  expect(row.publication_gate_reason).toBe('ok');
  const original=history.find(item=>item.source_url===row.source_url);
  expect(original,'Every actual feed row must retain its published history URL').toBeTruthy();
  expect(original.event_date).toBe(row.event_date);
  expect(original.evidence_maturity).toBe('media_reported');
  const published=queue.find(item=>item.source==='pulso_latercera'&&item.status==='published'&&item.raw?.url===row.source_url);
  expect(published,'Every actual feed URL needs a published queue record').toBeTruthy();
  expect(published.raw.metadata.article_verified).toBe(true);
  expect(published.raw.metadata.editorial_assessment.threshold).toBe(72);
  expect(published.raw.metadata.editorial_assessment.decision).toBe('published');
  expect(row.event_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  expect(['www.latercera.com','latercera.com']).toContain(new URL(row.source_url).hostname);
  expect(row.what_happened).toMatch(/pulso|la tercera/i);
  expect(row.signal_types).toContain('Noticias');
  const allowed=row.feed_visibility!==false&&!['HOLD','REJECT'].includes(String(row.editorial_committee?.verdict||'PASS').toUpperCase());
  const card=cardFor(page,row);
  if(!allowed){await expect(card).toHaveCount(0);continue;}
  await expect(card).toHaveCount(1);await expect(card.locator('.card-meta')).toContainText(PUBLISHER);
  await expect(card.locator('.card-meta')).toContainText('Publicado');
  await expect(card.getByRole('link',{name:'Fuente original ↗'})).toHaveAttribute('href',row.source_url);
  await expect(card.locator('.body')).toContainText(/pulso|la tercera/i);
  if(await card.locator('[data-detail]').count()){
   await card.locator('[data-detail]').click();
   await expect(page.locator('#detailBody .source')).toContainText(PUBLISHER);
   await expect(page.locator('#detailBody .source')).toContainText('Fecha de publicación:');
   await expect(page.locator('#detailBody .source a')).toHaveAttribute('href',row.source_url);
   await page.locator('#closeDetail').click();
  }
 }
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});
test('real Pulso source registry links actual core and selected signal without stale or mismatched names',async({page})=>{
 await showNews(page);const rows=await sourceRows(page);
 const product=await(await page.request.get('/data/product.json')).json();
 const health=product.sources?.pulso_latercera;
 expect(health,'product registry must include actual core Pulso health').toBeTruthy();
 expect(health.name).toBe(PUBLISHER);expect(health.checked_at).toBeTruthy();
 expect(product.discovery?.runtime).toBe('daily_core');
 expect(product.discovery?.sources?.pulso_latercera).toBeTruthy();
 await page.locator('#sourcesOpen').click();
 const more=page.locator('#sourcesMore');if(await more.isVisible())await more.click();
 const source=page.locator('#sourcesList .source-row').filter({has:page.locator('strong').filter({hasText:PUBLISHER})});
 await expect(source).toHaveCount(1);await expect(source).toContainText('Última consulta');
 await expect(source).toContainText('Última señal detectada');await expect(source).toContainText('Última seleccionada');
 await expect(source).not.toContainText('aún no visible');
 await expect(source.locator('xpath=ancestor::section[contains(@class,"source-group")]')).toContainText('Noticias y mercado');
});

test('real Pulso published URLs follow30/90day and scope filters without changing editorial outcomes',async({page})=>{
 await showNews(page);const rows=await sourceRows(page);
 const today=new Date(),todayUTC=Date.UTC(today.getUTCFullYear(),today.getUTCMonth(),today.getUTCDate());
 for(const period of ['30','90']){
  await page.locator('#period').selectOption(period);
  for(const row of rows){
   const age=Math.floor((todayUTC-Date.parse(row.event_date+'T00:00:00Z'))/86400000);
   const allowed=row.feed_visibility!==false&&!['HOLD','REJECT'].includes(String(row.editorial_committee?.verdict||'PASS').toUpperCase());
   await expect(cardFor(page,row)).toHaveCount(allowed&&age>=0&&age<=Number(period)?1:0);
  }
 }
 const scope=rows.flatMap(row=>row.scopes||[]).find(Boolean);
 expect(scope,'Actual published rows must declare a scope').toBeTruthy();
 await page.locator('#scopeFilters .chip').filter({hasText:new RegExp('^'+scope.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'$')}).click();
 for(const row of rows){await expect(cardFor(page,row)).toHaveCount(row.scopes.includes(scope)?1:0);}
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});
