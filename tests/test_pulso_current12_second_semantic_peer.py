"""Verify the independent reader's actual primary/model pins, not published quotas."""
from pathlib import Path
import gzip
import hashlib
import json

from radar_salud.llm_analysis import news_analysis_input
from radar_salud.pulso_editorial_review import canonical_sha

ROOT = Path(__file__).resolve().parents[1]
DIAG = 'data/audits/pulso_current12_remaining5_second_semantic_diagnosis_2026_10_11.json'
PEER = 'data/audits/pulso_current12_all12_five_publications_second_peer_2026_10_11.json'


def fixture():
    audit = json.loads((ROOT / DIAG).read_text())
    raw = (ROOT / audit['actual_fixture']['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == audit['actual_fixture']['sha256']
    return audit, json.loads(gzip.decompress(raw))


def test_actual_five_full_primary_and_paid_model_pins_preserve_two_fresh_three_reuse():
    audit, data = fixture()
    assert audit['summary'] == dict(actual_remaining=5, reuse_code_fn=3,
                                 assess_contract_or_semantic_defect=2)
    assert {r['row'] for r in data['rows']} == {2, 5, 6, 9, 11}
    assert set(audit['inputs']) == {'history', 'queue', 'runtime_report', 'telemetry'}
    assert {v['commit'] for v in audit['inputs'].values()} == {audit['producer_commit']}
    for actual, row in zip(data['rows'], audit['rows']):
        ai, body = actual['actual_full_model_output'], actual['original_full_primary_body']
        raw = actual['actual_full_queue_entry']['raw']
        response = ai['_pulso_analysis_meta']
        assert hashlib.sha256(body.encode()).hexdigest() == row['body_sha256']
        assert canonical_sha(ai) == row['model_output_sha256']
        assert response['response_id'] == row['response_id']
        assert response['analysis_text_sha256'] == row['body_sha256']
        request = news_analysis_input(title=raw['title'], text=body,
                                      source_name=raw['source_name'], full_text=True)
        assert hashlib.sha256(request.encode()).hexdigest() == response['request_input_sha256']
        pin = dict(url=row['url'], publication_date=row['publication_date'],
                   body_sha256=row['body_sha256'], html_sha256=row['html_sha256'],
                   model_sha256=canonical_sha(ai), response_id=response['response_id'],
                   request_input_sha256=response['request_input_sha256'])
        assert canonical_sha(pin) == row['immutable_actual_model_primary_pin_sha256']
        assert raw['event_date'] == row['publication_date'] == raw['metadata']['publication_date']
        assert row['publication_approved'] is False
        assert actual['actual_status'] == row['actual_status'] == 'retry'
    assert all(row['producer_guard_replay_matches'] for row in audit['all12_original_guard_and_request_checks'])
    assert len(audit['all12_original_guard_and_request_checks']) == 12


def test_hanta_comparator_is_existing_published_primary_not_search_snippet():
    audit, data = fixture()
    old = data['hanta_published_comparator']
    assert old['publication_date'] == '2026-08-08'
    assert hashlib.sha256(old['original_full_primary_body'].encode()).hexdigest() == old['body_sha256']
    assert old['original_full_signal']['evidence_maturity'] == 'media_reported'
    assert old['original_signal_sha256'] == canonical_sha(old['original_full_signal'])
    assert audit['hanta_comparator']['prior_alert_quote'] in old['original_full_primary_body']
    hanta = next(r for r in audit['rows'] if r['row'] == 9)
    assert hanta['runtime_route'] == 'assess_contract_or_semantic_defect'


def test_second_peer_covers_every_actual_new_publication_without_promoting_pending():
    peer = json.loads((ROOT / PEER).read_text())
    assert peer['summary'] == dict(all12_read=True, actual_published=5, accept=1,
                                  correct=4, actual_rejected=2, actual_pending=5)
    assert len(peer['all12_primary_actual_output_read']) == 12
    assert len(peer['all_signals']) == 5
    assert peer['pending_publication_approved'] is False
    assert peer['reviewer_AI_calls'] == 0 and peer['state_mutated'] is False
    for row in peer['all_signals']:
        body, ai, signal = row['original_full_primary_body'], row['original_full_model_output'], row['original_full_signal']
        assert hashlib.sha256(body.encode()).hexdigest() == row['original_body_sha256']
        assert canonical_sha(signal) == row['original_signal_sha256']
        pin = dict(url=row['url'], publication_date=row['publication_date'],
                   body_sha256=row['original_body_sha256'], html_sha256=row['original_html_sha256'],
                   model_sha256=canonical_sha(ai), response_id=ai['_pulso_analysis_meta']['response_id'],
                   request_input_sha256=ai['_pulso_analysis_meta']['request_input_sha256'])
        assert canonical_sha(pin) == row['paired_immutable_actual_model_primary_pin_sha256']
        assert row['decision'] in {'accept', 'correct'}
        assert signal['evidence_maturity'] == 'media_reported'
        assert signal['editorial_relevance'] >= 72
