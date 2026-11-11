const {test,expect}=require('./fixtures.cjs');
const fs=require('node:fs');
const path=require('node:path');
const SHOTS=process.env.ALICANTO_SHOTS_DIR||'artifacts';

// Datos (Dirección, 3-nov-2026): latest published ficha per statistics family, from data/datos.json (served copy).
const datos=async page=>(await page.request.get('/data/datos.json')).json();
const live=d=>d.families.filter(f=>f.state==='live');
const noHScroll=page=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1);

test('Datos: Recientes by default, Por grupo by actor, the choice persists',async({page})=>{
 const d=await datos(page);expect(live(d).length).toBeGreaterThan(0);
 await page.goto('/datos.html');
 const rows=page.locator('#datosList [data-family]');await expect(rows).toHaveCount(d.families.length);
 await expect(page.locator('#datosView [data-view="recientes"]')).toHaveAttribute('aria-pressed','true');
 // Live cards first, newest verification first; planned/pending greyed at the end.
 const order=await rows.evaluateAll(xs=>xs.map(x=>x.dataset.family));
 const expected=[...live(d)].sort((a,b)=>String(b.updated_on).localeCompare(String(a.updated_on))||a.order-b.order).map(f=>f.family);
 expect(order.slice(0,expected.length)).toEqual(expected);
 for(const f of d.families.filter(f=>f.state!=='live'))await expect(page.locator(`.dx-soon[data-family="${f.family}"] .dx-tag`)).toHaveText(f.state==='planned'?'pronto':'en verificación');
 // Each live card (Dirección 10-nov-2026): «Datos <período> · <cadencia>», descriptive title (not the finding headline),
 // its topics with their published labels, the Chile date line and «Compartir»; no KPI block, no «Vigente».
 for(const f of live(d)){
  const c=page.locator(`.dx-item[data-family="${f.family}"] .dc-card`);
  await expect(c.locator('.dc-src')).toHaveText(new RegExp(`^Datos ${f.period_label} · ${f.cadence.replace(/[()]/g,'\\$&')}`));
  expect(f.period_label).toMatch(/^((ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)–)?(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic) 20\d\d$/);
  await expect(c.locator('.dc-title')).toHaveText(f.index_title);
  await expect(c).not.toContainText(f.headline);
  expect(await c.locator('.dc-t .dc-l').allTextContents()).toEqual(f.topics.map(t=>t.label));
  await expect(c.locator('.dc-meta')).toContainText(new RegExp(`^(Detectado|Publicado|Actualizado) .+ · ${f.source}$`));
  await expect(c.locator('.act-share')).toHaveAttribute('data-share-url',f.share_url);
  await expect(c.locator('.dx-kpis,.dx-st,.dx-badge')).toHaveCount(0);
  expect(await c.locator('.dc-open').getAttribute('href')).toBe(`index.html?abrir=1&desde=datos#sig-${f.piece_id}`);
 }
 await expect(page.locator('body')).not.toContainText(/cómo leer/i);
 await page.locator('#datosView [data-view="grupo"]').click();
 await expect(page.locator('#datosView [data-view="grupo"]')).toHaveAttribute('aria-pressed','true');
 const heads=await page.locator('#datosList .dx-sec').allTextContents();
 const groups=d.groups.filter(g=>d.families.some(f=>f.group===g.key)).map(g=>g.label);
 expect(heads).toEqual(groups);
 for(const f of d.families){const g=d.groups.find(x=>x.key===f.group);await expect(page.locator('.dx-group').filter({has:page.locator('.dx-sec',{hasText:g.label})}).locator(`[data-family="${f.family}"]`)).toHaveCount(1)}
 await page.reload();
 await expect(page.locator('#datosView [data-view="grupo"]')).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('#datosList .dx-sec').first()).toBeVisible();
 await page.locator('#datosView [data-view="recientes"]').click();await page.reload();
 await expect(page.locator('#datosView [data-view="recientes"]')).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('#datosList .dx-sec')).toHaveCount(0);
});

test('Datos works when localStorage throws',async({page})=>{
 await page.addInitScript(()=>{const deny=()=>{throw new Error('blocked')};Storage.prototype.getItem=deny;Storage.prototype.setItem=deny});
 const d=await datos(page);await page.goto('/datos.html');
 await expect(page.locator('#datosList [data-family]')).toHaveCount(d.families.length);
 await page.locator('#datosView [data-view="grupo"]').click();
 await expect(page.locator('#datosList .dx-sec').first()).toBeVisible();
});

test('Data card index: numbered by row, «Ver restantes» toggles with aria and keyboard, 40px targets',async({page})=>{
 const d=await datos(page);await page.goto('/datos.html');
 for(const f of live(d)){
  const c=page.locator(`.dx-item[data-family="${f.family}"] .dc-card`);await expect(c.locator('.dc-t').first()).toBeVisible();
  // Row numbering: 1 2 / 3 4 / 5 6 (same top for each pair, number n+1 to the right of n).
  const boxes=await c.locator('.dc-toc:not([hidden]) .dc-t').evaluateAll(xs=>xs.map(x=>{const r=x.getBoundingClientRect();return {n:x.querySelector('.dc-n').textContent,l:r.left,t:r.top,h:r.height}}));
  expect(boxes.map(b=>b.n)).toEqual(boxes.map((_,i)=>String(i+1)));
  for(let i=0;i+1<boxes.length;i+=2){expect(Math.abs(boxes[i].t-boxes[i+1].t)).toBeLessThan(2);expect(boxes[i+1].l).toBeGreaterThan(boxes[i].l)}
  for(const b of boxes)expect(b.h).toBeGreaterThanOrEqual(40);
  const more=c.locator('.dc-more');
  if(f.topics.length<=6){expect(boxes.length).toBe(f.topics.length);await expect(more).toHaveCount(0);continue}
  expect(boxes.length).toBe(6);
  const rest=f.topics.length-6,list=page.locator(`#${await more.getAttribute('aria-controls')}`);
  await expect(more).toHaveText(`Ver restantes (${rest}) ↓`);await expect(more).toHaveAttribute('aria-expanded','false');await expect(list).toBeHidden();
  expect((await more.boundingBox()).height).toBeGreaterThanOrEqual(40);
  await more.focus();await page.keyboard.press('Enter');
  await expect(more).toHaveAttribute('aria-expanded','true');await expect(more).toHaveText('Ocultar temas ↑');await expect(list).toBeVisible();
  expect(await list.locator('.dc-n').allTextContents()).toEqual(f.topics.slice(6).map((_,i)=>String(i+7)));
  await page.keyboard.press(' ');
  await expect(more).toHaveAttribute('aria-expanded','false');await expect(list).toBeHidden();await expect(more).toBeFocused();
 }
 // Visible focus on a topic link.
 const t=page.locator('.dc-t').first();await t.focus();
 expect(await t.evaluate(x=>getComputedStyle(x).outlineStyle)).not.toBe('none');
});

test('Data card topics open the ficha at that topic (Chile and Datos)',async({page})=>{
 const d=await datos(page);
 // Chile: a statistics ficha in the feed is the same data card; its topic opens the ficha in place at that topic.
 await page.goto('/');
 const row=page.locator('#local article.dc-row').first();await expect(row).toBeVisible();
 const id=await row.getAttribute('data-card'),fam=live(d).find(x=>x.piece_id===id);expect(fam).toBeTruthy();
 // The feed shows 2 topics before «Ver restantes» (Dirección 10-nov 23:29); Datos shows 6.
 const t=fam.topics[Math.min(1,fam.topics.length-1)];
 await expect(row.locator('.dc-toc:not(.dc-rest) .dc-t')).toHaveCount(Math.min(2,fam.topics.length));
 await expect(row.locator('.dc-title')).toHaveText(fam.index_title);
 await expect(row.locator('.dc-top .tag')).toHaveText('Datos');
 await expect(row.locator('.dc-src')).toHaveText(new RegExp(`^Datos ${fam.period_label}`));
 await row.locator(`.dc-t[data-dc-tema="${t.id}"]`).click();
 await expect(page.locator('#signalDetail')).toBeVisible();
 await expect(page.locator('#detailBody [data-sf-view="topic"]')).toBeVisible();
 await expect(page.locator('#detailBody .sf-pick-label')).toHaveText(t.label);
 await expect(page).toHaveURL(new RegExp(`&tema=${t.id}$`));
 // Datos: the same topic link is a deep link that opens the ficha at that topic.
 await page.goto('/datos.html');
 const link=page.locator(`.dx-item[data-family="${fam.family}"] .dc-t[data-dc-tema="${t.id}"]`);
 expect(await link.getAttribute('href')).toBe(`index.html?abrir=1&desde=datos#sig-${fam.piece_id}&tema=${t.id}`);
 await link.click();
 await expect(page.locator('#signalDetail')).toBeVisible();
 await expect(page.locator('#detailBody [data-sf-view="topic"]')).toBeVisible();
 await expect(page.locator('#detailBody .sf-pick-label')).toHaveText(t.label);
});

test('Datos: read state uses the Chile dot; a read here or in Chile shows in both',async({page})=>{
 const d=await datos(page),fams=live(d);expect(fams.length).toBeGreaterThan(1);
 await page.goto('/datos.html');
 const card=f=>page.locator(`.dx-item[data-family="${f.family}"] .dc-card`);
 const first=fams[0];
 await expect(card(first)).not.toHaveClass(/\bread\b/);
 await expect(card(first).locator('.dotbtn .unread-dot')).toHaveCount(1);
 const unread=await card(first).evaluate(c=>({bg:getComputedStyle(c).backgroundColor,w:getComputedStyle(c.querySelector('.dc-title')).fontWeight}));
 expect(unread.bg).toBe('rgb(255, 255, 255)');expect(Number(unread.w)).toBeGreaterThanOrEqual(700);
 // The dot marks it read (tick, regular muted title, no white fill) and back.
 await card(first).locator('.dotbtn').click();
 await expect(card(first)).toHaveClass(/\bread\b/);await expect(card(first).locator('.dotbtn.done')).toHaveCount(1);
 const read=await card(first).evaluate(c=>({bg:getComputedStyle(c).backgroundColor,w:getComputedStyle(c.querySelector('.dc-title')).fontWeight}));
 expect(read.bg).toBe('rgba(0, 0, 0, 0)');expect(Number(read.w)).toBeLessThan(500);
 await card(first).locator('.dotbtn').click();await expect(card(first)).not.toHaveClass(/\bread\b/);
 // Opening the ficha marks it read.
 await card(first).locator('.dc-open').click();
 await expect(page.locator('#signalDetail')).toBeVisible();
 await page.locator('#closeDetail').click();
 await expect(page).toHaveURL(/datos\.html$/);
 await expect(card(first)).toHaveClass(/\bread\b/);
 // Same piece id and IndexedDB store as the inbox: a read recorded in Chile shows in Datos.
 const other=fams[1];
 await page.goto('/');await page.evaluate(id=>AlicantoRead.set(id,true),other.piece_id);
 await page.goto('/datos.html');
 await expect(card(other)).toHaveClass(/\bread\b/);
});

test('Datos and the Chile data card fit 320 and 390 px with no horizontal scroll; nav links Datos on every page',async({page})=>{
 for(const width of [320,390]){
  await page.setViewportSize({width,height:760});
  await page.goto('/datos.html');await expect(page.locator('#datosList .dc-card').first()).toBeVisible();
  for(const b of await page.locator('.dc-more').all())await b.click();
  expect(await noHScroll(page)).toBeTruthy();
  const over=await page.evaluate(()=>[...document.querySelectorAll('.dc-card')].filter(c=>c.scrollWidth>c.clientWidth+1).length);expect(over).toBe(0);
  await page.locator('#datosView [data-view="grupo"]').click();await expect(page.locator('#datosList .dx-sec').first()).toBeVisible();
  expect(await noHScroll(page)).toBeTruthy();
  await page.locator('#datosView [data-view="recientes"]').click();
  await page.goto('/');await expect(page.locator('#local .dc-row').first()).toBeVisible();
  expect(await noHScroll(page)).toBeTruthy();
 }
 await page.setViewportSize({width:320,height:700});
 for(const [url,current] of [['/','index.html'],['/global.html','global.html'],['/datos.html','datos.html']]){
  await page.goto(url);
  const link=page.locator('.brandbar .topnav a[href="datos.html"]');
  await expect(link).toHaveAttribute('data-short','Datos');await expect(link).toBeVisible();
  await expect(page.locator('.topnav a[aria-current="page"]')).toHaveAttribute('href',current);
  const fit=await page.evaluate(()=>{const w=innerWidth,r=el=>el.getBoundingClientRect();const nav=[...document.querySelectorAll('.brandbar .topnav a,.brandbar .premium-access')].filter(e=>e.offsetParent);return {premium:r(document.querySelector('.premium-access')).right,links:nav.map(e=>({l:r(e).left,r:r(e).right})),w}});
  expect(fit.premium).toBeLessThanOrEqual(fit.w);for(const x of fit.links){expect(x.l).toBeGreaterThanOrEqual(0);expect(x.r).toBeLessThanOrEqual(fit.w)}
  expect(await noHScroll(page)).toBeTruthy();
 }
 await page.goto('/sources.html');await expect(page.locator('.sources-page .topnav a[href="datos.html"]')).toHaveText('Datos');
});

test('Datos screenshots at 390 px',async({browser},testInfo)=>{
 test.skip(testInfo.project.name!=='mobile','one set of screenshots');
 const ctx=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:2,isMobile:true,hasTouch:true});
 const page=await ctx.newPage();await page.clock.setFixedTime(new Date('2026-11-10T12:00:00-03:00'));
 fs.mkdirSync(SHOTS,{recursive:true});
 await page.goto('/datos.html');await expect(page.locator('#datosList .dc-card').first()).toBeVisible();
 await page.locator('.dc-more').first().click();
 await page.screenshot({path:path.join(SHOTS,'datos_recientes.png'),fullPage:true});
 await page.locator('#datosView [data-view="grupo"]').click();await expect(page.locator('#datosList .dx-sec').first()).toBeVisible();
 await page.screenshot({path:path.join(SHOTS,'datos_grupo.png'),fullPage:true});
 await ctx.close();
});

// Series largas 1990–2025 (plan comercial): from data/series_isapre.json, built from the SIS workbook with receipts.
test('Datos: series largas 1990–2025 with selector, period, table and source',async({page})=>{
 const s=await (await page.request.get('/data/series_isapre.json')).json();
 await page.goto('/datos.html');
 const sec=page.locator('#seriesLargas');
 await expect(sec.locator('.sl-title')).toHaveText(s.title);
 for(const h of s.highlights){const k=sec.locator(`.sl-kpi[data-kpi="${h.id}"]`);await expect(k.locator('.sl-kv')).toHaveText(h.value);for(const l of h.lines)await expect(k).toContainText(l)}
 await expect(sec.locator('.sl-chart svg')).toHaveAttribute('aria-label',/^Beneficiarios · total, 1990–2025: de 2\.108\.308 a 2\.517\.305; máximo 3\.882\.572 en 1997\.$/);
 await sec.locator('.sl-data summary').click();
 await expect(sec.locator('.sl-table tbody tr')).toHaveCount(36);
 await expect(sec.locator('.sl-table tbody tr').first()).toContainText('2025');
 await sec.locator('[data-range="10"]').click();
 await expect(sec.locator('.sl-table tbody tr')).toHaveCount(10);
 const ban=s.isapres.beneficiarios.find(b=>b.short==='Banmédica');
 await sec.locator('[data-sl="serie"]').selectOption(`isapre-${ban.code}-${ban.tipo}`);
 await expect(sec.locator('.sl-cap')).toContainText('Banmédica');
 await expect(sec.locator('.sl-table tbody tr').first()).toContainText(new Intl.NumberFormat('es-CL').format(ban.values.at(-1)));
 await sec.locator('.sl-notes summary').click();
 await expect(sec.locator('.sl-src a')).toHaveAttribute('href',s.source.page);
 await expect(sec.locator('.sl-src')).toContainText(s.source.sha256.slice(0,12));
 expect(await noHScroll(page)).toBeTruthy();
});
