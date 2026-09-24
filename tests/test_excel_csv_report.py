import csv
import importlib.util
import json
from pathlib import Path


def test_excel_csv_uses_canonical_validation_and_preserves_comparison_interval(tmp_path):
    spec = importlib.util.spec_from_file_location("product_report", Path("scripts/product_report.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "root"
    (root / "data/excel").mkdir(parents=True)
    canonical = {"families": {
        "movilidad": {"status": "validated", "sha256": "a" * 64,
                      "series": [{"period_start": "2025-07", "period_end": "2026-07",
                                  "period_type": "comparison_between_july_cuts"}]},
        "cartera": {"status": "schema_not_validated", "error": "Unknown header", "series": []},
    }}
    (root / "data/excel/validated_series.json").write_text(json.dumps(canonical))
    module.build(root, tmp_path / "out")
    with (tmp_path / "out/excel_diagnostics.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = {row["family"]: row for row in csv.DictReader(stream)}
    assert rows["movilidad"]["period_start"] == "2025-07"
    assert rows["movilidad"]["period_end"] == "2026-07"
    assert rows["movilidad"]["period_type"] == "comparison_between_july_cuts"
    assert rows["cartera"]["error"] == "Unknown header"


def test_queue_exists_but_no_successful_discovery_does_not_claim_live_measurement(tmp_path):
    spec = importlib.util.spec_from_file_location("product_report", Path("scripts/product_report.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "root"
    (root / "data/state").mkdir(parents=True)
    (root / "data/state/pending_queue.json").write_text("{}")
    (root / "data/state/discovery_run.json").write_text('{"successful_sources":0,"failed_sources":7}')
    report=module.build(root,tmp_path / "out")
    assert report["queue_status"] == "awaiting_successful_global_discovery"
    assert report["coverage_live"] is None and report["queue"] is None


def test_old_discovery_and_renamed_statistics_source_do_not_inflate_coverage(tmp_path):
    spec = importlib.util.spec_from_file_location("product_report", Path("scripts/product_report.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root=tmp_path / "root"
    (root / "data/state").mkdir(parents=True)
    (root / "data/state/pending_queue.json").write_text("{}")
    (root / "data/state/discovery_run.json").write_text('{"at":"2020-01-01T00:00:00+00:00","successful_sources":1}')
    (root / "data/source_health.json").write_text(json.dumps({"sources":{"superintendencia_stats":{"status":"ok"},"superintendencia":{"status":"ok"}}}))
    report=module.build(root,tmp_path / "out")
    assert report["queue_status"]=="awaiting_successful_global_discovery"
    assert list(report["sources"])==["superintendencia"]
