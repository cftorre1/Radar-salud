(function(root){
 // Fuentes (Dirección 27-oct-2026): one line per source — status dot, full official name,
 // short description and the date of the newest captured content. Narrow screens show short_name
 // (SUSESO, DEIS · Minsal); the official name stays in the link text for assistive tech and search. Status and date come
 // only from source_health.json; without it the row shows no status and "—".
 const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const ORDER=['Organismos públicos y reguladores','Datos oficiales','Noticias y mercado','Prestadores e industria','Seguridad laboral'];
 const LABEL={fresh:'Al día',active:'Activa',partial:'Parcial',trial:'En prueba'};
 function status(x,h){if(/en prueba/i.test(x.description||''))return'trial';if(!h)return'active';const t=String(h.technical_status||'').toLowerCase();if(t==='partial')return'partial';if(t==='ok'&&h.content_freshness==='recent')return'fresh';return'active'}
 function shortDescription(text){return String(text||'').replace(/;.*$/,'').replace(/\.\s*$/,'').trim()}
 function contentDate(h){const raw=h&&(h.latest_original_at||h.last_signal_at);if(!raw)return null;const d=new Date(/^\d{4}-\d{2}-\d{2}$/.test(raw)?raw+'T12:00:00Z':raw);if(Number.isNaN(d.getTime()))return null;return{iso:d.toISOString().slice(0,10),label:new Intl.DateTimeFormat('es-CL',{day:'numeric',month:'short',timeZone:'America/Santiago'}).format(d).replace(/\.$/,'')}}
 function rows(sources,health){const hs=(health&&health.sources)||{};return (Array.isArray(sources)?sources:[]).filter(x=>x.name&&x.group&&/^https:\/\//.test(x.url||'')).map(x=>({...x,st:status(x,hs[x.id]),date:contentDate(hs[x.id])}))}
 function render(host,sources,health){
  const xs=rows(sources,health),groups=new Map(ORDER.map(g=>[g,[]]));
  for(const x of xs){if(!groups.has(x.group))groups.set(x.group,[]);groups.get(x.group).push(x)}
  host.innerHTML=[...groups].filter(([,g])=>g.length).map(([label,g])=>`<section class="source-group"><h3 class="source-group-title"><span>${esc(label)}</span><span>${g.length}</span></h3>${g.map(x=>`<div class="source-row" title="${esc(x.description)}"><i class="d ${x.st==='active'?'':x.st}" role="img" aria-label="${LABEL[x.st]}"></i><span class="nm"><a href="${esc(x.url)}" target="_blank" rel="noopener">${x.short_name&&x.short_name!==x.name?`<span class="nm-full">${esc(x.name)}</span><span class="nm-short" aria-hidden="true">${esc(x.short_name)}</span>`:esc(x.name)}</a> <span class="ds">· ${esc(shortDescription(x.description))}</span></span>${x.date?`<time datetime="${x.date.iso}">${esc(x.date.label)}</time>`:'<time>—</time>'}</div>`).join('')}</section>`).join('')||'<p>No hay fuentes activas verificadas disponibles para este catálogo.</p>';
  return xs;
 }
 // "12 fuentes públicas verificadas · 3 al día · revisadas 27 oct, 09:04"
 function context(list,health){const checks=Object.values((health&&health.sources)||{}).map(x=>Date.parse(x.checked_at||'')).filter(Number.isFinite),fresh=list.filter(x=>x.st==='fresh').length;let out=`${list.length} fuentes públicas verificadas · ${fresh} al día`;if(checks.length){const d=new Date(Math.max(...checks)),f=new Intl.DateTimeFormat('es-CL',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'America/Santiago'}).format(d).replace(/\./g,'');out+=` · revisadas ${f}`}return out}
 root.AlicantoSources={render,context,status};
})(typeof window==='undefined'?globalThis:window);
