"""Autopilot V1 watchdog: durable anti-silence state for Alicanto.

This script does not modify product code. It classifies whether approved work is
moving, blocked, or requires escalation so Pelé/Paolo can resume without hidden
chat context.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ACTIVE = {"approved", "in_progress"}
DONE = {"validated", "completed", "cancelled"}


def load(path: str | Path, fallback):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else fallback


def executable_tasks(queue):
    tasks = queue.get("tasks") or []
    status = {t.get("id"): t.get("status") for t in tasks}
    result = []
    for task in tasks:
        if task.get("status") not in ACTIVE:
            continue
        if task.get("blocked_by"):
            continue
        deps = task.get("depends_on") or []
        if all(status.get(dep) in DONE for dep in deps):
            result.append(task)
    priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(result, key=lambda t: (priority.get(t.get("priority"), 9), t.get("id", "")))


def classify(queue, control_state, now=None, stale_minutes=60):
    now = now or datetime.now(timezone.utc)
    executable = executable_tasks(queue)
    last_progress = control_state.get("last_progress_at")
    age = None
    if last_progress:
        try:
            stamp = datetime.fromisoformat(last_progress.replace("Z", "+00:00"))
            age = max(0.0, (now - stamp).total_seconds() / 60)
        except ValueError:
            age = None

    blockers = control_state.get("blockers") or []
    human_required = [b for b in blockers if b.get("requires_human") is True]
    stalled = bool(executable and age is not None and age > stale_minutes)

    if human_required:
        state = "human_escalation_required"
    elif stalled:
        state = "recovery_required"
    elif executable:
        state = "work_available"
    else:
        state = "idle_no_executable_work"

    return {
        "generated_at": now.isoformat(),
        "state": state,
        "stale_minutes": stale_minutes,
        "minutes_since_progress": None if age is None else round(age, 1),
        "next_task": executable[0].get("id") if executable else None,
        "executable_tasks": [t.get("id") for t in executable],
        "human_blockers": human_required,
        "all_blockers": blockers,
        "required_behavior": {
            "work_available": "Pele/Paolo should continue with next_task without waiting for Toba.",
            "recovery_required": "Diagnose latest failure, attempt bounded repair, then continue or record blocker.",
            "human_escalation_required": "Escalate with evidence/options/recommendation, while continuing independent work.",
            "idle_no_executable_work": "Reconcile backlog/PMO and record that no approved executable work remains."
        }[state]
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", default="config/orchestrator_queue.json")
    parser.add_argument("--state", default="data/autopilot/v1_control_state.json")
    parser.add_argument("--output", default="artifacts/autopilot_v1_watchdog.json")
    parser.add_argument("--stale-minutes", type=int, default=60)
    args = parser.parse_args()

    queue = load(args.queue, {"tasks": []})
    state = load(args.state, {})
    result = classify(queue, state, stale_minutes=args.stale_minutes)

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))

    if result["state"] in {"recovery_required", "human_escalation_required"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
