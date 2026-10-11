"""Replay every retained exception original, validating immutable response bytes."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.pulso_source import (ConflictingPublicationArticle, TextUnavailableArticle,
                                    _verified_detail, extract_article,
                                    verified_publication_date_conflict, verified_video_without_text)

REAL = Path(__file__).parent / 'fixtures/pulso_editorial_exception_real'
MANIFEST = json.loads((REAL / 'manifest.json').read_text())
CONFLICTS = [row for row in MANIFEST['requests']
             if 'observed_primary_publication_date_conflict' in row['retention_categories']]
VIDEO_OBJECTS = [row for row in MANIFEST['requests']
                 if 'url_bound_primary_video_object' in row['retention_categories']]


def original(row):
    compressed = (REAL / row['gzip_file']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == row['gzip_sha256']
    payload = gzip.decompress(compressed)
    assert hashlib.sha256(payload).hexdigest() == row['sha256']
    assert len(payload) == row['bytes']
    return payload.decode(row['charset'])


def test_all_four_actual_date_conflicts_and_all_forty_four_video_objects_are_retained():
    assert len(CONFLICTS) == 4 and len(VIDEO_OBJECTS) == 44
    assert sum('/videos/' in row['url'] for row in VIDEO_OBJECTS) == 21


@pytest.mark.parametrize('row', CONFLICTS, ids=lambda row: row['url'].split('/')[-2])
def test_every_actual_publisher_date_conflict_stays_unresolved_with_complete_primary_body(row):
    html = original(row)
    with pytest.raises(ConflictingPublicationArticle, match='^conflicting_publication_dates$') as raised:
        extract_article(html, row['url'])
    metadata = raised.value.metadata
    assert metadata['publication_date'] is metadata['publication_timestamp'] is None
    assert metadata['visible_publication_date'] == row['visible_byline_day']
    assert metadata['primary_identity_verified'] and not metadata['publication_date_verified']
    assert metadata['canonical_url'] == row['canonical'] == row['url']
    assert hashlib.sha256(raised.value.body.encode()).hexdigest() == row['primary_body_sha256']
    assert len(raised.value.body) == row['primary_body_chars'] >= 160
    result = _verified_detail(dict(url=row['url'], listing='retained-original', lastmod='actual-original'),
                              lambda _: html, None)
    assert verified_publication_date_conflict(result['metadata'])
    assert result['deferred_reason'] == 'publisher_conflicting_publication_dates'
    assert result['metadata']['html_sha256'] == row['sha256']
    assert [entry['timestamp'] for entry in result['metadata']['publication_evidence']] == [
        entry['timestamp'] for entry in row['publication_evidence']]


@pytest.mark.parametrize('row', VIDEO_OBJECTS, ids=lambda row: row['url'].split('/')[-2])
def test_every_original_video_object_distinguishes_embedded_video_from_missing_transcript(row):
    html = original(row)
    result = _verified_detail(dict(url=row['url'], listing='retained-original'), lambda _: html, None)
    assert 'status' not in result
    metadata = result['metadata']
    assert metadata['canonical_url'] == row['url'] and metadata['html_sha256'] == row['sha256']
    if row['visible_byline_day']:
        assert metadata['publication_date'] == row['visible_byline_day']
    else:
        # The retained live blog has no visible time byline or bound Article
        # node; canonical-page publication metadata dates its primary HTML.
        assert row['sha256'] == '561db69a4bbe9aed501ebd64167d98251fa396ec54e303b7ec301687b779a96c'
        assert metadata['publication_date'] == '2026-07-21'
        assert metadata['publication_date_source'] == 'article_published_time'
    substantive_video = '/aluvion-' in row['url']
    if '/videos/' in row['url'] and not substantive_video:
        assert result['deferred_reason'] == 'publisher_video_text_unavailable'
        assert verified_video_without_text(metadata)
        assert not metadata['article_verified'] and not metadata['article_body_complete']
        assert len(metadata['page_text']) < 160
    else:
        assert not result.get('deferred_reason')
        assert metadata['article_verified'] and len(metadata['page_text']) >= 160


def test_actual_alzheimer_original_does_not_upgrade_eighty_four_characters_with_metadata_wrapper():
    row = next(row for row in VIDEO_OBJECTS if row['sha256'] ==
               '6c310d175c41f476e2d54622122d63e370f5c916c4b8408587dccb2952082967')
    assert row['primary_body_chars'] == 84
    with pytest.raises(TextUnavailableArticle) as raised:
        extract_article(original(row), row['url'])
    assert len(raised.value.body) == 84
    assert hashlib.sha256(raised.value.body.encode()).hexdigest() == row['primary_body_sha256']
    assert raised.value.metadata['article_body_complete'] is False
    assert raised.value.metadata['body_source'] == 'url_bound_json_ld_articleBody'
