"""Single-call scope/prospectivity guards use captured complete originals."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from radar_salud import beta_sources, llm_analysis
from radar_salud.models import RawItem
from radar_salud.processing import DeferredProcessing
from radar_salud.pulso_editorial_proof import VERSION, model_binding_matches, validate_pulso_editorial_proof
from radar_salud.pulso_source import _verified_detail

ROOT = Path(__file__).resolve().parents[1]
ROWS = json.loads((ROOT / "data/audits/pulso_first_real_all32_semantic_review_2026_10_11.json").read_text())["all_signals"]
SNAPSHOT = json.loads((ROOT / "data/audits/pulso_first_real_processing_snapshot_2026_10_11.json").read_text())["signals"]


def clinical_assessment():
    row, signal = ROWS[6], SNAPSHOT[6]
    action = "hemos decidido trasladar a todos los pacientes, proceso que concluyó durante esta jornada"
    consequence = "suspender las operaciones durante algunas semanas mientras se realizan los trabajos de despeje, limpieza y recuperación de las áreas afectadas"
    assessment = dict(relevance_score=signal["editorial_relevance"], what_happened=signal["what_happened"],
                      why_it_matters=signal["why_it_matters"], reason="Traslado completo y cierre de semanas como nuevo balance del prestador.")
    assessment["pulso_editorial_proof"] = dict(
        scope_decision="human_health_specific", scope_reason="Suspensión de capacidad clínica y traslado de todos los pacientes de un prestador chileno.",
        human_health_scope_quote="las actuales condiciones no permiten contar con todos los servicios de apoyo operando a su capacidad habitual",
        actor="Clínica UC Christus", actor_quote="Clínica UC Christus dio a conocer el último balance del estado de su situación",
        action="trasladar a todos los pacientes", action_quote=action,
        consequence="suspender las operaciones durante algunas semanas", consequence_quote=consequence,
        event_status="actual", event_status_quote="proceso que concluyó durante esta jornada",
        novelty_decision="new_material_information", novelty_reason="El balance posterior informa traslado completado y cierre por semanas.",
        novelty_quote=action, future_claims=[])
    # The scope quote must directly carry the clinical identity too.
    assessment["pulso_editorial_proof"]["human_health_scope_quote"] = "mantener la actividad hospitalaria mediante traslados preventivos al Hospital Clínico UC"
    return row["original_full_primary_body"], assessment


def care_plan_assessment():
    row = ROWS[13]
    action = "habrá un aumento de 2.624 millones de pesos, equivalente al 4,7%, para la Red Local de Apoyos y Cuidados."
    consequence = "Esto permitirá incorporar 24 nuevas comunas y llegar a 333 de las 345 que establece la ley."
    what = "Según Pulso / La Tercera, Desarrollo Social anunció un aumento previsto de $2.624 millones para la Red Local de Apoyos y Cuidados, que permitiría incorporar 24 comunas y llegar a 333; es una ampliación futura."
    why = "Si se concreta la ampliación anunciada, podría aumentar la cobertura de cuidados domiciliarios; las 24 nuevas comunas y la meta de 333 deben distinguirse de capacidad ya disponible."
    ai = dict(relevance_score=78, what_happened=what, why_it_matters=why,
              reason="Distingue el avance operacional de discapacidad y el anuncio prospectivo de cuidados.")
    ai["pulso_editorial_proof"] = dict(
        scope_decision="human_health_specific", scope_reason="Una ampliación concreta de cuidados a personas con dependencia, todavía futura.",
        human_health_scope_quote="modernizar la solicitud de la certificación de discapacidad y la nueva plataforma que permite al usuario hacer seguimiento del proceso",
        actor="ministra Wulf", actor_quote="En materia de cuidados domiciliarios, la ministra Wulf destacó por su parte que " + action,
        action="habrá un aumento de 2.624 millones de pesos", action_quote=action,
        consequence="incorporar 24 nuevas comunas", consequence_quote=consequence,
        event_status="plan", event_status_quote=action,
        novelty_decision="new_material_information", novelty_reason="Cuantifica el aumento anunciado y la expansión territorial todavía pendiente.",
        novelty_quote=consequence, future_claims=[
            dict(summary_field="what_happened", summary_quote=what, source_quote=action),
            dict(summary_field="why_it_matters", summary_quote=why, source_quote=consequence)])
    return row["original_full_primary_body"], ai


def bind(ai, request):
    answer = copy.deepcopy(ai)
    serialized = json.dumps(answer, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    answer["_pulso_analysis_meta"] = dict(schema_version=VERSION, source_name=request["source_name"],
        analysis_text_sha256=hashlib.sha256(request["text"].encode()).hexdigest(),
        request_input_sha256=hashlib.sha256(llm_analysis.news_analysis_input(
            title=request["title"], text=request["text"], source_name=request["source_name"], full_text=True).encode()).hexdigest(),
        response_id="unit-test-response", model="unit-test-no-paid-call",
        raw_model_output_sha256=hashlib.sha256(serialized.encode()).hexdigest())
    return answer


def original_clinical_raw():
    row = ROWS[6]
    path = ROOT / "tests/fixtures/pulso_runtime_real" / (row["original_html_sha256"] + ".html.gz")
    html = gzip.decompress(path.read_bytes()).decode()
    assert hashlib.sha256(html.encode()).hexdigest() == row["original_html_sha256"]
    parsed = _verified_detail(dict(url=row["url"], listing="captured-original-unit-test"), lambda _: html, None)
    assert parsed["metadata"]["article_body_sha256"] == row["original_body_sha256"]
    return RawItem("pulso_latercera", parsed["title"], row["url"], "Pulso / La Tercera", "press_high_trust",
                   parsed["metadata"]["publication_date"], parsed["body"], parsed["metadata"])


def test_original_clinical_increment_is_grounded_and_quotes_are_not_semantic_approval():
    body, ai = clinical_assessment()
    verdict = validate_pulso_editorial_proof(ai, body)
    assert verdict["decision"] == "ready" and verdict["prospective_evidence"] is False
    assert verdict["quote_validation_is_semantic_approval"] is False
    assert verdict["publication_approved"] is False
    assert verdict["analysis_text_sha256"] == ROWS[6]["original_body_sha256"]


@pytest.mark.parametrize("change", ["missing", "foreign_quote", "actor_paraphrase", "score_bool", "future_type", "what_type"])
def test_missing_or_incompatible_proof_defers_instead_of_publishing(change):
    body, ai = clinical_assessment()
    if change == "missing": ai.pop("pulso_editorial_proof")
    elif change == "foreign_quote": ai["pulso_editorial_proof"]["action_quote"] = "Un hospital distinto inauguró un pabellón no reportado en este original."
    elif change == "actor_paraphrase": ai["pulso_editorial_proof"]["actor"] = "Otro prestador imaginario"
    elif change == "score_bool": ai["relevance_score"] = True
    elif change == "future_type": ai["pulso_editorial_proof"]["future_claims"] = None
    elif change == "what_type": ai["what_happened"] = []
    assert validate_pulso_editorial_proof(ai, body)["decision"] == "deferred"


@pytest.mark.parametrize("scope", ["incidental_health", "non_human_health", "marketing", "opinion"])
def test_explicit_excluded_scope_rejects_even_with_high_score_and_real_quotes(scope):
    body = ROWS[22]["original_full_primary_body"]
    _, ai = clinical_assessment(); ai["relevance_score"] = 99
    ai["pulso_editorial_proof"].update(scope_decision=scope,
        scope_reason="El original trata una querella sobre ecosistemas y salud animal o vegetal, sin cambio en atención humana.",
        human_health_scope_quote="propagación indebida de agentes susceptibles de poner en peligro la salud animal o vegetal")
    assert validate_pulso_editorial_proof(ai, body)["reason"] == "pulso_editorial_" + scope


def test_real_announced_care_plan_is_eligible_but_achieved_capacity_copy_is_deferred():
    body, ai = care_plan_assessment()
    assert validate_pulso_editorial_proof(ai, body)["prospective_evidence"] is True
    bad = copy.deepcopy(ai)
    bad["what_happened"] = SNAPSHOT[13]["what_happened"]
    bad["why_it_matters"] = SNAPSHOT[13]["why_it_matters"]
    bad["pulso_editorial_proof"]["future_claims"][0]["summary_quote"] = "alcanzando 333 de las 345 previstas por ley"
    bad["pulso_editorial_proof"]["future_claims"][1]["summary_quote"] = "el mayor presupuesto y la expansión territorial elevan la capacidad de atención"
    assert validate_pulso_editorial_proof(bad, body)["reason"] == "pulso_editorial_future_copy_not_grounded"
    ai["pulso_editorial_proof"].update(event_status="actual", future_claims=[])
    assert validate_pulso_editorial_proof(ai, body)["reason"] == "pulso_editorial_future_status_mismatch"


@pytest.mark.parametrize("novelty,decision", [("repetition_or_context", "rejected"), ("uncertain", "deferred")])
def test_context_repetition_or_uncertain_increment_never_becomes_approved(novelty, decision):
    body, ai = clinical_assessment(); ai["pulso_editorial_proof"]["novelty_decision"] = novelty
    assert validate_pulso_editorial_proof(ai, body)["decision"] == decision


def test_pipeline_keeps_threshold72_original_date_press_maturity_and_single_assessment(monkeypatch):
    raw = original_clinical_raw(); body, ai = clinical_assessment(); calls = []
    def assess(**request):
        calls.append(request)
        return bind(ai, request)
    monkeypatch.setattr(llm_analysis, "analyze_news", assess)
    row = beta_sources.process_curated_beta_source(raw, {})
    assert len(calls) == 1 and calls[0]["text"] == body and calls[0]["pulso_editorial_proof"] is True
    assert row["evidence_maturity"] == "media_reported" and row["publication_date"] == "2026-10-10"
    assert row["editorial_relevance"] == 72 and raw.metadata["editorial_assessment"]["threshold"] == 72
    assert raw.metadata["pulso_editorial_proof_validation"]["publication_approved"] is False
    raw = original_clinical_raw(); ai["relevance_score"] = 71
    assert beta_sources.process_curated_beta_source(raw, {}) is None
    assert raw.metadata["rejection_reason"] == "editorial_relevance_below_threshold"


def test_pipeline_missing_structured_proof_defers_and_records_exact_model_binding(monkeypatch):
    raw = original_clinical_raw(); _, ai = clinical_assessment(); ai.pop("pulso_editorial_proof")
    monkeypatch.setattr(llm_analysis, "analyze_news", lambda **request: bind(ai, request))
    with pytest.raises(DeferredProcessing, match="pulso_editorial_proof_missing"):
        beta_sources.process_curated_beta_source(raw, {})
    assert raw.metadata["editorial_assessment"]["decision"] == "pending"
    assert raw.metadata["analysis_model_output"]["_pulso_analysis_meta"]["response_id"] == "unit-test-response"


def test_pipeline_cross_article_response_cannot_bypass_body_request_binding(monkeypatch):
    raw = original_clinical_raw(); _, ai = clinical_assessment()
    def mismatched(**request):
        response = bind(ai, request)
        response["_pulso_analysis_meta"]["request_input_sha256"] = "0" * 64
        return response
    monkeypatch.setattr(llm_analysis, "analyze_news", mismatched)
    with pytest.raises(DeferredProcessing, match="pulso_editorial_model_binding_mismatch"):
        beta_sources.process_curated_beta_source(raw, {})


@pytest.mark.parametrize("strict", [False, True])
def test_llm_adds_only_opt_in_schema_to_the_same_single_fast_call(monkeypatch, strict):
    body, ai = clinical_assessment(); calls = []; budget = []; results = []; traces = []
    response = SimpleNamespace(output_text=json.dumps(ai), id="unit-provider-response", model="unit-model")
    def create(**kwargs): calls.append(kwargs); return response
    monkeypatch.setattr(llm_analysis, "_client", lambda: SimpleNamespace(responses=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_analysis, "allow_call", lambda kind: budget.append(kind) or True)
    monkeypatch.setattr(llm_analysis, "record_result", lambda *args: results.append(args))
    monkeypatch.setattr(llm_analysis, "record_response", lambda *args: traces.append(args))
    result = llm_analysis.analyze_news(title="Original clinical article", text=body, source_name="Pulso / La Tercera",
                                      full_text=True, pulso_editorial_proof=strict)
    assert len(calls) == len(results) == len(traces) == 1 and budget == ["fast"]
    schema = calls[0]["text"]["format"]["schema"]
    if strict:
        assert "pulso_editorial_proof" in schema["required"]
        request_sha = hashlib.sha256(calls[0]["input"].encode()).hexdigest()
        assert model_binding_matches(result, source_name="Pulso / La Tercera", input_text_sha256=hashlib.sha256(body.encode()).hexdigest(), request_input_sha256=request_sha)
    else:
        assert schema is llm_analysis.NEWS_SCHEMA and len(schema["required"]) == 4
        assert "_pulso_analysis_meta" not in result


def test_strict_proof_cannot_send_an_excerpt_or_spend_budget_before_full_input(monkeypatch):
    monkeypatch.setattr(llm_analysis, "_client", lambda: pytest.fail("Do not call client for a truncated proof request"))
    with pytest.raises(ValueError, match="complete primary input"):
        llm_analysis.analyze_news(title="Article", text="Excerpt", source_name="Pulso", pulso_editorial_proof=True)
