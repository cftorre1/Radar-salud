"""CMF in the daily cycle: Dirección 27-oct-2026, decision (c).

Uses the committed, byte-verified CMF stock from the 11-oct capture
(data/market/cmf_events.json and cmf_disclosures.json) as fixture.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from radar_salud.cmf_daily import CmfDailyScout, process_cmf_event, verified_items, lane_enabled
from radar_salud.processing import DeferredProcessing

ROOT = Path(__file__).resolve().parents[1]
CFG = {"slug": "cmf_health_ecosystem", "name": "CMF", "source_type": "official", "base_confidence": 100,
       "system_domain": "PROVIDERS", "default_category": "Mercado"}


@pytest.fixture
def market_root(tmp_path):
    (tmp_path / "data/market").mkdir(parents=True)
    for name in ("cmf_events.json", "cmf_disclosures.json"):
        shutil.copy(ROOT / "data/market" / name, tmp_path / "data/market" / name)
    return tmp_path


def fake_runner(command, **kwargs):
    output = Path(command[command.index("--output") + 1])
    output.mkdir(parents=True, exist_ok=True)
    assert command[command.index("--packages") + 1:] == ["cmf", "isapres"] and kwargs["timeout"] == 60
    (output / "receipts.json").write_text(json.dumps({"as_of": "2026-10-11", "receipts": []}))


def ok_collector(captures, root):
    return {"pages_checked": 1, "items_discovered": 9, "unique_items": 9, "items_recent": 0, "items_material": 5,
            "published": 0, "rejected": 2, "deferred": 7, "parse_errors": 0, "coverage_complete": False,
            "coverage_reason": "fixture", "technical_status": "ok"}


def test_verified_events_become_queue_items_with_stable_identity(market_root):
    items = verified_items(market_root)
    assert len(items) == 5  # 7 deferred primary disclosures -> 5 material events
    urls = {raw.url for raw in items}
    assert len(urls) == 5 and all("#hecho-esencial-" in url and "ver_sgd" not in url for url in urls)
    clc = next(raw for raw in items if raw.metadata["official_document_number"] == "2026080512549")
    assert clc.event_date == "2026-08-05" and clc.title.startswith("Clínica Las Condes:")
    assert clc.metadata["verification"] == "primary_pdf_sha256_matches_reviewed_record"


def test_scout_runs_bounded_capture_and_marks_daily_activation(market_root):
    scout = CmfDailyScout(root=market_root, enabled=True, budget_seconds=60, runner=fake_runner,
                          collectors={"sis_isapre_universe": ok_collector, "cmf_health_ecosystem": ok_collector})
    items = scout.discover()
    assert len(items) == 5
    health = json.loads((market_root / "data/source_health.json").read_text())["sources"]
    assert health["cmf_health_ecosystem"]["runtime_activation"] == "daily_engine"
    assert health["sis_isapre_universe"]["runtime_activation"] == "daily_engine"
    assert scout.surface_results[0]["collectors"]["sis_isapre_universe"]["status"] == "ok"


def test_failed_collection_or_time_budget_never_emits_stale_events(market_root):
    def broken(captures, root):
        raise ValueError("CMF index layout changed")
    scout = CmfDailyScout(root=market_root, enabled=True, budget_seconds=60, runner=fake_runner,
                          collectors={"cmf_health_ecosystem": broken})
    with pytest.raises(RuntimeError, match="stale evidence"):
        scout.discover()

    def slow(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    scout = CmfDailyScout(root=market_root, enabled=True, budget_seconds=60, runner=slow)
    with pytest.raises(RuntimeError, match="budget"):
        scout.discover()
    assert scout.surface_results[0]["status"] == "capture_time_budget_exceeded"


def test_primary_not_refetched_this_poll_is_not_emitted(market_root):
    path = market_root / "data/market/cmf_disclosures.json"
    data = json.loads(path.read_text())
    for doc in data["documents"]:
        doc["primary_fetched_this_poll"] = False
    path.write_text(json.dumps(data))
    assert verified_items(market_root) == []


def test_deterministic_card_passes_normal_editorial_gate(market_root):
    raw = next(r for r in verified_items(market_root) if r.metadata["official_document_number"] == "2026090588441")
    row = process_cmf_event(raw, CFG)
    assert row["signal_types"] == ["Noticias"] and row["scopes"] == ["Prestadores"]
    assert row["primary_source_url"].startswith("https://www.cmfchile.cl/") and row["deterministic_processing"]
    assert "Hecho esencial oficial" in row["why_it_matters"] and row["publication_ready_score"] >= 62
    raw.metadata["verification"] = "unverified"
    with pytest.raises(DeferredProcessing):
        process_cmf_event(raw, CFG)


def test_lane_gate_and_disabled_scout():
    assert lane_enabled({"RADAR_CAPTURE_EVIDENCE": "1"}) and not lane_enabled({"RADAR_CAPTURE_EVIDENCE": "1", "PYTEST_CURRENT_TEST": "t"})
    assert CmfDailyScout(enabled=False).discover() == []


def test_capture_failure_keeps_sis_universe_polled_with_visible_error(market_root):
    def slow(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    with pytest.raises(RuntimeError):
        CmfDailyScout(root=market_root, enabled=True, budget_seconds=60, runner=slow).discover()
    sis = json.loads((market_root / "data/source_health.json").read_text())["sources"]["sis_isapre_universe"]
    assert sis["status"] == "error" and sis["runtime_activation"] == "daily_engine"
