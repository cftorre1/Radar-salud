(function(root){
 const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 // Existing collectors only. A URL is not authorization to activate a source.
 const catalog={
 superintendencia_normativa:['Organismos públicos y reguladores','https://www.superdesalud.gob.cl/normativa/','Normas y actos de la Superintendencia de Salud.'],
 superintendencia:['Datos oficiales','https://www.superdesalud.gob.cl/biblioteca-digital/','Publicaciones estadísticas del sistema de salud.'],
 superintendencia_fiscalizacion:['Organismos públicos y reguladores','https://www.superdesalud.gob.cl/','Resoluciones y fiscalización.'],
 minsal:['Organismos públicos y reguladores','https://www.minsal.cl/','Noticias del Ministerio de Salud.'],
 suseso:['Organismos públicos y reguladores','https://www.suseso.cl/','Normativa de seguridad social.'],
 suseso_news:['Organismos públicos y reguladores','https://www.suseso.cl/','Noticias institucionales.'],
 suseso_fiscalizacion:['Organismos públicos y reguladores','https://www.suseso.cl/','Fiscalización de seguridad social.'],
 diario_oficial:['Organismos públicos y reguladores','https://www.diariooficial.interior.gob.cl/','Publicaciones oficiales.'],
 diario_financiero:['Noticias y mercado','https://www.df.cl/empresas/salud','Textos públicos verificables; cobertura parcial.'],
 pulso_latercera:['Noticias y mercado','https://www.latercera.com/pulso/','Noticias públicas del sector.'],
 redsalud:['Prestadores e industria','https://www.redsalud.cl/','Noticias institucionales.'],
 bupa_chile:['Prestadores e industria','https://www.bupa.cl/','Noticias institucionales.'],
 red_davila:['Prestadores e industria','https://www.davila.cl/','Noticias institucionales.'],
 andes_salud:['Prestadores e industria','https://www.andessalud.cl/','Noticias institucionales.'],
 clinicas_chile:['Prestadores e industria','https://www.clinicasdechile.cl/noticias/','Noticias gremiales.'],
 pfizer_chile:['Prestadores e industria','https://www.pfizer.cl/','Noticias institucionales.'],
 ist:['Seguridad laboral','https://www.ist.cl/','Noticias institucionales.']};
 function eligible(x){if(!x?.checked_at||x.error||x.error_type)return false;const states=[x.status,x.technical_status,x.coverage_status,x.access_status].map(v=>String(v||'').toLowerCase());if(states.some(v=>/paused|blocked|held|license|not_permitted|unverified|error/.test(v)))return false;return x.technical_status==='ok'&&['observed','verified','complete'].includes(x.coverage_status)||x.technical_status==='partial'&&x.textual_capture_status==='verified'&&x.format_capability?.text==='runtime_verified';}
 function render(host,sources){const groups=new Map();for(const [id,x] of Object.entries(sources||{})){const meta=catalog[id];if(!meta||!eligible(x))continue;const [group,url,description]=meta;if(!groups.has(group))groups.set(group,[]);groups.get(group).push({name:x.name,url,description})}host.innerHTML=[...groups].map(([name,xs])=>`<section class="source-group"><h2 class="source-group-title">${esc(name)}</h2>${xs.map(x=>`<div class="source-row"><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)} ↗</a><p>${esc(x.description)}</p></div>`).join('')}</section>`).join('')||'<p>No hay fuentes activas verificadas disponibles para este catálogo.</p>';}
 root.AlicantoSources={eligible,render};
})(typeof window==='undefined'?globalThis:window);
