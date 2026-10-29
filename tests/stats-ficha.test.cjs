// Statistics ficha renderer (web/stats-ficha.js): layout only, numbers come from the evidence package.
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
function load(){const c={Intl,URL,CSS:{escape:s=>s}};c.globalThis=c;vm.createContext(c);vm.runInContext(fs.readFileSync('web/stats-ficha.js','utf8'),c);return c.AlicantoFicha}
const live=JSON.parse(fs.readFileSync('data/stats_fichas/live/f1_cartera.json','utf8'));
const pub={...live};delete pub.evidence;

// Dirección 29-oct (option C→B): index of topics with sparklines → topic mode (sticky picker, hero chart first).
const figs=html=>[...html.matchAll(/<figure class="sf-chart" data-chart="([^"]+)"/g)].map(m=>m[1]);
const panel=(html,id)=>{const a=html.indexOf(`data-sf-id="${id}"`);const b=html.indexOf('<section class="sf-tpanel"',a+1);return html.slice(a,b<0?html.indexOf('</section></div></section>',a):b)};
test('ficha opens as an index of topics and renders each topic with the hero chart first',()=>{
 const html=load().render(pub,{shareId:'sig-stats-ficha:F1:2026-08',shareUrl:'data/fichas/f1_cartera.html'});
 const order=['sf-kicker','sf-headline','sf-dek','sf-share','sf-index','sf-topic','sf-notes'];
 const at=order.map(k=>html.indexOf(k));assert.ok(at.every(i=>i>=0),JSON.stringify(at));assert.deepEqual([...at].sort((a,b)=>a-b),at);
 // No KPI strip, 'Qué mirar' or facts section outside the topics; notes and sources behind one collapsed toggle.
 assert.doesNotMatch(html,/aria-label="Indicadores clave"/);assert.doesNotMatch(html,/class="sf-watch"/);assert.doesNotMatch(html,/class="sf-facts"/);
 assert.match(html,/<details class="sf-notes"><summary>Notas y fuentes<\/summary>/);assert.doesNotMatch(html,/Por qué importa/);
 assert.match(html,/id="detailTitle"/);assert.match(html,/2\.486\.683/);assert.match(html,/agosto 2026/);
 // Index rows link to '#sig-<id>&tema=<topic>' (a copied URL reopens the ficha); without a signal id, '#tema=<topic>'.
 assert.match(load().render(pub),/<a class="sf-row" href="#tema=total" data-sf-row="0">/);assert.doesNotMatch(load().render(pub),/data-sf-sig=/);
 assert.match(html,/<article class="sf sf-cb" data-sf-sig="sig-stats-ficha:F1:2026-08"/);
 // Index: 5 rows with label, one line and a sparkline (no number under it); Regional is pending.
 const rows=[...html.matchAll(/<a class="sf-row" href="#sig-stats-ficha%3AF1%3A2026-08&amp;tema=([\w-]+)" data-sf-row="\d"><span class="sf-row-txt"><span class="sf-row-label">([^<]+)(?:<span class="sf-pending">pendiente<\/span>)?<\/span><span class="sf-row-line">([^<]+)<\/span><\/span><span class="sf-spark">(<svg[^]*?<\/svg>|<span class="sf-spark-pend">pendiente<\/span>)<\/span>/g)];
 assert.deepEqual(rows.map(m=>[m[1],m[2],m[3]]),[['total','Cartera total','2.486.683 beneficiarios · menor baja del año'],
  ['isapres','Por Isapre','Banmédica: 77% de la baja · 3 Isapres crecen'],['mezcla','Cotizantes y cargas','Cotizantes suben por segundo mes'],
  ['movilidad','Movilidad y desahucios','Salen más de los que entran · dato a julio'],['regional','Regional','Enlace a la SIS · cifras aún no extraídas']]);
 assert.equal(rows.filter(m=>m[4].startsWith('<svg')).length,4);assert.match(rows[4][4],/pendiente/);
 for(const m of rows)assert.doesNotMatch(m[4],/<b>|<text/);
 // Topic mode: select-only combobox with 'Todos los temas' first, step buttons, one hidden panel per topic.
 assert.match(html,/<button type="button" class="sf-pick" aria-haspopup="listbox" aria-expanded="false" aria-controls="(sf\d+)-list">/);
 const opts=[...html.matchAll(/role="option"[^>]*><span class="sf-opt-n">[^]*?<span class="sf-opt-label">([^<]+)/g)].map(m=>m[1]);
 assert.deepEqual(opts,['Todos los temas','Cartera total','Por Isapre','Cotizantes y cargas','Movilidad y desahucios','Regional']);
 assert.match(html,/aria-label="Tema anterior" disabled/);assert.match(html,/data-sf-step="1" aria-label="Tema siguiente"/);
 assert.equal((html.match(/class="sf-tpanel"[^>]*hidden>/g)||[]).length,5);
 assert.equal(figs(html).length,8);assert.equal((html.match(/Ver datos del gráfico/g)||[]).length,8);
 // Cartera total: stock line first, monthly differences second; no dek, no KPIs, no reading legends.
 const total=panel(html,'total');assert.deepEqual(figs(total),['f1-stock','f1-mm']);assert.match(total,/^[^]*?<div class="sf-hero"><figure class="sf-chart" data-chart="f1-stock"/);
 assert.doesNotMatch(total,/sf-tdek|class="sf-kpi"/);
 assert.match(total,/role="img" aria-label="Cambio mensual de beneficiarios[^"]*Ago −814/);
 const chartText=[...html.matchAll(/<figure[^]*?<\/figure>/g)].map(m=>m[0]).join(' ');assert.equal(chartText.length>0,true);
 for(const gone of ['eje sin partir de cero','Columna más corta','Tinta = pierde','agosto en acento','no se suman'])assert.ok(!chartText.includes(gone),gone);
 assert.match(html,/punto = agosto, aro = enero/);assert.match(total,/la calcula Alicanto/);
 // Isapres: no dek, no KPIs; the by-Isapre table splits each change into cotizantes and cargas.
 const isa=panel(html,'isapres');assert.doesNotMatch(isa,/sf-tdek|class="sf-kpi"/);
 assert.match(isa,/<thead><tr><th scope="col" class="">Isapre<\/th><th scope="col" class="n">Cambio<\/th><th scope="col" class="n">Cotizantes<\/th><th scope="col" class="n">Cargas<\/th><th scope="col" class="n">% vs\. enero<\/th><\/tr><\/thead>/);
 assert.match(isa,/<th scope="row">Cerradas \(3\)<\/th><td class="n">−1\.433<\/td><td class="n">−553<\/td><td class="n">−880<\/td>/);
 assert.match(isa,/<th scope="row">Sistema<\/th><td class="n">−27\.355<\/td><td class="n">−5\.895<\/td><td class="n">−21\.460<\/td><td class="n">−1,09%<\/td>/);
 // Cotizantes y cargas: the hero chart, then the dek and two KPI cards, then the other chart.
 const mez=panel(html,'mezcla');const k=[...mez.matchAll(/<p class="sf-lab">([^<]+)<\/p><p class="sf-val">([^<]+)<span[^]*?<p class="sf-delta">([^<]+)<\/p>/g)].map(m=>m.slice(1));
 assert.deepEqual(k,[['Cotizantes','1.551.169','−5.895 desde enero (−0,38%)'],['Cargas','935.514','−21.460 desde enero (−2,24%)']]);
 const ix=['data-chart="f1-cot"','<p class="sf-tdek">Las cargas explican el 78% de la baja del año.</p>','sf-tkpis','data-chart="f1-mix"','Siguiente tema','Todos los temas'].map(x=>mez.indexOf(x));
 assert.ok(ix.every(i=>i>=0),JSON.stringify(ix));assert.deepEqual([...ix].sort((a,b)=>a-b),ix);
 assert.doesNotMatch(panel(html,'movilidad'),/sf-tdek|class="sf-kpi"/);
 // Regional (no 'dek' from the builder) falls back to its tab text and links; the last topic has no 'Siguiente tema'.
 const reg=panel(html,'regional');assert.match(reg,/sf-tdek">Alicanto aún no extrae/);assert.match(reg,/a-nivel-regional-agosto-2026/);assert.doesNotMatch(reg,/Siguiente tema/);
 assert.match(html,/Compartir informe/);assert.match(html,/data-share-url="data\/fichas\/f1_cartera\.html"/);
 assert.match(html,/sha256 [0-9a-f]{12}…/);assert.doesNotMatch(html,/Lectura Alicanto<\/h3>/);
});

test('the last-point label goes below the point when the line descends (0,603 never sits on the line)',()=>{
 const html=load().render(pub);const mix=html.slice(html.indexOf('data-chart="f1-mix"'));const svg=mix.slice(0,mix.indexOf('</svg>'));
 const c=[...svg.matchAll(/<circle cx="([\d.]+)" cy="([\d.]+)"/g)].map(m=>[Number(m[1]),Number(m[2])]).pop();
 const lab=/<text class="sf-lastlab" x="([\d.]+)" y="([\d.]+)"[^>]*>0,603<\/text>/.exec(svg);assert.ok(lab,'last label');
 assert.ok(Number(lab[2])>c[1]+10,`label y ${lab[2]} vs point ${c[1]}`);
 // A rising series keeps the label above its last point.
 const up=load().render({...pub,tabs:[{id:'t',label:'T',charts:[{id:'u',form:'line',digits:0,headline:'x',rows:[{label:'A',value:1},{label:'B',value:3}]}]}]});
 const u=/<circle cx="[\d.]+" cy="([\d.]+)" r="5"[^]*?<text class="sf-lastlab" x="[\d.]+" y="([\d.]+)"/.exec(up);assert.ok(Number(u[2])<Number(u[1]));
});

test('a builder without topic fields falls back to its tab text and first chart',()=>{
 const html=load().render({...pub,tabs:[{id:'a',label:'A',text:['Primera frase corta; segunda parte.','Otro párrafo.'],charts:[{id:'c1',form:'columns_signed',headline:'Titular del gráfico',rows:[{label:'x',value:-2},{label:'y',value:3}]}]},
  {id:'b',label:'B',dek:null,text:['No se muestra.'],charts:[{id:'c2',form:'dots',headline:'Puntos',rows:[{label:'x',value:2}]}]}]});
 assert.match(html,/<span class="sf-row-line">Primera frase corta<\/span><\/span><span class="sf-spark"><svg viewBox="0 0 96 28" role="img" aria-label="Titular del gráfico">/);
 assert.match(html,/<p class="sf-tdek">Primera frase corta; segunda parte\.<\/p><p class="sf-tdek">Otro párrafo\.<\/p>/);
 // dek: null means no text; a one-row chart has no sparkline.
 assert.doesNotMatch(html,/sf-tdek">No se muestra/);assert.match(html,/<span class="sf-row-line">No se muestra<\/span><\/span><span class="sf-spark"><\/span>/);
 // A ficha without topics keeps the KPI strip.
 assert.match(load().render({...pub,tabs:[]}),/aria-label="Indicadores clave"/);
});

test('Lectura shows only after a verifier PASS and all text is escaped',()=>{
 const F=load();
 const ok=F.render({...pub,lectura:{status:'pass',text:'Para las Isapres <b>importa</b> la base de cotizantes.'}});
 assert.match(ok,/Lectura Alicanto<\/h3><p>Para las Isapres &lt;b&gt;importa&lt;\/b&gt;/);
 assert.doesNotMatch(F.render({...pub,lectura:{status:'verifier_fail',text:'x'}}),/Lectura Alicanto<\/h3>/);
 assert.match(F.render({...pub,headline:'<img src=x onerror=1>'}),/&lt;img src=x onerror=1&gt;/);
 assert.match(F.render({...pub,status:'HOLD'}),/Ficha no disponible/);
});

test('app.js hands statistics fichas to the self-contained renderer and keeps legacy paths',()=>{
 const app=fs.readFileSync('web/app.js','utf8');
 assert.match(app,/if\(s\.stats_ficha&&typeof AlicantoFicha!=='undefined'\)return AlicantoFicha\.render\(s\.stats_ficha,\{shareId:`sig-\$\{idFor\(s\)\}`,shareUrl:s\.share_url\}\);/);
 // The detail mounts the index → topic behaviour after rendering; a shared '#sig-<id>&tema=<tema>' still finds the signal.
 assert.match(app,/AlicantoFicha\.mount\(body\)/);assert.match(app,/replace\(\/&tema=\[\^&\]\*\$\/,''\)/);
 // A copied topic URL (page-load hash with '&tema=') reopens the ficha; the ficha's own pushState URLs never do.
 assert.match(app,/topicLink=\/&tema=\[\^&\]\*\$\/\.test\(location\.hash\)&&location\.hash===loadHash/);
 const index=fs.readFileSync('web/index.html','utf8');
 assert.ok(index.indexOf('stats-ficha.js')>index.indexOf('statistical-view.js')&&index.indexOf('stats-ficha.js')<index.indexOf('src="app.js"'));
 assert.match(index,/stats-ficha\.css/);
});

test('snapshot carries the August ficha and its share page has an OG preview',()=>{
 const snap=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8'));const card=snap.signals.find(s=>s.stats_ficha);
 assert.equal(card.data_period,'2026-08');assert.equal(card.share_url,'data/fichas/f1_cartera.html');assert.equal(card.stats_ficha.evidence,undefined);
 const page=fs.readFileSync('web/data/fichas/f1_cartera.html','utf8');
 assert.match(page,/<meta property="og:title" content="[^"]+· Alicanto Salud"/);assert.match(page,/url=\.\.\/\.\.\/index\.html\?abrir=1#sig-stats-ficha:F1:2026-08/);assert.match(page,/twitter:card" content="summary"/);
});

test('GES correction: the row tag and the detail note use the same date label',()=>{
 const F=load();const snap=JSON.parse(fs.readFileSync('web/data/radar_today.json','utf8'));
 const ges=snap.signals.find(s=>s.statistical_view&&s.statistical_view.correction);const c=ges.statistical_view.correction;
 assert.equal(c.label,'28 oct');assert.ok(c.text.startsWith('Corregido el 28 oct:'));
 assert.match(F.correctionTag(ges),/>Corregido el 28 oct<\/span>/);
 assert.equal(F.correctionLabel({corrected_at:'2026-10-28'}),'28 oct');assert.equal(F.correctionTag({}),'');
 assert.match(fs.readFileSync('web/app.js','utf8'),/AlicantoFicha\.correctionTag\(s\)/);
});

// F4 (GES) and F6 (Boletín IP) fichas: fixture cards built by tests/stats_ficha_fixtures.py (fixture hashes; F4 values
// are synthetic, F6 values are the verified N°2-2026 reading). Layout only: every number comes from the package.
for(const [slug,tabs,charts,kpis] of [['f4_ges',['Totales','Top problemas','Fonasa vs Isapre','Tendencia trimestral'],5,0],
                                      ['f6_prestadores',['Acreditación','Mediación','Reclamos','RNPI'],3,0]]){
 test(`${slug}: index of topics, topic text, collapsed notes and Option-B share`,()=>{
  const card=JSON.parse(fs.readFileSync(`tests/fixtures/stats_fichas/${slug}.card.json`,'utf8'));const f=card.stats_ficha;
  assert.equal(f.evidence,undefined);assert.equal(f.status,'PASS');
  const html=load().render(f,{shareId:`sig-${card.piece_id}`,shareUrl:card.share_url});
  const order=['sf-kicker','sf-headline','sf-dek','sf-share','sf-index','sf-topic','sf-notes'];
  const at=order.map(k=>html.indexOf(k));assert.ok(at.every(i=>i>=0),JSON.stringify(at));assert.deepEqual([...at].sort((a,b)=>a-b),at);
  // The generic index → topic layout: one index row per topic (builder index line), a sparkline when the topic has a
  // chart with 2+ rows, and the topic text (no builder dek) under the hero chart.
  assert.deepEqual([...html.matchAll(/<span class="sf-row-label">([^<]+)/g)].map(m=>m[1]),tabs);
  assert.deepEqual([...html.matchAll(/<span class="sf-row-line">([^<]+)/g)].map(m=>m[1]),f.tabs.map(t=>t.index_line));
  assert.ok(f.tabs.every(t=>t.index_line&&t.index_line.length<=64));
  assert.equal((html.match(/<figure class="sf-chart"/g)||[]).length,charts);
  assert.equal((html.match(/class="sf-kpi"/g)||[]).length,kpis);assert.doesNotMatch(html,/class="sf-watch"/);
  for(const t of f.tabs)for(const x of t.text||[])assert.ok(html.includes(x.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')),x);
  assert.match(html,/<details class="sf-notes"><summary>Notas y fuentes<\/summary>/);assert.doesNotMatch(html,/<details class="sf-notes" open/);
  assert.doesNotMatch(html,/Por qué importa/);assert.doesNotMatch(html,/class="sf-facts"/);
  assert.match(html,new RegExp(`data-share-url="data/fichas/${slug}\\.html"`));assert.match(html,/sha256 [0-9a-f]{12}…/);
  assert.equal(card.share_url,`data/fichas/${slug}.html`);
 });
}
test('F4 shows tasa bruta, Fonasa rate not available and percent bars with one decimal',()=>{
 const f=JSON.parse(fs.readFileSync('tests/fixtures/stats_fichas/f4_ges.card.json','utf8')).stats_ficha;const html=load().render(f);
 assert.match(html,/Tasa bruta Isapre/);assert.match(html,/tasa no disponible/);
 assert.match(html,/aria-label="Problemas que crecen: variación a\/a de casos[^"]*Cáncer de mama en… 35,5%/);
 assert.match(html,/Dos problemas superan 15% a\/a/);assert.match(html,/posible cambio de decreto GES/);
});
test('F6 keeps stocks and titles labelled and shows the claims change',()=>{
 const f=JSON.parse(fs.readFileSync('tests/fixtures/stats_fichas/f6_prestadores.card.json','utf8')).stats_ficha;const html=load().render(f);
 assert.match(html,/971/);assert.match(html,/1\.004\.982/);assert.match(html,/no profesionales únicos/);assert.match(html,/\+30,5%/);
 assert.match(html,/nunca se suman entre boletines/);
});
test('line axis labels thin out for many quarters; F1 monthly labels keep every position',()=>{
 const F=load();const xs=svg=>[...svg.matchAll(/<text class="sf-xlab" x="([\d.]+)"[^>]*>([^<]+)</g)].map(m=>[Number(m[1]),m[2]]);
 const cx=svg=>[...svg.matchAll(/<circle cx="([\d.]+)"/g)].map(m=>Number(m[1]));
 // F1: every month labelled, each label under its point (unchanged layout).
 const f1=F.render(pub);const stock=f1.slice(f1.indexOf('data-chart="f1-stock"'));const svg1=stock.slice(0,stock.indexOf('</svg>'));
 const l1=xs(svg1);assert.equal(l1.length,cx(svg1).length);assert.deepEqual(l1.map(l=>l[0]),cx(svg1));
 // 12 quarters 'T1 2024'…'T4 2026': every 2nd label, counted back from the last one (always shown).
 const rows=[];for(const y of [2024,2025,2026])for(const q of [1,2,3,4])rows.push({label:`T${q} ${y}`,value:1000+rows.length*7});
 const html=F.render({...pub,tabs:[{id:'t',label:'T',charts:[{id:'f4-trend',form:'line',digits:0,headline:'Casos',rows}],text:[]}]});
 const fig=html.slice(html.indexOf('<figure'));const svg=fig.slice(fig.indexOf('<svg'),fig.indexOf('</svg>'));const labs=xs(svg);
 assert.deepEqual(labs.map(l=>l[1]),['T2 2024','T4 2024','T2 2025','T4 2025','T2 2026','T4 2026']);
 for(let i=1;i<labs.length;i++)assert.ok(labs[i][0]-labs[i-1][0]>=7*6.6,`labels ${i} collide`);
 // 4 quarters fit: all labelled.
 const h4=F.render({...pub,tabs:[{id:'t',label:'T',charts:[{id:'x',form:'line',rows:rows.slice(-4)}],text:[]}]});
 assert.equal(xs(h4.slice(h4.indexOf('<figure'))).length,4);
});
test('bars never draw a negative value as a positive bar',()=>{
 const F=load();const html=F.render({...pub,tabs:[{id:'t',label:'T',charts:[{id:'b',form:'bars',unit:'%',digits:1,headline:'x',rows:[{label:'A',value:12.5},{label:'B',value:-8.1}]}],text:[]}]});
 assert.match(html,/−8,1|−8/);assert.doesNotMatch(html,/<title>B: 8,1%<\/title>/);
});
