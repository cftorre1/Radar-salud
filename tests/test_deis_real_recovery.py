"""Replay of primary HTML captured by GitHub runtime 38114731188.

The full primary bytes and transport/hash manifest are durable audit evidence,
not reconstructed markup. Network behavior is exercised again in the Action.
"""
import hashlib
from pathlib import Path
import json

import pytest

from radar_salud.deis_sources import DeisDocumentScout, DeisCatalogScout
from radar_salud.public_source_transport import normalized_official_url
from radar_salud.public_source_evidence import verified_publication


CAPTURE = Path('data/audits/public_sources_c_20261011/recovery/runs/38114731188')


def captured(url):
    row = next(r for r in json.loads((CAPTURE / 'transport.json').read_text())['probes'] if r['url'] == url)
    body = (CAPTURE / row['body_path']).read_bytes()
    assert hashlib.sha256(body).hexdigest() == row['sha256']
    return body.decode('utf-8')


def test_primary_deis_notice_binds_june_release_to_requestable_pdf():
    items = DeisDocumentScout().discover_from_html(captured('https://deis.minsal.cl/centrofic/'))
    latest = items[0]
    assert latest.event_date == '2026-06-25'
    assert '/2021/03/' in latest.url
    assert '%20' in latest.url and '%C3%B3' in latest.url
    assert ' ' not in latest.url
    assert verified_publication(latest)
    assert len(items) == 12


def test_primary_deis_homepage_declares_all_public_catalogs_and_ajax_identity():
    surfaces = DeisCatalogScout.surfaces_from_html(captured('https://deis.minsal.cl/'))
    assert {r['title'] for r in surfaces} == set(DeisCatalogScout.PURPOSES)
    assert {r['table_id'] for r in surfaces} == {'2736', '2889', '2833', '2892', '3367'}
    assert all('target_action=get-all-data' in r['url'] for r in surfaces)


def test_spaces_and_unicode_are_encoded_once_without_changing_authority():
    raw = 'https://repositoriodeis.minsal.cl/docs/Capítulo XXI%20junio 2026.pdf'
    expected = 'https://repositoriodeis.minsal.cl/docs/Cap%C3%ADtulo%20XXI%20junio%202026.pdf'
    assert normalized_official_url(raw, 'deis') == expected
    assert normalized_official_url(expected, 'deis') == expected
    with pytest.raises(ValueError):
        normalized_official_url('https://repositoriodeis.minsal.cl.evil.org/docs/abc.pdf', 'deis')


def test_catalog_period_never_becomes_feed_date():
    surface = {'title': 'Datos Abiertos', 'purpose': 'trend_benchmark_dataset'}
    payload = [{'nombre': 'Egresos hospitalarios 2026', 'ver': 'https://repositoriodeis.minsal.cl/data.zip',
                'filtro_1': '2026', 'formato': 'zip', 'tags': 'egresos'}]
    resources = DeisCatalogScout.resources_from_json(payload, surface)
    assert resources[0]['publication_date'] is None
    assert resources[0]['feed_eligible'] is False
    assert resources[0]['purpose'] == 'trend_benchmark_dataset'
