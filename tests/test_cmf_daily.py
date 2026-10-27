"""CMF in the daily cycle: Dirección 27-oct-2026, decision (c).

Uses the committed, byte-verified CMF stock from the 11-oct capture
(data/market/cmf_events.json and cmf_disclosures.json) as fixture.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from datetime import date

from radar_salud.cmf_daily import CmfDailyScout, process_cmf_event, verified_items, lane_enabled, publishable_event_date
from radar_salud.processing import DeferredProcessing, RejectedProcessing

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


def ok_collector(captures, root, collected=()):
    return {"pages_checked": 1, "items_discovered": 9, "unique_items": 9, "items_recent": 0, "items_material": 5,
            "published": 0, "rejected": 2, "deferred": 7, "parse_errors": 0, "coverage_complete": False,
            "coverage_reason": "fixture", "technical_status": "ok", "collected_record_ids": list(collected)}


ALL_IDS = ["93930000-7:2026080512549", "93930000-7:2026070499450", "94139000-5:2026070487689",
           "76020458-7:2026090624817", "76020458-7:2026090606426", "76020458-7:2026090598213",
           "92051000-0:2026090588747", "92051000-0:2026090588441", "92051000-0:2026090573202"]
BOND = "92051000-0:2026090588441"


def refresh(root, record_id, day, receipt):
    """Simulate a new hecho esencial collected in this run (same verified bytes)."""
    path = root / "data/market/cmf_disclosures.json"
    data = json.loads(path.read_text())
    for doc in data["documents"]:
        if doc["record_id"] == record_id:
            doc.update(published_at=day, event_date=day, primary_fetched_this_poll=True,
                       primary_receipt_completed_at=receipt)
            number = doc["official_document_number"]
    path.write_text(json.dumps(data))
    path = root / "data/market/cmf_events.json"
    events = json.loads(path.read_text())
    for event in events["events"]:
        if event["official_document_number"] == number:
            event["event_date"] = day
    path.write_text(json.dumps(events))


def test_committed_five_old_events_are_never_emitted_even_with_90_day_window(market_root, monkeypatch):
    # Dirección 27-oct-2026: the 2-ago..14-sep events stay archived.
    monkeypatch.setenv("RADAR_DAILY_WINDOW_DAYS", "90")
    data = json.loads((market_root / "data/market/cmf_disclosures.json").read_text())
    for doc in data["documents"]:
        doc["primary_receipt_completed_at"] = "2026-10-27T12:00:00+00:00"
    (market_root / "data/market/cmf_disclosures.json").write_text(json.dumps(data))
    skipped = []
    items = verified_items(market_root, collected_ids=ALL_IDS, run_started="2026-10-27T11:00:00+00:00",
                           today=date(2026, 10, 27), skipped=skipped)
    assert items == [] and len(skipped) == 5
    assert {s["reason"] for s in skipped} <= {"before_activation_or_older_than_30_days",
                                              "event_date_differs_from_lead_document_date"}
    assert publishable_event_date("2026-09-09", date(2026, 10, 27)) is False
    assert publishable_event_date("2026-10-26", date(2026, 10, 27)) is False  # before activation
    assert publishable_event_date("2026-10-27", date(2026, 10, 27)) is True
    assert publishable_event_date("2026-11-20", date(2026, 12, 27)) is False  # > 30 days


def test_new_event_collected_this_run_becomes_item_with_stable_identity(market_root):
    refresh(market_root, BOND, "2026-11-02", "2026-11-03T12:05:00+00:00")
    items = verified_items(market_root, collected_ids=ALL_IDS, run_started="2026-11-03T12:00:00+00:00",
                           today=date(2026, 11, 3))
    assert len(items) == 1
    raw = items[0]
    assert "#hecho-esencial-2026090588441" in raw.url and "ver_sgd" not in raw.url
    assert raw.title.startswith("INDISA:") and raw.event_date == "2026-11-02"
    assert raw.metadata["verification"] == "primary_pdf_sha256_matches_reviewed_record"


def test_stale_flags_receipts_or_uncollected_records_are_not_emitted(market_root):
    refresh(market_root, BOND, "2026-11-02", "2026-11-03T11:00:00+00:00")
    # Receipt older than this run's start: fetched in an earlier poll.
    assert verified_items(market_root, collected_ids=ALL_IDS, run_started="2026-11-03T12:00:00+00:00",
                          today=date(2026, 11, 3)) == []
    refresh(market_root, BOND, "2026-11-02", "2026-11-03T12:05:00+00:00")
    # Not collected in this run (only carried over from stored stock).
    skipped = []
    assert verified_items(market_root, collected_ids=[], run_started="2026-11-03T12:00:00+00:00",
                          today=date(2026, 11, 3), skipped=skipped) == []
    assert skipped[0]["reason"] == "lead_primary_not_fetched_this_run"


def test_event_date_must_match_lead_document_date(market_root):
    refresh(market_root, BOND, "2026-11-02", "2026-11-03T12:05:00+00:00")
    path = market_root / "data/market/cmf_events.json"
    events = json.loads(path.read_text())
    for event in events["events"]:
        if event["official_document_number"] == "2026090588441":
            event["event_date"] = "2026-11-01"
    path.write_text(json.dumps(events))
    skipped = []
    assert verified_items(market_root, collected_ids=ALL_IDS, run_started="2026-11-03T12:00:00+00:00",
                          today=date(2026, 11, 3), skipped=skipped) == []
    assert any(s["reason"] == "event_date_differs_from_lead_document_date" for s in skipped)


def test_scout_runs_bounded_capture_and_marks_daily_activation(market_root):
    scout = CmfDailyScout(root=market_root, enabled=True, budget_seconds=60, runner=fake_runner,
                          collectors={"sis_isapre_universe": ok_collector,
                                      "cmf_health_ecosystem": lambda c, r: ok_collector(c, r, ALL_IDS)})
    items = scout.discover()
    assert items == [] and len(scout.surface_results[0]["skipped_events"]) == 5
    health = json.loads((market_root / "data/source_health.json").read_text())["sources"]
    assert health["cmf_health_ecosystem"]["runtime_activation"] == "daily_engine"
    assert health["sis_isapre_universe"]["runtime_activation"] == "daily_engine"


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


def test_collect_cmf_resets_stored_poll_flags_and_fails_when_all_transport_fails(market_root):
    from radar_salud.market_sources import collect_cmf

    class NoTransport:
        as_of = "2026-10-27"
        receipts = [{"package": "cmf", "kind": "essential_90d", "transport_ok": False, "url": "https://www.cmfchile.cl/x",
                     "network": {"http_code": 0}}]
    with pytest.raises(RuntimeError, match="every issuer"):
        collect_cmf(NoTransport(), market_root)


def test_deterministic_card_passes_gate_only_for_publishable_dates(market_root, monkeypatch):
    refresh(market_root, BOND, "2026-11-02", "2026-11-03T12:05:00+00:00")
    raw = verified_items(market_root, collected_ids=ALL_IDS, run_started="2026-11-03T12:00:00+00:00",
                         today=date(2026, 11, 3))[0]
    monkeypatch.setattr("radar_salud.cmf_daily._chile_today", lambda: date(2026, 11, 3))
    row = process_cmf_event(raw, CFG)
    assert row["signal_types"] == ["Noticias"] and row["scopes"] == ["Prestadores"]
    assert row["primary_source_url"].startswith("https://www.cmfchile.cl/") and row["deterministic_processing"]
    assert "Hecho esencial oficial" in row["why_it_matters"] and row["publication_ready_score"] >= 62
    monkeypatch.setattr("radar_salud.cmf_daily._chile_today", lambda: date(2026, 12, 20))
    with pytest.raises(RejectedProcessing, match="older_than_30_days"):
        process_cmf_event(raw, CFG)
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
