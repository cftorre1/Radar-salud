// Global Intelligence (Dirección 27-oct 23:13; 28-oct 08:20): ONE inbox. Alicanto's research themes
// (data/global_themes.json) and the daily headlines from licensed or official sources (data/global_feed.json,
// formerly "Al día afuera") share one list ordered by date, newest first, like Chile: same bar, period options,
// rows with Ver ficha › · Fuente original ↗ · Compartir (opción B), inline undo and ficha header (inbox-bar.js).
// Read keys stay global:<theme_id> (shared with the Home teaser) and global-feed:<headline_id>.
// Editorial rule (punto 5): a headline ficha shows only captured data; a missing field hides its section.
// Feed contract (schema_version 2, 28-oct): 90-day window; description (publisher's own summary, verbatim, or null),
// description_truncated (ends with "…"), also_reported_by [{source,source_label,url}] and rights_basis
// {basis,attribution,license_label}; OGL v3.0 items carry the licence's attribution statement.
const esc=(s='')=>String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const dateText=raw=>raw?new Intl.DateTimeFormat('es-CL',{day:'2-digit',month:'short',year:'numeric',timeZone:'America/Santiago'}).format(new Date(`${String(raw).slice(0,10)}T12:00:00Z`)):'Fecha no verificada';
function stored(key,fallback){try{return JSON.parse(localStorage.getItem(key))??fallback}catch{return fallback}}
function globalKey(id){return `global:${id}`}
function feedKey(id){return `global-feed:${id}`}
const readSet=AlicantoRead.readSet;
// Same period options as Chile; the Global window is 90 days. A saved longer period (1 año, todo) becomes 90 días.
const PERIODS=['last','7','14','30','60','90'],WINDOW_DAYS=90,FEED_SCHEMA=2,OGL_URL='https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/';
let themes=[],headlines=[],feedMeta=null,entries=[],detailOrigin=null,detailPending=null;
const filters=stored('alicanto_global_filters',{});
// Before 27-oct a single publisher was stored as `publisher`; it becomes a one-item selection.
const activePublishers=new Set(Array.isArray(filters.publishers)?filters.publishers:filters.publisher&&filters.publisher!=='Todos'?[filters.publisher]:[]);
let periodMode=PERIODS.includes(String(filters.period))?String(filters.period):['365','all'].includes(String(filters.period))?'90':'30';
let laneMode=['p','l','t'].includes(filters.lane)?filters.lane:'p';
let previousVisit=null;try{previousVisit=localStorage.getItem('alicanto_global_last_visit')}catch{}
function persistFilters(){try{localStorage.setItem('alicanto_global_filters',JSON.stringify({period:periodMode,publishers:[...activePublishers],lane:laneMode}))}catch{}}
function santiagoDay(now=new Date()){const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'America/Santiago',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now).map(x=>[x.type,x.value]));return `${p.year}-${p.month}-${p.day}`}
function ageDays(raw,now=new Date()){return Math.floor((Date.parse(`${santiagoDay(now)}T00:00:00Z`)-Date.parse(String(raw).slice(0,10)+'T00:00:00Z'))/86400000)}
function latestDate(t){return (t.sources||[]).map(s=>s.published_at).filter(Boolean).sort().at(-1)||'1900-01-01'}
function latestCapture(t){return (t.sources||[]).map(s=>String(s.captured_at||'').slice(0,10)).filter(Boolean).sort().at(-1)||''}
function publishers(t){return [...new Set((t.sources||[]).map(s=>s.publisher).filter(Boolean))]}
function httpsUrl(u){try{const x=new URL(String(u||''));return x.protocol==='https:'&&x.hostname?x.href:''}catch{return''}}
function paragraphs(items,prior=[]){const seen=new Set(prior.map(x=>String(x||'').trim().toLowerCase()));return items.filter(Boolean).filter(x=>{const n=String(x).trim().toLowerCase();if(seen.has(n))return false;seen.add(n);return true}).map(x=>`<p>${esc(x)}</p>`).join('')}
function source(s){const a=s.analysis||{};return `<section class="source"><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.publisher)} · ${esc(s.title)} ↗</a><span>Publicado ${dateText(s.published_at)} · ${esc(s.material_type)}</span>${paragraphs([a.executive_summary,...(a.key_findings||[]),...(a.figures||[])])}${a.methodology?`<p><strong>Metodología y alcance:</strong> ${esc(a.methodology)}</p>`:''}${a.implications?.length?`<details><summary>Análisis de esta fuente</summary>${paragraphs(a.implications)}</details>`:''}</section>`}
function publicTitle(t){return t.id==='global-ai-coding-payer-cost-2026'?'BCBSA estima US$942 millones adicionales por codificación; atribución a IA no verificada':t.title}
function detailHtml(t){if(t.id==='global-ai-coding-payer-cost-2026')return `<h2 id="globalDetailTitle">${esc(publicTitle(t))}</h2><p class="stat-limit">El registro histórico atribuye a BCBSA una estimación de US$942 millones adicionales por cambios de codificación, según Reuters. Falta verificar el informe técnico primario, su método y denominadores. Este registro no acredita un efecto causal de la IA ni un efecto comprobado en Chile.</p><h3>Fuentes y evidencia disponible</h3>${(t.sources||[]).map(s=>`<section class="source"><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.publisher)} · ${esc(s.title)} ↗</a><span>Publicado ${dateText(s.published_at)}</span></section>`).join('')}`;const x=t.cross_analysis||{},w=t.chile_watch||{};return `<h2 id="globalDetailTitle">${esc(publicTitle(t))}</h2>${paragraphs([t.detail_body||t.global_finding,x.tensions],[t.title])}${t.depth_limit?`<p>${esc(t.depth_limit)}</p>`:''}${t.hold_reason?`<p class="stat-limit">${esc(t.hold_reason)}</p>`:''}<div class="sources"><h3>Fuentes y evidencia</h3>${(t.sources||[]).map(source).join('')}</div>${x.recurring_pattern||x.decision_use||w.text?`<details><summary>Contexto analítico y límites de transferencia</summary>${paragraphs([x.recurring_pattern,x.decision_use,w.text],[t.global_finding])}<p>Las hipótesis de transferencia requieren evidencia local; no equivalen a un efecto comprobado en Chile.</p></details>`:''}`}
function primaryUrl(t){return (t.sources||[]).map(s=>s.url).find(u=>/^https:\/\//.test(u||''))||''}
// One entry model for both kinds; `dom` is the row id, the share target and the hash that reopens the ficha.
function themeEntry(t){return {kind:'theme',id:t.id,dom:`theme-${t.id}`,key:globalKey(t.id),date:latestDate(t),seen:latestCapture(t),title:publicTitle(t),publishers:publishers(t),url:primaryUrl(t),t}}
function headlineEntry(x){return {kind:'headline',id:x.id,dom:`daily-${x.id}`,key:feedKey(x.id),date:String(x.published_at).slice(0,10),seen:String(x.first_seen_on||'').slice(0,10),title:x.title,publishers:[x.source_label].filter(Boolean),url:httpsUrl(x.url),priority:Number(x.priority)||0,x}}
function buildEntries(){entries=[...themes.map(themeEntry),...headlines.map(headlineEntry)]}
function entryFor(dom){return entries.find(e=>e.dom===dom)}
function isRead(e){return readSet.has(e.key)}
// "Desde mi última visita": items first seen (headline first_seen_on, theme source capture) on or after the day of
// the previous Global visit; without a recorded visit it falls back to 7 days, as on Chile.
function inPeriod(e){const a=ageDays(e.date);if(!(a>=0&&a<WINDOW_DAYS))return false;if(periodMode==='last'&&previousVisit)return Boolean(e.seen)&&e.seen>=santiagoDay(new Date(previousVisit));return a<Number(periodMode==='last'?7:periodMode)}
// Sources: OR between selected publishers; none selected = all sources. Newest first, like Chile.
function visibleEntries(){return entries.filter(inPeriod).filter(e=>!activePublishers.size||e.publishers.some(p=>activePublishers.has(p))).sort((a,b)=>b.date.localeCompare(a.date)||(b.priority||0)-(a.priority||0)||a.dom.localeCompare(b.dom))}
function laneEntries(v){return v.filter(e=>laneMode==='t'||(laneMode==='p'?!isRead(e):isRead(e)))}
// Factual date buckets, as on Chile.
function groups(shown){const bucket=e=>{const a=ageDays(e.date);return a<=1?0:a<=7?1:2},names=['Hoy y ayer','Últimos 7 días','Anteriores'];return names.map((n,i)=>[n,shown.filter(e=>bucket(e)===i)]).filter(g=>g[1].length)}
function periodLabel(){return periodMode==='last'?'desde última visita':`${periodMode} días`}
// Headline attribution, as captured: source label, authors (first two + "y otros"), license link.
function authors(x){const b=(x.bylines||[]).filter(Boolean);return b.length>2?`${b.slice(0,2).join(', ')} y otros`:b.join(', ')}
function license(x){const u=httpsUrl(x.rights_basis?.license_url);return u?` · <a class="lic" href="${esc(u)}" target="_blank" rel="noopener license">${esc(x.rights_basis.license_label||'Licencia')}</a>`:''}
function metaFor(e){if(e.kind==='theme')return `${esc(e.publishers.join(' + '))} · ${dateText(e.date)}`;const x=e.x,a=authors(x);return `<span class="eyebrow">Titular</span> · ${esc(x.source_label)}${a?` (${esc(a)})`:''} · ${dateText(e.date)}${license(x)}`}
function row(e){const read=isRead(e),attr=e.kind==='theme'?`data-theme="${esc(e.id)}"`:`data-daily="${esc(e.id)}"`;return `<article class="${e.kind==='theme'?'theme':'daily-item'} signal item ${read?'read':''}" id="${esc(e.dom)}" tabindex="-1" ${attr}>${AlicantoBar.dotButton('data-read',e.dom,read,e.title)}<div class="item-body"><h2><button type="button" class="title-open" data-open="${esc(e.dom)}">${esc(e.title)}</button></h2><div class="card-meta"><span class="meta-text">${metaFor(e)}</span></div>${AlicantoBar.rowActions(`data-open="${esc(e.dom)}"`,e.url,e.dom,e.title)}</div></article>`}
// A headline ficha holds only verified data: title, the publisher's own description if one was captured (verbatim;
// "…" when the feed cut it), date, source and attribution, the OGL statement when it applies, and related sources
// (related_sources plus also_reported_by, https only). description null -> title and meta only, no "Resumen de la fuente".
// A payload from an unknown newer schema is not read; window_days defaults to (and never exceeds) 90.
function feedAccepted(d){const v=d?.schema_version;return Boolean(d)&&d.enabled===true&&d.content_use==='metadata_and_link_only'&&(v===undefined||(Number.isInteger(Number(v))&&Number(v)>=1&&Number(v)<=FEED_SCHEMA))}
function feedWindow(d){const w=Number(d?.window_days);return w>0?Math.min(w,WINDOW_DAYS):WINDOW_DAYS}
// A truncated publisher summary is marked as an excerpt ("… (extracto)"): CC BY (ECDC, EC) asks to indicate changes,
// and every cut summary gets the same notice.
function headlineDesc(x){let d=typeof x.description==='string'?x.description.trim():'';if(!d)return'';if(x.description_truncated===true){d=d.replace(/\s*\(extracto\)$/,'');if(!d.endsWith('…'))d+=' …';d+=' (extracto)'}return d}
function isOgl(x){const r=x.rights_basis||{};return r.basis==='uk_open_government_licence_v3'||/^OGL\b/.test(String(r.license_label||''))}
function oglNote(x,cls){if(!isOgl(x))return'';const u=httpsUrl(x.rights_basis.license_url)||OGL_URL;return `<p class="${cls}">Contains public sector information licensed under the <a href="${esc(u)}" target="_blank" rel="noopener license">Open Government Licence v3.0</a>.</p>`}
// Other pages on the same announcement: captured related_sources (need a title) and the feed's deduplicated copies
// (also_reported_by: publisher label + link). One entry per https URL; the item's own URL is not repeated.
function relatedFor(x,own){const seen=new Set([own].filter(Boolean)),out=[];
 for(const r of Array.isArray(x.related_sources)?x.related_sources:[]){const u=httpsUrl(r?.url);if(u&&r.title&&!seen.has(u)){seen.add(u);out.push({url:u,label:r.source_label||'',title:r.title,date:r.published_at})}}
 for(const r of Array.isArray(x.also_reported_by)?x.also_reported_by:[]){const u=httpsUrl(r?.url);if(u&&r.source_label&&!seen.has(u)){seen.add(u);out.push({url:u,label:r.source_label,title:'',date:r.published_at})}}
 return out}
function headlineDetail(e){const x=e.x,desc=headlineDesc(x),by=(x.bylines||[]).filter(Boolean),related=relatedFor(x,e.url);
 const origin=`<section class="source">${e.url?`<a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(x.source_label||'')}${x.source_label?' · ':''}${esc(x.title)} ↗</a>`:''}<span>Publicado ${dateText(e.date)}${by.length?` · ${esc(by.join(', '))}`:''}${license(x)}</span>${x.attribution&&x.attribution!==x.source_label?`<span>${esc(x.attribution)}</span>`:''}</section>`;
 return `<h2 id="globalDetailTitle">${esc(x.title)}</h2>${desc?`<h3 class="ficha-h">Resumen de la fuente</h3><p>${esc(desc)}</p>`:''}<section class="ficha-sources sources"><h3 class="ficha-h">Fuentes</h3>${origin}${related.map(r=>`<section class="source"><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.label)}${r.label&&r.title?' · ':''}${esc(r.title)} ↗</a>${r.date?`<span>Publicado ${dateText(r.date)}</span>`:''}</section>`).join('')}</section>${oglNote(x,'ficha-note ficha-attr')}<p class="ficha-note">Titular de la fuente, sin análisis de Alicanto.</p>`}
function renderPublishers(){const base=entries.filter(inPeriod),all=[...new Set(entries.flatMap(e=>e.publishers))].sort((a,b)=>a.localeCompare(b,'es')),host=document.getElementById('globalPublisher');for(const p of [...activePublishers])if(!all.includes(p))activePublishers.delete(p);const count=p=>base.filter(e=>e.publishers.includes(p)).length;const focused=document.activeElement?.dataset?.publisher;host.innerHTML=`<button type="button" class="tog tog-all" data-publisher="" aria-pressed="${!activePublishers.size}"><span class="box" aria-hidden="true"></span><span>Todas las fuentes</span><small>${base.length}</small></button><div class="interest-grid">${all.map(p=>`<button type="button" class="tog" data-publisher="${esc(p)}" aria-pressed="${activePublishers.has(p)}"><span class="box" aria-hidden="true"></span><span>${esc(p)}</span><small>${count(p)}</small></button>`).join('')}</div>`;host.querySelectorAll('[data-publisher]').forEach(b=>b.onclick=()=>{const p=b.dataset.publisher;if(!p)activePublishers.clear();else if(activePublishers.has(p))activePublishers.delete(p);else activePublishers.add(p);persistFilters();render()});if(focused!==undefined)host.querySelector(`[data-publisher="${CSS.escape(focused)}"]`)?.focus()}
function updateCounts(){const v=visibleEntries(),unread=v.filter(e=>!isRead(e));document.getElementById('globalMetrics').textContent=unread.length?`${unread.length} pendientes`:'Estás al día';AlicantoBar.syncLanes(document.getElementById('globalLanes'),laneMode,{p:unread.length,l:v.length-unread.length,t:v.length});document.getElementById('globalMarkAll').hidden=!unread.length;return v}
function render(){
 const v=updateCounts(),shown=laneEntries(v),host=document.getElementById('themes');
 document.getElementById('globalFilterLabel').textContent=AlicantoBar.selectionLabel([...activePublishers],'Todas las fuentes','fuentes');
 document.getElementById('globalDone').textContent=`Ver ${v.length} señales`;
 document.getElementById('globalFeedCount').textContent=`${v.length} señales · ${periodLabel()}`;
 const empty=laneMode==='p'?'Estás al día con las señales de este período.':laneMode==='l'?'Aún no hay señales leídas en este período.':'No hay señales en este período.';
 const gs=groups(shown);
 host.innerHTML=gs.length?gs.map(([n,xs])=>`<section class="inbox-group" aria-label="${n}"><h3 class="group-head">${n}</h3>${xs.map(row).join('')}</section>`).join(''):`<p class="inbox-empty">${empty}</p>`;
 host.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>openEntry(b.dataset.open));
 host.querySelectorAll('[data-read]').forEach(b=>b.onclick=()=>toggleRead(b.dataset.read));
 host.querySelectorAll('[data-share]').forEach(b=>b.onclick=()=>AlicantoBar.shareCard(b));
 // Opening a headline's source marks it read, as tapping its title did in "Al día afuera".
 host.querySelectorAll('article[data-daily] a.act-src').forEach(a=>a.addEventListener('click',()=>{const id=a.closest('article').id,e=entryFor(id);if(e&&!isRead(e))AlicantoRead.set(e.key,true).then(()=>{syncRow(id);offerUndo(id)})}));
 AlicantoBar.placeStrip(host,'article[data-theme],article[data-daily]');
 renderPublishers();
}
function readStatus(message){document.getElementById('readStatus').textContent=AlicantoRead.persistent?message:'La lectura se conserva sólo en esta sesión; no se pudo guardar en este navegador.'}
function focusAfter(index,attr='data-read'){const dots=document.querySelectorAll(`#themes [${attr}]`);const next=dots[Math.min(index,dots.length-1)];if(next)next.focus();else{const host=document.getElementById('themes');host.tabIndex=-1;host.focus()}}
// Inline undo on the row, as on the Home (Dirección 28-oct, punto 3): no bar under the filters.
function leaves(dom){const e=entryFor(dom);return Boolean(e)&&laneMode!=='t'&&(laneMode==='p')===isRead(e)}
function rowFor(dom){return document.getElementById(dom)}
function syncRow(dom){const r=rowFor(dom),e=entryFor(dom);if(!r||!e)return;const read=isRead(e);r.classList.toggle('read',read);const b=r.querySelector('[data-read]');if(b)AlicantoBar.syncDot(b,read,e.title);updateCounts()}
function settle(dom,focusAttr){const rows=[...document.querySelectorAll('#themes article.item')],at=rows.indexOf(rowFor(dom)),hadFocus=rowFor(dom)?.contains(document.activeElement)||document.activeElement===document.body;render();if(hadFocus)focusAfter(Math.max(0,at),focusAttr)}
function offerUndo(dom,focusAttr='data-read'){const r=rowFor(dom),e=entryFor(dom);if(!r||!e||!leaves(dom)){if(r)AlicantoBar.clearRowUndo(r);return}const read=isRead(e);AlicantoBar.rowUndo(r,{label:read?'Leída':'No leída',onUndo:async()=>{await AlicantoRead.set(e.key,!read);readStatus('Lectura deshecha.');syncRow(dom);rowFor(dom)?.querySelector('.title-open')?.focus()},onExpire:()=>settle(dom,focusAttr)})}
async function toggleRead(dom){const e=entryFor(dom);if(!e)return;const value=!isRead(e);await AlicantoRead.set(e.key,value);readStatus(value?'Marcado como leído.':'Marcado como no leído.');syncRow(dom);offerUndo(dom)}
async function markAll(){const keys=visibleEntries().filter(e=>!isRead(e)).map(e=>e.key),first=visibleEntries().find(e=>!isRead(e))?.dom;if(!keys.length)return;await AlicantoRead.setMany(keys,true);readStatus(`${keys.length} señales marcadas como leídas.`);render();AlicantoBar.feedUndo(document.getElementById('themes'),{label:`${keys.length} señales marcadas como leídas`,onUndo:async()=>{await AlicantoRead.setMany(keys,false);readStatus('Lectura deshecha.');render();rowFor(first)?.querySelector('.title-open')?.focus()}})?.querySelector('button')?.focus()}
// The ficha header keeps Volver and the read toggle; its actions (Fuente original ↗ · Compartir) sit under it.
function wireDetailBar(e){const bar=document.getElementById('globalDetailBar');if(!bar)return;bar.innerHTML=`<button type="button" class="textbtn" id="globalDetailRead">${isRead(e)?'Marcar no leída':'Marcar leída'}</button>`;const acts=document.getElementById('globalDetailActs');if(acts){acts.innerHTML=AlicantoBar.fichaActions(e.url,e.dom,e.title);acts.querySelectorAll('[data-share]').forEach(b=>b.onclick=()=>AlicantoBar.shareCard(b))}document.getElementById('globalDetailRead').onclick=async()=>{await AlicantoRead.set(e.key,!isRead(e));readStatus(isRead(e)?'Marcado como leído.':'Marcado como no leído.');wireDetailBar(e);document.getElementById('globalDetailRead')?.focus()}}
async function openEntry(dom){const e=entryFor(dom);if(!e)return;const dialog=document.getElementById('globalDetail');detailOrigin=document.activeElement;detailPending={dom,was:isRead(e)};try{document.getElementById('globalDetailBody').innerHTML=e.kind==='theme'?detailHtml(e.t):headlineDetail(e);wireDetailBar(e);if(!dialog.open)dialog.showModal();document.getElementById('closeGlobalDetail').focus();await AlicantoRead.set(e.key,true);wireDetailBar(e);readStatus('Marcado como leído.')}catch{readStatus('No se pudo abrir la ficha.')}}
// Like the Home's syncReadUI: read changes (this tab or another) update rows in place; rows never jump.
AlicantoRead.subscribe(()=>{if(entries.length){document.querySelectorAll('#themes article.item').forEach(r=>syncRow(r.id));updateCounts()}if(!AlicantoRead.persistent)readStatus('')});
const filtersDropdown=AlicantoBar.dropdown(document.getElementById('globalFilters'));
const periodSelect=document.getElementById('globalPeriod');
periodSelect.value=periodMode;
periodSelect.onchange=ev=>{periodMode=ev.target.value;persistFilters();filtersDropdown.close(false);render()};
AlicantoBar.wireLanes(document.getElementById('globalLanes'),()=>laneMode,k=>{laneMode=k;persistFilters();render()});
document.getElementById('globalMarkAll').onclick=markAll;
document.getElementById('globalDone').onclick=()=>filtersDropdown.close(true);
document.getElementById('globalReset').onclick=()=>{activePublishers.clear();periodMode='30';periodSelect.value=periodMode;persistFilters();render()};
document.getElementById('closeGlobalDetail').onclick=()=>document.getElementById('globalDetail').close();
document.getElementById('globalDetail').onclick=ev=>{if(ev.target.id==='globalDetail')ev.target.close()};
// Closing returns focus to the row; an item read by opening it leaves Pendientes only after its inline undo.
document.getElementById('globalDetail').addEventListener('close',()=>{const p=detailPending;detailPending=null;const dom=detailOrigin?.dataset?.open;if(p)syncRow(p.dom);const again=dom&&document.querySelector(`#${CSS.escape(dom)} .title-open`);if(again)again.focus();else if(detailOrigin?.isConnected)detailOrigin.focus();else{const next=document.querySelector('#themes [data-open]');if(next)next.focus();else{const host=document.getElementById('themes');host.tabIndex=-1;host.focus()}}const e=p&&entryFor(p.dom);if(e&&!p.was&&isRead(e))offerUndo(p.dom,'data-open')});
// A shared link changed in place (same page, new hash) also opens its ficha.
window.addEventListener('hashchange',()=>{let hash='';try{hash=decodeURIComponent(location.hash.slice(1))}catch{}if(entries.length&&/^(theme|daily)-/.test(hash))openEntry(hash)});
function motionBehavior(){return window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'}
const backTop=document.getElementById('backTop'),topControls=document.querySelector('.global-intro');backTop.hidden=true;
if(topControls&&'IntersectionObserver' in window){new IntersectionObserver(entries=>{const e=entries[0];backTop.hidden=e.isIntersecting||e.boundingClientRect.top>=0}).observe(topControls)}else if(topControls){const updateTop=()=>backTop.hidden=topControls.getBoundingClientRect().bottom>0;window.addEventListener('scroll',updateTop,{passive:true});updateTop()}
backTop.onclick=()=>{const host=document.querySelector('main');host.tabIndex=-1;host.focus({preventScroll:true});host.scrollIntoView({behavior:motionBehavior()})};
// Daily headlines only when Dirección authorized them (enabled) as metadata and link; bad or old items are dropped.
function loadFeed(){return fetch('data/global_feed.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(d=>{if(!feedAccepted(d))return;feedMeta=d;const w=feedWindow(d);headlines=(d.items||[]).filter(x=>x&&x.id&&x.title&&httpsUrl(x.url)&&x.published_at&&ageDays(x.published_at)>=0&&ageDays(x.published_at)<w)}).catch(()=>{})}
// Footer: attribution and no-endorsement note, shown while headlines are listed; a stale feed says so.
// OGL v3.0 items listed -> the licence's attribution statement is in the footer too.
function renderFooter(){const note=document.getElementById('globalAttribution');if(!note)return;note.hidden=!headlines.length;const ogl=document.getElementById('globalFeedOgl');if(ogl)ogl.innerHTML=headlines.some(isOgl)?` Contains public sector information licensed under the <a href="${esc(OGL_URL)}" target="_blank" rel="noopener license">Open Government Licence v3.0</a>.`:'';const f=feedMeta?.freshness||{};document.getElementById('globalFeedStale').textContent=f.status==='stale'&&f.newest_published_at?` Sin titulares nuevos desde ${dateText(f.newest_published_at)}.`:''}
Promise.all([fetch('data/global_themes.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('global themes');return r.json()}),loadFeed()]).then(async([d])=>{await AlicantoRead.ready;// The page date is the newer of the themes file and the daily feed (Dirección 29-oct: Global showed 08 oct with 28-oct items).
 const stamps=[d.generated_at,feedMeta?.generated_at].filter(x=>x&&!Number.isNaN(Date.parse(x))).sort((a,b)=>Date.parse(b)-Date.parse(a));document.getElementById('updated').textContent=`Última actualización: ${dateText(stamps[0]||d.generated_at)}`;themes=d.themes||[];buildEntries();periodSelect.value=periodMode;render();renderFooter();persistFilters();try{localStorage.setItem('alicanto_global_last_visit',new Date().toISOString())}catch{}let hash='';try{hash=decodeURIComponent(location.hash.slice(1))}catch{}if(/^(theme|daily)-/.test(hash))openEntry(hash)}).catch(()=>{document.getElementById('themes').textContent='No se pudo cargar Global.'});
