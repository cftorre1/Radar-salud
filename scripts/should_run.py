"""Scheduler backstop gate (Dirección 28-oct-2026, "Respaldo en GitHub").

GitHub drops or delays scheduled events under load (27/28-oct: 8 of ~10 hourly
queue slots never fired; the 22:30 Daily Radar fired at 01:31). The workflows add
backstop crons; this gate decides, without checking out the repository, whether a
scheduled run should do the work or exit as a no-op.

Prints ``run=true|false`` and ``reason=...`` for $GITHUB_OUTPUT. Manual and push
runs always run. Errors fail OPEN (``run=true``) for primary crons, i.e. never worse
than having no gate, and fail CLOSED (``run=false``) for the backstop crons in
``BACKSTOP_CRONS``: a broken gate must not turn every backstop into a full run
(~8 extra discoveries/day plus a batch at every :45). The workflow shell wrapper
applies the same rule when this script cannot even be fetched.
Standard library only; GitHub data comes from ``gh api``.

Pinning: the workflows fetch this file from ``$GITHUB_SHA`` (for scheduled runs, the
default-branch commit whose workflow is running), so main's scheduling only executes
the copy reviewed in main's own tree. Update procedure: change it on staging (with
tests), then copy it byte-identical to main in a separate reviewed PR together with
tests/test_should_run.py; never fetch it from a moving branch.

Known, accepted risk: check-then-act race. The gate reads run/commit state and the
writer job starts later; a writer that becomes active in between is not seen. The
``alicanto-staging-writer`` concurrency group still serialises writers, so the worst
case is one redundant batch/discovery, not two concurrent writers.

    python3 should_run.py queue --repo OWNER/NAME --event schedule --run-id 123 --schedule '45 0-9,... * * *'
    python3 should_run.py daily --repo OWNER/NAME --event schedule --run-id 123 --schedule '7 0,12,16,20 * * *'
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
WRITER_GROUP = "alicanto-staging-writer"
# Every workflow (union of staging and main) whose run or job declares ``group: alicanto-staging-writer``.
# tests/test_should_run.py greps .github/workflows/*.yml and fails if a writer is missing here.
WRITER_WORKFLOWS = frozenset({
    "autopilot.yml", "clinic-connectivity-diagnostic.yml", "daily-radar.yml", "df-isolated-audit.yml",
    "import-commander-runtime.yml", "occupational-source-recovery.yml", "queue-hourly.yml",
    "weekly-insight-v2.yml", "weekly-insight.yml",
})
# Backstop cron expressions (github.event.schedule): these fail CLOSED on gate errors.
QUEUE_BACKSTOP_CRON = "45 0-9,11-13,15-17,19-21,23 * * *"
DAILY_BACKSTOP_CRON = "7 0,12,16,20 * * *"
BACKSTOP_CRONS = frozenset({QUEUE_BACKSTOP_CRON, DAILY_BACKSTOP_CRON})


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


def run_workflow_file(run: dict) -> str:
    """Workflow file name of a run (``path`` is ``.github/workflows/x.yml``, sometimes ``...@ref``)."""
    return (run.get("path") or "").split("@", 1)[0].rsplit("/", 1)[-1]


def active_writer_runs(runs: list[dict], exclude_id: int | None = None) -> list[dict]:
    """Active runs (any status in ACTIVE) of any workflow in the writer group, de-duplicated by id."""
    seen, out = set(), []
    for r in active_runs(runs, exclude_id):
        if run_workflow_file(r) in WRITER_WORKFLOWS and r.get("id") not in seen:
            seen.add(r.get("id"))
            out.append(r)
    return out


def discovery_at_from_head(text: str) -> datetime | None:
    """``at`` from the first bytes of data/state/discovery_run.json (17 MB; never download it whole)."""
    m = re.search(r'"at"\s*:\s*"([^"]+)"', text)
    return parse_ts(m.group(1)) if m else None


def queue_decision(now: datetime, event: str, run_id: int, last_batch_at: datetime | None,
                   writers_active: list[dict]) -> tuple[bool, str]:
    """Hourly queue gate. ``last_batch_at``: newest of the last queue commit or the last
    run whose batch job actually executed (empty batches do not commit). ``writers_active``:
    active runs of any WRITER_WORKFLOWS workflow except this run (see active_writer_runs)."""
    if event != "schedule":
        return True, "manual_or_dispatch"
    queue_active = [r for r in writers_active if run_workflow_file(r) == QUEUE_WORKFLOW]
    others = [r for r in writers_active if run_workflow_file(r) != QUEUE_WORKFLOW]
    if others:
        # Daily Radar, weekly insight, import-commander-runtime, manual writers...: entering the group
        # now could replace their pending run (Daily Radar also processes the queue).
        return False, "writer_active_" + run_workflow_file(others[0]).removesuffix(".yml")
    if any(int(r.get("id") or 0) < run_id for r in queue_active):
        return False, "earlier_queue_run_active"
    if last_batch_at and now - last_batch_at < QUEUE_RECENT:
        return False, "queue_batch_recent"
    return True, "no_recent_batch"


def daily_decision(now: datetime, event: str, discovery_at: datetime | None,
                   refresh_commit_at: datetime | None, backstop: bool = False) -> tuple[bool, str]:
    """Daily Radar gate: a scheduled run (primary or backstop) discovers only if no
    discovery has happened since the current slot started. Runs inside the writer
    lock, so a slot's earlier run has already pushed its state. An unreadable
    discovery state is a gate failure: a backstop then stays closed."""
    if event != "schedule":
        return True, "manual_or_push"
    slot = latest_daily_slot(now)
    if discovery_at and discovery_at >= slot:
        return False, "discovery_done_for_slot"
    if refresh_commit_at and refresh_commit_at >= slot:
        return False, "daily_refresh_committed_for_slot"
    if discovery_at is None and backstop:
        return False, "discovery_state_unreadable_backstop"
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


def repo_active_runs(repo: str) -> list[dict]:
    """All active runs in the repository (every workflow), one call per active status."""
    runs: list[dict] = []
    for status in sorted(ACTIVE):
        runs += gh_json(f"repos/{repo}/actions/runs?status={status}&per_page=100").get("workflow_runs", [])
    return runs


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
        last = [t for t in (last_commit_at(commits, QUEUE_COMMIT),
                            recent_queue_batch_at(args.repo, now, queue_runs, args.run_id)) if t]
        return queue_decision(now, args.event, args.run_id, max(last) if last else None,
                              active_writer_runs(repo_active_runs(args.repo), args.run_id))
    head = gh_head(f"repos/{args.repo}/contents/data/state/discovery_run.json?ref=staging")
    return daily_decision(now, args.event, discovery_at_from_head(head), last_commit_at(commits, DAILY_COMMIT),
                          backstop=args.schedule in BACKSTOP_CRONS)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["queue", "daily"])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--event", required=True)
    ap.add_argument("--run-id", type=int, default=0)
    ap.add_argument("--schedule", default="", help="github.event.schedule (cron expression that fired)")
    args = ap.parse_args(argv)
    try:
        run, reason = decide(args, datetime.now(timezone.utc))
    except Exception as exc:
        # Primary crons fail open (a broken gate must never stop the pipeline); backstop crons fail
        # closed (a broken gate must not turn every backstop into an extra full run).
        if args.schedule in BACKSTOP_CRONS:
            run, reason = False, f"gate_error_backstop_{type(exc).__name__}"
        else:
            run, reason = True, f"gate_error_{type(exc).__name__}"
    print(f"run={'true' if run else 'false'}")
    print(f"reason={reason}")


if __name__ == "__main__":
    sys.exit(main())
