const {test}=require('node:test');const assert=require('node:assert/strict');
require('../web/listen.js');const L=globalThis.AlicantoListen;
// «Escuchar pendientes», phase 1 (Dirección 19-nov-2026): podcast-style script, no AI, device voice.
const items=[{id:'a',kind:'noticia',title:'Res. exenta E 5.558/2026 · Instruye el envío de un Plan',what:'El ISP dictó la Resolución E 5.216, de 2026. Segunda frase. Tercera frase.',topic:'farma'},
 {id:'b',kind:'noticia',title:'Circular IF/N°540 · Actualiza el Formato Único',what:'La SIS actualizó el formato con 12,5% más campos.',topic:'normativa'},
 {id:'c',kind:'noticia',title:'Bupa vende clínicas',what:'Texto del medio que no se lee.',paywalled:true,topic:'prestadores'},
 {id:'d',kind:'datos',title:'Licencias médicas por Isapre',period:'julio–septiembre 2026',topic:'datos'}];
test('script has a podcast intro, a transition per topic, every item once and an outro',()=>{
  const r=L.buildScript(items,{mode:'corto',hour:8,day:0});
  assert.match(r.segments[0].text,/^Buenos días\. Bienvenido a Alicanto al oído/);
  assert.deepEqual(r.segments.filter(s=>s.id).map(s=>s.id),['a','b','c','d']);
  assert.match(r.segments[3].text,/^Se viene una noticia importante para los prestadores\./);
  assert.match(r.segments.at(-1).text,/marcado como leído.*voz sintética/);
});
test('the ear version expands shorthand and never splits inside a number',()=>{
  assert.equal(L.speakable('Circular IF/N°540 · Actualiza'),'Circular I F número 540. Actualiza.');
  assert.equal(L.sentences('Dictó la Resolución E 5.216, de 2026. Otra.',1),'Dictó la Resolución E 5.216, de 2026.');
  const d=L.buildScript([items[3]],{}).segments[1].text;assert.match(d,/Con datos de julio a septiembre de 2026\./);
});
test('paywalled cards say only the title, never the outlet text',()=>{
  const c=L.buildScript([items[2]],{}).segments[1].text;assert.doesNotMatch(c,/Texto del medio/);assert.match(c,/muro de pago/);
});
test('short mode fits its time budget and tells how many remain',()=>{
  const many=Array.from({length:80},(_,i)=>({id:'x'+i,kind:'noticia',title:'Título número '+i,what:'Una frase de veinte palabras '.repeat(4),topic:'isapres'}));
  const r=L.buildScript(many,{mode:'corto'});assert.ok(r.minutes<=10&&r.included<80&&r.left===80-r.included);
  assert.match(r.segments.at(-1).text,new RegExp(`Te quedan ${r.left} pendientes`));
  const e=L.buildScript(many,{mode:'extenso'});assert.ok(e.included>r.included&&e.minutes<=20);
});
test('ear text: abbreviations, dates, money, boletín and press suffix (review of #219)',()=>{
  assert.equal(L.speakable(L.sentences('Aprobó el D.S. Nº 30. Otra frase.',1)),'Aprobó el decreto supremo número 30.');
  assert.equal(L.speakable('Rige desde el 19/11/2026 hasta 2026-2028'),'Rige desde el 19 de noviembre de 2026 hasta 2026 a 2028.');
  assert.equal(L.speakable('Inversión de USD 45 millones en 10.576 m²'),'Inversión de 45 millones de dólares en 10.576 metros cuadrados.');
  assert.equal(L.speakable('El proyecto (Boletín N° 18255-31) avanza'),'El proyecto avanza.');
  assert.equal(L.speakable('Clínica inauguró instalaciones - Andes Salud'),'Clínica inauguró instalaciones.');
  assert.equal(L.speakable('Suseso Contigo y la Superintendencia de Salud (SIS)'),'Suseso Contigo y la Superintendencia de Salud.');
});
test('important items are chosen first; the rest in feed order (review of #219)',()=>{
  const many=Array.from({length:60},(_,i)=>({id:'x'+i,kind:'noticia',title:'Título '+i,what:'Una frase larga '+'con muchas palabras '.repeat(12)+'.',topic:i%2?'isapres':'farma',important:i===55}));
  const r=L.buildScript(many,{mode:'corto'});const ids=r.segments.filter(s=>s.id).map(s=>s.id);
  assert.ok(ids.includes('x55')&&ids.includes('x0')&&!ids.includes('x54'));
});
test('a cancelled utterance never marks or advances (Safari fires end on cancel)',async()=>{
  const said=[],done=[];let cur=null;
  globalThis.SpeechSynthesisUtterance=function(t){this.text=t};
  globalThis.speechSynthesis={speak(u){cur=u;said.push(u.text)},cancel(){const u=cur;cur=null;u&&u.onend&&u.onend()},getVoices(){return[]}};
  globalThis.document={addEventListener(){}};globalThis.navigator={};
  const P=L.Player({onItemDone:id=>done.push(id),onState(){}});
  P.play({segments:[{id:null,text:'intro'},{id:'a',text:'A'},{id:'b',text:'B'},{id:null,text:'fin'}]});
  cur.onend();// intro finished
  P.next();// skip «A» while it plays: Safari fires its end on cancel
  assert.deepEqual(done,[]);assert.equal(said.at(-1),'B');
  cur.onend();assert.deepEqual(done,['b']);
});
