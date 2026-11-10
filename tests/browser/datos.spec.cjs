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
 const rows=page.locator('#datosList .dx-row');await expect(rows).toHaveCount(d.families.length);
 await expect(page.locator('#datosView [data-view="recientes"]')).toHaveAttribute('aria-pressed','true');
 // Live rows first, newest verification first; planned/pending greyed at the end.
 const order=await rows.evaluateAll(xs=>xs.map(x=>x.dataset.family));
 const expected=[...live(d)].sort((a,b)=>String(b.updated_on).localeCompare(String(a.updated_on))||a.order-b.order).map(f=>f.family);
 expect(order.slice(0,expected.length)).toEqual(expected);
 for(const f of d.families.filter(f=>f.state!=='live'))await expect(page.locator(`.dx-soon[data-family="${f.family}"] .dx-tag`)).toHaveText(f.state==='planned'?'pronto':'en verificación');
 // Each live row: label, verified headline, KPI strings verbatim, "Datos a <mes> <año> · <fuente>", status.
 for(const f of live(d)){
  const row=page.locator(`a.dx-row[data-family="${f.family}"]`);
  await expect(row.locator('.dx-title')).toHaveText(f.headline);
  await expect(row.locator('.dx-kick')).toContainText(f.label);
  for(const k of f.kpis)await expect(row.locator('.dx-kpis')).toContainText(k.value);
  await expect(row.locator('.dx-meta')).toContainText(`Datos a ${f.period_label} · ${f.source}`);
  // Monthly families read 'ago 2026'; quarterly ones (F12/F13, period_kind quarter) read 'jul–sep 2026'.
  expect(f.period_label).toMatch(/^((ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)–)?(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic) 20\d\d$/);
  await expect(row.locator('.dx-st')).toHaveText(f.status==='updating'?'Actualizándose':'Vigente');
  expect(await row.getAttribute('href')).toBe(`index.html?abrir=1&desde=datos#sig-${f.piece_id}`);
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
 await expect(page.locator('#datosList .dx-row')).toHaveCount(d.families.length);
 await page.locator('#datosView [data-view="grupo"]').click();
 await expect(page.locator('#datosList .dx-sec').first()).toBeVisible();
});

test('Datos: Nuevo clears after opening the ficha, and a read in Chile clears it too',async({page})=>{
 const d=await datos(page),fams=live(d);expect(fams.length).toBeGreaterThan(0);
 await page.goto('/datos.html');
 for(const f of fams)await expect(page.locator(`a.dx-row[data-family="${f.family}"] .dx-badge`)).toHaveText('Nuevo');
 const first=fams[0];
 await page.locator(`a.dx-row[data-family="${first.family}"]`).click();
 await expect(page.locator('#signalDetail')).toBeVisible();
 await expect(page.locator('#detailBody')).toContainText(first.headline);
 await page.locator('#closeDetail').click();
 await expect(page).toHaveURL(/datos\.html$/);
 await expect(page.locator(`a.dx-row[data-family="${first.family}"]`)).toBeVisible();
 await expect(page.locator(`a.dx-row[data-family="${first.family}"] .dx-badge`)).toHaveCount(0);
 // Same piece id and IndexedDB store as the inbox: a read recorded in Chile shows in Datos.
 if(fams.length>1){
  const other=fams[1];
  await page.goto('/');await page.evaluate(id=>AlicantoRead.set(id,true),other.piece_id);
  await page.goto('/datos.html');
  await expect(page.locator(`a.dx-row[data-family="${other.family}"]`)).toBeVisible();
  await expect(page.locator(`a.dx-row[data-family="${other.family}"] .dx-badge`)).toHaveCount(0);
 }
});

test('Datos fits 320 px in both views and the nav links Datos on every page',async({page})=>{
 await page.setViewportSize({width:320,height:700});
 await page.goto('/datos.html');await expect(page.locator('#datosList .dx-row').first()).toBeVisible();
 expect(await noHScroll(page)).toBeTruthy();
 await page.locator('#datosView [data-view="grupo"]').click();await expect(page.locator('#datosList .dx-sec').first()).toBeVisible();
 expect(await noHScroll(page)).toBeTruthy();
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
 const page=await ctx.newPage();await page.clock.setFixedTime(new Date('2026-11-03T12:00:00-03:00'));
 fs.mkdirSync(SHOTS,{recursive:true});
 await page.goto('/datos.html');await expect(page.locator('#datosList .dx-row').first()).toBeVisible();
 await page.screenshot({path:path.join(SHOTS,'datos_recientes.png'),fullPage:true});
 await page.locator('#datosView [data-view="grupo"]').click();await expect(page.locator('#datosList .dx-sec').first()).toBeVisible();
 await page.screenshot({path:path.join(SHOTS,'datos_grupo.png'),fullPage:true});
 await ctx.close();
});
