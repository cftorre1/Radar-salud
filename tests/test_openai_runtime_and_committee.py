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
