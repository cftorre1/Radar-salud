"""Real document dates cannot stand in for 165 independently dated entries."""
import gzip
import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.processing import DeferredProcessing
from radar_salud.pulso_source import (
    _verified_detail, article_body_evidence, complete_article_body, extract_article,
    liveblog_analysis_text, verified_liveblog_temporal_evidence,
)
from radar_salud.pulso_editorial_proof import PROOF_SCHEMA, validate_pulso_editorial_proof
from pulso_editorial_test_support import valid_assessment


REAL = Path(__file__).parent / 'fixtures/pulso_liveblog_temporal_real'
FIXTURES = json.loads((REAL / 'manifest.json').read_text())['fixtures']


def original(entry):
    compressed = (REAL / entry['path']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == entry['gzip_sha256']
    payload = gzip.decompress(compressed)
    assert hashlib.sha256(payload).hexdigest() == entry['sha256']
    return payload.decode(entry['charset'])


def raw_original(entry, html=None):
    title, body, metadata = extract_article(html or original(entry), entry['url'])
    metadata.update(article_body_evidence(body), captured_at=entry['captured_at'],
                    market_role='media', source_quality_gate='passed')
    return RawItem('pulso_latercera', title, entry['url'], 'Pulso / La Tercera',
                   'press_high_trust', metadata['publication_date'], body[:1800], metadata)


def model_requests(monkeypatch):
    requests = []
    def create(**kwargs):
        requests.append(kwargs)
        prefix, body = kwargs['input'].split('Contenido:\n', 1)
        source, title = prefix.split('\nTítulo: ', 1)
        request = dict(source_name=source.removeprefix('Fuente: '), title=title.rstrip('\n'), text=body)
        assessment = dict(relevance_score=71, what_happened='', why_it_matters='',
                          reason='Sin suficiente materialidad incremental para publicación.')
        if 'hemos suspendido la atención del Servicio de Urgencias' in body:
            start = body.index('La Red UC Christus emitió un comunicado')
            end = body.index('viernes 9 de octubre', start) + len('viernes 9 de octubre')
            quote = ' '.join(body[start:end].split())
            assessment = valid_assessment(assessment, request, witness=dict(
                actor='La Red UC Christus',
                action='hemos suspendido la atención del Servicio de Urgencias',
                consequence='consultas médicas, exámenes y procedimientos ambulatorios durante hoy jueves y mañana viernes 9 de octubre',
                quote=quote, consequence_quote=quote, status='mixed_actual_and_future',
                what='Según La Tercera, UC Christus informó la suspensión preventiva; el comunicado prevé mantenerla el viernes 9 de octubre.',
                why='La medida podría limitar la atención ambulatoria durante el período anunciado; el comunicado no acredita evacuaciones.'))
            # The API wrapper must produce the binding from this actual mock
            # response, rather than receiving a prebound assessment shortcut.
            assessment.pop('_pulso_analysis_meta')
        else:
            quote = ('criticó la reducción de recursos para municipios, educación y salud, '
                     'especialmente en medio de las emergencias climáticas')
            assert quote in ' '.join(body.split())
            # The political speech names health among broad budget objections;
            # it supplies no specific clinical obligation. The scope rejection
            # is intentional, while all 110 original entry texts still reach
            # the same full-input API boundary for this assessment.
            proof = {field: '' for field in PROOF_SCHEMA['properties']}
            proof.update(scope_decision='incidental_health', scope_reason='Mención de salud en una objeción política general sin obligación clínica específica.',
                         human_health_scope_quote=quote, event_status='actual',
                         novelty_decision='new_material_information', future_claims=[])
            assessment['pulso_editorial_proof'] = proof
            assert validate_pulso_editorial_proof(assessment, body)['reason'] == 'pulso_editorial_incidental_health'
        return SimpleNamespace(output_text=json.dumps(assessment, ensure_ascii=False),
                               id='unit-test-liveblog-response', model='unit-test-no-paid-call')
    monkeypatch.setattr(llm_analysis, '_client', lambda: SimpleNamespace(responses=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_analysis, 'allow_call', lambda _: True)
    monkeypatch.setattr(llm_analysis, 'record_response', lambda *a, **kw: None)
    monkeypatch.setattr(llm_analysis, 'record_result', lambda *a, **kw: None)
    return requests


@pytest.mark.parametrize('entry', FIXTURES, ids=lambda row: row['url'].split('/')[-2])
def test_all_165_real_entry_dates_and_exact_json_bodies_supplement_unchanged_primary_projection(entry):
    raw = raw_original(entry)
    metadata = raw.metadata
    assert verified_liveblog_temporal_evidence(metadata)
    assert metadata['article_body_characters'] == entry['baseline_article_body_characters']
    assert metadata['article_body_sha256'] == entry['baseline_article_body_sha256']
    assert metadata['html_sha256'] == entry['sha256']
    assert metadata['captured_at'] == entry['captured_at']
    proof = metadata['liveblog_temporal_evidence']
    assert proof['document_publication_timestamp'] == entry['original_document_publication_timestamp']
    assert proof['document_modified_timestamp'] == entry['original_document_modified_timestamp']
    assert len(proof['entries']) == len(entry['expected_entries'])
    for actual, expected in zip(proof['entries'], entry['expected_entries']):
        assert actual['url'] == expected['url']
        assert actual['timestamp'] == actual['html_datetime'] == expected['datetime']
        assert actual['timestamp_calendar_day'] == expected['timestamp_calendar_day']
        assert actual['publisher_day'] == expected['america_santiago_day']
        assert actual['body_characters'] == expected['body_chars']
        assert actual['body_sha256'] == expected['body_sha256']
        assert actual['html_body_corroboration'] in {
            'primary_entry_paragraphs', 'bound_heading_without_primary_paragraphs'}
        assert actual['html_primary_text_sha256'] == hashlib.sha256(
            ' '.join(actual['body'].split()).encode()).hexdigest()
    assert raw.event_date == proof['document_publication_date']
    assert metadata['publication_date_verified'] is True
    assert metadata['publisher_date_convention'] != 'unresolved_primary_publisher_date_conflict'
    if '/nacional/' in raw.url:
        assert raw.event_date == '2026-10-08'
        assert Counter(row['publisher_day'] for row in proof['entries']) == {'2026-10-08': 52, '2026-10-09': 3}
        assert sum(row['timestamp_calendar_day'] != row['publisher_day'] for row in proof['entries']) == 18
    else:
        assert raw.event_date == '2026-07-21'
        assert sum(row['body'].endswith(' ') for row in proof['entries']) == 2


@pytest.mark.parametrize('entry', FIXTURES, ids=lambda row: row['url'].split('/')[-2])
def test_actual_responses_payload_contains_entire_body_and_every_dated_entry_with_strict_editorial_rejection(entry, monkeypatch):
    raw = raw_original(entry)
    before = deepcopy({key: raw.metadata[key] for key in ('page_text', 'article_body_sha256', 'html_sha256', 'captured_at')})
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda _: pytest.fail('Valid complete timeline needs no refetch'))
    requests = model_requests(monkeypatch)
    assert beta_sources.process_curated_beta_source(raw, {}) is None
    assert len(requests) == 1
    request = requests[0]['input']
    content = request.split('Contenido:\n', 1)[1]
    assert content == liveblog_analysis_text(raw.metadata)
    assert before['page_text'] in content
    for update in raw.metadata['liveblog_temporal_evidence']['entries']:
        assert update['url'] in content and update['timestamp'] in content and update['publisher_day'] in content
        assert update['body'] in content
    assert {key: raw.metadata[key] for key in before} == before
    assert raw.metadata['analysis_base_article_body_sha256'] == before['article_body_sha256']
    assert raw.metadata['analysis_input_body_sha256'] == hashlib.sha256(content.encode()).hexdigest()
    assert raw.metadata['analysis_input_body_sha256'] != before['article_body_sha256']
    assert raw.metadata['analysis_input_characters'] == len(content)
    assert raw.metadata['analysis_request_input_sha256'] == hashlib.sha256(request.encode()).hexdigest()
    assert raw.metadata['analysis_request_input_characters'] == len(request)
    assert raw.metadata['analysis_input_complete'] is True
    assert raw.metadata['editorial_assessment']['threshold'] == 72
    expected = ('editorial_relevance_below_threshold' if '/nacional/' in raw.url
                else 'pulso_editorial_incidental_health')
    assert raw.metadata['rejection_reason'] == expected
    assert raw.metadata['analysis_model_output']['relevance_score'] == 71
    assert raw.metadata['pulso_editorial_proof_validation']['model_response']['response_id'] == 'unit-test-liveblog-response'
    assert 'no convertir reporte de prensa en hecho oficial' in requests[0]['instructions']


def test_real_uc_and_andes_statements_keep_report_date_separate_from_planned_october9_actions():
    raw = raw_original(FIXTURES[0])
    updates = raw.metadata['liveblog_temporal_evidence']['entries']
    uc = next(row for row in updates if 'hemos suspendido la atención del Servicio de Urgencia' in row['body'])
    andes = next(row for row in updates if 'cirugías' in row['body'] and 'viernes 9' in row['body'])
    assert uc['publisher_day'] == andes['publisher_day'] == '2026-10-08'
    assert 'hoy jueves' in uc['body'] and 'mañana viernes 9' in uc['body']
    assert 'no ha sido necesario realizar evacuaciones' in uc['body']
    assert 'podrían' in andes['body'] or 'podría' in andes['body']
    assert any(row['publisher_day'] == '2026-10-09' for row in updates)


@pytest.mark.parametrize('entry', FIXTURES)
def test_warm_verified_timeline_cache_retains_capture_time_and_complete_base_body(entry):
    raw = raw_original(entry)
    lastmod = entry['original_document_modified_timestamp']
    listing = dict(url=raw.url, listing='official_sitemap', lastmod=lastmod)
    cached = dict(url=raw.url, title=raw.title, body=raw.raw_text, metadata=raw.metadata, relevant=True, lastmod=lastmod)
    reused = _verified_detail(listing, lambda _: pytest.fail('Warm cache should not rewrite capture proof'), cached)
    assert reused['cache_hit'] and verified_liveblog_temporal_evidence(reused['metadata'])
    assert reused['metadata']['captured_at'] == entry['captured_at']
    assert reused['metadata']['article_body_sha256'] == entry['baseline_article_body_sha256']


@pytest.mark.parametrize('mutation', ['html_datetime', 'visible_day', 'missing_json_identity'])
def test_unverified_entry_timeline_defers_before_analysis_without_fabricating_document_date_conflict(mutation, monkeypatch):
    entry = FIXTURES[0]
    html = original(entry)
    if mutation == 'html_datetime':
        html = html.replace('dateTime="2026-10-09T09:52:16.032Z"', 'dateTime="2026-10-08T09:52:16.032Z"', 1)
    elif mutation == 'visible_day':
        html = html.replace('>09 OCTUBRE</time>', '>08 OCTUBRE</time>', 1)
    else:
        html = html.replace('"@type":"LiveBlogPosting"', '"@type":"UnsupportedTimeline"', 1)
    assert html != original(entry)
    raw = raw_original(entry, html)
    assert raw.metadata['publisher_document_type'] == 'liveblog'
    assert not verified_liveblog_temporal_evidence(raw.metadata)
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda _: html)
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('Unverified temporal payload must not reach AI'))
    with pytest.raises(DeferredProcessing, match='publisher_liveblog_entry_dates_unverified'):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.event_date == raw.metadata['publication_date'] == '2026-10-08'
    assert raw.metadata['publication_date_verified'] is True
    assert complete_article_body(raw.metadata) and raw.metadata['article_body_complete'] is True
    assert raw.metadata['editorial_assessment']['reason'] == 'publisher_liveblog_entry_dates_unverified'
    assert 'analysis_input_complete' not in raw.metadata


@pytest.mark.parametrize('mutation', ['json_body_only', 'dom_paragraph_only'])
def test_entry_text_must_match_its_original_dom_before_full_timeline_reaches_model(mutation, monkeypatch):
    # Explicit adversarial mutation of a real original, never publisher evidence.
    entry = FIXTURES[0]
    html = original(entry)
    invented = ' La clínica informó cierre definitivo de urgencias durante todo octubre.'
    baseline = raw_original(entry)
    if mutation == 'json_body_only':
        scripts = re.compile(r'(<script[^>]+type="application/ld\+json"[^>]*>)(.*?)(</script>)', re.S)
        for match in scripts.finditer(html):
            node = json.loads(match[2])
            if node.get('@type') == 'LiveBlogPosting':
                node['liveBlogUpdate'][0]['articleBody'] += invented
                html = (html[:match.start(2)] + json.dumps(node, ensure_ascii=False,
                        separators=(',', ':')) + html[match.end(2):])
                break
        else:
            pytest.fail('Original URL-bound LiveBlogPosting not found')
    else:
        paragraph = ('<p class="article-body__paragraph">Desde Transporte Informa, '
                     'señalan de calles inhabilitadas tras aluvión. </p>')
        assert paragraph in html
        html = html.replace(paragraph, paragraph.replace('</p>', invented + '</p>'), 1)
    raw = raw_original(entry, html)
    assert raw.metadata['liveblog_temporal_evidence']['errors'] == [
        dict(index=0, reason='liveblog_entry_body_mismatch')]
    assert not verified_liveblog_temporal_evidence(raw.metadata)
    if mutation == 'json_body_only':
        assert raw.metadata['article_body_sha256'] == baseline.metadata['article_body_sha256']
        assert raw.metadata['page_text'] == baseline.metadata['page_text']
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda _: html)
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('Uncorroborated entry must not reach AI'))
    with pytest.raises(DeferredProcessing, match='publisher_liveblog_entry_dates_unverified'):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.event_date == raw.metadata['publication_date'] == '2026-10-08'
    assert raw.metadata['publication_date_verified'] is True
    assert complete_article_body(raw.metadata)
    assert raw.metadata['editorial_assessment']['reason'] == 'publisher_liveblog_entry_dates_unverified'
    assert 'analysis_input_complete' not in raw.metadata


def test_legacy_html_body_cache_fetches_primary_structure_before_dated_model_input(monkeypatch):
    entry = FIXTURES[0]
    raw = raw_original(entry)
    for key in ('publisher_document_type', 'liveblog_temporal_evidence', 'liveblog_temporal_evidence_verified'):
        raw.metadata.pop(key)
    calls = []
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda url: calls.append(url) or original(entry))
    requests = model_requests(monkeypatch)
    assert beta_sources.process_curated_beta_source(raw, {}) is None
    assert calls == [raw.url] and len(requests) == 1
    assert verified_liveblog_temporal_evidence(raw.metadata)
    assert 'fecha visible: 2026-10-09' in requests[0]['input']


@pytest.mark.parametrize('corruption', ['missing_entry', 'entry_body', 'document_timestamp',
                                      'entry_timestamp', 'original_hash', 'verification_flag', 'evidence_type',
                                      'dom_corroboration', 'dom_body_hash'])
def test_corrupt_saved_temporal_proof_cannot_bypass_primary_revalidation(corruption, monkeypatch):
    raw = raw_original(FIXTURES[0])
    proof = raw.metadata['liveblog_temporal_evidence']
    if corruption == 'missing_entry':
        proof['entries'].pop()
    elif corruption == 'entry_body':
        proof['entries'][0]['body'] += 'Invented change'
    elif corruption == 'document_timestamp':
        proof['document_publication_timestamp'] = '2026-10-09T09:54:31Z'
    elif corruption == 'entry_timestamp':
        proof['entries'][0]['timestamp'] = '2026-10-08T09:52:16.032Z'
    elif corruption == 'original_hash':
        proof['original_html_sha256'] = '0' * 64
    elif corruption == 'verification_flag':
        raw.metadata['liveblog_temporal_evidence_verified'] = False
    elif corruption == 'dom_corroboration':
        proof['entries'][0].pop('html_body_corroboration')
    elif corruption == 'dom_body_hash':
        proof['entries'][0]['html_primary_text_sha256'] = '0' * 64
    else:
        raw.metadata['publication_evidence'] = None
    if corruption in {'dom_corroboration', 'dom_body_hash'}:
        # Recomputed container hash cannot substitute for a missing/invalid
        # entry-level DOM corroboration contract.
        proof['entries_sha256'] = hashlib.sha256(json.dumps(proof['entries'], ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert not verified_liveblog_temporal_evidence(raw.metadata)
    def unavailable(_):
        raise OSError('Original unavailable')
    monkeypatch.setattr(beta_sources, 'fetch_html', unavailable)
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('Unverified temporal proof cannot reach AI'))
    with pytest.raises(DeferredProcessing, match='article verification failed'):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.event_date == '2026-10-08'
    assert 'analysis_input_complete' not in raw.metadata


def test_legacy_format_revalidation_does_not_depend_on_liveblog_title_or_route_words(monkeypatch):
    # Explicitly synthetic routing mutation of real HTML, not live-site proof.
    entry = deepcopy(FIXTURES[0])
    route = 'https://www.latercera.com/nacional/noticia/cobertura-de-jornada/'
    html = original(entry).replace(entry['url'], route)
    entry['url'] = route
    raw = raw_original(entry, html)
    raw.title = 'Actualización de la jornada'
    for key in ('publisher_document_type', 'liveblog_temporal_evidence', 'liveblog_temporal_evidence_verified'):
        raw.metadata.pop(key)
    calls = []
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda url: calls.append(url) or html)
    requests = model_requests(monkeypatch)
    assert beta_sources.process_curated_beta_source(raw, {}) is None
    assert calls == [route] and len(requests) == 1
    assert verified_liveblog_temporal_evidence(raw.metadata)
    assert 'fecha visible: 2026-10-09' in requests[0]['input']


def test_ordinary_html_body_article_remains_cacheable_after_one_structural_classification():
    # Synthetic ordinary article: title vocabulary alone is no format proof.
    url = 'https://www.latercera.com/nacional/noticia/jornada-de-salud/'
    node = dict(url=url, headline='Minuto a minuto de una jornada de salud',
                **{'@type': 'NewsArticle', 'datePublished': '2026-10-09'})
    html = (f'<link rel="canonical" href="{url}"><script type="application/ld+json">'
            + json.dumps(node) + '</script><article><div class="article-body"><p>'
            + 'El hospital revisó los antecedentes del funcionamiento de su red asistencial. ' * 6
            + '</p></div></article>')
    entry = dict(url=url, listing='official_sitemap', lastmod='2026-10-10T12:00:00Z')
    captured = _verified_detail(entry, lambda _: html, None)
    assert captured['metadata']['body_source'] == 'article_html'
    assert captured['metadata']['publisher_document_type'] == 'article'
    assert 'liveblog_temporal_evidence' not in captured['metadata']
    cached = _verified_detail(entry, lambda _: pytest.fail('Ordinary HTML article needs no repeated refetch'), captured)
    assert cached['cache_hit'] and cached['metadata']['captured_at'] == captured['metadata']['captured_at']
