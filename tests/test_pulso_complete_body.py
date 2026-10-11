"""Primary text must survive discovery, old caches and the actual model input.

The real original fixture tests use captured publisher bytes; long adversarial
HTML cases below are explicitly synthetic and establish no live coverage.
"""
import gzip
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.processing import DeferredProcessing
from radar_salud.pulso_source import (
    _verified_detail, article_body_evidence, complete_article_body, extract_article, health_anchor,
)

REAL = Path(__file__).parent / 'fixtures/pulso_real'
URL = 'https://www.latercera.com/pulso/noticia/gobierno-anuncia-nueva-gestion/'


def synthetic_original():
    # Its only health-sector change occurs past the former discovery/AI caps.
    body = ('Las autoridades revisaron los antecedentes y el calendario de trabajo. ' * 280
            + 'El hospital anuncia un recorte de presupuesto que reduce capacidad de sus pabellones y prestaciones.')
    node = {'@type': 'NewsArticle', 'url': URL,
            'headline': 'Gobierno anuncia un cambio al calendario de gestión',
            'datePublished': '2026-10-09', 'articleBody': body}
    html = (f'<link rel="canonical" href="{URL}">'
            + '<script type="application/ld+json">' + json.dumps(node) + '</script>')
    return html, ' '.join(body.split())


def raw_from_original(html, url=URL):
    title, body, metadata = extract_article(html, url)
    metadata.update(article_body_evidence(body), market_role='media', source_quality_gate='passed')
    return RawItem('pulso_latercera', title, url, 'Pulso / La Tercera',
                   'press_high_trust', metadata['publication_date'], body[:1800], metadata)


def actual_model_input(monkeypatch):
    requests = []
    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(output_text=json.dumps({
            'relevance_score': 71, 'what_happened': '', 'why_it_matters': '',
            'reason': 'Evaluación bajo el umbral editorial vigente.'}))
    monkeypatch.setattr(llm_analysis, '_client', lambda: SimpleNamespace(responses=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_analysis, 'allow_call', lambda kind: True)
    monkeypatch.setattr(llm_analysis, 'record_response', lambda *args, **kwargs: None)
    monkeypatch.setattr(llm_analysis, 'record_result', lambda *args, **kwargs: None)
    return requests


def test_real_senior_housing_primary_tail_reaches_actual_response_input_without_lowering_gate(monkeypatch):
    entry = next(entry for entry in json.loads((REAL / 'manifest.json').read_text())['fixtures']
                 if 'senior_housing.html.gz' in entry['path'])
    payload = gzip.decompress((REAL / 'senior_housing.html.gz').read_bytes())
    assert hashlib.sha256(payload).hexdigest() == entry['sha256']
    raw = raw_from_original(payload.decode('utf-8'), entry['url'])
    body = raw.metadata['page_text']
    assert len(body) > 10000
    requests = actual_model_input(monkeypatch)
    assert beta_sources.process_curated_beta_source(raw, {}) is None
    assert requests[0]['input'].split('Contenido:\n', 1)[1] == body
    assert body[-500:] in requests[0]['input']
    assert raw.metadata['analysis_input_body_sha256'] == raw.metadata['article_body_sha256']
    assert raw.metadata['analysis_input_characters'] == len(body)
    assert raw.metadata['analysis_input_complete'] is True
    assert raw.metadata['editorial_assessment']['threshold'] == 72
    assert raw.metadata['rejection_reason'] == 'editorial_relevance_below_threshold'


def test_real_generic_aluvion_headline_preserves_clinical_tail_after_5500_in_actual_response_input(monkeypatch):
    folder = Path(__file__).parent / 'fixtures/pulso_targeted_primary_real'
    entry = next(entry for entry in json.loads((folder / 'manifest.json').read_text())['requests']
                 if 'mas-de-2000-viviendas-afectadas' in entry['url'])
    compressed = (folder / entry['gzip_file']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == entry['gzip_sha256']
    payload = gzip.decompress(compressed)
    assert hashlib.sha256(payload).hexdigest() == entry['sha256']
    raw = raw_from_original(payload.decode('utf-8'), entry['url'])
    body = raw.metadata['page_text']
    assert not health_anchor(raw.title)
    assert raw.event_date == '2026-10-09'
    assert len(body) == entry['primary_date_and_body_audit']['primary_body_chars'] == 5781
    assert raw.metadata['article_body_sha256'] == entry['primary_date_and_body_audit']['primary_body_sha256']
    assert body.index('evacuación horizontal') > 5500
    assert body.index('La Clínica Las Condes permanece operativa') > 5500
    assert body.index('Hospital Dipreca') > 5500
    assert body.index('RedSalud Vitacura') > 5500
    requests = actual_model_input(monkeypatch)
    assert beta_sources.process_curated_beta_source(raw, {}) is None
    assert len(requests) == 1
    assert requests[0]['input'].split('Contenido:\n', 1)[1] == body
    assert body[5500:] in requests[0]['input']
    assert raw.metadata['analysis_input_body_sha256'] == raw.metadata['article_body_sha256']
    assert raw.metadata['analysis_input_characters'] == 5781
    assert raw.metadata['analysis_input_complete'] is True
    assert raw.metadata['editorial_assessment']['threshold'] == 72
    assert raw.metadata['rejection_reason'] == 'editorial_relevance_below_threshold'


def test_default_news_call_still_uses_5500_characters(monkeypatch):
    requests = actual_model_input(monkeypatch)
    body = 'x' * 5500 + 'Important tail for a different source'
    llm_analysis.analyze_news(title='Other source', text=body, source_name='Other publisher')
    assert requests[0]['input'].split('Contenido:\n', 1)[1] == body[:5500]


def test_primary_health_change_beyond_18000_survives_discovery_prefilter_and_model(monkeypatch):
    html, body = synthetic_original()
    entry = {'url': URL, 'listing': 'https://www.latercera.com/canal/pulso/', 'lastmod': '2026-10-10T12:00:00Z'}
    result = _verified_detail(entry, lambda url: html, None)
    assert result['relevant'] and complete_article_body(result['metadata'])
    assert result['metadata']['page_text'] == body and len(body) > 18000
    raw = RawItem('pulso_latercera', result['title'], URL, 'Pulso / La Tercera',
                  'press_high_trust', result['metadata']['publication_date'], result['body'], result['metadata'])
    requests = actual_model_input(monkeypatch)
    assert beta_sources.process_curated_beta_source(raw, {}) is None
    assert len(requests) == 1
    assert requests[0]['input'].split('Contenido:\n', 1)[1] == body
    assert raw.metadata['rejection_reason'] == 'editorial_relevance_below_threshold'


@pytest.mark.parametrize('corruption', ['truncated', 'missing_hash', 'wrong_hash', 'wrong_length'])
def test_old_positive_cache_requires_complete_body_proof_before_reuse(corruption):
    html, body = synthetic_original()
    entry = {'url': URL, 'listing': 'https://www.latercera.com/canal/pulso/', 'lastmod': '2026-10-10T12:00:00Z'}
    cached = _verified_detail(entry, lambda url: html, None)
    if corruption == 'truncated':
        cached['metadata']['page_text'] = body[:18000]
    elif corruption == 'missing_hash':
        del cached['metadata']['article_body_sha256']
    elif corruption == 'wrong_hash':
        cached['metadata']['article_body_sha256'] = '0' * 64
    else:
        cached['metadata']['article_body_characters'] -= 1
    calls = []
    refreshed = _verified_detail(entry, lambda url: calls.append(url) or html, cached)
    assert calls == [URL] and not refreshed['cache_hit']
    assert refreshed['metadata']['page_text'] == body
    assert complete_article_body(refreshed['metadata'])
    reused = _verified_detail(entry, lambda url: pytest.fail('Complete original must remain cacheable'), refreshed)
    assert reused['cache_hit'] and reused['metadata']['page_text'] == body


def test_incomplete_legacy_body_refetch_preserves_hold_and_capture_bookkeeping(monkeypatch):
    html, body = synthetic_original()
    raw = raw_from_original(html)
    raw.metadata.update(page_text=body[:18000], editorial_hold='requires_incremental_review',
                        detected_at='2026-10-10T10:00:00Z', attempts=3, ingestion_mode='BACKFILL',
                        retry_at='2026-10-11T07:00:00Z')
    bookkeeping = deepcopy({key: raw.metadata[key] for key in ('editorial_hold', 'detected_at', 'attempts', 'ingestion_mode', 'retry_at')})
    calls = []
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda url: calls.append(url) or html)
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('Hold must prevent analysis'))
    with pytest.raises(DeferredProcessing, match='incremental-value'):
        beta_sources.process_curated_beta_source(raw, {})
    assert calls == [URL] and complete_article_body(raw.metadata)
    assert {key: raw.metadata[key] for key in bookkeeping} == bookkeeping
    assert raw.metadata['editorial_assessment']['reason'] == 'requires_incremental_review'


def test_hash_missing_refetch_failure_defers_before_materiality_and_paid_analysis(monkeypatch):
    html, _ = synthetic_original()
    raw = raw_from_original(html)
    del raw.metadata['article_body_sha256']
    def unavailable(url):
        raise OSError('Publisher unavailable')
    monkeypatch.setattr(beta_sources, 'fetch_html', unavailable)
    monkeypatch.setattr(beta_sources, '_material', lambda *args: pytest.fail('Unverified body must not reach the gate'))
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('Must not spend analysis'))
    with pytest.raises(DeferredProcessing, match='article verification failed'):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.metadata['article_body_complete'] is False
    assert raw.metadata['editorial_assessment']['reason'] == 'article_verification_failed'
