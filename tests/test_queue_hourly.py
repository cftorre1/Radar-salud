import json
from datetime import date

from radar_salud.daily_window import eligible_daily_item, item_date
from radar_salud.pending_queue import PendingQueue


def test_undated_items_use_detection_date_instead_of_waiting_forever():
    item = {"raw": {"event_date": None}, "detected_at": "2026-10-20T10:00:00+00:00"}
    assert item_date(item) == date(2026, 10, 20)
    assert eligible_daily_item(item, today=date(2026, 10, 27), days=30)
    assert not eligible_daily_item({"raw": {}, "detected_at": "2026-08-01T00:00:00"}, today=date(2026, 10, 27), days=30)
    assert item_date({"raw": {"event_date": "2026-10-01"}, "detected_at": "2026-10-20"}) == date(2026, 10, 1)


def test_retired_sources_are_archived_not_left_pending(tmp_path):
    p = tmp_path / "q.json"
    p.write_text(json.dumps({
        "a": {"source": "red_davila", "status": "pending", "lane": "LIVE", "attempts": 0, "detected_at": "x", "raw": {}},
        "b": {"source": "minsal", "status": "pending", "lane": "LIVE", "attempts": 0, "detected_at": "x", "raw": {}}}))
    q = PendingQueue(p)
    assert q.archive_sources({"red_davila": "retirada"}, reason="source_retired") == 1
    assert q.items["a"]["status"] == "archived" and q.items["b"]["status"] == "pending"


def test_hourly_batch_shares_the_writer_lock_and_never_discovers():
    wf = open(".github/workflows/queue-hourly.yml", encoding="utf-8").read()
    daily = open(".github/workflows/daily-radar.yml", encoding="utf-8").read()
    for text in (wf, daily):
        assert "group: alicanto-staging-writer" in text and "cancel-in-progress: false" in text
    assert "--process-only" in wf and "tests/test_reviewer.py" in wf and "RADAR_MONTHLY_USD: 10" in wf
    assert "--process-only" not in daily


def test_budget_is_paced_over_the_month():
    from datetime import datetime, timezone
    from radar_salud.ai_pricing import paced_budget_usd
    assert paced_budget_usd(datetime(2026, 10, 1, tzinfo=timezone.utc)) < 1.4
    assert paced_budget_usd(datetime(2026, 10, 31, tzinfo=timezone.utc)) == 10


def test_hourly_skips_discovery_hours_and_retries_push():
    wf = open(".github/workflows/queue-hourly.yml", encoding="utf-8").read()
    assert "'15 0-9,11-13,15-17,19-21,23 * * *'" in wf and "discovery_due.py" in wf
    assert "git pull --rebase --autostash origin staging" in open(".github/workflows/queue-hourly.yml", encoding="utf-8").read()
    assert "git pull --rebase origin staging" in open(".github/workflows/daily-radar.yml", encoding="utf-8").read()


def _commit_script(job_status):
    import yaml
    wf = yaml.safe_load(open(".github/workflows/queue-hourly.yml", encoding="utf-8"))
    step = next(s for s in wf["jobs"]["batch"]["steps"] if s.get("id") == "commit")
    return step["run"].replace("${{ job.status }}", job_status)


def _git(cwd, *args):
    import subprocess
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _clone_with_remote(tmp_path):
    remote, seed, work = tmp_path / "remote.git", tmp_path / "seed", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(tmp_path, "init", "-q", "-b", "staging", str(seed))
    for d in ("data/state", "data/history", "data/analysis_cache", "data/ai_usage", "data/inbox", "data/outbox", "web/data"):
        (seed / d).mkdir(parents=True)
        (seed / d / "f.json").write_text("{}")
    (seed / "data/source_health.json").write_text("{}")
    _git(seed, "add", "-A")
    _git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed")
    _git(seed, "push", "-q", str(remote), "staging")
    _git(tmp_path, "clone", "-q", "-b", "staging", str(remote), str(work))
    return remote, seed, work


def _run(script, cwd, tmp_path):
    import subprocess
    out = tmp_path / "gh_output"
    out.write_text("")
    proc = subprocess.run(["bash", "-e", "-c", script], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, "GITHUB_OUTPUT": str(out)})
    return proc, out.read_text()


import os  # noqa: E402


def test_hourly_commit_persists_paid_data_when_snapshot_is_rejected(tmp_path):
    remote, seed, work = _clone_with_remote(tmp_path)
    # Concurrent writer on staging while the batch ran: the pull --rebase must still succeed.
    (seed / "data/history/other.json").write_text("{}")
    _git(seed, "add", "-A")
    _git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "other")
    _git(seed, "push", "-q", str(remote), "staging")
    (work / "data/analysis_cache/f.json").write_text('{"paid": 1}')
    (work / "data/state/f.json").write_text('{"ledger": 1}')
    (work / "web/data/f.json").write_text('{"rejected_snapshot": 1}')  # reviewer failed: must not block or publish
    (work / "web/data/new.json").write_text("{}")
    proc, output = _run(_commit_script("failure"), work, tmp_path)
    assert proc.returncode == 0, proc.stderr
    pushed = _git(tmp_path, "--git-dir", str(remote), "show", "staging:data/analysis_cache/f.json")
    assert '"paid": 1' in pushed
    assert "rejected_snapshot" not in _git(tmp_path, "--git-dir", str(remote), "show", "staging:web/data/f.json")
    assert "changed=false" in output


def test_hourly_commit_fails_when_no_push_succeeds(tmp_path):
    remote, seed, work = _clone_with_remote(tmp_path)
    (work / "data/state/f.json").write_text('{"ledger": 1}')
    _git(work, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    script = _commit_script("success").replace("sleep $((attempt * 20))", "true")
    proc, output = _run(script, work, tmp_path)
    assert proc.returncode != 0 and "NOT pushed" in proc.stdout
    assert "push --dry-run" not in _commit_script("success")
