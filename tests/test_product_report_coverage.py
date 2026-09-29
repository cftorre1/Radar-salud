import importlib.util
import json
from pathlib import Path
from datetime import datetime, timezone

from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue


def load_report_module():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("product_report", root / "scripts/product_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_feature_observability_separates_monthly_accumulated_and_actual_model():
    module = load_report_module()
    rows = [
        {"at": "2026-08-20T00:00:00Z", "feature": "global_intelligence", "model": "gpt-5.6-terra",
         "requested_model": "gpt-5.6-luna", "input_tokens": 10, "output_tokens": 5, "cost_usd": None,
         "output_id": "old", "run_id": "r1"},
        {"at": "2026-09-20T00:00:00Z", "feature": "global_intelligence", "model": "gpt-5.6-terra",
         "requested_model": "gpt-5.6-luna", "input_tokens": 20, "output_tokens": 8, "cost_usd": None,
         "output_id": "new", "run_id": "r2"},
    ]
    free = {"global_teaser": {"model_trace": {"api_call": False, "output_id": "teaser"}}, "weekly_insight": None}
    result = module.feature_observability(rows, "2026-09", free)["global_intelligence"]
    assert result["periods"]["monthly"]["models"]["gpt-5.6-terra"]["calls"] == 1
    assert result["periods"]["accumulated"]["models"]["gpt-5.6-terra"]["calls"] == 2
    assert result["periods"]["accumulated"]["models"]["gpt-5.6-luna"]["calls"] is None
    assert result["periods"]["accumulated"]["cost_per_output"] is None


def test_coverage_live_funnel_excludes_backfill(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("product_report", root / "scripts/product_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    queue = PendingQueue(tmp_path / "data/state/pending_queue.json")
    (tmp_path / "data/state").mkdir(parents=True,exist_ok=True)
    (tmp_path / "data/state/discovery_run.json").write_text(json.dumps({"successful_sources":1,"failed_sources":0,"at":datetime.now(timezone.utc).isoformat()}))
    def raw(name):
        return RawItem("source", name, f"https://example.org/{name}", "Source", "official", "2026-09-23")
    queue.discover("source", [raw("visible"), raw("rejected")], last_discovered_at="2026-09-22T12:00:00+00:00")
    queue.discover("source", [raw("historical")])
    for key, item in queue.items.items():
        if item["raw"]["title"] == "visible":
            queue.finish(key, "published")
        elif item["raw"]["title"] == "rejected":
            queue.finish(key, "rejected")
    snapshot = tmp_path / "web/data/radar_today.json"
    snapshot.parent.mkdir(parents=True)
    observed={item["raw"]["title"]:item["detected_at"] for item in queue.items.values()}
    snapshot.write_text(json.dumps({"signals": [
        {"source_url": "https://example.org/visible", "ingestion_mode": "LIVE", "detected_at":observed["visible"]},
        {"source_url": "https://example.org/historical", "ingestion_mode": "BACKFILL", "detected_at":observed["historical"]},
    ]}))
    result = module.build(tmp_path, tmp_path / "web/data")
    assert result["coverage_live"] == {"detected": 2, "evaluated": 2, "selected": 1}
    assert result["queue"]["backfill_pending"] == 1

def test_coverage_counts_live_resolutions_inside_pulse(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("product_report", root / "scripts/product_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    queue = PendingQueue(tmp_path / "data/state/pending_queue.json")
    (tmp_path / "data/state").mkdir(parents=True,exist_ok=True)
    (tmp_path / "data/state/discovery_run.json").write_text(json.dumps({"successful_sources":1,"failed_sources":0,"at":datetime.now(timezone.utc).isoformat()}))
    queue.discover("s",[RawItem("s",name,f"https://example.org/{name}","Source","official","2026-09-23") for name in ("a","b")],last_discovered_at="2026-09-22T12:00:00+00:00")
    for key in queue.items:queue.finish(key,"published")
    snapshot=tmp_path/"web/data/radar_today.json";snapshot.parent.mkdir(parents=True)
    evidence={item["raw"]["title"]:item["detected_at"] for item in queue.items.values()}
    snapshot.write_text(json.dumps({"signals":[{"source_url":"https://example.org/a","ingestion_mode":"LIVE","detected_at":evidence["a"],"sanction_count":2,"source_alternatives":[{"url":"https://example.org/b","ingestion_mode":"LIVE","detected_at":evidence["b"]}]}]}))
    assert module.build(tmp_path,tmp_path/"web/data")["coverage_live"]["selected"]==2

def test_published_backfill_cannot_be_selected_by_fake_live_snapshot(tmp_path):
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location("product_report",root/"scripts/product_report.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    state=tmp_path/"data/state";state.mkdir(parents=True)
    (state/"discovery_run.json").write_text(json.dumps({"successful_sources":1,"at":datetime.now(timezone.utc).isoformat()}))
    q=PendingQueue(state/"pending_queue.json")
    q.discover("s",[RawItem("s","live","https://example.org/live","Source","official",datetime.now(timezone.utc).date().isoformat())],last_discovered_at=datetime.now(timezone.utc).isoformat())
    q.discover("s",[RawItem("s","backfill","https://example.org/backfill","Source","official",datetime.now(timezone.utc).date().isoformat())])
    for key in q.items:q.finish(key,"published")
    by_title={v["raw"]["title"]:v for v in q.items.values()}
    web=tmp_path/"web/data";web.mkdir(parents=True)
    (web/"radar_today.json").write_text(json.dumps({"signals":[
        {"source_url":"https://example.org/backfill","ingestion_mode":"LIVE","detected_at":by_title["backfill"]["detected_at"]},
        {"source_url":"https://example.org/live","ingestion_mode":"LIVE","detected_at":"forged"}]}))
    result=module.build(tmp_path,web)
    assert result["coverage_live"]=={"detected":1,"evaluated":1,"selected":0}


def test_statistics_parser_backlog_auto_registers_new_unparsed_data_sources():
    module = load_report_module()
    history = [
        {"title":"Nueva Estadística de Salud 2026","source_url":"https://example.org/new","event_date":"2026-09-26",
         "signal_types":["Datos"],"source_documents":[{"url":"https://example.org/new.xlsx"}]},
        {"title":"Estadística de cartera","source_url":"https://example.org/parsed","event_date":"2026-09-25",
         "signal_types":["Datos"],"data_insights":["Hallazgo reproducible"]},
        {"title":"Noticia común","source_url":"https://example.org/news","signal_types":["Noticias"]},
    ]
    rows = module.statistics_parser_backlog(history)
    by = {x["source_url"]:x for x in rows}
    assert by["https://example.org/new"]["status"] == "parser_pending"
    assert by["https://example.org/new"]["documents"] == 1
    assert by["https://example.org/parsed"]["status"] == "covered"
    assert "https://example.org/news" not in by


def test_segment_coverage_reports_live_funnel_published_stock_and_freshness_without_quotas():
    module=load_report_module()
    source_cfgs=[
        {"slug":"redsalud","source_type":"corporate","system_domain":"HEALTH"},
        {"slug":"minsal","source_type":"official","system_domain":"PUBLIC_HEALTH"},
        {"slug":"superintendencia_salud","source_type":"official","system_domain":"HEALTH_INSURANCE"},
    ]
    health={name:{"technical_status":"ok","status":"ok","last_signal_at":"2026-09-25"}
            for name in ("redsalud","minsal","superintendencia_salud")}
    queue_items=[{"source":"redsalud","lane":"LIVE"},{"source":"redsalud","lane":"BACKFILL"}]
    snapshot={"signals":[
        {"source_slug":"redsalud","scopes":["Prestadores","Isapres"],"event_date":"2026-09-25","ingestion_mode":"LIVE"},
        {"source_slug":"minsal","scopes":["Salud pública","Prestadores","Fonasa","Isapres"],"event_date":"2026-09-24","ingestion_mode":"BACKFILL"},
    ]}
    report=module.coverage_by_segment(source_cfgs,health,queue_items,snapshot,measured=True,today=__import__('datetime').date(2026,9,28))
    assert report["Prestadores"]["registered_sources"]==1
    assert report["Prestadores"]["active_sources"]==1
    assert report["Prestadores"]["detected_live"]==1
    assert report["Prestadores"]["selected_live"]==1
    assert report["Prestadores"]["published_feed"]==2
    assert report["Transversal"]["published_feed"]==2
    assert report["Prestadores"]["last_signal_age_days"]==3
    unavailable=module.coverage_by_segment(source_cfgs,health,queue_items,snapshot,measured=False,today=__import__('datetime').date(2026,9,28))
    assert unavailable["Prestadores"]["detected_live"] is None
    assert unavailable["Prestadores"]["published_feed"]==2


def test_product_report_preserves_persisted_deep_intelligence_weekly_insight(tmp_path):
    module = load_report_module()
    root = tmp_path
    (root / "data/weekly_insight").mkdir(parents=True)
    persisted = {
        "status": "pass",
        "top3": [{"rank": 1, "title": "Circular IF/N°535"}],
        "model": {"name": "gpt-5.6-terra", "fallback_used": False},
        "weekly_insight": {
            "id": "weekly-insight-v2",
            "insight_title": "Insight Terra",
            "source_url": "https://example.org/if535",
            "model_trace": {"api_call": True, "model": "gpt-5.6-terra"}
        },
    }
    (root / "data/weekly_insight/latest.json").write_text(json.dumps(persisted), encoding="utf-8")
    deterministic = {
        "status": "partial",
        "global_teaser": {"title": "Global"},
        "weekly_insight": {"insight_title": "Deterministic old"},
        "selection_policy": {"weekly_insight_status": "published_single_source_deep_dive"},
    }
    merged = module.merge_persisted_weekly_insight(root, deterministic)
    assert merged["weekly_insight"]["insight_title"] == "Insight Terra"
    assert merged["selection_policy"]["weekly_insight_status"] == "published_deep_intelligence"
    assert merged["selection_policy"]["deep_intelligence"]["name"] == "gpt-5.6-terra"
    assert merged["selection_policy"]["top3"][0]["title"] == "Circular IF/N°535"


def test_product_report_reads_orchestrator_queue_for_executive_status(tmp_path):
    module = load_report_module()
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config/orchestrator_queue.json").write_text(json.dumps({
        "updated_at": "2026-09-27",
        "tasks": [
            {"id": "a", "status": "in_progress"},
            {"id": "b", "status": "approved"},
            {"id": "c", "status": "blocked"},
            {"id": "d", "status": "validated"},
        ],
    }), encoding="utf-8")
    result = module.build(tmp_path, tmp_path / "web/data")
    assert result["read_model"]["freshness"] == "available"
    assert result["read_model"]["active_task_count"] == 2
    assert result["read_model"]["blocked_task_count"] == 1
    observed = result["scorecard"]["observed"]["development"]
    assert observed["active_task_count"] == 2
    assert observed["blocked_task_count"] == 1


def test_statistics_parser_backlog_marks_ges_parser_ready():
    module = load_report_module()
    rows = module.statistics_parser_backlog([{
        "title":"Estadística Trimestral de Casos GES (AUGE) de Fonasa y Sistema ISAPRE – a marzo 2026",
        "source_url":"https://example.org/ges",
        "event_date":"2026-07-10",
        "signal_types":["Datos"],
        "source_documents":[{"url":"https://example.org/ges.xlsx"}],
    }])
    assert rows[0]["status"]=="parser_ready"
    assert rows[0]["parser_family"]=="ges"
