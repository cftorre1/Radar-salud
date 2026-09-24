import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
spec=importlib.util.spec_from_file_location("reviewer",Path("scripts/review_candidate.py"))
reviewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(reviewer)

def test_missing_snapshot_is_critical(tmp_path):
    r=reviewer.review(tmp_path,"abc")
    assert not r["checks"]["data"]
    assert any(x["code"]=="invalid_snapshot" for x in r["findings"])

def test_current_snapshot_passes_existing_editorial_gate():
    r=reviewer.review(Path("web"),"abc")
    assert r["checks"]["editorial"]
    assert not [f for f in r["findings"] if f["category"]=="data" and f["code"]!="stale_snapshot"]

def test_gate_rejects_explicitly_unrelated_and_generic_or_truncated_copy():
    from radar_salud.editorial_gate import publication_ready
    base={"title":"Noticia financiera con fecha comprobada", "source_name":"Diario Financiero", "source_url":"https://df.cl/salud/nota", "event_date":"2026-09-22", "what_happened":"La autoridad sancionó una sociedad tras una revisión.", "why_it_matters":"La sanción afecta a la sociedad, pero no hay antecedentes que permitan vincularla con el sector salud."}
    assert publication_ready(base)[1]=="unrelated_to_health"
    assert publication_ready(dict(base,why_it_matters="Aporta información oficial reciente sobre decisiones del sistema de salud."))[1]=="generic_impact"
    assert publication_ready(dict(base,why_it_matters="La decisión modifica la cobertura de los prestadores asociados.",what_happened="Texto incompleto Respecto de la CIC Nº […]"))[1]=="truncated_summary"

def test_new_export_timestamp_cannot_mask_stale_source_poll(tmp_path):
    (tmp_path/"data").mkdir()
    (tmp_path/"data/radar_today.json").write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat(),"signals":[]}),encoding="utf-8")
    (tmp_path/"data/source_health.json").write_text(json.dumps({"sources":{"sample":{"status":"ok","checked_at":"2020-01-01T00:00:00+00:00"}}}),encoding="utf-8")
    result=reviewer.review(tmp_path,"sha")
    assert any(x["code"]=="stale_source_check" for x in result["findings"])
