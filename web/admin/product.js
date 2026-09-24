const text=(id,value)=>document.getElementById(id).textContent=value;
function node(tag,value){const n=document.createElement(tag);n.textContent=value;return n}
const number=v=>v==null?'Sin medir':new Intl.NumberFormat('es-CL').format(v);
function line(parent,value,tag='p'){parent.append(node(tag,value))}
function link(parent,url,label){const a=node('a',label);a.href=url;parent.append(a)}
function renderPMO(pmo){
  if(!pmo){text('readiness','Sin baseline PMO verificado. No se puede determinar Beta Readiness.');return}
  text('readiness',`${pmo.readiness.label} · ${pmo.readiness.validated}/${pmo.readiness.total} bloques críticos validados`);
  text('releaseRule',pmo.release_rule);
  text('deployments',`Staging candidato: ${pmo.candidate_sha||'Sin SHA de CI'} · Último deploy staging validado: ${pmo.reference_staging_sha.slice(0,8)} · Producción: último SHA comprobado ${pmo.production_reference_sha.slice(0,8)} (estado actual no medido en este reporte).`);
  const deployment=document.getElementById('deployments');deployment.append(document.createTextNode(' Evidencia: '));link(deployment,pmo.reference_deploy.url,'run de staging validado');
  text('qa',`QA de referencia: ${pmo.reference_deploy.checks.join(', ')} · ${pmo.reference_deploy.result}. Los cambios del candidato requieren su propia evidencia.`);
  for(const block of pmo.blocks){
    const box=node('article','');box.className='block';
    line(box,block.title,'h3');const state=node('span',block.status);state.className=`state ${block.status.toLowerCase().replaceAll(' ','-')}`;box.append(state);
    if(block.validation_note)line(box,block.validation_note);
    if(block.missing.length)line(box,`Falta: ${block.missing.join('; ')}`,'p');
    if(block.dependencies.length)line(box,`Depende de: ${block.dependencies.join('; ')}`,'p');
    for(const evidence of block.evidence_links){const p=node('p','Evidencia de referencia: ');link(p,evidence.url,`${evidence.sha.slice(0,8)} · ${evidence.result}`);box.append(p)}
    document.getElementById('blocks').append(box);
  }
  const failures=document.getElementById('failures');
  if(!pmo.open_failures.length&&!pmo.human_blockers.length)line(failures,'Sin bloqueos abiertos.');
  for(const x of pmo.open_failures)line(failures,`${x.severity}: ${x.description} (${x.source})`);
  for(const x of pmo.human_blockers)line(failures,`${x.action} Proveedor: ${x.provider}. Datos: ${x.required_data}. Tiempo: ${x.estimated_time}. Impacto: ${x.beta_impact}`);
  text('deviations',pmo.scope_deviations.length?pmo.scope_deviations.join('; '):'Sin desviaciones de alcance registradas.');
  const changes=document.getElementById('changes');for(const x of pmo.changes_since_yesterday)line(changes,`${x.date}: ${x.change}`);
  if(!pmo.changes_since_yesterday.length)line(changes,'Sin cambios registrados desde ayer.');
  const missing=document.getElementById('missing');for(const x of pmo.missing_for_beta)line(missing,x,'p');
  text('nextAction',`Siguiente acción: ${pmo.next_action}`);
}
fetch('../data/product.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('HTTP');return r.json()}).then(d=>{
  text('status',`Actualizado: ${new Date(d.generated_at).toLocaleString('es-CL')}`);
  for(const [label,value] of [['Señales publicadas',d.published],['LIVE pending',d.queue?.live_pending],['Backfill pending',d.queue?.backfill_pending],['Intentos hoy',d.iterations.filter(x=>x.day===new Date().toISOString().slice(0,10)).length]]){
    const box=node('div','');box.className='metric';box.append(node('strong',number(value)),node('span',label));document.getElementById('metrics').append(box);
  }
  const iterations=document.getElementById('iterations');
  renderPMO(d.pmo);
  text('coverage',d.coverage_live?`Cobertura LIVE: ${number(d.coverage_live.detected)} detectadas · ${number(d.coverage_live.evaluated)} evaluadas · ${number(d.coverage_live.selected)} seleccionadas. BACKFILL separado.`:'Cobertura LIVE aún sin medición global; no se mezcla con BACKFILL.');
  if(!d.iterations.length)iterations.append(node('p','Sin iteraciones automáticas registradas. La habilitación de producción exige evidencia de todos los checks.'));
  for(const item of d.iterations.slice(-10).reverse())iterations.append(node('p',`${item.id} · ${item.state} · ${item.candidate_sha?.slice(0,8)} · checks: ${Object.entries(item.checks||{}).map(([k,v])=>`${k}=${v}`).join(', ')||'sin medir'} · feedback: ${(item.feedback||[]).map(x=>x.detail||x.code).join('; ')||'sin hallazgos'}`));
  for(const source of Object.values(d.sources)){const row=node('tr','');const checked=source.checked_at?new Date(source.checked_at):null;const last=checked&&!Number.isNaN(checked.getTime())?checked.toLocaleString('es-CL'):'Sin medir';for(const v of [source.name,source.technical_status||'Sin medir',source.content_freshness||'Sin medir',source.editorial_outcome||'Sin medir',last,number(source.live_pending),number(source.backfill_pending),number(source.rejected)])row.append(node('td',v));document.getElementById('sources').append(row)}
  if(!d.queue)iterations.append(node('p',`Cola global pendiente de primera medición. Pendientes del sistema anterior: ${number(d.legacy_pending)}; sin clasificación fiable LIVE/BACKFILL.`));
  text('usage',`${number(d.usage.measured_responses)} llamadas registradas · ${number(d.usage.input_tokens)} tokens de entrada · ${number(d.usage.output_tokens)} de salida · fast: ${number(d.usage.fast_failed)} fallos históricos, ${number(d.usage.fast_unclassified)} sin causa registrada · causas futuras: ${Object.entries(d.usage.errors||{}).map(([k,v])=>`${k}=${number(v)}`).join(', ')||'sin medir'}. Costo USD: no disponible hasta aprobar tarifas.`);
  const familyEvidence=document.getElementById('excelValidation');for(const item of Object.values(d.excel_validation?.families||{})){const series=item.series||[],last=series.at(-1),span=last?(last.period||`${last.period_start} → ${last.period_end}`):'sin período validado';const metrics=last?Object.entries(last.metrics).map(([key,value])=>`${key.replaceAll('_',' ')}: ${number(value)}`).join(' · '):'sin métricas';const lineItem=node('p',`${item.family}: ${item.status} · ${series.length} ${item.family==='movilidad'?'comparación':'meses'} · ${span} · ${metrics} · SHA-256 ${item.sha256||'sin archivo validado'} · `);if(item.source_url)link(lineItem,item.source_url,'Workbook oficial');familyEvidence.append(lineItem)}
  if(!familyEvidence.childElementCount)familyEvidence.append(node('p','Sin pruebas controladas registradas.'));
  const list=node('ul','');for(const x of d.excel)list.append(node('li',`${x.title}: ${x.status} (${x.insights} insights)`));document.getElementById('excel').append(list);
}).catch(()=>text('status','No se pudo cargar el estado. No es posible verificar los checks.'));
