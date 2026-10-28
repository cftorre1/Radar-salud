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
 function miniShare(targetId,title){return `<button type="button" class="iconbtn sharebtn" data-share="${esc(targetId)}" data-share-title="${esc(title)}" aria-label="Compartir: ${esc(title)}" title="Compartir">${icons.share}</button><span class="share-feedback" role="status" aria-live="polite"></span>`}
 function rowActions(url,targetId,title){return `<span class="item-actions">${sourceLink(url)}${miniShare(targetId,title)}</span>`}
 async function shareCard(button){const url=new URL(location.href);url.hash=button.dataset.share;const payload={title:button.dataset.shareTitle,text:button.dataset.shareTitle,url:url.href},feedback=button.nextElementSibling,report=(state,message)=>{button.dataset.shareResult=state;button.title=message;button.setAttribute('aria-label',`${message}: ${button.dataset.shareTitle}`);if(feedback?.classList.contains('share-feedback'))feedback.textContent=message};try{if(navigator.share){await navigator.share(payload);report('shared','Compartido');return}if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(url.href);else{const field=document.createElement('textarea');field.value=url.href;field.setAttribute('readonly','');field.style.position='fixed';field.style.opacity='0';document.body.append(field);field.select();const copied=document.execCommand('copy');field.remove();if(!copied)throw new Error('copy failed')}report('copied','Enlace copiado')}catch(error){if(error?.name!=='AbortError')report('error','No se pudo compartir')}}

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
 root.AlicantoBar={syncLanes,wireLanes,dropdown,selectionLabel,esc,icons,dotInner,dotLabel,dotButton,syncDot,sourceLink,miniShare,rowActions,shareCard,rowUndo,clearRowUndo,feedUndo,placeStrip,UNDO_MS};
})(typeof window!=='undefined'?window:globalThis);
