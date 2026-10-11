"""Validate the durable complete-original review without giving runtime credit."""
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'data/audits/pulso_expanded_editorial_originals_independent_review_2026_10_11.json'
FROZEN = 'b9c3ce2aea38107797fc19572581f27884d15611214fd2328d458bd35e906374'


def test_expanded_original_proof_has_complete_cohort_and_no_runtime_or_editorial_credit():
    report = json.loads(REPORT.read_text())
    rows = report['articles']
    assert len(rows) == len({row['url'] for row in rows}) == report['counts']['all_originals'] == 89
    assert all(all(row['raw_byte_integrity'].values()) for row in rows)
    assert all(all(row['source_comparisons'].values()) for row in rows)
    assert report['findings'] == []
    assert report['code_binding']['frozen_control_sha256'] == FROZEN
    assert report['acceptance_pass'] is False
    boundary = report['runtime_acceptance_boundary']
    assert boundary['queue_mutated'] is boundary['model_invoked'] is boundary['publication_approved'] is False
    assert boundary['editorial_threshold'] == 72 and boundary['evidence_stance'] == 'media_reported'
    assert boundary['later_source_queue_guard_repairs_require_new_real_core_qa'] is True


def test_every_new_url_retains_full_primary_body_hash_and_honest_conflict_or_video_state():
    report = json.loads(REPORT.read_text())
    review = report['all_31_new_url_original_semantic_reviews']
    rows = review['all_new_originals']
    assert len(rows) == len({row['url'] for row in rows}) == report['counts']['new_urls'] == 31
    assert {row['url'] for row in rows} == {row['url'] for row in report['articles'] if row['new_url_vs_cold58']}
    assert review['acceptance_pass'] is False
    for row in rows:
        body = row['primary_body_full']
        assert len(body) == row['primary_body_characters']
        assert hashlib.sha256(body.encode()).hexdigest() == row['primary_body_sha256']
        assert row['raw_sha_independently_verified'] and row['gzip_sha_independently_verified'] and row['canonical_verified']
        assert row['publication_or_gate_approval_claimed'] is False
        assert row['materiality_review']['approval_of_publication_or_AI_analysis'] is False
    conflicts = [row for row in rows if row['genuine_complete_primary_date_conflict']]
    assert len(conflicts) == 7
    assert all(row['publication_day_adopted'] is None and row['publication_date_verified'] is False for row in conflicts)
    videos = [row for row in rows if row['video_route'] and row['conservative_disposition'] == 'VIDEO_IDENTITY_DATE_VERIFIED_PRIMARY_TEXT_UNAVAILABLE']
    assert len(videos) == 10
    assert all(row['primary_body_full'] == '' and row['primary_body_characters'] == 0 for row in videos)
    assert all(row['retainer_declared_body_chars'] >= 160 and row['retainer_body_projection_matches_independent_primary'] is False for row in videos)


def test_all_liveblog_entries_keep_their_own_dates_across_the_document_date():
    report = json.loads(REPORT.read_text())
    docs = report['all_165_liveblog_entry_date_proof']
    assert len(docs) == 2
    assert sum(len(doc['all_updates']) for doc in docs) == 165
    for doc in docs:
        entries = doc['all_updates']
        assert len(entries) == len({entry['url'] for entry in entries}) == doc['updates']
        assert doc['all_entry_date_proof_failures'] == []
        assert doc['document_publication_does_not_replace_entry_dates'] is True
        assert all(entry['html_datetime_equals_json_datePublished'] for entry in entries)
        assert all(entry['url'].startswith(doc['url'] + '#lbp-') for entry in entries)
    national = next(doc for doc in docs if '/nacional/' in doc['url'])
    assert national['document_publication_date'] == '2026-10-08'
    assert Counter(row['timestamp_calendar_day'] for row in national['all_updates']) == {'2026-10-08': 34, '2026-10-09': 21}
    assert Counter(row['america_santiago_day'] for row in national['all_updates']) == {'2026-10-08': 52, '2026-10-09': 3}
