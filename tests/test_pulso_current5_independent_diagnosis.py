"""All five actual held responses remain evidence, never synthetic approvals."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).parents[1]
PRODUCER = '66f37ca044b4cf233bc9f649b7140ff8a69855d3'
AUDIT = ROOT / 'data/audits/pulso_current5_guard_independent_diagnosis_2026_10_11.json'


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def test_all_actual_five_body_response_and_date_provenance_is_immutable():
    audit = json.loads(AUDIT.read_text())
    queue = json.loads(subprocess.check_output(['git', 'show', PRODUCER + ':data/state/pending_queue.json'], cwd=ROOT))
    assert audit['producer_commit'] == PRODUCER and audit['publication_approved'] is False
    assert audit['runtime_route_counts'] == {'reuse_code_fn': 3, 'assess_contract_or_semantic_defect': 2}
    assert len(audit['rows']) == len({row['queue_fingerprint'] for row in audit['rows']}) == 5
    for row in audit['rows']:
        original = queue[row['queue_fingerprint']]; raw = original['raw']; meta = raw['metadata']
        assert row['original_full_primary_body'] == meta['page_text']
        assert hashlib.sha256(row['original_full_primary_body'].encode()).hexdigest() == row['original_body_sha256']
        assert row['original_full_model_output'] == meta['analysis_model_output']
        assert row['original_full_validation'] == meta['pulso_editorial_proof_validation']
        assert row['original_response_id'] == meta['analysis_model_output']['_pulso_analysis_meta']['response_id']
        assert row['actual_status'] == original['status'] == 'retry' and row['original_attempts'] == original['attempts'] == 4
        assert row['publication_date'] == raw['event_date'] and row['original_html_sha256'] == meta['html_sha256']
        assert row['actual_queue_entry_sha256'] == canonical(original)
        assert row['primary_capture_verified'] and all(quote['literal_primary_match'] for quote in row['all_citation_literal_checks'])
        assert row['publication_approved'] is False and row['runtime_route_is_publication_approval'] is False


def test_hanta_prior_published_decree_and_mama_period_error_prevent_blind_reuse():
    rows = json.loads(AUDIT.read_text())['rows']
    hanta = next(row for row in rows if 'el-mapa-del-hanta-' in row['url'])
    mama = next(row for row in rows if 'todas-somos-vulnerables-' in row['url'])
    assert hanta['runtime_route'] == mama['runtime_route'] == 'assess_contract_or_semantic_defect'
    target = hanta['existing_published_comparison']
    assert target['queue_status'] == 'published' and target['publication_date'] == '2026-08-08'
    assert target['prior_decree_verbatim_quote'] in target['original_full_primary_body']
    assert 'Previamente, el Minsal había decretado alerta sanitaria por hantavirus' in target['prior_decree_verbatim_quote']
    assert canonical(target['actual_full_published_signal']) == target['actual_published_signal_sha256']
    assert mama['unsupported_model_quote'] in mama['original_full_model_output']['why_it_matters']
    assert 'hasta la fecha' in mama['original_full_primary_body']
    assert '30.805' in mama['original_full_primary_body']
