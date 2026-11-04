"""Daily Radar watchdog (4-nov-2026): staleness alert and at most one re-dispatch per dropped slot."""
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("daily_watchdog", ROOT / "scripts/daily_watchdog.py")
wd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wd)


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def run(id_, created, status="completed", conclusion="success", event="schedule", wf="daily-radar.yml"):
    return {"id": id_, "created_at": created, "status": status, "conclusion": conclusion, "event": event,
            "path": f".github/workflows/{wf}"}


NOW = utc(2026, 11, 1, 12, 51)  # slot 10:30, backstop 12:07 dropped


def test_dispatches_only_when_both_crons_of_the_slot_were_dropped():
    old = [run(1, "2026-11-01T00:10:00Z")]
    assert wd.dispatch_decision(NOW, utc(2026, 11, 1, 0, 30), None, old, []) == (True, "slot_missed")
    assert wd.dispatch_decision(utc(2026, 11, 1, 12, 20), None, None, old, []) == (False, "slot_grace")
    assert wd.dispatch_decision(NOW, utc(2026, 11, 1, 10, 50), None, old, [])[1] == "discovery_done_for_slot"
    assert wd.dispatch_decision(NOW, None, utc(2026, 11, 1, 11, 0), old, [])[1] == "daily_refresh_committed_for_slot"


def test_never_stacks_runs_or_retries_a_deterministic_failure():
    active = [run(2, "2026-11-01T12:08:00Z", status="queued", conclusion=None)]
    assert wd.dispatch_decision(NOW, None, None, active, [])[1] == "daily_run_active"
    waiting = [run(3, "2026-11-01T12:45:00Z", status="pending", conclusion=None, wf="weekly-insight.yml")]
    assert wd.dispatch_decision(NOW, None, None, [], waiting)[1] == "writer_run_waiting"
    running = [run(3, "2026-11-01T12:45:00Z", status="in_progress", conclusion=None, wf="queue-hourly.yml")]
    assert wd.dispatch_decision(NOW, None, None, [], running) == (True, "slot_missed")
    failed = [run(4, "2026-11-01T10:40:00Z", conclusion="failure")]
    assert wd.dispatch_decision(NOW, None, None, failed, [])[1] == "daily_failed_for_slot"
    dispatched = [run(5, "2026-11-01T11:51:00Z", event="workflow_dispatch", conclusion="cancelled")]
    assert wd.dispatch_decision(NOW, None, None, dispatched, [])[1] == "already_dispatched_for_slot"
    # A failure from the previous slot does not stop this slot's recovery.
    assert wd.dispatch_decision(NOW, None, None, [run(6, "2026-10-31T22:40:00Z", conclusion="failure")], [])[0]


def test_staleness_uses_successful_build_jobs_not_gate_only_runs():
    runs = [run(10, "2026-11-01T12:07:00Z"), run(9, "2026-11-01T10:31:00Z", conclusion="failure"),
            run(8, "2026-10-30T05:33:00Z")]
    jobs = {10: [{"name": "gate", "conclusion": "success"}, {"name": "build", "conclusion": "skipped"}],
            8: [{"name": "build", "conclusion": "success", "completed_at": "2026-10-30T07:10:00Z"}]}
    last = wd.last_successful_build_at(runs, lambda rid: jobs.get(rid, []))
    assert last == utc(2026, 10, 30, 7, 10)
    assert wd.stale_decision(NOW, last) == (True, "last_success_53.7h_ago")
    assert wd.stale_decision(NOW, NOW - timedelta(hours=13))[0] is False
    assert wd.stale_decision(NOW, None) == (True, "no_successful_build_in_recent_runs")


def test_errors_never_dispatch(capsys, monkeypatch):
    monkeypatch.setattr(wd.sr, "workflow_runs", lambda *a: (_ for _ in ()).throw(OSError("gh down")))
    assert wd.main(["--repo", "o/r"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["dispatch=false", "dispatch_reason=watchdog_error_OSError",
                   "stale=false", "stale_reason=watchdog_error_OSError"]


def test_workflow_is_read_only_except_guarded_dispatch():
    yaml = pytest.importorskip("yaml")
    text = (ROOT / ".github/workflows/daily-radar-watchdog.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(text)
    assert wf["permissions"] == {"contents": "read", "actions": "write"}
    assert "secrets." not in text and "concurrency" not in text and "alicanto-staging-writer" not in text
    crons = [c["cron"] for c in wf[True]["schedule"]]
    assert crons == ["51 * * * *"]
    steps = wf["jobs"]["watchdog"]["steps"]
    assert not any("uses" in s for s in steps)  # no checkout
    assert "?ref=$GITHUB_SHA" in steps[0]["run"]
    dispatch = steps[1]
    assert "vars.DAILY_WATCHDOG_DISPATCH == 'true'" in dispatch["if"] and "steps.check.outputs.dispatch == 'true'" in dispatch["if"]
    assert "actions/workflows/daily-radar.yml/dispatches" in dispatch["run"]
    assert wf["jobs"]["watchdog"]["timeout-minutes"] <= 10
