// Entity names on cards (WATCH data, Dirección 27-oct-2026). Since Dirección 28-oct (punto 4) they are information
// only: Actores and Temas are the single filter system, so chips neither filter nor follow; the feed keeps its share.
const {test,expect}=require('./fixtures.cjs');

async function visibleRefs(page){
 return page.evaluate(()=>[...document.querySelectorAll('#local article[data-card]')].map(row=>{const s=allSignals.find(x=>idFor(x)===row.dataset.card);return refIds(s)}));
}
// design/home/design.md §1: union of feed card rects inside the first viewport / viewport height.
async function feedShare(page){
 return page.evaluate(()=>{const H=innerHeight;const iv=[...document.querySelectorAll('#local article.signal')].map(e=>e.getBoundingClientRect()).map(r=>[Math.max(0,r.top),Math.min(H,r.bottom)]).filter(([a,b])=>b>a).sort((x,y)=>x[0]-y[0]);let total=0,cur=null;for(const [a,b] of iv){if(!cur||a>cur[1]){if(cur)total+=cur[1]-cur[0];cur=[a,b]}else cur[1]=Math.max(cur[1],b)}if(cur)total+=cur[1]-cur[0];return total/H});
}

test('filters offer only Actores and Temas; a saved format is dropped but saved follows are kept',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{if(!sessionStorage.getItem('seeded')){localStorage.setItem('alicanto_filters',JSON.stringify({type:'Fiscalización',entities:['cl:org:uc-christus'],interests:[],period:'30',sort:'date',lane:'p'}));sessionStorage.setItem('seeded','1')}});
 await page.goto('/');await expect(page.locator('#local article[data-card]').first()).toBeVisible();
 // Following is not filtering: a saved follow leaves the inbox whole.
 await expect(page.locator('#filterLabel')).toHaveText('Todos los temas');
 await page.locator('#filterDetails summary').click();
 await expect(page.locator('#interestFilters .interest-group')).toHaveText(['Actores','Temas']);
 await expect(page.locator('#interestFilters [data-interest="siguiendo"]')).toBeVisible();
 await expect(page.locator('#entitySearch,#entityList,#typeFilters')).toHaveCount(0);
 await expect(page.locator('#filterDetails')).not.toContainText(/Entidades|Formato/);
 const saved=JSON.parse(await page.evaluate(()=>localStorage.getItem('alicanto_filters')));expect(saved.entities).toEqual(['cl:org:uc-christus']);expect(saved.type).toBeUndefined();
 expect(errors).toEqual([]);
});

// WATCH (Dirección 27-oct, restored 28-oct): follow from the ficha, rows of followed entities are marked,
// Actores › Siguiendo shows them, and the follow survives a reload.
test('follow an entity from the ficha, see the row marker, filter by Siguiendo and keep it after reload',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.locator('#local article[data-card]').first()).toBeVisible();
 // Rows no longer name their actors (Dirección 28-oct 21:49): take the first row whose signal has an entity.
 const {id,card}=await page.evaluate(()=>{for(const r of document.querySelectorAll('#local article[data-card]')){const ids=refIds(allSignals.find(x=>idFor(x)===r.dataset.card));if(ids.length)return {id:ids[0],card:r.dataset.card}}return {}});
 expect(id).toBeTruthy();const row=page.locator(`#local [data-card="${card}"]`);
 await expect(page.locator('#interestFilters [data-interest="siguiendo"]')).toHaveCount(0);
 await row.locator('.title-open').click();await expect(page.locator('#signalDetail')).toBeVisible();
 const toggle=page.locator(`#detailBody [data-follow="${id}"]`);await expect(toggle).toHaveAttribute('aria-pressed','false');await expect(toggle).toContainText('Seguir');
 await toggle.click();await expect(page.locator(`#detailBody [data-follow="${id}"]`)).toHaveAttribute('aria-pressed','true');await expect(page.locator(`#detailBody [data-follow="${id}"]`)).toContainText('Siguiendo');await expect(page.locator(`#detailBody [data-follow="${id}"]`)).toBeFocused();
 await page.keyboard.press('Escape');
 await page.locator('#lanes [data-lane="t"]').click();
 await expect(page.locator(`#local [data-card="${card}"] .follow-mark`)).toBeVisible();
 await expect(page.locator('#filterLabel')).toHaveText('Todos los temas');
 await page.reload();await expect(page.locator(`#local [data-card="${card}"] .follow-mark`)).toBeVisible();
 await page.locator('#filterDetails summary').click();await page.locator('#interestFilters [data-interest="siguiendo"]').click();
 await expect(page.locator('#filterLabel')).toHaveText('Siguiendo');
 const refs=await page.evaluate(()=>[...document.querySelectorAll('#local article[data-card]')].map(r=>refIds(allSignals.find(x=>idFor(x)===r.dataset.card))));
 expect(refs.length).toBeGreaterThan(0);for(const r of refs)expect(r).toContain(id);
 await expect(page.locator('#local article[data-card]:not(:has(.follow-mark))')).toHaveCount(0);
 await page.locator('#interestFilters .tog-all').click();await page.keyboard.press('Escape');
 await page.locator(`#local [data-card="${card}"] .title-open`).click();await page.locator(`#detailBody [data-follow="${id}"]`).click();
 await expect(page.locator(`#detailBody [data-follow="${id}"]`)).toHaveAttribute('aria-pressed','false');await page.keyboard.press('Escape');
 expect(JSON.parse(await page.evaluate(()=>localStorage.getItem('alicanto_filters'))).entities).toEqual([]);
 await expect(page.locator(`#local [data-card="${card}"] .follow-mark`)).toHaveCount(0);
 expect(errors).toEqual([]);
});

// Dirección 28-oct 21:49: rows carry no actor/entity chips; a content-type label (Normativa, Fiscalización, Datos)
// and the follow marker of a followed entity are the only labels left on the meta line.
test('feed rows carry no actor chips, only content-type labels',async({page})=>{
 await page.goto('/');const rows=page.locator('#local article[data-card]');await expect(rows.first()).toBeVisible();
 const withRefs=await page.evaluate(()=>[...document.querySelectorAll('#local article[data-card]')].filter(r=>refIds(allSignals.find(x=>idFor(x)===r.dataset.card)).length).length);
 expect(withRefs).toBeGreaterThan(0);
 await expect(page.locator('#local [data-entity-chip],#local .ent-chips,#local .ent-chip,#local .ent-more')).toHaveCount(0);
 for(const tag of await page.locator('#local article[data-card] .card-meta .tag').allTextContents())expect(tag.trim()).toMatch(/^(Normativa|Fiscalización|Datos|Corregido el .+)$/);
 await expect(page.locator('#local article[data-card] .follow-mark')).toHaveCount(0);
});

test('rows without actor chips keep the feed share of the first viewport',async({page})=>{
 await page.goto('/');await page.waitForLoadState('networkidle');await expect(page.locator('#local article[data-card]').first()).toBeVisible();
 const share=await feedShare(page),min=test.info().project.name==='mobile'?0.55:0.60;
 expect(share).toBeGreaterThanOrEqual(min);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(test.info().project.use.viewport.width+1);
});
