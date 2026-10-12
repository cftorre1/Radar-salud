"""A promoted source belongs to the daily queue, not a second beta writer."""
import json
from datetime import datetime, timezone


def core_handoff(root, slug):
    config = root / "config/sources.json"
    if not config.exists() or slug not in {item["slug"] for item in json.loads(config.read_text())}:
        return None
    def read(path):
        return json.loads(path.read_text()) if path.exists() else {}
    run = read(root / "data/state/discovery_run.json")
    health = read(root / "data/source_health.json").get("sources", {}).get(slug, {})
    discovery = run.get("sources", {}).get(slug)
    try:
        polled = datetime.fromisoformat(run["at"].replace("Z", "+00:00"))
        checked = datetime.fromisoformat(health["checked_at"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - polled).total_seconds()
        current = polled.tzinfo is not None and checked.tzinfo is not None and 0 <= age <= 3600 and checked >= polled
    except (KeyError, ValueError, TypeError):
        current = False
    dates = [item["publication_date"] for item in run.get("source_details", {}).get(slug, [])
             if item.get("status") == "discovered" and item.get("publication_date")]
    return dict(validation_mode="core_handoff", runtime="daily_core", checked_at=run.get("at"),
                discovered=discovery.get("discovered", 0) if discovery and current else 0,
                published=health.get("published") if discovery and current else None,
                technical_status=discovery.get("technical_status", "error") if discovery and current else "error",
                error=discovery.get("error_type") if discovery and current else "core_runtime_not_current",
                newest_event_date=max(dates, default=None) if current else None)
