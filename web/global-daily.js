// "Al día afuera" (28-oct): daily headline + link rows from licensed/official sources (web/data/global_feed.json).
// Publisher title verbatim, attribution, date and a deterministic relevance line; no body, no AI, no Chile claim.
// Read state uses the shared AlicantoRead store with keys global-feed:<id>. The section stays hidden without data.
(function(){
 'use strict';
 const host=document.getElementById('globalDaily');if(!host)return;
 const esc=(s='')=>String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
 const day=raw=>new Intl.DateTimeFormat('es-CL',{day:'2-digit',month:'short',year:'numeric',timeZone:'America/Santiago'}).format(new Date(`${String(raw).slice(0,10)}T12:00:00Z`));
 const tick='<svg class="mini-icon" aria-hidden="true" viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5"></path></svg>';
 const SHOW=4;let items=[],expanded=false,payload=null;
 const key=id=>`global-feed:${id}`,isRead=x=>AlicantoRead.readSet.has(key(x.id));
 function today(){const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'America/Santiago',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()).map(x=>[x.type,x.value]));return Date.parse(`${p.year}-${p.month}-${p.day}T00:00:00Z`)}
 function age(raw){return Math.floor((today()-Date.parse(String(raw).slice(0,10)+'T00:00:00Z'))/86400000)}
 function safeUrl(u){try{const x=new URL(u);return x.protocol==='https:'?x.href:''}catch{return''}}
 // Authors in feed order; more than two -> the first two + "y otros" (full list in the link's accessible name).
 function authors(x){const b=(x.bylines||[]).filter(Boolean);return b.length>2?`${b.slice(0,2).join(', ')} y otros`:b.join(', ')}
 function source(x){const a=authors(x);return a?`${x.source_label} (${a})`:x.source_label}
 function license(x){const u=safeUrl(x.rights_basis?.license_url||'');return u?` · <a class="lic" href="${esc(u)}" target="_blank" rel="noopener license">${esc(x.rights_basis.license_label||'Licencia')}</a>`:''}
 function accessibleName(x){const b=(x.bylines||[]).filter(Boolean);return `${x.title}. ${x.source_label}${b.length?`, autores: ${b.join(', ')}`:''}. Abre en otra pestaña.`}
 function row(x){const read=isRead(x),label=read?'Marcar como no leído':'Marcar como leído',url=safeUrl(x.url);
  return `<article class="signal item daily-item ${read?'read':''}" id="daily-${esc(x.id)}" data-daily="${esc(x.id)}"><button type="button" class="dotbtn ${read?'done':''}" data-daily-read="${esc(x.id)}" aria-label="${label}: ${esc(x.title)}" title="${label}">${read?tick:'<span class="unread-dot"></span>'}</button><div class="item-body"><h2><a class="title-open" href="${esc(url)}" target="_blank" rel="noopener" data-daily-open="${esc(x.id)}" title="${esc(x.summary_es||'')}" aria-label="${esc(accessibleName(x))}">${esc(x.title)} <span class="ext" aria-hidden="true">↗</span></a></h2><div class="card-meta"><span class="meta-text"><span class="eyebrow">Titular</span> · ${esc(source(x))} · ${day(x.published_at)}${x.tags_es?.length?` · ${esc(x.tags_es.join(' · '))}`:''}${license(x)}</span></div></div></article>`}
 function render(){
  const unread=items.filter(x=>!isRead(x)).length,shown=expanded?items:items.slice(0,SHOW),f=payload.freshness||{};
  document.getElementById('globalDailyMetrics').textContent=`${items.length} titulares en ${payload.window_days||14} días · no leídos ${unread}${f.status==='stale'&&f.newest_published_at?` · sin titulares nuevos desde ${day(f.newest_published_at)}`:''}`;
  const rows=document.getElementById('globalDailyRows');rows.innerHTML=shown.map(row).join('');
  const more=document.getElementById('globalDailyMore');more.hidden=items.length<=SHOW;more.textContent=expanded?'Ver menos':`Ver ${items.length-SHOW} titulares más`;more.setAttribute('aria-expanded',String(expanded));
  rows.querySelectorAll('[data-daily-read]').forEach(b=>b.onclick=async()=>{const id=b.dataset.dailyRead,x=items.find(i=>i.id===id);await AlicantoRead.set(key(id),!isRead(x));render();document.querySelector(`[data-daily-read="${CSS.escape(id)}"]`)?.focus()});
  rows.querySelectorAll('[data-daily-open]').forEach(a=>a.addEventListener('click',()=>{AlicantoRead.set(key(a.dataset.dailyOpen),true).then(render)}));
 }
 document.getElementById('globalDailyMore').onclick=()=>{expanded=!expanded;render()};
 fetch('data/global_feed.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(async d=>{
  if(!d||d.enabled!==true||d.content_use!=='metadata_and_link_only')return;
  await AlicantoRead.ready;payload=d;const w=Number(d.window_days)||14;
  items=(d.items||[]).filter(x=>x&&x.id&&x.title&&safeUrl(x.url)&&x.published_at&&age(x.published_at)>=0&&age(x.published_at)<w)
   .sort((a,b)=>String(b.published_at).localeCompare(String(a.published_at))||(b.priority||0)-(a.priority||0));
  if(!items.length)return;host.hidden=false;render();AlicantoRead.subscribe(()=>render());
 }).catch(()=>{});
 window.AlicantoGlobalDaily={rowHtml:row};
})();
