import json
from datetime import datetime, timezone

import src.radar_salud.ai_pricing as pricing

NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)


def _ledger(root, rows, usage=()):
    (root / "data/ai_usage").mkdir(parents=True)
    (root / "data/state").mkdir(parents=True)
    (root / "data/ai_usage/responses.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    (root / "data/state/model_usage.json").write_text(json.dumps({"calls": list(usage)}), encoding="utf-8")


def test_spend_counts_only_this_month_across_both_ledgers(tmp_path):
    _ledger(tmp_path, [
        {"at": "2026-10-02T00:00:00Z", "model": "gpt-5.6-luna", "input_tokens": 1_000_000, "output_tokens": 0},
        {"at": "2026-10-03T00:00:00Z", "model": "gpt-5.6-terra", "input_tokens": 0, "output_tokens": 100_000},
        {"at": "2026-09-30T00:00:00Z", "model": "gpt-6-astra", "input_tokens": 9_000_000, "output_tokens": 0},
    ], usage=[{"at": "2026-10-05T00:00:00Z", "estimated_cost_usd": 0.5}])
    # 0.20 (luna in) + 1.20 (terra out) + 0.50 (feature ledger); September excluded
    assert pricing.month_spend_usd(tmp_path, NOW) == 1.9


def test_budget_blocks_at_ten_dollars_and_unknown_models_are_priced_high(tmp_path, monkeypatch):
    _ledger(tmp_path, [{"at": "2026-10-02T00:00:00Z", "model": "nuevo-modelo", "input_tokens": 1_000_000, "output_tokens": 0}])
    assert pricing.month_spend_usd(tmp_path, NOW) == 10.0
    monkeypatch.delenv("RADAR_MONTHLY_USD", raising=False)
    assert not pricing.within_budget(tmp_path, NOW)
    monkeypatch.setenv("RADAR_MONTHLY_USD", "25")
    assert pricing.within_budget(tmp_path, NOW)


def test_daily_workflow_uses_usd_budget_and_batches():
    text = open(".github/workflows/daily-radar.yml", encoding="utf-8").read()
    assert "RADAR_MONTHLY_USD: 10" in text and "RADAR_PROCESSING_SECONDS: 3600" in text
    assert "inputs.processing_limit || 200" in text and "<= 30" not in text
