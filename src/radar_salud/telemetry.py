"""Append-only API usage; no prompts, API keys or document text are logged."""
import json
from datetime import datetime, timezone
from .paths import project_root

def record_response(kind, model, response, success):
    usage = getattr(response, "usage", None)
    details = getattr(usage, "input_tokens_details", None)
    row = {
        "at": datetime.now(timezone.utc).isoformat(), "kind": kind,
        "model": model, "response_id": getattr(response, "id", None),
        "success": bool(success),
        "input_tokens": getattr(usage, "input_tokens", None),
        "cached_input_tokens": getattr(details, "cached_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
        "cost_usd": None, "cost_status": "pricing_not_configured",
    }
    # Rates are deliberately not invented or changed by Autopilot.
    path = project_root() / "data/ai_usage/responses.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
