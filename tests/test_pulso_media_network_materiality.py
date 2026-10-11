"""Real primary reports missed by the media prefilter, without score overrides.

The fixtures are explicitly SHA-bound projections of complete bodies retained
by the real core run, not fabricated publisher HTML. Original raw gzip bytes
are preserved in the associated Actions artifact for independent revalidation.
"""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.pulso_source import complete_article_body


FIXTURE = Path(__file__).parent / 'fixtures/pulso_materiality_real/verified_primary_body_projections.json'
REAL = json.loads(FIXTURE.read_text())['fixtures']


@pytest.mark.parametrize('entry', REAL, ids=lambda entry: entry['name'])
def test_original_network_report_reaches_analysis_with_full_primary_evidence_and_unchanged_gate(entry, monkeypatch):
    body, metadata = entry['body'], deepcopy(entry['metadata'])
    assert hashlib.sha256(body.encode()).hexdigest() == metadata['article_body_sha256']
    assert metadata['canonical_url'] == entry['url']
    assert metadata['publication_date'] == entry['publication_date']
    assert complete_article_body(metadata)
    assert entry['original_http_capture']['status'] == 200
    assert entry['original_http_capture']['url'] == entry['url']
    assert entry['original_http_capture']['sha256'] == metadata['html_sha256']
    assert beta_sources._material('media', entry['title'], body)
    calls = []
    def assess(**kwargs):
        calls.append(kwargs)
        return dict(relevance_score=71, what_happened='', why_it_matters='',
                    reason='No agrega un cambio incremental sobre antecedentes previos.')
    monkeypatch.setattr(llm_analysis, 'analyze_news', assess)
    raw = RawItem('pulso_latercera', entry['title'], entry['url'], 'Pulso / La Tercera',
                  'press_high_trust', entry['publication_date'], body[:1800], metadata)
    assert beta_sources.process_curated_beta_source(raw, {}) is None
    assert len(calls) == 1 and calls[0]['text'] == body and calls[0]['full_text']
    assert 'no convertir reporte de prensa en hecho oficial' in calls[0]['kind']
    assert raw.metadata['editorial_assessment']['threshold'] == 72
    assert raw.metadata['rejection_reason'] == 'editorial_relevance_below_threshold'


def test_original_ges_announcement_preserves_its_historical_period_for_editorial_review():
    entry = next(row for row in REAL if row['name'] == 'ges_coverage')
    assert entry['publication_date'] == '2026-09-16'
    assert 'cuenta pública del Ministerio de Salud en julio' in entry['body']
    assert 'se incorporarán a las Garantías Explícitas de Salud (GES)' in entry['body']
    assert 'esta patología no es GES' in entry['body']


@pytest.mark.parametrize(('title', 'body'), [
    ('Ministerio de Salud presenta una guía de bienestar', 'La salud mejora con hábitos de descanso y una alimentación equilibrada.'),
    ('Salud recomienda usar mascarilla', 'El Ministerio de Salud recomienda usar mascarilla al visitar los servicios de urgencia.'),
    ('Salud: uso obligatorio de casco', 'El uso obligatorio de casco para bicicletas busca mejorar la salud en las rutas urbanas.'),
    ('Salud y gestiones culturales', 'El anuncio incorpora nuevas gestiones en una actividad de bienestar sin cambio asistencial.'),
    ('Salud celebra una actividad comunitaria', 'La comunidad recuerda las Garantías Explícitas de Salud sin cambios anunciados ni barreras actuales.'),
])
def test_narrow_network_matches_do_not_admit_advice_or_substring_noise(title, body):
    assert not beta_sources._material('media', title, body)


def test_new_media_network_terms_do_not_expand_other_source_roles():
    title = 'Salud extiende el uso obligatorio de mascarillas'
    body = 'El uso obligatorio de mascarillas continúa en los servicios de urgencia de la red pública y privada.'
    assert beta_sources._material('media', title, body)
    assert not beta_sources._material('provider', title, body)
    assert not beta_sources._material('mutuality', title, body)
