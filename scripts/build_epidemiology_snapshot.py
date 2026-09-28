from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from radar_salud.respiratory_pressure import build_respiratory_pressure


def main() -> None:
    source = Path("data/epidemiology/respiratory_pressure_2026.json")
    output = Path("web/data/epidemiology.json")
    dataset = json.loads(source.read_text(encoding="utf-8"))
    signal = build_respiratory_pressure(dataset)
    if signal is None:
        output.write_text(json.dumps({"status": "no_material_weekly_change", "signals": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    if (date.today() - date.fromisoformat(signal["event_date"])).days > 14:
        output.write_text(json.dumps({"status": "stale_not_promoted", "signals": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    output.write_text(json.dumps({"status": "promoted_material_weekly_change", "signals": [signal]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
