"""Read-only runtime audit of Codex E sources; no analysis API or publication."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from radar_salud.beta_sources import CuratedBetaSourceScout
from radar_salud.occupational_sources import SOURCES
from radar_salud.pending_queue import atomic_json


def audit(root):
    checked = datetime.now(ZoneInfo("America/Santiago"))
    result = {"candidate_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              "checked_at": checked.isoformat(), "sources": {}, "published": 0, "analysis_api_calls": 0,
              "window_start": {str(n): (checked.date() - timedelta(days=n)).isoformat() for n in (30, 90)}}
    for slug in sorted(SOURCES):
        scout = CuratedBetaSourceScout(slug)
        path = root / "data/audits/source_e" / f"{slug}.json"
        manual = json.loads(path.read_text())
        entry = {"listing": scout.cfg["page"], "reconciliation_evidence": str(path.relative_to(root)),
                 "evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                 "samples": manual["samples"], "inventory_complete": False}
        try:
            rows = scout.discover()
            entry.update(technical_status="ok", discovered=len(rows), decisions=scout.decisions)
        except Exception as exc:
            entry.update(technical_status="error", error={"type": type(exc).__name__,
                "code": getattr(exc, "code", type(exc).__name__), "url": getattr(exc, "url", scout.cfg["page"]),
                "message": str(exc)}, decisions=getattr(scout, "decisions", []))
        result["sources"][slug] = entry
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/audits/source_e/runtime.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = audit(root)
    atomic_json(root / args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
