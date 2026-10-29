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
 expect(await page.locator('#detailActs .act').evaluateAll(xs=>xs.map(a=>a.textContent.trim()))).toEqual(['Fuente original']);
 const body=page.locator('#detailBody'),dialog=page.locator('#signalDetail');
 await expect(body.locator('.sf-headline')).toHaveText(card.stats_ficha.headline);
 // Index: 5 topics, each with its one-line reading and a sparkline (Regional pending); no topic open yet.
 const index=body.locator('.sf-index'),topic=body.locator('.sf-topic');
 await expect(index).toBeVisible();await expect(topic).toBeHidden();
 expect(await body.locator('.sf-row-label').evaluateAll(xs=>xs.map(x=>x.firstChild.textContent))).toEqual(['Cartera total','Por Isapre','Cotizantes y cargas','Movilidad y desahucios','Regional']);
 await expect(body.locator('.sf-row').nth(1)).toContainText('Banmédica: 77% de la baja · 3 Isapres crecen');
 await expect(body.locator('.sf-index .sf-spark svg')).toHaveCount(4);
 await expect(body.locator('.sf-kpi:visible')).toHaveCount(0);await expect(body.locator('.sf-watch')).toHaveCount(0);
 await expect(body.locator('details.sf-notes')).not.toHaveAttribute('open','');
 await expect(body.locator('.sf-reading')).toHaveCount(0);  // no verified Lectura in this release
 for(const r of await labelsFit(page))expect(r.bad,r.chart).toEqual([]);
 expect(await noOverflow(page)).toBeTruthy();
 const box=await body.locator('.sf-row').first().boundingBox();expect(box.height).toBeGreaterThanOrEqual(44);
 await body.locator('.sf-share').click();
 await expect(body.locator('.sf-share-status')).toHaveText('Enlace copiado.');
 expect(await page.evaluate(()=>window.__copied[0])).toMatch(/\/data\/fichas\/f1_cartera\.html$/);
 await body.locator('.sf-share-status').evaluate(e=>{e.textContent=''});
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
 await expect(page.locator('#closeDetail')).toContainText('Todos los temas');
 // The picker pins under the dialog's top and the hero chart starts right below it.
 const pinned=async()=>{const pick=await body.locator('.sf-sticky').boundingBox(),dtop=(await dialog.boundingBox()).y,hero=await panel.locator('.sf-hero').boundingBox();
  return Math.abs(pick.y-dtop)<4&&hero.y-(pick.y+pick.height)<40&&hero.y>pick.y+pick.height-1};
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
 await expect(page.locator('#closeDetail')).toContainText('Volver');
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
   const [p,s]=await Promise.all([body.locator('.sf-pick').boundingBox(),body.locator('[data-sf-step="1"]').boundingBox()]);
   expect(Math.abs(p.y-s.y)).toBeLessThan(2);
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
