// "Al día afuera" (28-oct): daily headline rows on Global from web/data/global_feed.json (fixture routed here).
const {test,expect}=require('@playwright/test');
const fs=require('fs');
function santiagoDay(offset=0){const d=new Date(Date.now()-offset*86400000);return new Intl.DateTimeFormat('en-CA',{timeZone:'America/Santiago',year:'numeric',month:'2-digit',day:'2-digit'}).format(d)}
function feed(enabled=true){return {enabled,content_use:'metadata_and_link_only',window_days:14,freshness:{status:'fresh',newest_published_at:santiagoDay()},
 items:[...Array(10)].map((_,i)=>({id:`d${i}`,source:i%2?'fda':'ema',source_label:i%2?'FDA':'EMA',attribution:'x',bylines:i===0?['Ana Researcher']:[],
  title:`Headline number ${i} about drug approval and coverage policy`,url:`https://www.ema.europa.eu/en/news/item-${i}`,published_at:santiagoDay(i),
  tags_es:['Regulación','Medicamentos y farma'],summary_es:'Regulador. Relevante para: Regulación.',priority:80})).concat([
  {id:'old',source:'ema',source_label:'EMA',title:'Too old',url:'https://www.ema.europa.eu/old',published_at:santiagoDay(20),tags_es:[]},
  {id:'bad',source:'ema',source_label:'EMA',title:'Unsafe link',url:'javascript:alert(1)',published_at:santiagoDay(),tags_es:[]}])}}
test('Global shows daily headline rows with read state, without touching the theme inbox',async({page})=>{
 await page.route('**/data/global_feed.json',r=>r.fulfill({json:feed()}));
 const themes=JSON.parse(fs.readFileSync('web/data/global_themes.json','utf8')).themes.length;
 await page.goto('/global.html');
 const section=page.locator('#globalDaily');await expect(section).toBeVisible();
 const rows=section.locator('.daily-item');await expect(rows).toHaveCount(8);
 await expect(page.locator('#globalDailyMetrics')).toHaveText(/^10 titulares en 14 días · no leídos 10/);
 await expect(rows.first()).toContainText('Titular · EMA (Ana Researcher)');await expect(rows.first()).toContainText('Regulación · Medicamentos y farma');
 await expect(rows.first().locator('a.title-open')).toHaveAttribute('target','_blank');await expect(rows.first().locator('a.title-open')).toHaveAttribute('rel','noopener');
 await expect(section).not.toContainText('Too old');await expect(section).not.toContainText('Unsafe link');
 await page.locator('#globalDailyMore').click();await expect(rows).toHaveCount(10);
 await rows.first().locator('[data-daily-read]').click();await expect(rows.first()).toHaveClass(/read/);
 await expect(page.locator('#globalDailyMetrics')).toHaveText(/no leídos 9/);await expect(rows.first().locator('[data-daily-read]')).toBeFocused();
 await page.reload();await expect(section.locator('#daily-d0')).toHaveClass(/read/);
 await page.locator('#globalPeriod').selectOption('all');await page.locator('#globalLanes [data-lane="t"]').click();
 await expect(page.locator('#themes .theme')).toHaveCount(themes);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.screenshot({path:`artifacts/${test.info().project.name}-global-daily.png`,fullPage:false});
});
test('daily section stays hidden while the feed is not authorized or missing',async({page})=>{
 await page.route('**/data/global_feed.json',r=>r.fulfill({json:feed(false)}));
 await page.goto('/global.html');await expect(page.locator('#themes .theme').first()).toBeVisible();
 await expect(page.locator('#globalDaily')).toBeHidden();
 await page.unroute('**/data/global_feed.json');await page.route('**/data/global_feed.json',r=>r.fulfill({status:404,body:''}));
 await page.reload();await expect(page.locator('#themes .theme').first()).toBeVisible();await expect(page.locator('#globalDaily')).toBeHidden();
});
