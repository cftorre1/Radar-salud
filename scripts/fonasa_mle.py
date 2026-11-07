"""FONASA Arancel MLE 2026 → code table (Dirección, 6-nov-2026 20:46).

FONASA's site refuses automated downloads (robots.txt 403 to the Actions runner, 6-nov-2026), so Dirección provided the
official "Libro Arancel MLE 2026" PDF. This script reads the text that ``pdftotext -layout`` extracts from it and writes
``data/reference/fonasa_mle_2026.json``: code → description, pabellón category, nivel 1/2/3 values (TOTAL and the
beneficiary's part). The PDF itself is not committed; its SHA-256, size and page count go in the receipt.

Row layout (one line per code in ``-layout`` text): ``GG SS PPP  [COD PAB]  DENOMINACIÓN  [EQ] [ANES TOTAL BENEF]
N1 TOTAL BENEF [N2 TOTAL BENEF N3 TOTAL BENEF]``. The numeric block is separated from the description by 3 or more
spaces. A row is accepted only when its amounts parse as 2 (single level) or 6 values (three levels, nondecreasing
totals), optionally preceded by EQ and, for surgical codes, the anaesthesia pair; anything else is counted and skipped,
never guessed. Pabellón charges (derecho de pabellón) are billed in the SIS file as codes 0000001–0000014; their values
come from the book's last page ("CÓDIGOS Y VALORES PABELLÓN").

Usage: python scripts/fonasa_mle.py --pdf <file> --layout-text <pdftotext -layout output> --pages N --out <json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SOURCE = "Libro Arancel MLE 2026, FONASA, provided by Dirección 6-nov-2026"
URL = "https://www.fonasa.gob.cl/wp-content/uploads/sites/3/2026/03/1-Libro-Arancel-MLE-2026.pdf"
ROW = re.compile(r"^(\d{2}) (\d{2}) (\d{3})(?:\s{2,}(\d{1,2})(?=\s{2,}\S))?\s+(.+?)\s{3,}((?:\d[\d.]*)(?:\s+\d[\d.]*)*)\s*$")
PAB = re.compile(r"^\s*(\d{1,2})\s*=\s*(\d+)\s*$")


def amount(tok: str) -> int | None:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})*", tok):
        return int(tok.replace(".", ""))
    return None


def split_amounts(tokens: list[str], has_pab: bool) -> tuple[int | None, list[int]] | None:
    """(EQ, amounts) for the numeric block, or None. EQ only with a pabellón category; amounts end with 2 or 6."""
    eq = None
    toks = list(tokens)
    # EQ (team size, one digit) leads the block when the block has an odd length (3, 7 or 9 tokens); with a pabellón
    # category it is required.
    if toks and re.fullmatch(r"\d", toks[0]) and (has_pab or len(toks) in (3, 7, 9)):
        eq = int(toks.pop(0))
    elif has_pab:
        return None
    vals = [amount(t) for t in toks]
    if any(v is None for v in vals):
        return None
    for k in (6, 2):
        extra = len(vals) - k
        if extra in (0, 2) and not (extra == 2 and k == 2 and not has_pab):
            lv = vals[extra:]
            tot = lv[0::2]
            if all(b <= t for t, b in zip(lv[0::2], lv[1::2])) and tot == sorted(tot) and tot[0] > 0:
                return eq, vals
    return None


def parse_layout(text: str) -> tuple[dict, dict, dict]:
    codes: dict[str, dict] = {}
    stats: Counter = Counter()
    conflicts: set[str] = set()
    for line in text.splitlines():
        m = ROW.match(line)
        if not m:
            if re.match(r"^\d{2} \d{2} \d{3}\b", line):
                stats["filas_codigo_sin_montos"] += 1
            continue
        code = m.group(1) + m.group(2) + m.group(3)
        pab = int(m.group(4)) if m.group(4) and 1 <= int(m.group(4)) <= 14 else None
        toks = m.group(6).split()
        got = split_amounts(toks, pab is not None)
        desc = m.group(5)
        if got is None and pab is not None:  # a 1-2 digit token that was the start of the description
            pab, desc = None, f"{m.group(4)} {desc}"
            got = split_amounts(toks, False)
        if got is None:
            stats["filas_no_leidas"] += 1
            continue
        eq, vals = got
        lv = vals[2:] if len(vals) in (4, 8) else vals
        rec = {"descripcion": re.sub(r"\s+", " ", desc).strip(), "cod_pabellon": pab, "equipo": eq,
               "nivel1_total": lv[0], "nivel1_benef": lv[1]}
        if len(lv) == 6:
            rec.update(nivel2_total=lv[2], nivel2_benef=lv[3], nivel3_total=lv[4], nivel3_benef=lv[5])
        if len(vals) in (4, 8):
            rec.update(anestesia_total=vals[0], anestesia_benef=vals[1])
        if code in codes and codes[code] != rec:
            conflicts.add(code)
        codes[code] = rec
        stats["filas_leidas"] += 1
        stats["niveles_3" if len(lv) == 6 else "nivel_unico"] += 1
    for c in conflicts:
        codes.pop(c)
    stats["codigos_en_conflicto"] = len(conflicts)
    pab_vals: dict[str, int] = {}
    if "VALORES PABELL" in text:
        for line in text[text.rindex("VALORES PABELL"):].splitlines():
            m = PAB.match(line)
            if m and 1 <= int(m.group(1)) <= 14:
                pab_vals[f"{int(m.group(1)):07d}"] = int(m.group(2))
    return codes, pab_vals, dict(stats)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--layout-text", type=Path, required=True)
    ap.add_argument("--pages", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    data = a.pdf.read_bytes()
    codes, pab, stats = parse_layout(a.layout_text.read_text(encoding="utf-8"))
    for code, v in pab.items():
        codes[code] = {"descripcion": f"DERECHO DE PABELLÓN, CATEGORÍA {int(code)}", "cod_pabellon": int(code),
                       "equipo": None, "nivel1_total": v, "nivel1_benef": None, "pabellon": True}
    receipt = {"source": SOURCE, "url": URL, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
               "pages": a.pages, "codes": len(codes), "pabellon_categories": len(pab), "extractor": "pdftotext -layout",
               "parse": stats, "built_at": datetime.now(timezone.utc).isoformat(),
               "valor_referencia": "nivel1_total (pesos, nivel 1, TOTAL); códigos de nivel único: su único valor"}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"receipt": receipt, "codigos": dict(sorted(codes.items()))}, ensure_ascii=False,
                                separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
