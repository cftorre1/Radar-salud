"""Rebuild web/data/global_feed.json from the saved discovery outputs (no network, no AI)."""
import argparse
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from radar_salud.global_daily_feed import export

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(ZoneInfo("America/Santiago")).date())
    args = parser.parse_args()
    payload = export(args.root, args.as_of)
    print(json.dumps({"items": len(payload["items"]), "enabled": payload["enabled"], "freshness": payload["freshness"], "held": payload["held"]}))
