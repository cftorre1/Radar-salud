// Preferences stay on this device. No personal usage data is transmitted.
function stored(key,fallback){try{return JSON.parse(localStorage.getItem(key))??fallback}catch{return fallback}}
function saveLocal(key,value){try{localStorage.setItem(key,value)}catch{}}
function coverageText(d){
 const sources=Object.values(d.sources||{}).filter(s=>s.discovery_scope!=='global_intelligence'),live=d.coverage_live;
 const fmt=n=>new Intl.NumberFormat('es-CL').format(n);
 return d.queue_status==='measured'&&d.queue&&live
  ?`Cobertura global auditada: ${fmt(sources.filter(s=>s.technical_status==='ok'||(!s.technical_status&&['ok','warning'].includes(s.status))).length)} fuentes activas · ${fmt(live.detected)} señales detectadas · ${fmt(live.evaluated)} evaluadas · ${fmt(live.selected)} seleccionadas (LIVE, portada actual).${d.discovery?.failed_sources?` Medición parcial: ${fmt(d.discovery.failed_sources)} fuentes con error.`:''}`
  :`Cobertura global aún no medida: ${fmt(sources.length)} fuentes registradas · señales LIVE sin medición global.`;
}
const esc=(s='')=>String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const filterStored=stored('alicanto_filters',{});
// Interests (Dirección 27-oct-2026, design/home/design.md §3): OR between interests; none selected = everything.
// Rules use existing classification fields (scopes, signal_types, topics, category), never a model.
const has=(xs,vals)=>arr(xs).some(x=>vals.includes(x));
const INTERESTS=[
 {k:'isapres',label:'Isapres',group:'Actores',match:s=>has(s.scopes,['Isapres','Agentes de ventas'])},
 {k:'fonasa',label:'Fonasa',group:'Actores',match:s=>has(s.scopes,['Fonasa'])},
 {k:'prestadores',label:'Prestadores',group:'Actores',match:s=>has(s.scopes,['Prestadores'])},
 {k:'laboral',label:'Salud laboral',group:'Actores',match:s=>has(s.scopes,['Salud laboral','Seguridad social','COMPIN'])},
 {k:'farma',label:'Farma e ISP',group:'Actores',match:s=>has(s.scopes,['Farma / medicamentos'])},
 {k:'publica',label:'Salud pública',group:'Actores',match:s=>has(s.scopes,['Salud pública'])},
 // WATCH (Dirección 27-oct, restored 28-oct): following is its own service, not a filter; "Siguiendo" is the one
 // Actores option that shows the items of followed entities, so there is still a single filter system.
 {k:'siguiendo',label:'Siguiendo',group:'Actores',match:s=>refIds(s).some(id=>followed.has(id))},
 {k:'normativa',label:'Normativa y fiscalización',group:'Temas',match:s=>has(s.signal_types,['Normativa','Fiscalización','Acreditación'])},
 {k:'mercado',label:'Mercado e inversiones',group:'Temas',match:s=>has(s.topics,['investment_ma','competition'])},
 {k:'politica',label:'Política y presupuesto',group:'Temas',match:s=>has(s.scopes,['Política pública','Financiamiento'])||(has(s.scopes,['Sistema de salud'])&&has(s.topics,['financing','waiting_lists']))},
 {k:'datos',label:'Datos y cifras',group:'Temas',match:s=>has(s.signal_types,['Datos'])||['Datos sectoriales','Epidemiología y presión asistencial'].includes(s.category)},
 {k:'innovacion',label:'Innovación y global',group:'Temas',match:s=>has(s.scopes,['Healthtech'])||['Innovación & Startups','Radar Mundo'].includes(s.category)},
];
// A scope saved before 27-oct translates to its interest; 'Todos' and unmapped scopes mean no interest.
const SCOPE_TO_INTEREST={'Isapres':'isapres','Agentes de ventas':'isapres','Fonasa':'fonasa','Prestadores':'prestadores','Salud laboral':'laboral','Seguridad social':'laboral','COMPIN':'laboral','Farma / medicamentos':'farma','Salud pública':'publica','Política pública':'politica','Financiamiento':'politica','Healthtech':'innovacion'};
function storedInterests(f){if(Array.isArray(f.interests))return f.interests.filter(k=>INTERESTS.some(x=>x.k===k));const k=SCOPE_TO_INTEREST[f.scope];return k?[k]:[]}
let allSignals=[],sortMode=filterStored.sort||'date';
const activeInterests=new Set(storedInterests(filterStored));
// Dirección 28-oct (punto 4): one filter system, Actores + Temas; "Formato" is gone and "Entidades" is no longer a
// filter. WATCH stays: followed entities persist (same `entities` key as PR #75, so earlier follows survive),
// are toggled from the ficha, mark their rows, and are reachable through Actores › Siguiendo.
const followed=new Set(arr(filterStored.entities).filter(x=>typeof x==='string'));
let entityCatalog=[];
function refIds(s){return [...new Set(arr(s.entity_refs).map(r=>typeof r==='string'?r:r?.canonical_id).filter(Boolean))]}
function entityInfo(id){return entityCatalog.find(e=>e.id===id)||{id,name:id,short:id}}
function catalogFrom(d){const xs=arr(d.entities).filter(e=>e&&e.id&&e.name);if(xs.length)return xs;const seen=new Map();for(const s of arr(d.signals))for(const r of arr(s.entity_refs))if(r?.canonical_id&&!seen.has(r.canonical_id))seen.set(r.canonical_id,{id:r.canonical_id,name:r.name||r.canonical_id,short:r.name||r.canonical_id,kind:r.kind});return [...seen.values()]}
function filtersActive(){return activeInterests.size>0}
let freeValue={};
let previousVisit;try{previousVisit=localStorage.getItem('alicanto_last_visit')}catch{}
let periodMode=filterStored.period||'30';
let laneMode=['p','l','t'].includes(filterStored.lane)?filterStored.lane:'p',detailPending=null;
const readSet=AlicantoRead.readSet;
function persistFilters(){saveLocal('alicanto_filters',JSON.stringify({interests:[...activeInterests],entities:[...followed],period:periodMode,sort:sortMode,lane:laneMode}))}
function encodedId(value){return btoa(unescape(encodeURIComponent(value)))}
function idFor(s){if(s.piece_id)return s.piece_id;return encodedId((s.source_url||'')+'|'+(s.event_date||'')+'|'+(s.event_type||'OTHER'))}
function legacyIdFor(s,title=s.title){return encodedId((s.source_url||'')+'|'+(title||''))}
function decodedId(value){try{return decodeURIComponent(escape(atob(value)))}catch{return''}}
// Migrate title-based IDs to the stable URL+event-date identity. This keeps a read
// state even when an audited headline changes, without relying on a guessed title.
async function migrateReads(){const byKnown=new Map();for(const s of allSignals){const id=idFor(s);for(const old of [legacyIdFor(s),s.source_title_full?legacyIdFor(s,s.source_title_full):null,s.legacy_read_title?legacyIdFor(s,s.legacy_read_title):null,...arr(s.read_aliases)].filter(Boolean)){byKnown.set(old,[...(byKnown.get(old)||[]),id]);byKnown.set(old.slice(0,120),[...(byKnown.get(old.slice(0,120))||[]),id])}}const aliases=new Map();for(const [old,ids] of byKnown)if(new Set(ids).size===1){const id=ids[0];aliases.set(id,[...(aliases.get(id)||[]),old])}for(const [id,xs] of aliases)if(xs.some(alias=>readSet.has(alias)))await AlicantoRead.migrate('alias-v1:'+id+':'+encodedId(xs.sort().join('|')),[[id,xs,'legacy_alias']]);}
function isRead(s){return readSet.has(idFor(s))}
function weeklyId(w){return `weekly:${w.approved_version_id||w.id}`}
async function migrateWeekly(w){const base=w&&allSignals.find(s=>s.source_url===w.source_url);await AlicantoRead.migrate('weekly-legacy-link-v1',w?[[weeklyId(w),[...(base?[idFor(base)]:[]),`weekly:${w.id}`,...arr(w.read_aliases)],'legacy_shared_read']]:[],{legacyOnly:true});}
function globalId(id){return `global:${id}`}
function weeklyFresh(w,now=new Date()){
 if(!w||w.editorial_review_pass!==true)return false;
 const day=v=>{if(typeof v!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(v))return NaN;const n=Date.parse(v+'T00:00:00Z');return Number.isFinite(n)&&new Date(n).toISOString().slice(0,10)===v?n:NaN};
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Santiago',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
 const p=Object.fromEntries(parts.map(x=>[x.type,x.value])),today=day(`${p.year}-${p.month}-${p.day}`),event=day(w.event_date),anchor=day(w.freshness_anchor_date||w.event_date);
 const D=86400000,expiry=day(w.expires_on);
 // Monday insights (Dirección 27-oct-2026): mirror weekly_freshness.monday_freshness_gate.
 if(w.anchor_kind==='monday')return [anchor,event,expiry].every(Number.isFinite)&&new Date(anchor).getUTCDay()===1&&expiry===anchor+7*D&&anchor<=today&&today<expiry&&anchor-event>=0&&anchor-event<=7*D;
 // Friday→Monday bridge for the last legacy insight (sunset 2026-11-02), as in weekly_freshness.
 let win=7*D;if(Number.isFinite(expiry)&&Number.isFinite(anchor)&&new Date(expiry).getUTCDay()===1&&expiry<=day('2026-11-02')&&expiry-anchor>7*D&&expiry-anchor<=10*D)win=expiry-anchor;
 return [event,anchor].every(d=>Number.isFinite(d)&&today>=d&&today-d<win)&&(!('expires_on' in w)||today<expiry);
}
function currentWeekly(){return weeklyFresh(freeValue.weekly_insight)?freeValue.weekly_insight:null}
// Mirrors HELD_GLOBAL_THEMES in src/radar_salud/free_value.py (config/editorial_rules_v3.json holds):
// stale published data must not promote a held theme as the Home teaser.
const HELD_TEASER_THEMES=['global-ai-coding-payer-cost-2026'];
function teaserAllowed(g){return Boolean(g)&&!HELD_TEASER_THEMES.includes(g.theme_id)&&!arr(freeValue.selection_policy?.global_teaser_excluded_by_hold).includes(g.theme_id)}
function globalPreview(g){return g?.theme_id==='global-ai-coding-payer-cost-2026'?{...g,title:'BCBSA estima US$942 millones adicionales por codificación; atribución a IA no verificada',excerpt:'Estimación atribuida en Reuters. Informe técnico primario, método y denominadores pendientes de verificación.'}:g}
function specials(){const out=[],g=teaserAllowed(freeValue.global_teaser)?globalPreview(freeValue.global_teaser):null,w=currentWeekly();if(w)out.push({kind:'weekly',id:weeklyId(w),title:w.insight_title||w.title,summary:w.insight_teaser||w.insight_reading,date:w.event_date,source:w.source_name,href:w.source_url,sourceCount:arr(w.sources).filter(x=>/^https:\/\//.test(x.url||'')).length});if(g)out.push({kind:'global',id:globalId(g.theme_id),title:g.title,summary:g.excerpt,date:g.published_at,source:g.source_label||(g.publishers||[]).join(' · '),href:g.premium_href});return out}
function specialRead(x){return readSet.has(x.id)}
function specialInPeriod(x){if(periodMode==='last')return false;if(x.kind==='global')return true;return inPeriod({event_date:x.date})}
const checkIcon='<svg class="action-icon" aria-hidden="true" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"></rect><path d="m3 6 9 7 9-7"></path></svg>';
const unreadIcon='<svg class="action-icon" aria-hidden="true" viewBox="0 0 24 24"><path d="m3 10 9-7 9 7v10H3z"></path><path d="m3 10 9 6 9-6"></path></svg>';
// Row pieces (dot toggle, source ↗, share) are shared with Global through inbox-bar.js (Dirección 28-oct, punto 5).
const tickIcon=AlicantoBar.icons.tick;
function dotInner(read){return AlicantoBar.dotInner(read)}
function dotLabel(read){return AlicantoBar.dotLabel(read)}
function dotButton(attr,id,read,title,inner){return AlicantoBar.dotButton(attr,id,read,title,inner)}
function miniShare(targetId,title){return AlicantoBar.miniShare(targetId,title)}
function sourceLink(url){return AlicantoBar.sourceLink(url)}
// Dirección 28-oct-2026: a row without a valid original URL shows no link, never a broken one.
function originalLink(s){if(!s||s.source_link_status==='invalid')return '';const u=String(s.source_link||s.source_url||'');return /^https:\/\/[^\s\/?#]+\.[^\s\/?#]+(\/\S*)?$/.test(u)?u:''}
// Dirección 28-oct-2026 15:16: a thin paywalled piece borrows "Qué pasó" only from authorized open sources,
// every sentence attributed and linked; the paywalled piece stays as "Fuente original". Nothing else is shown.
function corroborationBlock(s){const c=s&&s.paywalled===true?s.corroboration:null;if(!c||!['corroborated','related_only'].includes(c.status))return'';const ok=u=>/^https:\/\/[^\s\/?#]+\.[^\s\/?#]+(\/\S*)?$/.test(String(u||''));const what=arr(c.what).filter(w=>w&&w.text&&w.attribution&&ok(w.source_url));const groups=[];for(const w of what){const g=groups[groups.length-1];if(g&&g.a===w.attribution&&g.u===w.source_url)g.t.push(w.text);else groups.push({a:w.attribution,u:w.source_url,t:[w.text]})}const rel=arr(c.related_sources).filter(x=>x&&ok(x.url));if(!groups.length&&!rel.length)return'';return `<section class="corroboration"><h3>Qué pasó</h3>${groups.map(g=>`<p>Según ${esc(g.a)}: ${esc(g.t.join(' '))} <a href="${esc(g.u)}" target="_blank" rel="noopener">Ver fuente ↗</a></p>`).join('')}<p class="source">${esc(c.original_label||'Fuente original: contenido para suscriptores')}</p>${rel.length?`<div class="related-sources"><h4>Fuentes relacionadas</h4><ul>${rel.map(x=>`<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.source_name||'Fuente')} · ${esc(x.title||'Ver publicación')} ↗</a>${x.event_date?` <span class="related-desc">${fmtDate(x.event_date)}</span>`:''}</li>`).join('')}</ul></div>`:''}</section>`}
function paywallNote(s){return s&&s.paywalled===true?`<p class="paywall-note">${esc(s.paywall_label||'Contenido para suscriptores')}. Mostramos sólo el titular y la bajada pública.</p>`:''}
function readAction(read){return `${read?unreadIcon:checkIcon}<span class="read-label">${read?'Leído':'No leído'}</span>`}
// Global teaser copy (Dirección 28-oct, punto 8): an invitation to the premium section, never a limit.
const GLOBAL_TEASER={label:'Global Premium · desde afuera',invite:'El análisis completo, con sus fuentes, te espera en Global Premium.',cta:'Entrar a Global'};
function specialLabel(x){return x.kind==='global'?GLOBAL_TEASER.label:`Insight de la semana${x.sourceCount>1?` · ${x.sourceCount} fuentes`:''}`}
const chevIcon='<svg class="mini-icon" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"></path></svg>';
// Insight and Global are always-present slim accordion rows (Dirección 27-oct-2026): reading them
// changes their mark (Nuevo → Leído) and collapses them; they never leave "Esta semana".
// Expanding shows the teaser; the title and the CTA open the piece and count as reading.
const openSpecials=new Set();
function specialCard(x){const read=specialRead(x),open=openSpecials.has(x.id),body=`special-body-${esc(x.id)}`;return `<article id="special-${esc(x.id)}" tabindex="-1" class="signal special big-feature ${x.kind} ${read?'read':''} ${open?'open':''}" data-special="${esc(x.id)}"><div class="acc-row"><div class="big-eyebrow">${dotButton('data-special-read',x.id,read,x.title,read?'<span class="read-ring"></span>':'<span class="unread-dot"></span>')}<span>${specialLabel(x)}</span></div><h2><button class="title-open" data-special-open="${esc(x.id)}">${esc(x.title)}</button></h2><span class="acc-state ${read?'':'new'}">${read?'Leído':'Nuevo'}</span><button type="button" class="acc-toggle" data-special-toggle="${esc(x.id)}" aria-expanded="${open}" aria-controls="${body}" aria-label="${open?'Ocultar':'Ver'} resumen: ${esc(x.title)}">${chevIcon}</button></div><div class="acc-body" id="${body}" ${open?'':'hidden'}>${x.summary?`<p class="big-summary">${esc(x.summary)}</p>`:''}${x.kind==='global'?`<p class="big-invite">${GLOBAL_TEASER.invite}</p>`:''}<div class="card-meta"><span class="meta-text">${esc(x.source)}${x.date?` · ${fmtBriefDate(x.date)}`:''}</span><span class="item-actions">${miniShare(`special-${x.id}`,x.title)}<button type="button" class="big-cta" data-special-open="${esc(x.id)}">${x.kind==='global'?GLOBAL_TEASER.cta:'Ver análisis'} →</button></span></div></div></article>`}
function specialAnchor(x){return `<div class="big-anchor ${x.kind} read" id="special-${esc(x.id)}" tabindex="-1" data-special="${esc(x.id)}"><button type="button" class="anchor-open" data-special-open="${esc(x.id)}"><span class="anchor-label">${tickIcon}${x.kind==='global'?'Global Premium':'Insight de la semana'}</span><span class="anchor-title">${esc(x.title)}</span></button></div>`}
let specialOrigin=null;
async function openSpecial(x){detailOrigin=document.activeElement;specialOrigin=x.id;if(x.kind==='global'){location.href=x.href;return}const w=currentWeekly();if(w){try{renderWeeklyDetail(w);document.getElementById('weeklyInsightDialog').showModal();await AlicantoRead.set(x.id,true)}catch{readStatus('No se pudo abrir la ficha.')}}else draw()}
async function setSpecialRead(x,value){await AlicantoRead.set(x.id,value);draw();readStatus(value?'Marcado como leído.':'Marcado como no leído.');(document.querySelector(`[data-special="${CSS.escape(x.id)}"] [data-special-read]`)||document.querySelector('#bigThings [data-special-read]'))?.focus()}
function readStatus(message){const host=document.getElementById('readStatus');if(host)host.textContent=AlicantoRead.persistent?message:'La lectura se conserva sólo en esta sesión; no se pudo guardar en este navegador.'}
function arr(x){return Array.isArray(x)?x:[]}
function publicationContractOk(s){if(String(s.editorial_schema_version)==='3')return Boolean(s.piece_id&&s.detail_body&&s.title&&s.source_url&&s.event_date&&s.source_name&&s.review?.verdict==='PASS'&&s.review.author!==s.review.reviewer&&s.depth_gate?.ok);const types=new Set(arr(s.signal_types).map(x=>String(x).toLowerCase()));const core=Boolean((s.display_title||s.title)&&arr(s.signal_types).length&&arr(s.scopes).length&&s.event_date&&s.source_name&&s.source_url&&(s.card_what||s.what_happened)&&(s.card_why_optional||(s.card_why||s.why_it_matters)));return core&&(!types.has('normativa')||Boolean(s.normative_document_label))}
function individualCardAllowed(s){const verdict=String(s.editorial_committee?.verdict||'PASS').toUpperCase();return s.feed_visibility!==false&&publicationContractOk(s)&&!['HOLD','REJECT'].includes(verdict)}
function typeTags(s){return arr(s.signal_types)} function scopeTags(s){return arr(s.scopes)}
function rel(score){const n=Number(score||0);if(n>=85)return{label:'Esencial',cls:'essential'};if(n>=65)return{label:'Relevante',cls:'relevant'};return{label:'Contexto',cls:'context'}}
function canonicalSource(name){const n=String(name||'').toLowerCase();if(n.includes('suseso')||n.includes('superintendencia de seguridad social'))return'SUSESO';if(n.includes('superintendencia'))return'Superintendencia de Salud';if(n==='minsal'||n.includes('ministerio'))return'Ministerio de Salud';if(/^(?:pulso(?:\s*\/\s*la tercera|\s+latercera)?|la tercera)$/.test(n))return'Pulso / La Tercera';return name}
function sourceCaptureLabel(x){
 const technical=String(x.technical_status||'').toLowerCase(),status=String(x.status||'').toLowerCase(),coverage=String(x.coverage_status||'').toLowerCase();
 if(technical.includes('license_hold')||coverage==='not_permitted')return'Captura pausada por licencia';
 if(technical.includes('paused')||status.includes('paused')||technical==='held')return'Captura pausada';
 if(technical==='error'||status==='error'||x.error_type||coverage==='blocked')return'Captura con error · no se puede confirmar si hay novedades';
 if(technical==='partial'||status==='warning'||['partial','gap','format_gap','unverified'].includes(coverage))return'Cobertura parcial o pendiente de validación';
 return x.checked_at?'Consulta registrada · no acredita cobertura completa':'Sin consulta verificable';
}
function fmtDate(raw){if(!raw)return'';const d=new Date(/^\d{4}-\d{2}-\d{2}$/.test(raw)?raw+'T12:00:00Z':raw);if(Number.isNaN(d.getTime()))return esc(raw);return new Intl.DateTimeFormat('es-CL',{day:'2-digit',month:'short',year:'numeric',timeZone:'America/Santiago'}).format(d)}
function fmtBriefDate(raw){if(!raw)return'';const d=new Date(/^\d{4}-\d{2}-\d{2}$/.test(raw)?raw+'T12:00:00Z':raw);if(Number.isNaN(d.getTime()))return String(raw);return new Intl.DateTimeFormat('es-CL',{day:'numeric',month:'short',timeZone:'America/Santiago'}).format(d).replace(/^(\d{1,2})-(?=\p{L})/u,'$1 ').replace(/\.$/,'')}
function briefSource(x){return x.kind==='weekly'&&x.source==='Superintendencia de Salud'?'SIS':String(x.source||'').replace(/\s*[·+]\s*/g,' + ')}
function fmtUpdated(raw){const d=new Date(raw);if(Number.isNaN(d.getTime()))return'';const t=new Intl.DateTimeFormat('es-CL',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'America/Santiago'}).format(d);return`Última actualización: ${fmtDate(raw)}, ${t}`}
function tagHtml(s){return [...typeTags(s).map(x=>`<span class="tag">${esc(x)}</span>`),...scopeTags(s).slice(0,3).map(x=>`<span class="tag scope">${esc(x)}</span>`)].join('')}
function processHtml(s){const xs=arr(s.affected_processes);return xs.length?`<p class="affects"><span class="label">Impacta en:</span> ${xs.map(x=>`<span class="process">${esc(x)}</span>`).join(' ')}</p>`:''}
function listBlock(title,xs){return xs.length?`<div class="intel"><div class="intel-title">${title}</div><ul>${xs.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}
function insightBlock(s){
 const xs=arr(s.data_insight_evidence);
 if(s.methodology_visibility==='collapsed'){
  const method=s.statistical_methodology||{};
  const fields=Object.entries(method).filter(([k])=>!['source_url','source_document_url','source_documents'].includes(k)).map(([k,v])=>`<div class='related-desc'><strong>${esc(k)}:</strong> ${esc(Array.isArray(v)?v.join(' · '):typeof v==='object'?JSON.stringify(v):v)}</div>`).join('');
  const docs=arr(method.source_documents);
  return `<details class='related statistical-methodology'><summary>Método y fuentes de datos</summary>${fields}${xs.length?`<ul>${xs.map(x=>`<li>${esc(x.text)}<div class='related-desc'>${esc(x.period)} · ${esc(x.formula)} · ${esc(x.sheet)} · <a href='${esc(x.source_url)}' target='_blank' rel='noopener'>Fuente estadística ↗</a></div></li>`).join('')}</ul>`:''}${docs.map(url=>`<div class='related-item'><a href='${esc(url)}' target='_blank' rel='noopener'>Documento de respaldo ↗</a></div>`).join('')}${method.source_url?`<div class='related-item'><a href='${esc(method.source_url)}' target='_blank' rel='noopener'>Ficha metodológica oficial ↗</a></div>`:''}${method.source_document_url?`<div class='related-item'><a href='${esc(method.source_document_url)}' target='_blank' rel='noopener'>Archivo de datos ↗</a></div>`:''}</details>`
 }
 if(!xs.length)return listBlock('Cifras y lectura de datos',arr(s.data_insights));
 return `<div class='intel'><div class='intel-title'>Muestra de datos validada · período, cálculo y evidencia</div><ul>${xs.map(x=>`<li>${esc(x.text)}<div class='related-desc'>${esc(x.period)} · ${esc(x.formula)} · ${esc(x.sheet)} · <a href='${esc(x.source_url)}' target='_blank' rel='noopener'>Serie oficial ↗</a></div></li>`).join('')}</ul></div>`
}
function summaryTableBlock(s){
 const t=s.summary_table;if(!t||!Array.isArray(t.rows)||!t.rows.length)return'';
 const cols=t.columns||['Indicador','Período','Valor','Lectura'];
 return `<div class='intel summary-table'><div class='intel-title'>${esc(t.title||'Resumen ejecutivo')}</div><div class='table-wrap'><table><thead><tr>${cols.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${t.rows.map(r=>{const cells=Array.isArray(r.cells)?r.cells:[r.indicator,r.period,r.value,r.reading];return `<tr>${cells.map((v,i)=>`<td data-label="${esc(cols[i])}">${i===cols.length-1?`<strong>${esc(v)}</strong>`:esc(v)}</td>`).join('')}</tr>`}).join('')}</tbody></table></div></div>`
}

function contextBlock(xs){if(!xs.length)return'';return`<details class="related"><summary>Normativa relacionada · ${xs.length}</summary>${xs.map(x=>`<div class="related-item"><div class="related-title">${esc(x.title||'Norma relacionada')}</div>${x.relationship?`<div class="relationship">${esc(x.relationship)}</div>`:''}${x.summary?`<div class="related-desc">${esc(x.summary)}</div>`:''}${x.event_date?`<div class="related-desc">${x.date_basis?sourceTiming(x):`Fecha: ${fmtDate(x.event_date)}`}</div>`:''}${x.url&&x.verified?`<a href="${esc(x.url)}" target="_blank" rel="noopener">Ver antecedente ↗</a>`:'<div class="related-desc">Referencia identificada en la fuente · enlace pendiente de verificación</div>'}</div>`).join('')}</details>`}
function sourceTiming(s){if(s.date_basis==='first_detected')return `Detectado el ${fmtDate(s.first_detected_at||s.event_date)} · fecha de publicación no informada por la fuente`;if(s.date_basis==='data_release')return `${s.data_release_scope==='catalog'?'Catálogo actualizado el':'Datos actualizados el'} ${fmtDate(s.data_release_date||s.event_date)}`;const fiscal=Boolean(s.issued_on||s.emission_date)||arr(s.signal_types).includes('Fiscalización')||s.event_date_basis==='emission'||s.event_date_basis==='verified_primary_emission';if(fiscal){const parts=[];if(s.published_on||s.publication_date)parts.push(`Publicado ${fmtDate(s.published_on||s.publication_date)}`);if(s.issued_on||s.emission_date)parts.push(`Emitido ${fmtDate(s.issued_on||s.emission_date)}`);if(!s.published_on&&!s.publication_date)parts.push('Publicación no verificada');return parts.join(' · ')}return s.event_date?`Publicado ${fmtDate(s.event_date)}`:'Fecha de publicación no verificada'}
function sourceBlock(xs,isPulse=false,isData=false,label=null){if(!xs.length)return'';return`<details class="related sourceverify ${label?"historical-sanctions":""}"><summary>${label|| (isData?'Series oficiales incluidas':isPulse?'Resoluciones incluidas en este pulso':'Otras fuentes que verifican este hallazgo')} · ${xs.length}</summary>${xs.map(x=>`<div class="related-item"><div class="related-title">${esc(x.material||x.source_name||'Fuente')}</div><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title||'Ver publicación')} ↗</a>${x.event_date?`<div class="related-desc">${sourceTiming(x)}</div>`:''}</div>`).join('')}</details>`}
function enrichmentBlock(xs,historical,status){if(!xs.length&&!historical.length&&!status)return'';return`<details class="related editorial-enrichment"><summary>Para profundizar · ${xs.length}</summary>${xs.map(x=>`<div class="related-item"><div class="relationship">${esc(x.label)}</div><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)} ↗</a><div class="related-desc">${esc(x.note)}</div></div>`).join('')}${historical.length?`<div class="intel-title">Conexiones históricas</div>${historical.map(x=>`<div class="related-item"><div class="relationship">${esc(x.label)}</div><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)} ↗</a>${x.event_date?`<div class="related-desc">${x.date_basis?sourceTiming(x):`Publicado ${fmtDate(x.event_date)}`}</div>`:''}<div class="related-desc">${esc(x.note)}</div></div>`).join('')}`:''}${status?`<div class="related-desc">${esc(status)}</div>`:''}</details>`}
function distinct(a,b){const norm=x=>String(x||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();const x=norm(a),y=norm(b);return !!x&&x!==y&&!(x.startsWith(y)&&x.length-y.length<35)&&!(y.startsWith(x)&&y.length-x.length<35)}
function substantivePoints(s){return arr(s.key_points).filter(x=>distinct(x,s.what_happened)&&distinct(x,s.title)&&distinct(x,s.why_it_matters)&&!/(no (se )?(inform[aó]|entreg[aó]|detall[aó]|especific[aó]|precis[aó])|sin detalles|no hay detalles|falta(n)? detalles)/i.test(x))}
function detailKind(s){if(s.statistical_value_level==='deep_analysis'&&s.summary_table?.rows?.length)return 'summary';if(substantivePoints(s).length||arr(s.data_insights).length)return 'summary';if(s.normative_context||arr(s.related_context).length||arr(s.source_alternatives).length||arr(s.editorial_enrichment).length||arr(s.historical_connections).length)return 'context';return null}
function cardDepth(s){return detailKind(s)!==null}
function httpsSource(value){try{const url=new URL(value);return url.protocol==='https:'&&Boolean(url.hostname)}catch{return false}}
function detailHtml(s){
 const v3=String(s.editorial_schema_version)==='3';const title=triageTitle(s),seen=new Set([String(title).trim().toLowerCase()]);
 const fresh=x=>{if(!x)return false;const n=String(x).trim().toLowerCase();if(seen.has(n))return false;seen.add(n);return true};
 let body='';
 if(!s.statistical_view&&String(s.source_url||'').includes('estadisticas-financieras-del-sistema-isapre-a-marzo-2026/'))s={...s,statistical_view:{publication_status:'HOLD',limitations:['La nota de cobertura contradice cifras institucionales de Esencial; comparaciones y agregados afectados pendientes de aclaración.'],source_url:s.source_url}};
 if(s.statistical_view){
  body=AlicantoStats.render(s.statistical_view);
  const kinds={portfolio_mix_shift:'cartera',subscriptions_voluntary_gap:'suscripciones',mobility_interval:'movilidad'};
  const complementary=arr(s.data_insight_evidence).filter(x=>Object.hasOwn(kinds,x.analysis_kind)&&kinds[x.analysis_kind]===x.family&&/^[a-f0-9]{64}$/.test(x.sha256||'')&&x.sha256===s.data_insight_meta?.sha256?.[x.family]&&httpsSource(x.source_url));
  if(!v3&&s.statistical_view.publication_status!=='HOLD'&&s.data_insight_meta?.status==='validated'&&complementary.length){
   body+=`<details class='related statistical-calculations'><summary>Cálculos adicionales verificados</summary>${insightBlock({...s,data_insight_evidence:complementary})}</details>`;
  }
 }
 else if(String(s.editorial_schema_version)==='3'){
  const used=new Set(Object.values(s.paragraph_claim_ids||{}).flat());
  body=String(s.detail_body||'').split('\n\n').filter(Boolean).map(x=>`<p>${esc(x)}</p>`).join('');
  body+=arr(s.depth_modules).map(m=>{const claims=arr(s.claims).filter(c=>arr(m.claim_ids).includes(c.id)&&!used.has(c.id));for(const c of claims)used.add(c.id);return claims.length?`<details class='related'><summary>${esc(m.label)}</summary>${claims.map(c=>`<p>${esc(c.text)}</p>`).join('')}</details>`:''}).join('');
 }else{
  if(s.normative_minimal){body=`<p>${esc(s.normative_context||'')}</p>`;
   return `<h2 id='detailTitle'>${esc(title)}</h2>${body}${originalLink(s)?`<p class='source'><a href="${esc(originalLink(s))}" target="_blank" rel="noopener">Documento oficial</a></p>`:''}`}
  // Dirección 28-oct (punto 1): "un texto al grano". What happened, then why it matters, as plain paragraphs;
  // no meta-label (it used to fold "why" away behind one) and nothing collapsed.
  const texts=[s.card_what||s.what_happened,s.card_why_optional?null:s.card_why||s.why_it_matters,s.normative_context,...arr(s.key_points),...arr(s.key_facts)].filter(fresh);
  body=texts.map(x=>`<p>${esc(x)}</p>`).join('');
  if(!texts.length)body='<p>La fuente disponible no aporta más detalle verificado para esta ficha histórica.</p>';
  body+=corroborationBlock(s);
  body+=summaryTableBlock(s)+insightBlock(s);
  body+=arr(s.risk_notes).filter(fresh).map(x=>`<p>${esc(x)}</p>`).join('');
 }
 const dates=[s.issued_on||s.emission_date?`Emisión: ${fmtDate(s.issued_on||s.emission_date)}`:null,s.inspection_date?`Fiscalización: ${fmtDate(s.inspection_date)}`:null,s.inspection_period?`Período de fiscalización: ${esc(s.inspection_period)}`:null,s.fact_period?`Período fiscalizado: ${esc(s.fact_period)}`:null].filter(Boolean).join(' · ');
 const docs=[...arr(s.source_documents),...(v3?arr(s.evidence).map(e=>({url:e.url,title:e.locator})):[])].map(x=>typeof x==='string'?{url:x,title:'Documento original'}:x).filter(x=>/^https:\/\//.test(x.url||x.document_url||''));
 return `<h2 id='detailTitle'>${esc(title)}</h2>${body}${s.validity_text?`<p><strong>Vigencia:</strong> ${esc(s.validity_text)}</p>`:''}${dates?`<p class='source'>${dates}</p>`:''}${!v3?contextBlock(arr(s.related_context))+(s.event_type==='STORY_SUMMARY'?sourceBlock(arr(s.source_alternatives),false,false,'Piezas incluidas en esta síntesis'):sourceBlock(arr(s.source_alternatives),Boolean(s.sanction_count)||s.event_type==='ACCREDITATION_PULSE',s.event_type==='DATA_PULSE'))+sourceBlock(arr(s.historical_sanction_context),false,false,'Suspensiones de oficios históricos')+enrichmentBlock(arr(s.editorial_enrichment),arr(s.historical_connections),s.historical_context_status):''}${docs.length?`<ul>${docs.map(x=>`<li><a href='${esc(x.url||x.document_url)}' target='_blank' rel='noopener'>${esc(x.title||x.label||'Documento original')} ↗</a></li>`).join('')}</ul>`:''}<p class='source'>${s.data_period?'Período de datos: '+esc(s.data_period)+' · ':''}${sourceTiming(s)}${s.validation_date?' · Validado: '+fmtDate(s.validation_date):''} · ${esc(s.source_name)}${originalLink(s)?` · <a href='${esc(originalLink(s))}' target='_blank' rel='noopener'>Fuente original ↗</a>`:''}</p>${paywallNote(s)}`
}
function cardMetadata(s){const dataPulse=s.event_type==='DATA_PULSE'&&s.data_period;const date=dataPulse?`Datos a ${esc(s.data_period)} · ${s.event_date?`Publicado ${fmtDate(s.event_date)}`:'Publicación no verificada'}${s.validation_date?` · Validado ${fmtDate(s.validation_date)}`:''}`:sourceTiming(s);return `${date}${s.source_name?` · ${esc(s.source_name)}`:''}`}
function normativeIdentityHtml(){return ""}
// Inbox rows use a short 'source · date'; data pulses and sanction pulses keep their full dated metadata, and the record always shows it in full.
function rowMeta(s){if(s.event_type==='DATA_PULSE'||s.sanction_count||!s.event_date||s.date_basis==='first_detected'||s.date_basis==='data_release')return cardMetadata(s);const badge='';return `${s.source_name?`${esc(canonicalSource(s.source_name))} · `:''}${fmtDate(s.event_date)}${badge}`}
// Dense rows label only formats that change how a row is read (Normativa, Fiscalización, Datos).
function formatTag(s){const t=['Normativa','Fiscalización','Datos'].find(x=>typeTags(s).includes(x));return t?` <span class="tag">${t}</span>`:''}
// Entity chips: at most two, named in the card itself before acts aggregated in a pulse. Since Dirección 28-oct
// (punto 4) they are plain labels: who is involved, at a glance; filtering lives only in Actores and Temas.
const ENTITY_CHIPS=2;
function entityChips(s){const order={text:0,source:1,pipeline:2,member:3},refs=arr(s.entity_refs).filter(r=>r&&r.canonical_id).sort((a,b)=>(order[a.basis]??4)-(order[b.basis]??4)),ids=[...new Set(refs.map(r=>r.canonical_id))],shown=ids.slice(0,ENTITY_CHIPS);if(!shown.length)return'';return `<span class="ent-chips">${shown.map(id=>{const e=entityInfo(id);return `<span class="ent-chip${followed.has(id)?' on':''}" data-entity-chip="${esc(id)}" title="${esc(followed.has(id)?`Sigues a ${e.name}`:e.name)}"><span class="ent-name">${esc(e.short||e.name)}</span></span>`}).join('')}${ids.length>shown.length?`<span class="ent-more" title="${esc(ids.slice(ENTITY_CHIPS).map(x=>entityInfo(x).name).join(', '))}">+${ids.length-shown.length}</span>`:''}</span>`}
// Chips and the row actions travel together so the icons never drop to a line of their own.
function metaTail(chips,actions){return chips?`<span class="meta-tail">${chips}${actions}</span>`:actions}
const followIcon='<svg class="mini-icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M6 4h12v17l-6-4-6 4z"></path></svg>';
// A row that names a followed entity carries a small marker before its source (WATCH).
function followMark(s){const ids=refIds(s).filter(id=>followed.has(id));return ids.length?`<span class="follow-mark" title="Sigues a ${esc(ids.map(id=>entityInfo(id).name).join(', '))}">${followIcon}<span class="sr-only">Sigues a ${esc(ids.map(id=>entityInfo(id).name).join(', '))}. </span></span>`:''}
function card(s){const rd=isRead(s),id=idFor(s),title=triageTitle(s);return `<article id="sig-${esc(id)}" tabindex="-1" data-card="${esc(id)}" data-rel="${rel(s.radar_score).cls}" class="signal item ${rd?'read':''}">${dotButton('data-read',id,rd,title)}<div class="item-body"><h2><button class="title-open" data-detail="${esc(id)}">${esc(title)}</button></h2><div class="card-meta">${followMark(s)}<span class="meta-text">${rowMeta(s)}</span>${formatTag(s)}${metaTail(entityChips(s),`<span class="item-actions">${sourceLink(originalLink(s))}${miniShare(`sig-${id}`,title)}</span>`)}</div></div></article>`}
let detailOrigin=null;
function detailBar(s){const id=idFor(s),r=isRead(s);return `${sourceLink(originalLink(s))}${miniShare(`sig-${id}`,triageTitle(s))}<button type="button" class="textbtn" id="detailRead">${r?'Marcar no leída':'Marcar leída'}</button>`}
function wireDetailBar(s){const bar=document.getElementById('detailBar');if(!bar)return;bar.innerHTML=detailBar(s);bar.querySelectorAll('[data-share]').forEach(b=>b.onclick=()=>shareCard(b));const t=document.getElementById('detailRead');if(t)t.onclick=async()=>{await AlicantoRead.set(idFor(s),!isRead(s));readStatus(isRead(s)?'Marcado como leído.':'Marcado como no leído.');wireDetailBar(s);document.getElementById('detailRead')?.focus()}}
// Inside the ficha every named entity gets a "Seguir <entidad>" toggle (WATCH). It never changes the filters.
function followRow(s){const ids=refIds(s);if(!ids.length)return'';return `<div class="follow-row" role="group" aria-label="Seguir entidades">${ids.map(id=>{const e=entityInfo(id),on=followed.has(id);return `<button type="button" class="follow-chip" data-follow="${esc(id)}" aria-pressed="${on}">${on?tickIcon:followIcon}<span>${on?'Siguiendo':'Seguir'} ${esc(e.short||e.name)}</span></button>`}).join('')}</div>`}
function wireFollow(host,s){host.querySelectorAll('[data-follow]').forEach(b=>b.onclick=()=>{const id=b.dataset.follow,on=!followed.has(id);if(on)followed.add(id);else followed.delete(id);persistFilters();const fresh=document.createElement('div');fresh.innerHTML=followRow(s);host.querySelector('.follow-row').replaceWith(fresh.firstElementChild);wireFollow(host,s);host.querySelector(`[data-follow="${CSS.escape(id)}"]`)?.focus();readStatus(on?`Siguiendo ${entityInfo(id).name}.`:`Dejaste de seguir ${entityInfo(id).name}.`);draw()})}
async function openDetail(s){const dialog=document.getElementById('signalDetail');detailOrigin=document.activeElement;detailPending={id:idFor(s),was:isRead(s)};try{const body=document.getElementById('detailBody');body.innerHTML=detailHtml(s);body.querySelector('#detailTitle')?.insertAdjacentHTML('afterend',followRow(s));wireFollow(body,s);if(s.statistical_view)AlicantoStats.wire(document.getElementById('detailBody'),s.statistical_view);if(!dialog.open)dialog.showModal();dialog.querySelector('#closeDetail').focus();await AlicantoRead.set(idFor(s),true);wireDetailBar(s);readStatus('Marcado como leído.')}catch{readStatus('No se pudo abrir la ficha.')}}

function dateVal(s){const raw=s.event_date||0,dateOnly=typeof raw==='string'&&raw.length===10&&raw[4]==='-'&&raw[7]==='-';const normalized=dateOnly?raw+'T12:00:00Z':raw;return new Date(normalized).getTime()||0}
function ageDays(s,now=new Date()){const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'America/Santiago',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now).map(x=>[x.type,x.value]));const today=Date.parse(`${p.year}-${p.month}-${p.day}T00:00:00Z`),event=Date.parse(String(s.event_date||'').slice(0,10)+'T00:00:00Z');return Math.floor((today-event)/86400000)}
function freshness(s){const a=ageDays(s);if(a<=2)return 100;if(a<=7)return 88;if(a<=14)return 72;if(a<=30)return 48;if(a<=60)return 28;return 12}
function personalizedScore(s){const radar=Number(s.radar_score||0),action=Number(s.actionability_score||radar),scope=Number(s.scope_score||radar);const impact=Math.max(Number(s.regulatory_impact_score||0),Number(s.economic_impact_score||0),Number(s.editorial_relevance||0));return .39*radar+.11*action+.07*scope+.10*impact+.07*freshness(s)}
function inboxPool(){return visible().filter(s=>!isRead(s)).sort((a,b)=>dateVal(b)-dateVal(a))}
function periodPhrase(){if(periodMode==='last'&&previousVisit)return'desde tu última visita';return`en los últimos ${periodMode==='last'?7:periodMode} días`}
function inPeriod(s){if(!s.event_date)return false;if(periodMode==='last'&&previousVisit)return s.ingestion_mode==='LIVE'&&new Date(s.detected_at||0).getTime()>new Date(previousVisit).getTime();return ageDays(s)>=0&&ageDays(s)<Number(periodMode==='last'?7:periodMode)}
function visible(){let out=allSignals.filter(individualCardAllowed).filter(inPeriod).filter(interestMatch);if(sortMode==='date')out.sort((a,b)=>(isRead(a)-isRead(b))||dateVal(b)-dateVal(a));else out.sort((a,b)=>(isRead(a)-isRead(b))||personalizedScore(b)-personalizedScore(a)||dateVal(b)-dateVal(a));return out}
function interestMatch(s){return !filtersActive()||INTERESTS.some(x=>activeInterests.has(x.k)&&x.match(s))}
// Counts per interest over the active period, before the interest filter itself.
function interestBase(){return allSignals.filter(individualCardAllowed).filter(inPeriod)}
function firstComplete(value){const text=String(value||'').trim(),match=text.match(/^(.+?[.!?])\s+(?=[A-ZÁÉÍÓÚ])/);return match&&match[1].length>=65?match[1]:text}
function trimSummary(s){let t=String(s.what_happened||'').trim();const title=String(s.title||'').trim();if(t.toLowerCase().startsWith(title.toLowerCase()))t=t.slice(title.length).replace(/^[\s:–—-]+/,'');if(!t)t=s.why_it_matters||title;return s.card_what||firstComplete(t)}
const verifiedTriageTitles={
 'https://www.superdesalud.gob.cl/normativa/circular-if-n535/':'Isapres: reembolsos públicos sin compensación de deudas · IF/N°535',
 'https://www.superdesalud.gob.cl/normativa/circular-if-n534/':'Isapres: bonos electrónicos con cédula si falla la biometría · IF/N°534',
 'https://www.minsal.cl/ministra-de-salud-presenta-piloto-para-que-pacientes-del-hospital-barros-luco-retiren-sus-medicamentos-en-farmacias-cercanas-a-sus-hogares-adheridas-a-ley-cenabast/':'Minsal prueba retiro de medicamentos del Barros Luco en farmacias Cenabast',
 'https://www.minsal.cl/consejo-para-mejorar-eficiencia-y-reducir-deficit-estructural-en-salud-incorpora-mirada-de-servicios-de-salud-y-hospitales-en-su-segunda-sesion/':'Minsal suma hospitales y Servicios de Salud al consejo sobre eficiencia y déficit',
 'https://www.df.cl/empresas/salud/max-luksic-propone-alianza-entre-municipalidades-para-mejorar-atencion':'Max Luksic propone alianza municipal para ejecutar recursos de atención primaria'
};
function triageTitle(s){const title=String(s.title||'').trim();if(s.display_title)return String(s.display_title).trim();if(verifiedTriageTitles[s.source_url])return verifiedTriageTitles[s.source_url];if(/^(resolución|circular|decreto|oficio)\b/i.test(title)&&s.normative_document_label){const subject=s.normative_subject||firstComplete(s.card_why||s.card_what||s.why_it_matters||s.what_happened);if(subject)return `${s.normative_document_label} sobre ${String(subject).charAt(0).toLowerCase()+String(subject).slice(1)}`}if(s.editorial_review_id)return title;if(/^(resolución|circular|decreto|oficio)\b/i.test(title)&&s.card_what)return firstComplete(s.card_what);if(title.length>95&&s.card_what&&s.card_what.length<title.length)return firstComplete(s.card_what);return title||firstComplete(s.card_what||s.what_happened||'Señal verificada')}
function triageSummary(s){const what=trimSummary(s),why=s.card_why||firstComplete(s.why_it_matters);return distinct(what,triageTitle(s))?what:why}
async function setReadWithoutReorder(s,value=true){const id=idFor(s);await AlicantoRead.set(id,value);syncReadUI();readStatus(value?'Marcado como leído.':'Marcado como no leído.');}
function syncReadUI(){
for(const row of document.querySelectorAll('#local [data-card]')){const value=readSet.has(row.dataset.card);row.classList.toggle('read',value);const b=row.querySelector('[data-read]');if(b)syncDot(b,value,row.querySelector('.title-open')?.textContent||'')}if(allSignals.length){brief();updateMetrics()}}
// Read rows keep source, date and actions (Dirección 28-oct 03:49): the dot only switches to a tick and back.
function syncDot(b,read,title){AlicantoBar.syncDot(b,read,title)}
function openFromBrief(s){return openDetail(s)}
function wireSpecials(xs){for(const host of [document.getElementById('bigThings'),document.getElementById('brief')]){if(!host)continue;host.querySelectorAll('[data-special-read]').forEach(b=>b.onclick=()=>{const x=xs.find(s=>s.id===b.dataset.specialRead);if(x)setSpecialRead(x,!specialRead(x))});host.querySelectorAll('[data-special-open]').forEach(b=>b.onclick=()=>{const x=xs.find(s=>s.id===b.dataset.specialOpen);if(x)openSpecial(x)});host.querySelectorAll('[data-share]').forEach(b=>b.onclick=()=>shareCard(b));host.querySelectorAll('[data-special-toggle]').forEach(b=>b.onclick=()=>toggleSpecial(b.dataset.specialToggle))}}
function toggleSpecial(id){const open=!openSpecials.has(id);if(open)openSpecials.add(id);else openSpecials.delete(id);const row=document.querySelector(`#bigThings [data-special="${CSS.escape(id)}"]`);if(!row)return;row.classList.toggle('open',open);row.querySelector('.acc-body').hidden=!open;const b=row.querySelector('[data-special-toggle]');b.setAttribute('aria-expanded',String(open));b.setAttribute('aria-label',`${open?'Ocultar':'Ver'} resumen: ${row.querySelector('.title-open')?.textContent||''}`)}
// The week's two big things stay in 'Esta semana' as accordions, read or not (Dirección 27-oct-2026).
// They are weekly editorial pieces: inbox period, filters and 'mark all' deliberately do not apply to them.
function brief(){const xs=specials(),big=document.getElementById('bigThings'),host=document.getElementById('brief');if(!big||!host)return;const focusedId=document.activeElement?.closest?.('[data-special]')?.dataset.special;big.innerHTML=xs.map(specialCard).join('');big.hidden=!xs.length;host.innerHTML='';host.hidden=true;wireSpecials(xs);if(focusedId&&document.activeElement===document.body){const again=document.querySelector(`[data-special="${CSS.escape(focusedId)}"] [data-special-read],[data-special="${CSS.escape(focusedId)}"] [data-special-open]`);again?.focus()}}
function periodMetric(){return periodMode==='last'?'desde última visita':`${periodMode} días`}
// Public freshness notice: an empty or stale inbox must never read as 'nothing happened'.
function freshnessNotice(health,now=Date.now()){const checks=Object.values(health?.sources||{}).filter(x=>String(x.status||'').toLowerCase()==='ok').map(x=>Date.parse(x.checked_at||'')).filter(Number.isFinite);if(!checks.length)return 'No hay una revisión exitosa de fuentes registrada. Lo que ves puede no estar al día.';const last=Math.max(...checks);if(now-last<=48*3600000)return null;return `Última revisión exitosa de fuentes: ${fmtBriefDate(new Date(last).toISOString())}. Lo que ves puede no estar al día; estamos revisando la captura.`}
function laneCounts(){const v=visible(),unread=v.filter(s=>!isRead(s));return{v,unread,read:v.length-unread.length}}
function updateMetrics(){const c=laneCounts(),m=document.getElementById('radarMetrics');if(m){m.textContent=c.unread.length?`${c.unread.length} pendientes`:'Estás al día';m.title='Calculado sobre el período y los filtros activos guardados en este dispositivo.'}AlicantoBar.syncLanes(document.getElementById('lanes'),laneMode,{p:c.unread.length,l:c.read,t:c.v.length});const all=document.getElementById('markAllRead');if(all)all.hidden=!c.unread.length;const count=document.getElementById('feedCount');if(count)count.textContent=`${c.v.length} señales · ${periodMetric()}`;const rail=document.getElementById('railSettings');if(rail)rail.textContent=`${periodMetric()} · ${sortMode==='date'?'Más recientes':'Relevancia para mí'}`;const done=document.getElementById('filterDone');if(done)done.textContent=`Ver ${c.v.length} señales`;const label=document.getElementById('filterLabel');if(label)label.textContent=filterLabel();const dot=document.getElementById('filterDot');if(dot)dot.hidden=sortMode==='date'}
// The filters dropdown names its own state: an empty selection is "Todos los temas" (Dirección 27-oct 22:44, punto 5).
function filterLabel(){return AlicantoBar.selectionLabel(INTERESTS.filter(x=>activeInterests.has(x.k)).map(x=>x.label),'Todos los temas','temas')}
// Read status is one always-visible segmented control: Pendientes · Leídas · Todas (Dirección 27-oct 22:44, punto 5).
function wireLanes(){AlicantoBar.wireLanes(document.getElementById('lanes'),()=>laneMode,k=>{laneMode=k;persistFilters();draw()})}
function focusLanes(){document.querySelector('#lanes .lane.on')?.focus()}
// Dirección 28-oct (punto 3): no "Marcada como leída · Deshacer" bar under the filters. A row that leaves its
// lane first shows "Leída · Deshacer" on itself (AlicantoBar.rowUndo); in Todas its own dot is the undo.
function leaves(id){return laneMode!=='t'&&(laneMode==='p')===readSet.has(id)}
function rowFor(id){return document.querySelector(`#local [data-card="${CSS.escape(id)}"]`)}
function offerUndo(id,focusAttr='data-read'){const row=rowFor(id);if(!row||!leaves(id)){if(row)AlicantoBar.clearRowUndo(row);return}const read=readSet.has(id);AlicantoBar.rowUndo(row,{label:read?'Leída':'No leída',onUndo:async()=>{await AlicantoRead.set(id,!read);readStatus('Lectura deshecha.');syncReadUI();rowFor(id)?.querySelector('.title-open')?.focus()},onExpire:()=>settle([id],focusAttr)})}
// Rows leave a lane they no longer belong to with a short fade, then the list redraws.
function settle(ids,focusAttr='data-read'){const rows=ids.map(id=>document.querySelector(`#local [data-card="${CSS.escape(id)}"]`)).filter(row=>row&&laneMode!=='t'&&(laneMode==='p'?readSet.has(row.dataset.card):!readSet.has(row.dataset.card)));if(!rows.length)return;const all=[...document.querySelectorAll('#local [data-card]')],at=all.indexOf(rows[0]);rows.forEach(r=>r.classList.add('leaving'));const reduce=typeof window!=='undefined'&&window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;setTimeout(()=>{const hadFocus=rows.some(r=>r.contains(document.activeElement))||document.activeElement===document.body;draw();if(hadFocus){const left=[...document.querySelectorAll(`#local [data-card] [${focusAttr}]`)],next=left[Math.min(at,left.length-1)];if(next)next.focus();else{const host=document.getElementById('local');host.tabIndex=-1;host.focus()}}},reduce?0:650)}
function wireRow(el){const find=id=>allSignals.find(x=>idFor(x)===id);el.querySelectorAll('[data-read]').forEach(b=>b.onclick=()=>{const s=find(b.dataset.read);if(s)toggleRead(s)});el.querySelectorAll('[data-detail]').forEach(b=>b.onclick=()=>{const s=find(b.dataset.detail);if(s)openDetail(s)});el.querySelectorAll('[data-share]').forEach(b=>b.onclick=()=>shareCard(b))}
async function toggleRead(s){const id=idFor(s),value=!isRead(s);await AlicantoRead.set(id,value);readStatus(value?'Marcado como leído.':'Marcado como no leído.');syncReadUI();offerUndo(id)}
async function markAllRead(){const ids=visible().filter(s=>!isRead(s)).map(idFor);if(!ids.length)return;if(AlicantoRead.setMany)await AlicantoRead.setMany(ids,true);else for(const id of ids)await AlicantoRead.set(id,true);readStatus(`${ids.length} señales marcadas como leídas.`);draw();AlicantoBar.feedUndo(document.getElementById('local'),{label:`${ids.length} señales marcadas como leídas`,onUndo:async()=>{if(AlicantoRead.setMany)await AlicantoRead.setMany(ids,false);else for(const id of ids)await AlicantoRead.set(id,false);readStatus('Lectura deshecha para las señales.');draw();rowFor(ids[0])?.querySelector('.title-open')?.focus()}})?.querySelector('button')?.focus()}
let revealedHash='';
function sharedHashTarget(){try{return decodeURIComponent(location.hash.slice(1))}catch{return ''}}
function revealSharedHash(){const target=sharedHashTarget();if(!target||target===revealedHash)return;let element=document.getElementById(target);if(!element){const prefix=target.startsWith('special-')?'special-':target.startsWith('sig-')?'sig-':'',id=target.slice(prefix.length),signal=prefix==='sig-'?allSignals.find(x=>idFor(x)===id):null,special=prefix==='special-'?specials().find(x=>x.id===id):null;if(signal){activeInterests.clear();if(!inPeriod(signal))periodMode='90';persistFilters();renderFilters();element=null}}if(!element)element=document.getElementById(target);revealedHash=target;if(element){requestAnimationFrame(()=>requestAnimationFrame(()=>{const current=document.getElementById(target);if(!current)return;current.focus({preventScroll:true});current.scrollIntoView({block:'start'})}))}}
function shareCard(button){return AlicantoBar.shareCard(button)}
// Relevance scores are not calibrated enough to split the inbox (most signals score as relevant),
// so groups are factual date buckets; relevance stays available as a sort order.
// Only a measured detection time counts as new; history without detected_at is never presented as news.
function sinceLastVisit(s){if(!previousVisit||!s.detected_at)return false;const seen=Date.parse(previousVisit),at=Date.parse(s.detected_at);return Number.isFinite(seen)&&Number.isFinite(at)&&at>seen}
function inboxGroups(shown){if(sortMode==='personalized')return shown.length?[['Por relevancia para ti',shown]]:[];if(previousVisit&&shown.some(sinceLastVisit))return [['Nuevas desde tu última visita',shown.filter(sinceLastVisit)],['Anteriores',shown.filter(s=>!sinceLastVisit(s))]].filter(g=>g[1].length);const bucket=s=>{const a=ageDays(s);return a<=1?0:a<=7?1:2},names=['Hoy y ayer','Últimos 7 días','Anteriores'];return names.map((n,i)=>[n,shown.filter(s=>bucket(s)===i)]).filter(g=>g[1].length)}
function laneSignals(v){const shown=v.filter(s=>laneMode==='t'||(laneMode==='p'?!isRead(s):isRead(s)));return shown.sort((a,b)=>(sortMode==='personalized'?personalizedScore(b)-personalizedScore(a):0)||dateVal(b)-dateVal(a))}
function draw(){const hashTarget=sharedHashTarget();if(hashTarget.startsWith('sig-')&&hashTarget!==revealedHash&&!document.getElementById(hashTarget)){const signal=allSignals.find(x=>idFor(x)===hashTarget.slice(4));if(signal){activeInterests.clear();if(!inPeriod(signal))periodMode='90';if(laneMode!=='t'&&(laneMode==='p')===isRead(signal))laneMode='t';const period=document.getElementById('period');if(period)period.value=periodMode;persistFilters();renderFilters()}}const v=visible(),shown=laneSignals(v);updateMetrics();brief();const groups=inboxGroups(shown);const unmeasured=periodMode==='last'&&previousVisit&&allSignals.some(s=>!s.ingestion_mode||!s.detected_at);const empty=laneMode==='p'?(unmeasured?'No se puede verificar qué cambió desde tu última visita: parte del histórico no tiene fecha de detección. Usa 14 días para revisar las señales.':'Estás al día con las señales de este período.'):laneMode==='l'?'Aún no hay señales leídas en este período.':'No hay señales en este período.';renderInterests();const host=document.getElementById('local');host.innerHTML=`<div class="inbox">${groups.length?groups.map(([n,xs])=>`<section class="inbox-group" aria-label="${n}"><h3 class="group-head">${n}</h3>${xs.map(card).join('')}</section>`).join(''):`<p class="inbox-empty">${empty}</p>`}</div>`;host.querySelectorAll('[data-read]').forEach(b=>b.onclick=()=>{const s=v.find(x=>idFor(x)===b.dataset.read);if(s)toggleRead(s)});host.querySelectorAll('[data-detail]').forEach(b=>b.onclick=()=>{const s=v.find(x=>idFor(x)===b.dataset.detail);if(s)openDetail(s)});host.querySelectorAll('[data-share]').forEach(b=>b.onclick=()=>shareCard(b));placeNewsletter(host);revealSharedHash()}
// The newsletter invitation is a slim row inside the feed, after the 7th signal (or at its end); same on Global.
function placeNewsletter(host){AlicantoBar.placeStrip(host,'article[data-card]',host.querySelector('.inbox'))}
function renderFilters(){renderInterests()}
// One interest Set drives the filters dropdown and the desktop rail: Actores and Temas (Dirección 28-oct, punto 4).
function interestCounts(){const base=interestBase();return{total:base.length,by:Object.fromEntries(INTERESTS.map(x=>[x.k,base.filter(x.match).length]))}}
function setInterest(k,on){if(!k)activeInterests.clear();else if(on)activeInterests.add(k);else activeInterests.delete(k);persistFilters();draw()}
function renderInterests(){
 const c=interestCounts();
 const toggle=(cls,x)=>`<button type="button" class="${cls}" data-interest="${x.k}" aria-pressed="${activeInterests.has(x.k)}"><span class="box" aria-hidden="true"></span><span>${esc(x.label)}</span><small>${c.by[x.k]}</small></button>`;
 const shown=x=>x.k!=='siguiendo'||followed.size>0||activeInterests.has('siguiendo');
 const grouped=cls=>['Actores','Temas'].map(g=>`<p class="interest-group">${g}</p><div class="interest-grid">${INTERESTS.filter(x=>x.group===g&&shown(x)).map(x=>toggle(cls,x)).join('')}</div>`).join('');
 const sheet=document.getElementById('interestFilters');
 if(sheet)sheet.innerHTML=`<button type="button" class="tog tog-all" data-interest="" aria-pressed="${!filtersActive()}"><span class="box" aria-hidden="true"></span><span>Todos los temas</span><small>${c.total}</small></button>${grouped('tog')}`;
 const rail=document.getElementById('interestRail');if(rail)rail.innerHTML=grouped('rail-item');
 document.querySelectorAll('[data-interest]').forEach(b=>b.onclick=()=>{const k=b.dataset.interest;setInterest(k,k?!activeInterests.has(k):false);if(k)document.querySelector(`#${b.closest('#interestRail')?'interestRail':'interestFilters'} [data-interest="${k}"]`)?.focus()});
 document.querySelectorAll('[data-open-filters]').forEach(b=>b.onclick=openFilters);
}
// Filters open as a compact dropdown over the feed: the list keeps its place (Dirección 27-oct 22:44, punto 3).
function openFilters(){const d=document.getElementById('filterDetails');if(!d)return;d.open=true;d.scrollIntoView({block:'nearest'});d.querySelector('.filter-body [data-interest]')?.focus({preventScroll:true})}
let filtersDropdown=null;
function closeFilters(focus){filtersDropdown?.close(focus)}
function insightList(label,value){const items=Array.isArray(value)?value:value?[value]:[];return items.length?`<h3>${esc(label)}</h3><ul>${items.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
function legacyInsightChart(c){const rows=arr(c.rows).filter(r=>Number.isFinite(Number(r.value)));if(!rows.length)return'';const max=Math.max(...rows.map(r=>Math.abs(Number(r.value))))||1,neg=rows.some(r=>Number(r.value)<0),W=320,lw=118,bh=22,gap=8,H=rows.length*(bh+gap),avail=W-lw-56,zero=lw+(neg?avail:0);const fmt=v=>`${Number(v).toLocaleString('es-CL',{maximumFractionDigits:1})}${c.unit==='%'?'%':''}`;const bars=rows.map((r,i)=>{const v=Number(r.value),len=Math.abs(v)/max*avail,y=i*(bh+gap),x=v<0?zero-len:zero;return`<text x="0" y="${y+15}" class="ic-label">${esc(r.label)}</text><rect x="${x}" y="${y}" width="${Math.max(len,1)}" height="${bh}" rx="4" class="ic-bar ${v<0?'neg':''} ${r.style==='partial'?'partial':''}"></rect><text x="${v<0?x-4:x+len+4}" y="${y+15}" text-anchor="${v<0?'end':'start'}" class="ic-val">${fmt(v)}</text>`}).join('');const desc=rows.map(r=>`${r.label}: ${fmt(r.value)}`).join('; ');return`<figure class="insight-chart"><figcaption>${esc(c.title)}</figcaption><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.title+'. '+desc)}">${bars}</svg><p class="ic-source">${esc(c.source||'')}</p></figure>`}
// Weekly insight, presentation A (Dirección 27-oct-2026): headline → charts → short essay → watch → notes.
// Numbers are drawn from the reviewed JSON; the only computation here is the paired delta (to − from).
const WI={ink:'#1D3345',ink70:'#4F6170',ink50:'#7C8995',axis:'#B9B3A6',base:'#CFC9BC',accent:'#C37C37',accentSoft:'#F3E6D6'};
function wiNum(v,digits=1){return Number(v).toLocaleString('es-CL',{minimumFractionDigits:digits,maximumFractionDigits:digits}).replace(/^-/,'−')}
function wiNoteIndex(w){return new Map(arr(w.notes).map((n,i)=>[n.id,i+1]))}
function wiRefs(ids,idx){return arr(ids).filter(id=>idx.has(id)).map(id=>`<sup class="wi-ref"><a href="#wi-note-${esc(id)}" data-note="${esc(id)}" aria-label="Nota ${idx.get(id)}">${idx.get(id)}</a></sup>`).join('')}
function wiText(text,idx){return esc(text).replace(/\[\^(n\d+)\]/g,(m,id)=>wiRefs([id],idx))}
function wiPairedBars(c){
 const series=arr(c.series),rows=arr(c.rows),from=c.delta?.from,to=c.delta?.to;if(series.length<2||!rows.length)return'';
 const unit=c.unit==='%'?'%':'',vals=rows.flatMap(r=>series.map(s=>Math.abs(Number(r.values?.[s.key])))).filter(Number.isFinite),max=Math.max(...vals)||1,x0=70,span=192,block=56,top=28,H=top+block*rows.length+26;
 const legend=series.map((s,i)=>`<rect x="${i*80}" y="6" width="12" height="10" rx="2" fill="${s.emphasis?WI.accent:WI.base}"/><text x="${i*80+17}" y="15">${esc(s.label)}</text>`).join('')+(c.delta?.label?`<text x="356" y="15" text-anchor="end" font-weight="700" fill="${WI.accent}">${esc(c.delta.label)}</text>`:'');
 const body=rows.map((r,i)=>{const y=top+6+i*block;const bars=series.map((s,j)=>{const v=Number(r.values?.[s.key]);if(!Number.isFinite(v))return'';const w=Math.abs(v)/max*span,by=y+j*17;return`<rect x="${x0}" y="${by}" width="${w.toFixed(1)}" height="14" rx="2" fill="${s.emphasis?WI.accent:WI.base}"/><text x="${(x0+w+6).toFixed(1)}" y="${by+11}" ${s.emphasis?`font-weight="700" fill="${WI.ink}"`:`fill="${WI.ink50}"`}>${wiNum(v)}${unit}</text>`}).join('');const a=Number(r.values?.[from]),b=Number(r.values?.[to]),d=Math.round((b-a)*10)/10;const delta=c.delta&&Number.isFinite(a)&&Number.isFinite(b)?`<text x="356" y="${y+22}" font-size="13" text-anchor="end" fill="${WI.accent}" ${r.strong?'font-weight="700"':''}>${d>0?'+':''}${wiNum(d)} ${esc(c.delta.unit||'')}</text>`:'';return`<text x="0" y="${y+18}" font-size="13" fill="${WI.ink}" ${r.strong?'font-weight="700"':''}>${esc(r.label)}</text>${bars}${delta}`}).join('');
 const desc=rows.map(r=>`${r.label}: ${series.map(s=>`${wiNum(r.values?.[s.key])}${unit} (${s.label})`).join(', ')}`).join('; ');
 return`<svg viewBox="0 0 360 ${H}" role="img" aria-label="${esc(`${c.subtitle||c.headline}. ${desc}.`)}"><g font-size="12" fill="${WI.ink70}">${legend}</g><line x1="${x0}" y1="${top}" x2="${x0}" y2="${top+block*rows.length-2}" stroke="${WI.axis}"/><g font-size="12">${body}</g>${c.footnote?`<text x="0" y="${H-4}" font-size="11" fill="${WI.ink50}">${esc(c.footnote)}</text>`:''}</svg>`;
}
function wiColumns(c){
 const rows=arr(c.rows).filter(r=>Number.isFinite(Number(r.value)));if(!rows.length)return'';const dg=Number.isInteger(c.digits)&&c.digits>=0&&c.digits<=2?c.digits:0;
 const max=Math.max(...rows.map(r=>Math.abs(Number(r.value))))||1,base=160,scale=108/max,slot=360/rows.length,w=Math.min(76,slot-24),hatch=`wi-hatch-${String(c.id||'c').replace(/[^\w-]/g,'')}`;
 const cols=rows.map((r,i)=>{const v=Number(r.value),h=Math.abs(v)*scale,x=slot*i+(slot-w)/2,cx=x+w/2,partial=r.style==='partial';return`<rect x="${x.toFixed(1)}" y="${(base-h).toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" rx="3" ${partial?`fill="url(#${hatch})" stroke="${WI.accent}" stroke-width="1.5" stroke-dasharray="4 3"`:`fill="${WI.ink}"`}/><text x="${cx.toFixed(1)}" y="${(base-h-8).toFixed(1)}" font-size="18" font-family="Georgia,serif" text-anchor="middle" fill="${partial?WI.accent:WI.ink}">${wiNum(v,dg)}</text><text x="${cx.toFixed(1)}" y="178" font-size="12" text-anchor="middle" fill="${WI.ink70}">${esc(r.label)}</text>${partial&&r.partial_label?`<text x="${cx.toFixed(1)}" y="192" font-size="11.5" text-anchor="middle" fill="${WI.accent}">${esc(r.partial_label)}</text>`:''}`}).join('');
 const desc=rows.map(r=>`${r.label}: ${wiNum(r.value,dg)}${r.style==='partial'&&r.partial_label?` (${r.partial_label})`:''}`).join('; ');
 return`<svg viewBox="0 0 360 196" role="img" aria-label="${esc(`${c.subtitle||c.headline}. ${desc}.`)}"><defs><pattern id="${hatch}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="${WI.accentSoft}"/><line x1="0" y1="0" x2="0" y2="6" stroke="${WI.accent}" stroke-width="1.6"/></pattern></defs><line x1="0" y1="${base}" x2="360" y2="${base}" stroke="${WI.axis}"/>${cols}</svg>`;
}
function insightChart(c,idx=new Map()){
 if(!c||(!c.form&&!c.headline))return legacyInsightChart(c||{});
 const svg=c.form==='paired_bars'?wiPairedBars(c):wiColumns(c);if(!svg)return'';
 return`<figure class="wi-chart"><h3>${esc(c.headline||c.title||'')}</h3>${c.subtitle?`<p class="wi-sub">${esc(c.subtitle)}</p>`:''}${svg}${c.source?`<p class="wi-src">${esc(c.source)}${wiRefs(c.note_refs,idx)}</p>`:''}</figure>`;
}
function wiWords(w){return [w.headline,w.dek,...arr(w.essay?.facts?.paragraphs),...arr(w.essay?.reading?.paragraphs),...arr(w.watch).flatMap(x=>[x.headline,x.explanation])].join(' ').replace(/\[\^n\d+\]/g,'').split(/\s+/).filter(Boolean).length}
function renderWeeklyA(w){
 const idx=wiNoteIndex(w),minutes=Number(w.reading_time_min)||Math.max(1,Math.round(wiWords(w)/200));
 let dek=esc(w.dek||'');if(w.dek_emphasis&&String(w.dek).includes(w.dek_emphasis))dek=dek.replace(esc(w.dek_emphasis),`<strong>${esc(w.dek_emphasis)}</strong>`);
 const section=(cls,s)=>arr(s?.paragraphs).length?`<section class="${cls}"><h3>${esc(s.heading||'')}</h3>${arr(s.paragraphs).map(x=>`<p>${wiText(x,idx)}</p>`).join('')}</section>`:'';
 const watch=arr(w.watch).filter(x=>x&&x.headline&&String(x.explanation||'').trim().split(/\s+/).length>=12);
 const sources=arr(w.sources).filter(x=>/^https:\/\//.test(x.url||''));
 return`<article class="wi"><p class="wi-kicker">Insight semanal <span>· ${fmtDate(w.anchor_kind==='monday'&&w.freshness_anchor_date?w.freshness_anchor_date:w.event_date)} · lectura de ${minutes} min</span></p><h2 id="weeklyInsightTitle" class="wi-headline">${esc(w.headline)}</h2>${dek?`<p class="wi-dek">${dek}</p>`:''}${arr(w.charts).length?`<section class="wi-charts" aria-label="Gráficos">${arr(w.charts).map(c=>insightChart(c,idx)).join('')}</section>`:''}<div class="wi-essay">${section('wi-facts',w.essay?.facts)}${section('wi-reading',w.essay?.reading)}</div>${watch.length>=2?`<aside class="wi-watch"><h3>${esc(w.watch_heading||'Qué mirar')}</h3><ol>${watch.map(x=>`<li><strong>${esc(x.headline)}</strong> ${esc(x.explanation)}</li>`).join('')}</ol></aside>`:''}<footer class="wi-notes">${idx.size?`<h3>Notas sobre la evidencia</h3><ol>${arr(w.notes).map(n=>`<li id="wi-note-${esc(n.id)}" tabindex="-1">${esc(n.text)}</li>`).join('')}</ol>`:''}<h3>Fuentes</h3><ul>${sources.map(x=>`<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.short_label||x.label)}</a> <span class="wi-role">· ${esc(x.short_role||x.role||'')}</span></li>`).join('')}</ul>${w.expires_on?`<p class="wi-valid">Vigente hasta el ${fmtDate(w.expires_on)}.</p>`:''}</footer></article>`;
}
// Older reviewed insights (list schema) keep their original layout.
function renderWeeklyLegacy(w){return `<h2 id="weeklyInsightTitle">${esc(w.insight_title||w.title)}</h2><p class="meta-line">${esc(w.source_name)} · ${w.date_basis?sourceTiming(w):fmtDate(w.event_date)}</p><p>${esc(w.summary)}</p>${insightList('Cifras y alcance',w.key_figures)}${arr(w.charts).map(c=>insightChart(c)).join('')}${insightList('Actores',w.actors)}${insightList('Lectura Alicanto:',w.insight_reading)}${insightList('Decisiones que cambia',w.decision_use)}${insightList('Qué observar',w.what_to_watch)}${insightList('Límites de la evidencia',w.uncertainties)}<h3>Fuentes</h3><ul>${arr(w.sources).filter(x=>/^https:\/\//.test(x.url||'')).map((x,i)=>`<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${i===0?'Revisar fuente original · ':''}${esc(x.label)}</a> · ${esc(x.role)}</li>`).join('')}</ul>`}
function renderWeeklyDetail(w){const host=document.getElementById('weeklyInsightBody');host.innerHTML=w&&w.essay&&w.headline?renderWeeklyA(w):renderWeeklyLegacy(w);if(host.closest)host.closest('dialog')?.classList.toggle('wi-dialog',Boolean(w&&w.essay&&w.headline))}
async function renderFreeValue(d){await AlicantoRead.ready;freeValue=d||{};const weekly=currentWeekly();document.getElementById('valueHighlights').hidden=true;document.getElementById('weeklyInsightBody').innerHTML='';if(weekly){renderWeeklyDetail(weekly);}if(allSignals.length)draw()}
if(typeof document!=='undefined'){document.getElementById('period').disabled=true;document.getElementById('sort').disabled=true;}
if(typeof window!=='undefined')window.setInterval(()=>{if(freeValue.weekly_insight&&!currentWeekly()){const dialog=document.getElementById('weeklyInsightDialog');if(dialog?.open)dialog.close();if(allSignals.length)draw()}},60000);

const freeValueLoad=typeof fetch==='function'?fetch('data/free_value.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('free value');return r.json()}).then(renderFreeValue).catch(()=>{}):Promise.resolve();
fetch('data/radar_today.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('snapshot');return r.json()}).then(async d=>{await AlicantoRead.ready;await freeValueLoad;const updateLabel=fmtUpdated(d.generated_at);allSignals=d.signals||[];entityCatalog=catalogFrom(d);await migrateReads();await migrateWeekly(currentWeekly());if(!['last','7','14','30','60','90'].includes(periodMode))periodMode='30';if(!['personalized','date'].includes(sortMode))sortMode='date';document.getElementById('sort').value=sortMode;const period=document.getElementById('period');period.value=periodMode;renderFilters();draw();document.getElementById('meta').textContent=updateLabel;persistFilters();period.onchange=e=>{periodMode=e.target.value;persistFilters();closeFilters(false);draw()};document.getElementById('sort').onchange=e=>{sortMode=e.target.value;persistFilters();draw()};const reset=document.getElementById('resetFilters');if(reset)reset.onclick=()=>{activeInterests.clear();sortMode='date';periodMode='30';period.value=periodMode;document.getElementById('sort').value=sortMode;persistFilters();renderFilters();draw()};period.disabled=false;document.getElementById('sort').disabled=false;saveLocal('alicanto_last_visit',new Date().toISOString())}).catch(()=>document.getElementById('local').innerHTML='<div>No se pudo cargar Alicanto.</div>');

function openDialog(id){const dialog=document.getElementById(id);if(dialog&&!dialog.open)dialog.showModal()}
document.getElementById('sourcesOpen').onclick=()=>openDialog('sourcesDialog');
document.querySelectorAll('[data-open-sources]').forEach(b=>b.onclick=()=>openDialog('sourcesDialog'));
// Premium and newsletter dialogs (header, strip, rail) are opened by conversion.js, shared with Global.
document.querySelectorAll('[data-open-filters]').forEach(b=>b.onclick=openFilters);
wireLanes();
filtersDropdown=AlicantoBar.dropdown(document.getElementById('filterDetails'));
document.getElementById('filterDone').onclick=()=>closeFilters(true);
// Footnote links stay inside the insight dialog and never rewrite the shared-link hash.
document.getElementById('weeklyInsightBody').addEventListener('click',e=>{const a=e.target.closest?.('[data-note]');if(!a)return;e.preventDefault();const note=document.getElementById(`wi-note-${a.dataset.note}`);if(note){note.scrollIntoView({block:'center',behavior:motionBehavior()});note.focus({preventScroll:true})}});
document.querySelectorAll('[data-close]').forEach(button=>button.onclick=()=>document.getElementById(button.dataset.close).close());
document.querySelectorAll('.home-dialog').forEach(dialog=>dialog.onclick=event=>{if(event.target===dialog)dialog.close()});
const healthLoad=fetch('data/source_health.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject());
healthLoad.then(h=>{const msg=freshnessNotice(h),el=document.getElementById('freshness');if(el&&msg){el.textContent=msg;el.hidden=false}}).catch(()=>{const el=document.getElementById('freshness');if(el){el.textContent='No se pudo verificar cuándo se revisaron las fuentes. Lo que ves puede no estar al día.';el.hidden=false}});
fetch('data/public_sources.json',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(async d=>{const health=await healthLoad.catch(()=>null);const list=AlicantoSources.render(document.getElementById('sourcesList'),d.sources,health);const line=AlicantoSources.context(list,health);const ctx=document.getElementById('sourcesContext');if(ctx)ctx.textContent=line;const rail=document.getElementById('railSources');if(rail)rail.textContent=`${list.length} fuentes · ${list.filter(x=>x.st==='fresh').length} al día`}).catch(()=>{document.getElementById('sourcesList').textContent='No se pudo cargar la lista de fuentes.'});
document.getElementById('sourcesMore').hidden=true;
AlicantoRead.subscribe(()=>{syncReadUI();if(!AlicantoRead.persistent)readStatus('')});
function motionBehavior(){return window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'}
const backTop=document.getElementById('backTop'),topControls=document.getElementById('feedTop')||document.querySelector('.radar-head');backTop.hidden=true;
if(topControls&&'IntersectionObserver' in window){new IntersectionObserver(entries=>{const e=entries[0];backTop.hidden=e.isIntersecting||e.boundingClientRect.top>=0}).observe(topControls)}else if(topControls){const updateTop=()=>backTop.hidden=topControls.getBoundingClientRect().bottom>0;window.addEventListener('scroll',updateTop,{passive:true});updateTop()}
document.getElementById('backTop').onclick=()=>{const host=document.querySelector('main');host.tabIndex=-1;host.focus({preventScroll:true});host.scrollIntoView({behavior:motionBehavior()})};
for(const dialogId of ['signalDetail','weeklyInsightDialog'])document.getElementById(dialogId).addEventListener('close',()=>{const special=dialogId==='weeklyInsightDialog'&&specialOrigin?document.querySelector(`[data-special="${CSS.escape(specialOrigin)}"] .anchor-open,[data-special="${CSS.escape(specialOrigin)}"] [data-special-open]`):null;const sameRow=detailPending?document.querySelector(`#local [data-card="${CSS.escape(detailPending.id)}"] .title-open`):null;if(detailOrigin?.isConnected)detailOrigin.focus();else if(special)special.focus();else if(sameRow)sameRow.focus();else{const next=document.querySelector('#local .title-open');if(next)next.focus()}if(dialogId==='signalDetail'&&detailPending){const {id,was}=detailPending;detailPending=null;if(!was&&readSet.has(id))offerUndo(id,'data-detail')}});
document.getElementById('markAllRead')?.addEventListener('click',markAllRead);
document.getElementById('closeDetail').onclick=()=>document.getElementById('signalDetail').close();
document.getElementById('signalDetail').onclick=e=>{if(e.target.id==='signalDetail')e.target.close()};

