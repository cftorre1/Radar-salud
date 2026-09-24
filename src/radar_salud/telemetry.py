"""Append-only API usage; no prompts, API keys or document text are logged."""
import json
from datetime import datetime, timezone
from .paths import project_root

def record_response(kind, model, response, success, error_type=None, *, feature=None, output_id=None, run_id=None,
                    publishable=None, incremental_quality_points=None):
    trace = (feature, output_id, run_id)
    if any(value is not None for value in trace) and not all(value is not None for value in trace):
        raise ValueError("feature telemetry requires feature, output_id and run_id together")
    usage = getattr(response, "usage", None)
    details = getattr(usage, "input_tokens_details", None)
    row = {
        "at": datetime.now(timezone.utc).isoformat(), "kind": kind,
        "model": getattr(response, "model", None) or model,
        "requested_model": model, "response_id": getattr(response, "id", None),
        "success": bool(success),
        "error_type": error_type,
        "input_tokens": getattr(usage, "input_tokens", None),
        "cached_input_tokens": getattr(details, "cached_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
        "cost_usd": None, "cost_status": "pricing_not_configured",
        "feature": feature, "output_id": output_id, "run_id": run_id,
        "publishable": publishable, "incremental_quality_points": incremental_quality_points,
    }
    # Rates are deliberately not invented or changed by Autopilot.
    path = project_root() / "data/ai_usage/responses.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
