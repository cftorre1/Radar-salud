"""Scheduler backstop gate (Dirección 28-oct-2026, "Respaldo en GitHub").

GitHub drops or delays scheduled events under load (27/28-oct: 8 of ~10 hourly
queue slots never fired; the 22:30 Daily Radar fired at 01:31). The workflows add
backstop crons; this gate decides, without checking out the repository, whether a
scheduled run should do the work or exit as a no-op.

Prints ``run=true|false`` and ``reason=...`` for $GITHUB_OUTPUT. Manual and push
runs always run. Any error fails open (``run=true``), i.e. never worse than having
no gate. Standard library only; GitHub data comes from ``gh api``.

    python3 should_run.py queue --repo OWNER/NAME --event schedule --run-id 123
    python3 should_run.py daily --repo OWNER/NAME --event schedule --run-id 123
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

QUEUE_RECENT = timedelta(minutes=40)
DAILY_SLOTS = ((10, 30), (14, 30), (18, 30), (22, 30))  # UTC, daily-radar.yml primary cron
ACTIVE = {"queued", "in_progress", "waiting", "pending", "requested"}
QUEUE_COMMIT = "chore: hourly queue batch"
DAILY_COMMIT = "chore: refresh Alicanto Salud"
QUEUE_WORKFLOW = "queue-hourly.yml"
DAILY_WORKFLOW = "daily-radar.yml"


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def latest_daily_slot(now: datetime, slots=DAILY_SLOTS) -> datetime:
    """Most recent primary Daily Radar slot at or before ``now`` (UTC)."""
    now = now.astimezone(timezone.utc)
    for days_back in (0, 1):
        day = now - timedelta(days=days_back)
        candidates = [day.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in slots]
        past = [c for c in candidates if c <= now]
        if past:
            return max(past)
    raise ValueError("no slots configured")


def last_commit_at(commits: list[dict], prefix: str) -> datetime | None:
    """Committer time of the newest commit whose message starts with ``prefix``
    (commits as returned by GET /repos/{repo}/commits, newest first)."""
    for c in commits:
        info = c.get("commit") or {}
        if (info.get("message") or "").startswith(prefix):
            return parse_ts((info.get("committer") or {}).get("date"))
    return None


def active_runs(runs: list[dict], exclude_id: int | None = None) -> list[dict]:
    return [r for r in runs if r.get("status") in ACTIVE and r.get("id") != exclude_id]


def discovery_at_from_head(text: str) -> datetime | None:
    """``at`` from the first bytes of data/state/discovery_run.json (17 MB; never download it whole)."""
    m = re.search(r'"at"\s*:\s*"([^"]+)"', text)
    return parse_ts(m.group(1)) if m else None


def queue_decision(now: datetime, event: str, run_id: int, last_batch_at: datetime | None,
                   daily_active: list[dict], queue_active: list[dict]) -> tuple[bool, str]:
    """Hourly queue gate. ``last_batch_at``: newest of the last queue commit or the last
    run whose batch job actually executed (empty batches do not commit)."""
    if event != "schedule":
        return True, "manual_or_dispatch"
    if daily_active:
        # Entering the writer group now could replace a pending Daily Radar; it also processes the queue.
        return False, "daily_radar_active"
    if any(int(r.get("id") or 0) < run_id for r in queue_active):
        return False, "earlier_queue_run_active"
    if last_batch_at and now - last_batch_at < QUEUE_RECENT:
        return False, "queue_batch_recent"
    return True, "no_recent_batch"


def daily_decision(now: datetime, event: str, discovery_at: datetime | None,
                   refresh_commit_at: datetime | None) -> tuple[bool, str]:
    """Daily Radar gate: a scheduled run (primary or backstop) discovers only if no
    discovery has happened since the current slot started. Runs inside the writer
    lock, so a slot's earlier run has already pushed its state."""
    if event != "schedule":
        return True, "manual_or_push"
    slot = latest_daily_slot(now)
    if discovery_at and discovery_at >= slot:
        return False, "discovery_done_for_slot"
    if refresh_commit_at and refresh_commit_at >= slot:
        return False, "daily_refresh_committed_for_slot"
    return True, "slot_missing"


def batch_executed(jobs: list[dict]) -> bool:
    """True when a run's ``batch`` job ran (not skipped by the gate, not cancelled while pending)."""
    return any(j.get("name") == "batch" and j.get("started_at") and j.get("conclusion") not in ("skipped", "cancelled")
               for j in jobs)


# --- GitHub I/O (thin; not unit tested) ---------------------------------------------------------

def gh_json(path: str):
    out = subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True, timeout=60).stdout
    return json.loads(out)


def gh_head(path: str, size: int = 4096) -> str:
    proc = subprocess.Popen(["gh", "api", "-H", "Accept: application/vnd.github.raw", path],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        return proc.stdout.read(size).decode("utf-8", "replace")
    finally:
        proc.kill()
        proc.wait()


def workflow_runs(repo: str, workflow: str) -> list[dict]:
    return gh_json(f"repos/{repo}/actions/workflows/{workflow}/runs?per_page=20").get("workflow_runs", [])


def recent_queue_batch_at(repo: str, now: datetime, runs: list[dict], run_id: int) -> datetime | None:
    newest = None
    for r in runs:
        created = parse_ts(r.get("created_at"))
        if r.get("id") == run_id or r.get("status") != "completed" or not created or now - created > QUEUE_RECENT * 4:
            continue
        jobs = gh_json(f"repos/{repo}/actions/runs/{r['id']}/jobs").get("jobs", [])
        if batch_executed(jobs):
            ended = max((parse_ts(j.get("completed_at")) or created for j in jobs if j.get("name") == "batch"), default=created)
            newest = max(filter(None, (newest, ended)))
    return newest


def decide(args, now: datetime) -> tuple[bool, str]:
    if args.event != "schedule":
        return True, "manual_or_dispatch"
    commits = gh_json(f"repos/{args.repo}/commits?sha=staging&per_page=100")
    if args.mode == "queue":
        queue_runs = workflow_runs(args.repo, QUEUE_WORKFLOW)
        daily_runs = workflow_runs(args.repo, DAILY_WORKFLOW)
        last = [t for t in (last_commit_at(commits, QUEUE_COMMIT),
                            recent_queue_batch_at(args.repo, now, queue_runs, args.run_id)) if t]
        return queue_decision(now, args.event, args.run_id, max(last) if last else None,
                              active_runs(daily_runs), active_runs(queue_runs, args.run_id))
    head = gh_head(f"repos/{args.repo}/contents/data/state/discovery_run.json?ref=staging")
    return daily_decision(now, args.event, discovery_at_from_head(head), last_commit_at(commits, DAILY_COMMIT))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["queue", "daily"])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--event", required=True)
    ap.add_argument("--run-id", type=int, default=0)
    args = ap.parse_args(argv)
    try:
        run, reason = decide(args, datetime.now(timezone.utc))
    except Exception as exc:  # fail open: a broken gate must never stop the pipeline
        run, reason = True, f"gate_error_{type(exc).__name__}"
    print(f"run={'true' if run else 'false'}")
    print(f"reason={reason}")


if __name__ == "__main__":
    sys.exit(main())
