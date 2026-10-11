"""Every cold thin detail replays exact original bytes, never a title sample."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.pulso_source import _verified_detail, extract_article

REAL = Path(__file__).parent / 'fixtures/pulso_thin_primary_real'
MANIFEST = json.loads((REAL / 'manifest.json').read_text())
SHORT_HEADLINES = [row for row in MANIFEST['requests'] if row['title_below_18']]


def original(row):
    raw = gzip.decompress((REAL / row['gzip_file']).read_bytes())
    assert hashlib.sha256(raw).hexdigest() == row['sha256']
    return raw.decode(row['charset'])


def test_all_thirteen_short_primary_headlines_are_covered():
    assert len(SHORT_HEADLINES) == 13
    assert all(row['url_bound_article_nodes'] == 1 and row['body_complete_as_original']
               and not row['primary_body_below_160'] for row in SHORT_HEADLINES)


@pytest.mark.parametrize('row', SHORT_HEADLINES, ids=lambda row: row['url'].split('/')[-2])
def test_legitimate_short_headline_retains_complete_original_body_and_date(row):
    title, body, metadata = extract_article(original(row), row['url'])
    assert title == row['title'].strip()
    assert 0 < len(title) < 18 and len(body) >= 160
    assert body == row['full_primary_body']
    assert hashlib.sha256(body.encode()).hexdigest() == row['primary_body_sha256']
    assert metadata['publication_date'] == row['visible_byline_day']
    assert metadata['canonical_url'] == row['url']


def test_short_health_headline_opens_full_detail_and_cannot_be_false_negative():
    row = next(row for row in SHORT_HEADLINES if '/vivir-con-toc/' in row['url'])
    result = _verified_detail(dict(url=row['url'], listing='official-primary', lastmod='real-token'),
                              lambda _: original(row), None)
    assert result['relevant'] is True
    assert result['metadata']['page_text'] == row['full_primary_body']
    assert result['metadata']['article_body_characters'] == 8690
    assert 'status' not in result
