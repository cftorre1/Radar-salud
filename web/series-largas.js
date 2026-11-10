// Series largas del sistema Isapre 1990–2025 (Datos). Everything comes from data/series_isapre.json, built
// deterministically from the SIS workbook with receipts (scripts/build_series_isapre_1990_2025.py). This file only lays
// out: highlights arrive formatted, the chart plots the published values, and the table lists them.
// House chart style (stats-ficha.js): ink line, accent on the latest point, recessive axis; one series at a time.
(function(root){
 'use strict';
 const C={ink:'#1D3345',ink70:'#4F6170',ink50:'#6B7884',axis:'#B9B3A6',grid:'#ECE8DF',accent:'#C37C37'};
 const esc=(s='')=>String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
 const nf=v=>new Intl.NumberFormat('es-CL').format(v);
 const RANGES=[{key:'todo',label:'1990–2025',from:1990},{key:'2005',label:'Desde 2005',from:2005},{key:'10',label:'10 años',from:2016}];
 // Series catalogue: system lines first, then current Isapres (short name), then regions, then Isapres that no longer operate.
 function catalogue(d){
  const s=d.sistema,m=d.mercado,out=[
   {key:'ben',group:'Sistema',label:'Beneficiarios · total',values:s.beneficiarios.total,unit:'beneficiarios'},
   {key:'ben-abiertas',group:'Sistema',label:'Beneficiarios · Isapres abiertas',values:s.beneficiarios.abiertas,unit:'beneficiarios'},
   {key:'ben-cerradas',group:'Sistema',label:'Beneficiarios · Isapres cerradas',values:s.beneficiarios.cerradas,unit:'beneficiarios'},
   {key:'cot',group:'Sistema',label:'Cotizantes · total',values:s.cotizantes.total,unit:'cotizantes'},
   {key:'isapres',group:'Sistema',label:'Isapres con cartera',values:m.isapres_total,unit:'Isapres'}];
  const isa=(d.isapres&&d.isapres.beneficiarios)||[];
  isa.filter(b=>b.short).forEach(b=>out.push({key:`isapre-${b.code}-${b.tipo}`,group:'Isapres vigentes',label:b.short,full:b.name,isapre:b.short,values:b.values,unit:'beneficiarios'}));
  (d.regiones||[]).forEach(r=>out.push({key:`region-${r.code}`,group:'Regiones',label:r.short||r.name,full:r.name,region:r.short||r.name,values:r.values,unit:'beneficiarios'}));
  isa.filter(b=>!b.short).forEach(b=>out.push({key:`isapre-${b.code}-${b.tipo}`,group:'Isapres que ya no operan',label:`${b.name} (${b.desde}–${b.hasta})`,full:b.name,values:b.values,unit:'beneficiarios'}));
  return out;
 }
 function points(d,serie,from){return d.years.map((y,i)=>({y,v:serie.values[i]})).filter(p=>p.y>=from&&Number.isFinite(p.v))}
 function chart(d,serie,from,W){
  const pts=points(d,serie,from);if(pts.length<2)return'<p class="sl-empty">Sin datos en este período.</p>';
  W=Math.max(300,Math.min(W||360,900));const H=W<480?170:210,L=W<480?46:56,R=14,T=16,B=26,iw=W-L-R,ih=H-T-B;
  const vals=pts.map(p=>p.v),hi=Math.max(...vals),lo=serie.unit==='Isapres'?0:Math.min(...vals),pad=(hi-lo)*.08||1;
  const max=hi+pad,min=Math.max(0,lo-pad),x=i=>L+i*iw/(pts.length-1),y=v=>T+(max-v)/((max-min)||1)*ih;
  const tick=(()=>{const raw=(max-min)/4,p=10**Math.floor(Math.log10(raw)),k=[1,2,2.5,5,10].find(k=>k*p>=raw)*p;return k})();
  const short=v=>v>=1e6?`${(v/1e6).toLocaleString('es-CL',{maximumFractionDigits:1})} M`:v>=1e3?`${(v/1e3).toLocaleString('es-CL',{maximumFractionDigits:0})} mil`:nf(v);
  let g='';
  for(let v=Math.ceil(min/tick)*tick;v<=max;v+=tick)g+=`<line x1="${L}" x2="${W-R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="${C.grid}"/><text x="${L-6}" y="${(y(v)+4).toFixed(1)}" font-size="11" text-anchor="end" fill="${C.ink50}">${short(v)}</text>`;
  const step=[1,2,5,10].find(k=>iw/(pts.length-1)*k>=34)||10;
  pts.forEach((p,i)=>{if((pts.length-1-i)%step===0)g+=`<text x="${x(i).toFixed(1)}" y="${H-6}" font-size="11" text-anchor="middle" fill="${C.ink70}">${p.y}</text>`});
  g+=`<line x1="${L}" x2="${W-R}" y1="${T+ih}" y2="${T+ih}" stroke="${C.axis}"/>`;
  g+=`<polyline points="${pts.map((p,i)=>`${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ')}" fill="none" stroke="${C.ink}" stroke-width="2" stroke-linejoin="round"/>`;
  const iMax=vals.indexOf(hi),last=pts.length-1;
  if(iMax!==last)g+=`<circle cx="${x(iMax).toFixed(1)}" cy="${y(hi).toFixed(1)}" r="4" fill="#fff" stroke="${C.ink}" stroke-width="2"/><text x="${(x(iMax)-L<80?x(iMax)-4:x(iMax)).toFixed(1)}" y="${(y(hi)-9).toFixed(1)}" font-size="11.5" text-anchor="${x(iMax)-L<80?'start':iMax>last-3?'end':'middle'}" fill="${C.ink}">máx. ${nf(hi)} (${pts[iMax].y})</text>`;
  g+=`<circle cx="${x(last).toFixed(1)}" cy="${y(vals[last]).toFixed(1)}" r="5" fill="${C.accent}"/><text x="${x(last).toFixed(1)}" y="${(y(vals[last])+(vals[last]<vals[last-1]?20:-10)).toFixed(1)}" font-size="12.5" font-weight="700" text-anchor="end" fill="${C.ink}">${nf(vals[last])}</text>`;
  const desc=`${serie.label}, ${pts[0].y}–${pts[last].y}: de ${nf(vals[0])} a ${nf(vals[last])}${iMax!==last?`; máximo ${nf(hi)} en ${pts[iMax].y}`:''}.`;
  return`<div class="sl-plot" data-l="${L}" data-iw="${iw}" data-n="${pts.length}"><svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(desc)}">${g}<line class="sl-cross" x1="0" x2="0" y1="${T}" y2="${T+ih}" stroke="${C.ink50}" stroke-dasharray="3 3" visibility="hidden"/></svg><div class="sl-tip" role="status" hidden></div></div>`;
 }
 function table(d,serie,from){
  const pts=points(d,serie,from).reverse();
  return`<table class="sl-table"><thead><tr><th scope="col">Año (dic)</th><th scope="col" class="n">${esc(serie.unit[0].toUpperCase()+serie.unit.slice(1))}</th></tr></thead><tbody>${pts.map(p=>`<tr><th scope="row">${p.y}</th><td class="n">${nf(p.v)}</td></tr>`).join('')}</tbody></table>`;
 }
 function options(cat,sel){
  const groups=[...new Set(cat.map(s=>s.group))];
  return groups.map(g=>`<optgroup label="${esc(g)}">${cat.filter(s=>s.group===g).map(s=>`<option value="${esc(s.key)}"${s.key===sel?' selected':''}>${esc(s.label)}</option>`).join('')}</optgroup>`).join('');
 }
 function highlights(d){return`<div class="sl-kpis">${(d.highlights||[]).map(h=>`<div class="sl-kpi" data-kpi="${esc(h.id)}"><p class="sl-kl">${esc(h.label)}</p><p class="sl-kv">${esc(h.value)}</p>${(h.lines||[]).map(l=>`<p class="sl-kd">${esc(l)}</p>`).join('')}</div>`).join('')}</div>`}
 function notes(d){
  const s=d.source||{},day=String(s.retrieved_at||'').slice(0,10);
  return`<details class="sl-notes"><summary>Notas y fuente</summary><ul>${(d.notas||[]).map(n=>`<li>${esc(n)}</li>`).join('')}</ul><p class="sl-src">${esc(s.short||'SIS')} · <a href="${esc(s.page)}" rel="noopener" target="_blank">${esc(s.label)}</a> · cuadros ${esc((s.cuadros||[]).join(', '))} · descargado el ${esc(day)} · SHA-256 <code title="${esc(s.sha256)}">${esc(String(s.sha256||'').slice(0,12))}…</code> · conciliación ${esc((d.verificacion||{}).status||'')}</p></details>`;
 }
 function shell(d,state){
  const cat=catalogue(d),serie=cat.find(s=>s.key===state.serie)||cat[0];
  return`<div class="sl-head"><h2 class="sl-title" id="sl-title">${esc(d.title)}</h2><p class="sl-lead">Beneficiarios, cotizantes e Isapres a diciembre de cada año, según las series oficiales de la Superintendencia de Salud.</p></div>${highlights(d)}
<div class="sl-card"><div class="sl-controls"><label class="sl-field"><span>Serie</span><select data-sl="serie">${options(cat,serie.key)}</select></label><div class="sl-range" role="group" aria-label="Período">${RANGES.map(r=>`<button type="button" data-range="${r.key}" aria-pressed="${r.key===state.range}">${r.label}</button>`).join('')}</div></div>
<p class="sl-cap"><strong>${esc(serie.label)}</strong>${serie.full&&serie.full!==serie.label?` <span>(${esc(serie.full)})</span>`:''} · ${esc(serie.unit)} a diciembre</p><div class="sl-chart" data-serie="${esc(serie.key)}"></div>
<details class="sl-data"><summary>Ver datos de la serie</summary><div class="sl-tablewrap"></div></details></div>${notes(d)}`;
 }
 function mount(host,d,opts={}){
  const state={serie:opts.serie||'ben',range:opts.range||'todo'};
  const cat=catalogue(d);
  host.innerHTML=shell(d,state);
  const drawChart=()=>{
   const serie=cat.find(s=>s.key===state.serie)||cat[0],from=(RANGES.find(r=>r.key===state.range)||RANGES[0]).from;
   const box=host.querySelector('.sl-chart');box.dataset.serie=serie.key;box.innerHTML=chart(d,serie,from,box.clientWidth||360);
   host.querySelector('.sl-tablewrap').innerHTML=table(d,serie,from);
   const cap=host.querySelector('.sl-cap');cap.innerHTML=`<strong>${esc(serie.label)}</strong>${serie.full&&serie.full!==serie.label?` <span>(${esc(serie.full)})</span>`:''} · ${esc(serie.unit)} a diciembre`;
   hover(box,points(d,serie,from),serie.unit);
  };
  host.querySelector('[data-sl="serie"]').onchange=e=>{state.serie=e.target.value;drawChart();opts.onChange&&opts.onChange(state)};
  host.querySelectorAll('[data-range]').forEach(b=>b.onclick=()=>{state.range=b.dataset.range;host.querySelectorAll('[data-range]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));drawChart()});
  drawChart();
  let w=host.clientWidth;if(root.addEventListener)root.addEventListener('resize',()=>{if(Math.abs(host.clientWidth-w)>20){w=host.clientWidth;drawChart()}});
  return{select(key){if(cat.some(s=>s.key===key)){state.serie=key;host.querySelector('[data-sl="serie"]').value=key;drawChart()}},state,catalogue:cat};
 }
 // Crosshair + tooltip: the nearest year to the pointer; hit area is the whole plot.
 function hover(box,pts,unit){
  const plot=box.querySelector('.sl-plot');if(!plot)return;const svg=plot.querySelector('svg'),tip=plot.querySelector('.sl-tip'),cross=svg.querySelector('.sl-cross');
  const L=Number(plot.dataset.l),iw=Number(plot.dataset.iw),n=Number(plot.dataset.n);
  const move=e=>{const r=svg.getBoundingClientRect(),vb=svg.viewBox.baseVal,sx=(e.clientX-r.left)*vb.width/r.width,i=Math.max(0,Math.min(n-1,Math.round((sx-L)/(iw/(n-1))))),p=pts[i],cx=L+i*iw/(n-1);
   cross.setAttribute('x1',cx);cross.setAttribute('x2',cx);cross.setAttribute('visibility','visible');
   tip.hidden=false;tip.innerHTML=`<b>${p.y}</b> ${nf(p.v)} ${esc(unit)}`;const px=cx*r.width/vb.width;tip.style.left=`${Math.min(Math.max(px,60),r.width-60)}px`};
  svg.addEventListener('pointermove',move);svg.addEventListener('pointerdown',move);
  svg.addEventListener('pointerleave',()=>{tip.hidden=true;cross.setAttribute('visibility','hidden')});
 }
 const api={catalogue,chart,table,mount,points,RANGES};
 root.AlicantoSeries=api;
 if(typeof document==='undefined')return;
 const host=document.getElementById('seriesLargas');if(!host||host.dataset.manual)return;
 fetch('data/series_isapre.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('series');return r.json()}).then(d=>mount(host,d)).catch(()=>{host.innerHTML='<p class="datos-empty">No se pudieron cargar las series.</p>'});
})(typeof window==='undefined'?globalThis:window);
