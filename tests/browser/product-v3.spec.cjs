const {test,expect}=require('./fixtures.cjs');
const fs=require('node:fs');
const snapshot=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8'));
const fixture=snapshot.signals.find(s=>s.source_url.includes('circular-if-n534'));
async function prepare(page){await page.clock.install({time:new Date('2026-10-12T15:00:00Z')});await page.route('**/data/radar_today.json',r=>r.fulfill({json:{...snapshot,signals:[fixture]}}));}
test('row title opens the record without a Más info button; opening reads, the dot toggles, state survives reload',async({page})=>{
 await prepare(page);await page.goto('/');const card=page.locator('[data-card]');await expect(card).toHaveCount(1);const id=await card.getAttribute('data-card');
 await expect(page.getByRole('button',{name:'Más info',exact:true})).toHaveCount(0);
 await card.locator('.title-open').click();await expect(page.locator('#signalDetail')).toBeVisible();const body=await page.locator('#detailBody').textContent();await expect(card).toHaveClass(/read/);
 await expect(page.locator('#detailRead')).toHaveText('Marcar no leída');await page.keyboard.press('Escape');
 await expect(card).toHaveCount(0);await expect(page.locator('#undoBar')).toContainText('Marcada como leída');
 await page.locator('[data-lane="t"]').click();await expect(card).toHaveClass(/read/);
 await card.locator('.title-open').click();await expect(page.locator('#detailBody')).toHaveText(body);await page.keyboard.press('Escape');
 // Read rows carry no mark; the record's text control marks them unread again.
 await expect(card.locator('[data-read]')).toHaveCount(0);await card.locator('.title-open').click();await page.locator('#detailRead').click();await expect(page.locator('#detailRead')).toHaveText('Marcar leída');await page.keyboard.press('Escape');await expect(card).not.toHaveClass(/read/);await expect(card.locator('[data-read]')).toHaveAttribute('aria-label',/^Marcar como leído/);
 await page.reload();await expect(card).not.toHaveClass(/read/);await expect(page.locator('.lane.on')).toContainText('Todas');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.screenshot({path:`artifacts/product-v3-${test.info().project.name}.png`,fullPage:true});
});
test('distinct concurrent writes and tombstones synchronize without lost updates',async({context,page})=>{
 await prepare(page);await page.goto('/');await page.evaluate(()=>AlicantoRead.ready);const second=await context.newPage();await prepare(second);await second.goto('/');await second.evaluate(()=>AlicantoRead.ready);
 await Promise.all([page.evaluate(()=>AlicantoRead.set('test:a',true)),second.evaluate(()=>AlicantoRead.set('test:b',true))]);
 for(const p of [page,second])await expect.poll(()=>p.evaluate(()=>['test:a','test:b'].every(id=>AlicantoRead.readSet.has(id)))).toBeTruthy();
 await page.evaluate(()=>AlicantoRead.set('test:a',false));await expect.poll(()=>second.evaluate(()=>AlicantoRead.readSet.has('test:a'))).toBeFalsy();await second.reload();await expect.poll(()=>second.evaluate(()=>AlicantoRead.readSet.has('test:b'))).toBeTruthy();await expect.poll(()=>second.evaluate(()=>AlicantoRead.readSet.has('test:a'))).toBeFalsy();
 await second.evaluate(()=>AlicantoRead.set('test:a',true));await page.evaluate(()=>AlicantoRead.set('test:a',false));await page.reload();await expect.poll(()=>page.evaluate(()=>AlicantoRead.readSet.has('test:a'))).toBeFalsy();
});
test('two first opens migrate legacy once and preserve unread over stale legacy',async({context,page})=>{
 await prepare(page);await page.addInitScript(()=>localStorage.setItem('alicanto_read',JSON.stringify(['legacy:kept','global:old'])));const second=await context.newPage();await prepare(second);await Promise.all([page.goto('/'),second.goto('/')]);await Promise.all([page.evaluate(()=>AlicantoRead.ready),second.evaluate(()=>AlicantoRead.ready)]);
 await expect.poll(()=>page.evaluate(()=>AlicantoRead.readSet.has('legacy:kept'))).toBeTruthy();await second.evaluate(()=>AlicantoRead.set('legacy:kept',false));await page.reload();await expect.poll(()=>page.evaluate(()=>AlicantoRead.readSet.has('legacy:kept'))).toBeFalsy();await expect.poll(()=>page.evaluate(()=>AlicantoRead.readSet.has('global:old'))).toBeTruthy();
});
test('corrected ID preserves explicit unread over stale imported title alias',async({page})=>{
 await prepare(page);await page.addInitScript(()=>localStorage.setItem('alicanto_read',JSON.stringify(['legacy:title','stable:old'])));await page.goto('/');await page.evaluate(()=>AlicantoRead.ready);
 await page.evaluate(async()=>{await AlicantoRead.set('stable:old',false);await AlicantoRead.migrate('date-correction',[['stable:new',['legacy:title','stable:old'],'legacy_alias']]);});
 expect(await page.evaluate(()=>AlicantoRead.readSet.has('stable:new'))).toBeFalsy();await page.reload();expect(await page.evaluate(async()=>{await AlicantoRead.ready;return AlicantoRead.readSet.has('stable:new')})).toBeFalsy();
});
test('Global Home teaser and Global canonical detail share read state',async({context,page})=>{
 await prepare(page);const data=JSON.parse(fs.readFileSync('web/data/global_themes.json','utf8'));const t=data.themes[0];await page.route('**/data/free_value.json',r=>r.fulfill({json:{global_teaser:{theme_id:t.id,title:t.title,published_at:'2026-10-12',premium_href:`global.html#theme-${t.id}`}}}));await page.goto('/');const other=await context.newPage();await prepare(other);await other.goto('/global.html');await other.locator('#globalPeriod').selectOption('all');
 await other.locator(`[data-open="${t.id}"]`).first().click();await expect(other.locator('#globalDetail')).toBeVisible();await expect(page.locator(`#bigThings [data-special="global:${t.id}"]`)).toHaveClass(/read/);/* Dirección 27-oct-2026: read specials keep their row in 'Esta semana' instead of moving to Leídas. */await page.locator('[data-lane="l"]').click();await expect(page.locator(`#local [data-special="global:${t.id}"]`)).toHaveCount(0);await other.keyboard.press('Escape');await other.locator(`[data-read="${t.id}"]`).click();await expect(page.locator(`#bigThings [data-special="global:${t.id}"]`)).toHaveCount(1);await expect(page.locator(`#bigThings [data-special="global:${t.id}"]`)).not.toHaveClass(/read/);await expect(page.locator(`#local [data-special="global:${t.id}"]`)).toHaveCount(0);
});
test('catalog excludes blocked paused and unverified; filter plus is adjacent and floating action outside cards',async({page})=>{
 await page.route('**/data/public_sources.json',r=>r.fulfill({json:{sources:[{id:'minsal',name:'Activa',group:'Organismos públicos',url:'https://www.minsal.cl/',description:'Noticias'}]}}));await page.goto('/sources.html');await expect(page.locator('#catalog')).toContainText('Activa');await expect(page.locator('#catalog')).not.toContainText(/Bloqueada|Pausada|Desconocida/);
 const links=await page.locator('.sources-page .topnav a').evaluateAll(xs=>xs.map(x=>{const r=x.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,height:r.height}}));
 expect(links).toHaveLength(3);for(let i=0;i<links.length;i++){expect(links[i].height).toBeGreaterThanOrEqual(44);if(i)expect(links[i].top>=links[i-1].bottom||links[i].left-links[i-1].right>=12).toBeTruthy();}
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();await page.screenshot({path:`artifacts/sources-navigation-${test.info().project.name}.png`});
 await prepare(page);await page.goto('/');const summary=page.locator('#filterDetails>summary');expect(await summary.evaluate(el=>getComputedStyle(el).justifyContent)).toBe('flex-start');await expect(page.locator('article #backTop')).toHaveCount(0);expect(await page.locator('#backTop').evaluate(el=>getComputedStyle(el).position)).toBe('fixed');
 await expect(page.locator('#backTop')).toBeHidden();await page.emulateMedia({reducedMotion:'reduce'});
 // One fixture card is shorter than the viewport; extra height lets the test scroll past the controls it checks.
 await page.evaluate(()=>{document.body.style.paddingBottom='2000px'});await page.locator('.radar-head').evaluate(el=>window.scrollTo(0,el.getBoundingClientRect().bottom+window.scrollY+1));await expect(page.locator('#backTop')).toBeVisible();
 await page.evaluate(()=>{window.__scrollBehavior=null;const native=Element.prototype.scrollIntoView;Element.prototype.scrollIntoView=function(options){window.__scrollBehavior=options?.behavior;return native.call(this,options)}});
 await page.locator('#backTop').click();expect(await page.evaluate(()=>window.__scrollBehavior)).toBe('auto');await expect(page.locator('main')).toBeFocused();
});
