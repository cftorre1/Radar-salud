const fs=require('fs'),vm=require('vm');
const source=fs.readFileSync('/workspace/work/radar-contract/web/app.js','utf8').split("fetch('data/radar_today.json'")[0];
const c={AlicantoRead:{readSet:new Set(),ready:Promise.resolve(),migrate:async()=>{}},AlicantoStats:{render:()=>'',wire:()=>{}},localStorage:{getItem:()=>null,setItem:()=>{}},btoa:s=>Buffer.from(s,'binary').toString('base64'),atob:s=>Buffer.from(s,'base64').toString('binary'),escape,unescape,decodeURIComponent,encodeURIComponent,Intl,URL,Date,Set,Map};
vm.createContext(c);vm.runInContext(source,c);
const probes=JSON.parse(fs.readFileSync('/workspace/work/reviewer-contract/signed-surface-probe.json','utf8'));
const results=probes.map(p=>({id:p.id,content_version_unchanged:p.content_version_unchanged,depth_ok:p.after_depth.ok,publication_ready:p.publication_ready,exported:p.exported.length,before_title:c.triageTitle(p.before),after_title:c.triageTitle(p.after),before_brief:c.triageSummary(p.before),after_brief:c.triageSummary(p.after),detail_contains_unreviewed:c.detailHtml(p.after).includes(p.after.card_what)}));
fs.writeFileSync('/workspace/work/reviewer-contract/signed-surface-render-results'+(process.env.REVIEW_SUFFIX||'')+'.json',JSON.stringify(results,null,2));
console.log(JSON.stringify(results,null,2));
