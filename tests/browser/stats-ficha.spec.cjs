const {test,expect}=require('./fixtures.cjs');
const fs=require('node:fs');

const path=require('node:path');
const SHOTS=process.env.ALICANTO_SHOTS_DIR||'artifacts';
// Scrolls the ficha dialog so that `el` sits `below` px under the dialog's top edge (the sticky picker's height).
const scrollTo=(loc,below=0)=>loc.evaluate((e,b)=>{const d=e.closest('dialog');d.scrollTop+=e.getBoundingClientRect().top-d.getBoundingClientRect().top-b},below);
const shot=async(page,name)=>{fs.mkdirSync(SHOTS,{recursive:true});await page.screenshot({path:path.join(SHOTS,`${name}.png`),fullPage:false})};
const f1Card=()=>JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8')).signals.find(s=>s.stats_ficha&&s.stats_ficha.family==='F1');
async function openF1(page,card){
 await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-10-12',generated_at:'2026-10-12T12:00:00Z',signals:[card]}}));
 await page.goto('/');
 const row=page.locator('article[data-card]').filter({hasText:card.title});
 await expect(row).toHaveCount(1);
 return row;
}
// Every SVG text of the shown charts stays inside its viewBox; x-axis labels never overlap.
const labelsFit=page=>page.evaluate(()=>[...document.querySelectorAll('#detailBody .sf-tpanel:not([hidden]) svg[role=img], #detailBody .sf-index svg[role=img]')].map(s=>{
 const vb=s.viewBox.baseVal,texts=[...s.querySelectorAll('text')],bad=texts.filter(t=>{const b=t.getBBox();return b.x<-1||b.x+b.width>vb.width+1||b.y<-1||b.y+b.height>vb.height+1}).map(t=>t.textContent);
 const xl=[...s.querySelectorAll('text.sf-xlab')].map(t=>t.getBBox()).sort((a,b)=>a.x-b.x);
 return {chart:s.closest('[data-chart]')?.dataset.chart||'spark',bad,overlap:xl.some((b,i)=>i&&b.x<xl[i-1].x+xl[i-1].width)}}));
const noOverflow=page=>page.evaluate(()=>{const d=document.getElementById('signalDetail');return document.documentElement.scrollWidth<=innerWidth+1&&d.scrollWidth<=d.clientWidth+1&&
 [...d.querySelectorAll('.sf-row,.sf-pick,.sf-next,.sf-kpi')].filter(e=>e.offsetParent).every(e=>e.scrollWidth<=e.clientWidth+1)});

// F1 statistics ficha, option C→B (Dirección 29-oct-2026) at 390 and 1440 px: the ficha opens as an index of topics;
// a topic opens with the sticky picker and the hero chart first; Back, the picker and the foot return to the index.
test('F1 ficha opens as an index and walks its topics',async({page})=>{
 const card=f1Card();
 expect(card.data_period).toBe('2026-08');
 await page.addInitScript(()=>{Object.defineProperty(navigator,'share',{value:undefined,configurable:true});
  window.__copied=[];Object.defineProperty(navigator,'clipboard',{value:{writeText:async t=>{window.__copied.push(t)}},configurable:true})});
 const row=await openF1(page,card);
 const mobile=test.info().project.name==='mobile';
 await expect(row).toContainText('Datos a 2026-08');
 // Opción B on the stats row: Ver ficha · Fuente original (only with a source link) · Compartir (share page deep link).
 expect(await row.locator('.row-acts .act').evaluateAll(xs=>xs.map(a=>a.textContent.trim()))).toEqual(['Ver ficha','Fuente original','Compartir']);
 await expect(row.locator('.act-share')).toHaveAttribute('data-share-url',card.share_url);
 await row.locator('[data-detail]').first().click();
 const body=page.locator('#detailBody'),dialog=page.locator('#signalDetail');
 // Header and chrome as in the approved mockup (Dirección 29-oct): the top bar holds only '← Volver' and the round share
 // icon; 'Fuente original ↗' and the read toggle are at the foot, after Notas y fuentes; no 'Seguir <entidad>' chips.
 await expect(page.locator('#detailActs .act')).toHaveCount(0);
 await expect(dialog.locator('.follow-row, .follow-chip')).toHaveCount(0);await expect(dialog).not.toContainText('Seguir ');
 const share=dialog.locator('.detail-top .sf-share');
 await expect(share).toHaveAttribute('aria-label','Compartir informe');await expect(body.locator('.sf-share, .sf-actions')).toHaveCount(0);
 expect(await dialog.locator('.detail-top').locator('a,button').evaluateAll(xs=>xs.map(x=>x.id||x.className))).toEqual(['closeDetail','sf-share']);
 const foot=body.locator('#detailFoot');
 await expect(foot.locator('#detailRead')).toHaveText('Marcar no leída');
 expect(await foot.locator('a,button').evaluateAll(xs=>xs.map(x=>x.textContent.trim()))).toEqual(['Fuente original ↗','Marcar no leída']);
 await expect(foot.locator('a')).toHaveAttribute('href',/^https:\/\//);
 expect(await page.evaluate(()=>{const n=document.querySelector('#detailBody .sf-notes'),f=document.getElementById('detailFoot');return Boolean(n.compareDocumentPosition(f)&Node.DOCUMENT_POSITION_FOLLOWING)})).toBe(true);
 // Kicker + 'Destacada' on one line; the two-line meta list under the headline; the headline and dek are the builder's.
 await expect(body.locator('.sf-kicker')).toHaveText('Cartera y movilidadDestacada');
 expect(await body.locator('.sf-meta li').allTextContents()).toEqual(['Datos a agosto 2026','Publicado por la SIS el 2 oct 2026']);
 await expect(body.locator('.sf-dek')).toHaveText(card.stats_ficha.dek);
 // The share icon sits at the right end of the bar, on the same line as Volver.
 const bar=await page.evaluate(()=>{const r=e=>document.querySelector(e).getBoundingClientRect(),d=r('#signalDetail'),s=r('#signalDetail .sf-share'),b=r('#closeDetail');
  return {right:d.right-s.right,line:Math.abs((s.top+s.height/2)-(b.top+b.height/2)),w:s.width,h:s.height}});
 expect(bar.right).toBeLessThan(40);expect(bar.line).toBeLessThan(4);expect(bar.w).toBeGreaterThanOrEqual(44);expect(bar.h).toBeGreaterThanOrEqual(44);
 await expect(body.locator('.sf-headline')).toHaveText(card.stats_ficha.headline);
 // Index: 5 topics, each with its one-line reading and a sparkline (Regional pending); no topic open yet.
 const index=body.locator('.sf-index'),topic=body.locator('.sf-topic');
 await expect(index).toBeVisible();await expect(topic).toBeHidden();
 expect(await body.locator('.sf-row-label').evaluateAll(xs=>xs.map(x=>x.firstChild.textContent))).toEqual(['Cartera total','Por Isapre','Cotizantes y cargas','Movilidad y desahucios','Regional']);
 await expect(body.locator('.sf-row').nth(1)).toContainText('Banmédica: 77% de la baja · 3 Isapres crecen');
 await expect(body.locator('.sf-index .sf-spark svg')).toHaveCount(4);
 // Regional (pending) says 'pendiente' once, in its sparkline slot; no second badge next to its label.
 const regional=body.locator('.sf-row').filter({hasText:'Regional'});
 await expect(regional.locator('.sf-spark-pend')).toHaveText('pendiente');await expect(regional.locator('.sf-row-label .sf-pending')).toHaveCount(0);
 expect((await regional.innerText()).match(/pendiente/gi)).toHaveLength(1);
 await expect(body.locator('.sf-kpi:visible')).toHaveCount(0);await expect(body.locator('.sf-watch')).toHaveCount(0);
 await expect(body.locator('details.sf-notes')).not.toHaveAttribute('open','');
 await expect(body.locator('.sf-reading')).toHaveCount(0);  // no verified Lectura in this release
 for(const r of await labelsFit(page))expect(r.bad,r.chart).toEqual([]);
 expect(await noOverflow(page)).toBeTruthy();
 const box=await body.locator('.sf-row').first().boundingBox();expect(box.height).toBeGreaterThanOrEqual(44);
 await share.click();
 await expect(dialog.locator('.sf-share-status')).toHaveText('Enlace copiado.');
 expect(await page.evaluate(()=>window.__copied[0])).toMatch(/\/data\/fichas\/f1_cartera\.html$/);
 await dialog.locator('.sf-share-status').evaluate(e=>{e.textContent=''});
 await shot(page,`stats-ficha-f1-index-${test.info().project.name}`);
 // Index → topic pushes a history entry: #sig-<id>&tema=total, the picker reads 'Cartera total 1/5', the stock line comes first.
 const len0=await page.evaluate(()=>history.length);
 await body.locator('.sf-row').filter({hasText:'Cartera total'}).click();
 await expect(page).toHaveURL(/#sig-[^&]+&tema=total$/);expect(await page.evaluate(()=>history.length)).toBe(len0+1);
 await expect(index).toBeHidden();await expect(topic).toBeVisible();
 await expect(body.locator('.sf-pick-label')).toHaveText('Cartera total');await expect(body.locator('.sf-pick-count')).toHaveText('1/5');
 const panel=body.locator('.sf-tpanel:not([hidden])');
 expect(await panel.locator('.sf-chart').evaluateAll(xs=>xs.map(x=>x.dataset.chart))).toEqual(['f1-stock','f1-mm']);
 await expect(panel.locator('.sf-tdek')).toHaveCount(0);await expect(panel.locator('.sf-kpi')).toHaveCount(0);
 await expect(panel.locator('svg[role=img]').nth(1)).toHaveAttribute('aria-label',/Ago −814/);
 // In topic mode the top bar's left button reads '← Todos los temas' (mockup .mk-bar.topic).
 await expect(page.locator('#closeDetail')).toContainText('Todos los temas');await expect(page.locator('#closeDetail')).toHaveAttribute('aria-label','Volver a todos los temas');
 await expect(dialog.locator('.detail-top')).toHaveClass(/sf-bar-topic/);
 // The picker pins right under the sticky top bar and the hero chart starts right below it.
 const pinned=()=>page.evaluate(()=>{const r=e=>document.querySelector(e).getBoundingClientRect(),bar=r('#signalDetail .detail-top'),pick=r('#detailBody .sf-sticky'),hero=r('#detailBody .sf-tpanel:not([hidden]) .sf-hero');
  return Math.abs(pick.top-bar.bottom)<3&&bar.top>=r('#signalDetail').top-1&&hero.top-pick.bottom<40&&hero.top>pick.bottom-1});
 await expect.poll(pinned,{timeout:3000}).toBe(true);  // after the smooth scroll
 for(const r of await labelsFit(page)){expect(r.bad,r.chart).toEqual([]);expect(r.overlap,r.chart).toBeFalsy()}
 for(const loc of [body.locator('.sf-pick'),body.locator('.sf-step').last()]){const b=await loc.boundingBox();expect(b.height).toBeGreaterThanOrEqual(44)}
 await shot(page,`stats-ficha-f1-total-${test.info().project.name}`);
 // ‹ › switch topics and replace the entry (no new history); the by-Isapre table splits cambio into cotizantes and cargas.
 await body.locator('[data-sf-step="1"]').click();
 await expect(page).toHaveURL(/#sig-[^&]+&tema=isapres$/);expect(await page.evaluate(()=>history.length)).toBe(len0+1);
 await expect(body.locator('.sf-pick-count')).toHaveText('2/5');
 await expect(panel.locator('.sf-tdek')).toHaveCount(0);await expect(panel.locator('.sf-kpi')).toHaveCount(0);
 const isa=panel.locator('[data-chart="f1-isapres"]');
 await isa.locator('summary').click();
 expect(await isa.locator('thead th').evaluateAll(xs=>xs.map(x=>x.textContent))).toEqual(['Isapre','Cambio','Cotizantes','Cargas','% vs. enero']);
 const trs=await isa.locator('tbody tr').evaluateAll(rs=>rs.map(r=>[...r.children].map(c=>c.textContent)));
 expect(trs.at(-1)).toEqual(['Sistema','−27.355','−5.895','−21.460','−1,09%']);expect(trs.map(r=>r[0])).toContain('Cerradas (3)');
 const n=x=>Number(x.replace('−','-').replace('+','').replace(/\./g,''));for(const r of trs)expect(n(r[1])).toBe(n(r[2])+n(r[3]));
 expect(await noOverflow(page)).toBeTruthy();
 await scrollTo(isa.locator('summary'),76);
 await shot(page,`stats-ficha-f1-isapres-table-${test.info().project.name}`);
 await isa.locator('summary').click();
 // The picker (select-only combobox): keyboard opens it on the current topic; ↓ + Enter picks the next one.
 await body.locator('.sf-pick').focus();await page.keyboard.press('Enter');
 const list=body.locator('[role=listbox]');await expect(list).toBeVisible();await expect(list).toBeFocused();
 await expect(body.locator('.sf-pick')).toHaveAttribute('aria-expanded','true');
 expect(await list.getAttribute('aria-activedescendant')).toBe(await body.locator('[role=option][aria-selected=true]').getAttribute('id'));
 await expect(list.locator('[role=option]').first()).toContainText('Todos los temas');
 await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
 await expect(list).toBeHidden();await expect(body.locator('.sf-pick')).toBeFocused();
 await expect(page).toHaveURL(/#sig-[^&]+&tema=mezcla$/);
 // Cotizantes y cargas: hero chart, then the dek and the two KPI cards from the evidence, then the ratio chart.
 await expect(panel.locator('.sf-tdek')).toHaveText('Las cargas explican el 78% de la baja del año.');
 expect(await panel.locator('.sf-kpi').evaluateAll(xs=>xs.map(x=>[x.querySelector('.sf-lab').textContent,x.querySelector('.sf-val').firstChild.textContent,x.querySelector('.sf-delta').textContent])))
  .toEqual([['Cotizantes','1.551.169','−5.895 desde enero (−0,38%)'],['Cargas','935.514','−21.460 desde enero (−2,24%)']]);
 for(const r of await labelsFit(page)){expect(r.bad,r.chart).toEqual([]);expect(r.overlap,r.chart).toBeFalsy()}
 // '0,603' sits below its point (the series descends into August).
 const lab=await panel.locator('[data-chart="f1-mix"] text.sf-lastlab').evaluate(t=>{const p=[...t.parentNode.querySelectorAll('circle')].pop();return t.getBBox().y-Number(p.getAttribute('cy'))});
 expect(lab).toBeGreaterThan(0);
 await scrollTo(body.locator('.sf-topic'));
 await shot(page,`stats-ficha-f1-cotizantes-${test.info().project.name}`);
 // ← / → change topic in topic mode (desktop keyboard).
 if(!mobile){await page.locator('body').press('ArrowRight');await expect(page).toHaveURL(/#sig-[^&]+&tema=movilidad$/);await page.locator('body').press('ArrowLeft');await expect(page).toHaveURL(/#sig-[^&]+&tema=mezcla$/)}
 // Browser Back returns to the index (dialog stays open), highlighting and focusing the last topic's row.
 await page.goBack();
 await expect(index).toBeVisible();await expect(topic).toBeHidden();await expect(dialog).toBeVisible();
 expect(page.url()).not.toContain('tema=');
 const last=body.locator('.sf-row').filter({hasText:'Cotizantes y cargas'});await expect(last).toHaveClass(/sf-last/);await expect(last).toBeFocused();
 await expect(page.locator('#closeDetail')).toContainText('Volver');await expect(page.locator('#closeDetail')).toHaveAttribute('aria-label','Cerrar ficha');
 // The foot's 'Siguiente tema' and 'Todos los temas', and the dialog's back button in topic mode, also lead back.
 await body.locator('.sf-row').filter({hasText:'Movilidad y desahucios'}).click();
 await expect(panel.locator('.sf-tdek')).toHaveCount(0);await expect(panel.locator('.sf-kpi')).toHaveCount(0);
 await panel.locator('.sf-next').click();await expect(page).toHaveURL(/#sig-[^&]+&tema=regional$/);
 await expect(panel).toContainText('Alicanto aún no extrae');await expect(panel.locator('.sf-links a').first()).toHaveAttribute('href',/a-nivel-regional-agosto-2026/);
 await expect(panel.locator('.sf-next')).toHaveCount(0);await expect(body.locator('[data-sf-step="1"]')).toBeDisabled();
 await panel.locator('.sf-all').click();await expect(index).toBeVisible();expect(page.url()).not.toContain('tema=');
 await body.locator('.sf-row').first().click();await expect(topic).toBeVisible();
 await page.locator('#closeDetail').click();await expect(index).toBeVisible();await expect(dialog).toBeVisible();
 await page.locator('#closeDetail').click();await expect(dialog).toBeHidden();
 // Closing in topic mode leaves no topic in the URL.
 await row.locator('[data-detail]').first().click();await body.locator('.sf-row').nth(2).click();await expect(page).toHaveURL(/#sig-[^&]+&tema=mezcla$/);
 await page.keyboard.press('Escape');await expect(dialog).toBeHidden();await expect.poll(()=>page.url()).not.toContain('tema=');
});

test('a #tema deep link opens that topic directly and Back leaves it',async({page})=>{
 const card=f1Card();
 await openF1(page,card);
 const id=encodeURIComponent(`sig-${card.piece_id}`);
 await page.goto(`/index.html?abrir=1#${id}&tema=movilidad`);
 const body=page.locator('#detailBody');
 await expect(page.locator('#signalDetail')).toBeVisible();
 await expect(body.locator('.sf-topic')).toBeVisible();await expect(body.locator('.sf-index')).toBeHidden();
 await expect(body.locator('.sf-pick-label')).toHaveText('Movilidad y desahucios');await expect(body.locator('.sf-pick-count')).toHaveText('4/5');
 expect(page.url()).not.toContain('abrir=1');
 // 'Todos los temas' from the picker: the topic is dropped from the URL, the signal stays.
 await body.locator('.sf-pick').click();await body.locator('[role=option]').first().click();
 await expect(body.locator('.sf-index')).toBeVisible();
 expect(page.url()).toContain(`#${id}`);expect(page.url()).not.toContain('tema=');
});

// Independent review 29-oct: a topic URL keeps the signal anchor, so copying it from the address bar reopens the ficha
// on that topic; an unknown topic opens the ficha at its index (never a silent no-op) and is dropped from the URL.
test('a copied topic URL reopens the ficha; an unknown topic opens its index',async({page})=>{
 const card=f1Card();
 const row=await openF1(page,card);
 const id=encodeURIComponent(`sig-${card.piece_id}`),body=page.locator('#detailBody'),dialog=page.locator('#signalDetail');
 await row.locator('[data-detail]').first().click();
 await body.locator('.sf-row').filter({hasText:'Cotizantes y cargas'}).click();
 await expect(page).toHaveURL(new RegExp(`#${id}&tema=mezcla$`));
 await expect(body.locator('.sf-row').first()).toHaveAttribute('href',`#${id}&tema=total`);
 const copied=page.url();
 await page.goto('about:blank');await page.goto(copied);  // a fresh load of the copied URL (no ?abrir=1)
 await expect(dialog).toBeVisible();await expect(body.locator('.sf-topic')).toBeVisible();
 await expect(body.locator('.sf-pick-label')).toHaveText('Cotizantes y cargas');await expect(body.locator('.sf-pick-count')).toHaveText('3/5');
 // Closing the reopened ficha drops the topic and keeps the signal anchor.
 await page.locator('#closeDetail').click();await expect(body.locator('.sf-index')).toBeVisible();
 expect(page.url()).toContain(`#${id}`);expect(page.url()).not.toContain('tema=');
 await page.locator('#closeDetail').click();await expect(dialog).toBeHidden();
 // An unknown topic: the ficha opens at its index and the bad '&tema=' leaves the URL.
 for(const bad of ['nope','x.y']){
  await page.goto('about:blank');await page.goto(`/index.html#${id}&tema=${bad}`);
  await expect(dialog).toBeVisible();await expect(body.locator('.sf-index')).toBeVisible();await expect(body.locator('.sf-topic')).toBeHidden();
  await expect.poll(()=>page.url()).not.toContain('tema=');expect(page.url()).toContain(`#${id}`);
 }
 // Closing the ficha also strips an unknown '&tema=' that reached the URL after it opened.
 await page.evaluate(h=>history.replaceState(null,'',location.pathname+h),`#${id}&tema=nope`);
 await page.locator('#closeDetail').click();await expect(dialog).toBeHidden();
 await expect.poll(()=>page.url()).not.toContain('tema=');expect(page.url()).toContain(`#${id}`);
});

test('swipe changes topic on phones',async({page})=>{
 test.skip(test.info().project.name!=='mobile','touch only');
 const row=await openF1(page,f1Card());
 await row.locator('[data-detail]').first().click();
 const body=page.locator('#detailBody');
 await body.locator('.sf-row').first().click();await expect(page).toHaveURL(/#sig-[^&]+&tema=total$/);
 const swipe=dx=>body.locator('.sf-tpanels').evaluate((el,dx)=>{const r=el.getBoundingClientRect(),y=r.top+80,x=r.left+r.width/2;
  const t=(cx)=>new Touch({identifier:1,target:el,clientX:cx,clientY:y});
  el.dispatchEvent(new TouchEvent('touchstart',{touches:[t(x)],changedTouches:[t(x)],bubbles:true}));
  el.dispatchEvent(new TouchEvent('touchend',{touches:[],changedTouches:[t(x+dx)],bubbles:true}))},dx);
 await swipe(-120);await expect(page).toHaveURL(/#sig-[^&]+&tema=isapres$/);
 await swipe(120);await expect(page).toHaveURL(/#sig-[^&]+&tema=total$/);
 await swipe(30);await expect(page).toHaveURL(/#sig-[^&]+&tema=total$/);  // short moves are scrolls, not swipes
});

// 320 and 390 px with CI's fallback font (DejaVu Sans, wider than local fonts): index rows, picker, KPI cards and every
// chart label fit inside the dialog and their viewBox, in every topic.
for(const width of [320,390]){
 test(`F1 ficha fits ${width} px with DejaVu Sans`,async({page})=>{
  test.skip(test.info().project.name!=='mobile','narrow widths run once, in the mobile project');
  await page.setViewportSize({width,height:740});
  const row=await openF1(page,f1Card());
  await page.addStyleTag({content:'*,svg text{font-family:"DejaVu Sans",sans-serif!important}'});
  await row.locator('[data-detail]').first().click();
  const body=page.locator('#detailBody');
  await expect(body.locator('.sf-index')).toBeVisible();
  for(const r of await labelsFit(page))expect(r.bad,r.chart).toEqual([]);
  expect(await noOverflow(page),'index').toBeTruthy();
  await body.locator('.sf-row').first().click();
  for(let i=0;i<5;i++){
   if(i)await body.locator('[data-sf-step="1"]').click();
   await expect(body.locator('.sf-pick-count')).toHaveText(`${i+1}/5`);
   const label=await body.locator('.sf-pick-label').textContent();
   for(const r of await labelsFit(page)){expect(r.bad,`${label} ${r.chart}`).toEqual([]);expect(r.overlap,`${label} ${r.chart}`).toBeFalsy()}
   expect(await noOverflow(page),label).toBeTruthy();
   // The picker keeps its label, count and both arrows on one line.
   // Measured in one frame (two boundingBox calls can straddle the smooth scroll to the topic), until settled.
   await expect.poll(()=>page.evaluate(()=>{const d=document.getElementById('detailBody');const a=d.querySelector('.sf-pick').getBoundingClientRect(),b=d.querySelector('[data-sf-step="1"]').getBoundingClientRect();return Math.abs(a.top-b.top)}),{timeout:3000}).toBeLessThan(2);
  }
  if(width===390)await shot(page,'stats-ficha-f1-390-dejavu');
 });
}

test('the F1 share page redirects to the ficha deep link',async({page})=>{
 const snap=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8'));
 const card=snap.signals.find(s=>s.stats_ficha);
 await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-10-12',generated_at:'2026-10-12T12:00:00Z',signals:[card]}}));
 await page.goto('/data/fichas/f1_cartera.html');
 await page.waitForURL(/index\.html#sig-stats-ficha/);
 await expect(page.locator('article[data-card]').filter({hasText:card.title})).toHaveCount(1);
 // The share link opens the ficha detail, not just the row.
 await expect(page.locator('#signalDetail')).toBeVisible();
 await expect(page.locator('#detailBody .sf-headline')).toHaveText(card.stats_ficha.headline);
 expect(page.url()).not.toContain('abrir=1');
});

test('the withdrawn GES finding shows a dated public correction',async({page})=>{
 const snap=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8'));
 const ges=snap.signals.find(s=>s.statistical_view&&s.statistical_view.correction);
 expect(ges).toBeTruthy();
 // The GES release (14-oct) is after the suite's pinned fixture day; pin the clock to the correction day.
 await page.clock.setFixedTime(new Date('2026-10-28T12:00:00-03:00'));
 await page.route('**/data/radar_today.json',route=>route.fulfill({json:{date:'2026-10-28',generated_at:'2026-10-28T12:00:00Z',signals:[ges]}}));
 await page.goto('/');
 const row=page.locator('article[data-card]').filter({hasText:ges.title});
 await expect(row.locator('.correction-tag')).toHaveText('Corregido el 28 oct');
 await row.locator('[data-detail]').first().click();
 await expect(page.locator('#detailBody .stat-correction')).toContainText('Corregido el 28 oct:');
 await expect(page.locator('#detailBody')).not.toContainText('21 presenta');
});

// Dirección 29-oct, compact header at 390×844 with CI's fallback font: in the index view the first two topic rows show
// whole without scrolling; in topic mode the top half of the hero chart shows under the sticky selector, also with the
// ficha scrolled to its top. Measured in one page.evaluate, with motion reduced (instant scroll, no smooth-scroll race).
const fold=(page,sel)=>page.evaluate(sel=>{const d=document.getElementById('signalDetail'),r=d.getBoundingClientRect(),bottom=Math.min(innerHeight,r.bottom-parseFloat(getComputedStyle(d).borderBottomWidth||0));
 const els=[...document.querySelectorAll(sel)].filter(e=>e.offsetParent).map(e=>{const b=e.getBoundingClientRect();return {top:b.top,bottom:b.bottom,mid:b.top+b.height/2}});
 const st=document.querySelector('#detailBody .sf-topic:not([hidden]) .sf-sticky');return {bottom,top:r.top,scroll:d.scrollTop,els,sticky:st?st.getBoundingClientRect().bottom:null}},sel);
test('F1 compact header: index rows and the hero chart show above the fold at 390×844',async({page})=>{
 test.skip(test.info().project.name!=='mobile','390×844 runs once, in the mobile project');
 await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:'reduce'});
 const row=await openF1(page,f1Card());
 await page.addStyleTag({content:'*,svg text{font-family:"DejaVu Sans",sans-serif!important}'});
 await row.locator('[data-detail]').first().click();
 const body=page.locator('#detailBody');await expect(body.locator('.sf-index')).toBeVisible();
 // The bar is a single row; the kicker is a single line.
 expect(await page.evaluate(()=>document.querySelector('#signalDetail .detail-top').getBoundingClientRect().height)).toBeLessThanOrEqual(52);
 expect(await body.locator('.sf-kicker').evaluate(e=>e.getBoundingClientRect().height)).toBeLessThan(24);
 const ix=await fold(page,'#detailBody .sf-row');
 expect(ix.scroll).toBe(0);expect(ix.els.length).toBe(5);
 // As in the mockup at 390×844: every topic row of the index (at least the first two, Dirección's target) is above the fold.
 for(const r of ix.els)expect(r.bottom,'index row above the fold').toBeLessThanOrEqual(ix.bottom);
 await shot(page,'stats-ficha-f1-fold-index-390x844');
 // Topic mode on 'Por Isapre': the hero chart's top half shows under the sticky selector.
 await body.locator('.sf-row').filter({hasText:'Por Isapre'}).click();
 await expect(body.locator('.sf-pick-label')).toHaveText('Por Isapre');
 const hero=body.locator('.sf-tpanel:not([hidden]) .sf-hero .sf-chart');await expect(hero).toBeVisible();
 await expect.poll(async()=>{const t=await fold(page,'#detailBody .sf-tpanel:not([hidden]) .sf-hero .sf-chart');const h=t.els[0];return h.top>=t.sticky-1&&h.mid<=t.bottom},{timeout:3000}).toBe(true);
 await shot(page,'stats-ficha-f1-fold-isapres-390x844');
 // The sticky bar and picker are opaque (page background) with the mockup's divider: nothing shows through them.
 const chrome=await page.evaluate(()=>[document.querySelector('#signalDetail .detail-top'),document.querySelector('#detailBody .sf-sticky')].map(e=>{const c=getComputedStyle(e);return {bg:c.backgroundColor,border:c.borderBottomColor,width:c.borderBottomWidth}}));
 for(const c of chrome)expect(c.bg).toBe('rgb(250, 249, 245)');
 expect(chrome[0].width).toBe('1px');await expect(body.locator('.sf-sticky')).toHaveClass(/stuck/);
 // The bar's divider fades in (0.2 s border transition): polled until settled.
 for(const sel of ['#signalDetail .detail-top','#detailBody .sf-sticky'])
  await expect.poll(()=>page.evaluate(s=>getComputedStyle(document.querySelector(s)).borderBottomColor,sel),{timeout:3000}).toBe('rgb(228, 223, 211)');
 // Even with the ficha scrolled back to its top (header in view), the hero's top half is above the fold.
 await page.evaluate(()=>{document.getElementById('signalDetail').scrollTop=0});
 const t0=await fold(page,'#detailBody .sf-tpanel:not([hidden]) .sf-hero .sf-chart');
 expect(t0.scroll).toBe(0);expect(t0.els[0].mid,'hero top half above the fold').toBeLessThanOrEqual(t0.bottom);
 // '← Todos los temas' in the sticky top bar, right above the sticky picker, stays in view while scrolling and returns
 // to the index.
 await page.evaluate(()=>{const d=document.getElementById('signalDetail');d.scrollTop=d.scrollHeight});
 const topAll=page.locator('#closeDetail');await expect(topAll).toContainText('Todos los temas');
 const inView=await topAll.evaluate(e=>{const b=e.getBoundingClientRect(),d=document.getElementById('signalDetail').getBoundingClientRect(),p=document.querySelector('#detailBody .sf-sticky').getBoundingClientRect();return b.top>=d.top-1&&b.bottom<=p.top+1&&b.height>=44});
 expect(inView).toBeTruthy();
 await topAll.click();
 await expect(body.locator('.sf-index')).toBeVisible();await expect(body.locator('.sf-topic')).toBeHidden();
 await expect.poll(()=>page.url()).not.toContain('tema=');
 await expect(body.locator('.sf-row').filter({hasText:'Por Isapre'})).toHaveClass(/sf-last/);
});

// The top bar's '← Todos los temas' pops the entry the topic pushed, like Back: the URL keeps the ficha's hash only.
test('the top "Todos los temas" button returns to the index like Back',async({page})=>{
 const row=await openF1(page,f1Card());
 await row.locator('[data-detail]').first().click();
 const body=page.locator('#detailBody');
 const len0=await page.evaluate(()=>history.length);
 await body.locator('.sf-row').nth(2).click();await expect(page).toHaveURL(/#sig-[^&]+&tema=mezcla$/);
 await body.locator('[data-sf-step="1"]').click();await expect(page).toHaveURL(/#sig-[^&]+&tema=movilidad$/);
 await expect(page.locator('#closeDetail')).toContainText('Todos los temas');await page.locator('#closeDetail').click();
 await expect(body.locator('.sf-index')).toBeVisible();await expect(page.locator('#signalDetail')).toBeVisible();
 await expect.poll(()=>page.url()).not.toContain('tema=');expect(await page.evaluate(()=>history.length)).toBe(len0+1);
 await expect(body.locator('.sf-row').filter({hasText:'Movilidad y desahucios'})).toBeFocused();
 await expect(page.locator('#closeDetail')).toHaveText('Volver');
});
