"""Real primary reports missed by the media prefilter, without score overrides.

The fixtures are explicitly SHA-bound projections of complete bodies retained
by the real core run, not fabricated publisher HTML. Original raw gzip bytes
are preserved in the associated Actions artifact for independent revalidation.
"""
import gzip
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.pulso_source import complete_article_body, extract_article
from pulso_editorial_test_support import valid_assessment
from pulso_editorial_real_test_witnesses import real_witness


FIXTURE = Path(__file__).parent / 'fixtures/pulso_materiality_real/verified_primary_body_projections.json'
REAL = json.loads(FIXTURE.read_text())['fixtures']


def test_mask_obligation_projection_matches_independently_recaptured_original_html():
    entry = next(row for row in REAL if row['name'] == 'care_obligation')
    originals = Path(__file__).parent / 'fixtures/pulso_runtime_real'
    record = next(row for row in json.loads((originals / 'manifest.json').read_text())['fixtures']
                  if row['url'] == entry['url'])
    compressed = (originals / record['path']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == record['gzip_sha256']
    payload = gzip.decompress(compressed)
    assert hashlib.sha256(payload).hexdigest() == record['sha256']
    title, body, metadata = extract_article(payload.decode('utf-8'), entry['url'])
    assert title == entry['title'] and body == entry['body']
    assert hashlib.sha256(body.encode()).hexdigest() == entry['metadata']['article_body_sha256']
    assert metadata['publication_date'] == entry['publication_date'] == '2026-09-01'
    assert beta_sources._material('media', title, body)


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
    assert metadata['publication_date_source'] == 'visible_article_byline'
    assert metadata['visible_publication_date'] == entry['publication_date']
    # These older body projections omitted the verifier's explicit flags. The
    # unit supplies the verified contract after checking their captured URL,
    # day and full-body binding; it makes no new live-verification claim.
    metadata.update(primary_identity_verified=True, publication_date_verified=True)
    assert beta_sources._material('media', entry['title'], body)
    calls = []
    def assess(**kwargs):
        calls.append(kwargs)
        return valid_assessment(dict(relevance_score=71, what_happened='', why_it_matters='',
                    reason='No agrega un cambio incremental sobre antecedentes previos.'),
                    kwargs, witness=real_witness(kwargs))
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


def test_original_clinical_legislation_remains_a_proposal_with_its_actual_dates():
    entry = next(row for row in REAL if row['name'] == 'care_legislation')
    assert entry['publication_date'] == '2026-07-26'
    assert 'Fue presentado el 7 de julio' in entry['body']
    assert 'se encuentra en tramitación en la Comisión de Salud' in entry['body']
    assert 'el Gobierno aún no adopta una postura definitiva' in entry['body']
    assert 'La iniciativa busca modificar el artículo 119 del Código Sanitario' in entry['body']
    assert 'si la paciente declina escucharla, el profesional deberá negarse a practicar la interrupción' in entry['body']


def test_all_101_independently_reviewed_complete_rejects_keep_frozen_eligibility_after_narrow_repairs():
    cases = json.loads((FIXTURE.parent / 'all_101_semantic_prefilter_cases.json').read_text())['cases']
    assert len(cases) == len({entry['url'] for entry in cases}) == 101
    assert sum(entry['allows_analysis_after_repair'] for entry in cases) == 3
    for entry in cases:
        assert entry['original_bytes_verified'] is True
        assert hashlib.sha256(entry['body'].encode()).hexdigest() == entry['body_sha256']
        assert beta_sources._material('media', entry['title'], entry['body']) == entry['allows_analysis_after_repair'], entry['url']


@pytest.mark.parametrize(('title', 'body'), [
    ('Salud debate una propuesta sobre latidos', 'El proyecto Escucha su corazón genera discusión sobre el aborto, sin especificar una condición de atención.'),
    ('Salud informa un aluvión', 'El Ministerio de Salud monitorea las lluvias. Una vivienda resultó inundada, mientras la clínica no sufrió daños.'),
    ('Clínica resulta inundada', 'La clínica resultó inundada producto del temporal; no se informa respuesta de ninguna autoridad sanitaria.'),
])
def test_clinical_conditions_and_provider_damage_need_concrete_publisher_context(title, body):
    assert not beta_sources._material('media', title, body)


@pytest.mark.parametrize(('title', 'body'), [
    ('Ministerio de Salud presenta una guía de bienestar', 'La salud mejora con hábitos de descanso y una alimentación equilibrada.'),
    ('Salud recomienda usar mascarilla', 'El Ministerio de Salud recomienda usar mascarilla al visitar los servicios de urgencia.'),
    ('Salud: uso obligatorio de casco', 'El uso obligatorio de casco para bicicletas busca mejorar la salud en las rutas urbanas.'),
    ('Salud y gestiones culturales', 'El anuncio incorpora nuevas gestiones en una actividad de bienestar sin cambio asistencial.'),
    ('Salud celebra una actividad comunitaria', 'La comunidad recuerda las Garantías Explícitas de Salud sin cambios anunciados ni barreras actuales.'),
    ('Salud ofrece una charla histórica', 'La charla explica el Código Sanitario y el acceso a una prestación que ya existe.'),
    ('Salud debate un proyecto de administración de edificios', 'El proyecto modifica el Código Sanitario en materias de administración de edificios.'),
])
def test_narrow_network_matches_do_not_admit_advice_or_substring_noise(title, body):
    assert not beta_sources._material('media', title, body)


def test_new_media_network_terms_do_not_expand_other_source_roles():
    title = 'Salud extiende el uso obligatorio de mascarillas'
    body = 'El uso obligatorio de mascarillas continúa en los servicios de urgencia de la red pública y privada.'
    assert beta_sources._material('media', title, body)
    assert not beta_sources._material('provider', title, body)
    assert not beta_sources._material('mutuality', title, body)
