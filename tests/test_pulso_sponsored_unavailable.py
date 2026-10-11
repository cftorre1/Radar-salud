"""The exact publisher's empty commercial story is held, never fabricated."""
import gzip
import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.processing import DeferredProcessing
from radar_salud.pulso_source import (_verified_detail, TextUnavailableArticle, extract_article,
                                     verified_sponsored_without_text)

ROOT = Path(__file__).parents[1]
FOLDER = ROOT / 'tests/fixtures/pulso_targeted_primary_real'
RECORD = next(row for row in json.loads((FOLDER/'manifest.json').read_text())['requests']
              if row['sha256'] == 'eec1ca11083227a69b3691afe92422d5d20332eae39afee234f43d027c63535d')
REASON = 'publisher_sponsored_text_unavailable'
spec = importlib.util.spec_from_file_location('independent_pulso_qa', ROOT/'scripts/qa_pulso_recovery.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


def original():
    compressed = (FOLDER/RECORD['gzip_file']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == RECORD['gzip_sha256']
    raw = gzip.decompress(compressed)
    assert len(raw) == RECORD['bytes'] == 410950
    assert hashlib.sha256(raw).hexdigest() == RECORD['sha256']
    return raw.decode(RECORD['charset'])


def detail(html=None):
    return _verified_detail(dict(url=RECORD['url'], listing='official_sitemap',
                                 lastmod='2026-10-11T09:00:04.775Z'), lambda _: html or original(), None)


def test_actual_original_corroborates_date_and_empty_bound_fusion_body_not_the_long_subtitle():
    result = detail()
    metadata = result['metadata']
    assert result['relevant'] and result['deferred_reason'] == REASON
    assert metadata['publication_date'] == metadata['visible_publication_date'] == '2026-10-11'
    assert metadata['publication_timestamp'] == '2026-10-11T09:00:00Z'
    assert metadata['html_sha256'] == RECORD['sha256']
    assert metadata['primary_identity_verified'] and metadata['publication_date_verified']
    assert metadata['article_verified'] is metadata['article_body_complete'] is False
    assert len(metadata['description']) > 160 and metadata['page_text'] == result['body'] == ''
    assert metadata['article_body_characters'] == 0 and metadata['article_body_sha256'] == hashlib.sha256(b'').hexdigest()
    assert metadata['sponsored_text_evidence']['fusion_story_id'] == 'ICIYD2SPIZHAFDXQG4WCTDDDHQ'
    assert metadata['sponsored_text_evidence']['primary_body_region_count'] == 1
    assert metadata['source_quality_gate'] == 'deferred_sponsored_text'
    assert verified_sponsored_without_text(metadata)


def test_actual_unknown_commercial_body_defers_without_inventing_a_nonhealth_title_exclusion_or_spending_ai(monkeypatch):
    result = detail()
    raw = RawItem('pulso_latercera', result['title'], RECORD['url'], 'Pulso / La Tercera',
                  'press_high_trust', result['metadata']['publication_date'], '', result['metadata'])
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda _: pytest.fail('A verified limitation needs no refetch'))
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **_: pytest.fail('Unknown commercial content cannot reach AI'))
    with pytest.raises(DeferredProcessing, match='^'+REASON+'$'):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.metadata['editorial_assessment'] == dict(decision='pending', reason=REASON)
    assert 'analysis_input_complete' not in raw.metadata and 'rejection_reason' not in raw.metadata


def test_warm_original_reuses_only_the_verified_limitation_and_preserves_original_capture():
    cold = detail()
    entry = dict(url=RECORD['url'], listing='official_sitemap', lastmod=cold['lastmod'])
    warm = _verified_detail(entry, lambda _: pytest.fail('Validated unchanged empty story should reuse original'), cold)
    assert warm['cache_hit'] and warm['metadata'] == cold['metadata']
    assert verified_sponsored_without_text(warm['metadata'])


@pytest.mark.parametrize('mutation', ['nonempty_fusion', 'fusion_identity', 'dom_text', 'missing_region',
                                     'ordinary_factual', 'unbound_article', 'publication_conflict', 'unsupported_json_body'])
def test_original_structural_tampering_cannot_excuse_ordinary_incomplete_or_unparsed_primary_text(mutation):
    # Explicit mutations are regression probes, not additional publisher evidence.
    html = original()
    if mutation == 'nonempty_fusion':
        html = html.replace('"content":"","type":"text"', '"content":"El hospital amplía capacidad.","type":"text"', 1)
    elif mutation == 'fusion_identity':
        html = html.replace('"canonical_url":"/branded/noticia/empresas-x-chile-', '"canonical_url":"/branded/noticia/unbound-', 1)
    elif mutation == 'dom_text':
        html = html.replace('<div class="article-right-rail__body">', '<div class="article-right-rail__body"><div>Texto primario no recuperado.</div>', 1)
    elif mutation == 'missing_region':
        html = html.replace('class="article-right-rail__body"', 'class="unknown-body"', 1)
    elif mutation == 'ordinary_factual':
        html = html.replace('"articleSection":"Branded"', '"articleSection":"Nacional"', 1)
    elif mutation == 'unbound_article':
        html = html.replace('"url":"'+RECORD['url']+'"', '"url":"https://www.latercera.com/branded/noticia/other/"', 1)
    elif mutation == 'unsupported_json_body':
        html = html.replace('"articleSection":"Branded"', '"articleBody":["Contenido primario no compatible"],"articleSection":"Branded"', 1)
    else:
        html = html.replace('"datePublished":"2026-10-11T09:00:00Z"', '"datePublished":"2026-10-10T09:00:00Z"', 1)
    assert html != original(), mutation
    result = detail(html)
    assert result.get('status') == 'detail_error', (mutation, result)
    assert result.get('deferred_reason') is None


@pytest.mark.parametrize('change', ['body', 'date', 'proof', 'type', 'capture_future', 'factual_taxonomy'])
def test_saved_empty_commercial_proof_requires_revalidation_when_any_primary_claim_changes(change):
    result = detail()
    metadata = deepcopy(result['metadata'])
    if change == 'body':
        metadata['page_text'] = metadata['description']
    elif change == 'date':
        metadata['publication_date_verified'] = False
    elif change == 'proof':
        metadata['sponsored_text_evidence']['fusion_text_characters'] = 1
    elif change == 'type':
        metadata['article_verified'] = True
    elif change == 'capture_future':
        metadata['captured_at'] = '2099-01-01T00:00:00Z'
    else:
        metadata['publisher_taxonomy']['classification'] = 'factual'
    assert not verified_sponsored_without_text(metadata)


def test_independent_reader_reopens_exact_original_and_never_calls_it_verified_article_content():
    result = detail()
    metadata = result['metadata']
    capture = dict(RECORD, gzip_file=str(Path('tests/fixtures/pulso_targeted_primary_real')/RECORD['gzip_file']))
    row = dict(url=RECORD['url'], publication_date='2026-10-11', publication_date_verified=True,
               primary_detail_sha256=RECORD['sha256'], original_http_captures=[capture])
    trace = dict(metadata, url=RECORD['url'], status='discovered_metadata_only', reason=REASON)
    proof, errors = qa.verify_publisher_exception(row, metadata, [trace], ROOT)
    assert errors is None, errors
    assert proof['publication_date_verified'] and proof['article_content_verified'] is False
    assert proof['body_characters'] == 0
    # Self-consistent metadata is insufficient if the publisher section/date
    # or the exact raw capture binding is gone.
    metadata['sponsored_text_evidence']['fusion_text_characters'] = 1
    trace['sponsored_text_evidence'] = metadata['sponsored_text_evidence']
    assert qa.verify_publisher_exception(row, metadata, [trace], ROOT)[1]


def test_empty_commercial_candidate_completes_count_delimited_inventory_without_health_text_credit(tmp_path):
    from datetime import date
    from radar_salud.pulso_source import discover_public_feeds
    def loader(url):
        if '/canal/' in url:
            return ''
        if '/pf/api/' in url:
            return json.dumps(dict(count=1, next=None, content_elements=[dict(
                canonical_url=RECORD['url'], first_publish_date='2026-10-11T09:00:00Z',
                last_updated_date='2026-10-11T09:00:04.775Z')]))
        assert url == RECORD['url']
        return original()
    audit = []
    candidates, coverage = discover_public_feeds(loader, audit, tmp_path/'cache.json',
                                                today=date(2026, 10, 11), feeds=[('tag', 'salud')])
    assert coverage['coverage_complete']
    assert next(row for row in audit if row['status'] == 'public_feed_coverage')['errors'] == 0
    assert coverage['new_inventory_urls'] == 1 and coverage['new_health_urls'] == 0
    assert coverage['metadata_only_sponsored_text_unavailable_candidates'] == 1
    assert coverage['publication_date_coverage_complete'] and not coverage['article_content_coverage_complete']
    assert len(candidates) == 1 and verified_sponsored_without_text(candidates[0].metadata)
    assert not any(row['status'] in ('detail_error', 'listing_error') for row in audit)
