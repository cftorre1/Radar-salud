"""External AI health alert (9-nov-2026).

Since 7-nov-2026 every model call failed with RateLimitError and the verified normative
records (normative_autorecord) stopped silently: only "Sin lectura editorial" cards reached
the feed. This reads the usage ledger (data/ai_usage/responses.jsonl), never calls a model,
and reports when >=95% of at least 5 calls in the last 24 h failed. It never blocks the run.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

LEDGER = "data/ai_usage/responses.jsonl"
WINDOW_HOURS = 24
MIN_CALLS = 5
FAILURE_RATIO = 0.95


def _at(row: dict[str, Any]) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(str(row.get("at") or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def load_rows(root: Path) -> list[dict[str, Any]]:
    path = Path(root) / LEDGER
    rows = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and _at(row):
            rows.append(row)
    return rows


def failure_alert(rows: Iterable[dict[str, Any]], now: datetime | None = None, *, window_hours: int = WINDOW_HOURS,
                  min_calls: int = MIN_CALLS, ratio: float = FAILURE_RATIO) -> dict[str, Any] | None:
    """Alert payload when the external model stopped answering, else None."""
    now = now or datetime.now(timezone.utc)
    rows = sorted((r for r in rows if _at(r) and _at(r) <= now), key=_at)
    recent = [r for r in rows if _at(r) >= now - timedelta(hours=window_hours)]
    failed = [r for r in recent if r.get("success") is not True]
    if len(recent) < min_calls or len(failed) < ratio * len(recent):
        return None
    errors = Counter(str(r.get("error_type") or "error_desconocido") for r in failed)
    last_ok = max((_at(r) for r in rows if r.get("success") is True), default=None)
    # Failures since the last success; if a success closed the window, the first failure in it.
    since = min((_at(r) for r in rows if r.get("success") is not True and (last_ok is None or _at(r) > last_ok)),
                default=min(_at(r) for r in failed))
    main_error = ", ".join(name for name, _ in errors.most_common(2))
    message = (f"IA externa sin respuesta: {len(failed)}/{len(recent)} llamadas fallaron ({main_error}) "
               f"desde {since.date().isoformat()}; registros normativos verificados en espera")
    return {"status": "alert", "message": message, "window_hours": window_hours, "calls": len(recent),
            "failed": len(failed), "errors": dict(errors), "failing_since": since.isoformat(),
            "last_success_at": last_ok.isoformat() if last_ok else None, "checked_at": now.isoformat(),
            "blocks_pipeline": False}


def record(root: Path, alert: dict[str, Any] | None, now: datetime | None = None) -> None:
    """Keep the state in data/source_health.json (admin telemetry) next to source rows."""
    from .pending_queue import atomic_json
    path = Path(root) / "data/source_health.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"sources": {}}
    except (OSError, ValueError):
        return  # never rewrite an unreadable health file from here
    now = now or datetime.now(timezone.utc)
    data["ai_provider"] = alert or {"status": "ok", "checked_at": now.isoformat(), "blocks_pipeline": False}
    atomic_json(path, data)


def report(root: Path, now: datetime | None = None, *, write: bool = True) -> dict[str, Any] | None:
    alert = failure_alert(load_rows(root), now)
    if write:
        record(root, alert, now)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if alert:
        print(f"::warning title=IA externa sin respuesta::{alert['message']}")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(f"\n### ALERTA: {alert['message']}\n\nNo bloquea la publicación determinística; "
                         "requiere acción de Dirección en la cuenta del proveedor.\n")
    else:
        print("IA externa: sin alerta de fallas en las últimas 24 h")
    return alert


def main(argv: list[str] | None = None) -> int:
    root = Path(argv[0]) if argv else Path(".")
    try:
        report(root)
    except Exception as exc:  # an alert must never break the daily run
        print(f"::warning title=IA externa::no se pudo evaluar ({type(exc).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
