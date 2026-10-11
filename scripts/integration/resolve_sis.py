import json,re,subprocess
from pathlib import Path
root=Path.cwd()
def resolve(path,fn):
 p=root/path;s=p.read_text();i=0
 def fix(m):
  nonlocal i
  a,b=m.group(1),m.group(2);v=fn(i,a,b);i+=1;return v
 s=re.sub(r'^<<<<<<< HEAD\n(.*?)^=======\n(.*?)^>>>>>>> [^\n]+\n',fix,s,flags=re.M|re.S)
 p.write_text(s);print(path,'resolved',i)
resolve('src/radar_salud/processing.py',lambda i,a,b:a+'\n'+b.split('\n',1)[1])
for f in ['tests/test_source_health_facets.py','tests/test_web_snapshot.py']:
 resolve(f,lambda i,a,b:a+'\n\n'+b)
resolve('src/radar_salud/source_health.py',lambda i,a,b:b.replace('source_queue:list[dict]|None=None)', 'source_queue:list[dict]|None=None, discovery_evidence:dict|None=None)') if i==0 else a+b)
def pending(i,a,b):
 if i==0:return a[:a.index('            if key in self.items')]+b
 if i==1:return a+b[b.index('            if source in FISCALIZATION_SOURCES:'):]
 return a
resolve('src/radar_salud/pending_queue.py',pending)
def engine(i,a,b):
 if i==0:return a
 if i==1:return a+b
 if i==2:return a+b[b.index('            if name=="suseso_fiscalizacion":'):]
 if i==3:return '''    queue.enforce_backfill_horizon(sources=set(args.source) if args.source else None)
    ready=[(key,item) for key,item in queue.ready() if item['source'] in processors and (not args.source or
        item['source'] in args.source or ('suseso_fiscalizacion' in args.source and item['raw'].get('metadata',{}).get('routed_from')=='suseso_fiscalizacion'))]
    for index,(key,item) in enumerate(ready):
'''
 if i==4:return a
 if i==5:return b[:b.index('        except DeferredProcessing')]+a
 if i==6:return a[:a.index('        health_record')]+b[:b.index('        health_record')]+a[a.index('        health_record'):]
 if i==7:return b.replace('surfaces=surfaces.get(name),','surfaces=surfaces.get(name), discovery_evidence=df_evidence,')
 raise ValueError(i)
resolve('src/radar_salud/engine_cli.py',engine)
p=root/'src/radar_salud/engine_cli.py';s=p.read_text();s=s.replace('    args=ap.parse_args()','    args=ap.parse_args()\n    args.source=list(dict.fromkeys((args.source or []) + args.only_source))')
s=s.replace('        processing_raw=RawItem(**item["raw"])','        from copy import deepcopy\n        processing_raw=RawItem(**deepcopy(item["raw"]))')
s=s.replace('exc.reason or "budget_or_analysis_deferred"','exc.reason or str(exc) or "budget_or_analysis_deferred"');p.write_text(s)
# Semantic 3-way: apply only a lane's changed JSON records to the integrated base.
missing=object();conflicts=[]
def merge(b,o,t,path=''):
 if o==t:return o
 if b==t:return o
 if b==o:return t
 if all(isinstance(x,dict) for x in [b,o,t]):
  out={}
  for k in list(o)+[k for k in t if k not in o]:
   v=merge(b.get(k,missing),o.get(k,missing),t.get(k,missing),path+'/'+k)
   if v is not missing:out[k]=v
  return out
 if path.endswith('/updated_at') or path.endswith('/generated_at'):return max(str(o),str(t))
 if all(isinstance(x,list) for x in [b,o,t]):
  if all(isinstance(v,dict) and 'source_url' in v for x in [b,o,t] for v in x):
   key=lambda v:(v['source_url'],v.get('source_record_id'))
  elif all(isinstance(v,dict) and 'id' in v for x in [b,o,t] for v in x):key=lambda v:v['id']
  else:
   # Preserve both append-only governance/evidence sequences without dropping prior rows.
   if all(v in o for v in b) and all(v in t for v in b):return o+[v for v in t if v not in o]
   conflicts.append(path);return o
  maps=[{key(v):v for v in x} for x in [b,o,t]]
  if any(len(m)!=len(x) for m,x in zip(maps,[b,o,t])):raise ValueError('Duplicate identities '+path)
  out=[]
  for k in list(maps[1])+[k for k in maps[2] if k not in maps[1]]:
   v=merge(*[m.get(k,missing) for m in maps],path+'/'+str(k))
   if v is not missing:out.append(v)
  return out
 conflicts.append(path);return o
for f in ['config/pmo_baseline.json','data/history/superintendencia_signals.json','data/source_health.json','data/state/pending_queue.json']:
 vals=[json.loads(subprocess.check_output(['git','show',f':{stage}:{f}'],cwd=root)) for stage in (1,2,3)]
 out=merge(*vals,f);(root/f).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print('JSON',f,'conflicts',conflicts)
 if conflicts:raise ValueError(conflicts)
# Derived files will be rebuilt from merged history; do not import stale lane snapshots.
for f in ['web/data/radar_today.json','web/data/source_health.json']:
 (root/f).write_bytes(subprocess.check_output(['git','show','HEAD:'+f],cwd=root))
print('semantic resolution complete')

p=root/'scripts/integration_runtime.py'
s=p.read_text().replace("urls=[v.get('source_url') for v in history if v.get('source_name') in source_names]", "from radar_salud.history import _key as history_identity\n        urls=[history_identity(v) for v in history if v.get('source_name') in source_names]")
s=s.replace("'Duplicate selected-source history URLs'", "'Duplicate selected-source history identities (URL plus official record ID)'")
p.write_text(s)
p=root/'config/integration_runtime_targets.json';d=json.loads(p.read_text());d.update(sources=['superintendencia_fiscalizacion','suseso_fiscalizacion'],origin_prs=[15]);p.write_text(json.dumps(d,indent=2)+'\n')
expected=json.loads((root/'scripts/integration/sis_expected_blobs.json').read_text())
for path,expected_sha in expected.items():
 actual=subprocess.check_output(['git','hash-object',path],text=True,cwd=root).strip()
 if actual!=expected_sha:raise RuntimeError(f'Local-reviewed candidate mismatch: {path}: {actual} != {expected_sha}')
print('All local-reviewed code/config/stock blobs reproduced exactly')
