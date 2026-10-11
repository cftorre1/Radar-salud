"""Immutable cold witnesses remain required when retained originals expand.

Recapture may change a page's HTML and gzip hash. Its primary body, publisher
byline and observed taxonomy remain checked against every original cold case.
The old byte hashes separately bind the independent historical audit.
"""
import json
from pathlib import Path


WITNESS_PATH = Path(__file__).parent / 'fixtures/pulso_editorial_exception_real/cold_witnesses_2026_10_11.json'
WITNESSES = json.loads(WITNESS_PATH.read_text())
COLD_RECORDS = {row['url']: row for row in WITNESSES['requests']}


def assert_cold_witnesses(records):
    current = {row['url']: row for row in records}
    assert len(current) == len(records), 'Retained originals must have unique canonical URLs'
    assert set(COLD_RECORDS).issubset(current), 'A cold original witness disappeared'
    for url, cold in COLD_RECORDS.items():
        for key in ('primary_body_sha256', 'primary_body_chars', 'visible_byline_day'):
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
