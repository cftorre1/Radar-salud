"""Publication-safe GES aggregates for F14 from the historical backfill output (``ges_gpp_<q>.json``).

Usage: ``python scripts/ges_f14_publicable.py --source <dir with <q>/ges_gpp_<q>.json and receipts_<q>.json>
[--source-ref <branch@sha>] [--out data/sis_open_data_history]``.

For each quarter it writes ``<out>/<q>/ges_gpp_publicable_<q>.json`` (``radar_salud.ges_privacy.sanitize``: only the
four tables F14 shows, ≥ 10 cases and ≥ 3 providers per row, complementary suppression across tables) and copies the
quarter's receipt (URL, bytes, SHA-256 and row count of the SIS ZIP; no row-level data). The source file itself is not
copied: it stays where the backfill wrote it, and the output names its SHA-256. Nothing is downloaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_salud import ges_privacy as gp  # noqa: E402

REF = ROOT / "data" / "reference" / "ges_problemas_ds29_2025.json"
OUT = ROOT / "data" / "sis_open_data_history"
QUARTER = re.compile(r"^20\d{2}t[1-4]$")


def convert(src_dir: Path, q: str, ref: dict, source_ref: str | None) -> tuple[dict, dict, dict]:
    raw = (src_dir / q / f"ges_gpp_{q}.json").read_bytes()
    src = json.loads(raw.decode("utf-8"))
    rec = json.loads((src_dir / q / f"receipts_{q}.json").read_text(encoding="utf-8"))
    if src.get("periodo") != q or rec.get("periodo") != q:
        raise ValueError(f"period_mismatch:{q}")
    doc, rep = gp.sanitize(src, ref)
    arch = rec.get("archivo") or {}
    out = {"periodo": q, "script_version": src.get("script_version"), "version_publicable": gp.PUBLIC_VERSION,
           "sha256_zip": arch.get("sha256"), "filas_zip": (arch.get("parse") or {}).get("rows_ok"),
           "fuente_agregada": {"archivo": f"ges_gpp_{q}.json", "sha256": hashlib.sha256(raw).hexdigest(),
                               "bytes": len(raw), "referencia": source_ref,
                               "celdas_suprimidas_en_fuente": {t: (src.get(t) or {}).get("celdas_suprimidas")
                                                               for t in gp.TABLES}},
           "definicion": src.get("definicion"),
           "regla_publicacion": (f"Filas con ≥ {gp.MIN_CASES} casos distintos y ≥ {gp.MIN_PROVIDERS} prestadores distintos; "
                                 "supresión complementaria entre tablas (familia ← problemas, familia ← Isapres, "
                                 "problema ← regiones, total ← familias); un problema oculto oculta sus regiones. "
                                 "Solo cuatro tablas; problema × Isapre, problema × Isapre × región e intervención se "
                                 "omiten."),
           "supresion": rep, "fuente_nombres": src.get("fuente_nombres"), **doc}
    return out, rec, rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--source-ref", default=None)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    ref = json.loads(REF.read_text(encoding="utf-8"))
    summary = {}
    for qdir in sorted(p for p in a.source.iterdir() if p.is_dir() and QUARTER.match(p.name)):
        q = qdir.name
        if not (qdir / f"ges_gpp_{q}.json").exists():
            continue
        out, rec, rep = convert(a.source, q, ref, a.source_ref)
        dst = a.out / q
        dst.mkdir(parents=True, exist_ok=True)
        (dst / f"ges_gpp_publicable_{q}.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n",
                                                           encoding="utf-8")
        shutil.copyfile(a.source / q / f"receipts_{q}.json", dst / f"receipts_{q}.json")  # byte for byte
        summary[q] = rep
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
