"""Hourly/daily step: official-text evidence + verified automatic normative records (Dirección 9-nov-2026).

Non-blocking by design: always exits 0; failures are printed. Writes the run summary (detection→publication
latency median/max, cost per act) to stdout and, in GitHub Actions, to $GITHUB_STEP_SUMMARY.
Budget: every model call goes through openai_runtime (USD 10/month paced cap and weekly guard, unchanged).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    try:
        from radar_salud.normative_autorecord import format_summary, run_step
        history = json.loads((ROOT / "data/history/superintendencia_signals.json").read_text(encoding="utf-8"))
        summary = run_step(ROOT, history.get("signals", []))
        text = format_summary(summary)
        print(text)
        print(json.dumps(summary, ensure_ascii=False))
        if os.getenv("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        if os.getenv("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
                fh.write(f"written={summary['records_written']}\n")
    except Exception as exc:  # never fails the run
        print("normative_autorecord step skipped:", type(exc).__name__, str(exc)[:120])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
