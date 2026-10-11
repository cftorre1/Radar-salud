"""Persist desktop/mobile and Node QA against captured source metadata."""
import json
import os
import re
import hashlib
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
report=json.loads((root/'artifacts/browser.json').read_text())
stats=report['stats']
projects={p['name'] for p in report['config']['projects']}
node=(root/'work/global-node-qa.log').read_text()
passed=re.search(r'^# pass (\d+)$',node,re.M)
failed=re.search(r'^# fail (\d+)$',node,re.M)
directed=ET.parse(root/'work/global-directed-qa.xml').findall('.//testcase')
if projects!={'desktop','mobile'} or stats['unexpected'] or stats['flaky'] or stats['skipped'] or not stats['expected']:
    raise ValueError('Global desktop/mobile QA incomplete or failed')
if not passed or not failed or int(failed[1]) or not int(passed[1]): raise ValueError('Node QA failed or incomplete')
if any(c.find('failure') is not None or c.find('error') is not None for c in directed): raise ValueError('directed Python QA failed')
capture_run_id=json.loads((root/'data/global_intelligence/discovery.json').read_text())['run_id']
result={'result':'PASS','qa_run_id':os.environ['GITHUB_RUN_ID'],'tested_commit':os.environ['GITHUB_SHA'],
        'capture_run_id':capture_run_id,'qa_source_network_requests':0,'deployment':False,
        'directed_python_passed':len(directed),'node_passed':int(passed[1]),'node_failed':0,
        'browser_passed':stats['expected'],'browser_failed':stats['unexpected'],'projects':sorted(projects),
        'scope':'Global views, source groups and Global metadata exclusion from Chile LIVE coverage'}
baseline=json.loads((root/'work/baseline-browser/artifacts/browser.json').read_text())
result['baseline_browser']={'sha':'4ff51cf','stats':baseline['stats'],
    'note':'Old tests assumed Home teaser top-ten inclusion and research headings absent in the unchanged Lite renderer. Current source QA verifies read state, factual findings, sources and separate Chile hypotheses; does not certify richer research UI.'}
renderer=(root/'web/global.js').read_bytes()
if renderer!=subprocess.check_output(['git','show','4ff51cf:web/global.js'],cwd=root): raise ValueError('Global renderer changed outside source QA scope')
result['global_renderer_byte_identical_to_staging']=True
result['global_renderer_sha256']=hashlib.sha256(renderer).hexdigest()
path=root/'data/audits/global_source_recovery_2026_10_11/runs'/capture_run_id/'browser_qa.json'
path.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
