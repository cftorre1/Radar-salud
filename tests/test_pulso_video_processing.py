"""Unavailable original video transcripts remain pending before paid analysis."""
import gzip
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.processing import DeferredProcessing
from radar_salud.pulso_source import (_Article, _verified_detail, article_body_evidence,
                                    verified_video_without_text)


REAL = Path(__file__).parent / 'fixtures/pulso_thin_primary_real'
VIDEOS = [row for row in json.loads((REAL / 'manifest.json').read_text())['requests']
          if '/videos/' in row['url']]
EXCEPTIONS = Path(__file__).parent / 'fixtures/pulso_editorial_exception_real'
# All twenty original current-window videos without a factual text; the other
# /videos/ original supplies a 2,616-character transcript and is not held here.
CURRENT_UNAVAILABLE = [row for row in json.loads((EXCEPTIONS / 'manifest.json').read_text())['requests']
                       if '/videos/' in row['url'] and (row['primary_body_chars'] < 160
                       or row['primary_body_source'] != 'url_bound_json_ld_articleBody')]


def original_video_raw(entry, root=REAL):
    compressed = (root / entry['gzip_file']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == entry['gzip_sha256']
    payload = gzip.decompress(compressed)
    assert hashlib.sha256(payload).hexdigest() == entry['sha256']
    result = _verified_detail({'url': entry['url'], 'listing': 'https://www.latercera.com/canal/nacional/'},
                              lambda url: payload.decode('utf-8'), None)
    assert result['deferred_reason'] == 'publisher_video_text_unavailable'
    metadata = result['metadata']
    assert verified_video_without_text(metadata)
    assert metadata['html_sha256'] == entry['sha256']
    return RawItem('pulso_latercera', result['title'], entry['url'], 'Pulso / La Tercera',
                   'press_high_trust', metadata['publication_date'], result['body'], metadata)


@pytest.mark.parametrize('entry', CURRENT_UNAVAILABLE, ids=lambda row: row['url'].split('/')[-2])
def test_all_twenty_original_current_video_text_holds_spend_no_analysis(entry, monkeypatch):
    assert len(CURRENT_UNAVAILABLE) == 20
    raw = original_video_raw(entry, EXCEPTIONS)
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda *args: pytest.fail('No missing transcript retry'))
    monkeypatch.setattr(beta_sources, '_material', lambda *args: pytest.fail('No factual transcript to assess'))
    monkeypatch.setattr(llm_analysis, '_client', lambda: pytest.fail('No Responses call for unavailable text'))
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('No AI for unavailable text'))
    with pytest.raises(DeferredProcessing, match='^publisher_video_text_unavailable$'):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.metadata['article_body_complete'] is False
    assert raw.metadata['publication_date_verified'] is True
    assert raw.metadata['article_verified'] is False
    assert raw.metadata['editorial_assessment'] == {'decision': 'pending', 'reason': 'publisher_video_text_unavailable'}
    assert 'analysis_input_complete' not in raw.metadata


def test_original_alzheimer_84_characters_never_becomes_251_character_wrapper_transcript(monkeypatch):
    entry = next(row for row in CURRENT_UNAVAILABLE if 'descubren-doble-avance' in row['url'])
    payload = gzip.decompress((EXCEPTIONS / entry['gzip_file']).read_bytes())
    assert hashlib.sha256(payload).hexdigest() == entry['sha256']
    parser = _Article()
    parser.feed(payload.decode(entry['charset']))
    wrapper = ' '.join(parser.body or parser.paragraphs)
    assert len(wrapper) == 251 and 'Compartir Twitter' in wrapper and 'Más sobre:' in wrapper
    raw = original_video_raw(entry, EXCEPTIONS)
    assert raw.event_date == '2026-09-08'
    assert len(raw.metadata['page_text']) == entry['primary_body_chars'] == 84
    assert raw.metadata['page_text'] == entry['full_primary_body']
    assert raw.metadata['article_body_sha256'] == entry['primary_body_sha256']
    assert 'Compartir Twitter' not in raw.metadata['page_text']
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda *args: pytest.fail('No refetch can invent the missing text'))
    monkeypatch.setattr(llm_analysis, '_client', lambda: pytest.fail('No Responses call for wrapper text'))
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('No AI for wrapper text'))
    with pytest.raises(DeferredProcessing, match='^publisher_video_text_unavailable$'):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.metadata['article_body_complete'] is False
    assert 'analysis_input_complete' not in raw.metadata


def test_hash_consistent_legacy_alzheimer_wrapper_requires_original_and_exact_availability_hold(monkeypatch):
    # Reconstruct the old cache failure from exact original bytes; the wrapper
    # hash matches itself, but the original still supplies only84 factual chars.
    entry = next(row for row in CURRENT_UNAVAILABLE if 'descubren-doble-avance' in row['url'])
    compressed = (EXCEPTIONS / entry['gzip_file']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == entry['gzip_sha256']
    payload = gzip.decompress(compressed)
    assert hashlib.sha256(payload).hexdigest() == entry['sha256']
    html = payload.decode(entry['charset'])
    parser = _Article()
    parser.feed(html)
    wrapper = ' '.join(parser.body or parser.paragraphs)
    assert len(wrapper) == 251
    metadata = dict(canonical_url=entry['url'], publication_date='2026-09-08', section='Videos',
                    market_role='media', article_verified=True, article_body_complete=True,
                    body_source='url_bound_json_ld_articleBody', **article_body_evidence(wrapper))
    raw = RawItem('pulso_latercera', entry['title'], entry['url'], 'Pulso / La Tercera',
                   'press_high_trust', '2026-09-08', wrapper, metadata)
    calls = []
    def fetch(url):
        calls.append(url)
        return html
    monkeypatch.setattr(beta_sources, 'fetch_html', fetch)
    monkeypatch.setattr(beta_sources, '_material', lambda *args: pytest.fail('Wrapper must not be scored'))
    monkeypatch.setattr(llm_analysis, '_client', lambda: pytest.fail('Wrapper must not reach Responses'))
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('Wrapper must not reach AI'))
    with pytest.raises(DeferredProcessing, match='^publisher_video_text_unavailable$'):
        beta_sources.process_curated_beta_source(raw, {})
    assert calls == [entry['url']]
    assert raw.event_date == '2026-09-08'
    assert raw.metadata['page_text'] == entry['full_primary_body']
    assert len(raw.metadata['page_text']) == 84
    assert raw.metadata['article_body_sha256'] == entry['primary_body_sha256']
    assert raw.metadata['html_sha256'] == entry['sha256']
    assert raw.metadata['article_verified'] is False and raw.metadata['article_body_complete'] is False
    assert raw.metadata['editorial_assessment'] == {'decision': 'pending', 'reason': 'publisher_video_text_unavailable'}


@pytest.mark.parametrize('entry', VIDEOS, ids=lambda row: row['url'].split('/')[-2])
def test_every_real_thin_video_remains_exactly_pending_without_refetch_prefilter_or_ai(entry, monkeypatch):
    raw = original_video_raw(entry)
    raw.metadata.update(detected_at='2026-10-11T06:00:00Z', attempts=2, ingestion_mode='BACKFILL')
    before = deepcopy(raw.metadata)
    monkeypatch.setattr(beta_sources, 'fetch_html', lambda *args: pytest.fail('A missing transcript must not be refetched'))
    monkeypatch.setattr(beta_sources, '_material', lambda *args: pytest.fail('Unavailable text cannot reach materiality'))
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('Unavailable text cannot consume AI'))
    with pytest.raises(DeferredProcessing, match='^publisher_video_text_unavailable$'):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.event_date == entry['visible_byline_day']
    assert raw.metadata['canonical_url'] == entry['url']
    assert raw.metadata['article_body_complete'] is False
    assert raw.metadata['source_quality_gate'] == 'deferred_video_text'
    assert raw.metadata['editorial_assessment'] == {'decision': 'pending', 'reason': 'publisher_video_text_unavailable'}
    assert 'analysis_input_complete' not in raw.metadata
    for key in ('detected_at', 'attempts', 'ingestion_mode', 'video_evidence', 'publication_evidence', 'html_sha256'):
        assert raw.metadata[key] == before[key]


@pytest.mark.parametrize('tamper', ['video_identity', 'video_id', 'embed', 'raw_url', 'raw_date'])
def test_unbound_video_availability_flags_cannot_skip_original_verification(tamper, monkeypatch):
    raw = original_video_raw(VIDEOS[0])
    if tamper == 'video_identity':
        raw.metadata['video_identity_verified'] = False
    elif tamper == 'video_id':
        raw.metadata['video_evidence']['id'] = 'https://www.latercera.com/videos/noticia/other/#video'
    elif tamper == 'embed':
        raw.metadata['video_evidence']['embed_url'] = ''
    elif tamper == 'raw_url':
        raw.url = 'https://www.latercera.com/videos/noticia/other/'
    else:
        raw.event_date = '2026-10-01'
    calls = []
    def unavailable(url):
        calls.append(url)
        raise OSError('Original unavailable')
    monkeypatch.setattr(beta_sources, 'fetch_html', unavailable)
    monkeypatch.setattr(llm_analysis, 'analyze_news', lambda **kwargs: pytest.fail('Unverified source cannot consume AI'))
    with pytest.raises(DeferredProcessing, match='Pulso article verification failed'):
        beta_sources.process_curated_beta_source(raw, {})
    assert calls == [raw.url]
    assert raw.metadata['editorial_assessment']['reason'] == 'article_verification_failed'

