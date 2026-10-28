// Preview of the three row/ficha proposals (Dirección 28-oct, puntos 2 y 9: "haz las tres propuestas para verlas
// y elegir"). Off by default: with no ?propuesta= and nothing stored, this file changes nothing on the page.
// ?propuesta=a|b|c picks a variant and remembers it on this device; ?propuesta=off forgets it. Each variant is a
// body class (prop-a/-b/-c) plus proposals.css, decorating the rows and fichas that app.js / global.js /
// global-daily.js already render with the shared inbox-bar.js pieces, so Chile and Global stay homologated.
// Every variant keeps the fixed action order: Fuente original ↗ · Análisis · Compartir.
(function(){
 'use strict';
 const KEY='alicanto_propuesta',VALID=['a','b','c'];
 let param=null;try{param=new URLSearchParams(location.search).get('propuesta')}catch{}
 param=param==null?null:String(param).trim().toLowerCase();
 let stored=null;try{stored=localStorage.getItem(KEY)}catch{}
 if(param!=null){
  if(VALID.includes(param)){try{localStorage.setItem(KEY,param)}catch{}}
  else{try{localStorage.removeItem(KEY)}catch{}stored=null}
 }
 const opt=VALID.includes(param)?param:param==null&&VALID.includes(stored)?stored:null;
 if(!opt||typeof document==='undefined')return;
 const body=document.body,page=body.classList.contains('global-page')?'global':'chile';
 body.classList.add('prop-on',`prop-${opt}`);body.dataset.propuesta=opt;
 const Bar=window.AlicantoBar,esc=Bar.esc;
 const withParam=(href,o)=>{const u=new URL(href,location.href);u.searchParams.set('propuesta',o);u.hash='';return u.pathname.split('/').pop()+u.search};
 // If this browser cannot store the choice, Chile ↔ Global links carry it instead.
 if(VALID.includes(param))document.querySelectorAll('a[href="index.html"],a[href="./"],a[href="global.html"]').forEach(a=>a.setAttribute('href',withParam(a.getAttribute('href'),opt)));

 // Floating pill: Propuesta A · B · C, and × back to the current version.
 const pill=document.createElement('nav');pill.className='prop-switch';pill.setAttribute('aria-label','Propuestas de diseño');
 pill.innerHTML=`<span class="prop-switch-label">Propuesta</span>${VALID.map(o=>`<a href="${esc(withParam(location.href,o))}" data-prop="${o}" ${o===opt?'aria-current="true"':''} aria-label="Propuesta ${o.toUpperCase()}">${o.toUpperCase()}</a>`).join('')}<a class="prop-off" href="${esc(withParam(location.href,'off'))}" data-prop="off" aria-label="Volver a la versión actual" title="Volver a la versión actual">×</a>`;
 body.append(pill);

 const I={
  chev:'<svg class="mini-icon" aria-hidden="true" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6"></path></svg>',
  down:'<svg class="mini-icon" aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"></path></svg>',
  ext:Bar.icons.link,share:Bar.icons.share,
  analysis:'<svg class="mini-icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M4 19V9M10 19V5M16 19v-7M22 19H2"></path></svg>'
 };
 const firstSentence=t=>String(t||'').split(/(?<=\.)\s+(?=[A-ZÁÉÍÓÚ¿¡])/)[0];
 // Row data, read from the page state (top-level bindings of app.js / global.js) and the row itself.
 function info(row){
  const src=row.querySelector('.item-actions a.iconbtn')?.href||'';
  if(row.dataset.card&&typeof allSignals!=='undefined'){const s=allSignals.find(x=>idFor(x)===row.dataset.card);if(s)return{kind:'news',summary:firstSentence(s.card_what||s.what_happened),why:firstSentence(s.card_why||s.why_it_matters),url:src||s.source_url||''}}
  if(row.dataset.theme&&typeof themes!=='undefined'){const t=themes.find(x=>x.id===row.dataset.theme);if(t)return{kind:'theme',summary:firstSentence(t.global_finding||t.detail_body),why:'',url:src,analysis:!!(t.cross_analysis&&(t.cross_analysis.recurring_pattern||t.cross_analysis.decision_use))||!!t.chile_watch?.text}}
  if(row.dataset.daily)return{kind:'headline',summary:'',url:row.querySelector('a.title-open')?.href||''};
  return{kind:'other',summary:'',url:src};
 }
 // One labeled group, fixed order. "Análisis" only when Alicanto has one (Global themes with analytical context).
 function actionGroup(x,cls){
  const items=[];
  if(x.url)items.push(`<a class="act" href="${esc(x.url)}" target="_blank" rel="noopener">${I.ext}<span>Fuente original</span></a>`);
  if(x.analysis)items.push(`<button type="button" class="act" data-act="analysis">${I.analysis}<span>Análisis</span></button>`);
  items.push(`<button type="button" class="act" data-act="share">${I.share}<span>Compartir</span></button>`);
  return `<div class="act-group ${cls}" role="group" aria-label="Acciones">${items.join('')}</div>`;
 }
 const titleOf=row=>row.querySelector('.title-open');
 // Opens the ficha through the page's own handler (onclick set by app.js / global.js), never a copy of it.
 function openRow(row){const t=titleOf(row);if(!t)return;if(t.tagName==='A'){t.click();return}if(typeof t.onclick==='function')t.onclick.call(t,new MouseEvent('click'));else t.click()}
 async function shareRow(row,btn){const s=row.querySelector('.item-actions [data-share]');if(!s)return;await Bar.shareCard(s);const l=btn.querySelector('span');if(l&&s.dataset.shareResult&&s.dataset.shareResult!=='shared')l.textContent=s.title}

 // ── Rows ──
 const openRows=new Set();
 const decorate={
  a(row){const ext=row.dataset.daily!=null;row.classList.add('a-row');row.insertAdjacentHTML('beforeend',`<span class="a-chev" aria-hidden="true">${ext?I.ext:I.chev}</span>`);
   row.addEventListener('click',e=>{if(e.target.closest('button,a,.row-undo,.chip,select,input'))return;if(getSelection&&String(getSelection()).length)return;openRow(row)})},
  b(row){const x=info(row),meta=row.querySelector('.card-meta');if(!meta)return;row.classList.add('b-row');
   const ext=x.kind==='headline';
   const primary=ext?`<a class="b-primary" href="${esc(x.url||'#')}" target="_blank" rel="noopener" data-b-ext>Leer en la fuente ${I.ext}</a>`:`<button type="button" class="b-primary" data-b-open>Ver ficha ${I.chev}</button>`;
   const sec=ext?'':`<span class="b-sec">${x.url?`<a class="b-act" href="${esc(x.url)}" target="_blank" rel="noopener">${I.ext}<span>Fuente</span></a>`:''}<button type="button" class="b-act" data-b-share>${I.share}<span>Compartir</span></button></span>`;
   meta.insertAdjacentHTML('afterend',`<div class="b-actions">${primary}${sec}</div>`);
   row.querySelector('[data-b-open]')?.addEventListener('click',()=>openRow(row));
   row.querySelector('[data-b-ext]')?.addEventListener('click',()=>markDaily(row));
   row.querySelector('[data-b-share]')?.addEventListener('click',e=>shareRow(row,e.currentTarget))},
  c(row){const x=info(row),bodyEl=row.querySelector('.item-body');if(!bodyEl)return;row.classList.add('c-row');
   const key=row.id||row.dataset.card||row.dataset.theme||row.dataset.daily;
   row.insertAdjacentHTML('beforeend',`<button type="button" class="c-toggle" aria-expanded="false" aria-label="Ver resumen">${I.down}</button>`);
   const ext=x.kind==='headline';
   const lead=ext?'<p class="c-sum">Titular publicado por la fuente; Alicanto no lo resume. Se abre en su sitio.</p>':`${x.summary?`<p class="c-sum">${esc(x.summary)}</p>`:''}${x.why?`<p class="c-why">${esc(x.why)}</p>`:''}`;
   const primary=ext?`<a class="act primary" href="${esc(x.url||'#')}" target="_blank" rel="noopener" data-c-ext><span>Leer en la fuente</span>${I.ext}</a>`:`<button type="button" class="act primary" data-c-open><span>Ver ficha completa</span>${I.chev}</button>`;
   bodyEl.insertAdjacentHTML('beforeend',`<div class="c-panel" hidden>${lead}<div class="c-acts">${primary}${ext?'':actionGroup(x,'c-sec')}</div></div>`);
   const panel=row.querySelector('.c-panel'),tg=row.querySelector('.c-toggle');
   const set=open=>{panel.hidden=!open;row.classList.toggle('c-open',open);tg.setAttribute('aria-expanded',String(open));tg.setAttribute('aria-label',open?'Ocultar resumen':'Ver resumen');if(open)openRows.add(key);else openRows.delete(key)};
   const toggle=()=>set(panel.hidden);
   tg.addEventListener('click',toggle);
   // The title expands the row instead of opening the ficha (capture on the row runs before the title's own handler).
   row.addEventListener('click',e=>{const t=e.target.closest('.title-open');if(t&&row.contains(t)){e.preventDefault();e.stopPropagation();toggle()}},true);
   row.addEventListener('click',e=>{if(e.target.closest('button,a,.row-undo,.chip,.c-panel'))return;toggle()});
   row.querySelector('[data-c-open]')?.addEventListener('click',()=>openRow(row));
   row.querySelector('[data-c-ext]')?.addEventListener('click',()=>markDaily(row));
   row.querySelector('.c-sec [data-act="share"]')?.addEventListener('click',e=>shareRow(row,e.currentTarget));
   row.querySelector('.c-sec [data-act="analysis"]')?.addEventListener('click',()=>{openRow(row);setTimeout(()=>openAnalysis(document.getElementById('globalDetailBody')),0)});
   if(openRows.has(key))set(true)}
 };
 // "Al día afuera": opening the source marks the headline read, as tapping its title does today.
 function markDaily(row){if(!row.classList.contains('read'))row.querySelector('[data-daily-read]')?.click()}
 function scan(){document.querySelectorAll('#local article[data-card],#themes article[data-theme],#globalDailyRows article[data-daily]').forEach(r=>{if(r.dataset.prop)return;r.dataset.prop=opt;decorate[opt](r)})}

 // ── Ficha ──
 // A puts the group at the ficha footer, B on top of the ficha body; C keeps the current ficha (its row is the preview).
 // The group is rebuilt whenever the page rewrites the ficha's header bar (open, read toggle), so its links always
 // belong to the ficha on screen. The WATCH "Seguir" row and the unified title stay untouched inside the body.
 function openAnalysis(bodyEl){if(!bodyEl)return;const ds=[...bodyEl.querySelectorAll('details')];const d=ds.find(x=>/Contexto anal/i.test(x.querySelector('summary')?.textContent||''))||ds[0];if(d){d.open=true;d.scrollIntoView({block:'start',behavior:'smooth'})}}
 function fichaGroup(dialog,barEl,bodyEl){
  dialog.querySelector('.prop-ficha-actions')?.remove();
  if(!bodyEl.firstElementChild)return;
  const url=barEl.querySelector('a.iconbtn')?.href||'',analysis=dialog.id==='globalDetail'&&!!bodyEl.querySelector('details');
  const html=actionGroup({url,analysis},`prop-ficha-actions ${opt}-ficha-actions`);
  if(opt==='a')bodyEl.insertAdjacentHTML('afterend',html);else bodyEl.insertAdjacentHTML('beforebegin',html);
  const g=dialog.querySelector('.prop-ficha-actions');
  g.querySelector('[data-act="analysis"]')?.addEventListener('click',()=>openAnalysis(bodyEl));
  g.querySelector('[data-act="share"]')?.addEventListener('click',async e=>{const s=barEl.querySelector('[data-share]');if(!s)return;const l=e.currentTarget.querySelector('span');await Bar.shareCard(s);if(s.dataset.shareResult&&s.dataset.shareResult!=='shared')l.textContent=s.title});
 }
 if(opt!=='c')for(const [d,b,x] of [['signalDetail','detailBar','detailBody'],['globalDetail','globalDetailBar','globalDetailBody']]){
  const dialog=document.getElementById(d),barEl=document.getElementById(b),bodyEl=document.getElementById(x);
  if(dialog&&barEl&&bodyEl)new MutationObserver(()=>fichaGroup(dialog,barEl,bodyEl)).observe(barEl,{childList:true});
 }

 // ── Global identity ──
 if(page==='global'){
  if(opt==='b')document.querySelector('.brandbar')?.insertAdjacentHTML('afterend','<div class="b-band" role="note"><span>Global Premium</span><em>Inteligencia internacional seleccionada para decidir antes en Chile</em></div>');
  if(opt==='c')document.querySelector('.global-intro h1')?.insertAdjacentHTML('afterbegin','<span class="c-mark" aria-hidden="true">◆</span>');
 }
 scan();
 for(const id of ['local','themes','globalDailyRows']){const h=document.getElementById(id);if(h)new MutationObserver(scan).observe(h,{childList:true,subtree:true})}
})();
