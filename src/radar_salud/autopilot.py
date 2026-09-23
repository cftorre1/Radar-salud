"""Bounded state machine and independent feedback consolidation.

CI serializes all writers and commits reservations before doing work. The ledger
counts failed/abandoned attempts, including a re-run of the same workflow.
"""
import hashlib
from datetime import datetime, timezone
from .pending_queue import atomic_json

CRITICAL = {"tests", "editorial", "data", "desktop", "mobile", "reviewer"}

def reserve(ledger, candidate_sha, builder, now=None):
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(timezone.utc).date().isoformat()
    entries = ledger.setdefault("iterations", [])
    if sum(x["day"] == day for x in entries) >= 5:
        raise RuntimeError("Daily limit of 5 attempts reached")
    entry = dict(id=f"{day}-{sum(x['day']==day for x in entries)+1}",
        day=day, started_at=now.isoformat(), candidate_sha=candidate_sha,
        builder=builder, state="reserved", checks={}, feedback=[])
    entries.append(entry)
    return entry

def consolidate(reports):
    out = {}
    for report in reports:
        for finding in report.get("findings", []):
            identity = "|".join(str(finding.get(k, "")) for k in ("category", "path", "code"))
            key = hashlib.sha256(identity.encode()).hexdigest()[:16]
            if key not in out:
                out[key] = dict(finding, id=key, reviewers=[])
            out[key]["reviewers"].append(report["reviewer"])
            if finding.get("severity") == "critical":
                out[key]["severity"] = "critical"
    return list(out.values())

def approve(entry, reports, checks):
    if not reports or any(r.get("reviewer") == entry["builder"] for r in reports):
        raise ValueError("Reviewer must be independent of Builder")
    if any(r.get("candidate_sha") != entry["candidate_sha"] for r in reports):
        raise ValueError("Review must match candidate SHA")
    entry["feedback"] = consolidate(reports)
    entry["checks"] = checks
    passed = all(checks.get(k) is True for k in CRITICAL)
    passed = passed and not any(x.get("severity") == "critical" for x in entry["feedback"])
    entry["state"] = "ready" if passed else "blocked"
    return passed

def save_ledger(path, ledger):
    atomic_json(path, ledger)
