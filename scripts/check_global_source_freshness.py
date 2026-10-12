"""Read-only Global snapshot check. No network, AI, publication or health writes."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from radar_salud.global_source_freshness import assess_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/global_intelligence/source_health.json"))
    parser.add_argument("--now", type=datetime.fromisoformat, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    now = args.now or datetime.now(timezone.utc)
    health = json.loads(args.input.read_text())["sources"]
    report = {
        "mode": "read_only_snapshot_observation",
        "network_requests": 0,
        "paid_ai_calls": 0,
        "publication_count": 0,
        "does_not_satisfy_daily_cycle_or_24h_cadence": True,
        "sources": {key: assess_snapshot(health[key], now) for key in ("who", "paho")},
        "reuters": {"status": "PAUSED_LICENSE", "poll_requested": False},
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        protected = [args.input, Path("data/source_health.json"), Path("web/data/source_health.json"),
                     Path("web/data/product.json")]
        output = args.output.resolve()
        allowed = [Path("work").resolve(), Path("data/audits/global_integration_2026_10_11").resolve()]
        if (any(output == path.resolve() for path in protected)
                or not any(output.is_relative_to(path) for path in allowed)
                or output.exists()):
            raise ValueError("read-only check cannot overwrite canonical Global/source health state")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
