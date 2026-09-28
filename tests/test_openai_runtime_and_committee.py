import json
from radar_salud.editorial_committee import weekly_candidate_eligibility, build_committee_artifact
from radar_salud.openai_runtime import rolling_7d_spend

def test_weekly_gate_excludes_routine_accreditation_before_scoring():
    s={"title":"Resonancia Magnética del Biobío mantiene su acreditación tras cumplir el plan de corrección","source_name":"Superintendencia de Salud","signal_types":["Normativa"],"source_url":"https://example.org/r","feed_visibility":True}
    assert weekly_candidate_eligibility(s)["eligible"] is False

def test_weekly_gate_excludes_degraded_signal():
    s={"title":"Consejo sin medidas","source_name":"Minsal","signal_types":["Noticias"],"source_url":"https://example.org/n","editorial_decision":"degrade"}
    assert weekly_candidate_eligibility(s)["eligible"] is False

def test_committee_requires_normative_identity():
    s={"title":"Cobertura TEA cambia","source_name":"Superintendencia de Salud","source_url":"https://example.org/r","signal_types":["Normativa"],"editorial_decision":"accept"}
    a=build_committee_artifact(s)
    assert a["verdict"]=="REVISE"
    assert "normative_identity_missing" in a["critical_objections"]

def test_budget_ledger_sums_empty_recent_calls(tmp_path):
    p=tmp_path/"usage.json";p.write_text(json.dumps({"calls":[]}),encoding="utf-8")
    assert rolling_7d_spend(p)==0


def test_committee_stock_report_turns_grouped_and_degraded_items_into_hold():
    from radar_salud.editorial_committee import build_stock_committee_report
    base = {
        "source_name": "Superintendencia de Salud",
        "source_url": "https://example.org/source",
        "signal_types": ["Noticias"],
        "title": "Señal material",
        "what_happened": "Ocurrió un cambio verificable.",
        "why_it_matters": "Afecta una decisión.",
    }
    report = build_stock_committee_report([
        {**base, "id": "accept", "editorial_decision": "accept"},
        {**base, "id": "group", "editorial_decision": "group"},
        {**base, "id": "degrade", "editorial_decision": "degrade"},
        {**base, "id": "reject", "editorial_decision": "reject"},
    ])
    by_id = {x["signal_id"]: x for x in report["items"]}
    assert by_id["accept"]["verdict"] == "PASS"
    assert by_id["accept"]["individual_card_allowed"] is True
    assert by_id["group"]["verdict"] == "HOLD"
    assert by_id["degrade"]["verdict"] == "HOLD"
    assert by_id["reject"]["verdict"] == "REJECT"
    assert report["counts"] == {"PASS": 1, "REVISE": 0, "HOLD": 2, "REJECT": 1}


def test_astra_cost_estimate_uses_standard_api_input_and_output_rates():
    from radar_salud.openai_runtime import _estimate
    assert _estimate("gpt-6-astra", 100_000, 20_000) == 2.0


def test_unknown_model_pricing_fails_closed():
    import pytest
    from radar_salud.openai_runtime import _estimate
    with pytest.raises(ValueError, match="model_pricing_missing"):
        _estimate("unpriced-model", 1_000, 1_000)
