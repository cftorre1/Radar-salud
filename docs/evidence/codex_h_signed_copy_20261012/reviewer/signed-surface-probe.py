import sys, json, runpy, copy
from pathlib import Path
ROOT=Path('/workspace/work/radar-contract')
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT))
from radar_salud.editorial_v3 import content_version,validate_depth
from radar_salud.editorial_gate import publication_ready
from scripts.export_web_snapshot import curate
factory=runpy.run_path(str(ROOT/'tests/test_product_editorial_v3.py'))['record']
original=factory()
mutated=copy.deepcopy(original)
mutated['card_what']='Resolución IF/N°1 acoge reposición y levanta la sanción.'
items=json.loads((ROOT/'tests/fixtures/product_editorial_v3_cases.json').read_text())['items']
case=copy.deepcopy(items[0]['candidate'])
case_mutated=copy.deepcopy(case)
case_mutated['card_what']='La intervención demostró una reducción de mortalidad del 80%.'
results=[]
for name,before,after in [('signed_title',original,mutated),('signed_fixture_brief',case,case_mutated)]:
    results.append({'id':name,'content_version_unchanged':content_version(before)==content_version(after),'before_depth':validate_depth(before),'after_depth':validate_depth(after),'publication_ready':publication_ready(after),'exported':curate([after],resolve_external=False),'before':before,'after':after})
Path('/workspace/work/reviewer-contract/signed-surface-probe.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps([{k:v for k,v in x.items() if k not in {'before','after','exported'}} for x in results],ensure_ascii=False,indent=2))
