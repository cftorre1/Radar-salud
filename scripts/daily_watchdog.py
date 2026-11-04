"""Daily Radar watchdog (.github/workflows/daily-radar-watchdog.yml). Standard library + ``gh api``.

Two independent outputs, printed for $GITHUB_OUTPUT:

* ``stale=true|false``: the last *successful* Daily Radar build (job ``build`` concluded success) is older
  than STALE_AFTER (the longest normal gap is the 12 h night gap between the 22:30 and 10:30 UTC slots).
  The workflow then fails with an ``::error`` annotation, so GitHub notifies (failed scheduled run) and the
  outage is visible in Actions instead of going unnoticed (30-oct..1-nov: ~55 h without a publication).
* ``dispatch=true|false``: GitHub's scheduler dropped both the primary and the backstop cron of the current
  slot. The workflow dispatches daily-radar.yml (workflow_dispatch via GITHUB_TOKEN does start a run) only when
  the repository variable DAILY_WATCHDOG_DISPATCH is 'true' (Dirección authorization); otherwise it only reports.

Dispatch rules (all must hold), so the watchdog never adds a second discovery per slot:
  - at least GRACE has passed since the slot (the backstop cron sits at +97 min);
  - no discovery and no refresh commit since the slot (same signals as scripts/should_run.py);
  - no Daily Radar run is active, and no writer-group run is waiting (a new pending run in the
    concurrency group would replace a pending one, e.g. a weekly insight);
  - no Daily Radar run created since the slot failed (a deterministic failure needs a fix, not a retry)
    and none was already dispatched for this slot.
Errors never dispatch; they mark the watchdog itself as failed (reason=watchdog_error_*).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import should_run as sr  # noqa: E402  (fetched next to this file at the same commit)

GRACE = timedelta(minutes=120)
STALE_AFTER = timedelta(hours=14)
WAITING = {"queued", "waiting", "pending", "requested"}


def last_successful_build_at(runs: list[dict], jobs_of) -> datetime | None:
    """Completion time of the newest run whose ``build`` job succeeded (gate-skipped runs also conclude
    'success' but did not publish). ``jobs_of(run_id)`` returns the run's jobs; at most 10 lookups."""
    candidates = [r for r in runs if r.get("conclusion") == "success"]
    for r in sorted(candidates, key=lambda r: r.get("created_at") or "", reverse=True)[:10]:
        for j in jobs_of(r["id"]):
            if j.get("name") == "build" and j.get("conclusion") == "success":
                return sr.parse_ts(j.get("completed_at"))
    return None


def dispatch_decision(now: datetime, discovery_at: datetime | None, refresh_at: datetime | None,
                      daily_runs: list[dict], writer_runs: list[dict]) -> tuple[bool, str]:
    slot = sr.latest_daily_slot(now)
    if now - slot < GRACE:
        return False, "slot_grace"
    if discovery_at and discovery_at >= slot:
        return False, "discovery_done_for_slot"
    if refresh_at and refresh_at >= slot:
        return False, "daily_refresh_committed_for_slot"
    if sr.active_runs(daily_runs):
        return False, "daily_run_active"
    if any(r.get("status") in WAITING for r in writer_runs):
        return False, "writer_run_waiting"
    since_slot = [r for r in daily_runs if (sr.parse_ts(r.get("created_at")) or slot - timedelta(1)) >= slot]
    if any(r.get("conclusion") == "failure" for r in since_slot):
        return False, "daily_failed_for_slot"
    if any(r.get("event") == "workflow_dispatch" for r in since_slot):
        return False, "already_dispatched_for_slot"
    # A cancelled run may have been building (someone stopped it on purpose): never second-guess it (review of #137).
    if any(r.get("conclusion") == "cancelled" for r in since_slot):
        return False, "daily_cancelled_for_slot"
    return True, "slot_missed"


def stale_decision(now: datetime, last_success_at: datetime | None) -> tuple[bool, str]:
    if last_success_at is None:
        return True, "no_successful_build_in_recent_runs"
    age = now - last_success_at
    hours = f"{age.total_seconds() / 3600:.1f}h"
    return (age > STALE_AFTER), f"last_success_{hours}_ago"


def evaluate(repo: str, now: datetime) -> dict:
    daily_runs = sr.workflow_runs(repo, sr.DAILY_WORKFLOW)
    commits = sr.gh_json(f"repos/{repo}/commits?sha=staging&per_page=100")
    head = sr.gh_head(f"repos/{repo}/contents/data/state/discovery_run.json?ref=staging")
    writers = sr.active_writer_runs(sr.repo_active_runs(repo))
    last_ok = last_successful_build_at(
        daily_runs, lambda rid: sr.gh_json(f"repos/{repo}/actions/runs/{rid}/jobs").get("jobs", []))
    dispatch, dreason = dispatch_decision(now, sr.discovery_at_from_head(head),
                                          sr.last_commit_at(commits, sr.DAILY_COMMIT), daily_runs, writers)
    stale, sreason = stale_decision(now, last_ok)
    return dict(dispatch=dispatch, dispatch_reason=dreason, stale=stale, stale_reason=sreason)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args(argv)
    try:
        out = evaluate(args.repo, datetime.now(timezone.utc))
    except Exception as exc:
        out = dict(dispatch=False, dispatch_reason=f"watchdog_error_{type(exc).__name__}",
                   stale=False, stale_reason=f"watchdog_error_{type(exc).__name__}")
    for key in ("dispatch", "dispatch_reason", "stale", "stale_reason"):
        value = out[key]
        print(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
