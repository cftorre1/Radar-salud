"""Monthly AI spend in USD, estimated from recorded tokens (Dirección, 27-oct-2026).

The real limit is money, not call counts: at most RADAR_MONTHLY_USD (default 10)
per calendar month across every AI feature. Both ledgers are read: per-call
token records (data/ai_usage/responses.jsonl) and feature calls with an
estimated cost (data/state/model_usage.json).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Standard API input/output rates per 1M tokens (same table as openai_runtime).
MODEL_PRICES_PER_MILLION = {
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-6-astra": (10.00, 50.00),
}
# Unknown models are priced at the most expensive known rate (fail-safe).
_FALLBACK = max(MODEL_PRICES_PER_MILLION.values())


def monthly_budget_usd() -> float:
    try:
        return float(os.getenv("RADAR_MONTHLY_USD", "10"))
    except ValueError:
        return 10.0


def estimate(model: str | None, input_tokens: int, output_tokens: int) -> float:
    a, b = MODEL_PRICES_PER_MILLION.get(str(model or ""), _FALLBACK)
    return input_tokens * a / 1_000_000 + output_tokens * b / 1_000_000


def month_spend_usd(root: Path, now: datetime | None = None) -> float:
    month = (now or datetime.now(timezone.utc)).strftime("%Y-%m")
    total = 0.0
    ledger = Path(root) / "data/ai_usage/responses.jsonl"
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not str(row.get("at") or "").startswith(month):
                continue
            cost = row.get("cost_usd")
            total += float(cost) if isinstance(cost, (int, float)) else estimate(
                row.get("model"), int(row.get("input_tokens") or 0), int(row.get("output_tokens") or 0))
    usage = Path(root) / "data/state/model_usage.json"
    if usage.exists():
        try:
            calls = json.loads(usage.read_text(encoding="utf-8")).get("calls") or []
        except ValueError:
            calls = []
        for row in calls:
            if str(row.get("at") or "").startswith(month):
                total += float(row.get("estimated_cost_usd") or 0)
    return round(total, 4)


def paced_budget_usd(now: datetime | None = None) -> float:
    """Budget available so far this month: spread evenly over the days, plus USD 1 of slack.

    With hourly runs a burst could otherwise spend the whole month in a day or two and
    leave the rest of the month unprocessed (reviewer, 27-oct-2026)."""
    import calendar
    now = now or datetime.now(timezone.utc)
    days = calendar.monthrange(now.year, now.month)[1]
    cap = monthly_budget_usd()
    return min(cap, cap * now.day / days + 1.0)


def within_budget(root: Path, now: datetime | None = None) -> bool:
    return month_spend_usd(root, now) < paced_budget_usd(now)
