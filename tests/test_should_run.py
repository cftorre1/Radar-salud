"""Scheduler backstop gate (Dirección 28-oct-2026): pure skip logic and workflow wiring."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("should_run", ROOT / "scripts/should_run.py")
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_latest_daily_slot_wraps_to_previous_evening():
    assert sr.latest_daily_slot(utc(2026, 10, 28, 1, 31)) == utc(2026, 10, 27, 22, 30)
    assert sr.latest_daily_slot(utc(2026, 10, 28, 0, 7)) == utc(2026, 10, 27, 22, 30)
    assert sr.latest_daily_slot(utc(2026, 10, 28, 10, 30)) == utc(2026, 10, 28, 10, 30)
    assert sr.latest_daily_slot(utc(2026, 10, 28, 12, 7)) == utc(2026, 10, 28, 10, 30)
    assert sr.latest_daily_slot(utc(2026, 10, 28, 10, 29)) == utc(2026, 10, 27, 22, 30)


def test_daily_backstop_runs_only_when_the_slot_discovery_is_missing():
    # 27/28-oct: 22:30 slot did not fire; the backstop at 00:07 sees discovery from 19:32.
    assert sr.daily_decision(utc(2026, 10, 28, 0, 7), "schedule", utc(2026, 10, 27, 20, 10), utc(2026, 10, 27, 21, 4)) \
        == (True, "slot_missing")
    # The late primary at 01:31 then finds the backstop's discovery and skips: never two per slot.
    assert sr.daily_decision(utc(2026, 10, 28, 1, 31), "schedule", utc(2026, 10, 28, 0, 40), None) \
        == (False, "discovery_done_for_slot")
    # Primary ran on time: backstop skips.
    assert sr.daily_decision(utc(2026, 10, 28, 12, 7), "schedule", utc(2026, 10, 28, 11, 2), None)[0] is False
    # Refresh commit is a second signal when discovery_run cannot be read.
    assert sr.daily_decision(utc(2026, 10, 28, 12, 7), "schedule", None, utc(2026, 10, 28, 12, 0)) \
        == (False, "daily_refresh_committed_for_slot")
    # Manual and push runs are never gated.
    assert sr.daily_decision(utc(2026, 10, 28, 12, 7), "workflow_dispatch", utc(2026, 10, 28, 11, 2), None)[0] is True
    assert sr.daily_decision(utc(2026, 10, 28, 12, 7), "push", utc(2026, 10, 28, 11, 2), None)[0] is True


def test_queue_gate_skips_recent_batches_and_active_writers():
    now = utc(2026, 10, 28, 3, 45)
    assert sr.queue_decision(now, "schedule", 50, now - timedelta(minutes=25), [], []) == (False, "queue_batch_recent")
    assert sr.queue_decision(now, "schedule", 50, now - timedelta(minutes=41), [], []) == (True, "no_recent_batch")
    assert sr.queue_decision(now, "schedule", 50, None, [], [])[0] is True
    assert sr.queue_decision(now, "schedule", 50, None, [{"id": 9, "status": "queued"}], []) == (False, "daily_radar_active")
    assert sr.queue_decision(now, "schedule", 50, None, [], [{"id": 49, "status": "in_progress"}]) \
        == (False, "earlier_queue_run_active")
    # A later duplicate does not stop the earlier one (exactly one of a racing pair proceeds).
    assert sr.queue_decision(now, "schedule", 50, None, [], [{"id": 51, "status": "queued"}])[0] is True
    assert sr.queue_decision(now, "workflow_dispatch", 50, now, [{"id": 9, "status": "queued"}], [])[0] is True


def test_signal_parsers():
    commits = [{"commit": {"message": "Merge PR #84", "committer": {"date": "2026-10-28T08:22:26Z"}}},
               {"commit": {"message": "chore: hourly queue batch", "committer": {"date": "2026-10-28T05:49:19Z"}}},
               {"commit": {"message": "chore: refresh Alicanto Salud", "committer": {"date": "2026-10-28T03:02:02Z"}}}]
    assert sr.last_commit_at(commits, sr.QUEUE_COMMIT) == utc(2026, 10, 28, 5, 49, 19)
    assert sr.last_commit_at(commits, sr.DAILY_COMMIT) == utc(2026, 10, 28, 3, 2, 2)
    assert sr.last_commit_at(commits[:1], sr.QUEUE_COMMIT) is None
    head = '{\n  "at": "2026-10-28T02:12:52.132018+00:00",\n  "sources": {\n    "superintendencia": {"discovered": 7'
    assert sr.discovery_at_from_head(head) == datetime(2026, 10, 28, 2, 12, 52, 132018, tzinfo=timezone.utc)
    assert sr.discovery_at_from_head("") is None
    runs = [{"id": 1, "status": "completed"}, {"id": 2, "status": "in_progress"}, {"id": 3, "status": "queued"}]
    assert [r["id"] for r in sr.active_runs(runs, exclude_id=3)] == [2]
    assert sr.batch_executed([{"name": "gate", "conclusion": "success", "started_at": "x"},
                              {"name": "batch", "conclusion": "success", "started_at": "x"}])
    assert not sr.batch_executed([{"name": "batch", "conclusion": "skipped", "started_at": None}])


def test_gate_fails_open(capsys, monkeypatch):
    def boom(*_a, **_k):
        raise OSError("gh unavailable")
    monkeypatch.setattr(sr, "gh_json", boom)
    sr.main(["queue", "--repo", "o/r", "--event", "schedule", "--run-id", "1"])
    out = capsys.readouterr().out
    assert "run=true" in out and "gate_error_OSError" in out


def test_workflow_text_keeps_both_crons():
    queue = (ROOT / ".github/workflows/queue-hourly.yml").read_text(encoding="utf-8")
    daily = (ROOT / ".github/workflows/daily-radar.yml").read_text(encoding="utf-8")
    assert "'45 0-9,11-13,15-17,19-21,23 * * *'" in queue and "'7 0,12,16,20 * * *'" in daily
    for text in (queue, daily):
        assert "needs: gate" in text and "should_run.py" in text and "fetch-depth: 0" in text


def test_workflows_wire_backstop_crons_and_gate():
    yaml = pytest.importorskip("yaml")  # not a runtime dependency; structural check where available
    queue = yaml.safe_load((ROOT / ".github/workflows/queue-hourly.yml").read_text(encoding="utf-8"))
    daily = yaml.safe_load((ROOT / ".github/workflows/daily-radar.yml").read_text(encoding="utf-8"))
    assert [c["cron"] for c in queue[True]["schedule"]] == ["15 0-9,11-13,15-17,19-21,23 * * *",
                                                            "45 0-9,11-13,15-17,19-21,23 * * *"]
    assert [c["cron"] for c in daily[True]["schedule"]] == ["30 10,14,18,22 * * *", "7 0,12,16,20 * * *"]
    # Backstop daily slots sit ~97 min after the primary ones.
    for (h, m), backstop in zip(sr.DAILY_SLOTS, (12, 16, 20, 0)):
        assert (backstop * 60 + 7 - (h * 60 + m)) % 1440 == 97
    # Queue: gate outside the writer lock, batch inside it; Daily: whole run inside it (gate sees pushed state).
    assert "concurrency" not in queue and "concurrency" not in queue["jobs"]["gate"]
    assert queue["jobs"]["batch"]["concurrency"] == {"group": "alicanto-staging-writer", "cancel-in-progress": False}
    assert daily["concurrency"] == {"group": "alicanto-staging-writer", "cancel-in-progress": False}
    for wf, job, mode in ((queue, "batch", "queue"), (daily, "build", "daily")):
        assert wf["jobs"][job]["needs"] == "gate" and "needs.gate.outputs.run != 'false'" in wf["jobs"][job]["if"]
        gate = wf["jobs"]["gate"]
        assert gate["permissions"] == {"contents": "read", "actions": "read"}
        assert not any("uses" in s for s in gate["steps"])  # no checkout of the heavy repo
        assert f"should_run.py\" {mode} " in gate["steps"][0]["run"]
