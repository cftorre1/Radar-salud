// Statistics ficha (Dirección 28-oct-2026), mirrors Insight format A: kicker → headline → dek → KPI strip →
// tabs (charts + their own analysis) → Lectura Alicanto → Qué mirar (≤ 2) → 'Notas y fuentes' (collapsed).
// Every number arrives formatted or as a value from the evidence package; this file only lays out.
(function(root){
 const C={ink:'#1D3345',ink70:'#4F6170',ink50:'#6B7884',axis:'#B9B3A6',accent:'#C37C37'};
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const arr=x=>Array.isArray(x)?x:[];
 const nf=v=>new Intl.NumberFormat('es-CL').format(Math.abs(Number(v)));
 const sg=v=>(Number(v)>0?'+':Number(v)<0?'−':'')+nf(v);
 const https=u=>/^https:\/\//.test(String(u||''));
 function fmtDay(raw){const d=new Date(/^\d{4}-\d{2}-\d{2}$/.test(raw||'')?raw+'T12:00:00Z':raw);return Number.isNaN(d.getTime())?esc(raw):new Intl.DateTimeFormat('es-CL',{day:'numeric',month:'short',year:'numeric',timeZone:'America/Santiago'}).format(d)}
 function table(t){if(!t||!arr(t.columns).length)return'';return`<table class="sf-table"><thead><tr>${t.columns.map((c,i)=>`<th scope="col" class="${i?'n':''}">${esc(c)}</th>`).join('')}</tr></thead><tbody>${arr(t.rows).map(r=>`<tr>${arr(r).map((c,i)=>i?`<td class="n">${esc(c)}</td>`:`<th scope="row">${esc(c)}</th>`).join('')}</tr>`).join('')}</tbody></table>`}
 // Signed columns: bars hang from (or rise to) the zero line; the emphasized period takes the accent.
 function columns(c){
  const rows=arr(c.rows).filter(r=>Number.isFinite(Number(r.value)));if(!rows.length)return'';
  const vals=rows.map(r=>Number(r.value)),hi=Math.max(0,...vals),lo=Math.min(0,...vals),span=(hi-lo)||1,W=360,top=34,H=150,zero=top+H*hi/span,bw=Math.min(40,(W-20)/rows.length-10),gap=(W-20-rows.length*bw)/Math.max(1,rows.length-1);
  const peak=vals.reduce((a,v,i)=>Math.abs(v)>Math.abs(vals[a])?i:a,0);
  let s=`<line x1="10" y1="${zero.toFixed(1)}" x2="${W}" y2="${zero.toFixed(1)}" stroke="${C.axis}"/><text x="0" y="${(zero+4).toFixed(1)}" font-size="11" fill="${C.ink50}">0</text>`;
  rows.forEach((r,i)=>{const v=Number(r.value),x=10+i*(bw+gap),h=Math.max(Math.abs(v)/span*H,2),y=v<0?zero:zero-h,last=Boolean(r.emphasis);
   s+=`<g class="sf-mark"><title>${esc(r.label)}: ${sg(v)}</title><rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="3" fill="${last?C.accent:C.ink}"/></g>`;
   s+=`<text x="${(x+bw/2).toFixed(1)}" y="${(v<0?zero-8:zero+16).toFixed(1)}" font-size="12" text-anchor="middle" fill="${C.ink70}">${esc(r.label)}</text>`;
   if(last||i===peak||i===0)s+=`<text x="${(x+bw/2).toFixed(1)}" y="${(v<0?y+h+15:y-6).toFixed(1)}" font-size="${last?13.5:12}" font-weight="${last?700:500}" text-anchor="middle" fill="${C.ink}">${sg(v)}</text>`});
  const desc=rows.map(r=>`${r.label} ${sg(r.value)}`).join(', ');
  return`<svg viewBox="0 0 ${W} ${top+H+44}" role="img" aria-label="${esc(`${c.subtitle||c.headline}: ${desc}.`)}">${s}${c.legend?`<text x="0" y="${top+H+40}" font-size="11" fill="${C.ink50}">${esc(c.legend)}</text>`:''}</svg>`;
 }
 // Diverging bars by actor: ink loses, accent gains; bold labels for ≥ 5.000 personas.
 function diverging(c){
  const rows=arr(c.rows).filter(r=>Number.isFinite(Number(r.value)));if(!rows.length)return'';
  const vals=rows.map(r=>Number(r.value)),lo=Math.min(0,...vals),hi=Math.max(0,...vals),W=360,row=26,top=8,x0=162,x1=356,k=(x1-x0)/((hi-lo)||1),z=x0+(-lo)*k,H=top+rows.length*row+24;
  let s=`<line x1="${z.toFixed(1)}" y1="${top-4}" x2="${z.toFixed(1)}" y2="${top+rows.length*row}" stroke="${C.axis}"/>`;
  rows.forEach((r,i)=>{const v=Number(r.value),y=top+i*row,w=Math.max(Math.abs(v)*k,2),x=v<0?z-w:z,strong=Math.abs(v)>=5000;
   s+=`<text x="0" y="${y+15}" font-size="12.5" fill="${C.ink}">${esc(r.label)}</text><text x="${x0-8}" y="${y+15}" font-size="12.5" text-anchor="end" font-weight="${strong?700:400}" fill="${C.ink}">${sg(v)}</text>`;
   s+=`<g class="sf-mark"><title>${esc(r.label)}: ${sg(v)}</title><rect x="${x.toFixed(1)}" y="${y+5}" width="${w.toFixed(1)}" height="14" rx="3" fill="${v<0?C.ink:C.accent}"/></g>`});
  const desc=rows.map(r=>`${r.label} ${sg(r.value)}`).join(', ');
  return`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${c.subtitle||c.headline}: ${desc}.`)}">${s}${c.legend?`<text x="0" y="${H-4}" font-size="11" fill="${C.ink50}">${esc(c.legend)}</text>`:''}</svg>`;
 }
 const dec=(v,d)=>Number(v).toLocaleString('es-CL',{minimumFractionDigits:d,maximumFractionDigits:d}).replace(/^-/,'−');
 // Line for stocks and ratios: the axis does not start at zero (stated in the subtitle); last point in accent.
 function line(c){
  const rows=arr(c.rows).filter(r=>Number.isFinite(Number(r.value)));if(rows.length<2)return'';const d=Number.isInteger(c.digits)?c.digits:0;
  const vals=rows.map(r=>Number(r.value)),lo=Math.min(...vals),hi=Math.max(...vals),pad=(hi-lo)*.15||Math.abs(hi)*.01||1,min=lo-pad,max=hi+pad,W=360,top=24,H=130,x=i=>20+i*(W-40)/(rows.length-1),y=v=>top+(max-v)/(max-min)*H;
  const pts=rows.map((r,i)=>`${x(i).toFixed(1)},${y(Number(r.value)).toFixed(1)}`).join(' ');
  let s=`<polyline points="${pts}" fill="none" stroke="${C.ink}" stroke-width="2.5"/>`;
  rows.forEach((r,i)=>{const v=Number(r.value),last=i===rows.length-1,first=i===0;s+=`<g class="sf-mark"><title>${esc(r.label)}: ${dec(v,d)}</title><circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="${last?5:3.5}" fill="${last?C.accent:C.ink}"/></g><text x="${x(i).toFixed(1)}" y="${top+H+22}" font-size="11.5" text-anchor="${first&&rows.length>1&&String(r.label).length>4?'start':last&&String(r.label).length>4?'end':'middle'}" fill="${C.ink70}">${esc(r.label)}</text>`;if(first||last)s+=`<text x="${x(i).toFixed(1)}" y="${(y(v)-10).toFixed(1)}" font-size="${last?13:12}" font-weight="${last?700:500}" text-anchor="${first?'start':'end'}" fill="${C.ink}">${dec(v,d)}</text>`});
  return`<svg viewBox="0 0 ${W} ${top+H+30}" role="img" aria-label="${esc(`${c.subtitle||c.headline}: ${rows.map(r=>`${r.label} ${dec(r.value,d)}`).join(', ')}.`)}">${s}</svg>`;
 }
 // Dot plot vs. the base period: dot = current, ring = base.
 function dots(c){
  const rows=arr(c.rows).filter(r=>Number.isFinite(Number(r.value)));if(!rows.length)return'';const d=Number.isInteger(c.digits)?c.digits:1;
  // Right margin sized to the longest value label, so '50.515' never runs past the viewBox at 390 px.
  const lab=Math.max(...rows.map(r=>(dec(r.value,d)+(c.unit==='%'?'%':'')).length))*7.4+14;
  const all=rows.flatMap(r=>[Number(r.value),Number(r.base)]).filter(Number.isFinite),max=Math.max(...all)||1,W=360,row=26,x0=118,x1=W-lab,X=v=>x0+v/max*(x1-x0),H=8+rows.length*row+6;
  let s=`<line x1="${x0}" y1="4" x2="${x0}" y2="${H-6}" stroke="${C.axis}"/>`;
  rows.forEach((r,i)=>{const v=Number(r.value),b=Number(r.base),y=8+i*row+9;s+=`<text x="0" y="${y+4}" font-size="12.5" fill="${C.ink}">${esc(r.label)}</text>`;
   if(Number.isFinite(b))s+=`<line x1="${X(Math.min(v,b)).toFixed(1)}" y1="${y}" x2="${X(Math.max(v,b)).toFixed(1)}" y2="${y}" stroke="${C.axis}" stroke-width="2"/><circle cx="${X(b).toFixed(1)}" cy="${y}" r="5" fill="#fff" stroke="${C.ink50}" stroke-width="1.5"/>`;
   s+=`<g class="sf-mark"><title>${esc(r.label)}: ${dec(v,d)}${c.unit==='%'?'%':''}</title><circle cx="${X(v).toFixed(1)}" cy="${y}" r="5.5" fill="${Number.isFinite(b)&&v>b?C.accent:C.ink}"/></g><text x="${(X(Math.max(v,Number.isFinite(b)?b:v))+10).toFixed(1)}" y="${y+4}" font-size="12" fill="${C.ink}">${dec(v,d)}${c.unit==='%'?'%':''}</text>`});
  return`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${c.subtitle||c.headline}: ${rows.map(r=>`${r.label} ${dec(r.value,d)}`).join(', ')}.`)}">${s}</svg>`;
 }
 // Plain horizontal bars for non-negative values: counts (integer) or, with c.digits, rates and percentages (F4/F6).
 function bars(c){
  const rows=arr(c.rows).filter(r=>Number.isFinite(Number(r.value)));if(!rows.length)return'';const max=Math.max(...rows.map(r=>Math.abs(Number(r.value))))||1,W=360,row=30,x0=128,L=160,H=rows.length*row+8;
  const fv=v=>Number.isInteger(c.digits)?dec(v,c.digits)+(c.unit==='%'?'%':''):nf(v);
  const s=rows.map((r,i)=>{const v=Number(r.value),w=Math.max(Math.abs(v)/max*L,2),y=4+i*row;return`<text x="0" y="${y+15}" font-size="12.5" fill="${C.ink}">${esc(r.label)}</text><g class="sf-mark"><title>${esc(r.label)}: ${fv(v)}</title><rect x="${x0}" y="${y+3}" width="${w.toFixed(1)}" height="16" rx="3" fill="${r.emphasis?C.accent:'#CFC9BC'}"/></g><text x="${(x0+w+6).toFixed(1)}" y="${y+15}" font-size="12.5" font-weight="${r.emphasis?700:500}" fill="${C.ink}">${fv(v)}</text>`}).join('');
  return`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${c.subtitle||c.headline}: ${rows.map(r=>`${r.label} ${fv(r.value)}`).join(', ')}.`)}">${s}</svg>`;
 }
 const FORMS={diverging,line,dots,bars,columns_signed:columns};
 function chart(c,i){const svg=(FORMS[c.form]||columns)(c);if(!svg)return'';return`<figure class="sf-chart" data-chart="${esc(c.id||i)}"><h3>${esc(c.headline)}</h3>${c.subtitle?`<p class="sf-sub">${esc(c.subtitle)}</p>`:''}${svg}<details class="sf-data"><summary>Ver datos del gráfico</summary>${table(c.table)}</details>${c.source?`<p class="sf-src">${esc(c.source)}</p>`:''}</figure>`}
 const PROV={C:'Capturada por Alicanto: archivo y hash en el repositorio'};
 function kpi(k){return`<div class="sf-kpi"><p class="sf-lab">${esc(k.label)}</p><p class="sf-val">${esc(k.value)}${k.prov?`<span class="sf-prov" title="${esc(PROV[k.prov]||k.prov)}" aria-label="${esc(PROV[k.prov]||k.prov)}">${esc(k.prov)}</span>`:''}</p>${arr(k.lines).map(x=>`<p class="sf-delta">${esc(x)}</p>`).join('')}${k.badge?`<span class="sf-badge ${k.badge_kind==='crossed'?'':'muted'}">${esc(k.badge)}</span>`:''}</div>`}
 function dek(f){let d=esc(f.dek||'');if(f.dek_emphasis&&String(f.dek).includes(f.dek_emphasis))d=d.replace(esc(f.dek_emphasis),`<strong>${esc(f.dek_emphasis)}</strong>`);return d}
 // Tabs (Dirección 28-oct 04:59): one theme per panel; arrow keys move between tabs (WAI-ARIA tabs pattern).
 let seq=0;
 function tabs(f){
  const ts=arr(f.tabs).filter(t=>t&&t.label);
  if(!ts.length)return arr(f.charts).length?`<section class="sf-charts" aria-label="Gráficos">${arr(f.charts).map(chart).join('')}</section>`:'';
  const base=`sf${++seq}`;
  const list=ts.map((t,i)=>`<button type="button" role="tab" class="sf-tab" id="${base}-t${i}" aria-controls="${base}-p${i}" aria-selected="${i===0}" tabindex="${i===0?0:-1}" data-sf-tab="${i}">${esc(t.label)}${t.status==='pendiente'?' <span class="sf-pending">pendiente</span>':''}</button>`).join('');
  const panels=ts.map((t,i)=>`<section role="tabpanel" class="sf-panel" id="${base}-p${i}" aria-labelledby="${base}-t${i}" tabindex="0" ${i===0?'':'hidden'}>${arr(t.text).map(x=>`<p class="sf-tab-text">${esc(x)}</p>`).join('')}${arr(t.charts).length?`<div class="sf-charts">${arr(t.charts).map(chart).join('')}</div>`:''}${arr(t.links).filter(l=>https(l.url)).length?`<ul class="sf-links">${arr(t.links).filter(l=>https(l.url)).map(l=>`<li><a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a></li>`).join('')}</ul>`:''}</section>`).join('');
  return`<section class="sf-tabs" aria-label="Temas de la ficha"><div class="sf-tablist" role="tablist" aria-label="Temas">${list}</div>${panels}</section>`;
 }
 function selectTab(btn,focus){const list=btn.closest('[role=tablist]'),host=list.parentElement;list.querySelectorAll('[role=tab]').forEach(b=>{const on=b===btn;b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;const p=host.querySelector('#'+CSS.escape(b.getAttribute('aria-controls')));if(p)p.hidden=!on});if(focus)btn.focus()}
 function render(f,opts={}){
  if(!f||f.status!=='PASS'||!f.headline)return'<p>Ficha no disponible.</p>';
  const lect=f.lectura&&f.lectura.status==='pass'&&f.lectura.text?f.lectura.text:null;
  const sources=arr(f.sources).filter(s=>https(s.url));
  const share=opts.shareId?`<p class="sf-actions"><button type="button" class="sf-share" data-ficha-share="${esc(opts.shareId)}" data-share-url="${esc(opts.shareUrl||'')}" data-share-title="${esc(f.headline)}">Compartir informe</button><span class="sf-share-status" role="status" aria-live="polite"></span></p>`:'';
  return`<article class="sf" data-family="${esc(f.family)}" data-period="${esc(f.period)}">`+
   `<p class="sf-kicker">${esc(f.kicker)}${f.kicker_meta?` · <span>${esc(f.kicker_meta)}</span>`:''}${f.featured?' <span class="sf-featured">Destacada</span>':''}</p>`+
   `<h2 id="detailTitle" class="sf-headline">${esc(f.headline)}</h2>`+
   `<p class="sf-dek">${dek(f)}</p>${share}`+
   `<section class="sf-kpis" aria-label="Indicadores clave">${arr(f.kpis).map(kpi).join('')}</section>`+
   tabs(f)+
   // Dirección 28-oct 08:20: each tab carries its own analysis, so 'Qué muestran los datos' is not a separate
   // section unless the ficha predates that layout; notes, sources and the machine note sit behind one toggle.
   (f.facts?.rendered_in_tabs||!arr(f.facts?.paragraphs).length?'':`<section class="sf-facts"><h3>${esc(f.facts?.heading||'Qué muestran los datos')}</h3>${arr(f.facts?.paragraphs).map(p=>`<p>${esc(p)}</p>`).join('')}</section>`)+
   (lect?`<section class="sf-reading"><h3>Lectura Alicanto</h3><p>${esc(lect)}</p></section>`:'')+
   (arr(f.watch).length?`<aside class="sf-watch"><h3>Qué mirar</h3><ol>${arr(f.watch).slice(0,2).map(w=>`<li><strong>${esc(w.headline)}</strong> ${esc(w.explanation)}</li>`).join('')}</ol></aside>`:'')+
   `<details class="sf-notes"><summary>Notas y fuentes</summary>${arr(f.notes).length?`<h3>Notas sobre la evidencia</h3><ol>${arr(f.notes).map(n=>`<li>${esc(n.text)}</li>`).join('')}</ol>`:''}`+
   `<h3>Fuentes</h3><ul>${sources.map(s=>`<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a> <span class="sf-role">· ${esc(s.role||'')}</span><br><code>sha256 ${esc(String(s.sha256||'').slice(0,12))}… · ${esc(s.locator||'')}${s.fetched_at?` · capturado ${fmtDay(String(s.fetched_at).slice(0,10))}`:''}</code></li>`).join('')}</ul>`+
   (f.machine_note?`<p class="sf-machine">${esc(f.machine_note)}</p>`:'')+`</details></article>`;
 }
 // "Compartir informe": stable deep link back to Alicanto; Web Share API with copy-link fallback. No email.
 async function shareFicha(button){
  const status=button.parentElement?.querySelector('.sf-share-status');const say=m=>{if(status)status.textContent=m};
  // Prefer the pre-rendered share page (OG title/description/image) that redirects to the ficha.
  let url;if(button.dataset.shareUrl){url=new URL(button.dataset.shareUrl,root.location.href)}else{url=new URL(root.location.href);url.hash=button.dataset.fichaShare}
  const data={title:button.dataset.shareTitle,text:button.dataset.shareTitle,url:url.href};
  try{if(root.navigator?.share){await root.navigator.share(data);say('Informe compartido.');return}}catch(e){if(e&&e.name==='AbortError')return}
  try{await root.navigator.clipboard.writeText(url.href);say('Enlace copiado.')}catch{say(`Copia este enlace: ${url.href}`)}
 }
 if(root.document){
  root.document.addEventListener('click',e=>{const b=e.target.closest?.('[data-ficha-share]');if(b){e.preventDefault();shareFicha(b);return}const t=e.target.closest?.('[data-sf-tab]');if(t)selectTab(t,false)});
  root.document.addEventListener('keydown',e=>{const t=e.target.closest?.('[data-sf-tab]');if(!t||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;const all=[...t.parentElement.querySelectorAll('[data-sf-tab]')],i=all.indexOf(t);const n=e.key==='Home'?0:e.key==='End'?all.length-1:(i+(e.key==='ArrowRight'?1:-1)+all.length)%all.length;e.preventDefault();selectTab(all[n],true)});
 }
 // Public correction (CLAUDE.md rule 6): a short dated mark on the row ("Corregido el 28 oct"), the same date label as
 // the detail note; the export writes it as correction.label.
 const MON=['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
 function correctionLabel(c){if(c.label)return c.label;const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(String(c.corrected_at||''));return m?`${Number(m[3])} ${MON[Number(m[2])-1]}`:''}
 function correctionTag(s){const c=s&&s.statistical_view&&s.statistical_view.correction;if(!c||!c.corrected_at)return'';const label=correctionLabel(c);return label?` <span class="tag correction-tag" title="${esc(c.text||'')}">Corregido el ${esc(label)}</span>`:''}
 root.AlicantoFicha={render,shareFicha,correctionTag,correctionLabel};
})(typeof window!=='undefined'?window:globalThis);
