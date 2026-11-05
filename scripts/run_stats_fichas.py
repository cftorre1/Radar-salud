"""Build the live statistics fichas (Dirección 28-oct-2026; see data/stats_fichas/POLICY.md).

PASS (deterministic verification + reconciliation) replaces the live ficha of the family and archives
the previous one. HOLD never publishes. The Lectura Alicanto is the only model-written block: it uses
the shared AI budget (ai_budget, paced_budget_usd, openai_runtime weekly cap) and is omitted when there
is no budget, no key or the verifier fails.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from radar_salud import (dipres_refresh, stats_capture, stats_capture_fefi, stats_ficha_f1, stats_ficha_f2, stats_ficha_f4,  # noqa: E402
                         stats_ficha_f6, stats_ficha_f7, stats_ficha_f12, stats_ficha_f13, stats_fichas)

BUILDERS = {"F1": stats_ficha_f1.run, "F2": stats_ficha_f2.run, "F4": stats_ficha_f4.run, "F6": stats_ficha_f6.run,
            "F7": stats_ficha_f7.run, "F12": stats_ficha_f12.run, "F13": stats_ficha_f13.run}
# F12 (Prestaciones bonificadas) and F13 (Licencias médicas), Dirección 5-nov-2026: the builders read only the committed
# aggregates in data/sis_open_data_aggregates/<quarter>/ (written by scripts/aggregate_sis_open_data.py in its own
# GitHub Actions workflow, callable from the daily pipeline); nothing is downloaded here and the Lectura stays off.
# Their first PASS waits for Dirección's review (families.F12/F13.first_pass_requires_review), like F4 and F7.
CAPTURED = {"F4", "F6"}  # families whose documents are captured by stats_capture (F1 reads the market lane's capture)
FEFI_CAPTURED = {"F2"}  # FEFI workbooks (stats_capture_fefi): the latest release, then the same quarter one year earlier
# F2 is active since 2-nov-2026 and runs in the daily default like F1/F4/F6. Its capture is bounded (≤ 2 downloads or
# re-checks per run, SIS fetcher limits, step deadline). Its Lectura stays off, so no paid call is made, until Dirección
# sets families.F2.lectura_enabled, whatever OPENAI_API_KEY says (stats_ficha_f2.run).
# F7 (DIPRES Partida 16): its builder reads only data/market/dipres_health_budget.json (no download, Lectura off); its
# first PASS waits for Dirección's review (families.F7.first_pass_requires_review), like F4. Since 4-nov-2026 the lane
# itself is refreshed here by dipres_refresh (Director): once per Chile day, new monthly execution reports only, bounded
# by DIPRES_BUDGET_S and skipped when the step has already used DIPRES_SKIP_AFTER_S (the builds must still run before
# the workflow's 15-minute step timeout). A DIPRES failure is reported and never blocks any family.
DIPRES_CAPTURED = {"F7"}
DIPRES_BUDGET_S = dipres_refresh.TIME_BUDGET_S
DIPRES_SKIP_AFTER_S = 10 * 60


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--as-of", type=date.fromisoformat, default=None)
    ap.add_argument("--no-llm", action="store_true", help="Skip the Lectura Alicanto model call")
    ap.add_argument("--family", action="append", choices=sorted(BUILDERS), help="Default: every active family")
    ap.add_argument("--no-capture", action="store_true", help="Do not download new F2/F4/F6 documents nor check DIPRES (offline runs, tests)")
    args = ap.parse_args(argv)
    step_started = time.monotonic()
    from radar_salud.weekly_freshness import chile_today
    today = args.as_of or chile_today()
    registry = stats_fichas.load_registry()
    families = args.family or [f for f, c in registry["families"].items() if c.get("status") == "active" and f in BUILDERS]
    llm = not args.no_llm and bool(os.getenv("OPENAI_API_KEY"))
    summary = {}
    if not args.no_capture and CAPTURED & set(families):
        try:  # bounded: each listed SIS document is downloaded once; failures are recorded and retried later
            summary["capture"] = stats_capture.capture(args.root)
        except Exception as exc:  # a capture failure never blocks the other families
            summary["capture"] = {"error": f"{type(exc).__name__}:{exc}"[:200]}
    if not args.no_capture and FEFI_CAPTURED & set(families):
        try:
            summary["capture_fefi"] = stats_capture_fefi.capture_fefi(args.root)
        except Exception as exc:
            summary["capture_fefi"] = {"error": f"{type(exc).__name__}:{exc}"[:200]}
    if not args.no_capture and DIPRES_CAPTURED & set(families):
        elapsed = time.monotonic() - step_started
        if elapsed >= DIPRES_SKIP_AFTER_S:
            summary["capture_dipres"] = {"status": "skipped_step_time", "elapsed_s": round(elapsed)}
        else:
            try:
                summary["capture_dipres"] = dipres_refresh.refresh(
                    args.root, today=today, registry=registry,
                    time_budget_s=min(DIPRES_BUDGET_S, DIPRES_SKIP_AFTER_S - elapsed))
            except Exception as exc:  # never blocks a family: the lane stays as it was
                summary["capture_dipres"] = {"status": "error", "error": f"{type(exc).__name__}:{exc}"[:200]}
    for fam in families:
        # One family's crash never stops the others (review 2-nov): it is reported and nothing is published for it.
        try:
            result = BUILDERS[fam](args.root, today=today, registry=registry, llm=llm)
        except Exception as exc:
            summary[fam] = {"status": "error", "errors": [f"{type(exc).__name__}:{exc}"[:200]]}
            continue
        written = stats_fichas.publish(result, args.root)
        if result.get("release_holds"):
            written["release_holds"] = stats_fichas.publish_release_holds(result, args.root)
        lect = ((result.get("ficha") or {}).get("lectura") or {})
        summary[fam] = {"status": result["status"], "period": result.get("period"),
                        "triggers": (result.get("decision") or {}).get("triggers"),
                        "errors": result.get("errors"), "lectura": lect.get("status"),
                        "cost_usd": lect.get("cost_usd"), **written}
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
