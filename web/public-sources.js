(function(root){
 const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function render(host,sources){const groups=new Map();for(const x of Array.isArray(sources)?sources:[]){if(!x.name||!x.group||!/^https:\/\//.test(x.url||''))continue;if(!groups.has(x.group))groups.set(x.group,[]);groups.get(x.group).push(x)}host.innerHTML=[...groups].map(([label,xs])=>`<section class="source-group"><h2 class="source-group-title">${esc(label)}</h2>${xs.map(x=>`<div class="source-row"><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)} ↗</a><p>${esc(x.description)}</p></div>`).join('')}</section>`).join('')||'<p>No hay fuentes activas verificadas disponibles para este catálogo.</p>';}
 root.AlicantoSources={render};
})(typeof window==='undefined'?globalThis:window);
