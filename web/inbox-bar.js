// Shared "Tu bandeja" bar (Dirección 27-oct 23:13: proposal A on Chile and Global).
// Segmented read status, one compact filters dropdown that floats over the feed, and its label.
// No network, no storage: each page keeps its own persisted filter model.
(function(root){
 // Pendientes · Leídas · Todas: buttons [data-lane] inside `host`; counts go in their <span>.
 function syncLanes(host,mode,counts){if(!host)return;host.querySelectorAll('[data-lane]').forEach(b=>{const on=b.dataset.lane===mode;b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));const n=b.querySelector('span');if(n&&counts)n.textContent=counts[b.dataset.lane]??''})}
 function wireLanes(host,getMode,setMode){if(!host)return;host.querySelectorAll('[data-lane]').forEach(b=>b.onclick=()=>{if(getMode()===b.dataset.lane)return;setMode(b.dataset.lane);b.focus()})}
 // The dropdown closes on a click outside, on Escape (unless a dialog is open) and through close().
 function dropdown(details){
  const close=focus=>{if(!details||!details.open)return;details.open=false;if(focus)details.querySelector('summary')?.focus()};
  if(details&&typeof document!=='undefined'){
   document.addEventListener('pointerdown',e=>{if(details.open&&!details.contains(e.target))details.open=false});
   document.addEventListener('keydown',e=>{if(e.key==='Escape'&&details.open&&!document.querySelector('dialog[open]'))close(true)});
  }
  return {close,open(){if(details)details.open=true}};
 }
 // An empty selection names the whole set ("Todos los temas", "Todas las fuentes").
 function selectionLabel(names,allLabel,plural){const xs=names.filter(Boolean);return !xs.length?allLabel:xs.length===1?xs[0]:`${xs.length} ${plural}`}
 root.AlicantoBar={syncLanes,wireLanes,dropdown,selectionLabel};
})(typeof window!=='undefined'?window:globalThis);
