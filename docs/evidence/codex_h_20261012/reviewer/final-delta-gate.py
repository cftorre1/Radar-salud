import json,sys,copy
sys.path.insert(0,'/workspace/work/codex-h/implementation/src')
from radar_salud.editorial_v3 import content_version,validate_depth
from radar_salud.editorial_gate import publication_ready
fixture=json.load(open('/workspace/work/codex-h/implementation/tests/fixtures/product_editorial_v3_cases.json'))['items'][0]['candidate']
r=copy.deepcopy(fixture);r['validity_text']='schema.org PropertyValue';r['review']['content_version']=content_version(r)
before=copy.deepcopy(r);out={'invalid_validity':{'gate':publication_ready(r),'unchanged':r==before,'hash_unchanged':content_version(r)==content_version(before)}}
r=copy.deepcopy(fixture);r['statistical_view']=json.load(open('/workspace/work/codex-h/implementation/tests/fixtures/product_statistics_v3.json'))['statistical_view'];r['review']['content_version']=content_version(r);old=content_version(r)
r.update(data_insight_meta={'status':'validated','sha256':{'mix':'a'*64}},data_insight_evidence=[{'family':'mix','analysis_kind':'mix','sha256':'a'*64,'text':'Afirmación pública añadida sin revisión.','period':'2026-07','sheet':'Datos!A1','formula':'A/B','source_url':'https://example.org/original'}])
out['unbound_complementary_payload']={'same_hash':content_version(r)==old,'depth':validate_depth(r),'gate':publication_ready(r)}
print(json.dumps(out,ensure_ascii=False,indent=2));open('/workspace/work/codex-h/reviewer/final-delta-gate-results.json','w').write(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
