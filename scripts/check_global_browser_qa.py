"""Persist desktop/mobile and Node QA against captured source metadata."""
import json
import os
import re
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
result={'result':'PASS','qa_run_id':os.environ['GITHUB_RUN_ID'],'tested_commit':os.environ['GITHUB_SHA'],
        'capture_run_id':'38145510005','source_network_requests':0,'deployment':False,
        'directed_python_passed':len(directed),'node_passed':int(passed[1]),'node_failed':0,
        'browser_passed':stats['expected'],'browser_failed':stats['unexpected'],'projects':sorted(projects),
        'scope':'Global views, source groups and Global metadata exclusion from Chile LIVE coverage'}
path=root/'data/audits/global_source_recovery_2026_10_11/runs/38145510005/browser_qa.json'
path.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
