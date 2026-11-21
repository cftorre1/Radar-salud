// Norm card (Dirección, 11-nov-2026): ONE renderer for a SIS/SUSESO norm in Normativa and in Al día, as data-card.js is
// for Datos, so both sections show the same thing. Every card has the default actions of any Al día card (read dot, date
// line, Ver ficha, Fuente original, Compartir) plus what the Normativa mockup added: the countdown or date box, the
// effective-date line (literal from the norm, or «en revisión») and the «Implementada» check.
// Item fields come from data/normativa.json (src/radar_salud/normativa_index.py). Nothing here infers a date or a state.
(function(root){
 'use strict';
 const MES=['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
 const MESL=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
 const DAY=864e5;
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const D=s=>new Date(s+'T12:00:00-03:00');
 // UTC getters on a noon-Chile date: the same calendar day for readers in any time zone (review of #180).
 const fmt=d=>`${d.getUTCDate()} ${MES[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
 const ymd=d=>{const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:'America/Santiago',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(d).map(x=>[x.type,x.value]));return `${p.year}-${p.month}-${p.day}`};
 let today=D(ymd(new Date()));
 // «Implementada»: a per-reader mark (phase 1), shared by both pages through this browser's storage.
 const IMPL_KEY='alicanto_normativa_implementadas';let impl=new Set();
 try{impl=new Set(JSON.parse(root.localStorage.getItem(IMPL_KEY)||'[]'))}catch{impl=new Set()}
 function toggleImpl(id){impl.has(id)?impl.delete(id):impl.add(id);try{root.localStorage.setItem(IMPL_KEY,JSON.stringify([...impl]))}catch{}return impl.has(id)}
 const isImpl=id=>impl.has(id);
 const legalOf=x=>{const k=x&&x.review&&x.review.kind;return k==='susp'||k==='sinef'?k:null};
 // Effective state. Dirección 21-nov-2026: five states, no technical notes («calculada», «Diario Oficial»):
 // próxima (countdown) · vigente · pendiente de Diario Oficial · suspendida · derogada. A norm whose text gives no date is
 // in force from its own date; only a term Alicanto cannot date («seis meses desde su notificación») stays «en revisión».
 function vstat(x){const r=x.review||{},eff=r.kind==='date'?r.eff:(x.kind==='date'?x.eff:(x.kind==='on_publication_do'?x.do_date:null));
  if(eff){const e=D(eff),days=Math.round((e-today)/DAY);return days>0?{k:'prox',days,e}:{k:'vig',e,since:-days}}
  if(x.kind==='on_publication_do')return {k:'pdo'};
  if(x.unclear&&r.kind!=='nofija')return {k:'sin'};
  if(x.date){const e=D(x.date);return {k:'vig',e,since:Math.round((today-e)/DAY),pub:x.kind==='on_notification'?'notif':'fecha'}}
  return {k:'sin'}}
 // Groups of the Normativa feed. «Implementada» is a mark, never a position (review 11-nov).
 function grp(x){const l=legalOf(x);if(l)return l;const s=vstat(x);
  if(s.k==='prox')return s.days<=30?'p30':'p30p';if(s.k==='vig')return s.since<=30?'v30':'vhist';return s.k}
 const effKey=x=>{const s=vstat(x);return s.e&&!s.pub?ymd(s.e):''};
 const monthOnly=x=>x.prec==='month'&&!(x.review&&x.review.kind==='date');
 const when=(x,e)=>monthOnly(x)?`${MESL[e.getUTCMonth()]} de ${e.getUTCFullYear()}`:fmt(e);
 const nd=n=>`${n} ${n===1?'día':'días'}`;
 function chip(x){const g=grp(x),s=vstat(x),r=x.review||{},who=x.target?`${esc(x.target)} `:'';
  if(g==='susp'||g==='sinef')return `<span class="nm-vig off">${g==='susp'?'Suspendida':'Derogada'} por ${esc(r.by)}</span>`;
  const tag=x.partial?' <span class="tag">· con excepciones: ver texto oficial</span>':'';
  if(s.k==='prox')return `<span class="nm-vig ${g}">${who}${x.target?'entra':'Entra'} en vigencia en ${nd(s.days)} · ${when(x,s.e)}${tag}</span>`;
  if(s.k==='vig'&&s.pub==='notif')return `<span class="nm-vig v">Vigente desde su notificación${tag}</span>`;
  if(s.k==='vig')return `<span class="nm-vig v">${who}${x.target?'vigente':'Vigente'} desde ${when(x,s.e)}${tag}</span>`;
  if(s.k==='pdo')return `<span class="nm-vig pdo">Desde su publicación en Diario Oficial, aún pendiente${tag}</span>`;
  return `<span class="nm-vig sin">Vigencia en revisión${tag}</span>`}
 // Compliance deadlines (Dirección 21-nov-2026): apart from the entry into force, each with its own countdown.
 function plazoState(p){if(!p.due)return {k:p.caso?'caso':'pend'};const e=D(p.due),days=Math.round((e-today)/DAY);return {k:days>=0?'vence':'vencido',days,e}}
 const nextDue=x=>{const ds=(x.plazos||[]).map(plazoState).filter(s=>s.k==='vence').map(s=>s.days);return ds.length?Math.min(...ds):null};
 function plazos(x){const ps=x.plazos||[];if(!ps.length)return '';
  return `<ul class="nm-plz">${ps.map(p=>{const s=plazoState(p),term=p.plazo?`${esc(p.plazo)} ${esc(p.desde||'')}`.trim():'';
   const due=s.k==='vence'?`<b>${s.days===0?'vence hoy':`vence en ${nd(s.days)}`}</b> · ${fmt(s.e)}`:s.k==='vencido'?`venció el ${fmt(s.e)}`:s.k==='caso'?term:`${term} · fecha pendiente`;
   return `<li class="nm-pz ${s.k}"><span class="k">${s.k==='caso'?'Plazo por caso':'Plazo'}:</span> ${esc(p.accion)} · ${due}</li>`}).join('')}</ul>`}
 function box(x){const g=grp(x),s=vstat(x);
  if(g==='p30'||g==='p30p')return `<div class="nm-dd ${g}" aria-hidden="true"><b>${s.days}</b><span>${s.days===1?'día':'días'}</span></div>`;
  if((g==='v30'||g==='vhist')&&s.pub)return '<div class="nm-dd v" aria-hidden="true"><b>✓</b><span>vigente</span></div>';
  if(g==='v30'||g==='vhist')return `<div class="nm-dd v" aria-hidden="true"><b>${s.e.getUTCDate()}</b><span>${MES[s.e.getUTCMonth()]} ${String(s.e.getUTCFullYear()).slice(2)}</span></div>`;
  if(g==='susp'||g==='sinef')return `<div class="nm-dd off" aria-hidden="true"><b>‖</b><span>${g==='susp'?'susp.':'derogada'}</span></div>`;
  if(g==='pdo')return '<div class="nm-dd sin" aria-hidden="true"><b>DO</b><span>pendiente</span></div>';
  return '<div class="nm-dd sin" aria-hidden="true"><b>?</b><span>en revisión</span></div>'}
 // Match on the raw text, then escape each slice (never inside an entity).
 function hl(t,q){t=String(t??'');if(!q)return esc(t);const i=t.toLowerCase().indexOf(String(q).toLowerCase());return i<0?esc(t):`${esc(t.slice(0,i))}<mark>${esc(t.slice(i,i+q.length))}</mark>${esc(t.slice(i+q.length))}`}
 const title=x=>`${x.label} · ${x.subject}`;
 // o: {read (true/false draws the dot; undefined draws none), readId, openHref, openAttr (Al día's data-detail), dateLine
 // (already-escaped «Publicado 6 nov 2026 · SUSESO»), shareId, shareTitle, shareUrl, srcUrl, q (search highlight)}
 function render(x,o={}){
  const Bar=root.AlicantoBar,on=impl.has(x.id),r=x.review||{},legal=legalOf(x),t=o.shareTitle||title(x),q=o.q||'';
  const href=o.openHref||'';
  const open=href||o.openAttr?`<a class="act act-open" href="${esc(href||'#')}"${o.openAttr?` ${o.openAttr}`:''} aria-label="Ver ficha: ${esc(title(x))}"><span>Ver ficha</span>${Bar&&Bar.icons?Bar.icons.chev:''}</a>`:'';
  const dot=typeof o.read==='boolean'&&Bar?Bar.dotButton('data-read',o.readId||x.signal_id||x.id,o.read,title(x)):'';
  return `<div class="nm-card${on?' is-impl':''}${o.read?' read':''}${dot?' has-dot':''}" data-nm="${esc(x.id)}">${dot}`+
   // Dirección 11-nov-2026: no left column («Vigente» box) and no «Norma · Circular · tema» line; the type is the V1 mark
   // in the date line and «Implementada» is a checkbox with its word, next to the state.
   // Option B (Dirección 12-nov-2026): pill («Normativa» in Al día, the act type in Normativa) + «día · emisor» above
   // the title; the validity chip and «Implementada» stay under it.
   (Bar&&Bar.kicker?Bar.kicker('normativa',o.kickerLabel||x.type||'Normativa',[Bar.shortDay(x.date),esc(x.emisor)].filter(Boolean).join(' · '),o.topExtra||''):'')+
   `<h3 class="nm-title">${o.openAttr?`<button type="button" class="title-open nm-open" ${o.openAttr}>`:href?`<a class="nm-open" href="${esc(href)}">`:''}<span class="lab">${hl(x.label,q)}</span> · ${hl(AlicantoBar.tameCaps(x.subject),q)}${o.openAttr?'</button>':href?'</a>':''}</h3><div class="nm-state">${chip(x)}${legal?'':`<button type="button" class="nm-ck" data-impl="${esc(x.id)}" role="checkbox" aria-checked="${on}" aria-label="Implementada: ${esc(x.label)}"><span class="nm-box" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M6 12.5l4 4 8-9"/></svg></span>Implementada</button>`}</div>${plazos(x)}`+

   `<div class="row-acts" role="group" aria-label="Acciones">${open}${Bar?Bar.sourceAct(o.srcUrl||x.url,t):''}${Bar?Bar.shareAct(o.shareId||`n-${x.id}`,t,o.shareUrl):''}</div></div>`;
 }
 // Inside the open ficha (F2, 11-nov-2026): the same state chip and official text as the row, so a norm reads the same
 // in its row, in Normativa and in its ficha.
 // Inside the open ficha: the same state chip as the row. Dirección 11-nov-2026: no «Texto oficial de vigencia» toggle;
 // only a suspension, «sin efecto» or an editorial date decision is quoted inline, since it explains the state.
 function fichaState(x){const r=x.review||{},legal=legalOf(x);
  const note=legal?`<p class="nm-note"><span class="k">${legal==='susp'?'Suspensión':'Sin efecto'}:</span> ${esc(r.by)}: <q>${esc(r.quote)}</q></p>`:r.kind==='date'?`<p class="nm-note"><span class="k">Fecha de vigencia registrada en revisión:</span> <q>${esc(r.quote)}</q></p>`:'';
  return `<div class="nm-ficha"><div class="nm-state">${chip(x)}</div>${plazos(x)}${note}</div>`}
 // The date line both pages print: the norm's emission and its issuer («Emitida 6 nov 2026 · SUSESO»).
 function dateLine(x){return [x.date?`Emitida ${fmt(D(x.date))}`:'',esc(x.emisor)].filter(Boolean).join(' · ')}
 root.AlicantoNormCard={vstat,grp,effKey,chip,box,plazos,plazoState,nextDue,render,dateLine,fichaState,title,toggleImpl,isImpl,legalOf,fmt,ymd,D,MES,MESL,IMPL_KEY,
  setToday:d=>{today=D(ymd(d))}};
})(typeof window==='undefined'?globalThis:window);
