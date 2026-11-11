// Normativa, phase 1 (Dirección, 11-nov-2026; mockup «2 · Cuenta regresiva arriba»). Data: data/normativa.json, built by
// src/radar_salud/normativa_index.py from the standing registry (no 90-day logic). Effective dates are literal from the
// norm; without one the norm is «en revisión» (Dirección's manual review). Groups are computed here against today, so a
// norm moves down as it enters into force without a rebuild. «Implementada» is a per-reader mark kept in this browser.
(function(){
'use strict';
const Bar=window.AlicantoBar||null;
const NC=window.AlicantoNormCard;
const {MES,MESL,fmt,ymd,D}=NC;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const Read=window.AlicantoRead||null;
let items=[];
const S={g:'all',month:null,q:'',emi:'',tema:'',open:new Set()};
const GROUPS=[['p30','Próximos 30 días'],['p30p','En más de 30 días'],['v30','Vigentes · últimos 30 días'],['vhist','Vigentes · histórico'],
 ['sin','Sin fecha · en revisión'],['impl','Implementadas'],['susp','Suspendidas'],['sinef','Derogadas o sin efecto']];
const PANEL=[['all','Todas',null],['p30','Próx. 30 días',['p30']],['p30p','Más de 30 días',['p30p']],['vig','Vigentes',['v30','vhist']],
 ['sin','Sin fecha',['sin']],['impl','Implementadas',['impl']],['susp','Suspendidas',['susp']],['sinef','Derogadas',['sinef']]];
const FOLD=['vhist','impl','susp','sinef'];
const vstat=NC.vstat,grp=NC.grp,effKey=NC.effKey;
function base(){const q=S.q.trim().toLowerCase();return items.filter(x=>(!q||[x.label,x.subject,x.tema,x.target].join(' ').toLowerCase().includes(q))&&(!S.emi||x.emisor===S.emi)&&(!S.tema||x.tema===S.tema))}
const keysOf=k=>k==='all'?null:(PANEL.find(p=>p[0]===k)||[])[2]||[k];
function shown(){const ks=keysOf(S.g);return base().filter(x=>(!ks||ks.includes(grp(x)))&&(!S.month||effKey(x).startsWith(S.month)))}
const when=(x,e)=>x.prec==='month'&&!(x.review&&x.review.kind==='date')?`${MESL[e.getMonth()]} ${e.getFullYear()}`:fmt(e);
const isRead=x=>Boolean(Read&&Read.readSet&&Read.readSet.has(x.signal_id||x.id));
// Same card as Al día (norma-card.js): read dot, date line, Ver ficha (the Al día ficha), Fuente original, Compartir.
function card(x){return `<article class="nm-item${isRead(x)?' read':''}" id="n-${esc(x.id)}" tabindex="-1">${NC.render(x,{read:isRead(x),readId:x.signal_id||x.id,openHref:x.ficha,dateLine:NC.dateLine(x),shareId:`n-${x.id}`,q:S.q.trim(),open:S.open.has(x.id)})}</article>`}
function counts(){const xs=base(),c={};for(const [k,,ks] of PANEL)c[k]=ks?xs.filter(x=>ks.includes(grp(x))).length:xs.length;return c}
function drawGroups(){const c=counts();document.getElementById('nmGroups').innerHTML=PANEL.map(([k,l])=>`<button type="button" data-g="${k}" aria-pressed="${S.g===k}"${c[k]||k==='all'?'':' class="zero"'}>${l}<b>${c[k]}</b></button>`).join('')}
function drawMonths(){const xs=base().filter(x=>!(x.review&&['susp','sinef'].includes(x.review.kind)));const keys=[...new Set(xs.map(effKey).filter(Boolean).map(k=>k.slice(0,7)))].sort();
 const cur=ymd(new Date()).slice(0,7),start=keys.filter(k=>k>=cur)[0]?Math.max(0,keys.findIndex(k=>k>=cur)-2):Math.max(0,keys.length-6),ks=keys.slice(start);
 const n=k=>xs.filter(x=>effKey(x).startsWith(k)).length,max=Math.max(1,...ks.map(n));
 document.getElementById('nmMonths').innerHTML=ks.map(k=>{const [y,m]=k.split('-').map(Number),c=n(k);return `<button type="button" class="nm-mo${k<cur?' past':''}${k===cur?' cur':''}" data-month="${k}" aria-pressed="${S.month===k}" aria-label="${MESL[m-1]} ${y}: ${c} entran en vigencia"><span class="m">${MES[m-1]} ${String(y).slice(2)}</span><span class="c">${c}</span><span class="bar"><i style="width:${(c/max*100).toFixed(0)}%"></i></span></button>`}).join('');
 document.getElementById('nmMonths').hidden=!ks.length}
function drawHero(){const xs=base().filter(x=>['p30','p30p'].includes(grp(x))).sort((a,b)=>vstat(a).days-vstat(b).days).slice(0,3);const h=document.getElementById('nmHero');
 h.innerHTML=xs.length?`<p class="nm-hero-h">Próximas entradas en vigencia</p><div class="nm-hero-row">${xs.map(x=>{const s=vstat(x);return `<a class="nm-hc${s.days<=30?' u':''}" href="#n-${esc(x.id)}" data-jump="${esc(x.id)}"><span class="d"><b>${s.days}</b><span>${s.days===1?'día':'días'}</span></span><span class="w">${when(x,s.e)}</span><span class="t">${esc(x.target||x.label)}</span><span class="s">${esc(x.emisor)} · ${esc(x.subject)}</span></a>`}).join('')}</div>`:'';h.hidden=!xs.length}
function drawCount(){const ch=[];const lab={...Object.fromEntries(PANEL.map(p=>[p[0],p[1]]))};if(S.g!=='all')ch.push(['g',lab[S.g]]);if(S.month){const [y,m]=S.month.split('-').map(Number);ch.push(['month',`${MESL[m-1]} ${y}`])}if(S.emi)ch.push(['emi',S.emi]);if(S.tema)ch.push(['tema',S.tema]);if(S.q.trim())ch.push(['q',`«${S.q.trim()}»`]);
 const n=(S.emi?1:0)+(S.tema?1:0)+(S.q.trim()?1:0);document.getElementById('nmFxN').textContent=n?` · ${n}`:'';
 document.getElementById('nmCount').innerHTML=`<span>${shown().length} de ${items.length} normas</span>${ch.map(([k,l])=>`<span class="nm-chip">${esc(l)}<button type="button" data-clear="${k}" aria-label="Quitar filtro ${esc(l)}">×</button></span>`).join('')}${ch.length>1?'<button type="button" class="nm-lnk" data-clear="all">Limpiar</button>':''}`}
function drawFeed(){const xs=shown(),by={};for(const x of xs)(by[grp(x)]=by[grp(x)]||[]).push(x);
 const sortIn=g=>(a,b)=>{const sa=vstat(a),sb=vstat(b);if(g==='p30'||g==='p30p')return sa.days-sb.days;if(g==='v30'||g==='vhist')return (sa.since-sb.since)||String(b.date).localeCompare(String(a.date));return String(b.date).localeCompare(String(a.date))};
 const html=GROUPS.map(([g,l])=>{const list=(by[g]||[]).sort(sortIn(g));
  if(!list.length){return S.g==='all'&&!S.month&&!S.q&&['impl','susp','sinef'].includes(g)?`<section class="nm-grp" data-g="${g}"><div class="nm-gh g-${g}"><h2>${l}</h2><span class="c">0</span></div><p class="nm-gempty">${g==='impl'?'Toca el círculo de una norma para marcarla como implementada.':'Ninguna por ahora. Se registran solo con la norma que lo dispone y su texto literal.'}</p></section>`:''}
  const h=`<div class="nm-gh g-${g}"><h2>${l}</h2><span class="c">${list.length}</span></div>`,body=`<div class="nm-list">${list.map(card).join('')}</div>`;
  if(FOLD.includes(g)&&S.g==='all'){const k='G:'+g;return `<details class="nm-grp" data-gk="${k}"${S.open.has(k)?' open':''}><summary>${h}</summary>${body}</details>`}
  return `<section class="nm-grp" data-g="${g}">${h}${body}</section>`}).join('');
 document.getElementById('nmFeed').innerHTML=html||'<p class="nm-empty">Ninguna norma coincide. Prueba con el número («3937») o quita un filtro.</p>'}
function draw(){drawHero();drawGroups();drawMonths();drawCount();drawFeed()}
function jumpTo(id){const el=document.getElementById('n-'+id);if(!el)return;const fold=el.closest('details.nm-grp');if(fold&&!fold.open){fold.open=true;S.open.add(fold.dataset.gk)}el.scrollIntoView({block:'center'});el.classList.add('nm-hit');setTimeout(()=>el.classList.remove('nm-hit'),1600)}
function wire(){
 document.addEventListener('click',e=>{const t=e.target.closest('[data-g],[data-month],[data-clear],[data-impl],[data-jump],[data-share],[data-read]');if(!t||!t.closest('.nm-wrap'))return;const d=t.dataset;
  if(d.share!==undefined&&Bar){Bar.shareCard(t);return}
  if(d.read!==undefined&&t.closest('#nmFeed')){if(Read){const id=d.read;Read.set(id,!Read.readSet.has(id)).then(draw)}return}
  if(d.g&&t.closest('#nmGroups')){S.g=S.g===d.g&&d.g!=='all'?'all':d.g;draw()}
  else if(d.month){S.month=S.month===d.month?null:d.month;draw()}
  else if(d.clear){if(d.clear==='all')Object.assign(S,{g:'all',month:null,q:'',emi:'',tema:''});else S[d.clear]=d.clear==='g'?'all':d.clear==='month'?null:'';syncInputs();draw()}
  else if(d.impl){NC.toggleImpl(d.impl);draw();const b=document.querySelector(`[data-impl="${CSS.escape(d.impl)}"]`);if(b)b.focus()}
  else if(d.jump){e.preventDefault();jumpTo(d.jump)}});
 document.addEventListener('toggle',e=>{const el=e.target;if(!el.dataset)return;const k=el.dataset.id||el.dataset.gk;if(k){el.open?S.open.add(k):S.open.delete(k)}},true);
 const q=document.getElementById('nmQ');q.addEventListener('input',()=>{S.q=q.value;draw()});
 document.getElementById('nmEmi').addEventListener('change',e=>{S.emi=e.target.value;draw()});
 document.getElementById('nmTema').addEventListener('change',e=>{S.tema=e.target.value;draw()});
 window.addEventListener('hashchange',()=>{const id=decodeURIComponent(location.hash.slice(1)).replace(/^n-/,'');if(id)jumpTo(id)})}
function syncInputs(){document.getElementById('nmQ').value=S.q;document.getElementById('nmEmi').value=S.emi;document.getElementById('nmTema').value=S.tema}
function start(d){items=Array.isArray(d&&d.items)?d.items.filter(x=>x&&x.id&&x.label):[];
 const temas=[...new Set(items.map(x=>x.tema).filter(Boolean))].sort();document.getElementById('nmTema').insertAdjacentHTML('beforeend',temas.map(t=>`<option value="${esc(t)}">${esc(t)}</option>`).join(''));
 draw();const id=decodeURIComponent(location.hash.slice(1)).replace(/^n-/,'');if(id)requestAnimationFrame(()=>jumpTo(id))}
if(typeof document!=='undefined'&&document.getElementById('nmFeed')){wire();if(Read&&Read.subscribe)Read.subscribe(()=>{if(items.length)draw()});(Read&&Read.ready?Read.ready:Promise.resolve()).then(()=>fetch('data/normativa.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('normativa');return r.json()})).then(start)).catch(()=>{document.getElementById('nmFeed').innerHTML='<p class="nm-empty">No se pudo cargar la normativa.</p>'})}

})();
