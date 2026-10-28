#!/usr/bin/env python3
"""Offline report: which paywalled items get an authorized corroboration (Dirección 28-oct-2026).

Reads only repository files (no network, no model). Writes a reviewable audit:
  data/audits/paywall_corroboration_<date>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from radar_salud import entity_watch  # noqa: E402
from radar_salud.paywall_corroboration import (CorpusIndex, Registry, build_corpus, corroborate, is_thin,  # noqa: E402
                                               load_registry, paywalled_item, render_what)
from radar_salud.source_rights import load_fingerprints  # noqa: E402

QUEUE_STATUSES = {"published", "archived", "deferred", "superseded", "retry"}


def paywalled_items(root: Path) -> list[dict]:
    items: dict[str, dict] = {}
    for rel in ("web/data/radar_today.json", "data/history/superintendencia_signals.json"):
        for row in json.loads((root / rel).read_text(encoding="utf-8")).get("signals") or []:
            it = paywalled_item(row)
            if it and it["url"] not in items:
                items[it["url"]] = {**it, "origin": rel}
    queue = json.loads((root / "data/state/pending_queue.json").read_text(encoding="utf-8"))
    for q in queue.values():
        if q.get("status") not in QUEUE_STATUSES:
            continue
        it = paywalled_item({}, raw=q.get("raw") or {})
        if it and it["url"] not in items and it["title"]:
            items[it["url"]] = {**it, "origin": f"data/state/pending_queue.json:{q.get('status')}"}
    return list(items.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--output", default="data/audits/paywall_corroboration_2026_10_28.json")
    args = ap.parse_args()
    root = Path(args.root)
    registry = Registry(load_registry(root))
    corpus = build_corpus(root, registry)
    index = CorpusIndex(corpus, registry, fingerprints=load_fingerprints(root), catalog=entity_watch.load_catalog())
    rows, counts = [], Counter()
    for it in paywalled_items(root):
        thin = is_thin(it, registry)
        tier = "title_only" if len(it["teaser"]) < 60 else ("thin" if thin else "lead_ok")
        block = corroborate(it, index)
        counts[(tier, block["status"])] += 1
        rows.append({"title": it["title"], "url": it["url"], "event_date": str(it["date"]), "tier": tier,
                     "origin": it["origin"], "status": block["status"],
                     "what_rendered": render_what(block["what"]) if block["what"] else None,
                     "related_sources": block["related_sources"], "candidates": block.get("candidates", [])})
    rows.sort(key=lambda r: (r["status"] != "corroborated", r["event_date"]), reverse=False)
    summary = {f"{t}/{s}": n for (t, s), n in sorted(counts.items())}
    out = {"generated_for": "Dirección 28-oct-2026 15:16 (corroboración de prensa con muro de pago)",
           "inputs": ["web/data/radar_today.json", "data/history/superintendencia_signals.json",
                      "data/state/pending_queue.json", "data/market/cmf_events.json"],
           "corpus_documents": len(corpus),
           "corpus_by_source": dict(Counter(d.source["id"] for d in corpus)),
           "corpus_excluded": dict(Counter(d.excluded for d in corpus if d.excluded)),
           "paywalled_items": len(rows), "summary": summary,
           "note": "Sólo se listan piezas con corroboración o caso limítrofe; el resto queda título + bajada.",
           "items": [r for r in rows if r["status"] != "none"]}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("corpus_documents", "corpus_by_source", "paywalled_items", "summary")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
