"""Ficha-vs-Insight contract check for a weekly Insight anchored on a stats ficha (Dirección 2-nov-2026).

Editorial sessions (the Insights written by hand) must run this before committing an anchored Insight:

  python scripts/run_weekly_insight_a.py --offline --as-of <monday>          # writes the brief
  python scripts/check_weekly_insight_contract.py \\
      --brief data/weekly_insight/candidates/<monday>-stats-brief.json --write  # checks editorial_approved.json

  python scripts/check_weekly_insight_contract.py --gate                      # what CI checks (also a test)

--write stores data/weekly_insight/contract_checks/<insight id>.json (brief id, check result, Insight
sha256, source sha). Commit it together with the Insight and the brief; only a PASS record clears the
gate, and any later edit of the Insight invalidates it. No model, no network.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from radar_salud import weekly_insight_stats_anchor as sa

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", type=Path, help="stats brief written by run_weekly_insight_a.py --offline")
    parser.add_argument("--insight", type=Path, default=ROOT / "data/weekly_insight/editorial_approved.json",
                        help="file holding {weekly_insight: ...} (default: editorial_approved.json)")
    parser.add_argument("--write", action="store_true", help="write the contract-check record")
    parser.add_argument("--gate", action="store_true", help="check every committed Insight (CI gate)")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.gate:
        errors = sa.contract_gate(root)
        print(json.dumps({"gate": "PASS" if not errors else "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 1
    if not args.brief:
        parser.error("--brief is required unless --gate")
    brief_path = args.brief if args.brief.is_absolute() else (Path.cwd() / args.brief)
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    payload = json.loads(args.insight.read_text(encoding="utf-8"))
    weekly = payload.get("weekly_insight") if isinstance(payload.get("weekly_insight"), dict) else payload
    if args.write:
        out = sa.write_contract_record(root, weekly, brief, brief_path.resolve())
    else:
        out = sa.check_against_brief(weekly, brief)
        out = {"brief_id": brief.get("brief_id"), "insight_id": weekly.get("id"), "check": out}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if (out.get("check") or {}).get("verdict") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
