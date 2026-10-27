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

from radar_salud.daily_window import eligible_daily_item  # noqa: E402
from radar_salud.pending_queue import PendingQueue  # noqa: E402
from radar_salud.source_health import load_retired_sources  # noqa: E402


def backlog(root: Path = ROOT, days: int = 30) -> dict:
    """Items a batch could process right now (respects retry_at), inside the window."""
    queue = PendingQueue(root / "data/state/pending_queue.json")
    retired = load_retired_sources(root)
    live = [i for _, i in queue.ready() if i.get("source") not in retired and eligible_daily_item(i, days=days)]
    return {"window_days": days, "pending": len(live), "by_source": dict(Counter(i.get("source") for i in live).most_common())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--github-output", action="store_true")
    args = ap.parse_args()
    report = backlog()
    if args.github_output:
        print(f"pending={report['pending']}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
