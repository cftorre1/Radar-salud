"""Whole-stock zero-API evaluator units; windows/git transport are synthetic.

Real immutable paid323 bodies/models/ledgers and actual parser/processor are
used. A virtual Git transport supplies explicitly synthetic launch snapshots;
these tests do not count as a genuine core run or paid baseline acceptance.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('final_eval_unit', ROOT/'tests/test_pulso_final_paid_revalidation_qa.py')
units = importlib.util.module_from_spec(spec); spec.loader.exec_module(units)
qa = units.qa
CODE = 'f' * 40


@pytest.fixture(scope='module')
def origin():
    return qa.final_paid_origin(ROOT)


@pytest.fixture
def evaluation(tmp_path, origin, monkeypatch):
    values = [units.case.__wrapped__(SimpleNamespace(param=url), tmp_path, origin, monkeypatch)
              for url in sorted(origin['rows'])]
    queue = deepcopy(origin['queue'])
    for case in values:
        row = origin['rows'][case['item']['raw']['url']]
        queue[row['queue_fingerprint']] = case['item']
    history = deepcopy(origin['history'])
    execution = deepcopy(origin['execution'])
    execution.update(code_sha=CODE, started_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                     finished_at=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat(),
                     processing_attempts_increased=2, budget_before=deepcopy(execution['budget_after']))
    selection = execution['processing_selection']
    selection.update(ready_selected_urls=sorted(origin['rows']),
                     skipped_terminal_urls=sorted(set(selection['selected_urls'])-set(origin['rows'])),
                     skipped_not_due_urls=[], skipped_in_progress_urls=[])
    files = {path: qa.digest((ROOT/path).read_bytes()) for path in qa.required_runtime_fingerprint_paths(ROOT)}
    execution['runtime_fingerprint'] = dict(files=files, sha256=qa.object_digest(files), git_or_marker_sha_used=False)
    stock = {'data/state/pending_queue.json': json.dumps(origin['queue']).encode(),
             'data/history/superintendencia_signals.json': json.dumps({'signals':origin['history']}).encode()}
    real_run = qa.subprocess.run
    def virtual_git(command, **kwargs):
        if command[:2] == ['git','show'] and command[2].startswith(CODE+':'):
            path = command[2].split(':',1)[1]
            payload = stock.get(path, (ROOT/path).read_bytes() if (ROOT/path).is_file() else b'')
            return SimpleNamespace(returncode=0, stdout=payload, stderr=b'')
        return real_run(command, **kwargs)
    monkeypatch.setattr(qa.subprocess,'run',virtual_git)
    return dict(report={'last_core_execution':execution}, queue=queue, history=history,
                telemetry=origin['telemetry'], execution=execution, origin=origin)


def inspect(value):
    return qa.verify_final_revalidated_execution(ROOT, **value)


def test_zero_api_evaluation_keeps_original_failure_and_distinct_fingerprints(evaluation):
    result = inspect(evaluation)
    lineage = result['paid_model_lineage']
    assert lineage['original_processing_qa']['processing_qa'] == 'FAIL'
    assert lineage['original_paid_qa_promoted'] is False
    assert lineage['original_execution']['code_sha'] == qa.FINAL_PAID_CODE
    assert result['evaluation_execution']['code_sha'] == CODE
    assert lineage['original_runtime_fingerprint'] != result['evaluation_execution']['runtime_fingerprint']
    assert lineage['original_budget_delta']['fast']['successful'] == 2
    assert all(v == 0 for tier in result['actual_budget_delta'].values() for v in tier.values())
    assert len(result['current_revalidation_receipts']) == len(lineage['models']) == 2
    assert len(result['launch_stock']['preserved_terminal_urls']) == 111
    assert result['launch_stock']['native_queue_count'] == 5293
    assert result['launch_stock']['native_history_count'] == 897


@pytest.mark.parametrize('mutation', ['thin_fingerprint','native','prior_terminal','prior_history','new_event','one_attempt','ready_subset'])
def test_zero_api_claim_requires_full_implementation_and_whole_stocks(evaluation, mutation):
    # The fixture is fresh per mutation; real producer objects remain immutable.
    value = evaluation
    if mutation == 'thin_fingerprint':
        path='src/radar_salud/pulso_editorial_proof.py'
        files={path:value['execution']['runtime_fingerprint']['files'][path]}
        value['execution']['runtime_fingerprint'].update(files=files, sha256=qa.object_digest(files))
    elif mutation == 'native':
        next(item for item in value['queue'].values() if item.get('source') != qa.SOURCE)['attempts'] += 1
    elif mutation == 'prior_terminal':
        url=value['execution']['processing_selection']['skipped_terminal_urls'][0]
        next(item for item in value['queue'].values() if item['raw']['url']==url)['attempts'] += 1
    elif mutation == 'prior_history':
        next(row for row in value['history'] if qa.normalized_url(row.get('source_url')) not in value['origin']['rows'])['why_it_matters'] += ' unit invented prose'
    elif mutation == 'new_event':
        value['telemetry']=list(value['telemetry'])+[dict(at=value['execution']['started_at'],kind='fast',success=True,response_id='resp_synthetic_not_permitted')]
    elif mutation == 'one_attempt': value['execution']['processing_attempts_increased']=1
    else: value['execution']['processing_selection']['ready_selected_urls'].pop()
    with pytest.raises(ValueError): inspect(value)
