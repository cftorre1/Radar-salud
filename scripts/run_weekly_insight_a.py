"""Monday weekly insight (format A). See src/radar_salud/weekly_insight_a.py.

  python scripts/run_weekly_insight_a.py              # live: draft + verify + review + publish/candidate
  python scripts/run_weekly_insight_a.py --offline    # no AI: topic ranking, evidence and cost estimate only
  python scripts/run_weekly_insight_a.py --as-of 2026-11-02 --offline
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from radar_salud.weekly_freshness import (chile_today, freshness_gate, monday_anchor,
                                          reconcile_weekly_publication, reviewed_weekly)
from radar_salud.weekly_insight_a import (build_evidence, estimate_run_cost, publish, run_weekly_a,
                                          select_topic)

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_public(result: dict, approved: dict, as_of: date) -> dict:
    """latest.json + free_value.json always reflect the reviewed publication (or nothing)."""
    attempt = {k: result.get(k) for k in ("status", "anchor_date", "topic_ranking", "verification", "review",
                                          "total_cost_usd", "error")}
    out = reconcile_weekly_publication(attempt, approved, as_of)
    prior = (approved or {}).get("weekly_insight") or {}
    if out.get("status") != "pass" and prior:
        out["last_approved"] = {"id": prior.get("id"), "expires_on": prior.get("expires_on"),
                                "freshness_gate": freshness_gate(prior, as_of), "state": "expired_or_invalid"}
    (ROOT / "data/weekly_insight/latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    free_path = ROOT / "web/data/free_value.json"
    free = read(free_path, {})
    free["weekly_insight"] = out.get("weekly_insight")
    policy = free.setdefault("selection_policy", {})
    policy["weekly_insight_status"] = "published_editorial_reviewed" if out.get("weekly_insight") else "hidden_fail_closed"
    policy["freshness_gate"] = freshness_gate(out.get("weekly_insight"), as_of)
    policy["weekly_schedule"] = {"anchor": "monday", "anchor_date": monday_anchor(as_of).isoformat()}
    free_path.write_text(json.dumps(free, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    parser.add_argument("--offline", action="store_true", help="No model call: ranking, evidence and cost estimate")
    parser.add_argument("--force", action="store_true", help="Regenerate even if this Monday is already published")
    args = parser.parse_args()
    as_of = args.as_of or chile_today()
    anchor = monday_anchor(as_of)
    signals = read(ROOT / "data/history/superintendencia_signals.json", {}).get("signals") or []
    approved_path = ROOT / "data/weekly_insight/editorial_approved.json"
    approved = read(approved_path, {})
    current = reviewed_weekly(approved, as_of)
    if args.offline:
        prev = (approved or {}).get("weekly_insight") or {}
        ranked = select_topic(signals, anchor, recent_urls=set(prev.get("source_refs") or []),
                              recent_text=" ".join(str(prev.get(k) or "") for k in ("headline", "summary")))
        evidence = build_evidence(ranked[0]) if ranked else None
        record = {"status": "offline_evidence_only", "anchor_date": anchor.isoformat(),
                  "topic_ranking": [{"score": r["score"], "title": r["signal"].get("title"), "url": r["signal"].get("source_url"),
                                     "event_date": r["signal"].get("event_date"), "related": [x.get("title") for x in r["related"]]}
                                    for r in ranked[:5]],
                  "evidence": evidence, "cost_estimate": estimate_run_cost(evidence, anchor=anchor) if evidence else None}
        out = ROOT / "data/weekly_insight/candidates" / f"{anchor.isoformat()}-evidence.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": record["status"], "anchor": anchor.isoformat(), "file": str(out.relative_to(ROOT)),
                          "top": record["topic_ranking"][:1], "cost": record["cost_estimate"]}, ensure_ascii=False))
        return 0
    if current and current.get("anchor_kind") == "monday" and current.get("freshness_anchor_date") == anchor.isoformat() and not args.force:
        print(json.dumps({"status": "already_published_for_monday", "id": current.get("id")}, ensure_ascii=False))
        write_public({"status": "skipped_already_published"}, approved, as_of)
        return 0
    result = run_weekly_a(signals, as_of=as_of, previous=approved)
    written = publish(result)
    write_public(result, read(approved_path, {}), as_of)
    print(json.dumps({"status": result.get("status"), "anchor": result.get("anchor_date"), **written,
                      "errors": (result.get("verification") or {}).get("errors"),
                      "review": (result.get("review") or {}).get("verdict"), "cost_usd": result.get("total_cost_usd")},
                     ensure_ascii=False))
    # A FAIL is a normal, fail-closed outcome (candidate saved); only crashes fail the job.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
