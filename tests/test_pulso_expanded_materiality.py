"""Exact new original controls reach unchanged editorial scoring with full body."""
import gzip
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.pulso_source import _verified_detail


REAL = Path(__file__).parent / 'fixtures/pulso_runtime_real'
CONTROLS = [row for row in json.loads((REAL / 'manifest.json').read_text())['fixtures']
            if any(part in row['url'] for part in ('minsal-publica-nomina-con-los-eleam',
                       'uc-christus-san-carlos-de-apoquindo-suspende-atencion-de-urgencia'))]
PROJECTIONS = json.loads((Path(__file__).parent / 'fixtures/pulso_expanded_materiality_real/verified_primary_body_projections.json').read_text())['fixtures']
REPAIRED_PROJECTIONS = ('proposed_clinical_condition_colmed', 'regional_health_power_interruption',
                        'modular_hospital_transport', 'mapped_multi_provider_flood_damage',
                        'proposed_reproductive_legislative_progress',
                        'medical_insurance_coverage_inquiry', 'provider_judicial_financial_liability')


def original_raw(entry):
    compressed = (REAL / entry['path']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == entry['gzip_sha256']
    payload = gzip.decompress(compressed)
    assert hashlib.sha256(payload).hexdigest() == entry['sha256']
    result = _verified_detail({'url': entry['url'], 'listing': 'captured-primary-original'},
                              lambda _: payload.decode('utf-8'), None)
    metadata = result['metadata']
    assert metadata['html_sha256'] == entry['sha256']
    assert metadata['article_verified'] and metadata['publication_date_verified']
    return RawItem('pulso_latercera', result['title'], entry['url'], 'Pulso / La Tercera',
                   'press_high_trust', metadata['publication_date'], result['body'], metadata)


@pytest.mark.parametrize('entry', CONTROLS, ids=lambda row: row['url'].split('/')[-2])
def test_both_original_omitted_controls_reach_full_body_analysis_and_still_reject_score71(entry, monkeypatch):
    assert len(CONTROLS) == 2
    raw = original_raw(entry)
    body = raw.metadata['page_text']
    assert beta_sources._material('media', raw.title, body)
    calls = []
    def assess(**kwargs):
        calls.append(kwargs)
        return dict(relevance_score=71, what_happened='', why_it_matters='',
                    reason='Contexto sin suficiente valor incremental para publicación.')
    monkeypatch.setattr(llm_analysis, 'analyze_news', assess)
    assert beta_sources.process_curated_beta_source(raw, {}) is None
    assert len(calls) == 1 and calls[0]['text'] == body and calls[0]['full_text']
    assert 'no convertir reporte de prensa en hecho oficial' in calls[0]['kind']
    assert raw.metadata['analysis_input_body_sha256'] == hashlib.sha256(body.encode()).hexdigest()
    assert raw.metadata['analysis_input_complete'] is True
    assert raw.metadata['editorial_assessment']['threshold'] == 72
    assert raw.metadata['rejection_reason'] == 'editorial_relevance_below_threshold'


def test_original_eleam_registry_is_a_reported_new_list_with_existing_authorization_requirements():
    raw = original_raw(next(row for row in CONTROLS if 'eleam' in row['url']))
    assert raw.event_date == '2026-09-16'
    assert len(raw.metadata['page_text']) == 1750
    assert raw.metadata['article_body_sha256'] == '42a8afb2862a45f8cd4cafce27bcb62cb6eafd350966a902e4fe4d937454d97f'
    assert 'desde hoy está disponible públicamente' in raw.metadata['page_text']
    assert 'al 14 de septiembre del 2026' in raw.metadata['page_text']
    assert 'Decreto 20' in raw.metadata['page_text']
    assert '993 ELEAM -públicos y privados-' in raw.metadata['page_text']
    assert 'la lista será actualizada semanalmente' in raw.metadata['page_text']


def test_original_uc_christus_is_a_reported_temporary_service_suspension_without_evacuation():
    raw = original_raw(next(row for row in CONTROLS if 'uc-christus' in row['url']))
    assert raw.event_date == '2026-10-08'
    assert len(raw.metadata['page_text']) == 1345
    assert raw.metadata['article_body_sha256'] == '38ffa83c8276fba1876f5dd50e5eaaabad9c852c0a76505ace9a61830f7e545f'
    assert 'hemos suspendido la atención del Servicio de Urgencia' in raw.metadata['page_text']
    assert 'durante hoy jueves 8 y mañana viernes 9 de octubre' in raw.metadata['page_text']
    assert 'no ha sido necesario realizar evacuaciones' in raw.metadata['page_text']


@pytest.mark.parametrize('entry', [row for row in PROJECTIONS if row['name'] in REPAIRED_PROJECTIONS],
                         ids=lambda row: row['name'])
def test_additional_sha_bound_primary_actions_reach_full_body_analysis_without_score_override(entry, monkeypatch):
    metadata = deepcopy(entry['metadata'])
    body = entry['body']
    assert hashlib.sha256(body.encode()).hexdigest() == metadata['article_body_sha256'] == entry['provenance']['body_sha256']
    assert metadata['html_sha256'] == entry['provenance']['html_sha256']
    assert metadata['canonical_url'] == entry['url'] and metadata['publication_date'] == entry['publication_date']
    assert metadata['article_verified'] and metadata['publication_date_verified']
    assert beta_sources._material('media', entry['title'], body)
    raw = RawItem('pulso_latercera', entry['title'], entry['url'], 'Pulso / La Tercera',
                   'press_high_trust', entry['publication_date'], body[:1800], metadata)
    calls = []
    def assess(**kwargs):
        calls.append(kwargs)
        return dict(relevance_score=71, what_happened='', why_it_matters='', reason='Incremento insuficiente sobre eventos previos.')
    monkeypatch.setattr(llm_analysis, 'analyze_news', assess)
    assert beta_sources.process_curated_beta_source(raw, {}) is None
    assert len(calls) == 1 and calls[0]['text'] == body and calls[0]['full_text']
    assert 'no convertir reporte de prensa en hecho oficial' in calls[0]['kind']
    assert raw.metadata['analysis_input_complete'] is True
    assert raw.metadata['analysis_input_body_sha256'] == metadata['article_body_sha256']
    assert raw.metadata['editorial_assessment']['threshold'] == 72
    assert raw.metadata['rejection_reason'] == 'editorial_relevance_below_threshold'


def test_original_colmed_is_a_reported_objection_to_a_proposed_clinical_condition():
    entry = next(row for row in PROJECTIONS if row['name'] == 'proposed_clinical_condition_colmed')
    assert entry['publication_date'] == '2026-07-15'
    assert 'el cual propone que los médicos ofrezcan escuchar la actividad cardíaca fetal' in entry['body']
    assert 'condicionando la realización del procedimiento a la aceptación de esa instancia' in entry['body']
    assert 'consentimiento informado' in entry['body']
    assert 'ha sido rechazado desde distintos sectores' in entry['body']


def test_original_power_impact_preserves_quantified_risk_and_equipment_still_operating():
    entry = next(row for row in PROJECTIONS if row['name'] == 'regional_health_power_interruption')
    assert entry['publication_date'] == '2026-07-17'
    assert '981 tendrían corte de suministro eléctrico' in entry['body']
    assert 'por el momento mantendrían sus equipos en operación' in entry['body']
    assert 'centros de salud, el total de los afectados son 92 de más de 1.800' in entry['body']


def test_original_nonmedical_school_headline_reports_transport_without_assuming_hospital_operational():
    entry = next(row for row in PROJECTIONS if row['name'] == 'modular_hospital_transport')
    assert entry['publication_date'] == '2026-07-19'
    assert 'Gobierno suspende clases' in entry['title']
    assert 'el traslado de un hospital modular proporcionado por el Ejército' in entry['body']
    assert 'ese transporte ya se encuentra en desarrollo' in entry['body']
    assert 'estaría llegando a la región para la implementación lo más rápido posible' in entry['body']
    assert 'apoyar la atención de salud en la comuna de Ovalle' in entry['body']


def test_original_mapped_flood_names_two_affected_clinics_without_asserting_their_service_status():
    entry = next(row for row in PROJECTIONS if row['name'] == 'mapped_multi_provider_flood_damage')
    assert entry['publication_date'] == '2026-10-08'
    assert 'dejando clínicas inundadas' in entry['body']
    assert 'Entre los recintos asistenciales afectados' in entry['body']
    assert 'la Clínica UC Christus San Carlos de Apoquindo y la Clínica Universidad de los Andes' in entry['body']
    assert 'a través de un monitoreo, a través de dron' in entry['body'].lower()
    assert 'Carabineros identificó' in entry['body']
    assert 'suspend' not in entry['body']


def test_original_reproductive_bill_is_discussion_started_with_no_adopted_government_position():
    entry = next(row for row in PROJECTIONS if row['name'] == 'proposed_reproductive_legislative_progress')
    assert entry['publication_date'] == '2026-08-13'
    assert 'comisión de Salud del Senado inició la discusión del proyecto de ley' in entry['body']
    assert 'busca regular la gestación subrogada' in entry['body']
    assert 'es algo que está en discusión' in entry['body']
    assert 'en 2025 la experta de la ONU' in entry['body']


def test_original_dipreca_inquiry_is_an_allegation_without_an_investigation_result():
    entry = next(row for row in PROJECTIONS if row['name'] == 'medical_insurance_coverage_inquiry')
    assert entry['publication_date'] == '2026-07-30'
    assert 'habrían sido cubiertas' in entry['body']
    assert 'investigación en curso' in entry['body']
    assert 'habrá que esperar el resultado' in entry['body']
    assert 'no me corresponde que yo me refiera a ello' in entry['body']


def test_original_court_award_is_new_liability_for_old_clinical_events():
    entry = next(row for row in PROJECTIONS if row['name'] == 'provider_judicial_financial_liability')
    assert entry['publication_date'] == '2026-09-02'
    assert 'a pagar un total de $380.000.000' in entry['body']
    assert '27 de julio 2020' in entry['body']
    assert 'peritaje médico legal de 2023' in entry['body']
    assert 'indemnización de perjuicios por falta de servicio' in entry['body']


@pytest.mark.parametrize(('title', 'body'), [
    ('Minsal informa sobre salud de personas mayores', 'Los ELEAM necesitan autorización sanitaria. Las familias visitan a sus parientes.'),
    ('Lista de residencias ELEAM', 'Un directorio comercial ofrece un listado de ELEAM con autorización sanitaria, disponible públicamente.'),
    ('Minsal recuerda una lista histórica', 'El viejo listado de ELEAM con autorización sanitaria sigue disponible en una biblioteca, sin nuevos cambios.'),
    ('La clínica informa sobre clases', 'El colegio suspendió la atención de clases; la clínica continúa funcionando.'),
    ('Una empresa suspende atención', 'La empresa de transportes suspende la atención de urgencia a clientes; no presta atención de salud.'),
    ('Un hospital estudia ideas', 'La administración evaluará si suspender la atención de urgencia el próximo año, sin medidas adoptadas.'),
    ('Minsal observa tormenta', 'Hay corte de suministro eléctrico en casas de personas electrodependientes, sin datos de centros asistenciales.'),
    ('Centros de salud informan situación', 'Los centros de salud afectados son 92, pero el artículo no menciona electricidad ni pacientes electrodependientes.'),
    ('Una comunidad observa su hospital', 'La comunidad menciona un hospital modular y una jornada de aprendizaje, sin ningún despliegue asistencial.'),
    ('Salud organiza clases', 'Se traslada una sala modular para apoyar las clases de salud; no es un recinto hospitalario.'),
    ('Carabineros monitorea lluvia cerca de clínicas', 'Carabineros realiza monitoreo por dron de viviendas dañadas, mientras las clínicas permanecen sin daño.'),
    ('Salud aborda inundaciones', 'Un estudio describe clínicas inundadas y recintos asistenciales afectados durante un temporal histórico, sin respuesta actual.'),
    ('Una ministra comenta gestación subrogada', 'La ministra ofrece su opinión sobre gestación subrogada y propone que la comisión de Salud converse el tema algún día.'),
    ('El Senado debate educación', 'La comisión de educación inició la discusión del proyecto de ley de escuelas. En una entrevista aparte, un médico comenta gestación subrogada.'),
    ('Dipreca ofrece información', 'Dipreca describe la cobertura de cirugías estéticas, sin una investigación ni procedimientos sancionatorios.'),
    ('Dipreca investiga robos', 'Existe un sumario en Dipreca por robo de computadores de oficinas administrativas.'),
    ('Hospital recuerda controversia', 'Un hospital y un servicio de salud comentan un asunto pendiente en la Corte de Apelaciones, sin resolución ni monto de indemnización.'),
])
def test_narrow_registry_and_care_suspension_rules_do_not_admit_generic_directory_or_unadopted_ideas(title, body):
    assert not beta_sources._material('media', title, body)
