const esc = (s='') => String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

function relevanceLabel(score){
  const n=Number(score||0);
  if(n>=85) return {label:'Esencial', cls:'essential'};
  if(n>=65) return {label:'Relevante', cls:'relevant'};
  return {label:'Contexto', cls:'context'};
}
function fmtDate(raw){
  if(!raw) return '';
  const d=new Date(raw);
  if(Number.isNaN(d.getTime())) return esc(raw);
  return new Intl.DateTimeFormat('es-CL',{day:'2-digit',month:'short',year:'numeric'}).format(d);
}
function fmtUpdated(raw){
  if(!raw) return '';
  const d=new Date(raw);
  if(Number.isNaN(d.getTime())) return esc(raw);
  return new Intl.DateTimeFormat('es-CL',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'America/Santiago'}).format(d);
}
function card(s){
  const rel=relevanceLabel(s.personal_score ?? s.radar_score ?? 0);
  const grouped=s.grouped_count>1?`<span class="grouped">${esc(s.grouped_count)} publicaciones conectadas</span>`:'';
  return `<article class="signal"><div class="top"><span class="priority ${rel.cls}">${rel.label}</span><div class="body"><div class="kicker">${esc(s.category||'')} ${grouped}</div><h2>${esc(s.title)}</h2>
  ${s.what_happened?`<p><span class="label">Qué pasó:</span> ${esc(s.what_happened)}</p>`:''}
  ${s.why_it_matters?`<p><span class="label">Por qué importa:</span> ${esc(s.why_it_matters)}</p>`:''}
  <div class="source">${s.event_date?`${fmtDate(s.event_date)} · `:''}Fuente: ${esc(s.source_name||'')} · Confianza ${esc(s.confidence_score||'')}${s.source_url?` · <a href="${esc(s.source_url)}" target="_blank" rel="noopener">Ver fuente original ↗</a>`:''}</div></div></div></article>`;
}
fetch('data/radar_today.json',{cache:'no-store'}).then(r=>r.json()).then(d=>{
 document.getElementById('meta').innerHTML=`<span>${fmtDate(d.date)}</span><span>${esc(d.profile)}</span><span>Actualizado ${fmtUpdated(d.generated_at)}</span>`;
 const local=(d.signals||[]).filter(x=>x.category!=='Radar Mundo'); const world=(d.signals||[]).filter(x=>x.category==='Radar Mundo');
 document.getElementById('count').textContent = local.length ? `${local.length} señales seleccionadas` : 'Sin señales nuevas';
 document.getElementById('local').innerHTML=local.length?local.map(card).join(''):'<div class="empty">No hay señales locales publicables en esta actualización.</div>';
 const worldSection=document.querySelector('.world');
 if(world.length){ worldSection.hidden=false; document.getElementById('world').innerHTML=world.map(card).join(''); }
 else { worldSection.hidden=true; }
}).catch(e=>{document.getElementById('local').innerHTML='<div class="empty">Todavía no se generó el Radar de hoy.</div>';});
