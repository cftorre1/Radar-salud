from datetime import datetime, timezone

from scripts.autopilot_v1_watchdog import classify, executable_tasks


def queue():
    return {
        "tasks": [
            {"id": "done", "status": "validated", "priority": "critical"},
            {"id": "next", "status": "approved", "priority": "critical", "depends_on": ["done"]},
            {"id": "later", "status": "approved", "priority": "high"},
            {"id": "blocked", "status": "approved", "priority": "critical", "blocked_by": ["external"]},
        ]
    }


def test_selects_highest_priority_executable_task():
    assert [x["id"] for x in executable_tasks(queue())] == ["next", "later"]


def test_stale_work_requires_recovery_not_silence():
    result = classify(
        queue(),
        {"last_progress_at": "2026-09-27T18:00:00+00:00", "blockers": []},
        now=datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc),
        stale_minutes=60,
    )
    assert result["state"] == "recovery_required"
    assert result["next_task"] == "next"


def test_human_blocker_is_explicit():
    result = classify(
        queue(),
        {
            "last_progress_at": "2026-09-27T19:45:00+00:00",
            "blockers": [{"id": "credentials", "requires_human": True, "reason": "authorization"}],
        },
        now=datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc),
    )
    assert result["state"] == "human_escalation_required"
    assert result["human_blockers"][0]["id"] == "credentials"
