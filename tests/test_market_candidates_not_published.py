import json
from pathlib import Path

import scripts.export_web_snapshot as exporter

MARKET = {"dipres_health_budget", "cmf_health_ecosystem", "sis_isapre_universe"}


def _is_market(row):
    return (row.get("source_slug") in MARKET or str(row.get("candidate_id") or "").startswith(("dipres:", "cmf:"))
            or row.get("source_slug_market") in MARKET)


def test_market_candidates_never_reach_the_public_feed():
    """Freshness policy exempts these sources because they publish nothing (PR #43)."""
    history = json.loads(Path("data/history/superintendencia_signals.json").read_text())["signals"]
    curated = exporter.curate(history, resolve_external=False)
    assert not [r for r in curated if _is_market(r)]
    published = json.loads(Path("web/data/radar_today.json").read_text())["signals"]
    assert not [r for r in published if _is_market(r)]


def test_no_pipeline_script_routes_market_candidates_into_history():
    for path in list(Path("scripts").glob("*.py")) + list(Path("src/radar_salud").glob("*.py")):
        if path.name.startswith("market") or path.name in {"review_market_source_coverage.py", "validate_market_source_runtime.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "market_intelligence" not in text or "superintendencia_signals" not in text, path
