from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any


DEFAULT_OVERRIDES = Path(__file__).resolve().parents[2] / "config" / "editorial_copy_overrides_v1.json"


def signal_fingerprint(signal: dict[str, Any]) -> str:
    stable = {
        "source_url": signal.get("source_url"),
        "event_date": signal.get("event_date"),
        "what_happened": signal.get("what_happened"),
    }
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_overrides(path: Path | str = DEFAULT_OVERRIDES) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def apply_reviewed_copy(
    signals: list[dict[str, Any]], overrides: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    cfg = overrides or load_overrides()
    by_key = {(row["source_url"], row["event_date"]): row for row in cfg.get("items", [])}
    output = []
    for signal in signals:
        row = dict(signal)
        reviewed = by_key.get((row.get("source_url"), row.get("event_date")))
        if reviewed and reviewed.get("signal_fingerprint_sha256") != signal_fingerprint(row):
            reviewed = None
        if reviewed:
            proposed = reviewed.get("proposed") or {}
            mapping = {"title": "title", "summary": "card_what", "why": "card_why"}
            legacy_title = reviewed.get("legacy_title")
            if isinstance(legacy_title, str) and legacy_title.strip():
                # Keep the exact pre-review headline as an independent read-state
                # migration candidate. ``source_title_full`` may legitimately hold
                # a longer source headline and must not be overwritten.
                row["legacy_read_title"] = legacy_title.strip()
            for source_field, signal_field in mapping.items():
                value = proposed.get(source_field)
                if isinstance(value, str) and value.strip():
                    if signal_field == "title" and not row.get("source_title_full"):
                        row["source_title_full"] = legacy_title or row.get("title")
                    row[signal_field] = value.strip()
            row["editorial_review_id"] = cfg["audit_id"]
        output.append(row)
    return output
