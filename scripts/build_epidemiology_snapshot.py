from __future__ import annotations

import json
from pathlib import Path

from radar_salud.respiratory_pressure import build_respiratory_pressure


def main() -> None:
    source = Path("data/epidemiology/respiratory_pressure_2026.json")
    output = Path("web/data/epidemiology.json")
    dataset = json.loads(source.read_text(encoding="utf-8"))
    signal = build_respiratory_pressure(dataset)
    if signal is None:
        raise SystemExit("respiratory pressure dataset failed validation")
    output.write_text(json.dumps({"status": "provider_ready_not_promoted", "signals": [signal]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
