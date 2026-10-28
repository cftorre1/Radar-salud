"""Scheduler backstop gate (Dirección 28-oct-2026): pure skip logic and workflow wiring."""
import importlib.util
import os
import re
import subprocess
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


def run(id_, wf, status="queued"):
    return {"id": id_, "status": status, "path": f".github/workflows/{wf}"}


def test_queue_gate_skips_recent_batches_and_active_writers():
    now = utc(2026, 10, 28, 3, 45)
    assert sr.queue_decision(now, "schedule", 50, now - timedelta(minutes=25), []) == (False, "queue_batch_recent")
    assert sr.queue_decision(now, "schedule", 50, now - timedelta(minutes=41), []) == (True, "no_recent_batch")
    assert sr.queue_decision(now, "schedule", 50, None, [])[0] is True
    assert sr.queue_decision(now, "schedule", 50, None, [run(9, "daily-radar.yml")]) \
        == (False, "writer_active_daily-radar")
    assert sr.queue_decision(now, "schedule", 50, None, [run(49, "queue-hourly.yml", "in_progress")]) \
        == (False, "earlier_queue_run_active")
    # A later duplicate does not stop the earlier one (exactly one of a racing pair proceeds).
    assert sr.queue_decision(now, "schedule", 50, None, [run(51, "queue-hourly.yml")])[0] is True
    assert sr.queue_decision(now, "workflow_dispatch", 50, now, [run(9, "daily-radar.yml")])[0] is True


def test_queue_gate_skips_for_every_writer_in_the_group():
    # Monday 11:45 UTC: weekly-insight backstop and the queue :45 backstop fire together.
    now = utc(2026, 11, 2, 11, 45)
    for wf in ("weekly-insight.yml", "weekly-insight-v2.yml", "import-commander-runtime.yml", "autopilot.yml",
               "occupational-source-recovery.yml", "df-isolated-audit.yml", "clinic-connectivity-diagnostic.yml"):
        for status in ("queued", "in_progress", "pending", "waiting"):
            assert sr.queue_decision(now, "schedule", 50, None, sr.active_writer_runs([run(7, wf, status)], 50)) \
                == (False, "writer_active_" + wf[:-4]), (wf, status)
    # Manual (workflow_dispatch) writer runs count too: status, not event, decides.
    manual = dict(run(8, "weekly-insight.yml", "in_progress"), event="workflow_dispatch")
    assert sr.queue_decision(now, "schedule", 50, None, sr.active_writer_runs([manual], 50))[0] is False


def test_active_writer_runs_filters_by_group_membership_and_status():
    runs = [run(1, "weekly-insight.yml", "in_progress"),
            dict(run(2, "import-commander-runtime.yml"), path=".github/workflows/import-commander-runtime.yml@refs/heads/staging"),
            run(3, "weekly-insight.yml", "completed"),       # finished
            run(4, "pages-build.yml", "in_progress"),        # not a writer
            {"id": 5, "status": "queued", "path": "dynamic/pages/pages-build-deployment"},
            run(50, "queue-hourly.yml", "in_progress"),       # this run
            run(1, "weekly-insight.yml", "in_progress")]      # same run listed under two statuses
    assert [r["id"] for r in sr.active_writer_runs(runs, exclude_id=50)] == [1, 2]
    assert sr.queue_decision(utc(2026, 10, 28, 3, 45), "schedule", 50, None,
                             sr.active_writer_runs([run(4, "pages-build.yml", "in_progress")], 50))[0] is True


def test_writer_workflows_cover_every_workflow_declaring_the_group():
    pattern = re.compile(r"^\s*group:\s*['\"]?" + re.escape(sr.WRITER_GROUP) + r"['\"]?\s*(#.*)?$", re.M)
    declared = {p.name for p in (ROOT / ".github/workflows").glob("*.y*ml")
                if pattern.search(p.read_text(encoding="utf-8"))}
    assert {"daily-radar.yml", "queue-hourly.yml", "weekly-insight.yml"} <= declared
    # Hardcoded list is the union over staging and main; a writer missing from it is a bug.
    assert declared <= sr.WRITER_WORKFLOWS, sorted(declared - sr.WRITER_WORKFLOWS)
    # Any other mention of the group name (e.g. a different YAML spelling) must also be covered.
    mentioned = {p.name for p in (ROOT / ".github/workflows").glob("*.y*ml")
                 if sr.WRITER_GROUP in p.read_text(encoding="utf-8")}
    assert mentioned <= sr.WRITER_WORKFLOWS, sorted(mentioned - sr.WRITER_WORKFLOWS)


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


PRIMARY = {"queue": "15 0-9,11-13,15-17,19-21,23 * * *", "daily": "30 10,14,18,22 * * *"}
BACKSTOP = {"queue": sr.QUEUE_BACKSTOP_CRON, "daily": sr.DAILY_BACKSTOP_CRON}


@pytest.mark.parametrize("mode", ["queue", "daily"])
def test_gate_errors_fail_open_for_primary_and_closed_for_backstop(capsys, monkeypatch, mode):
    def boom(*_a, **_k):
        raise OSError("gh unavailable")
    monkeypatch.setattr(sr, "gh_json", boom)
    monkeypatch.setattr(sr, "gh_head", boom)
    for schedule, expected in ((PRIMARY[mode], "run=true\nreason=gate_error_OSError"),
                               ("", "run=true\nreason=gate_error_OSError"),
                               (BACKSTOP[mode], "run=false\nreason=gate_error_backstop_OSError")):
        sr.main([mode, "--repo", "o/r", "--event", "schedule", "--run-id", "1", "--schedule", schedule])
        assert capsys.readouterr().out.strip() == expected, schedule


def test_daily_backstop_closed_when_discovery_state_unreadable():
    now = utc(2026, 10, 28, 12, 7)
    assert sr.daily_decision(now, "schedule", None, None, backstop=True) == (False, "discovery_state_unreadable_backstop")
    assert sr.daily_decision(now, "schedule", None, None, backstop=False) == (True, "slot_missing")
    assert sr.daily_decision(now, "schedule", utc(2026, 10, 28, 1, 0), None, backstop=True) == (True, "slot_missing")


def _gate_script(workflow):
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8"))
    return wf["jobs"]["gate"]["steps"][0]["run"]


@pytest.mark.parametrize("workflow,mode", [("queue-hourly.yml", "queue"), ("daily-radar.yml", "daily")])
@pytest.mark.parametrize("fetch_ok", [False, True])
def test_workflow_gate_shell_fallback(tmp_path, workflow, mode, fetch_ok):
    """Run the real gate step with a stub ``gh``: a failed fetch (404/rate limit) or a failing API fails
    closed for the backstop cron and open for the primary cron, and the script is read at $GITHUB_SHA."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gh.log"
    serve = f'cat "{ROOT / "scripts/should_run.py"}"; exit 0' if fetch_ok else "exit 1"
    (bin_dir / "gh").write_text(
        "#!/bin/bash\n"
        f'echo "$*" >> "{log}"\n'
        f'case "$*" in *contents/scripts/should_run.py*) {serve} ;; esac\n'
        'echo "HTTP 403: API rate limit exceeded" >&2; exit 1\n')
    (bin_dir / "gh").chmod(0o755)
    for schedule, expected in ((PRIMARY[mode], "run=true"), (BACKSTOP[mode], "run=false")):
        out_file = tmp_path / f"out-{expected}"
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", GH_TOKEN="x", REPO="o/r", EVENT="schedule",
                   RUN_ID="5", SCHEDULE=schedule, GITHUB_SHA="deadbeef", RUNNER_TEMP=str(tmp_path),
                   GITHUB_OUTPUT=str(out_file))
        subprocess.run(["bash", "-e", "-c", _gate_script(workflow)], env=env, check=True, capture_output=True)
        lines = out_file.read_text().splitlines()
        assert lines[0] == expected, (schedule, lines)
        if fetch_ok:  # script fetched, but its API calls fail
            reason = "reason=gate_error_backstop_" if expected == "run=false" else "reason=gate_error_"
        else:         # script itself unavailable (404 / rate limit)
            reason = "reason=gate_unavailable_backstop" if expected == "run=false" else "reason=gate_unavailable"
        assert lines[1].startswith(reason) and len(lines) == 2, lines
    calls = [c for c in log.read_text().splitlines() if "contents/scripts/should_run.py" in c]
    assert calls and all(c.endswith("contents/scripts/should_run.py?ref=deadbeef") for c in calls)


def test_workflow_gate_shell_passes_through_script_decision(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text("#!/bin/bash\necho '#!/bin/sh'; exit 0\n")
    (bin_dir / "gh").chmod(0o755)
    (bin_dir / "python3").write_text("#!/bin/bash\nprintf 'run=false\\nreason=queue_batch_recent\\n'\n")
    (bin_dir / "python3").chmod(0o755)
    out_file = tmp_path / "out"
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", REPO="o/r", EVENT="schedule", RUN_ID="5",
               SCHEDULE=PRIMARY["queue"], GITHUB_SHA="abc", RUNNER_TEMP=str(tmp_path), GITHUB_OUTPUT=str(out_file))
    subprocess.run(["bash", "-e", "-c", _gate_script("queue-hourly.yml")], env=env, check=True, capture_output=True)
    assert out_file.read_text().splitlines() == ["run=false", "reason=queue_batch_recent"]


def test_workflow_text_keeps_both_crons():
    queue = (ROOT / ".github/workflows/queue-hourly.yml").read_text(encoding="utf-8")
    daily = (ROOT / ".github/workflows/daily-radar.yml").read_text(encoding="utf-8")
    assert "'45 0-9,11-13,15-17,19-21,23 * * *'" in queue and "'7 0,12,16,20 * * *'" in daily
    for text in (queue, daily):
        assert "needs: gate" in text and "should_run.py" in text and "fetch-depth: 0" in text
        # Pinned to the running commit, never a moving branch; schedule passed for fail-closed backstops.
        assert "should_run.py?ref=$GITHUB_SHA" in text and "should_run.py?ref=staging" not in text
        assert "SCHEDULE: ${{ github.event.schedule }}" in text and '--schedule "$SCHEDULE"' in text
        for cron in sr.BACKSTOP_CRONS:
            assert f"'{cron}'" in text


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
