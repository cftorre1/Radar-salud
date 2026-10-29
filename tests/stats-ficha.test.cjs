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
