"""Create an auditable, deterministic insight report from validated workbook totals."""
import json
from pathlib import Path

from radar_salud.isapre_insights import derive


def main():
    source = Path("data/excel/validated_series.json")
    report = derive(json.loads(source.read_text(encoding="utf-8")))
    if report["status"] != "validated":
        raise SystemExit("No insights published: series or denominators are not validated")
    target = Path("data/excel/insights_v1.json")
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{target}: {len(report['insights'])} validated deterministic insights")


if __name__ == "__main__":
    main()
