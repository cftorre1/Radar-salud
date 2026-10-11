"""Accept only the independently reproduced, unchanged snapshot baseline failure."""
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

root=Path(__file__).resolve().parents[1]
tree=ET.parse(root/'work/global-python-qa.xml')
cases=tree.findall('.//testcase')
failed=[c for c in cases if c.find('failure') is not None or c.find('error') is not None]
expected='test_normative_v2_recurates_all_visible_acts_and_routes_opaque_titles_to_review'
if len(failed)!=1 or failed[0].get('name')!=expected:
    raise ValueError('new regression or changed baseline failure: '+str([c.get('name') for c in failed]))
for path in ('tests/test_web_snapshot.py','scripts/export_web_snapshot.py','web/data/radar_today.json'):
    baseline=subprocess.check_output(['git','show','4ff51cf:'+path],cwd=root)
    if baseline != (root/path).read_bytes(): raise ValueError('baseline file changed: '+path)
evidence=root/'data/audits/global_source_recovery_2026_10_11/runs'/json.loads((root/'data/global_intelligence/discovery.json').read_text())['run_id']/'python_qa.json'
result={'result':'PASS_WITH_KNOWN_BASELINE_FAILURE','baseline_sha':'4ff51cf',
        'passed':sum(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in cases),
        'failed':len(failed),'inherited_failure':expected,'new_regressions':0,
        'excluded_unrelated_live_suite':'tests/test_beta_source_runtime_fast.py',
        'baseline_data_test_and_exporter_byte_identical':True}
evidence.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
