#!/usr/bin/env python3
"""Offline: what FNE and Congreso add to paywall corroboration (Dirección 28-oct-2026 17:08).

1. Current data: the repository corpus as it is (no FNE/Congreso piece has been
   captured yet, so this measures the matcher change only).
2. Verification set: real FNE records (title + date read on fne.gob.cl, see
   tests/fixtures/fne/verified_records_20261028.json) processed by the real
   scout code, added to the same corpus. Congress has no real record here (the
   Senado service by date could not be read from this environment).

No network, no model. Writes data/audits/fne_congreso_corroboration_2026_10_28.json.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_salud import entity_watch, fne_sources  # noqa: E402
from radar_salud.paywall_corroboration import (CorpusIndex, Registry, build_corpus, corroborate, is_thin,  # noqa: E402
                                               load_registry, render_what)
from radar_salud.source_rights import load_fingerprints  # noqa: E402


def _report_module():
    spec = importlib.util.spec_from_file_location("pcr", ROOT / "scripts/paywall_corroboration_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def verified_fne_rows(path):
    cfg = {"slug": fne_sources.SLUG, "name": fne_sources.SOURCE_NAME, "base_confidence": 100,
           "default_category": "Mercado", "force_category": True}
    rows = []
    for rec in json.loads(Path(path).read_text(encoding="utf-8"))["records"]:
        day = date.fromisoformat(rec["date"])
        for raw in fne_sources.items_from_rows([rec], listing=fne_sources.LISTING, today=day, window_days=1):
            rows.append({**fne_sources.process_fne(raw, cfg), "source_slug": fne_sources.SLUG})
    return rows


def run(root, items, registry, extra_rows=()):
    base = [json.loads((root / rel).read_text(encoding="utf-8")).get("signals") or []
            for rel in ("data/history/superintendencia_signals.json", "web/data/radar_today.json")]
    corpus = build_corpus(root, registry, signal_sets=base + [list(extra_rows)])
    index = CorpusIndex(corpus, registry, fingerprints=load_fingerprints(root), catalog=entity_watch.load_catalog())
    out = {}
    for it in items:
        out[it["url"]] = corroborate(it, index)
    return corpus, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="data/audits/fne_congreso_corroboration_2026_10_28.json")
    args = ap.parse_args()
    registry = Registry(load_registry(ROOT))
    items = _report_module().paywalled_items(ROOT)
    thin = [it for it in items if is_thin(it, registry)]
    corpus, before = run(ROOT, thin, registry)
    fne_rows = verified_fne_rows(ROOT / "tests/fixtures/fne/verified_records_20261028.json")
    corpus2, after = run(ROOT, thin, registry, fne_rows)
    count = lambda res: dict(Counter(b["status"] for b in res.values()))
    new = []
    for it in thin:
        a, b = before[it["url"]], after[it["url"]]
        if a["status"] != b["status"] or a["related_sources"] != b["related_sources"]:
            new.append({"title": it["title"], "url": it["url"], "event_date": str(it["date"]),
                        "before": a["status"], "after": b["status"],
                        "what_rendered": render_what(b["what"]) if b["what"] else None,
                        "related_sources": b["related_sources"], "candidates": b.get("candidates", [])})
    out = {"generated_for": "Dirección 28-oct-2026 17:08 ('Avanza con FNE y Congreso')",
           "thin_paywalled_items": len(thin),
           "current_data": {"corpus_documents": len(corpus),
                            "corpus_by_source": dict(Counter(d.source["id"] for d in corpus)),
                            "status": count(before),
                            "note": "Sin piezas FNE ni Congreso en el corpus: el colector diario aún no corre."},
           "with_verified_fne_records": {"records": len(fne_rows), "corpus_documents": len(corpus2),
                                         "status": count(after),
                                         "note": "Conjunto de verificación: 4 noticias reales de fne.gob.cl (título y fecha). No es corpus productivo."},
           "congress": "Sin registro real: tramitacion.php?fecha= no se pudo leer desde este entorno; la cobertura de proyectos de ley se medirá tras la primera corrida diaria.",
           "changed_items": new}
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "changed_items"}, ensure_ascii=False, indent=1))
    for row in new:
        print(row["event_date"], row["before"], "->", row["after"], "|", row["title"][:110])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
