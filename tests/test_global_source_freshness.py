from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest

from radar_salud.global_source_freshness import assess_snapshot


CHECKED = datetime(2026, 10, 11, 16, tzinfo=timezone.utc)


def qualified(**updates):
    return dict(checked_at=CHECKED.isoformat(), technical_status="ok",
                coverage_completeness="complete", pending_date_items=0,
                technical_failures=[], recurrent_operation_proven=False, **updates)


@pytest.mark.parametrize("seconds,expected", [
    (0, "qualified_snapshot_within_24h"),
    (86399, "qualified_snapshot_within_24h"),
    (86400, "alert_24h"),
    (172799, "alert_24h"),
    (172800, "degraded_48h"),
])
def test_daily_first_exact_24_48_hour_boundaries_do_not_prove_operation(seconds, expected):
    health = qualified()
    before = dict(health)
    result = assess_snapshot(health, CHECKED + timedelta(seconds=seconds))
    assert result["evidence_freshness"] == expected
    assert result["age_seconds"] == seconds
    assert not result["operation_proven_by_this_check"]
    assert not result["cadence_proven_by_this_check"]
    assert not result["publication_authority"]
    assert health == before


@pytest.mark.parametrize("timestamp", [None, "", "invalid", "2026-10-11", "2026-10-11T16:00:00"])
def test_unverifiable_or_timezone_missing_capture_fails_closed(timestamp):
    health = qualified(); health["checked_at"] = timestamp
    result = assess_snapshot(health, CHECKED)
    assert result["evidence_freshness"] == "unverified_timestamp"
    assert result["age_seconds"] is None


def test_future_capture_is_not_fresh_evidence():
    result = assess_snapshot(qualified(), CHECKED - timedelta(seconds=1))
    assert result["evidence_freshness"] == "future_timestamp_hold"
    assert result["age_seconds"] is None


@pytest.mark.parametrize("change", [
    {"technical_status": "error"}, {"coverage_completeness": "incomplete"},
    {"pending_date_items": 1}, {"technical_failures": [{"error": "HTTP403"}]},
    {"technical_status": "not_polled_license_hold"},
])
def test_recent_response_cannot_hide_technical_date_or_coverage_failure(change):
    health = qualified(); health.update(change)
    assert assess_snapshot(health, CHECKED)["evidence_freshness"] == "verification_hold"


def test_offset_capture_and_utc_observation_use_elapsed_time_not_calendar_day():
    health = qualified(); health["checked_at"] = "2026-10-11T13:00:00-03:00"
    result = assess_snapshot(health, CHECKED + timedelta(hours=24))
    assert result["age_seconds"] == 86400
    assert result["evidence_freshness"] == "alert_24h"


def test_observation_without_timezone_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        assess_snapshot(qualified(), CHECKED.replace(tzinfo=None))


@pytest.mark.parametrize("output", ["health.json", "data/global/themes.json", "web/data/product.json", "work/existing.json"])
def test_cli_refuses_overwrite_input_curated_health_or_existing_receipt(tmp_path, output):
    source = tmp_path / "health.json"
    source.write_text(json.dumps({"sources": {"who": qualified(), "paho": qualified()}}))
    target = tmp_path / output
    target.parent.mkdir(parents=True, exist_ok=True)
    if target != source:
        target.write_text("retained bytes")
    before = target.read_bytes()
    script = Path(__file__).resolve().parents[1] / "scripts/check_global_source_freshness.py"
    result = subprocess.run([sys.executable, str(script), "--input", str(source), "--now", CHECKED.isoformat(),
                             "--output", str(target)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0 and "cannot overwrite" in result.stderr
    assert target.read_bytes() == before


def test_cli_observation_writes_only_requested_new_work_receipt(tmp_path):
    source = tmp_path / "health.json"
    source.write_text(json.dumps({"sources": {"who": qualified(), "paho": qualified()}}))
    before = source.read_bytes()
    script = Path(__file__).resolve().parents[1] / "scripts/check_global_source_freshness.py"
    result = subprocess.run([sys.executable, str(script), "--input", str(source), "--now", CHECKED.isoformat(),
                             "--output", "work/observation.json"], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "work/observation.json").read_text())
    assert report["network_requests"] == report["paid_ai_calls"] == report["publication_count"] == 0
    assert report["does_not_satisfy_daily_cycle_or_24h_cadence"]
    assert source.read_bytes() == before


def test_package_merge_cannot_implicitly_activate_global_collection():
    config = json.loads(Path("config/global_discovery.json").read_text())
    assert config["daily_collection_enabled"] is False
    assert config["reuters"]["enabled"] is False
    text = Path(".github/workflows/daily-radar.yml").read_text()
    discovery = text.split("- name: Independent Global metadata discovery", 1)[1].split("- name:", 1)[0]
    assert "always() && steps.global_policy.outputs.enabled == 'true'" in discovery
    assert "OPENAI_API_KEY: ''" in discovery
    assert 'data/audits/global_integration_2026_10_11' in text
