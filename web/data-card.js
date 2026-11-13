// Data-piece card (Dirección 10-nov-2026, option J; 10-nov 22:05: it looks and behaves the same in Datos and in Chile).
// ONE renderer for both pages: the unread dot (read toggle), «Datos <período> · <cadencia>», a descriptive title (not the
// finding headline), the ficha's topics numbered by row in two columns (1 2 / 3 4 / 5 6) with «Ver restantes (N)» for
// the rest, the feed row's date line («Detectado 10 nov 2026 · SIS») and the row's «Compartir». Every topic opens the
// ficha at that topic ('#sig-<piece_id>&tema=<tab id>', the ficha renderer's own deep link). Chile adds only its extras
// (its «Datos» tag and «Fuente original»); nothing here computes a figure.
// The feed row's date and source helpers live here too, so Chile rows and Datos cards cannot drift apart; app.js
// delegates to them (fmtDate stays duplicated in app.js, where other tests read it as a standalone function).
(function(root){
 'use strict';
 const esc=(s='')=>String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
 const arr=x=>Array.isArray(x)?x:[];
 // Feed row: one date that says whether it is news ('Publicado' / 'Detectado' / 'Actualizado') and the source acronym.
const DIA=(d,y=true)=>{const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'America/Santiago',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(d).map(x=>[x.type,x.value]));return `${Number(p.day)} ${['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'][Number(p.month)-1]}${y?' '+p.year:''}`};// Dirección 11-nov-2026: «6 nov 2026», never «06 nov.» or «sept», the same in every browser
 function fmtDate(raw){if(!raw)return'';const d=new Date(/^\d{4}-\d{2}-\d{2}$/.test(raw)?raw+'T12:00:00Z':raw);if(Number.isNaN(d.getTime()))return esc(raw);return DIA(d)}
 function canonicalSource(name){const n=String(name||'').toLowerCase();if(n.includes('suseso')||n.includes('superintendencia de seguridad social'))return'SUSESO';if(n.includes('superintendencia'))return'Superintendencia de Salud';if(n==='minsal'||n.includes('ministerio'))return'Ministerio de Salud';if(/^(?:pulso(?:\s*\/\s*la tercera|\s+latercera)?|la tercera)$/.test(n))return'Pulso / La Tercera';return name}
 const SOURCE_ABBR={'superintendencia de salud':'SIS','ministerio de salud':'Minsal','minsal':'Minsal','fondo nacional de salud':'Fonasa','fonasa':'Fonasa','instituto de salud pública':'ISP','instituto de salud pública de chile':'ISP','isp':'ISP','superintendencia de seguridad social':'SUSESO','superintendencia de seguridad social (suseso)':'SUSESO','suseso':'SUSESO','fiscalía nacional económica':'FNE','fne':'FNE','congreso nacional':'Congreso','dirección de presupuestos':'DIPRES','dipres':'DIPRES','comisión para el mercado financiero':'CMF','cmf':'CMF','biblioteca del congreso nacional':'BCN','achs seguro laboral':'ACHS','sis':'SIS'};
 const bareSource=x=>{const t=String(x||'').trim(),m=t.match(/^(.*\S)\s*\(([^)]*)\)$/);return m&&SOURCE_ABBR[m[1].toLowerCase()]&&SOURCE_ABBR[m[1].toLowerCase()].toLowerCase()===m[2].trim().toLowerCase()?m[1]:t};
 function feedSource(name){const first=String(name||'').split(' · ')[0].trim();if(!first)return'';const bare=bareSource(first);return SOURCE_ABBR[bare.toLowerCase()]||(/^(?:pulso|la tercera)/i.test(bare)?canonicalSource(bare):first)}
 // Decision 5 (Dirección 11-nov-2026): one verb per piece type. A Datos ficha is «Actualizado» on the day its data
 // changed in Alicanto (new release detected); norms are «Emitida» (norma-card.js); news «Publicado», or «Detectado» when
 // the source gives no publication date (never inferred).
 function rowDate(s){if(s.stats_ficha){const d=s.publication_date||s.published_on||s.data_release_date||s.first_detected_at||s.event_date;return d?`Actualizado ${fmtDate(d)}`:''}
  if(s.date_basis==='first_detected'){const d=s.first_detected_at||s.event_date;return d?`Detectado ${fmtDate(d)}`:''}
  if(s.date_basis==='data_release'){const d=s.data_release_date||s.event_date;return d?`Actualizado ${fmtDate(d)}`:''}
  // A rolling sanctions register (Fiscalización · registro de 90 días) is data that updates: its row shows the issuance of
  // the newest act it counts (Dirección 5-nov rule 'Actualizado' for updated data; 10-nov-2026 on the SUSESO register).
  if(s.event_type==='SANCTION_REGISTER'){const d=s.emission_date||s.event_date;return d?`Actualizado ${fmtDate(d)}`:''}
  const fiscal=Boolean(s.issued_on||s.emission_date)||arr(s.signal_types).includes('Fiscalización')||s.event_date_basis==='emission'||s.event_date_basis==='verified_primary_emission';
  const pub=s.published_on||s.publication_date||(fiscal?null:s.event_date);if(pub)return `Publicado ${fmtDate(pub)}`;
  const det=s.first_detected_at||s.detected_at;return det?`Detectado ${fmtDate(det)}`:''} function cardMeta(s){return [rowDate(s),esc(feedSource(s.source_name))].filter(Boolean).join(' · ')}

 // Option B (Dirección 12-nov-2026): Al día rows show no index; the Datos page keeps two rows of it.
 const SHOWN=4,FEED_SHOWN=0;  // Datos page: 4 topics (two rows); Al día: none
 // Datos page pill: the family's group (datos.json «groups»), so it never repeats the title.
 const GROUP_LABEL={aseguradores:'Aseguradores',prestadores:'Prestadores',empleadores_licencias:'Empleadores y licencias',sector_publico:'Sector público'};
 const expanded=new Set();
 // The ficha's topics as its renderer lists them (stats-ficha.js `topics`): tabs with a label; id = tab id, else position.
 function topicsOf(ficha){return arr(ficha&&ficha.tabs).filter(t=>t&&t.label).map((t,i)=>({id:String(t.id||i),label:String(t.label)}))}
 // A card model from a datos.json family (Datos) or from a feed card plus its datos.json family (Chile). Chile passes
 // its own card as `row` (same fields that datos.json copies into feed_row) and its own share title.
 function model(f,s){
  const m={id:f?f.piece_id:(s&&s.piece_id),title:f?(f.index_title||f.label):String((s&&s.stats_ficha&&s.stats_ficha.family_label)||(s&&(s.display_title||s.title))||''),
   period_label:f?f.period_label:null,cadence:f?f.cadence:null,updating:Boolean(f&&f.status==='updating'),
   topics:f&&Array.isArray(f.topics)?f.topics:topicsOf(s&&s.stats_ficha),row:s||(f&&f.feed_row?{...f.feed_row,stats_ficha:true}:{}),
   share_title:(f&&f.share_title)||(f&&f.headline)||'',dataset:(f&&f.source_dataset)||'',share_url:(s&&s.share_url)||(f&&f.share_url)||'',
   topic:f?(GROUP_LABEL[f.group]||''):'',published:(s&&s.event_date)||(f&&(f.published_at||(f.feed_row&&f.feed_row.event_date)))||'',
   // The day Alicanto verified the release (the inbox sorts by it): shown as «Agregado <día>» when later than the
   // source's date and not in the future (Dirección 13-nov-2026).
   added:(()=>{const fd=String((s&&s.date_basis!=='first_detected'&&s.feed_date)||'').slice(0,10),ev=String((s&&s.event_date)||'').slice(0,10),today=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Santiago'}).format(new Date());return fd&&ev&&fd>ev&&fd<=today?fd:''})()};
  return m;
 }
 function topLine(m){return [`Datos${m.period_label?` ${m.period_label}`:''}`,m.cadence?String(m.cadence).replace(/\s*\([^)]*\)/g,'').trim():'',m.updating?'actualizándose':''].filter(Boolean).join(' · ')}
 const safeId=id=>String(id||'').replace(/[^\w-]/g,'-');
 function topicHref(base,id,tid){return `${base}#sig-${id}&tema=${tid}`}
 function items(m,base,ts,from){return ts.map((t,i)=>`<li><a class="dc-t" href="${esc(topicHref(base,m.id,t.id))}" data-dc-tema="${esc(t.id)}"><span class="dc-n" aria-hidden="true">${from+i+1}</span><span class="dc-l">${esc(t.label)}</span></a></li>`).join('')}
 // «Fuente original»: the row's own link, same rule as the feed (app.js originalLink), so both pages show the same acts.
 function srcLink(r){if(!r||r.source_link_status==='invalid')return '';const u=String(r.source_link||r.source_url||'');return /^https:\/\/[^\s\/?#]+\.[^\s\/?#]+(\/\S*)?$/.test(u)?u:''}
 const moreLabel=(open,n)=>open?'Ocultar temas ↑':`Ver restantes (${n}) ↓`;
 // o: {read, base (link to the ficha, before '#'), shareTitle, openAttr (Chile: its data-detail), topExtra (Al día: «Datos»
 // tag), shown (topics visible before «Ver restantes»: 6 in Datos, 2 in Al día)}. The Bar (inbox-bar.js) draws the dot and «Compartir» on both pages.
 function render(m,o={}){
  const Bar=root.AlicantoBar,read=Boolean(o.read),base=o.base||'',ts=arr(m.topics),shown=Number.isInteger(o.shown)?o.shown:SHOWN,first=ts.slice(0,shown),rest=shown>0?ts.slice(shown):[];  // shown 0 (Al día): no index at all
  const open=expanded.has(m.id),rid=`dcr-${safeId(m.id)}`,title=m.title||'';
  const shareTitle=o.shareTitle||m.share_title||title;
  const toc=first.length?`<ol class="dc-toc" aria-label="Temas de la ficha">${items(m,base,first,0)}</ol>`:'';
  const more=rest.length?`<ol class="dc-toc dc-rest" id="${rid}" start="${shown+1}" aria-label="Temas restantes"${open?'':' hidden'}>${items(m,base,rest,shown)}</ol><button type="button" class="dc-more" aria-expanded="${open}" aria-controls="${rid}" data-dc-more="${esc(m.id)}" data-n="${rest.length}">${moreLabel(open,rest.length)}</button>`:'';
  // «SIS · Datos abiertos: Prestaciones Bonificadas»: organism and dataset (Dirección 11-nov-2026).
  // V1 (Dirección 11-nov-2026): the type marker starts the date line; the period moves here from the old top line.
  // Option B (Dirección 12-nov-2026): pill (the topic on the Datos page, «Datos» in Al día) + «día · fuente»; the period
  // the data cover is the one chip under the title («Datos a agosto 2026»), never a second date in the top line.
  const r=m.row||{},src=esc(feedSource(r.source_name||''));
  const kday=Bar&&Bar.shortDay?Bar.shortDay(m.added||m.published||r.event_date):'';
  const kmeta=[kday?(m.added?`Agregado ${kday}`:kday):'',src].filter(Boolean).join(' · ');
  const top=Bar&&Bar.kicker?Bar.kicker('datos',o.kickerLabel||m.topic||'Datos',kmeta,o.topExtra||''):'';
  const state=m.period_label&&Bar&&Bar.stateChip?Bar.stateChip(`Datos a ${Bar.longPeriod(m.period_label)}${m.updating?' (actualizándose)':''}`,'per'):'';
  return `<div class="dc-card${read?' read':''}" data-dc="${esc(m.id)}">`+
   (Bar?Bar.dotButton('data-read',m.id,read,title):'')+

   top+`<h3 class="dc-title"><a class="dc-open" href="${esc(`${base}#sig-${m.id}`)}"${o.openAttr?` ${o.openAttr}`:''}>${esc(title)}</a></h3>`+state+
   toc+more+
   `<div class="row-acts" role="group" aria-label="Acciones"><a class="act act-open" href="${esc(`${base}#sig-${m.id}`)}"${o.openAttr?` ${o.openAttr}`:''} aria-label="Ver ficha: ${esc(title)}"><span>Ver ficha</span>${Bar&&Bar.icons?Bar.icons.chev:''}</a>${Bar?Bar.sourceAct(srcLink(m.row||{}),title):''}${Bar?Bar.shareAct(`sig-${m.id}`,shareTitle,m.share_url):''}</div>`+
   `</div>`;
 }
 // «Ver restantes» / «Ocultar temas»: a native button (Enter/Space), aria-expanded on it, aria-controls the hidden list.
 // The choice survives redraws of the page (read toggles, view switches) for this visit.
 function toggle(b){
  const doc=root.document,list=doc&&doc.getElementById(b.getAttribute('aria-controls'));if(!list)return;
  const open=list.hidden;list.hidden=!open;b.setAttribute('aria-expanded',String(open));b.textContent=moreLabel(open,Number(b.dataset.n)||0);
  const id=b.dataset.dcMore;if(id){if(open)expanded.add(id);else expanded.delete(id)}
 }
 if(root.document&&root.document.addEventListener)root.document.addEventListener('click',e=>{const b=e.target&&e.target.closest&&e.target.closest('.dc-more');if(b)toggle(b)});
 root.AlicantoDataCard={esc,fmtDate,canonicalSource,SOURCE_ABBR,bareSource,feedSource,rowDate,cardMeta,topicsOf,model,topLine,topicHref,render,toggle,expanded,SHOWN,FEED_SHOWN,srcLink};
})(typeof window==='undefined'?globalThis:window);
