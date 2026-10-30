// Dirección 28-oct 08:20: opción B is the UI on Chile and Global (no switcher), rows show their actions in plain
// view and in a fixed order, the meta → buttons gap is tight while touch targets stay ≥44px, news fichas are lean,
// and nothing is rendered without captured data.
const {test,expect,selectPeriod,selectLane}=require('./fixtures.cjs');
const fs=require('node:fs');
const ORDER=['Ver ficha','Fuente original','Compartir'];
async function rowGeometry(page,sel){return page.locator(sel).evaluateAll(rows=>rows.slice(0,8).map(r=>{const meta=r.querySelector('.card-meta').getBoundingClientRect(),acts=[...r.querySelectorAll('.row-acts .act')].map(a=>{const b=a.getBoundingClientRect(),t=a.querySelector('span').getBoundingClientRect();return {label:a.textContent.trim(),top:b.top,h:b.height,right:b.right,textTop:t.top}}),row=r.getBoundingClientRect();return {metaBottom:meta.bottom,acts,rowRight:row.right,rowBottom:row.bottom}}))}
for(const width of [320,390,1440]){
 test(`opción B rows on Chile and Global at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:900});
  for(const [path,sel] of [['/','#local article[data-card]'],['/global.html','#themes article.item']]){
   await page.goto(path+'?propuesta=a');await expect(page.locator(sel).first()).toBeVisible();
   // No proposal switcher or variant classes any more, with or without the old parameter.
   await expect(page.locator('.prop-switch,.b-actions,.c-toggle,.a-chev')).toHaveCount(0);expect(await page.evaluate(()=>document.body.className)).not.toMatch(/prop-/);
   const rows=await rowGeometry(page,sel);expect(rows.length).toBeGreaterThan(0);
   for(const r of rows){
    const labels=r.acts.map(a=>a.label);expect(ORDER.filter(l=>labels.includes(l))).toEqual(labels);expect(labels[0]).toBe('Ver ficha');expect(labels.at(-1)).toBe('Compartir');
    for(const a of r.acts){expect(a.h).toBeGreaterThanOrEqual(44);expect(a.right).toBeLessThanOrEqual(width+0.5)}
    // One line of actions, right under the meta line: the visible gap from "fuente · fecha" to the labels is small.
    expect(new Set(r.acts.map(a=>Math.round(a.top))).size).toBe(1);
    expect(r.acts[0].textTop-r.metaBottom).toBeLessThanOrEqual(14);expect(r.acts[0].top+r.acts[0].h).toBeLessThanOrEqual(r.rowBottom+0.5);
   }
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
   await page.screenshot({path:`artifacts/${test.info().project.name}-option-b-${path==='/'?'chile':'global'}-${width}.png`});
  }
  await expect(page.locator('.premium-band')).toContainText('Global Premium');
 });
}
test('news ficha is lean on Chile and Global and carries the action set',async({page})=>{
 await page.goto('/');const row=page.locator('#local article[data-card]').first();await row.locator('.act-open').click();
 const body=page.locator('#detailBody');await expect(page.locator('#signalDetail')).toBeVisible();
 await expect(body).not.toContainText(/Por qué importa/);await expect(body.locator('.ficha-h').first()).toHaveText(/Qué pasó/i);
 const id=await row.getAttribute('data-card');const s=await page.evaluate(id=>{const x=allSignals.find(s=>idFor(s)===id);return {why:x.card_why||x.why_it_matters,url:originalLink(x)}},id);
 if(s.why&&!s.why.startsWith((await body.locator('p').first().textContent()).slice(0,40)))await expect(body).not.toContainText(s.why.slice(0,60));
 expect(await page.locator('#detailActs .act').evaluateAll(xs=>xs.map(a=>a.textContent.trim()))).toEqual(['Fuente original','Compartir']);
 await expect(page.locator('#detailActs .act-src')).toHaveAttribute('href',s.url);
 await expect(page.locator('#detailBar')).toHaveText(/Marcar (no )?leída/);
 await page.keyboard.press('Escape');
 await page.goto('/global.html');await page.locator('#themes article.item .act-open').first().click();await expect(page.locator('#globalDetail')).toBeVisible();
 expect(await page.locator('#globalDetailActs .act').evaluateAll(xs=>xs.map(a=>a.textContent.trim()))).toEqual(['Fuente original','Compartir']);
 await expect(page.locator('#globalDetailBody')).not.toContainText(/Por qué importa/);
});
test('a headline ficha with no captured description shows no Qué pasó and no invented source',async({page})=>{
 await page.route('**/data/global_feed.json',r=>r.fulfill({json:{schema_version:2,enabled:true,content_use:'metadata_and_link_only',window_days:90,display:{spanish_only:false},freshness:{status:'fresh'},items:[{id:'only',source_label:'OMS',title:'OMS publica una guía',url:'https://www.who.int/news/item/only',published_at:'2026-10-11',summary_es:'Organismo multilateral. Relevante para: Regulación.',tags_es:['Regulación']}]}}));
 await page.goto('/global.html#daily-only');const body=page.locator('#globalDetailBody');await expect(page.locator('#globalDetailTitle')).toHaveText('OMS publica una guía');
 await expect(body.locator('.ficha-h')).toHaveText(['Fuentes']);await expect(body).not.toContainText(/Qué pasó|Resumen de la fuente|Organismo multilateral|Regulación/);
 expect(await body.locator('a').evaluateAll(xs=>xs.map(a=>a.href))).toEqual(['https://www.who.int/news/item/only']);
});

// Dirección 28-oct 21:49 (punto 2): "Ver ficha ›" is on EVERY row, with Fuente original ↗ (only with a link) and
// Compartir: news, Diario Oficial, data cards, stats fichas and normative cards on Chile, and every Global row.
test('every Chile and Global row type carries Ver ficha, its source link when it has one, and Compartir',async({page})=>{
 await page.goto('/');await expect(page.locator('#local article[data-card]').first()).toBeVisible();
 await selectLane(page,'t');await selectPeriod(page,'90');
 const rows=await page.locator('#local article[data-card]').evaluateAll(rs=>rs.map(r=>{const s=allSignals.find(x=>idFor(x)===r.dataset.card),tags=typeTags(s);
  return {kind:s.stats_ficha?'stats':/diario oficial/i.test(s.source_name||'')?'diario':tags.includes('Normativa')?'normativa':tags.includes('Datos')||s.event_type==='DATA_PULSE'?'datos':'news',
   link:Boolean(originalLink(s)),labels:[...r.querySelectorAll('.row-acts .act')].map(a=>a.textContent.trim())}}));
 const kinds=new Set(rows.map(r=>r.kind));
 for(const k of ['news','normativa','datos','stats'])expect(kinds.has(k),k).toBeTruthy();
 for(const r of rows){expect(r.labels,r.kind).toEqual(r.link?ORDER:['Ver ficha','Compartir'])}
 await page.goto('/global.html');await expect(page.locator('#themes article.item').first()).toBeVisible();
 const g=await page.locator('#themes article.item').evaluateAll(rs=>rs.map(r=>[...r.querySelectorAll('.row-acts .act')].map(a=>a.textContent.trim())));
 expect(g.length).toBeGreaterThan(0);for(const labels of g){expect(labels[0]).toBe('Ver ficha');expect(labels.at(-1)).toBe('Compartir')}
});

// Dirección 28-oct 21:49 (punto 3): a very long title (Diario Oficial decrees run ~9 lines on a phone) clamps to
// three lines with an ellipsis in the row; the ficha shows it in full.
test('a 350-character title clamps to three lines in the row at 390px and is complete in the ficha',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 const snap=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8'));
 const base=snap.signals.find(s=>!s.stats_ficha&&!s.statistical_view&&/diario oficial/i.test(s.source_name||''))||snap.signals.find(s=>!s.stats_ficha&&!s.statistical_view);
 const head='Decreto exento número 69, de 2026.- Aprueba Norma Técnica Operativa N° 264 que establece los requisitos ';
 const title=(head+'sobre certificación de las especialidades y subespecialidades de los prestadores individuales de salud, '.repeat(4)).slice(0,350);
 expect(title.length).toBe(350);
 const card={...base,title,display_title:title,event_date:'2026-10-11',piece_id:'long-title-test'};
 await page.route('**/data/radar_today.json',route=>route.fulfill({json:{...snap,date:'2026-10-12',generated_at:'2026-10-12T12:00:00Z',signals:[card]}}));
 await page.goto('/');const row=page.locator('#local article[data-card="long-title-test"]');await expect(row).toHaveCount(1);
 const m=await row.locator('.title-open').evaluate(el=>{const cs=getComputedStyle(el),lh=parseFloat(cs.lineHeight);return {lines:Math.round(el.getBoundingClientRect().height/lh),clamp:cs.webkitLineClamp||cs.getPropertyValue('-webkit-line-clamp'),clipped:el.scrollHeight>el.clientHeight+1,text:el.textContent}});
 expect(m.lines).toBeLessThanOrEqual(3);expect(String(m.clamp)).toBe('3');expect(m.clipped).toBeTruthy();expect(m.text).toBe(title);
 expect(await row.locator('.row-acts .act').first().textContent()).toContain('Ver ficha');
 await row.locator('.act-open').click();
 await expect(page.locator('#detailTitle')).toHaveText(title);
 const d=await page.locator('#detailTitle').evaluate(el=>({clipped:el.scrollHeight>el.clientHeight+1,clamp:getComputedStyle(el).webkitLineClamp}));
 expect(d.clipped).toBeFalsy();expect(['none','',undefined]).toContain(d.clamp);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});
