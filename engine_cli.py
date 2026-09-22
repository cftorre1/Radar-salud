from __future__ import annotations

import argparse
import json
from pathlib import Path

from .scouts import SeenStore, SuperintendenciaStatsScout, fetch_html, save_raw_items
from .sources import load_sources, source_index
from .superintendencia_pipeline import process_superintendencia_detail
from .distribution import UserPlan, choose_distribution
from .history import load_history, merge_history, save_history


def main():
    parser = argparse.ArgumentParser(description="Radar Salud Engine V0")
    parser.add_argument("--limit", type=int, default=5, help="max new detail pages to process")
    parser.add_argument("--reset-state", action="store_true", help="ignore previous seen-state for a clean run")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    cfg = source_index(load_sources(root / "config" / "sources.json"))["superintendencia_salud"]
    state_path = root / "data" / "state" / "superintendencia_seen.json"
    inbox_path = root / "data" / "inbox" / "superintendencia_new.json"
    signals_path = root / "data" / "outbox" / "superintendencia_signals.json"
    history_path = root / "data" / "history" / "superintendencia_signals.json"

    if args.reset_state and state_path.exists():
        state_path.unlink()

    scout = SuperintendenciaStatsScout()
    store = SeenStore(state_path)
    items = scout.discover_new(store)
    save_raw_items(items, inbox_path)

    signals = []
    errors = []
    for raw in items[: args.limit]:
        try:
            html = fetch_html(raw.url)
            signal = process_superintendencia_detail(raw, html, cfg)
            free_dist = choose_distribution(signal.radar_score, signal.confidence_score, UserPlan("free"), signal.watch_tags, ())
            pro_dist = choose_distribution(signal.radar_score, signal.confidence_score, UserPlan("pro"), signal.watch_tags, ())
            row = signal.to_dict()
            row["distribution_free"] = free_dist
            row["distribution_pro"] = pro_dist
            signals.append(row)
        except Exception as exc:  # keep batch resilient; production will add structured logging
            errors.append({"url": raw.url, "error": f"{type(exc).__name__}: {exc}"})

    signals_path.parent.mkdir(parents=True, exist_ok=True)
    signals_path.write_text(json.dumps({"signals": signals, "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")

    history = merge_history(load_history(history_path), signals)
    save_history(history_path, history)

    print("RADAR ENGINE V0 — Superintendencia")
    print(f"New discovered: {len(items)}")
    print(f"Processed:      {len(signals)}")
    print(f"Errors:         {len(errors)}")
    print(f"Output:         {signals_path}")
    print(f"History:        {history_path} ({len(history)} signals)")
    for s in signals:
        print(f"[{s['radar_score']}] {s['title']}")
        print(f"    confidence={s['confidence_score']} validation={s['validation_status']}")
        print(f"    FREE={s['distribution_free']} PRO={s['distribution_pro']}")


if __name__ == "__main__":
    main()
