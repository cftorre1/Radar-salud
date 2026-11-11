const {test,expect}=require('./fixtures.cjs');

// Weekly insight editorial rules (Dirección, 11-nov-2026), checked on the CURRENT approved essay. The suite clock is
// pinned to ALICANTO_FIXTURE_AS_OF (12-oct), when the current insight is not fresh yet, so this test moves the clock to
// the day after its anchor and opens it directly (data/weekly_insight/POLICY.md «Editorial rules»).
test('weekly insight essay: compact header, text on the first screen, byline, footnotes, no evidence labels',async({page})=>{
 const fv=await (await page.request.get('/data/free_value.json')).json(),w=fv.weekly_insight;
 test.skip(!w||w.schema_version!=='weekly_insight_a_v2','no v2 essay published');
 const anchor=new Date(`${w.freshness_anchor_date||w.event_date}T12:00:00-03:00`);
 await page.clock.setFixedTime(new Date(anchor.getTime()+864e5));
 await page.goto('/index.html');
 await page.waitForFunction(()=>typeof currentWeekly==='function'&&Boolean(currentWeekly()));
 await page.evaluate(()=>{renderWeeklyDetail(currentWeekly());document.getElementById('weeklyInsightDialog').showModal()});
 const d=page.locator('#weeklyInsightDialog');
 await expect(d.locator('.we-kicker')).toHaveText(/^Insight de la semana\d{1,2} [a-z]{3} \d{4}$/i);
 await expect(d.locator('.we-byline')).toHaveText(/^AlicantoLectura de \d+ min\d+ fuentes$/);
 // The lead paragraph starts on the first screen (phone 390×844 and desktop).
 const lead=await d.locator('.we-lead').boundingBox();expect(lead.y+60).toBeLessThan(page.viewportSize().height);
 const text=await d.innerText();
 for(const gone of ['Dato oficial','equipo editorial','Cifras verificadas'])expect(text).not.toContain(gone);
 await expect(d.locator('.we-legend,.we-badge,.we-tag,.we-est')).toHaveCount(0);
 // Estimates: lettered marks in reading order, each jumping to its note in «Notas».
 const marks=await d.locator('.we-n a').allTextContents();
 if(marks.length){expect([...new Set(marks)]).toEqual('abcdefghij'.slice(0,new Set(marks).size).split(''));
  await d.locator('.we-n a').first().click();await expect(d.locator('.we-notes li').first()).toBeFocused()}
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});
