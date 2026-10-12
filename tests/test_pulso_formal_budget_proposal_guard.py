"""A formal budget project is not implemented funding; original Oct5 body."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from radar_salud.pulso_editorial_proof import validate_pulso_editorial_proof, FORMAL_BUDGET_PROJECT, ACTUAL_BUDGET_LEGISLATIVE_STEP

ROOT=Path(__file__).resolve().parents[1]
PROOF_DOC=ROOT/'data/audits/pulso_all79_primary_independent_review_2026_10_11.json'
ORIGINAL=json.loads(PROOF_DOC.read_text())['all_controls'][5]
BODY=ORIGINAL['primary_body_full']
COUNTER_ANALYSIS={'relevance_score': 80, 'what_happened': 'Según La Tercera, el presupuesto de Salud para 2027 ya aumentó en 4,7% y los recursos están implementados y disponibles para ejecutar prestaciones.', 'why_it_matters': 'El incremento aprobado ya permite ampliar capacidad financiada en oncología, atención primaria y listas de espera.', 'reason': 'Afirmación adversarial de ejecución de recursos futuros, no respaldada por el proyecto citado.', 'pulso_editorial_proof': {'scope_decision': 'human_health_specific', 'scope_reason': 'Financiamiento del sistema de salud en el presupuesto propuesto para el siguiente ejercicio.', 'human_health_scope_quote': 'En esta línea, indicó que las prioridades del Ministerio de Salud para esta discusión son los tiempos de espera, así como oncología y APS.', 'actor': 'May Chomali', 'actor_quote': 'La ministra de Educación, May Chomali, abordó esta jornada el aumento de recursos contemplado para la cartera en el proyecto de Ley de Presupuestos 2027 presentado el Ejecutivo', 'action': 'un presupuesto aumentado en relación con el 2026 en un 4,7%', 'action_quote': 'Al respecto, la autoridad expresó en entrevista con Tele13 Radio que en el proyecto tienen “un presupuesto aumentado en relación con el 2026 en un 4,7%. Lo que es muy bueno considerando que hay una restricción fiscal general”.', 'consequence': 'los tiempos de espera', 'consequence_quote': 'En esta línea, indicó que las prioridades del Ministerio de Salud para esta discusión son los tiempos de espera, así como oncología y APS.', 'event_status': 'actual', 'event_status_quote': 'el aumento de recursos contemplado para la cartera en el proyecto de Ley de Presupuestos 2027 presentado el Ejecutivo', 'novelty_decision': 'new_material_information', 'novelty_reason': 'El anuncio presupuestario no permite inferir aprobación o financiamiento ejecutado.', 'novelty_quote': 'Al respecto, la autoridad expresó en entrevista con Tele13 Radio que en el proyecto tienen “un presupuesto aumentado en relación con el 2026 en un 4,7%. Lo que es muy bueno considerando que hay una restricción fiscal general”.', 'future_claims': []}}


def test_original_oct5_formal_budget_project_cannot_be_presented_as_implemented_funding():
    assert hashlib.sha256(BODY.encode()).hexdigest()=='0ebfaaf59515c5c7f01f4e150f7a9000e5f5a0888ecfaf48c73c9364378d0131'
    assert ORIGINAL['capture_sha256']=='60dd84e90cfdca2702312a13a90f669dbae10ed5de7dc2c71f76461d6115e807'
    result=validate_pulso_editorial_proof(COUNTER_ANALYSIS,BODY)
    assert result['decision']=='deferred'
    assert result['reason']=='pulso_editorial_future_status_mismatch'
    assert result['publication_approved'] is False


def test_original_budget_reference_cannot_evade_formal_context_by_shortening_status_quote():
    ai=deepcopy(COUNTER_ANALYSIS)
    ai['pulso_editorial_proof']['event_status_quote']=ai['pulso_editorial_proof']['action_quote']
    assert 'en el proyecto tienen' in ai['pulso_editorial_proof']['event_status_quote']
    result=validate_pulso_editorial_proof(ai,BODY)
    assert result['decision']=='deferred'
    assert result['reason']=='pulso_editorial_future_status_mismatch'

def test_same_original_proposed_budget_remains_eligible_with_complete_prospective_copy():
    ai=deepcopy(COUNTER_ANALYSIS);proof=ai['pulso_editorial_proof']
    proof['event_status']='proposal'
    ai['what_happened']='Según La Tercera, Chomali describió una propuesta de Presupuestos 2027 con alza de 4,7%; los recursos dependerán de la tramitación legislativa.'
    ai['why_it_matters']='De aprobarse, la propuesta podría modificar financiamiento de listas de espera, oncología y atención primaria; se informa una propuesta sin acreditación de ejecución.'
    proof['future_claims']=[{'summary_field':field,'summary_quote':ai[field],'source_quote':proof['event_status_quote']} for field in ('what_happened','why_it_matters')]
    result=validate_pulso_editorial_proof(ai,BODY)
    assert result['decision']=='ready'
    assert result['prospective_evidence'] is True
    assert result['publication_approved'] is False


def test_same_original_2026_operational_testimony_is_not_blanket_blocked_by_budget_elsewhere():
    ai=deepcopy(COUNTER_ANALYSIS);proof=ai['pulso_editorial_proof']
    procurement='En esta línea, destacó, han aumentado las compras centralizadas, la intermediación con Cenabast y las licitaciones versus las compras directas, y han disminuido el ausentismo.'
    production='En la evaluación del primer semestre llevábamos, digamos, tres meses nomás en el gobierno y teníamos al mismo gasto, más consultas, más cirugía, más procedimiento, más producción,'
    hospital='Y esto es porque definitivamente los hospitales han hecho el trabajo de hacer más eficiente el uso de los recursos en aquellas áreas que no tocan a los pacientes'
    for quote in (procurement,production,hospital):assert quote in BODY
    proof.update(event_status='actual',event_status_quote=procurement,
                 action='han aumentado las compras centralizadas',action_quote=procurement,
                 consequence='más consultas, más cirugía, más procedimiento, más producción',consequence_quote=production,
                 human_health_scope_quote=hospital,novelty_quote=procurement,future_claims=[])
    ai['what_happened']='Según La Tercera, Chomali afirmó que la evaluación del primer semestre de 2026 registró más producción hospitalaria al mismo gasto y describió cambios en compras y ausentismo.'
    ai['why_it_matters']='El relato aporta información sobre gestión de hospitales y compra centralizada; se conserva como testimonio de prensa y no como desempeño auditado.'
    result=validate_pulso_editorial_proof(ai,BODY)
    assert result['decision']=='ready'
    assert result['prospective_evidence'] is False
    assert result['publication_approved'] is False


def test_formal_language_detection_is_not_a_blanket_project_filter():
    assert FORMAL_BUDGET_PROJECT.search('proyecto de Ley de Presupuestos 2027 presentado')
    assert FORMAL_BUDGET_PROJECT.search('proyecto de presupuesto para 2027')
    assert not FORMAL_BUDGET_PROJECT.search('proyecto hospitalario terminado')
    assert ACTUAL_BUDGET_LEGISLATIVE_STEP.search('El Senado aprobó el proyecto de Ley de Presupuestos 2027')
    assert ACTUAL_BUDGET_LEGISLATIVE_STEP.search('El proyecto de Ley de Presupuestos 2027 fue aprobado por el Congreso')
    assert not ACTUAL_BUDGET_LEGISLATIVE_STEP.search('proyecto de Ley de Presupuestos 2027 presentado por el Ejecutivo')
