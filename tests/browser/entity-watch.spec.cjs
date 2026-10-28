// WATCH · seguimiento por entidad (Dirección 27-oct-2026): entities are followed from the existing
// Intereses sheet (and filtered from card chips); the feed keeps its first-viewport share.
const {test,expect}=require('./fixtures.cjs');

async function visibleRefs(page){
 return page.evaluate(()=>[...document.querySelectorAll('#local article[data-card]')].map(row=>{const s=allSignals.find(x=>idFor(x)===row.dataset.card);return refIds(s)}));
}
// design/home/design.md §1: union of feed card rects inside the first viewport / viewport height.
async function feedShare(page){
 return page.evaluate(()=>{const H=innerHeight;const iv=[...document.querySelectorAll('#local article.signal')].map(e=>e.getBoundingClientRect()).map(r=>[Math.max(0,r.top),Math.min(H,r.bottom)]).filter(([a,b])=>b>a).sort((x,y)=>x[0]-y[0]);let total=0,cur=null;for(const [a,b] of iv){if(!cur||a>cur[1]){if(cur)total+=cur[1]-cur[0];cur=[a,b]}else cur[1]=Math.max(cur[1],b)}if(cur)total+=cur[1]-cur[0];return total/H});
}

test('follow an entity from the Intereses sheet, persist it and unfollow from a card chip',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.locator('#local article[data-card]').first()).toBeVisible();
 const id='cl:org:uc-christus';
 await page.locator('#filterDetails summary').click();
 const search=page.locator('#entitySearch');await expect(search).toBeVisible();
 await search.fill('christus');
 const toggle=page.locator(`#entityList [data-entity="${id}"]`);await expect(toggle).toBeVisible();
 await expect(toggle).toHaveAttribute('aria-pressed','false');
 await toggle.click();
 await expect(page.locator(`#entityList [data-entity="${id}"]`)).toHaveAttribute('aria-pressed','true');
 await expect(page.locator(`#entityList [data-entity="${id}"]`)).toBeFocused();
 // Bar A (Dirección 27-oct 23:13): the filters dropdown names its selection instead of a dot.
 await expect(page.locator('#filterLabel')).not.toHaveText('Todos los temas');
 expect(JSON.parse(await page.evaluate(()=>localStorage.getItem('alicanto_filters'))).entities).toEqual([id]);
 await page.locator('#filterDone').click();
 const refs=await visibleRefs(page);expect(refs.length).toBeGreaterThan(0);
 for(const r of refs)expect(r).toContain(id);
 // Survives a reload through the same persisted filter model.
 await page.reload();await expect(page.locator('#local article[data-card]').first()).toBeVisible();
 // Bar A has no chips row on phones: the followed entity is named by the filters dropdown (rail on desktop).
 if(test.info().project.name==='mobile')await expect(page.locator('#filterLabel')).not.toHaveText('Todos los temas');
 else await expect(page.locator(`#interestRail [data-entity="${id}"]`)).toHaveAttribute('aria-pressed','true');
 for(const r of await visibleRefs(page))expect(r).toContain(id);
 // The card chip is the same toggle: clicking it unfollows and restores the full inbox.
 const chip=page.locator(`#local [data-entity-chip="${id}"]`).first();await expect(chip).toHaveAttribute('aria-pressed','true');
 await chip.click();
 await expect(page.locator(`#local [data-entity-chip="${id}"]`).first()).toHaveAttribute('aria-pressed','false');
 expect(JSON.parse(await page.evaluate(()=>localStorage.getItem('alicanto_filters'))).entities).toEqual([]);
 expect((await visibleRefs(page)).some(r=>!r.includes(id))).toBe(true);
 expect(errors).toEqual([]);
});

test('a card entity chip filters the inbox to that entity',async({page})=>{
 await page.goto('/');const chip=page.locator('#local [data-entity-chip]').first();await expect(chip).toBeVisible();
 const box=await chip.boundingBox();expect(box.height).toBeGreaterThanOrEqual(24);
 const id=await chip.getAttribute('data-entity-chip');await chip.click();
 const refs=await visibleRefs(page);expect(refs.length).toBeGreaterThan(0);for(const r of refs)expect(r).toContain(id);
 await expect(page.locator('#local [data-entity-chip][aria-pressed="true"]').first()).toBeVisible();
});

test('entity chips keep the feed share of the first viewport',async({page})=>{
 await page.goto('/');await page.waitForLoadState('networkidle');await expect(page.locator('#local article[data-card]').first()).toBeVisible();
 await expect(page.locator('#local [data-entity-chip]').first()).toBeVisible();
 const share=await feedShare(page),min=test.info().project.name==='mobile'?0.55:0.60;
 expect(share).toBeGreaterThanOrEqual(min);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(test.info().project.use.viewport.width+1);
});

// Review of PR #75: chips name the action, keep a ~44px invisible touch area that never covers
// the title, and travel with the row icons so these never drop to a line of their own.
test('entity chips expose the follow action, a 44px touch area below the title and inline icons',async({page})=>{
 await page.goto('/');const chip=page.locator('#local [data-entity-chip]').first();await expect(chip).toBeVisible();
 await expect(chip).toHaveAttribute('aria-label',/^Seguir \S/);
 const g=await chip.evaluate(el=>{const r=el.getBoundingClientRect(),row=el.closest('article'),t=row.querySelector('.title-open').getBoundingClientRect(),x=r.left+Math.min(12,r.width/2);let top=r.top,bottom=r.bottom;while(document.elementFromPoint(x,top-1)?.closest('[data-entity-chip]')===el)top--;while(document.elementFromPoint(x,bottom+1)?.closest('[data-entity-chip]')===el)bottom++;const icons=[...row.querySelectorAll('.item-actions .iconbtn,.item-actions .sharebtn')].map(i=>{const b=i.getBoundingClientRect();return b.top+b.height/2});return{hit:bottom-top,top,titleBottom:t.bottom,mid:r.top+r.height/2,icons}});
 expect(g.hit).toBeGreaterThanOrEqual(42);
 expect(g.top).toBeGreaterThanOrEqual(g.titleBottom-0.5);
 expect(g.icons.length).toBeGreaterThan(0);for(const y of g.icons)expect(Math.abs(y-g.mid)).toBeLessThan(12);
 await chip.click();await expect(page.locator(`#local [data-entity-chip="${await chip.getAttribute('data-entity-chip')}"]`).first()).toHaveAttribute('aria-label',/^Dejar de seguir \S/);
});
