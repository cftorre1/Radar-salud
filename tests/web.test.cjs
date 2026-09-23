const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
const source=fs.readFileSync('web/app.js','utf8').split("fetch('data/radar_today.json'")[0];
function context(){const c={localStorage:{getItem:()=>null,setItem:()=>{}},btoa:s=>Buffer.from(s,'binary').toString('base64'),unescape,encodeURIComponent,Intl,Date,Set,Map};vm.createContext(c);vm.runInContext(source,c);return c}
test('full card IDs do not collide for long URLs',()=>{const c=context();assert.notEqual(c.idFor({source_url:'https://example.org/'+ 'a'.repeat(160)+'1'}),c.idFor({source_url:'https://example.org/'+ 'a'.repeat(160)+'2'}))});
test('date-only publication keeps calendar date in Chile',()=>{const c=context();assert.match(c.fmtDate('2026-09-23'),/23/)});
test('Signal Density defaults and fiscalizacion',()=>{const c=context();assert.equal(vm.runInContext('periodMode',c),'7');assert.equal(vm.runInContext('sortMode',c),'date');assert.match(source,/Fiscalización/)});
test('BACKFILL never counts as new since visit',()=>{const c=context();vm.runInContext("periodMode='last';previousVisit='2026-09-22T00:00:00Z'",c);assert.equal(c.inPeriod({ingestion_mode:'BACKFILL',event_date:'2026-09-23',detected_at:'2026-09-23T12:00:00Z'}),false);assert.equal(c.inPeriod({ingestion_mode:'LIVE',event_date:'2026-09-23',detected_at:'2026-09-23T12:00:00Z'}),true)});

test('coverage counts never invent LIVE or BACKFILL when queue has not run',()=>{const c=context();const msg=c.coverageText({sources:{one:{}},queue:null,queue_status:'awaiting_first_global_discovery'});assert.match(msg,/sin medición global/);assert.doesNotMatch(msg,/0 LIVE/)});
test('coverage reports actual measured queue split',()=>{const c=context();const msg=c.coverageText({sources:{one:{}},queue_status:'measured',queue:{live_pending:2,backfill_pending:37,rejected:6}});assert.match(msg,/2 LIVE pendientes/);assert.match(msg,/37 históricos pendientes/)});
