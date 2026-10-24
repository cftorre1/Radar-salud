import sys,json,subprocess,hashlib
from pathlib import Path
ROOT=Path('/workspace/work/radar-contract')
sys.path.insert(0,str(ROOT/'src'))
from radar_salud.editorial_v3 import content_version,validate_depth
base='74da1c6d33b9e5746e79e0f481be3057f33d45df'
candidate=sys.argv[1] if len(sys.argv)>1 else '6048a1d5def99e060dd973fd9640c508d1ec853d'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
paths=['tests/fixtures/product_editorial_v3_cases.json','docs/evidence/codex_h_20261012/reviewer/editorial-case-receipts.json','src/radar_salud/editorial_v3.py','web/data/radar_today.json','web/data/source_health.json']
unchanged={path:git('show',base+':'+path)==git('show',candidate+':'+path) for path in paths}
receipts=[]
for x in json.loads(git('show',candidate+':tests/fixtures/product_editorial_v3_cases.json'))['items']:
 r=x['candidate'];receipts.append({'id':x['id'],'hash':content_version(r),'receipt_hash':r['review']['content_version'],'hash_matches':content_version(r)==r['review']['content_version'],'depth':validate_depth(r)})
protected={path:git('rev-parse',base+':'+path).strip().decode()==git('rev-parse',candidate+':'+path).strip().decode() for path in ['data','config','.github','web/data']}
result={'baseline_sha':base,'candidate_sha':candidate,'unchanged_files':unchanged,'protected_trees_unchanged':protected,'editorial_receipts':receipts,'changed_files':git('diff','--name-only',base,candidate).decode().splitlines()}
Path('/workspace/work/reviewer-contract/receipt-integrity-'+candidate[:8]+'.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
assert all(unchanged.values()) and all(protected.values()) and all(x['hash_matches'] and x['depth']['ok'] for x in receipts)
