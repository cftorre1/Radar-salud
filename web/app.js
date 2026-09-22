const esc=(s='')=>String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
let allSignals=[],activeType='Todos',activeScope='Todos',sortMode='unread',periodDays=60;
const readSet=new Set(JSON.parse(localStorage.getItem('alicanto_read')||localStorage.getItem('radar_read')||'[]'));
function idFor(s){return btoa(unescape(encodeURIComponent((s.source_url||'')+'|'+(s.title||'')))).slice(0,120)}
function isRead(s){return readSet.has(idFor(s))}
function markRead(s){const id=idFor(s);if(readSet.has(id))readSet.delete(id);else readSet.add(id);localStorage.setItem('alicanto_read',JSON.stringify([...readSet]));draw()}
function rel(score){const n=Number(score||0);if(n>=85)return{label:'Esencial',cls:'essential'};if(n>=65)return{label:'Relevante',cls:'relevant'};return{label:'Contexto',cls:'context'}}
function arr(x){return Array.isArray(x)?x:[]}
function typeTags(s){return arr(s.signal_types)} function scopeTags(s){return arr(s.scopes)}
function fmtDate(raw){if(!raw)return'';const d=new Date(raw);if(Number.isNaN(d.getTime()))return esc(raw);return new Intl.DateTimeFormat('es-CL',{day:'2-digit',month:'short',year:'numeric',timeZone:'America/Santiago'}).format(d)}
function fmtUpdated(raw){const d=new Date(raw);if(Number.isNaN(d.getTime()))return'';const t=new Intl.DateTimeFormat('es-CL',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'America/Santiago'}).format(d);return`Actualizado ${fmtDate(raw)}, ${t}`}
function tagHtml(s){return [...typeTags(s).slice(0,2).map(x=>`<span class="tag">${esc(x)}</span>`),...scopeTags(s).slice(0,3).map(x=>`<span class="tag scope">${esc(x)}</span>`)].join('')}
function listBlock(title,xs){return xs.length?`<div class="intel"><div class="intel-title">${title}</div><ul>${xs.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}
function related(title,sources){if(!sources.length)return'';return`<details class="related"><summary>${title}</summary>${sources.map(src=>`<div class="related-item"><div class="related-title">${esc(src.title||'Fuente')}</div>${src.summary?`<div class="related-desc">${esc(src.summary)}</div>`:''}${src.event_date?`<div class="related-desc">Fecha de publicación: ${fmtDate(src.event_date)}</div>`:''}${src.url?`<a href="${esc(src.url)}" target="_blank" rel="noopener">Ver fuente ↗</a>`:''}</div>`).join('')}</details>`}
function card(s){const r=rel(s.radar_score),rd=isRead(s);return`<article class="signal ${rd?'read':''}"><div class="cardhead"><div class="tagrow"><span class="priority ${r.cls}">${r.label}</span>${tagHtml(s)}</div><button class="readbtn ${rd?'done':''}" data-read="${esc(idFor(s))}">${rd?'↺ Marcar no leído':'✓ Marcar como leído'}</button></div><div class="body"><h2>${esc(s.title)}</h2>${s.what_happened?`<p><span class="label">Qué pasó:</span> ${esc(s.what_happened)}</p>`:''}${s.why_it_matters?`<p><span class="label">Por qué importa:</span> ${esc(s.why_it_matters)}</p>`:''}${typeTags(s).includes('Normativa')?`<p><span class="label">Vigencia:</span> ${esc(s.validity_text||'No identificada automáticamente')}</p>`:''}${listBlock('Puntos clave',arr(s.key_points).slice(0,3))}${listBlock('Aspectos a revisar',arr(s.risk_notes).slice(0,3))}${listBlock('Insights de datos',arr(s.data_insights).slice(0,3))}<div class="source">${s.event_date?`Fecha de publicación: ${fmtDate(s.event_date)} · `:''}Fuente: ${esc(s.source_name||'')}${s.source_url?` · <a href="${esc(s.source_url)}" target="_blank" rel="noopener">Ver fuente original ↗</a>`:''}</div>${related(`Ver ${arr(s.related_norms).length} normas relacionadas`,arr(s.related_norms))}${related(`Ver ${arr(s.related_sources).length} fuentes relacionadas`,arr(s.related_sources))}</div></article>`}
function dateVal(s){return new Date(s.event_date||0).getTime()||0}
function ageDays(s){return Math.max(0,(Date.now()-dateVal(s))/86400000)}
function within(s,days){return s.event_date&&ageDays(s)<=days+1}
function freshness(s){const a=ageDays(s);if(a<=2)return 100;if(a<=7)return 85;if(a<=14)return 70;if(a<=30)return 45;if(a<=60)return 25;return 10}
function strategicScore(s){
 const radar=Number(s.radar_score||0),action=Number(s.actionability_score||radar),scope=Number(s.scope_score||radar);
 const impact=Math.max(Number(s.regulatory_impact_score||0),Number(s.economic_impact_score||0),Number(s.editorial_relevance||0));
 return .55*radar+.15*action+.10*scope+.10*impact+.10*freshness(s);
}
function strategicTop(pool,n=3){
 let candidates=pool.filter(s=>!isRead(s)).map(s=>({s,base:strategicScore(s)})),picked=[];
 while(candidates.length&&picked.length<n){
   let best=null,bestScore=-Infinity;
   for(const c of candidates){
     const sameSource=picked.filter(x=>x.source_name===c.s.source_name).length;
     const sameType=picked.some(x=>typeTags(x)[0]&&typeTags(x)[0]===typeTags(c.s)[0]);
     const adjusted=c.base-(sameSource*9)-(sameType?3:0);
     if(adjusted>bestScore){bestScore=adjusted;best=c;}
   }
   picked.push(best.s);candidates=candidates.filter(x=>x!==best);
 }
 return picked;
}
function poolForPeriod(){
 let pool=allSignals.filter(s=>within(s,periodDays));
 if(pool.length<5){
   const ids=new Set(pool.map(idFor));
   pool=[...pool,...allSignals.filter(s=>!ids.has(idFor(s))).sort((a,b)=>dateVal(b)-dateVal(a)).slice(0,5-pool.length)];
 }
 return pool;
}
function visible(){
 let out=poolForPeriod().filter(s=>(activeType==='Todos'||typeTags(s).includes(activeType))&&(activeScope==='Todos'||scopeTags(s).includes(activeScope)));
 if(sortMode==='relevance')out.sort((a,b)=>strategicScore(b)-strategicScore(a));
 else if(sortMode==='date')out.sort((a,b)=>dateVal(b)-dateVal(a));
 else out.sort((a,b)=>(isRead(a)-isRead(b))||dateVal(b)-dateVal(a)||strategicScore(b)-strategicScore(a));
 return out;
}
function brief(v){
 const top=strategicTop(v,3),unread=v.filter(s=>!isRead(s)).length;
 document.getElementById('brief').innerHTML=`<section class="brief"><h2>Lo importante en 60 segundos</h2><p><strong>${unread}</strong> hallazgos no leídos en los últimos ${periodDays} días.</p>${top.length?top.map((s,i)=>`<p><span class="briefnum">${i+1}</span> ${esc(s.title)}</p>`).join(''):'<p class="muted">Estás al día.</p>'}<p class="muted">Priorizado por relevancia estratégica, impacto, frescura y diversidad de señales.</p></section>`;
}
function draw(){const v=visible();brief(v);document.getElementById('count').textContent=`${v.length} hallazgos`;document.getElementById('local').innerHTML=v.map(card).join('');document.querySelectorAll('[data-read]').forEach(b=>b.onclick=()=>{const s=v.find(x=>idFor(x)===b.dataset.read);if(s)markRead(s)})}
function chips(id,values,current,setter){document.getElementById(id).innerHTML=values.map(v=>`<button class="chip ${v===current?'active':''}" data-v="${esc(v)}">${esc(v)}</button>`).join('');document.querySelectorAll(`#${id} .chip`).forEach(b=>b.onclick=()=>{setter(b.dataset.v);renderFilters();draw()})}
function renderFilters(){chips('typeFilters',['Todos',...new Set(allSignals.flatMap(typeTags))],activeType,v=>activeType=v);chips('scopeFilters',['Todos',...new Set(allSignals.flatMap(scopeTags))],activeScope,v=>activeScope=v)}
fetch('data/radar_today.json',{cache:'no-store'}).then(r=>r.json()).then(d=>{document.getElementById('meta').textContent=fmtUpdated(d.generated_at);allSignals=d.signals||[];renderFilters();draw();document.getElementById('period').onchange=e=>{periodDays=Number(e.target.value);draw()};document.getElementById('sort').onchange=e=>{sortMode=e.target.value;draw()}}).catch(()=>document.getElementById('local').innerHTML='<div>No se pudo cargar Alicanto.</div>');
