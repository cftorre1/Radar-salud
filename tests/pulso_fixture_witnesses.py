"""Immutable cold witnesses remain required when retained originals expand.

Recapture may change a page's HTML and gzip hash. Its primary body, publisher
byline and observed taxonomy remain checked against every original cold case.
The old byte hashes separately bind the independent historical audit.
"""
import json
import gzip
import hashlib
from pathlib import Path


WITNESS_PATH = Path(__file__).parent / 'fixtures/pulso_editorial_exception_real/cold_witnesses_2026_10_11.json'
WITNESSES = json.loads(WITNESS_PATH.read_text())
COLD_RECORDS = {row['url']: row for row in WITNESSES['requests']}


def _assert_original_video_wrapper_was_reclassified_as_missing_primary(record, cold):
    """Verify an old wrapper observation without calling it a transcript."""
    from radar_salud.pulso_source import _Article, _nodes, article_url
    assert '/videos/noticia/' in cold['url']
    assert cold['primary_body_source'] == 'article_html'
    assert record['primary_body_source'] == 'primary_text_missing_in_original'
    assert record['primary_body_chars'] == 0
    assert record['primary_body_sha256'] == hashlib.sha256(b'').hexdigest()
    assert record['sha256'] == cold['sha256'] and record['gzip_sha256'] == cold['gzip_sha256']
    compressed = (WITNESS_PATH.parent / record['gzip_file']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == cold['gzip_sha256']
    raw = gzip.decompress(compressed)
    assert hashlib.sha256(raw).hexdigest() == cold['sha256'] and len(raw) == cold['bytes']
    parser = _Article()
    parser.feed(raw.decode(cold['charset']))
    assert article_url(parser.canonical) == cold['url']
    nodes = [node for script in parser.scripts for node in _nodes(json.loads(script))
             if article_url(node.get('url') or node.get('@id')) == cold['url']]
    articles = [node for node in nodes if node.get('@type') in ('NewsArticle', 'Article', 'ReportageNewsArticle')]
    videos = [node for node in nodes if node.get('@type') == 'VideoObject']
    assert len(articles) == len(videos) == 1
    assert not articles[0].get('articleBody') and not parser.body_paragraphs and not parser.paragraphs
    assert videos[0].get('@id') == cold['url']+'#video' and videos[0].get('embedUrl')
    historic_wrapper = ' '.join(parser.body or parser.paragraphs)
    assert len(historic_wrapper) == cold['primary_body_chars']
    assert hashlib.sha256(historic_wrapper.encode()).hexdigest() == cold['primary_body_sha256']


def assert_cold_witnesses(records):
    current = {row['url']: row for row in records}
    assert len(current) == len(records), 'Retained originals must have unique canonical URLs'
    assert set(COLD_RECORDS).issubset(current), 'A cold original witness disappeared'
    for url, cold in COLD_RECORDS.items():
        assert current[url]['visible_byline_day'] == cold['visible_byline_day'], (url, 'visible_byline_day')
        if any(current[url][key] != cold[key] for key in ('primary_body_sha256', 'primary_body_chars')):
            _assert_original_video_wrapper_was_reclassified_as_missing_primary(current[url], cold)
        else:
            for key in ('primary_body_sha256', 'primary_body_chars'):
                assert current[url][key] == cold[key], (url, key)
        assert set(current[url]['retention_categories']).issuperset(cold['retention_categories']), url


def cold_urls(category):
    return {url for url, row in COLD_RECORDS.items() if category in row['retention_categories']}


def expected_original_hold_urls(records):
    """Independent original structure, including wrappers longer than160.

The fixtures expose the primary articleBody source separately from the HTML
wrapper. A publisher /videos/ wrapper is not a factual transcript.
"""
    return {row['url'] for row in records
            if 'observed_primary_publication_date_conflict' in row['retention_categories']
            or 'explicit_commercial_publisher_section' in row['retention_categories']
            or ('/videos/' in row['url']
                and (row['primary_body_chars'] < 160
                     or row['primary_body_source'] != 'url_bound_json_ld_articleBody'))}
