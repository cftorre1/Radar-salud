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
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from radar_salud import stats_ficha_f1, stats_fichas  # noqa: E402

BUILDERS = {"F1": stats_ficha_f1.run}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--as-of", type=date.fromisoformat, default=None)
    ap.add_argument("--no-llm", action="store_true", help="Skip the Lectura Alicanto model call")
    ap.add_argument("--family", action="append", choices=sorted(BUILDERS), help="Default: every active family")
    args = ap.parse_args(argv)
    from radar_salud.weekly_freshness import chile_today
    today = args.as_of or chile_today()
    registry = stats_fichas.load_registry()
    families = args.family or [f for f, c in registry["families"].items() if c.get("status") == "active" and f in BUILDERS]
    llm = not args.no_llm and bool(os.getenv("OPENAI_API_KEY"))
    summary = {}
    for fam in families:
        result = BUILDERS[fam](args.root, today=today, registry=registry, llm=llm)
        written = stats_fichas.publish(result, args.root)
        lect = ((result.get("ficha") or {}).get("lectura") or {})
        summary[fam] = {"status": result["status"], "period": result.get("period"),
                        "triggers": (result.get("decision") or {}).get("triggers"),
                        "errors": result.get("errors"), "lectura": lect.get("status"),
                        "cost_usd": lect.get("cost_usd"), **written}
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
