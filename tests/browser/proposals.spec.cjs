// Live preview of the three row/ficha proposals (Dirección 28-oct, puntos 2 y 9). ?propuesta=a|b|c switches the
// variant on Chile and Global and is remembered on the device; without it the current UI is unchanged.
const {test,expect}=require('./fixtures.cjs');

const PAGES={chile:{path:'/',rows:'#local article[data-card]',dialog:'#signalDetail',title:'#detailTitle'},global:{path:'/global.html',rows:'#themes article[data-theme]',dialog:'#globalDetail',title:'#globalDetailTitle'}};
async function load(page,name,query=''){
 const p=PAGES[name];
 if(name==='global')await page.addInitScript(()=>{try{const f=JSON.parse(localStorage.getItem('alicanto_global_filters')||'{}');if(!f.period){f.period='all';localStorage.setItem('alicanto_global_filters',JSON.stringify(f))}}catch{}});
 await page.goto(p.path+query);await expect(page.locator(p.rows).first()).toBeVisible();return p;
}
async function noOverflow(page){return page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)}
// Opens the first row's ficha the way each variant intends: A taps the row, B "Ver ficha ›", C expands then "Ver ficha completa ›".
async function openFicha(page,opt,row){
 if(opt==='a'){const box=await row.boundingBox();await row.click({position:{x:box.width-16,y:Math.min(box.height-6,18)}})}
 else if(opt==='b')await row.locator('[data-b-open]').click();
 else{await row.locator('.title-open').click();await expect(row).toHaveClass(/c-open/);await expect(row.locator('.c-panel')).toBeVisible();await row.locator('[data-c-open]').click()}
}

for(const opt of ['a','b','c'])for(const name of ['chile','global']){
 test(`propuesta ${opt.toUpperCase()} on ${name}: rows, ficha, actions and no overflow`,async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const p=await load(page,name,`?propuesta=${opt}`);
  await expect(page.locator('body')).toHaveClass(new RegExp(`prop-${opt}`));
  await expect(page.locator('.prop-switch')).toBeVisible();
  await expect(page.locator(`.prop-switch [data-prop="${opt}"]`)).toHaveAttribute('aria-current','true');
  expect(await page.evaluate(()=>localStorage.getItem('alicanto_propuesta'))).toBe(opt);
  const row=page.locator(p.rows).first();await expect(row).toHaveAttribute('data-prop',opt);
  await expect(row.locator('.item-actions')).toBeHidden();
  if(opt==='a')await expect(row.locator('.a-chev')).toHaveCount(1);
  if(opt==='b'){await expect(row.locator('[data-b-open]')).toHaveText(/Ver ficha/);await expect(row.locator('[data-b-share]')).toBeVisible()}
  if(opt==='c'){await expect(row.locator('.c-toggle')).toHaveAttribute('aria-expanded','false');await expect(row.locator('.c-panel')).toBeHidden()}
  if(name==='global'){
   if(opt==='a')expect(await page.locator('.global-intro h1').evaluate(h=>getComputedStyle(h,'::after').content)).toContain('Premium');
   if(opt==='b')await expect(page.locator('.b-band')).toContainText('Global Premium');
   if(opt==='c')expect(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor)).toBe('rgb(247, 241, 227)');
  }
  await openFicha(page,opt,row);
  await expect(page.locator(p.dialog)).toBeVisible();await expect(page.locator(p.title)).toBeVisible();
  if(opt!=='c'){
   const g=page.locator(`${p.dialog} .prop-ficha-actions`);await expect(g).toHaveCount(1);
   const labels=(await g.locator('.act span').allTextContents());
   expect(labels.at(-1)).toBe('Compartir');if(labels.includes('Fuente original'))expect(labels[0]).toBe('Fuente original');
   if(labels.includes('Análisis'))expect(labels.indexOf('Análisis')).toBe(labels.length-2);
   await expect(page.locator(`${p.dialog} .detail-bar .iconbtn`).first()).toBeHidden();
  }
  // Rows stay inside a 320 px screen, collapsed and (C) expanded; the open ficha too.
  await page.setViewportSize({width:320,height:700});expect(await noOverflow(page)).toBe(true);
  await page.keyboard.press('Escape');await expect(page.locator(p.dialog)).toBeHidden();
  if(opt==='c'){const open=page.locator(`${p.rows}.c-open`);if(await open.count()===0)await page.locator(p.rows).first().locator('.c-toggle').click()}
  expect(await noOverflow(page)).toBe(true);
  expect(errors).toEqual([]);
 });
}

// WATCH (restored 28-oct) keeps working from the ficha in every variant.
for(const opt of ['a','b','c'])test(`propuesta ${opt.toUpperCase()}: "Seguir" in the ficha follows the entity`,async({page})=>{
 await load(page,'chile',`?propuesta=${opt}`);
 const chip=page.locator('#local [data-entity-chip]').first();await expect(chip).toBeVisible();
 const id=await chip.getAttribute('data-entity-chip');const row=chip.locator('xpath=ancestor::article');
 await openFicha(page,opt,row);await expect(page.locator('#signalDetail')).toBeVisible();
 const toggle=page.locator(`#detailBody [data-follow="${id}"]`);await expect(toggle).toHaveAttribute('aria-pressed','false');
 await toggle.click();await expect(page.locator(`#detailBody [data-follow="${id}"]`)).toHaveAttribute('aria-pressed','true');
 await expect(page.locator(`#detailBody [data-follow="${id}"]`)).toContainText('Siguiendo');
});

test('the pill switches variants on Chile and Global, persists without the param and × restores the current UI',async({page})=>{
 await load(page,'chile','?propuesta=a');
 await page.locator('.prop-switch [data-prop="b"]').click();
 await expect(page.locator('body')).toHaveClass(/prop-b/);await expect(page).toHaveURL(/propuesta=b/);
 await expect(page.locator('#local article[data-card] [data-b-open]').first()).toBeVisible();
 await load(page,'global');
 await expect(page.locator('body')).toHaveClass(/prop-b/);await expect(page.locator('.prop-switch [data-prop="b"]')).toHaveAttribute('aria-current','true');
 await page.locator('.prop-switch [data-prop="c"]').click();
 await expect(page.locator('body')).toHaveClass(/prop-c/);await expect(page.locator('#themes article[data-theme] .c-toggle').first()).toBeVisible();
 await page.locator('.prop-switch .prop-off').click();
 await expect(page.locator('#themes article[data-theme]').first()).toBeVisible();
 await expect(page.locator('.prop-switch')).toHaveCount(0);
 expect(await page.evaluate(()=>[...document.body.classList].filter(c=>c.startsWith('prop-')))).toEqual([]);
 expect(await page.evaluate(()=>localStorage.getItem('alicanto_propuesta'))).toBeNull();
});

for(const name of ['chile','global'])test(`no param, nothing stored: ${name} is the current UI`,async({page})=>{
 const p=await load(page,name);
 await expect(page.locator('.prop-switch')).toHaveCount(0);
 expect(await page.evaluate(()=>[...document.body.classList].filter(c=>c.startsWith('prop-')))).toEqual([]);
 await expect(page.locator('[data-prop],.a-chev,.b-actions,.c-toggle,.c-panel,.b-band,.prop-ficha-actions')).toHaveCount(0);
 await expect(page.locator(`${p.rows} .item-actions`).first()).toBeVisible();
 await page.locator(p.rows).first().locator('.title-open').click();
 await expect(page.locator(p.dialog)).toBeVisible();await expect(page.locator(`${p.dialog} .prop-ficha-actions`)).toHaveCount(0);
 await expect(page.locator(`${p.dialog} .detail-bar [data-share]`)).toBeVisible();
});
