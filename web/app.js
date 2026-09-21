const esc = (s='') => String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
function card(s){
  return `<article class="signal"><div class="top"><span class="score">${esc(s.personal_score ?? s.radar_score ?? '')}</span><div><h2>${esc(s.title)}</h2>
  ${s.what_happened?`<p><span class="label">Qué pasó:</span> ${esc(s.what_happened)}</p>`:''}
  ${s.why_it_matters?`<p><span class="label">Por qué importa:</span> ${esc(s.why_it_matters)}</p>`:''}
  <div class="source">Fuente: ${esc(s.source_name||'')} · Confianza ${esc(s.confidence_score||'')}${s.source_url?` · <a href="${esc(s.source_url)}" target="_blank" rel="noopener">Ver fuente original ↗</a>`:''}</div></div></div></article>`;
}
fetch('data/radar_today.json',{cache:'no-store'}).then(r=>r.json()).then(d=>{
 document.getElementById('meta').innerHTML=`<span>${esc(d.date)}</span><span>${esc(d.profile)}</span><span>Actualizado: ${esc(d.generated_at)}</span>`;
 const local=(d.signals||[]).filter(x=>x.category!=='Radar Mundo'); const world=(d.signals||[]).filter(x=>x.category==='Radar Mundo');
 document.getElementById('local').innerHTML=local.length?local.map(card).join(''):'<div class="empty">No hay señales locales publicables hoy.</div>';
 document.getElementById('world').innerHTML=world.length?world.map(card).join(''):'<div class="empty">No hay señales internacionales publicables hoy.</div>';
}).catch(e=>{document.getElementById('local').innerHTML='<div class="empty">Todavía no se generó el Radar de hoy.</div>';});
