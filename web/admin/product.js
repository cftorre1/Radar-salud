const text=(id,value)=>document.getElementById(id).textContent=value;
function node(tag,value){const n=document.createElement(tag);n.textContent=value;return n}
const number=v=>v==null?'Sin medir':new Intl.NumberFormat('es-CL').format(v);
fetch('../data/product.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('HTTP');return r.json()}).then(d=>{
  text('status',`Actualizado: ${new Date(d.generated_at).toLocaleString('es-CL')}`);
  for(const [label,value] of [['Señales publicadas',d.published],['LIVE pending',d.queue?.live_pending],['Backfill pending',d.queue?.backfill_pending],['Intentos hoy',d.iterations.filter(x=>x.day===new Date().toISOString().slice(0,10)).length]]){
    const box=node('div','');box.className='metric';box.append(node('strong',number(value)),node('span',label));document.getElementById('metrics').append(box);
  }
  const iterations=document.getElementById('iterations');
  if(!d.iterations.length)iterations.append(node('p','Sin iteraciones automáticas registradas. La habilitación de producción exige evidencia de todos los checks.'));
  for(const item of d.iterations.slice(-10).reverse())iterations.append(node('p',`${item.id} · ${item.state} · ${item.candidate_sha?.slice(0,8)} · ${item.feedback?.length||0} hallazgos`));
  for(const source of Object.values(d.sources)){const row=node('tr','');for(const v of [source.name,source.status,number(source.live_pending),number(source.backfill_pending),number(source.rejected)])row.append(node('td',v));document.getElementById('sources').append(row)}
  if(!d.queue)iterations.append(node('p',`Cola global pendiente de primera medición. Pendientes del sistema anterior: ${number(d.legacy_pending)}; sin clasificación fiable LIVE/BACKFILL.`));
  text('usage',`${number(d.usage.measured_responses)} respuestas medidas · ${number(d.usage.input_tokens)} tokens de entrada · ${number(d.usage.output_tokens)} de salida. Costo USD: no disponible hasta aprobar tarifas.`);
  const list=node('ul','');for(const x of d.excel)list.append(node('li',`${x.title}: ${x.status} (${x.insights} insights)`));document.getElementById('excel').append(list);
}).catch(()=>text('status','No se pudo cargar el estado. No es posible verificar los checks.'));
