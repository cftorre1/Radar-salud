// Datos (Dirección, 3-nov-2026): a permanent shelf with the latest published ficha of each statistics family.
// Everything shown comes from data/datos.json, which the export step copies from the published, verified fichas
// (headline and KPI strings verbatim); this page never computes a figure. Each row opens the ficha in the Chile
// feed (same piece id, same read state in IndexedDB), so opening it in either place clears "Nuevo" in both.
(function(root){
 'use strict';
 const VIEW_KEY='alicanto_datos_view',VIEWS=['recientes','grupo'];
 const esc=(s='')=>String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
 function loadView(){try{const v=root.localStorage?.getItem(VIEW_KEY);return VIEWS.includes(v)?v:'recientes'}catch{return 'recientes'}}
 function saveView(v){try{root.localStorage?.setItem(VIEW_KEY,v)}catch{}}
 const isLive=f=>f.state==='live'&&f.piece_id;
 // Recientes: live families by their latest verification day, newest first; then pending/planned in registry order.
 function recientes(families){
  const live=families.filter(isLive).sort((a,b)=>String(b.updated_on||'').localeCompare(String(a.updated_on||''))||a.order-b.order);
  const rest=families.filter(f=>!isLive(f)).sort((a,b)=>a.order-b.order);
  return [...live,...rest];
 }
 // Por grupo: the registry's groups in order; inside each, live families first (newest first), then the rest.
 function byGroup(data){
  const all=recientes(data.families||[]);
  return (data.groups||[]).map(g=>({key:g.key,label:g.label,families:all.filter(f=>f.group===g.key)})).filter(g=>g.families.length);
 }
 function href(f){return `index.html?abrir=1&desde=datos#sig-${f.piece_id}`}
 function row(f,isNew){
  if(!isLive(f)){
   const tag=f.state==='pending'?'en verificación':'pronto';
   return `<div class="dx-row dx-soon" data-family="${esc(f.family)}"><div class="dx-kick"><span>${esc(f.label)}</span><span class="dx-tag">${tag}</span></div></div>`;
  }
  const kpis=(f.kpis||[]).slice(0,2).map(k=>`<div class="dx-kpi"><span class="dx-v">${esc(k.value)}</span><span class="dx-l">${esc(k.label)}</span></div>`).join('');
  const status=f.status==='updating'?'<span class="dx-st dx-up">Actualizándose</span>':'<span class="dx-st dx-ok">Vigente</span>';
  return `<a class="dx-row${isNew?' dx-new':''}" href="${esc(href(f))}" data-family="${esc(f.family)}" data-piece="${esc(f.piece_id)}"><div class="dx-kick"><span>${esc(f.label)}${f.cadence?` · ${esc(f.cadence)}`:''}</span>${isNew?'<span class="dx-badge">Nuevo</span>':''}</div><h3 class="dx-title">${esc(f.headline)}</h3>${kpis?`<div class="dx-kpis">${kpis}</div>`:''}<div class="dx-meta"><span>Datos a ${esc(f.period_label)} · ${esc(f.source)}</span>${status}</div></a>`;
 }
 function render(data,view,readSet){
  const fresh=f=>isLive(f)&&!(readSet&&readSet.has(f.piece_id));
  const list=fs=>`<div class="dx-list">${fs.map(f=>row(f,fresh(f))).join('')}</div>`;
  if(!(data.families||[]).length)return '<p class="datos-empty">Aún no hay fichas publicadas.</p>';
  if(view==='grupo')return byGroup(data).map(g=>`<section class="dx-group" aria-labelledby="dx-g-${esc(g.key)}"><h2 class="dx-sec" id="dx-g-${esc(g.key)}">${esc(g.label)}</h2>${list(g.families)}</section>`).join('');
  return list(recientes(data.families));
 }
 const api={recientes,byGroup,render,row,href,loadView,saveView,VIEW_KEY};
 root.AlicantoDatos=api;
 if(typeof document==='undefined'||!document.getElementById('datosList'))return;
 const host=document.getElementById('datosList'),toggle=document.getElementById('datosView');
 const Read=root.AlicantoRead;
 let data=null,view=loadView();
 function sync(){toggle.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)));host.dataset.view=view}
 function draw(){sync();if(data)host.innerHTML=render(data,view,Read?Read.readSet:null)}
 toggle.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{if(view===b.dataset.view)return;view=b.dataset.view;saveView(view);draw()});
 sync();
 if(Read)Read.subscribe(()=>draw());
 fetch('data/datos.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('datos');return r.json()}).then(async d=>{if(Read)await Read.ready;data=d;draw()}).catch(()=>{host.innerHTML='<p class="datos-empty">No se pudieron cargar los datos.</p>'});
})(typeof window==='undefined'?globalThis:window);
