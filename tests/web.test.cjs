const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const source=fs.readFileSync('web/app.js','utf8').split("fetch('data/radar_today.json'")[0];
function context(Clock=Date){const c={AlicantoRead:{readSet:new Set(),ready:Promise.resolve(),migrate:async function(marker,entries){for(const [id,aliases] of entries)if(aliases.some(x=>this.readSet.has(x)))this.readSet.add(id)}},AlicantoStats:{render:()=>'',wire:()=>{}},localStorage:{getItem:()=>null,setItem:()=>{}},btoa:s=>Buffer.from(s,'binary').toString('base64'),atob:s=>Buffer.from(s,'base64').toString('binary'),escape,unescape,decodeURIComponent,encodeURIComponent,Intl,URL,Date:Clock,Set,Map};vm.createContext(c);vm.runInContext(source,c);return c}
test('full card IDs do not collide for long URLs',()=>{const c=context();assert.notEqual(c.idFor({source_url:'https://example.org/'+ 'a'.repeat(160)+'1'}),c.idFor({source_url:'https://example.org/'+ 'a'.repeat(160)+'2'}))});
test('date-only publication keeps calendar date in Chile',()=>{const c=context();assert.match(c.fmtDate('2026-09-23'),/23/)});
test('reviewed v3 public surfaces never substitute unsigned legacy copy',()=>{
 const c=context(),title='Resolución IF/N°1 rechaza reposición',unreviewed='Resolución IF/N°1 acoge reposición y levanta la sanción.';
 const base={editorial_schema_version:'3',piece_id:'synthetic:signed-title',title,detail_body:'No se acreditó daño irreparable.',source_url:'https://example.org/resolution',source_name:'Prueba',event_date:'2026-10-12'};
 for(const legacy of [{card_what:unreviewed},{normative_document_label:'Resolución IF/N°1',normative_subject:unreviewed,card_why:unreviewed},{source_url:'https://www.superdesalud.gob.cl/normativa/circular-if-n534/'}]){
  const row={...base,...legacy};assert.equal(c.triageTitle(row),title);assert.match(c.card(row),/Resolución IF\/N°1 rechaza reposición/);assert.match(c.detailHtml(row),/Resolución IF\/N°1 rechaza reposición/);assert.ok(!c.card(row).includes(unreviewed));assert.ok(!c.detailHtml(row).includes(unreviewed));
 }
 const news={...base,title:'El hospital realizó una intervención con una técnica y un equipo acreditados por la publicación original.',card_what:'La intervención redujo la mortalidad un 80%.',what_happened:unreviewed,why_it_matters:unreviewed};
 assert.equal(c.triageTitle(news),news.title);assert.equal(c.triageSummary(news),'');
 assert.equal(c.triageSummary({...news,brief_deck:'Participaron especialistas del hospital de referencia.'}),'Participaron especialistas del hospital de referencia.');
 assert.equal(c.triageTitle({...news,editorial_schema_version:3,display_title:'Titular firmado de la intervención'}),'Titular firmado de la intervención');
 // Historical v2 keeps its established projection.
 assert.equal(c.triageTitle({...base,editorial_schema_version:'2',card_what:unreviewed}),unreviewed);
});
test('update label is direct and does not overstate source review',()=>{const c=context();assert.match(c.fmtUpdated('2026-09-24T12:00:00Z'),/^Última actualización:/);assert.doesNotMatch(c.fmtUpdated('2026-09-24T12:00:00Z'),/Portada generada|revisión de las fuentes/)});
test('legacy statistical complements require valid matching source hashes and stay outside reviewed v3 copy',()=>{
 const c=context(),hash='a'.repeat(64),view={family:'cartera'},e={text:'Dato complementario',family:'cartera',analysis_kind:'portfolio_mix_shift',sha256:hash,source_url:'https://example.org/book',period:'2026-07',sheet:'Julio',formula:'1/2'};
 const s={title:'Stock verificado',statistical_view:view,data_insight_evidence:[e],data_insight_meta:{status:'validated',sha256:{cartera:hash}}};
 assert.match(c.detailHtml(s),/Dato complementario/);
 for(const bad of [undefined,'bad','b'.repeat(64)]){const x={...s,data_insight_evidence:[{...e,sha256:bad}],data_insight_meta:{status:'validated',sha256:{cartera:bad}}};if(bad==='b'.repeat(64))x.data_insight_meta.sha256.cartera=hash;assert.doesNotMatch(c.detailHtml(x),/Dato complementario/);}
 assert.doesNotMatch(c.detailHtml({...s,editorial_schema_version:'3'}),/Dato complementario/);
 assert.doesNotMatch(c.detailHtml({...s,statistical_view:{...view,publication_status:'HOLD'}}),/Dato complementario/);
 assert.doesNotMatch(c.detailHtml({...s,data_insight_evidence:[{...e,analysis_kind:'arbitrary'}]}),/Dato complementario/);
 assert.doesNotMatch(c.detailHtml({...s,data_insight_evidence:[{...e,source_url:'https://'}]}),/Dato complementario/);
});
test('Home Global teaser preserves attribution, exact historical amount and method hold',()=>{
 const c=context(),before={theme_id:'global-ai-coding-payer-cost-2026',title:'La IA clínica infla gasto',excerpt:'Causalidad no validada'};
 const projected=c.globalPreview(before);assert.match(projected.title,/BCBSA.*942/);assert.match(projected.excerpt,/pendientes de verificación/);assert.equal(before.title,'La IA clínica infla gasto');
});
test('portfolio adapter holds unsupported percentage families without a people chart',()=>{
 const c={Intl};vm.createContext(c);vm.runInContext(fs.readFileSync('web/statistical-view.js','utf8'),c);
 const out=c.AlicantoStats.render({family:'respiratory_positivity',unit:'%',publication_status:'REVIEW_REQUIRED',complete_series_verified:true,source_url:'https://example.org/report',series:[{period:'2026-01',value:10},{period:'2026-02',value:20},{period:'2026-03',value:30}]});
 assert.doesNotMatch(out,/<svg|<table|Millones de personas|Beneficiarios|stat-kpi/);assert.match(out,/pendiente de verificación/);assert.match(out,/https:\/\/example.org\/report/);
});
test('Signal Density defaults and fiscalizacion',()=>{const c=context();assert.equal(vm.runInContext('periodMode',c),'30');assert.equal(vm.runInContext('sortMode',c),'date');assert.match(source,/Fiscalización/);assert.match(fs.readFileSync('web/index.html','utf8'),/<option value="30" selected>30 días<\/option>/)});
test('BACKFILL never counts as new since visit',()=>{const c=context();vm.runInContext("periodMode='last';previousVisit='2026-09-22T00:00:00Z'",c);assert.equal(c.inPeriod({ingestion_mode:'BACKFILL',event_date:'2026-09-23',detected_at:'2026-09-23T12:00:00Z'}),false);assert.equal(c.inPeriod({ingestion_mode:'LIVE',event_date:'2026-09-23',detected_at:'2026-09-23T12:00:00Z'}),true)});

test('coverage counts never invent LIVE or BACKFILL when queue has not run',()=>{const c=context();const msg=c.coverageText({sources:{one:{}},queue:null,queue_status:'awaiting_first_global_discovery'});assert.match(msg,/sin medición global/);assert.doesNotMatch(msg,/0 LIVE/)});
test('coverage separates LIVE funnel and historical queue',()=>{const c=context();const msg=c.coverageText({sources:{one:{status:'ok'},two:{status:'error'}},queue_status:'measured',queue:{live_pending:2,backfill_pending:37,rejected:6},coverage_live:{detected:10,evaluated:8,selected:3}});assert.match(msg,/1 fuentes activas/);assert.match(msg,/10 señales detectadas · 8 evaluadas · 3 seleccionadas/)});
test('active source counts technical availability even when editorial outcome is warning',()=>{const c=context();const msg=c.coverageText({sources:{a:{technical_status:'ok',status:'warning'},b:{technical_status:'ok',status:'ok'},c:{technical_status:'error',status:'error'}},queue_status:'measured',queue:{},coverage_live:{detected:0,evaluated:0,selected:0}});assert.match(msg,/2 fuentes activas/)});
test('Global metadata qualification does not increase the Chile LIVE source count',()=>{const c=context();const msg=c.coverageText({sources:{local:{technical_status:'ok'},who:{technical_status:'ok',discovery_scope:'global_intelligence'},paho:{technical_status:'ok',discovery_scope:'global_intelligence'}},queue_status:'measured',queue:{},coverage_live:{detected:0,evaluated:0,selected:0}});assert.match(msg,/1 fuentes activas/)});
test('sanction pulse lists resolutions rather than corroborating sources',()=>{const c=context();assert.match(c.sourceBlock([{title:'Acto 1',url:'https://example.org/1'}],true),/Resoluciones incluidas en este pulso/)});
test('read status survives any audited headline change through stable identity and exact legacy migration',async()=>{const c=context(),before={source_url:'https://df.cl/example',event_date:'2026-09-25',event_type:'OTHER',title:'Titular anterior'},after={...before,title:'Titular revisado',source_title_full:'Titular anterior'};assert.equal(c.idFor(before),c.idFor(after));c.after=after;c.legacy=c.legacyIdFor(before);await vm.runInContext("allSignals=[after];readSet.add(legacy);migrateReads()",c);assert.equal(vm.runInContext('isRead(allSignals[0])',c),true)});
test('every visible pre-review title migrates read state even when persistent rules remove routine items',async()=>{const overrides=JSON.parse(fs.readFileSync('config/editorial_copy_overrides_v1.json','utf8')).items.filter(x=>x.legacy_title),snapshot=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8')).signals;assert.equal(overrides.length,10);let checked=0;for(const override of overrides){const c=context(),signal=snapshot.find(s=>s.source_url===override.source_url&&s.event_date===override.event_date);if(!signal)continue;checked++;assert.equal(signal.legacy_read_title,override.legacy_title);c.signal=signal;c.legacy=c.legacyIdFor(signal,override.legacy_title);await vm.runInContext("allSignals=[signal];readSet.add(legacy);migrateReads()",c);assert.equal(vm.runInContext('isRead(allSignals[0])',c),true,override.source_url)}assert.ok(checked>=8)});
test('ambiguous legacy read never marks two signals that reuse one URL',async()=>{const c=context();vm.runInContext("allSignals=[{source_url:'https://example.org/reused',event_date:'2026-09-24',event_type:'OTHER',title:'Título nuevo A'},{source_url:'https://example.org/reused',event_date:'2026-09-25',event_type:'OTHER',title:'Título nuevo B'}]",c);c.legacy=c.encodedId('https://example.org/reused|Título anterior');await vm.runInContext("readSet.add(legacy);migrateReads()",c);assert.equal(vm.runInContext('allSignals.some(isRead)',c),false)});
test('legacy read from an absent older date never marks the sole current item at the same URL',async()=>{const c=context();vm.runInContext("allSignals=[{source_url:'https://example.org/weekly',event_date:'2026-09-25',event_type:'OTHER',title:'Título actual'}]",c);c.legacy=c.encodedId('https://example.org/weekly|Título de la semana anterior');await vm.runInContext("readSet.add(legacy);migrateReads()",c);assert.equal(vm.runInContext('isRead(allSignals[0])',c),false)});
test('Cards V2 does not pretend depth from a headline or duplicate summary',()=>{const c=context();const shallow={title:'Un titular',what_happened:'Un titular',why_it_matters:'Un titular',source_url:'https://example.org'};assert.equal(c.cardDepth(shallow),false);const html=c.card(shallow);assert.match(html,/data-detail/);assert.doesNotMatch(html,/Qué pasó:|Por qué importa:/);assert.match(html,/Fuente original/);assert.equal(c.cardDepth({...shallow,what_happened:'Detalle nuevo y confirmado que cambia el cuadro para los actores involucrados.',key_points:['Otra cifra material comprobada']}),true)});
test('limited historical evidence stays accessible without claiming analytic depth',()=>{const c=context();const shallow={title:'Anuncio',what_happened:'El anuncio no entrega detalles sobre alcance, vigencia ni ejecución. '.repeat(6),why_it_matters:'Puede interesar',affected_processes:['Prestaciones'],risk_notes:['No se informaron detalles']};assert.equal(c.detailKind(shallow),null);assert.match(c.card(shallow),/Más info/);assert.equal(c.detailKind({...shallow,source_alternatives:[{title:'Resolución 1',url:'https://example.org'}]}),'context')});
test('negative evidence and repeated importance are not executive findings',()=>{const c=context();const s={title:'Anuncio',what_happened:'Se anunció una medida',why_it_matters:'Afectaría a prestadores'};assert.equal(c.detailKind({...s,key_points:['La fuente no especifica el alcance, la inversión ni los plazos de implementación.']}),null);assert.equal(c.detailKind({...s,key_points:[s.why_it_matters]}),null)});
test('one persistent filter model replaces the duplicate preference surface',()=>{const c=context();const html=fs.readFileSync('web/index.html','utf8');assert.match(html,/Tus filtros se guardan automáticamente/);assert.doesNotMatch(html,/Personalizar mi radar|Prioriza tus intereses/);assert.doesNotMatch(source,/alicanto_interests|interestState|interestScore\(/);assert.match(source,/alicanto_filters/);assert.match(source,/persistFilters\(\)/)});
test('Home V2 keeps conversion surfaces compact and fail-closed',()=>{const html=fs.readFileSync('web/index.html','utf8'),app=fs.readFileSync('web/app.js','utf8');assert.match(html,/id="earlyAccessOpen"/);assert.match(html,/id="newsletterOpen"/);assert.match(html,/id="valueHighlights"/);assert.match(html,/id="filterDetails"/);assert.match(html,/id="radarMetrics"/);assert.match(html,/Ponte al día en 30 segundos/);assert.match(html,/Ve más allá de la señal/);assert.match(html,/Lo importante de la semana, directo a tu correo/);assert.doesNotMatch(html,/proveedor y privacidad aprobados|todavía no hay cuentas ni pagos/);assert.doesNotMatch(html,/Ingresar|Registrarse|Personalizar mi radar/);assert.match(app,/tarjetas · no leídos/);assert.match(app,/período/);assert.match(html,/Volver arriba/);assert.doesNotMatch(app,/Volver a 30 segundos/)});
test('sources public catalog is separate from administrative diagnostics',()=>{const app=fs.readFileSync('web/app.js','utf8'),html=fs.readFileSync('web/index.html','utf8');assert.match(app,/data\/public_sources\.json/);assert.doesNotMatch(app,/fetch\('data\/product\.json/);assert.match(html,/Fuentes de Alicanto/);assert.match(html,/sources\.html/)});
test('triage title expands opaque regulatory labels without mechanical truncation',()=>{const c=context();assert.equal(c.triageTitle({title:'Circular IF/N°535 · Reembolsos a empleadores públicos: prohíbe compensarlos con otras deudas',display_title:'Circular IF/N°535 · Reembolsos a empleadores públicos: prohíbe compensarlos con otras deudas',card_what:'La Superintendencia ajustó el cálculo de garantías para las isapres.'}),'Circular IF/N°535 · Reembolsos a empleadores públicos: prohíbe compensarlos con otras deudas');assert.doesNotMatch(fs.readFileSync('web/index.html','utf8'),/-webkit-line-clamp/)});
test('card never cuts a Bupa announcement in the middle of its meaning',()=>{const c=context();const s={title:'Bupa acelera inversiones',what_happened:'Bupa anunció tres proyectos por US$15 millones: abrirá un centro en La Dehesa, comprará Clínicas Huinganal y abrirá Mindplace en San Damián.',why_it_matters:'Incorpora capacidad ambulatoria y salud mental en el sector oriente mediante inversión y compra.'};const html=c.detailHtml(s);assert.match(html,/Huinganal y abrirá Mindplace en San Damián\./);assert.match(html,/inversión y compra\./);assert.doesNotMatch(html,/\.\.\.|…/);assert.doesNotMatch(fs.readFileSync('web/index.html','utf8'),/-webkit-line-clamp/)});
test('editorial enrichment never looks like independent corroboration',()=>{const c=context();const e=[{label:'Mismo emisor · no es corroboración independiente',title:'Canal oficial',url:'https://example.org',note:'No sustenta hechos adicionales.'}],h=[{label:'Contexto del mismo artículo · no es corroboración independiente',title:'Expansión IntegraMédica',url:'https://df.cl/original',event_date:'2026-09-21',note:'Contexto del mismo artículo.'}],s={title:'Señal',what_happened:'Hecho distinto confirmado.',why_it_matters:'Importa por una razón verificable.',source_url:'https://df.cl/original',editorial_enrichment:e,historical_connections:h};const html=c.enrichmentBlock(e,h,'Conexión histórica atribuida al mismo artículo DF.');assert.match(html,/Enriquecimiento editorial/);assert.match(html,/no es corroboración independiente/);assert.match(html,/No sustenta hechos adicionales/);assert.match(html,/Conexiones históricas/);assert.match(html,/Expansión IntegraMédica/);assert.equal(c.detailKind(s),'context');assert.doesNotMatch(c.sourceBlock(e),/Enriquecimiento editorial/);const card=c.card(s);assert.match(card,/Más info/);assert.match(card,/Fuente original/);assert.match(c.detailHtml(s),/Fuente original/)});
test('sanction pulse lists every material resolution including anchor',()=>{const c=context();const links=[1,2,3].map(i=>({title:`Resolución IP/N°${i} - Emisión: 08/09/2026`,material:`Clínica ${i} · 70 UF · cheque en garantía`,url:`https://example.org/${i}`}));const s={title:'Pulso sanciones',what_happened:'3 sanciones registradas.',why_it_matters:'Fiscalización reciente.',sanction_count:3,source_alternatives:links,source_url:links[0].url};const html=c.detailHtml(s);assert.equal((html.match(/Clínica \d · 70 UF/g)||[]).length,3);assert.doesNotMatch(html,/3 sanciones registradas; 2 resoluciones/)});
test('card metadata separates resolution, data period, publication and validation dates',()=>{const c=context();const sanction=c.cardMetadata({sanction_count:3,event_date:'2026-09-15',source_name:'Superintendencia de Salud'});assert.match(sanction,/Publicado 15/);assert.doesNotMatch(sanction,/Resolución más reciente/);const data=c.cardMetadata({event_type:'DATA_PULSE',data_period:'2026-07',event_date:'2026-09-07',validation_date:'2026-09-24',source_name:'Superintendencia de Salud'});assert.match(data,/Datos a 2026-07/);assert.match(data,/Publicado 07/);assert.match(data,/Validado 24/);assert.doesNotMatch(data,/Publicación no verificada/)});
test('unverified Circular 77 relation remains visible without invented URL',()=>{const c=context();const html=c.contextBlock([{title:'Circular IF/N°77',relationship:'Norma modificada',url:null,verified:false}]);assert.match(html,/Normativa relacionada/);assert.match(html,/Circular IF\/N°77/);assert.match(html,/Norma modificada/);assert.match(html,/enlace pendiente de verificación/);assert.doesNotMatch(html,/href=/)});
test('Global Intelligence mirrors Home with value-first inbox and Chile hypothesis separation',()=>{const html=fs.readFileSync('web/global.html','utf8'),app=fs.readFileSync('web/app.js','utf8'),js=fs.readFileSync('web/global.js','utf8'),data=JSON.parse(fs.readFileSync('web/data/global_themes.json','utf8'));assert.match(html,/Ponte al día en Global Intelligence/);assert.match(html,/globalPeriod/);assert.match(html,/globalPublisher/);assert.match(html,/globalSort/);assert.doesNotMatch(html,/está en preparación|Vista pública de la experiencia/);assert.doesNotMatch(js,/<strong>Qué mirar en Chile|<strong>Lectura estratégica|<strong>Por qué importa/);assert.match(fs.readFileSync('web/read-state.js','utf8'),/alicanto_global_read/);assert.match(js,/AlicantoRead/);assert.match(js,/globalDetail/);assert.match(js,/Metodología y alcance/);assert.match(app,/Global Intelligence · análisis internacional/);assert.match(app,/globalId/);assert.ok(data.themes.every(t=>t.kind==='global_theme'&&t.chile_watch.kind==='hypothesis'&&t.chile_watch.trend_chile_status==='not_established'&&t.cross_analysis));assert.ok(data.themes.flatMap(t=>t.sources).filter(s=>s.material_type!=='high_trust_press').every(s=>s.analysis.key_findings.length>=3&&s.analysis.methodology))});
test('weekly analysis has its own read identity and keeps the base news accessible',()=>{
 class FixedClock extends Date{
  constructor(...args){super(...(args.length?args:['2026-10-12T01:30:00Z']))}
  static now(){return Date.parse('2026-10-12T01:30:00Z')}
 }
 const c=context(FixedClock);
 const base={title:'Resolución Exenta IF/N°11156',normative_document_label:'Resolución Exenta IF/N°11156',source_name:'Superintendencia de Salud',source_url:'https://example.org/reg',event_date:'2026-10-11',signal_types:['Normativa'],scopes:['Isapres'],what_happened:'La Superintendencia dictó una resolución con efecto operativo.',why_it_matters:'La isapre debe adecuar cumplimiento y operación.'};
 c.fixture=base;
 vm.runInContext("allSignals=[fixture];freeValue={weekly_insight:{id:'weekly',editorial_review_pass:true,title:fixture.title,insight_title:'Cobertura TEA',source_url:fixture.source_url,event_date:fixture.event_date},global_teaser:{theme_id:'theme-1',title:'Research',published_at:fixture.event_date}}",c);
 assert.equal(c.specials()[0].id,'global:theme-1');
 assert.equal(c.specials()[1].id,'weekly:weekly');
 assert.equal(c.visible().length,1);
 assert.equal(c.inboxPool().length,1);
 assert.equal(c.specials().length,2);
 assert.equal(c.weeklyFresh({...base,editorial_review_pass:true,event_date:'2026-10-12'}),false);
});
test('Final Home polish keeps sharing in feed state actions and metadata in every brief row',()=>{const c=context(),app=fs.readFileSync('web/app.js','utf8'),html=fs.readFileSync('web/index.html','utf8');assert.match(app,/\{global:0,weekly:1\}/);assert.match(app,/data-share=/);assert.match(app,/navigator\.share/);assert.match(app,/navigator\.clipboard/);assert.match(app,/<span class="brief-meta">\$\{fmtBriefDate\(x\.date\)\} · \$\{esc\(briefSource\(x\)\)\}<\/span>/);assert.doesNotMatch(app,/briefread[^>]+data-share/);const signal=c.card({title:'Señal',source_url:'https:\/\/example.org\/signal',event_date:'2026-09-25'}),special=c.specialCard({kind:'global',id:'global:1',title:'Research',summary:'Resumen',date:'2026-09-25',source:'WHO'});for(const generated of [signal,special]){const status=generated.match(/<div class="card-status-actions">([\s\S]*?)<\/div>/)?.[1]||'';const actions=generated.match(/<div class="card-actions">([\s\S]*?)<\/div>/)?.[1]||'';assert.match(status,/data-(?:special-)?read=/);assert.match(status,/data-share=/);assert.doesNotMatch(actions,/data-share=/)}assert.match(signal,/Fuente original/);assert.match(app,/querySelectorAll\('\.briefrow'\)\.length<=6/);assert.match(app,/Enlace copiado/);assert.match(app,/special-\$\{x\.id\}/);assert.match(app,/function sharedHashTarget\(\)\{try\{/);assert.match(html,/brief-list\.expanded/);assert.match(html,/overflow:hidden!important/);assert.match(html,/\.action-icon/);assert.match(html,/\.briefread\{width:44px!important;min-width:44px!important;min-height:44px!important/) });
test('persistent presentation contracts supersede older editorial copy without losing substance',()=>{const c=context(),radar=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8'));for(const signal of radar.signals.filter(row=>row.event_date>='2026-09-12')){const detail=c.detailHtml(signal),title=c.triageTitle(signal),summary=c.triageSummary(signal);assert.ok(title,signal.source_url+' title must remain non-empty');assert.ok(summary,signal.source_url+' triage summary must remain substantive');if(signal.normative_document_type&&signal.normative_document_number){assert.ok(title.toLowerCase().includes(String(signal.normative_document_type).toLowerCase()),signal.source_url+' must retain normative act type');assert.ok(title.includes(signal.normative_document_number),signal.source_url+' must retain normative number')}assert.ok(detail.length>0,signal.source_url+' detail must remain renderable')}});
test('subscription capture is MailerLite-ready, consented and fail-closed until provider and privacy approval',()=>{const html=fs.readFileSync('web/subscription.html','utf8'),js=fs.readFileSync('web/subscription.js','utf8'),cfg=JSON.parse(fs.readFileSync('web/data/subscription.json','utf8'));assert.match(html,/type="email"[^>]*required disabled/);assert.match(html,/id="consent"[^>]*required disabled/);assert.match(js,/confirmar la suscripción/);assert.match(js,/capture_enabled===true/);assert.match(js,/privacy_approved===true/);assert.match(js,/double_opt_in===true/);assert.match(js,/https:/);assert.equal(cfg.provider,'mailerlite');assert.deepEqual(cfg.groups,{newsletter_weekly:null,early_access:null});assert.equal(cfg.capture_enabled,false);assert.equal(cfg.send_enabled,false);assert.equal(cfg.api_html_content_supported,false);assert.equal(cfg.sender.verified,false);assert.equal(cfg.form_action,null)});
test('public pages carry consistent social metadata without unapproved canonical domain',()=>{
 for(const page of ['index','coverage','global','subscription']){
  const html=fs.readFileSync(`web/${page}.html`,'utf8');
  assert.match(html,/<meta property="og:title" content="[^"]+"\/>/);
  assert.match(html,/<meta property="og:description" content="[^"]+"\/>/);
  assert.match(html,/og:image" content="https:\/\/cftorre1\.github\.io\/Radar-salud\/assets\/alicanto-logo-header\.png/);
  assert.doesNotMatch(html,/alicanto\.cl|rel="canonical"/);
 }
});

test('normative detail keeps act identity visible even with descriptive triage title',()=>{const c=context();const html=c.detailHtml({title:'Circular IF/N°535 · Reembolsos a empleadores públicos: prohíbe compensarlos con otras deudas',display_title:'Circular IF/N°535 · Reembolsos a empleadores públicos: prohíbe compensarlos con otras deudas',card_what:'La Superintendencia ajustó una obligación material.',why_it_matters:'Las isapres deben adecuar su operación.',event_type:'REGULATION',normative_document_label:'Circular IF/N°535',normative_context:'La regla limita la compensación de reembolsos SIL, salvo habilitación legal expresa.',source_name:'Superintendencia de Salud',source_url:'https://example.org/c535'});assert.match(html,/Circular IF\/N°535 · Reembolsos a empleadores públicos/);assert.match(html,/La regla limita la compensación/);assert.doesNotMatch(html,/Documento:<\/strong>/);assert.doesNotMatch(html,/<\/h2>\}/);assert.equal(c.detailKind({event_type:'REGULATION',normative_context:'Contexto adicional'}),'context');});
test('admin P0 scorecard is fail-closed and never fabricates unavailable beta metrics',()=>{const html=fs.readFileSync('web/admin/product.html','utf8'),js=fs.readFileSync('web/admin/product.js','utf8'),cfg=JSON.parse(fs.readFileSync('config/admin_scorecard_v1.json','utf8'));assert.match(html,/Scorecard ejecutivo/);assert.match(html,/id="scorecard"/);assert.match(js,/renderScorecard/);assert.match(js,/No disponible/);assert.equal(cfg.status,'p0_read_model');for(const id of ['beta_usage','conversion','finops'])assert.match(cfg.dimensions.find(x=>x.id===id).availability,/blocked_until/);});

test('normative public title always includes act identity and subject before human override',()=>{const c=context();const s={title:'Circular IF/N°533',display_title:'Circular IF/N°533 sobre reporte mensual de inventario SIL',editorial_review_id:'expert',card_what:'Cambio operativo',why_it_matters:'Las isapres deben adecuar el reporte.'};assert.equal(c.triageTitle(s),'Circular IF/N°533 sobre reporte mensual de inventario SIL');});
test('persistent editorial contract encodes aggregation and review precedence',()=>{const cfg=JSON.parse(fs.readFileSync('config/editorial_rules_v2.json','utf8')).presentation_contract;assert.equal(cfg.normative_identity_and_subject.required,true);assert.equal(cfg.aggregate_over_components.required,true);assert.equal(cfg.surface_consistency.required,true);assert.equal(cfg.precedence.persistent_rules_override_human_copy,true);});

test('editorial intelligence committee is permanent, multidisciplinary and signal-specific',()=>{const cfg=JSON.parse(fs.readFileSync('config/editorial_intelligence_committee_v1.json','utf8'));assert.equal(cfg.name,'Comité de Inteligencia Editorial Alicanto');for(const id of ['editorial_intelligence','health_business','data_analytics','decision_intelligence','regulatory_legal','evidence_research'])assert.ok(cfg.standing_members.some(x=>x.id===id));assert.deepEqual(cfg.signal_panels.Datos,['editorial_intelligence','health_business','data_analytics','decision_intelligence','evidence_research']);assert.ok(cfg.signal_panels.Normativa.includes('regulatory_legal'));assert.equal(cfg.learning_loop.new_statistics.includes('deuda analítica'),true);});


test('visible stock obeys committee and publication contract site-wide',()=>{
 const c=context(),radar=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8'));
 for(const s of radar.signals){
   assert.ok(s.editorial_committee,s.source_url+' committee artifact required');
   assert.equal(s.editorial_committee.verdict,'PASS',s.source_url+' visible card must be committee PASS');
   assert.equal(c.individualCardAllowed(s),true,s.source_url+' must satisfy publication contract');
 }
});

test('Bupa and Pulso retain approved business depth without weak references',()=>{
 const radar=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8'));
 const bupa=radar.signals.find(s=>/Bupa refuerza/.test(s.title||''));
 assert.ok(bupa);
 assert.equal(bupa.source_name,'Diario Financiero');
 assert.match(bupa.what_happened,/US\$15 millones/);
 assert.match(bupa.what_happened,/La Dehesa/);
 assert.match(bupa.what_happened,/Huinganal/);
 assert.match(bupa.what_happened,/Mindplace/);
 assert.deepEqual(bupa.related_context||[],[]);
 assert.deepEqual(bupa.source_alternatives||[],[]);
 const pulso=radar.signals.find(s=>s.event_type==='DATA_PULSE'&&/Isapre/.test(s.title||''));
 assert.ok(pulso);
 assert.match(pulso.title,/Pulso Isapre/);
 assert.ok(pulso.summary_table?.rows?.length>=6);
 assert.match(pulso.why_it_matters,/no una explicación causal/);
 assert.ok((pulso.data_insight_evidence||[]).length>=5);
});


test('Home keeps period compact and exposes direct Global Intelligence navigation',()=>{
 const html=fs.readFileSync('web/index.html','utf8'),app=fs.readFileSync('web/app.js','utf8');
 assert.match(html,/class="header-premium" href="global\.html">Global · Internacional<\/a>/);
 const head=html.match(/<div class="radar-head">([\s\S]*?)<\/div>\s*<div class="radar-status-row">/)?.[1]||'';
 assert.doesNotMatch(head,/id="period"/);
 assert.match(html,/class="radar-status-row"/);
 assert.match(html,/id="period"/);
 assert.doesNotMatch(app,/tarjetas · no leídos \$\{unread\} · período/);
});



test('weekly freshness expires at Chile midnight and rejects invalid or recycled dates',()=>{
 const c=context(),w={editorial_review_pass:true,event_date:'2026-10-07',freshness_anchor_date:'2026-10-07',expires_on:'2026-10-14'};
 assert.equal(c.weeklyFresh(w,new Date('2026-10-14T02:59:59Z')),true);
 assert.equal(c.weeklyFresh(w,new Date('2026-10-14T03:00:00Z')),false);
 assert.equal(c.weeklyFresh({...w,event_date:'2026-10-32'},new Date('2026-10-11T12:00:00Z')),false);
 assert.equal(c.weeklyFresh({...w,freshness_anchor_date:'2026-09-14'},new Date('2026-10-11T12:00:00Z')),false);
 assert.equal(c.weeklyFresh({...w,editorial_review_pass:false},new Date('2026-10-11T12:00:00Z')),false);
});
test('approved insight detail exposes figures decisions limits and all evidence links',()=>{
 const c=context(),w=JSON.parse(fs.readFileSync('data/weekly_insight/editorial_approved.json')).weekly_insight,body={innerHTML:''};
 c.document={getElementById:id=>body};c.renderWeeklyDetail(w);
 for(const label of ['Cifras y alcance','Actores','Lectura Alicanto:','Decisiones que cambia','Qué observar','Límites de la evidencia'])assert.ok(body.innerHTML.includes(label));
 for(const url of w.source_refs)assert.ok(body.innerHTML.includes(url));
 assert.ok(body.innerHTML.includes('Límites de la evidencia'));
});

test('enforcement dates display issuance and preserve separately verified publication',()=>{const c=context();const s={signal_types:['Fiscalización'],event_date:'2026-09-23',emission_date:'2026-09-23',publication_date:null,event_date_basis:'verified_primary_emission'};assert.match(c.cardMetadata(s),/Emitido/);assert.match(c.cardMetadata(s),/Publicación no verificada/);assert.doesNotMatch(c.cardMetadata(s),/Publicado/);assert.match(c.cardMetadata({...s,publication_date:'2026-09-25'}),/Publicado.*25.*Emitido.*23/);assert.match(c.sourceBlock([{...s,url:'https://example.org',title:'Acto'}],true),/Emitido/)});

test('Global keeps every eligible theme beyond ten while preserving publisher filters',()=>{
 const c={AlicantoRead:{readSet:new Set()},localStorage:{getItem:()=>null,setItem:()=>{}},Date,Intl,Set,Map};vm.createContext(c);
 vm.runInContext(fs.readFileSync('web/global.js','utf8').split('AlicantoRead.subscribe(')[0],c);
 c.input=Array.from({length:14},(_,i)=>({id:String(i),sources:[{publisher:i%2?'WHO':'OECD',published_at:'2026-10-10'}]}));
 vm.runInContext("themes=input;periodMode='all'",c);
 assert.equal(c.visibleThemes().length,14);
 vm.runInContext("publisherMode='OECD'",c);assert.equal(c.visibleThemes().length,7);
});

test('source panel never equates transport errors or absent telemetry with no news',()=>{
 const c=context();
 assert.match(c.sourceCaptureLabel({technical_status:'error',checked_at:'2026-10-12T00:00:00Z'}),/no se puede confirmar si hay novedades/);
 assert.match(c.sourceCaptureLabel({coverage_status:'blocked'}),/Captura con error/);
 assert.match(c.sourceCaptureLabel({technical_status:'held'}),/pausada/);
 assert.equal(c.sourceCaptureLabel({technical_status:'not_polled_license_hold',status:'error',coverage_status:'not_permitted'}),'Captura pausada por licencia');
 assert.match(c.sourceCaptureLabel({technical_status:'partial'}),/parcial/);
 assert.match(c.sourceCaptureLabel({checked_at:'2026-10-12T00:00:00Z',technical_status:'ok'}),/no acredita cobertura completa/);
 assert.equal(c.sourceCaptureLabel({}),'Sin consulta verificable');
 assert.doesNotMatch(fs.readFileSync('web/app.js','utf8'),/sin señal reciente/);
});
test('SUSESO dates never contaminate SIS source selection dates',()=>{
 const c=context();
 assert.equal(c.canonicalSource('Superintendencia de Seguridad Social (SUSESO)'),'SUSESO');
 assert.equal(c.canonicalSource('Superintendencia de Salud'),'Superintendencia de Salud');
 assert.notEqual(c.canonicalSource('Superintendencia de Seguridad Social'),c.canonicalSource('Superintendencia de Salud'));
 assert.equal(c.canonicalSource('Pulso / La Tercera'),c.canonicalSource('La Tercera'));
});
