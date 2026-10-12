const fs=require('fs'),vm=require('vm'),{execFileSync}=require('child_process');
const root='/workspace/work/radar-contract',baseline='74da1c6d33b9e5746e79e0f481be3057f33d45df',candidate=process.env.REVIEW_SHA||'6048a1d5def99e060dd973fd9640c508d1ec853d';
function context(sha){const src=execFileSync('git',['show',sha+':web/app.js'],{cwd:root,encoding:'utf8'}).split("fetch('data/radar_today.json'")[0];const c={AlicantoRead:{readSet:new Set(),ready:Promise.resolve(),migrate:async()=>{}},AlicantoStats:{render:()=>'',wire:()=>{}},localStorage:{getItem:()=>null,setItem:()=>{}},btoa:s=>Buffer.from(s,'binary').toString('base64'),atob:s=>Buffer.from(s,'base64').toString('binary'),escape,unescape,decodeURIComponent,encodeURIComponent,Intl,URL,Date,Set,Map};vm.createContext(c);vm.runInContext(src,c);return c;}
const before=context(baseline),after=context(candidate),signals=JSON.parse(fs.readFileSync(root+'/web/data/radar_today.json','utf8')).signals;
const diffs=[];let legacy=0;
for(const row of signals){if(String(row.editorial_schema_version)==='3')continue;legacy++;for(const fn of ['triageTitle','triageSummary','card','detailHtml'])if(before[fn](row)!==after[fn](row))diffs.push({piece:row.piece_id||row.source_url,fn});}
const result={baseline_sha:baseline,candidate_sha:candidate,legacy_signals_checked:legacy,functions:['triageTitle','triageSummary','card','detailHtml'],differences:diffs};
fs.writeFileSync('/workspace/work/reviewer-contract/legacy-compatibility-'+candidate.slice(0,8)+'.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
if(diffs.length)process.exitCode=1;
