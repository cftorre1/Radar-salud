// Statistics ficha renderer (web/stats-ficha.js): layout only, numbers come from the evidence package.
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
function load(){const c={Intl,URL,CSS:{escape:s=>s}};c.globalThis=c;vm.createContext(c);vm.runInContext(fs.readFileSync('web/stats-ficha.js','utf8'),c);return c.AlicantoFicha}
const live=JSON.parse(fs.readFileSync('data/stats_fichas/live/f1_cartera.json','utf8'));
const pub={...live};delete pub.evidence;

test('ficha renders the Insight A order with tabs, KPI strip and data tables',()=>{
 const html=load().render(pub,{shareId:'sig-stats-ficha:F1:2026-08',shareUrl:'data/fichas/f1_cartera.html'});
 const order=['sf-kicker','sf-headline','sf-dek','sf-share','sf-kpis','sf-tabs','sf-watch','sf-notes'];
 // Dirección 28-oct 08:20: no separate 'Qué muestran los datos'; notes and sources behind one collapsed toggle.
 assert.doesNotMatch(html,/class="sf-facts"/);assert.match(html,/<details class="sf-notes"><summary>Notas y fuentes<\/summary>/);
 assert.equal((html.match(/<li><strong>/g)||[]).length,2);assert.doesNotMatch(html,/Por qué importa/);
 const at=order.map(k=>html.indexOf(k));assert.ok(at.every(i=>i>=0),JSON.stringify(at));assert.deepEqual([...at].sort((a,b)=>a-b),at);
 assert.match(html,/id="detailTitle"/);assert.match(html,/2\.486\.683/);assert.match(html,/agosto 2026/);
 assert.equal((html.match(/role="tab"/g)||[]).length,5);assert.equal((html.match(/role="tabpanel"/g)||[]).length,5);
 assert.equal((html.match(/aria-selected="true"/g)||[]).length,1);
 assert.equal((html.match(/<figure class="sf-chart"/g)||[]).length,8);
 assert.equal((html.match(/Ver datos del gráfico/g)||[]).length,8);
 assert.match(html,/role="img" aria-label="Cambio mensual de beneficiarios[^"]*Ago −814/);
 assert.match(html,/Compartir informe/);assert.match(html,/data-share-url="data\/fichas\/f1_cartera\.html"/);
 assert.match(html,/sha256 [0-9a-f]{12}…/);assert.doesNotMatch(html,/Lectura Alicanto<\/h3>/);
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
for(const [slug,tabs,charts,kpis] of [['f4_ges',['Totales','Top problemas','Fonasa vs Isapre','Tendencia trimestral'],5,4],
                                      ['f6_prestadores',['Acreditación','Mediación','Reclamos','RNPI'],3,4]]){
 test(`${slug}: themed tabs, KPI strip, collapsed notes and Option-B share`,()=>{
  const card=JSON.parse(fs.readFileSync(`tests/fixtures/stats_fichas/${slug}.card.json`,'utf8'));const f=card.stats_ficha;
  assert.equal(f.evidence,undefined);assert.equal(f.status,'PASS');
  const html=load().render(f,{shareId:`sig-${card.piece_id}`,shareUrl:card.share_url});
  const order=['sf-kicker','sf-headline','sf-dek','sf-share','sf-kpis','sf-tabs','sf-watch','sf-notes'];
  const at=order.map(k=>html.indexOf(k));assert.ok(at.every(i=>i>=0),JSON.stringify(at));assert.deepEqual([...at].sort((a,b)=>a-b),at);
  assert.deepEqual([...html.matchAll(/role="tab"[^>]*>([^<]+)/g)].map(m=>m[1]),tabs);
  assert.equal((html.match(/<figure class="sf-chart"/g)||[]).length,charts);
  assert.equal((html.match(/class="sf-kpi"/g)||[]).length,kpis);
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
 const svg=html.slice(html.indexOf('<svg'),html.indexOf('</svg>'));const labs=xs(svg);
 assert.deepEqual(labs.map(l=>l[1]),['T2 2024','T4 2024','T2 2025','T4 2025','T2 2026','T4 2026']);
 for(let i=1;i<labs.length;i++)assert.ok(labs[i][0]-labs[i-1][0]>=7*6.6,`labels ${i} collide`);
 // 4 quarters fit: all labelled.
 const h4=F.render({...pub,tabs:[{id:'t',label:'T',charts:[{id:'x',form:'line',rows:rows.slice(-4)}],text:[]}]});
 assert.equal(xs(h4.slice(h4.indexOf('<svg'))).length,4);
});
test('bars never draw a negative value as a positive bar',()=>{
 const F=load();const html=F.render({...pub,tabs:[{id:'t',label:'T',charts:[{id:'b',form:'bars',unit:'%',digits:1,headline:'x',rows:[{label:'A',value:12.5},{label:'B',value:-8.1}]}],text:[]}]});
 assert.match(html,/−8,1|−8/);assert.doesNotMatch(html,/<title>B: 8,1%<\/title>/);
});
