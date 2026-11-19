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
