"""Print mode=discover when the last discovery is older than the limit (self-healing
when a scheduled Daily Radar was cancelled or skipped), else mode=process."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LIMIT = timedelta(hours=float(sys.argv[1]) if len(sys.argv) > 1 else 6)
p = Path(__file__).resolve().parents[1] / "data/state/discovery_run.json"
try:
    at = datetime.fromisoformat(json.loads(p.read_text(encoding="utf-8"))["at"])
    stale = datetime.now(timezone.utc) - at > LIMIT
except (OSError, ValueError, KeyError, TypeError):
    stale = True
print("mode=" + ("discover" if stale else "process"))
