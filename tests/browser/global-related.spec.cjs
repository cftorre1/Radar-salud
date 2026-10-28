// Global feed schema 2 (28-oct) in the opción B inbox: a headline ficha shows the publisher's own description
// verbatim ("…" when the feed cut it), lists also_reported_by with related_sources (https only, escaped), and OGL v3.0
// items carry the licence's attribution statement in the ficha and the footer. Missing data hides its section.
const {test,expect,FIXTURE_AS_OF}=require('./fixtures.cjs');
function day(offset=0){const d=new Date(Date.parse(FIXTURE_AS_OF+'T12:00:00Z')-offset*86400000);return d.toISOString().slice(0,10)}
const OGL='https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/';
const ogl={basis:'uk_open_government_licence_v3',license_label:'OGL v3.0',license_url:OGL,attribution:'Contains public sector information licensed under the Open Government Licence v3.0 (MHRA, GOV.UK), with link'};
function feed(items){return {schema_version:2,enabled:true,content_use:'metadata_and_link_only',window_days:90,retention_days:90,freshness:{status:'fresh',newest_published_at:day()},duplicates:[],duplicates_merged:1,items}}
const mhra={id:'mhra1',source:'uk_mhra',source_label:'MHRA (Reino Unido)',attribution:'Medicines and Healthcare products Regulatory Agency',bylines:[],rights_basis:ogl,
 title:'MHRA approves a new treatment for children',url:'https://www.gov.uk/government/news/mhra-approves',published_at:day(1),first_seen_on:day(1),
 description:'Children <5 years and adults >65 are at risk. The approval covers the first indication',description_truncated:true,description_source:'publisher_summary',
 also_reported_by:[{source:'uk_dhsc',source_label:'DHSC <i>(Reino Unido)</i>',url:'https://www.gov.uk/government/news/dhsc-copy'},{source:'bad',source_label:'Insegura',url:'http://example.org/x'},{source:'js',source_label:'JS',url:'javascript:alert(1)'}],
 related_sources:[{title:'Ficha técnica',source_label:'MHRA',url:'https://www.gov.uk/drug-safety-update/x',published_at:day(2)},{title:'Sin URL'}],tags_es:[],priority:80};
const fda={id:'fda1',source:'fda_drugs',source_label:'FDA',attribution:'U.S. Food and Drug Administration',bylines:[],rights_basis:{basis:'us_federal_public_domain',license_label:'Dominio público (EE. UU.)'},
 title:'FDA approves a generic',url:'https://www.fda.gov/news-events/x',published_at:day(2),first_seen_on:day(2),description:null,description_truncated:false,description_source:null,also_reported_by:[],tags_es:[],priority:70};
test('schema 2 ficha: verbatim description with "…", related sources from also_reported_by, OGL attribution',async({page})=>{
 await page.route('**/data/global_feed.json',r=>r.fulfill({json:feed([mhra,fda])}));
 await page.goto('/global.html');const row=page.locator('#daily-mhra1');await expect(row).toBeVisible();
 expect(await row.locator('.row-acts .act').evaluateAll(xs=>xs.map(a=>a.textContent.trim()))).toEqual(['Ver ficha','Fuente original','Compartir']);
 const note=page.locator('#globalAttribution');await expect(note).toContainText('Contains public sector information licensed under the Open Government Licence v3.0.');
 await expect(note.locator('#globalFeedOgl a')).toHaveAttribute('href',OGL);
 await row.locator('.act-open').click();const body=page.locator('#globalDetailBody');await expect(page.locator('#globalDetail')).toBeVisible();
 await expect(body.locator('.ficha-h')).toHaveText(['Qué pasó','Fuentes']);
 // Plain text from _clean is escaped once: "<5" and ">65" are shown as written, nothing lost.
 await expect(body.locator('h3.ficha-h + p')).toHaveText('Children <5 years and adults >65 are at risk. The approval covers the first indication …');
 await expect(body.locator('.ficha-sources a.lic')).toHaveAttribute('href',OGL);const links=await body.locator('.ficha-sources .source > a').evaluateAll(xs=>xs.map(a=>[a.getAttribute('href'),a.textContent.trim()]));
 expect(links).toEqual([['https://www.gov.uk/government/news/mhra-approves','MHRA (Reino Unido) · MHRA approves a new treatment for children ↗'],['https://www.gov.uk/drug-safety-update/x','MHRA · Ficha técnica ↗'],['https://www.gov.uk/government/news/dhsc-copy','DHSC <i>(Reino Unido)</i> ↗']]);
 await expect(body.locator('i')).toHaveCount(0);await expect(body).not.toContainText(/Insegura|Sin URL|JS ↗/);
 const attr=body.locator('.ficha-attr');await expect(attr).toHaveText('Contains public sector information licensed under the Open Government Licence v3.0.');await expect(attr.locator('a')).toHaveAttribute('href',OGL);
 await page.keyboard.press('Escape');
 // description null: title and meta only, no "Qué pasó", no OGL statement, only the source's own link.
 await page.locator('#daily-fda1 .act-open').click();await expect(page.locator('#globalDetailTitle')).toHaveText('FDA approves a generic');
 await expect(body.locator('.ficha-h')).toHaveText(['Fuentes']);await expect(body).not.toContainText(/Qué pasó|Open Government Licence/);
 expect(await body.locator('a').evaluateAll(xs=>xs.map(a=>a.getAttribute('href')))).toEqual(['https://www.fda.gov/news-events/x']);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});
test('without OGL items the footer carries no OGL statement; an unknown schema is not read',async({page})=>{
 await page.route('**/data/global_feed.json',r=>r.fulfill({json:feed([fda])}));
 await page.goto('/global.html');await expect(page.locator('#daily-fda1')).toBeVisible();
 await expect(page.locator('#globalAttribution')).toBeVisible();await expect(page.locator('#globalAttribution')).not.toContainText('Open Government Licence');
 await page.unroute('**/data/global_feed.json');await page.route('**/data/global_feed.json',r=>r.fulfill({json:{...feed([fda]),schema_version:3}}));
 await page.reload();await expect(page.locator('#themes .theme').first()).toBeVisible();await expect(page.locator('#themes .daily-item')).toHaveCount(0);await expect(page.locator('#globalAttribution')).toBeHidden();
});
