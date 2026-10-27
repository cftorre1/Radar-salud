"""Pending items inside the daily window (the number Dirección tracks: 27-oct-2026).

Items older than the window are archived by the engine and do not count.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_salud.daily_window import eligible_daily_item, requested_window_days  # noqa: E402
from radar_salud.source_health import load_retired_sources  # noqa: E402


def backlog(root: Path = ROOT, days: int | None = None) -> dict:
    days = days or requested_window_days()
    items = json.loads((root / "data/state/pending_queue.json").read_text(encoding="utf-8"))
    retired = load_retired_sources(root)
    live = [i for i in items.values() if i.get("status") in ("pending", "retry", "processing")
            and i.get("source") not in retired and eligible_daily_item(i, days=days)]
    return {"window_days": days, "pending": len(live), "by_source": dict(Counter(i.get("source") for i in live).most_common())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--github-output", action="store_true")
    args = ap.parse_args()
    report = backlog(days=30 if args.github_output else None)
    if args.github_output:
        print(f"pending={report['pending']}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
