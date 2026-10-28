// Global is ONE inbox (Dirección 28-oct 08:20, punto 2): the daily headlines from web/data/global_feed.json
// (formerly "Al día afuera", fixture routed here) and Alicanto's themes share one list, newest first, like Chile.
const {test,expect,FIXTURE_AS_OF}=require('./fixtures.cjs');
const fs=require('fs');
function day(offset=0){const d=new Date(Date.parse(FIXTURE_AS_OF+'T12:00:00Z')-offset*86400000);return d.toISOString().slice(0,10)}
function feed(enabled=true){return {schema_version:2,enabled,content_use:'metadata_and_link_only',window_days:14,freshness:{status:'fresh',newest_published_at:day()},
 items:[...Array(10)].map((_,i)=>({id:`d${i}`,source:i%2?'fda':'ema',source_label:i%2?'FDA':'EMA',attribution:i%2?'U.S. Food and Drug Administration':'European Medicines Agency',bylines:i===0?['Zoe Z','Al A','Mo M']:[],rights_basis:i===1?{license_label:'CC BY 4.0',license_url:'https://creativecommons.org/licenses/by/4.0/'}:{},
  title:`Headline number ${i} about drug approval and coverage policy`,url:`https://www.ema.europa.eu/en/news/item-${i}`,published_at:day(i*3),first_seen_on:day(i*3),
  tags_es:['Regulación','Medicamentos y farma'],summary_es:'Regulador. Relevante para: Regulación.',priority:80})).concat([
  {id:'old',source:'ema',source_label:'EMA',title:'Too old',url:'https://www.ema.europa.eu/old',published_at:day(95),tags_es:[]},
  {id:'bad',source:'ema',source_label:'EMA',title:'Unsafe link',url:'javascript:alert(1)',published_at:day(),tags_es:[]}])}}
function themesInWindow(){return JSON.parse(fs.readFileSync('web/data/global_themes.json','utf8')).themes.filter(t=>{const d=t.sources.map(s=>s.published_at).sort().at(-1),a=(Date.parse(FIXTURE_AS_OF+'T00:00:00Z')-Date.parse(d+'T00:00:00Z'))/86400000;return a>=0&&a<90})}
test('headlines and themes are one list, newest first, each row with Ver ficha · Fuente original · Compartir',async({page,context})=>{
 await page.route('**/data/global_feed.json',r=>r.fulfill({json:feed()}));await context.route('https://www.ema.europa.eu/**',r=>r.fulfill({body:'ok'}));
 await page.goto('/global.html');await expect(page.locator('#themes article.item').first()).toBeVisible();
 await expect(page.locator('#globalDaily,#globalDailyRows')).toHaveCount(0);await expect(page.locator('body')).not.toContainText('Al día afuera');
 await page.locator('#globalPeriod').selectOption('90');await page.locator('#globalLanes [data-lane="t"]').click();
 const rows=page.locator('#themes article.item');await expect(rows).toHaveCount(themesInWindow().length+10);
 await expect(page.locator('#themes .daily-item')).toHaveCount(10);await expect(page.locator('#themes')).not.toContainText(/Too old|Unsafe link/);
 const dates=await page.evaluate(()=>[...document.querySelectorAll('#themes article.item')].map(r=>entryFor(r.id).date));expect(dates).toEqual([...dates].sort().reverse());
 const acts=await rows.evaluateAll(xs=>xs.map(r=>[...r.querySelectorAll('.row-acts .act')].map(a=>a.textContent.trim())));
 for(const a of acts)expect(a).toEqual(['Ver ficha','Fuente original','Compartir']);
 const d0=page.locator('#daily-d0');await expect(d0).toContainText('Titular · EMA (Zoe Z, Al A y otros)');
 await expect(page.locator('#daily-d1 a.lic')).toHaveAttribute('href','https://creativecommons.org/licenses/by/4.0/');
 const note=page.locator('#globalAttribution');await expect(note).toBeVisible();await expect(note).toContainText('CDC, HHS, el Gobierno de EE. UU.');
 expect(await page.evaluate(()=>{const n=document.getElementById('globalAttribution').getBoundingClientRect().top,last=[...document.querySelectorAll('#themes article.item')].at(-1).getBoundingClientRect().top;return n>last})).toBeTruthy();
 // Headline ficha: only captured data; no description was captured, so no "Qué pasó"; the only links are the source's.
 await d0.locator('.act-open').click();const dlg=page.locator('#globalDetail');await expect(dlg).toBeVisible();
 await expect(page.locator('#globalDetailTitle')).toHaveText('Headline number 0 about drug approval and coverage policy');
 const body=page.locator('#globalDetailBody');await expect(body).not.toContainText(/Qué pasó|Regulador\. Relevante|Por qué importa|Medicamentos y farma/);
 expect(await body.locator('a').evaluateAll(xs=>xs.map(a=>a.getAttribute('href')))).toEqual(['https://www.ema.europa.eu/en/news/item-0']);
 await expect(body).toContainText('Zoe Z, Al A, Mo M');await expect(body).toContainText('European Medicines Agency');
 expect(await page.locator('#globalDetailActs .act').evaluateAll(xs=>xs.map(a=>a.textContent.trim()))).toEqual(['Fuente original','Compartir']);
 await page.keyboard.press('Escape');await expect(d0).toHaveClass(/read/);
 // Opening a headline's source marks it read, as before.
 const d2=page.locator('#daily-d2');await expect(d2).not.toHaveClass(/read/);
 const [popup]=await Promise.all([context.waitForEvent('page'),d2.locator('.act-src').click()]);await popup.close();await expect(d2).toHaveClass(/read/);
 await page.reload();await expect(page.locator('#daily-d0')).toHaveClass(/read/);await expect(page.locator('#daily-d2')).toHaveClass(/read/);
 // Shared link to a headline reopens its ficha.
 await page.goto('/global.html#daily-d3');await expect(page.locator('#globalDetailTitle')).toHaveText(/Headline number 3/);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});
test('without an authorized feed Global lists only the themes and hides the attribution note',async({page})=>{
 await page.route('**/data/global_feed.json',r=>r.fulfill({json:feed(false)}));
 await page.goto('/global.html');await expect(page.locator('#themes .theme').first()).toBeVisible();
 await expect(page.locator('#themes .daily-item')).toHaveCount(0);await expect(page.locator('#globalAttribution')).toBeHidden();
 await page.unroute('**/data/global_feed.json');await page.route('**/data/global_feed.json',r=>r.fulfill({status:404,body:''}));
 await page.reload();await expect(page.locator('#themes .theme').first()).toBeVisible();await expect(page.locator('#themes .daily-item')).toHaveCount(0);await expect(page.locator('#globalAttribution')).toBeHidden();
});
