// Statistics ficha. Dirección 29-oct-2026 approved option "C→B": the ficha opens as an index of its topics (label,
// one-line reading, sparkline); a topic opens in topic mode: sticky "Ver: <tema> n/N ▾" picker with ‹ ›, the hero chart
// first, then that topic's dek, KPI cards and other charts, and "Siguiente tema" / "Todos los temas" at the foot.
// Deep links: #sig-<id>&tema=<topic> (#tema=<topic> when the ficha has no signal id), so a copied URL reopens the ficha
// on that topic. Entering a topic from the index pushes a history entry, switching topics replaces it, and Back
// returns to the index. Every number arrives formatted or as a value from the evidence package; this file only lays out.
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
  let s=`<line x1="10" y1="${zero.toFixed(1)}" x2="${W}" y2="${zero.toFixed(1)}" stroke="${C.axis}"/><text x="1.5" y="${(zero+4).toFixed(1)}" font-size="11" fill="${C.ink50}">0</text>`;
  rows.forEach((r,i)=>{const v=Number(r.value),x=10+i*(bw+gap),h=Math.max(Math.abs(v)/span*H,2),y=v<0?zero:zero-h,last=Boolean(r.emphasis);
   s+=`<g class="sf-mark"><title>${esc(r.label)}: ${sg(v)}</title><rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="3" fill="${last?C.accent:C.ink}"/></g>`;
   s+=`<text x="${(x+bw/2).toFixed(1)}" y="${(v<0?zero-8:zero+16).toFixed(1)}" font-size="12" text-anchor="middle" fill="${C.ink70}">${esc(r.label)}</text>`;
   if(last||i===peak||i===0)s+=`<text x="${(x+bw/2).toFixed(1)}" y="${(v<0?y+h+15:y-6).toFixed(1)}" font-size="${last?13.5:12}" font-weight="${last?700:500}" text-anchor="middle" fill="${C.ink}">${sg(v)}</text>`});
  const desc=rows.map(r=>`${r.label} ${sg(r.value)}`).join(', ');
  return`<svg viewBox="0 0 ${W} ${top+H+44}" role="img" aria-label="${esc(`${c.subtitle||c.headline}: ${desc}.`)}">${s}${c.legend?`<text x="1.5" y="${top+H+40}" font-size="11" fill="${C.ink50}">${esc(c.legend)}</text>`:''}</svg>`;
 }
 // Diverging bars by actor: ink loses, accent gains; bold labels for ≥ 5.000 personas.
 function diverging(c){
  const rows=arr(c.rows).filter(r=>Number.isFinite(Number(r.value)));if(!rows.length)return'';
  const vals=rows.map(r=>Number(r.value)),lo=Math.min(0,...vals),hi=Math.max(0,...vals),W=360,row=26,top=8,x0=162,x1=356,k=(x1-x0)/((hi-lo)||1),z=x0+(-lo)*k,H=top+rows.length*row+24;
  let s=`<line x1="${z.toFixed(1)}" y1="${top-4}" x2="${z.toFixed(1)}" y2="${top+rows.length*row}" stroke="${C.axis}"/>`;
  rows.forEach((r,i)=>{const v=Number(r.value),y=top+i*row,w=Math.max(Math.abs(v)*k,2),x=v<0?z-w:z,strong=Math.abs(v)>=5000;
   s+=`<text x="1.5" y="${y+15}" font-size="12.5" fill="${C.ink}">${esc(r.label)}</text><text x="${x0-8}" y="${y+15}" font-size="12.5" text-anchor="end" font-weight="${strong?700:400}" fill="${C.ink}">${sg(v)}</text>`;
   s+=`<g class="sf-mark"><title>${esc(r.label)}: ${sg(v)}</title><rect x="${x.toFixed(1)}" y="${y+5}" width="${w.toFixed(1)}" height="14" rx="3" fill="${v<0?C.ink:C.accent}"/></g>`});
  const desc=rows.map(r=>`${r.label} ${sg(r.value)}`).join(', ');
  return`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${c.subtitle||c.headline}: ${desc}.`)}">${s}${c.legend?`<text x="1.5" y="${H-4}" font-size="11" fill="${C.ink50}">${esc(c.legend)}</text>`:''}</svg>`;
 }
 const dec=(v,d)=>Number(v).toLocaleString('es-CL',{minimumFractionDigits:d,maximumFractionDigits:d}).replace(/^-/,'−');
 // Line for stocks and ratios: the axis does not start at zero; last point in accent.
 function line(c){
  const rows=arr(c.rows).filter(r=>Number.isFinite(Number(r.value)));if(rows.length<2)return'';const d=Number.isInteger(c.digits)?c.digits:0;
  const vals=rows.map(r=>Number(r.value)),lo=Math.min(...vals),hi=Math.max(...vals),pad=(hi-lo)*.15||Math.abs(hi)*.01||1,min=lo-pad,max=hi+pad,W=360,top=24,H=130,x=i=>20+i*(W-40)/(rows.length-1),y=v=>top+(max-v)/(max-min)*H;
  const pts=rows.map((r,i)=>`${x(i).toFixed(1)},${y(Number(r.value)).toFixed(1)}`).join(' ');
  let s=`<polyline points="${pts}" fill="none" stroke="${C.ink}" stroke-width="2.5"/>`;
  // Axis labels thin out when they would collide (e.g. 12 quarters 'T2 2026' at 390 px): every 2nd, 3rd, 4th or 6th,
  // counted back from the last point so the latest period is always labelled. Short monthly labels (F1) all fit: unchanged.
  const lw=Math.max(...rows.map(r=>String(r.label).length))*6.6+6,slot=(W-40)/(rows.length-1),step=[1,2,3,4,6,12].find(k=>slot*k>=lw)||Math.ceil(lw/slot),shown=i=>(rows.length-1-i)%step===0;
  rows.forEach((r,i)=>{const v=Number(r.value),last=i===rows.length-1,first=i===0;s+=`<g class="sf-mark"><title>${esc(r.label)}: ${dec(v,d)}</title><circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="${last?5:3.5}" fill="${last?C.accent:C.ink}"/></g>`;if(shown(i))s+=`<text class="sf-xlab" x="${x(i).toFixed(1)}" y="${top+H+22}" font-size="11.5" text-anchor="${first&&rows.length>1&&String(r.label).length>4?'start':last&&String(r.label).length>4?'end':'middle'}" fill="${C.ink70}">${esc(r.label)}</text>`;
   // Dirección 29-oct: when the series descends into the last point, its label goes below the point, so it never
   // sits on the line ('0,603').
   const down=last&&i>0&&v<Number(rows[i-1].value);
   if(first||last)s+=`<text class="${last?'sf-lastlab':'sf-firstlab'}" x="${x(i).toFixed(1)}" y="${(down?y(v)+20:y(v)-10).toFixed(1)}" font-size="${last?13:12}" font-weight="${last?700:500}" text-anchor="${first?'start':'end'}" fill="${C.ink}">${dec(v,d)}</text>`});
  return`<svg viewBox="0 0 ${W} ${top+H+30}" role="img" aria-label="${esc(`${c.subtitle||c.headline}: ${rows.map(r=>`${r.label} ${dec(r.value,d)}`).join(', ')}.`)}">${s}</svg>`;
 }
 // Dot plot vs. the base period: dot = current, ring = base.
 function dots(c){
  const rows=arr(c.rows).filter(r=>Number.isFinite(Number(r.value)));if(!rows.length)return'';const d=Number.isInteger(c.digits)?c.digits:1;
  // Right margin sized to the longest value label, so '50.515' never runs past the viewBox at 390 px. 9 px per
  // character covers wider fallback fonts (CI runners render DejaVu, wider than local fonts).
  const lab=Math.max(...rows.map(r=>(dec(r.value,d)+(c.unit==='%'?'%':'')).length))*9+16;
  const all=rows.flatMap(r=>[Number(r.value),Number(r.base)]).filter(Number.isFinite),max=Math.max(...all)||1,W=360,row=26,x0=118,x1=W-lab,X=v=>x0+v/max*(x1-x0),H=8+rows.length*row+6;
  let s=`<line x1="${x0}" y1="4" x2="${x0}" y2="${H-6}" stroke="${C.axis}"/>`;
  rows.forEach((r,i)=>{const v=Number(r.value),b=Number(r.base),y=8+i*row+9;s+=`<text x="1.5" y="${y+4}" font-size="12.5" fill="${C.ink}">${esc(r.label)}</text>`;
   if(Number.isFinite(b))s+=`<line x1="${X(Math.min(v,b)).toFixed(1)}" y1="${y}" x2="${X(Math.max(v,b)).toFixed(1)}" y2="${y}" stroke="${C.axis}" stroke-width="2"/><circle cx="${X(b).toFixed(1)}" cy="${y}" r="5" fill="#fff" stroke="${C.ink50}" stroke-width="1.5"/>`;
   s+=`<g class="sf-mark"><title>${esc(r.label)}: ${dec(v,d)}${c.unit==='%'?'%':''}</title><circle cx="${X(v).toFixed(1)}" cy="${y}" r="5.5" fill="${Number.isFinite(b)&&v>b?C.accent:C.ink}"/></g><text x="${(X(Math.max(v,Number.isFinite(b)?b:v))+10).toFixed(1)}" y="${y+4}" font-size="12" fill="${C.ink}">${dec(v,d)}${c.unit==='%'?'%':''}</text>`});
  return`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${c.subtitle||c.headline}: ${rows.map(r=>`${r.label} ${dec(r.value,d)}`).join(', ')}.`)}">${s}</svg>`;
 }
 // Plain horizontal bars for non-negative values: counts (integer) or, with c.digits, rates and percentages (F4/F6).
 function bars(c){
  const rows=arr(c.rows).filter(r=>Number.isFinite(Number(r.value)));if(!rows.length)return'';
  if(rows.some(r=>Number(r.value)<0))return columns(c);  // a negative value is never drawn as a positive bar
  const max=Math.max(...rows.map(r=>Math.abs(Number(r.value))))||1,W=360,row=30,x0=128,L=160,H=rows.length*row+8;
  const fv=v=>Number.isInteger(c.digits)?dec(v,c.digits)+(c.unit==='%'?'%':''):nf(v);
  const s=rows.map((r,i)=>{const v=Number(r.value),w=Math.max(Math.abs(v)/max*L,2),y=4+i*row;return`<text x="1.5" y="${y+15}" font-size="12.5" fill="${C.ink}">${esc(r.label)}</text><g class="sf-mark"><title>${esc(r.label)}: ${fv(v)}</title><rect x="${x0}" y="${y+3}" width="${w.toFixed(1)}" height="16" rx="3" fill="${r.emphasis?C.accent:'#CFC9BC'}"/></g><text x="${(x0+w+6).toFixed(1)}" y="${y+15}" font-size="12.5" font-weight="${r.emphasis?700:500}" fill="${C.ink}">${fv(v)}</text>`}).join('');
  return`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${c.subtitle||c.headline}: ${rows.map(r=>`${r.label} ${fv(r.value)}`).join(', ')}.`)}">${s}</svg>`;
 }
 const FORMS={diverging,line,dots,bars,columns_signed:columns};
 function chart(c,i){const svg=(FORMS[c.form]||columns)(c);if(!svg)return'';return`<figure class="sf-chart" data-chart="${esc(c.id||i)}"><h3>${esc(c.headline)}</h3>${c.subtitle?`<p class="sf-sub">${esc(c.subtitle)}</p>`:''}${svg}<details class="sf-data"><summary>Ver datos del gráfico</summary>${table(c.table)}</details>${c.source?`<p class="sf-src">${esc(c.source)}</p>`:''}</figure>`}
 const PROV={C:'Capturada por Alicanto: archivo y hash en el repositorio'};
 function kpi(k){return`<div class="sf-kpi"><p class="sf-lab">${esc(k.label)}</p><p class="sf-val">${esc(k.value)}${k.prov?`<span class="sf-prov" title="${esc(PROV[k.prov]||k.prov)}" aria-label="${esc(PROV[k.prov]||k.prov)}">${esc(k.prov)}</span>`:''}</p>${arr(k.lines).map(x=>`<p class="sf-delta">${esc(x)}</p>`).join('')}${k.badge?`<span class="sf-badge ${k.badge_kind==='crossed'?'':'muted'}">${esc(k.badge)}</span>`:''}</div>`}
 // Header as in the approved mockup (Dirección 29-oct, option C→B): the kicker is the family label (+ 'Destacada'); under
 // the headline a small meta list of two short lines, the builder's own words: 'Datos a agosto 2026' and 'Publicado por
 // la SIS el 2 oct 2026' (the year from published_at). Any other meta clause ('se actualiza cada mes') goes to Notas.
 const cap=x=>x?x[0].toUpperCase()+x.slice(1):'';
 function metaLines(f){
  const parts=String(f.kicker_meta||'').split(' · ').map(x=>x.trim()).filter(Boolean),y=/^(\d{4})-\d{2}-\d{2}/.exec(String(f.published_at||''));
  const data=parts.find(x=>/^datos\b/i.test(x)),pub=parts.find(x=>/^publicad[oa]\b/i.test(x));
  const pubLine=pub&&y&&/ el \d{1,2} \p{L}+\.?$/u.test(pub)?`${pub} ${y[1]}`:pub;
  return{lines:[data,pubLine].filter(Boolean).map(cap),rest:parts.filter(x=>x!==data&&x!==pub).map(cap)};
 }
 function dek(f){let d=esc(f.dek||'');if(f.dek_emphasis&&String(f.dek).includes(f.dek_emphasis))d=d.replace(esc(f.dek_emphasis),`<strong>${esc(f.dek_emphasis)}</strong>`);return d}

 // ---- Index → topic (C→B) ------------------------------------------------------------------------------------
 const ico=(d,w=18)=>`<svg width="${w}" height="${w}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${d}</svg>`;
 const I={chev:'<svg class="sf-pick-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="m6 9 6 6 6-6"/></svg>',
  left:ico('<path d="m15 6-6 6 6 6"/>'),right:ico('<path d="m9 6 6 6-6 6"/>'),
  share:ico('<path d="M12 3.5v11"/><path d="M7.8 7.6 12 3.5l4.2 4.1"/><path d="M5.5 11.5v7a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-7"/>',20),
  grid:ico('<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',16)};
 const SPARK={line:'line',columns:'columns',diverging:'diverging',bars:'bars'};
 const HERO_SPARK={line:'line',columns_signed:'columns',diverging:'diverging',bars:'bars',dots:'bars'};
 // The builder names the sparkline (chart + form); a builder that does not falls back to the topic's first chart.
 function sparkOf(t){
  if(t.spark===null)return null;const charts=arr(t.charts);
  if(t.spark&&t.spark.chart){const c=charts.find(x=>x.id===t.spark.chart);return c&&SPARK[t.spark.form]?{c,form:t.spark.form}:null}
  const c=charts[0];return c&&HERO_SPARK[c.form]?{c,form:HERO_SPARK[c.form]}:null;
 }
 // Mini chart from the chart's own evidence rows; no figure under it (Dirección 29-oct).
 function spark(t){
  const sp=sparkOf(t),pend=t.status==='pendiente';
  const rows=sp?arr(sp.c.rows).filter(r=>Number.isFinite(Number(r.value))):[];
  if(!sp||rows.length<2)return`<span class="sf-spark">${pend?'<span class="sf-spark-pend">pendiente</span>':''}</span>`;
  const v=rows.map(r=>Number(r.value)),W=96,H=28;let g='';
  if(sp.form==='line'){const lo=Math.min(...v),hi=Math.max(...v),x=i=>2+i*(W-6)/(v.length-1),y=a=>3+(hi-a)/((hi-lo)||1)*(H-6);
   g=`<polyline points="${v.map((a,i)=>`${x(i).toFixed(1)},${y(a).toFixed(1)}`).join(' ')}" fill="none" stroke="${C.ink}" stroke-width="1.6"/><circle cx="${x(v.length-1).toFixed(1)}" cy="${y(v[v.length-1]).toFixed(1)}" r="2.8" fill="${C.accent}"/>`}
  else{const hi=Math.max(0,...v),lo=Math.min(0,...v),k=(H-4)/((hi-lo)||1),z=2+hi*k,bw=Math.min(v.length<=3?20:9,(W-4)/v.length-2),gap=(W-4-v.length*bw)/Math.max(1,v.length-1);
   g=`<line x1="0" x2="${W}" y1="${z.toFixed(1)}" y2="${z.toFixed(1)}" stroke="${C.axis}"/>`+v.map((a,i)=>{const h=Math.max(Math.abs(a)*k,1.2),x=2+i*(bw+gap),fill=sp.form==='diverging'?(a<0?C.ink:C.accent):(i===v.length-1?C.accent:C.ink);return`<rect x="${x.toFixed(1)}" y="${(a<0?z:z-h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="1" fill="${fill}"/>`}).join('')}
  return`<span class="sf-spark"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sp.c.headline)}">${g}</svg></span>`;
 }
 // The index line: from the builder; else the first clause of the tab text; else the first chart's headline.
 function indexLine(t){if(t.index_line)return t.index_line;const x=String(arr(t.text)[0]||'').split(/(?<=[.;:])\s/)[0].replace(/[.;:]$/,'');return x&&x.length<=64?x:(arr(t.charts)[0]||{}).headline||''}
 // Topic text: the builder's dek (null = none); a builder without a 'dek' field falls back to the tab text.
 function topicText(t){return Object.prototype.hasOwnProperty.call(t,'dek')?(t.dek?[t.dek]:[]):arr(t.text)}
 function links(t){const ls=arr(t.links).filter(l=>https(l.url));return ls.length?`<ul class="sf-links">${ls.map(l=>`<li><a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a></li>`).join('')}</ul>`:''}
 function topicBody(t,i,ts){
  const ch=arr(t.charts).map(chart).filter(Boolean),kp=arr(t.kpis),txt=topicText(t);
  const nx=i<ts.length-1?`<button type="button" class="sf-next" data-sf-go="${i+1}"><span>Siguiente tema</span><b>${esc(ts[i+1].label)}</b>${I.right}</button>`:'';
  return(ch.length?`<div class="sf-hero">${ch[0]}</div>`:'')+txt.map(x=>`<p class="sf-tdek">${esc(x)}</p>`).join('')+
   (kp.length?`<section class="sf-kpis sf-tkpis" aria-label="Indicadores · ${esc(t.label)}">${kp.map(kpi).join('')}</section>`:'')+
   (ch.length>1?`<div class="sf-charts">${ch.slice(1).join('')}</div>`:'')+links(t)+
   nx+`<button type="button" class="sf-all" data-sf-index>${I.grid}<span>Todos los temas</span></button>`;
 }
 let seq=0;
 // The hash of a topic keeps the ficha's signal anchor: '#sig-<id>&tema=<topic>'.
 const temaHash=(sig,id)=>(sig?`#${encodeURIComponent(sig)}&`:'#')+'tema='+id;
 function topics(f,o={}){
  const ts=arr(f.tabs).filter(t=>t&&t.label),N=ts.length,base=`sf${++seq}`;
  // A pending topic shows 'pendiente' once in the index, in its sparkline slot (mockup); the picker list keeps the badge.
  const pend=t=>t.status==='pendiente'?'<span class="sf-pending">pendiente</span>':'';
  const ids=ts.map((t,i)=>String(t.id||i));
  const index=`<section class="sf-index" data-sf-view="index" aria-label="Temas de la ficha"><div class="sf-index-h">En esta ficha <span>${N} temas · toca para abrir</span></div>`+
   ts.map((t,i)=>`<div class="sf-item"><a class="sf-row" href="${esc(temaHash(o.shareId,ids[i]))}" data-sf-row="${i}"><span class="sf-row-txt"><span class="sf-row-label">${esc(t.label)}</span><span class="sf-row-line">${esc(indexLine(t))}</span></span>${spark(t)}<span class="sf-go">${I.right}</span></a></div>`).join('')+`</section>`;
  const opts=`<li role="option" id="${base}-o-all" class="sf-opt sf-opt-all" data-sf-opt="-1" aria-selected="false"><span class="sf-opt-n">${I.grid}</span><span class="sf-opt-txt"><span class="sf-opt-label">Todos los temas</span><span class="sf-opt-line">Volver al índice de la ficha</span></span></li>`+
   ts.map((t,i)=>`<li role="option" id="${base}-o${i}" class="sf-opt" data-sf-opt="${i}" aria-selected="${i===0}"><span class="sf-opt-n">${i+1}</span><span class="sf-opt-txt"><span class="sf-opt-label">${esc(t.label)}${pend(t)}</span><span class="sf-opt-line">${esc(indexLine(t))}</span></span></li>`).join('');
  const topic=`<section class="sf-topic" data-sf-view="topic" aria-label="Tema de la ficha" hidden><div class="sf-sticky"><div class="sf-picker">`+
   `<button type="button" class="sf-pick" aria-haspopup="listbox" aria-expanded="false" aria-controls="${base}-list"><span class="sf-pick-ver">Ver:</span><span class="sf-pick-label">${esc(ts[0].label)}</span><span class="sf-pick-count">1/${N}</span>${I.chev}</button>`+
   `<button type="button" class="sf-step" data-sf-step="-1" aria-label="Tema anterior" disabled>${I.left}</button><button type="button" class="sf-step" data-sf-step="1" aria-label="Tema siguiente"${N<2?' disabled':''}>${I.right}</button>`+
   `<ul id="${base}-list" class="sf-list" role="listbox" tabindex="-1" aria-label="Temas de la ficha" hidden>${opts}</ul></div></div>`+
   `<div class="sf-tpanels" aria-live="polite">${ts.map((t,i)=>`<section class="sf-tpanel" id="${base}-p${i}" data-sf-topic="${i}" data-sf-id="${esc(ids[i])}" role="region" aria-label="${esc(t.label)}" hidden>${topicBody(t,i,ts)}</section>`).join('')}</div></section>`;
  return index+topic;
 }
 // "Compartir informe" lives in the dialog's top bar (Dirección 29-oct): a compact icon button at its right edge, with
 // its status as a small note under it. app.js places it; shareFicha() below wires it.
 function shareButton(f,opts={}){
  if(!f||!opts.shareId||!f.headline)return'';
  return`<span class="sf-share-wrap"><button type="button" class="sf-share" data-ficha-share="${esc(opts.shareId)}" data-share-url="${esc(opts.shareUrl||'')}" data-share-title="${esc(f.headline)}" aria-label="Compartir informe" title="Compartir informe">${I.share}</button><span class="sf-share-status" role="status" aria-live="polite"></span></span>`;
 }
 function render(f,opts={}){
  if(!f||f.status!=='PASS'||!f.headline)return'<p>Ficha no disponible.</p>';
  const lect=f.lectura&&f.lectura.status==='pass'&&f.lectura.text?f.lectura.text:null;
  const sources=arr(f.sources).filter(s=>https(s.url));
  const mt=metaLines(f);
  const ts=arr(f.tabs).filter(t=>t&&t.label);
  // With topics, KPI cards live inside each topic (only when they add something its charts do not show) and the
  // ficha has no 'Qué mirar' block (Dirección 29-oct, option C→B). A ficha without topics keeps the KPI strip.
  const body=ts.length?topics(f,opts):
   `<section class="sf-kpis" aria-label="Indicadores clave">${arr(f.kpis).map(kpi).join('')}</section>`+
   (arr(f.charts).length?`<section class="sf-charts" aria-label="Gráficos">${arr(f.charts).map(chart).join('')}</section>`:'')+
   (f.facts?.rendered_in_tabs||!arr(f.facts?.paragraphs).length?'':`<section class="sf-facts"><h3>${esc(f.facts?.heading||'Qué muestran los datos')}</h3>${arr(f.facts?.paragraphs).map(p=>`<p>${esc(p)}</p>`).join('')}</section>`)+
   (arr(f.watch).length?`<aside class="sf-watch"><h3>Qué mirar</h3><ol>${arr(f.watch).slice(0,2).map(w=>`<li><strong>${esc(w.headline)}</strong> ${esc(w.explanation)}</li>`).join('')}</ol></aside>`:'');
  return`<article class="sf${ts.length?' sf-cb':''}"${opts.shareId?` data-sf-sig="${esc(opts.shareId)}"`:''} data-family="${esc(f.family)}" data-period="${esc(f.period)}">`+
   `<p class="sf-kicker"><span class="sf-kick">${esc(f.kicker)}</span>${f.featured?'<span class="sf-featured">Destacada</span>':''}</p>`+
   `<h2 id="detailTitle" class="sf-headline">${esc(f.headline)}</h2>`+
   (mt.lines.length?`<ul class="sf-meta" aria-label="Datos de la publicación">${mt.lines.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:'')+
   `<p class="sf-dek">${dek(f)}</p>`+body+
   (lect?`<section class="sf-reading"><h3>Lectura Alicanto</h3><p>${esc(lect)}</p></section>`:'')+
   `<details class="sf-notes"><summary>Notas y fuentes</summary>${mt.rest.length?`<p class="sf-cadence">${esc(mt.rest.join(' · '))}.</p>`:''}${arr(f.notes).length?`<h3>Notas sobre la evidencia</h3><ol>${arr(f.notes).map(n=>`<li>${esc(n.text)}</li>`).join('')}</ol>`:''}`+
   `<h3>Fuentes</h3><ul>${sources.map(s=>`<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a> <span class="sf-role">· ${esc(s.role||'')}</span><br><code>sha256 ${esc(String(s.sha256||'').slice(0,12))}… · ${esc(s.locator||'')}${s.fetched_at?` · capturado ${fmtDay(String(s.fetched_at).slice(0,10))}`:''}</code></li>`).join('')}</ul>`+
   (f.machine_note?`<p class="sf-machine">${esc(f.machine_note)}</p>`:'')+`</details></article>`;
 }

 // Behaviour of the index → topic layout inside the ficha detail (dialog). One ficha is mounted at a time; closing the
 // dialog unmounts it and leaves the URL as it was before the ficha opened a topic.
 let active=null;
 const TEMA=/(?:^#|&)tema=([\w-]+)$/,ANY_TEMA=/(?:^#|&)tema=[^&]*$/;
 function mount(container){
  if(active){active();active=null}
  const host=container&&container.querySelector?container.querySelector('.sf-cb'):null;if(!host||!root.document)return null;
  const doc=root.document,loc=root.location,hist=root.history,dialog=host.closest('dialog');
  const $=s=>host.querySelector(s),index=$('[data-sf-view=index]'),topic=$('[data-sf-view=topic]'),sticky=$('.sf-sticky'),
   btn=$('.sf-pick'),list=$('.sf-list'),optEls=[...list.querySelectorAll('[role=option]')],panels=[...host.querySelectorAll('[data-sf-topic]')],
   ids=panels.map(p=>p.dataset.sfId),N=panels.length,scroller=dialog||doc.scrollingElement||doc.documentElement;
  const reduce=!!(root.matchMedia&&root.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const back=dialog&&dialog.querySelector('.detail-close'),bar=back&&back.closest('.detail-top'),backTxt=back&&back.querySelector('span'),orig=back?{t:backTxt?backTxt.textContent:'',a:back.getAttribute('aria-label')}:null;
  const parse=()=>{const m=TEMA.exec(loc.hash);return m?ids.indexOf(m[1]):-1};
  const home=loc.pathname+loc.search+loc.hash.replace(/^#tema=[^&]*$/,'').replace(/&tema=[^&]*$/,'');
  // The ficha's signal anchor (from its render, else from a '#sig-…' already in the URL) stays in every topic URL.
  const sigOf=()=>{try{const m=/^#(sig-[^&]+)/.exec(loc.hash);return m?decodeURIComponent(m[1]):''}catch{return ''}};
  const sig=host.dataset.sfSig||sigOf();
  let cur=-1,last=0,entered=false,act=0;
  const url=i=>i<0?home:temaHash(sig,ids[i]);
  // The dialog's top bar is sticky too (mockup .mk-bar): the picker pins right under it.
  const barH=()=>bar&&root.getComputedStyle&&root.getComputedStyle(bar).position==='sticky'?bar.getBoundingClientRect().height:0;
  const top0=()=>(dialog?dialog.getBoundingClientRect().top+(dialog.clientTop||0):0)+barH();
  const offset=el=>el.getBoundingClientRect().top-top0();
  const go=y=>{try{scroller.scrollTo({top:Math.max(0,y),behavior:reduce?'auto':'smooth'})}catch{scroller.scrollTop=Math.max(0,y)}};
  const anim=(el,cls)=>{if(reduce)return;el.classList.remove('sf-in','sf-from-left','sf-from-right');void el.offsetWidth;el.classList.add(cls)};
  const onScroll=()=>{sticky.classList.toggle('stuck',!topic.hidden&&sticky.getBoundingClientRect().top<=top0()+1);if(bar)bar.classList.toggle('sf-scrolled',scroller.scrollTop>8)};
  // In topic mode the sticky top bar's back button reads '← Todos los temas' and returns to the index (mockup .mk-bar.topic).
  function backLabel(on){if(!back)return;bar&&bar.classList.toggle('sf-bar-topic',on);if(backTxt)backTxt.textContent=on?'Todos los temas':orig.t;if(on)back.setAttribute('aria-label','Volver a todos los temas');else if(orig.a===null)back.removeAttribute('aria-label');else back.setAttribute('aria-label',orig.a)}
  function show(i,{scroll=true,dir=0}={}){
   const from=cur;cur=i;
   if(i<0){
    topic.hidden=true;index.hidden=false;backLabel(false);
    host.querySelectorAll('.sf-row').forEach((r,j)=>r.classList.toggle('sf-last',j===last&&from>=0));
    anim(index,'sf-in');
    // Back on the index: the last topic's row is in view, highlighted and focused.
    if(scroll&&from>=0){const r=host.querySelector(`[data-sf-row="${last}"]`);if(r){go(scroller.scrollTop+offset(r)-Math.max(0,scroller.clientHeight-r.offsetHeight-24));r.focus({preventScroll:true})}}
    onScroll();return;
   }
   last=i;index.hidden=true;topic.hidden=false;backLabel(true);
   panels.forEach((p,j)=>{p.hidden=j!==i});
   $('.sf-pick-label').textContent=panels[i].getAttribute('aria-label');$('.sf-pick-count').textContent=`${i+1}/${N}`;
   optEls.forEach(o=>o.setAttribute('aria-selected',String(Number(o.dataset.sfOpt)===i)));
   host.querySelectorAll('[data-sf-step]').forEach(b=>{b.disabled=(b.dataset.sfStep==='-1'&&i===0)||(b.dataset.sfStep==='1'&&i===N-1)});
   anim(panels[i],dir>0?'sf-from-right':dir<0?'sf-from-left':'sf-in');
   // The picker pins at the top of the ficha; the hero chart starts right below it.
   if(scroll)go(scroller.scrollTop+offset(topic));
   onScroll();
  }
  // Navigation: index → topic pushes; topic → topic replaces; "Todos los temas" pops when we pushed.
  function openTopic(i,focus){if(i<0||i>=N)return;if(cur<0){entered=true;try{hist.pushState({sfTopic:ids[i]},'',url(i))}catch{}show(i);if(focus)btn.focus({preventScroll:true})}else if(i!==cur){const d=Math.sign(i-cur);try{hist.replaceState(hist.state,'',url(i))}catch{}show(i,{dir:d})}}
  function toIndex(){if(cur<0)return;if(entered&&parse()>=0){hist.back()}else{try{hist.replaceState(null,'',url(-1))}catch{}show(-1)}}
  const onPop=()=>{if(!host.isConnected)return;const i=parse();if(i<0)entered=false;show(i)};
  // Listbox (select-only combobox) with "Todos los temas" as its first option.
  const setAct=k=>{act=(k+optEls.length)%optEls.length;optEls.forEach((o,j)=>o.classList.toggle('active',j===act));list.setAttribute('aria-activedescendant',optEls[act].id)};
  const open=()=>{list.hidden=false;btn.setAttribute('aria-expanded','true');setAct(cur+1);list.focus({preventScroll:true})};
  const close=(f=true)=>{if(list.hidden)return;list.hidden=true;btn.setAttribute('aria-expanded','false');if(f)btn.focus({preventScroll:true})};
  const pickOpt=o=>{const i=Number(o.dataset.sfOpt);close(i>=0);if(i<0)toIndex();else openTopic(i)};
  btn.addEventListener('click',()=>list.hidden?open():close());
  btn.addEventListener('keydown',e=>{if(['ArrowDown','ArrowUp','Enter',' '].includes(e.key)){e.preventDefault();open()}});
  list.addEventListener('keydown',e=>{const k=e.key;if(k==='ArrowDown'){e.preventDefault();setAct(act+1)}else if(k==='ArrowUp'){e.preventDefault();setAct(act-1)}else if(k==='Home'){e.preventDefault();setAct(0)}else if(k==='End'){e.preventDefault();setAct(optEls.length-1)}else if(k==='Enter'||k===' '){e.preventDefault();pickOpt(optEls[act])}else if(k==='Escape'){e.preventDefault();e.stopPropagation();close()}else if(k==='Tab')close(false)});
  list.addEventListener('click',e=>{const o=e.target.closest('[role=option]');if(o)pickOpt(o)});
  const onDocClick=e=>{if(!e.target.closest||!e.target.closest('.sf-picker'))close(false)};
  // ←/→ change topic in topic mode, unless the focus is in a field, the listbox or a data-table toggle.
  const onKey=e=>{if(cur<0||e.altKey||e.ctrlKey||e.metaKey||!host.isConnected||(dialog&&!dialog.open))return;const t=e.target;if(t&&t.closest&&(t.closest('input,textarea,select,[role=listbox],summary')||(dialog&&!dialog.contains(t)&&t!==doc.body)))return;
   if(e.key==='ArrowRight'&&cur<N-1){e.preventDefault();openTopic(cur+1)}else if(e.key==='ArrowLeft'&&cur>0){e.preventDefault();openTopic(cur-1)}};
  host.addEventListener('click',e=>{
   const row=e.target.closest('[data-sf-row]');if(row){e.preventDefault();openTopic(Number(row.dataset.sfRow),e.detail===0);return}
   const s=e.target.closest('[data-sf-step]');if(s){openTopic(cur+Number(s.dataset.sfStep));return}
   const g=e.target.closest('[data-sf-go]');if(g){openTopic(Number(g.dataset.sfGo));return}
   if(e.target.closest('[data-sf-index]'))toIndex();
  });
  // In topic mode the dialog's back button reads "Todos los temas" and returns to the index instead of closing.
  const onBack=e=>{if(cur>=0&&back&&e.target.closest&&e.target.closest('.detail-close')===back){e.preventDefault();e.stopPropagation();toIndex()}};
  // Swipe between topics on phones.
  const tp=$('.sf-tpanels');let sx=null,sy=0;
  const onTs=e=>{const t=e.touches[0];sx=t.clientX;sy=t.clientY};
  const onTe=e=>{if(sx===null)return;const t=e.changedTouches[0],dx=t.clientX-sx,dy=t.clientY-sy;sx=null;if(Math.abs(dx)>70&&Math.abs(dx)>Math.abs(dy)*1.6){if(dx<0&&cur<N-1)openTopic(cur+1);if(dx>0&&cur>0)openTopic(cur-1)}};
  tp.addEventListener('touchstart',onTs,{passive:true});tp.addEventListener('touchend',onTe,{passive:true});
  root.addEventListener('popstate',onPop);doc.addEventListener('click',onDocClick);doc.addEventListener('keydown',onKey);scroller.addEventListener('scroll',onScroll,{passive:true});
  if(dialog)dialog.addEventListener('click',onBack,true);
  function unmount(){
   root.removeEventListener('popstate',onPop);doc.removeEventListener('click',onDocClick);doc.removeEventListener('keydown',onKey);scroller.removeEventListener('scroll',onScroll);
   if(dialog){dialog.removeEventListener('click',onBack,true);dialog.removeEventListener('close',onClose)}
   backLabel(false);if(bar)bar.classList.remove('sf-scrolled');if(active===unmount)active=null;
  }
  // Closing the ficha in topic mode leaves the URL as it was before (the pushed topic entry is popped).
  // An unknown '&tema=' (stale or mistyped link) is stripped too.
  function onClose(){const known=parse()>=0,any=ANY_TEMA.test(loc.hash);unmount();if(known&&entered)hist.back();else if(any)try{hist.replaceState(null,'',url(-1))}catch{}}
  if(dialog)dialog.addEventListener('close',onClose);
  active=unmount;
  // Deep link (#tema=<id>, or #sig-<id>&tema=<id> from a shared link): open that topic directly; Back then leaves.
  // An unknown topic opens the ficha at its index and drops the bad '&tema=' from the URL.
  const i0=parse();if(i0<0&&ANY_TEMA.test(loc.hash))try{hist.replaceState(null,'',home)}catch{}
  show(i0,{scroll:false});
  if(i0>=0)(root.requestAnimationFrame||setTimeout)(()=>{scroller.scrollTop+=offset(topic)});
  return{show,openTopic,toIndex,unmount,current:()=>cur};
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
  root.document.addEventListener('click',e=>{const b=e.target.closest?.('[data-ficha-share]');if(b){e.preventDefault();shareFicha(b)}});
 }
 // Public correction (CLAUDE.md rule 6): a short dated mark on the row ("Corregido el 28 oct"), the same date label as
 // the detail note; the export writes it as correction.label.
 const MON=['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
 function correctionLabel(c){if(c.label)return c.label;const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(String(c.corrected_at||''));return m?`${Number(m[3])} ${MON[Number(m[2])-1]}`:''}
 function correctionTag(s){const c=s&&s.statistical_view&&s.statistical_view.correction;if(!c||!c.corrected_at)return'';const label=correctionLabel(c);return label?` <span class="tag correction-tag" title="${esc(c.text||'')}">Corregido el ${esc(label)}</span>`:''}
 root.AlicantoFicha={render,shareButton,metaLines,mount,shareFicha,correctionTag,correctionLabel};
})(typeof window!=='undefined'?window:globalThis);
