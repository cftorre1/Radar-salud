from __future__ import annotations

import argparse
import json
from pathlib import Path

from radar_salud.editorial_copy import apply_reviewed_copy, signal_fingerprint


def build(audit: dict, snapshot: dict, previous: dict | None = None) -> dict:
    by_key = {(row.get("source_url"), row.get("event_date")): row for row in snapshot.get("signals", [])}
    previous_by_key = {
        (row.get("source_url"), row.get("event_date")): row
        for row in (previous or {}).get("items", [])
    }
    items = []
    for row in audit["items"]:
        if not str(row.get("id", "")).startswith("https://"):
            continue
        proposed = row.get("proposed") or {}
        if not any(isinstance(value, str) and value.strip() for value in proposed.values()):
            continue
        signal = by_key.get((row["id"], row.get("event_date")))
        if signal is None:
            raise ValueError(f"audited signal missing from snapshot: {row['id']}")
        prior = previous_by_key.get((row["id"], row.get("event_date"))) or {}
        legacy_title = prior.get("legacy_title")
        if proposed.get("title") and not legacy_title and signal.get("title") != proposed.get("title"):
            legacy_title = signal.get("title")
        item = {
            "source_url": row["id"],
            "event_date": row.get("event_date"),
            "signal_fingerprint_sha256": signal_fingerprint(signal),
            "verdict": row.get("verdict"),
            "proposed": proposed,
        }
        if legacy_title:
            item["legacy_title"] = legacy_title
        items.append(item)
    return {
        "audit_id": audit["audit_id"],
        "policy": "Only non-empty, human-reviewed proposed fields replace visible copy.",
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", default="data/editorial_audit_2026_09_26.json")
    parser.add_argument("--output", default="config/editorial_copy_overrides_v1.json")
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    snapshot_path = Path(args.snapshot or "web/data/radar_today.json")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    output_path = Path(args.output)
    previous = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else None
    overrides = build(audit, snapshot, previous)
    output_path.write_text(
        json.dumps(overrides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.snapshot:
        path = snapshot_path
        snapshot["signals"] = apply_reviewed_copy(snapshot["signals"], overrides)
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
