// Datos (Dirección, 3-nov-2026): a permanent shelf with the latest published ficha of each statistics family.
// Everything shown comes from data/datos.json, which the export step copies from the published, verified fichas;
// this page never computes a figure. Since 10-nov-2026 each live family is a data card (data-card.js, the same
// renderer as the Chile feed): dot, «Datos <período> · <cadencia>», descriptive title, numbered topic index (each topic
// opens the ficha at that topic), date line and «Compartir». Same piece id and read store (IndexedDB) as Chile, so a
// read in either place shows in both.
(function(root){
 'use strict';
 const VIEW_KEY='alicanto_datos_view',VIEWS=['recientes','grupo'],BASE='index.html?abrir=1&desde=datos';
 const esc=(s='')=>String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
 function loadView(){try{const v=root.localStorage?.getItem(VIEW_KEY);return VIEWS.includes(v)?v:'recientes'}catch{return 'recientes'}}
 function saveView(v){try{root.localStorage?.setItem(VIEW_KEY,v)}catch{}}
 const isLive=f=>f.state==='live'&&f.piece_id;
 // Recientes: live families by their latest verification day, newest first; then pending/planned in registry order.
 // Dirección 11-nov-2026: as in Al día, what was read goes down — unread first, then read, each newest first.
 function recientes(families,readSet){
  const rd=f=>readSet&&readSet.has(f.piece_id)?1:0;
  const live=families.filter(isLive).sort((a,b)=>rd(a)-rd(b)||String(b.updated_on||'').localeCompare(String(a.updated_on||''))||a.order-b.order);
  const rest=families.filter(f=>!isLive(f)).sort((a,b)=>a.order-b.order);
  return [...live,...rest];
 }
 // Por grupo: the registry's groups in order; inside each, live families first (newest first), then the rest.
 function byGroup(data,readSet){
  const all=recientes(data.families||[],readSet);
  return (data.groups||[]).map(g=>({key:g.key,label:g.label,families:all.filter(f=>f.group===g.key&&isLive(f))})).filter(g=>g.families.length);
 }
 function href(f){return `${BASE}#sig-${f.piece_id}`}
 function card(f,read){return root.AlicantoDataCard.render(root.AlicantoDataCard.model(f),{read,base:BASE})}
 function row(f,read){
  // Dirección 11-nov-2026: families without a published ficha are not shown («pronto» panels removed).
  if(!isLive(f))return '';
  return `<article class="dx-item" data-family="${esc(f.family)}" data-piece="${esc(f.piece_id)}">${card(f,read)}</article>`;
 }
 function render(data,view,readSet){
  const read=f=>Boolean(readSet&&readSet.has(f.piece_id));
  const list=fs=>`<div class="dx-list">${fs.map(f=>row(f,read(f))).join('')}</div>`;
  if(!(data.families||[]).some(isLive))return '<p class="datos-empty">Aún no hay fichas publicadas.</p>';
  if(view==='grupo')return byGroup(data,readSet).map(g=>`<section class="dx-group" aria-labelledby="dx-g-${esc(g.key)}"><h2 class="dx-sec" id="dx-g-${esc(g.key)}">${esc(g.label)}</h2>${list(g.families)}</section>`).join('');
  return list(recientes(data.families,readSet).filter(isLive));
 }
 const api={recientes,byGroup,render,row,card,href,loadView,saveView,VIEW_KEY,BASE};
 root.AlicantoDatos=api;
 if(typeof document==='undefined'||!document.getElementById('datosList'))return;
 const host=document.getElementById('datosList'),toggle=document.getElementById('datosView');
 const Read=root.AlicantoRead,Bar=root.AlicantoBar;
 let data=null,view=loadView();
 const status=m=>{const el=document.getElementById('readStatus');if(el)el.textContent=m};
 function sync(){toggle.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)));host.dataset.view=view}
 function draw(){sync();if(data)host.innerHTML=render(data,view,Read?Read.readSet:null)}
 toggle.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{if(view===b.dataset.view)return;view=b.dataset.view;saveView(view);draw()});
 // The dot is the read toggle, as in Chile; «Compartir» uses the Chile share path (inbox-bar.js shareCard).
 host.addEventListener('click',async e=>{
  const dot=e.target.closest('[data-read]');
  if(dot&&Read){const id=dot.dataset.read,value=!Read.readSet.has(id);await Read.set(id,value);status(value?'Marcado como leído.':'Marcado como no leído.');host.querySelector(`[data-read="${CSS.escape(id)}"]`)?.focus();return}
  const share=e.target.closest('[data-share]');if(share&&Bar)Bar.shareCard(share);
 });
 sync();
 if(Read)Read.subscribe(()=>draw());
 fetch('data/datos.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('datos');return r.json()}).then(async d=>{if(Read)await Read.ready;data=d;draw()}).catch(()=>{host.innerHTML='<p class="datos-empty">No se pudieron cargar los datos.</p>'});
})(typeof window==='undefined'?globalThis:window);
