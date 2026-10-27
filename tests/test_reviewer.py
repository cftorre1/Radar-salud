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
    # Freshness findings depend on the wall clock and are enforced by the CI
    # reviewer job and test_new_export_timestamp_cannot_mask_stale_source_poll;
    # this test guards the committed snapshot's structural and editorial gate.
    assert not [f for f in r["findings"] if f["category"]=="data" and f["code"] not in ("stale_snapshot","stale_source_check","stale_non_daily_source","awaiting_first_daily_poll")]

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

def test_reviewer_rejects_all_failed_or_future_source_polls(tmp_path):
    (tmp_path/"data").mkdir()
    (tmp_path/"data/radar_today.json").write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat(),"signals":[]}),encoding="utf-8")
    path=tmp_path/"data/source_health.json"
    path.write_text(json.dumps({"sources":{"official":{"status":"error"}}}),encoding="utf-8")
    assert any(x["code"]=="no_healthy_sources" for x in reviewer.review(tmp_path,"sha")["findings"])
    path.write_text(json.dumps({"sources":{"official":{"status":"ok","checked_at":"2099-01-01T00:00:00+00:00"}}}),encoding="utf-8")
    assert any(x["code"]=="future_source_check" for x in reviewer.review(tmp_path,"sha")["findings"])


def test_non_daily_sources_warn_but_daily_sources_still_block(tmp_path):
    (tmp_path/"data").mkdir()
    (tmp_path/"data/radar_today.json").write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat(),"signals":[]}),encoding="utf-8")
    old="2020-01-01T00:00:00+00:00"
    (tmp_path/"data/source_health.json").write_text(json.dumps({"sources":{
        "suseso":{"status":"ok","checked_at":old},
        "dipres_health_budget":{"status":"warning","checked_at":old},
        "global_who":{"status":"warning","checked_at":old,"operation_mode":"isolated_qualification"},
    }}),encoding="utf-8")
    findings=reviewer.review(tmp_path,"sha")["findings"]
    by_path={f["path"].rsplit("/",1)[-1]:f for f in findings if f["category"]=="data" and "stale" in f["code"]}
    assert by_path["suseso"]["code"]=="stale_source_check" and by_path["suseso"]["severity"]=="critical"
    for slug in ("dipres_health_budget","global_who"):
        assert by_path[slug]["code"]=="stale_non_daily_source" and by_path[slug]["severity"]=="warning"


def test_non_daily_policy_never_exempts_daily_capture_sources():
    policy=json.loads(Path("config/source_freshness_policy.json").read_text())
    daily=json.loads(Path("config/sources.json").read_text())+json.loads(Path("config/beta_source_configs.json").read_text())
    exempt=set(policy["non_daily_sources"])
    assert exempt <= {"dipres_health_budget","cmf_health_ecosystem","sis_isapre_universe"}
    ids={s.get("slug") or s.get("id") for s in daily if isinstance(s,dict)}
    assert len(ids)>20 and "suseso" in ids
    assert not (exempt & ids), "A source in the daily capture can never be exempted from the 7-day rule"


def test_daily_source_declaring_a_non_daily_mode_still_blocks(tmp_path):
    (tmp_path/"data").mkdir()
    (tmp_path/"data/radar_today.json").write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat(),"signals":[]}),encoding="utf-8")
    old="2020-01-01T00:00:00+00:00"
    (tmp_path/"data/source_health.json").write_text(json.dumps({"sources":{
        "suseso":{"status":"ok","checked_at":old,"operation_mode":"isolated_qualification"},
        "prestadores_data":{"status":"ok","checked_at":old,"operation_mode":"manual_curated_only"},
    }}),encoding="utf-8")
    findings=[f for f in reviewer.review(tmp_path,"sha")["findings"] if "stale" in f["code"]]
    assert {f["path"].rsplit("/",1)[-1] for f in findings if f["code"]=="stale_source_check" and f["severity"]=="critical"}=={"suseso","prestadores_data"}


def _grace_findings(tmp_path, monkeypatch, now, checked):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz else now.replace(tzinfo=None)
    monkeypatch.setattr(reviewer, "datetime", Frozen)
    (tmp_path/"data").mkdir(exist_ok=True)
    (tmp_path/"data/radar_today.json").write_text(json.dumps({"generated_at":now.isoformat(),"signals":[]}),encoding="utf-8")
    (tmp_path/"data/source_health.json").write_text(json.dumps({"sources":{
        "cmf_health_ecosystem":{"status":"ok","checked_at":checked},"suseso":{"status":"ok","checked_at":now.isoformat()}}}),encoding="utf-8")
    return {f["code"]:f["severity"] for f in reviewer.review(tmp_path,"sha")["findings"] if "cmf_health_ecosystem" in f.get("path","")}


def test_newly_activated_daily_source_grace_is_bounded_to_three_days_after_activation(tmp_path, monkeypatch):
    old = "2026-10-11T12:00:00+00:00"
    within = _grace_findings(tmp_path, monkeypatch, datetime(2026,10,29,12,tzinfo=timezone.utc), old)
    assert within == {"awaiting_first_daily_poll": "warning"}
    after = _grace_findings(tmp_path, monkeypatch, datetime(2026,10,31,12,tzinfo=timezone.utc), old)
    assert after.get("stale_source_check") == "critical"
    # Before the activation date (clock earlier than start) there is no grace either.
    before = _grace_findings(tmp_path, monkeypatch, datetime(2026,10,26,12,tzinfo=timezone.utc), old)
    assert "awaiting_first_daily_poll" not in before and before.get("stale_source_check") == "critical"


def test_naive_poll_timestamp_never_gets_activation_grace(tmp_path, monkeypatch):
    found = _grace_findings(tmp_path, monkeypatch, datetime(2026,10,28,12,tzinfo=timezone.utc), "2026-10-11T12:00:00")
    assert "awaiting_first_daily_poll" not in found and found.get("stale_source_check") == "critical"
