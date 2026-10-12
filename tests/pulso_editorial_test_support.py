"""Literal, request-bound editorial witnesses for unit-test assessments only.

These witnesses describe the existing fixtures; they do not approve publication,
change a relevance score, or stand in for an actual model response. An unfamiliar
fixture fails closed instead of borrowing quotes from another article.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import unicodedata

from radar_salud.llm_analysis import news_analysis_input
from radar_salud.pulso_editorial_proof import VERSION, validate_pulso_editorial_proof


def _normalized(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def _literal(body, text):
    quote = _normalized(text)
    assert quote in body, "Editorial unit witness must quote this complete request"
    return quote


def _between(body, beginning, ending):
    start = body.index(beginning)
    end = body.index(ending, start) + len(ending)
    return body[start:end]


def _witness(body):
    """Select an explicit actor, action and consequence from known fixtures."""
    if "La clínica suspendió operaciones y trasladó sus pacientes" in body:
        quote = _literal(body, "La clínica suspendió operaciones y trasladó sus pacientes "
                         "a otros establecimientos de su red asistencial.")
        consequence = _literal(body, "El cierre temporal reduce capacidad y obliga a redistribuir "
                               "consultas, procedimientos y prestaciones para asegurar continuidad.")
        return dict(actor="La clínica", action="suspendió operaciones y trasladó sus pacientes",
                    consequence="reduce capacidad y obliga a redistribuir consultas", quote=quote,
                    consequence_quote=consequence, status="actual")
    if "El hospital anuncia un recorte de presupuesto" in body:
        quote = _literal(body, "El hospital anuncia un recorte de presupuesto que reduce capacidad "
                         "de sus pabellones y prestaciones.")
        # The event is an announcement, not a claim that a future plan is implemented.
        return dict(actor="El hospital", action="anuncia un recorte de presupuesto",
                    consequence="reduce capacidad de sus pabellones y prestaciones", quote=quote,
                    consequence_quote=quote, status="actual")
    if "La propuesta de Presupuesto 2027 considera APS y Ley Ricarte Soto" in body:
        quote = _literal(body, "La propuesta de Presupuesto 2027 considera APS y Ley Ricarte Soto: "
                         "$189.696 millones frente a $166.951 millones.")
        return dict(actor="Ley Ricarte Soto", action="considera APS y Ley Ricarte Soto",
                    consequence="$189.696 millones frente a $166.951 millones", quote=quote,
                    consequence_quote=quote, status="proposal",
                    what="Según Pulso, la propuesta de Presupuesto 2027 considera APS y Ley Ricarte "
                         "Soto: $189.696 millones frente a $166.951 millones.",
                    why="El proyecto plantea las cantidades citadas para APS y Ley Ricarte Soto; "
                        "son recursos propuestos, sin una aprobación presupuestaria acreditada.")
    if "notificaron el 5 de agosto a la Fiscalía Nacional Económica su intención" in body:
        quote = _between(body, "El grupo Angelini,", "operación de residencias para adultos mayores.")
        return dict(actor="Inversiones Trentino Limitada",
                    action="notificaron el 5 de agosto a la Fiscalía Nacional Económica su intención de asociarse",
                    consequence="adquisición, desarrollo, construcción y operación de residencias para adultos mayores",
                    quote=quote, consequence_quote=quote, status="mixed_actual_and_future",
                    what="Según Pulso, Inversiones Trentino y Salfacorp notificaron su intención de "
                         "asociarse en un fondo que planea adquirir y operar residencias para adultos mayores.",
                    why="El plan podría ampliar la oferta de residencias para adultos mayores; la intención "
                        "notificada no constituye aprobación de la FNE ni una adquisición cerrada.")
    if "la UC San Carlos de Apoquindo presentó inundación del primer piso" in body:
        quote = _between(body, "En cuanto a los centros asistenciales,", "una evacuación horizontal.")
        return dict(actor="UC San Carlos de Apoquindo", action="presentó inundación del primer piso",
                    consequence="debió realizar una evacuación horizontal", quote=quote,
                    consequence_quote=quote, status="actual")
    if "se registraron 17.539 contratos suscritos por cotizantes" in body:
        quote = _between(body, "Según revelan las cifras que consolida la Superintendencia de Salud,",
                         "los 17.487 desahucios.")
        consequence = _between(body, "Esto se traduce en 52 suscripciones netas de desafiliaciones,",
                               "desde la industria.")
        return dict(actor="Superintendencia de Salud", action="se registraron 17.539 contratos suscritos",
                    consequence="52 suscripciones netas de desafiliaciones", quote=quote,
                    consequence_quote=consequence, status="actual")
    if "En mayo las isapres registraron 17.539 contratos suscritos" in body:
        quote = _literal(body, "En mayo las isapres registraron 17.539 contratos suscritos frente a "
                         "17.487 desahucios y 52 suscripciones netas.")
        return dict(actor="las isapres", action="registraron 17.539 contratos suscritos",
                    consequence="52 suscripciones netas", quote=quote,
                    consequence_quote=quote, status="actual")
    raise AssertionError("No concrete editorial unit witness for this request body")


def valid_assessment(ai, request, *, witness=None):
    """Add a literal fixture witness and unmistakably mocked response binding.

    The complete request text supplies every quote. Existing nonempty summaries,
    scores and reasons remain untouched; empty future summaries receive faithful
    prospective copy so a below-threshold test can reach the unchanged score gate.
    Additional fixtures may supply the same explicit witness fields as _witness;
    their quotes must still occur in this request, and validation remains strict.
    """
    result = deepcopy(ai)
    result.pop("_pulso_analysis_meta", None)
    body = request["text"]
    normalized_body = _normalized(body)
    witness = _witness(normalized_body) if witness is None else deepcopy(witness)
    quote = _literal(normalized_body, witness["quote"])
    consequence_quote = _literal(normalized_body, witness["consequence_quote"])
    proof = dict(scope_decision="human_health_specific",
                 scope_reason="La cita identifica el cambio concreto de cobertura, capacidad o financiamiento sanitario de la prueba.",
                 human_health_scope_quote=quote,
                 actor=witness["actor"], actor_quote=quote,
                 action=witness["action"], action_quote=quote,
                 consequence=witness["consequence"], consequence_quote=consequence_quote,
                 event_status=witness["status"], event_status_quote=quote,
                 novelty_decision="new_material_information",
                 novelty_reason="Testigo del dato o cambio específico evaluado; la prueba mantiene el puntaje y no aprueba publicación.",
                 novelty_quote=quote, future_claims=[])
    if witness["status"] != "actual":
        for field, fallback in (("what_happened", witness["what"]), ("why_it_matters", witness["why"])):
            if not result[field].strip():
                result[field] = fallback
            proof["future_claims"].append(dict(summary_field=field,
                                               summary_quote=result[field], source_quote=quote))
    result["pulso_editorial_proof"] = proof
    raw_output = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    request_input = news_analysis_input(title=request["title"], text=body,
                                        source_name=request["source_name"], full_text=True)
    result["_pulso_analysis_meta"] = dict(
        schema_version=VERSION, source_name=request["source_name"],
        analysis_text_sha256=hashlib.sha256(body.encode()).hexdigest(),
        request_input_sha256=hashlib.sha256(request_input.encode()).hexdigest(),
        response_id="unit-test-response", model="unit-test-no-paid-call",
        raw_model_output_sha256=hashlib.sha256(raw_output.encode()).hexdigest())
    validation = validate_pulso_editorial_proof(result, body)
    score = result["relevance_score"]
    if type(score) is int and 0 <= score < 72:
        assert validation["decision"] == "rejected", validation
        assert validation["reason"] == "editorial_relevance_below_threshold", validation
    else:
        assert validation["decision"] == "ready", validation
    assert result["relevance_score"] == ai["relevance_score"]
    assert result["reason"] == ai["reason"]
    return result
