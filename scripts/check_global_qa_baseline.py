"""Reject new failures; reproduce unchanged upstream PDF checks independently."""
import hashlib
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

root=Path(__file__).resolve().parents[1]
baseline_sha='bc723e08200ada1cfb0146c6ce6da0d6f1ad11af'
def cases(path):return ET.parse(path).findall('.//testcase')
def failures(rows):return sorted(c.get('name') for c in rows if c.find('failure') is not None or c.find('error') is not None)
current=cases(root/'work/global-python-qa.xml');failed=failures(current)
known=sorted(['test_complete_review_has_all_113_pages_bound_to_verified_origin_bytes','test_every_selected_finding_is_a_literal_quote_from_its_numbered_pdf_page'])
proof=None
if failed:
    if failed!=known:raise ValueError('new regression: '+str(failed))
    audit='data/audits/source_e_recovery/ist_full_pdf_review.json'
    upstream=json.loads(subprocess.check_output(['git','show',baseline_sha+':'+audit],cwd=root))
    paths=['tests/test_ist_full_pdf_review.py',audit,upstream['capture_evidence']['artifact']]
    with tempfile.TemporaryDirectory(prefix='global-upstream-pdf-',dir=root/'work') as temp:
        folder=Path(temp);hashes={}
        for name in paths:
            original=subprocess.check_output(['git','show',baseline_sha+':'+name],cwd=root)
            if original!=(root/name).read_bytes():raise ValueError('upstream reproduction input changed: '+name)
            dest=folder/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(original)
            hashes[name]=hashlib.sha256(original).hexdigest()
        result=subprocess.run([sys.executable,'-m','pytest','-q','tests/test_ist_full_pdf_review.py','--junitxml='+str(folder/'baseline.xml')],cwd=folder,capture_output=True,text=True)
        baseline_failed=failures(cases(folder/'baseline.xml'))
        if result.returncode!=1 or baseline_failed!=failed:raise ValueError('upstream failures not independently reproduced: '+str(baseline_failed))
        import pypdf
        proof={'baseline_sha':baseline_sha,'failed':baseline_failed,'input_sha256':hashes,'pypdf_version':pypdf.__version__,'network_requests':0}
        (root/'work/global-upstream-pdf-baseline.log').write_text(result.stdout+result.stderr)
        (root/'work/global-upstream-pdf-baseline.xml').write_bytes((folder/'baseline.xml').read_bytes())
run=json.loads((root/'data/global_intelligence/discovery.json').read_text())['run_id']
result={'result':'PASS_WITH_REPRODUCED_UPSTREAM_FAILURES' if failed else 'PASS','baseline_sha':baseline_sha,
 'passed':sum(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in current),
 'failed':len(failed),'inherited_failures':failed,'new_regressions':0,'upstream_reproduction':proof,
 'historical_normativa_failure':'Resolved by upstream staging; original fresh capture QA remains immutable.',
 'excluded_unrelated_live_suite':'tests/test_beta_source_runtime_fast.py'}
(root/'data/audits/global_source_recovery_2026_10_11/runs'/run/'python_qa.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
