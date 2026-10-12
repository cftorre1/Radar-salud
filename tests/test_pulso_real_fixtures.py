"""Regression evidence captured by permitted Actions, with immutable byte hashes."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud.pulso_source import _Article, extract_article

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'tests/fixtures/pulso_real/manifest.json').read_text())


@pytest.mark.parametrize('entry', [x for x in MANIFEST['fixtures'] if '/noticia/' in x['url']])
def test_original_publisher_story_identity_date_and_primary_body(entry):
    payload = gzip.decompress((ROOT / entry['path']).read_bytes())
    assert hashlib.sha256(payload).hexdigest() == entry['sha256']
    html = payload.decode('utf-8')
    title, body, metadata = extract_article(html, entry['url'])
    assert metadata['canonical_url'] == entry['url']
    assert metadata['publication_date'] == '2026-10-10'
    assert metadata['body_source'] == 'url_bound_json_ld_articleBody'
    parser = _Article(); parser.feed(html)
    primary = next(json.loads(script) for script in parser.scripts if json.loads(script).get('@type') == 'NewsArticle')
    assert body == ' '.join(primary['articleBody'].split())
    assert title == primary['headline']
    assert 'Más sobre:' not in body
    if 'senior-housing' in entry['url']:
        assert 'Acalis' in body and 'Villa Soleares' in body
        assert '(FILES)' not in body
    else:
        assert 'jueves 8 de octubre' in body
        assert 'trasladar a todos los pacientes' in body
