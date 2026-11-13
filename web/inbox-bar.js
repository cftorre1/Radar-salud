// Shared "Tu bandeja" bar and row pieces (Dirección 27-oct 23:13: proposal A on Chile and Global;
// 28-oct: Chile and Global stay homologated, so rows, actions and undo come from here, not from each page).
// Segmented read status, one compact filters dropdown that floats over the feed, and its label.
// No network, no storage: each page keeps its own persisted filter model and read keys.
(function(root){
 const esc=(s='')=>String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
 // Pendientes · Leídas · Todas: buttons [data-lane] inside `host`; counts go in their <span>.
 function syncLanes(host,mode,counts){if(!host)return;host.querySelectorAll('[data-lane]').forEach(b=>{const on=b.dataset.lane===mode;b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on));const n=b.querySelector('span');if(n&&counts)n.textContent=counts[b.dataset.lane]??''})}
 function wireLanes(host,getMode,setMode){if(!host)return;host.querySelectorAll('[data-lane]').forEach(b=>b.onclick=()=>{if(getMode()===b.dataset.lane)return;setMode(b.dataset.lane);b.focus()})}
 // The dropdown closes on a click outside, on Escape (unless a dialog is open), when focus leaves it and through close().
 function dropdown(details){
  const close=focus=>{if(!details||!details.open)return;details.open=false;if(focus)details.querySelector('summary')?.focus()};
  if(details&&typeof document!=='undefined'){
   document.addEventListener('pointerdown',e=>{if(details.open&&!details.contains(e.target))details.open=false});
   document.addEventListener('keydown',e=>{if(e.key==='Escape'&&details.open&&!document.querySelector('dialog[open]'))close(true)});
   // Tab (or any focus move) out of the dropdown closes it; a re-render inside it (relatedTarget null) does not.
   details.addEventListener('focusout',e=>{if(details.open&&e.relatedTarget&&!details.contains(e.relatedTarget))details.open=false});
  }
  return {close,open(){if(details)details.open=true}};
 }
 // An empty selection names the whole set ("Todos los temas", "Todas las fuentes").
 function selectionLabel(names,allLabel,plural){const xs=names.filter(Boolean);return !xs.length?allLabel:xs.length===1?xs[0]:`${xs.length} ${plural}`}

 // Row pieces shared by Chile (#local) and Global (#themes).
 const icons={
  tick:'<svg class="mini-icon" aria-hidden="true" viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5"></path></svg>',
  link:'<svg class="mini-icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M7 17 17 7M9 7h8v8"></path></svg>',
  share:'<svg class="mini-icon" aria-hidden="true" viewBox="0 0 24 24"><circle cx="18" cy="5" r="2.5"></circle><circle cx="6" cy="12" r="2.5"></circle><circle cx="18" cy="19" r="2.5"></circle><path d="m8.2 10.8 7.6-4.5M8.2 13.2l7.6 4.5"></path></svg>',
  back:'<svg class="mini-icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M19 12H5m6-6-6 6 6 6"></path></svg>'
 };
 function dotInner(read){return read?icons.tick:'<span class="unread-dot"></span>'}
 function dotLabel(read){return read?'Marcar como no leído':'Marcar como leído'}
 // The unread dot is the read toggle: it already occupies the left gutter, so the action costs no width.
 function dotButton(attr,id,read,title,inner=dotInner(read)){return `<button type="button" class="dotbtn ${read?'done':''}" ${attr}="${esc(id)}" aria-label="${dotLabel(read)}: ${esc(title)}" aria-description="Estado: ${read?'leído':'no leído'}" title="${dotLabel(read)}">${inner}</button>`}
 function syncDot(b,read,title){b.classList.toggle('done',read);b.innerHTML=dotInner(read);b.setAttribute('aria-label',`${dotLabel(read)}: ${title}`);b.setAttribute('aria-description',`Estado: ${read?'leído':'no leído'}`);b.title=dotLabel(read)}
 function sourceLink(url){return url?`<a class="iconbtn" href="${esc(url)}" target="_blank" rel="noopener" title="Fuente original" aria-label="Fuente original">${icons.link}<span class="sr-only">Fuente original</span></a>`:''}
 function miniShare(targetId,title,shareUrl){return `<button type="button" class="iconbtn sharebtn" data-share="${esc(targetId)}"${shareUrl?` data-share-url="${esc(shareUrl)}"`:''} data-share-title="${esc(title)}" aria-label="Compartir: ${esc(title)}" title="Compartir">${icons.share}</button><span class="share-feedback" role="status" aria-live="polite"></span>`}
 // Dirección 28-oct 08:20 (opción B): every row shows its actions in plain view and in one fixed order,
 // Ver ficha › · Fuente original ↗ · Compartir. `open` is the attribute the page wires to its ficha. The source
 // link is only rendered from the item's captured https URL; without one the button is absent, never a placeholder.
 icons.chev='<svg class="mini-icon" aria-hidden="true" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6"></path></svg>';
 function httpsUrl(u){try{const x=new URL(String(u||''));return x.protocol==='https:'&&x.hostname?x.href:''}catch{return''}}
 function sourceAct(url,title){const u=httpsUrl(url);return u?`<a class="act act-src" href="${esc(u)}" target="_blank" rel="noopener" aria-label="Fuente original: ${esc(title)} (abre en otra pestaña)"><span>Fuente original</span>${icons.link}</a>`:''}
 function shareAct(targetId,title,shareUrl){return `<button type="button" class="act act-share" data-share="${esc(targetId)}"${shareUrl?` data-share-url="${esc(shareUrl)}"`:''} data-share-title="${esc(title)}" aria-label="Compartir: ${esc(title)}">${icons.share}<span>Compartir</span></button><span class="share-feedback" role="status" aria-live="polite"></span>`}
 // `shareUrl` (stats fichas, #93): the pre-rendered share page that deep-links to the open ficha.
 function rowActions(open,url,targetId,title,shareUrl){return `<div class="row-acts" role="group" aria-label="Acciones"><button type="button" class="act act-open" ${open} aria-label="Ver ficha: ${esc(title)}"><span>Ver ficha</span>${icons.chev}</button>${sourceAct(url,title)}${shareAct(targetId,title,shareUrl)}</div>`}
 // The ficha carries the same set minus "Ver ficha" (it is the ficha), just under its header bar. A stats ficha
 // passes no targetId: its own "Compartir informe" (stats-ficha.js) is the share action, so it is not doubled.
 function fichaActions(url,targetId,title,extra=''){return `<div class="row-acts ficha-acts" role="group" aria-label="Acciones de la ficha">${sourceAct(url,title)}${targetId?shareAct(targetId,title):''}${extra}</div>`}
 // F2 sheet (Dirección 11-nov-2026): pull it down by its handle or top bar to close it, when its content is at the top.
 function sheetPull(d){if(!d)return;let y0=null,dy=0;const reduce=()=>root.matchMedia&&root.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const start=e=>{if(d.scrollTop>0||!e.touches||e.touches.length!==1)return;y0=e.touches[0].clientY;dy=0;d.style.transition='none'};
  const move=e=>{if(y0===null)return;dy=Math.max(0,e.touches[0].clientY-y0);d.style.transform=dy?`translateY(${dy}px)`:''};
  const end=()=>{if(y0===null)return;d.style.transition=reduce()?'none':'transform .18s ease-out';const close=dy>90;d.style.transform='';y0=null;if(close)d.close()};
  for(const sel of ['.sheet-grab','.detail-top'])d.querySelector(sel)?.addEventListener('touchstart',start,{passive:true});
  d.addEventListener('touchmove',move,{passive:true});d.addEventListener('touchend',end);d.addEventListener('touchcancel',end)}
 async function shareCard(button){let url;if(button.dataset.shareUrl)url=new URL(button.dataset.shareUrl,location.href);else{url=new URL(location.href);url.hash=button.dataset.share;// a shared piece opens its ficha, not only its row (Dirección 11-nov-2026)
 if(/^sig-/.test(button.dataset.share)){url.search='';url.searchParams.set('abrir','1')}}const payload={title:button.dataset.shareTitle,text:button.dataset.shareTitle,url:url.href},feedback=button.nextElementSibling,report=(state,message)=>{button.dataset.shareResult=state;button.title=message;button.setAttribute('aria-label',`${message}: ${button.dataset.shareTitle}`);if(feedback?.classList.contains('share-feedback'))feedback.textContent=message};try{if(navigator.share){await navigator.share(payload);report('shared','Compartido');return}if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(url.href);else{const field=document.createElement('textarea');field.value=url.href;field.setAttribute('readonly','');field.style.position='fixed';field.style.opacity='0';document.body.append(field);field.select();const copied=document.execCommand('copy');field.remove();if(!copied)throw new Error('copy failed')}report('copied','Enlace copiado')}catch(error){if(error?.name!=='AbortError')report('error','No se pudo compartir')}}

 // Inline undo (Dirección 28-oct, punto 3): no bar under the filters. When a row is about to leave its lane
 // (read in Pendientes, unread in Leídas), it stays a moment in place with "Leída · Deshacer" on the row itself,
 // then leaves. Focus on that pill pauses the timer. In Todas the row's own dot is the undo.
 const UNDO_MS=5000;
 function rowUndo(row,{label,onUndo,onExpire,ms=UNDO_MS}){
  if(!row)return null;clearRowUndo(row);
  const meta=row.querySelector('.card-meta')||row.querySelector('.item-body')||row;
  const pill=document.createElement('span');pill.className='row-undo';pill.setAttribute('role','status');
  pill.innerHTML=`<span>${esc(label)}</span><button type="button" class="row-undo-btn">Deshacer</button>`;
  meta.append(pill);
  let timer=null,done=false;
  // Focus on "Deshacer" pauses the timer and a pointer reaching the pill restarts it once. Focus returning to
  // the row's title after closing its ficha, or a resting mouse, must not keep the row in Pendientes forever.
  const busy=()=>pill.contains(document.activeElement);
  const arm=()=>{clearTimeout(timer);timer=setTimeout(()=>{if(done)return;if(busy()){arm();return}finish(false)},ms)};
  const finish=undo=>{if(done)return;done=true;clearTimeout(timer);pill.remove();delete row._rowUndo;(undo?onUndo:onExpire)?.()};
  pill.addEventListener('pointerenter',arm,{once:true});pill.addEventListener('focusout',()=>setTimeout(arm,0));
  pill.querySelector('button').onclick=e=>{e.stopPropagation();finish(true)};
  row._rowUndo={finish,cancel(){if(done)return;done=true;clearTimeout(timer);pill.remove();delete row._rowUndo}};
  arm();return row._rowUndo;
 }
 function clearRowUndo(row){row?._rowUndo?.cancel()}
 // Mark-all keeps its undo where the rows were: at the top of the feed (no bar under the filters).
 function feedUndo(host,{label,onUndo,ms=UNDO_MS*2}){
  if(!host)return null;host.querySelector('.feed-undo')?.remove();
  const p=document.createElement('p');p.className='feed-undo row-undo';p.setAttribute('role','status');
  p.innerHTML=`<span>${esc(label)}</span><button type="button" class="row-undo-btn">Deshacer</button>`;
  host.prepend(p);
  let timer=setTimeout(function tick(){if(p.contains(document.activeElement)){timer=setTimeout(tick,ms/2);return}p.remove()},ms);
  p.querySelector('button').onclick=()=>{clearTimeout(timer);p.remove();onUndo?.()};
  return p;
 }
 // The newsletter invitation is a slim row inside the feed, after the 7th row (or at its end), on both pages.
 const STRIP_AFTER=7;
 function placeStrip(host,rowSelector,fallback){const strip=document.querySelector('.newsletter-strip');if(!strip||!host)return;const rows=host.querySelectorAll(rowSelector),after=rows[Math.min(STRIP_AFTER,rows.length)-1];if(after)after.after(strip);else(fallback||host).append(strip)}
 // #readStatus is a screen-reader live region; the page shows it only while reads cannot be saved (data-read-volatile on <html>).
 if(root.AlicantoRead&&typeof root.AlicantoRead.subscribe==='function'&&root.document){const syncVolatile=()=>root.document.documentElement.toggleAttribute('data-read-volatile',!root.AlicantoRead.persistent);root.AlicantoRead.subscribe(syncVolatile);syncVolatile()}
 // Piece type (Dirección 11-nov-2026, V1): a small icon and its word at the start of the date line, so a reader sees at a
 // glance why rows differ (news, a Datos ficha, a norm) in Al día, Normativa and Datos. Global lists only news, so it has none.
 const TYPE_ICON={noticia:'<path d="M4 6h16M4 12h16M4 18h10"/>',datos:'<path d="M5 20V10M12 20V4M19 20v-7"/>',normativa:'<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',legal:'<path d="M3 21h18M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 9l9-5 9 5z"/>',insight:'<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0 0 12 3z"/>'};
 const TYPE_WORD={noticia:'Noticia',datos:'Datos',normativa:'Normativa',legal:'Legislación',insight:'Insight',fiscalizacion:'Fiscalización',global:'Global'};
 TYPE_ICON.fiscalizacion='<path d="M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/><path d="M9 12l2 2 4-4"/>';
 TYPE_ICON.global='<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.8 2.5 15.2 0 18M12 3c-2.5 2.8-2.5 15.2 0 18"/>';
 // Option B (Dirección 12-nov-2026): every row starts with a colour pill (icon + category, or the sub-type inside a
 // one-category section) and, beside it, «día · fuente». Under the title, at most one state chip of its own type.
 const MES=['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
 const MES_LARGO=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
 function shortDay(raw,now){const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(String(raw||''));if(!m)return '';const y=+m[1],year=(now||new Date()).getFullYear();return `${+m[3]} ${MES[+m[2]-1]}${y!==year?` ${y}`:''}`}
 // «ago 2026» / «jul–sep 2026» → «agosto 2026» / «julio–septiembre 2026» for the «Datos a …» chip.
 function longPeriod(p){return String(p||'').replace(/\b(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\b/g,x=>MES_LARGO[MES.indexOf(x)])}
 // `extra` (follow marker, «Corregido el …») sits beside the meta, never inside its ellipsis (review #193).
 function kicker(kind,label,meta,extra){const k=TYPE_ICON[kind]?kind:'noticia';return `<div class="rk"><span class="rk-pill rk-${k}"><svg class="ty-ic" viewBox="0 0 24 24" aria-hidden="true">${TYPE_ICON[k]}</svg>${esc(label||TYPE_WORD[k])}</span>${meta?`<span class="rk-meta">${meta}</span><span class="sr-only"> · </span>`:''}${extra?`<span class="rk-extra">${extra}</span>`:''}</div>`}
 function stateChip(text,tone){return text?`<span class="rk-state rk-st-${tone||'ok'}">${esc(text)}</span>`:''}
 function typeMark(kind){const k=TYPE_WORD[kind]?kind:'noticia';return `<span class="ty ty-${k}"><svg class="ty-ic" viewBox="0 0 24 24" aria-hidden="true">${TYPE_ICON[k]}</svg>${TYPE_WORD[k]}<span class="sr-only"> · </span></span>`}
 root.AlicantoBar={syncLanes,wireLanes,dropdown,selectionLabel,esc,icons,dotInner,dotLabel,dotButton,syncDot,sourceLink,miniShare,httpsUrl,sourceAct,shareAct,rowActions,fichaActions,shareCard,rowUndo,clearRowUndo,feedUndo,placeStrip,UNDO_MS,typeMark,sheetPull,kicker,stateChip,shortDay,longPeriod,TYPE_WORD};
})(typeof window!=='undefined'?window:globalThis);
