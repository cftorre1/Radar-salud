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
from radar_salud.pulso_source import _verified_detail, verified_video_without_text


REAL = Path(__file__).parent / 'fixtures/pulso_thin_primary_real'
VIDEOS = [row for row in json.loads((REAL / 'manifest.json').read_text())['requests']
          if '/videos/' in row['url']]


def original_video_raw(entry):
    compressed = (REAL / entry['gzip_file']).read_bytes()
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

