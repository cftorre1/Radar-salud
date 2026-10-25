const {test,expect,selectPeriod}=require('./fixtures.cjs');
const fs=require('node:fs');
const cases=JSON.parse(fs.readFileSync('tests/fixtures/product_editorial_v3_cases.json','utf8')).items;
const portfolio=JSON.parse(fs.readFileSync('tests/fixtures/product_statistics_v3.json','utf8')).statistical_view;
async function data(page,signals){await page.clock.install({time:new Date('2026-10-12T15:00:00Z')});await page.route('**/data/free_value.json',r=>r.fulfill({json:{}}));await page.route('**/data/radar_today.json',r=>r.fulfill({json:{generated_at:'2026-10-12T15:00:00Z',signals}}));}
for(const x of cases)test(`incremental editorial candidate ${x.id} retains facts and primary references`,async({page})=>{
 const candidate=x.candidate;expect(candidate.review.verdict).toBe('PASS');
 // Test-only preview of reviewed candidates, not mutation/publication of live data.
 await data(page,[{...candidate,depth_gate:{ok:true}}]);await page.goto('/');await selectPeriod(page,'90');
 const card=page.locator('[data-card]');await expect(card).toHaveCount(1);await card.locator('.title-open').click();const detail=page.locator('#detailBody');
 await expect(detail).toContainText(candidate.detail_body.split('\n\n')[0]);for(const e of candidate.evidence)await expect(detail.locator(`a[href="${e.url}"]`).first()).toHaveCount(1);
 await expect(detail).not.toContainText(/Qué pasó:|Por qué importa:|Qué encontró:|Lectura estratégica/);
 if(x.id==='resolucion_if10670'){await expect(detail).toContainText('una vez concluido octubre');await expect(detail).toContainText('no afirma pendencia actual');await detail.getByText('Peticiones recogidas por la resolución',{exact:true}).click();await expect(detail).toContainText('sin argumentos de fondo individualizados');}
 if(x.id==='circular_if534')await expect(detail).toContainText('1 de diciembre de 2026');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();await page.screenshot({path:`artifacts/${x.id}-${test.info().project.name}.png`});
});
test('adaptive portfolio presents comparable entity groups, meaningful precise deltas and accessible series',async({page})=>{
 const signal={title:'Beneficiarios de isapres disminuyen en cada mes de febrero a julio de 2026',event_date:'2026-09-07',source_name:'Superintendencia de Salud',source_url:'https://www.superdesalud.gob.cl/biblioteca-digital/cartera/',signal_types:['Datos'],scopes:['Isapres'],what_happened:'Cartera verificada',why_it_matters:'Comparación de stocks provisionales con bases homogéneas.',statistical_view:portfolio};
 await data(page,[signal]);await page.goto('/');await selectPeriod(page,'90');await page.locator('[data-detail]').first().click();const body=page.locator('#detailBody');
 await expect(body.locator('.stat-kpi').first()).toContainText('2.487.497');await expect(body.locator('#entityComparison tbody tr')).toHaveCount(13);await expect(body).toContainText('Total sistema');await expect(body).toContainText('cerradas');await expect(body).toContainText('Isalud');await expect(body.locator('#entityComparison')).toContainText('-0,00436');
 await body.locator('[data-stat-sort="delta"]').click();await expect(body.locator('th[aria-sort]')).toContainText('Cambio personas');await body.getByText('Ver datos del gráfico',{exact:true}).click();await expect(body.locator('.stat-chart tbody tr')).toHaveCount(7);
 await expect(body.locator('.stat-chart svg')).toHaveAttribute('aria-label',/personas/);await expect(body.locator('details.statistical-methodology')).not.toHaveAttribute('open','');
 for(const width of [390,320,195]){await page.setViewportSize({width,height:844});const screen=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,culprits:[...document.querySelectorAll('body *')].filter(e=>{const b=e.getBoundingClientRect();return b.width>0&&b.right>innerWidth+1}).slice(0,8).map(e=>({tag:e.tagName,cls:e.className,right:e.getBoundingClientRect().right}))}));expect(screen.scroll<=screen.width+1,JSON.stringify(screen)).toBeTruthy();expect(await body.locator('#entityComparison').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBeTruthy();}
 await page.setViewportSize(test.info().project.use.viewport);await page.screenshot({path:`artifacts/statistics-v3-${test.info().project.name}.png`});
});
test('held financial comparison has no chart ranking or misleading percentage',async({page})=>{
 const signal={title:'FEFI · cobertura pendiente de aclaración',event_date:'2026-10-10',source_name:'Superintendencia de Salud',source_url:'https://www.superdesalud.gob.cl/',signal_types:['Datos'],scopes:['Isapres'],what_happened:'Publicación financiera oficial',why_it_matters:'Se conserva acceso con límite explícito.',statistical_view:{family:'fefi',publication_status:'HOLD',limitations:['Cobertura Esencial contradictoria; comparación no aprobada.'],source_url:'https://www.superdesalud.gob.cl/app/uploads/2026/07/finan_ifrs_mar_2026_web_v2.xls'}};
 await data(page,[signal]);await page.goto('/');await page.locator('[data-detail]').first().click();const body=page.locator('#detailBody');await expect(body).toContainText('contradictoria');await expect(body.locator('svg,table,.stat-kpi')).toHaveCount(0);await expect(body).not.toContainText(/12.574|12574|%/);
});
