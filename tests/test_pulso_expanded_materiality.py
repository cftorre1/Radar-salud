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
from pulso_editorial_test_support import valid_assessment
from pulso_editorial_real_test_witnesses import real_witness


REAL = Path(__file__).parent / 'fixtures/pulso_runtime_real'
CONTROLS = [row for row in json.loads((REAL / 'manifest.json').read_text())['fixtures']
            if any(part in row['url'] for part in ('minsal-publica-nomina-con-los-eleam',
                       'uc-christus-san-carlos-de-apoquindo-suspende-atencion-de-urgencia'))]
PROJECTIONS = json.loads((Path(__file__).parent / 'fixtures/pulso_expanded_materiality_real/verified_primary_body_projections.json').read_text())['fixtures']
REPAIRED_PROJECTIONS = ('proposed_clinical_condition_colmed', 'regional_health_power_interruption',
                        'modular_hospital_transport', 'mapped_multi_provider_flood_damage',
                        'proposed_reproductive_legislative_progress',
                        'medical_insurance_coverage_inquiry', 'provider_judicial_financial_liability',
                        'blocked_essential_dialysis_access', 'reported_compulsory_respiratory_measure',
                        'damaged_hospital_emergency_funds', 'proposed_minors_mental_health_legislative_urgency',
                        'reported_national_health_cost_access_measurement', 'territorial_toxic_exposure_health_order',
                        'institutional_food_health_investigation')


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
        return valid_assessment(dict(relevance_score=71, what_happened='', why_it_matters='',
                    reason='Contexto sin suficiente valor incremental para publicación.'),
                    kwargs, witness=real_witness(kwargs))
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
        return valid_assessment(dict(relevance_score=71, what_happened='', why_it_matters='',
                    reason='Incremento insuficiente sobre eventos previos.'),
                    kwargs, witness=real_witness(kwargs))
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


def test_original_isolation_blocked_clinical_access_without_counting_all_isolated_as_patients():
    entry = next(row for row in PROJECTIONS if row['name'] == 'blocked_essential_dialysis_access')
    assert entry['publication_date'] == '2026-07-25'
    assert 'seremi de Cultura de Atacama' in entry['body']
    assert 'unas 3.500 personas aisladas' in entry['body']
    assert 'necesitaban dializarse' in entry['body']
    assert 'no permitía que los helicópteros pudiesen volar para evacuarlos' in entry['body']
    assert 'recién nacido a un consultorio por complicaciones de salud' in entry['body']
    assert 'El resto de los 51 que fueron rescatados tuvo que hacerlo por tierra' in entry['body']


def test_original_compulsory_mask_measure_is_reported_provincial_resolution_with_respiratory_purpose():
    entry = next(row for row in PROJECTIONS if row['name'] == 'reported_compulsory_respiratory_measure')
    assert entry['publication_date'] == '2026-08-22'
    assert 'uso obligatorio de mascarilla a partir de este sábado 22 de agosto' in entry['body']
    assert 'Resolución Exenta N°2' in entry['body']
    assert 'Autoridad Sanitaria' in entry['body']
    assert 'prevenir eventuales complicaciones y enfermedades respiratorias' in entry['body']


def test_original_emergency_funds_do_not_assert_a_specific_health_allocation():
    entry = next(row for row in PROJECTIONS if row['name'] == 'damaged_hospital_emergency_funds')
    assert entry['publication_date'] == '2026-08-22'
    assert 'Ley N° 16.282 para liberar fondos de emergencia' in entry['body']
    assert 'su publicación en el Diario Oficial' in entry['body']
    assert 'hospitales con daños en la infraestructura' in entry['body']
    assert 'monto' not in entry['body']


def test_original_minors_mental_health_progress_is_proposed_with_an_older_plan_as_context():
    entry = next(row for row in PROJECTIONS if row['name'] == 'proposed_minors_mental_health_legislative_urgency')
    assert entry['publication_date'] == '2026-08-26'
    assert 'sumo urgencia al proyecto de ley' in entry['body']
    assert 'primer trámite constitucional' in entry['body']
    assert 'presentaremos indicaciones' in entry['body']
    assert 'lanzado el 25 de mayo' in entry['body']
    assert 'salud mental de menores de edad' in entry['body']


def test_original_national_cost_survey_preserves_age_scope_and_reported_access_barrier():
    entry = next(row for row in PROJECTIONS if row['name'] == 'reported_national_health_cost_access_measurement')
    assert entry['publication_date'] == '2026-07-24'
    assert 'personas de 50 años o más en Chile' in entry['body']
    assert '700 casos a nivel nacional representativos' in entry['body']
    assert 'gastos de salud y cuidados' in entry['body']
    assert 'principal barrera de acceso es el costo (53%)' in entry['body']
    assert 'Caja Los Andes desarrolló Cincuentímeter' in entry['body']


def test_original_toxic_exposure_order_is_local_public_health_protection_without_clinical_capacity_claim():
    entry = next(row for row in PROJECTIONS if row['name'] == 'territorial_toxic_exposure_health_order')
    assert entry['publication_date'] == '2026-08-05'
    assert 'un análisis realizado por la Seremi de Salud' in entry['body']
    assert 'la toxicidad del humo' in entry['body']
    assert 'A todos los colegios de la comuna de Quilicura' in entry['body']
    assert 'incluye tanto a establecimientos públicos como privados' in entry['body']
    assert 'hospital' not in entry['body'].lower()


def test_original_food_health_inquiry_preserves_allegations_and_political_defense_context():
    entry = next(row for row in PROJECTIONS if row['name'] == 'institutional_food_health_investigation')
    assert entry['publication_date'] == '2026-08-21'
    assert 'delitos contra la salud pública' in entry['body']
    assert 'distribución de comida contaminada' in entry['body']
    assert 'habrían existido irregularidades' in entry['body']
    assert 'orden de entrada, registro e incautación' in entry['body']
    assert 'afectaría derechos fundamentales del senador' in entry['body']


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
    ('Vecinos informan aislamiento', 'Varias personas quedaron aisladas por nieve. Cerca de allí hay un centro de diálisis, pero mantiene la atención habitual.'),
    ('Pacientes hablan del invierno', 'Los pacientes necesitaban dializarse, por lo que acudieron al hospital sin impedimentos de acceso.'),
    ('Escuela exige vestimenta', 'Una escuela recomienda uso obligatorio de mascarilla para un ensayo teatral, sin orden sanitaria.'),
    ('Salud entrega consejos respiratorios', 'La Autoridad Sanitaria recomienda mascarilla para prevenir enfermedades respiratorias, sin resolución obligatoria.'),
    ('Gobierno atiende viviendas', 'La Ley N° 16.282 libera fondos de emergencia tras publicación en el Diario Oficial para reparar viviendas. Los hospitales siguen intactos.'),
    ('Ministra comenta salud mental', 'La ministra quiere conversar sobre salud mental de niños y propone colaborar en un futuro diálogo, sin avance parlamentario concreto.'),
    ('Vecinos comentan sus gastos', 'Una encuesta informal del barrio comenta gastos de salud y cuidados y una barrera de acceso es el costo, sin medición nacional representativa.'),
    ('Comuna suspende clases', 'La suspensión de clases en todos los colegios de la comuna obedece a mantención de edificios. La Seremi de Salud difundió un recordatorio separado.'),
    ('Escuela difunde estudio de humo', 'La Seremi de Salud estudia la toxicidad del humo en un colegio, sin ordenar suspensión de clases territorial.'),
    ('Fiscal investiga defensa política', 'La fiscal pidió incautación de documentos de Junaeb por pagos administrativos, sin acusaciones de daño sanitario.'),
])
def test_narrow_registry_and_care_suspension_rules_do_not_admit_generic_directory_or_unadopted_ideas(title, body):
    assert not beta_sources._material('media', title, body)
