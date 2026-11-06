"""Shared reader for the SIS open-data aggregates behind fichas F12 (Prestaciones bonificadas) and F13 (Licencias).

Input: ``data/sis_open_data_aggregates/<quarter>/`` only, written by ``scripts/aggregate_sis_open_data.py`` in GitHub
Actions (Dirección 5-nov-2026). Each quarter folder holds ``receipts_<q>.json`` (URL, bytes, SHA-256 and parsed rows of
every downloaded ZIP) and aggregate JSON files that name the SHA-256 of the ZIP they come from. Nothing is downloaded
here and no row-level data or identifier exists in these files.

``load_quarter`` reconciles one quarter before any figure is read (any failure → the ficha HOLDs):

- the receipt has the dataset for that quarter, from ``https://datos.superdesalud.gob.cl``, with a SHA-256, at most
  1 GiB, rows parsed and at most 0,1 % malformed rows;
- every aggregate file names the same quarter, the same aggregation script version and the receipt's SHA-256, and the
  row count it aggregated equals the receipt's;
- the quarter declared inside the file (column ``periodo``) is the folder's quarter;
- the Arancel Isapre descriptions come from the Arancel file of the same receipt.

Isapre names come from ``data/entities/isapres.json`` (``official_code`` → ``commercial_name``): a code without a name
HOLDs, a code is never shown. Providers exist only as pseudonymous aggregates: their names are never shown.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from . import stats_fichas as sf

AGG_ROOT = Path("data/sis_open_data_aggregates")
SCRIPT_VERSION = "sis_open_data_agg_v3"  # mirrors scripts/aggregate_sis_open_data.py SCRIPT_VERSION
FILE_HOST = "datos.superdesalud.gob.cl"
MAX_FILE_BYTES = 1 << 30
MAX_MALFORMED_SHARE = 0.001
QUARTER = re.compile(r"^(20\d{2})t([1-4])$")
FIRST_REVIEW_HOLD = "HOLD_FIRST_REVIEW:awaiting_first_review"
QUARTER_MONTHS = {1: ("enero", "marzo"), 2: ("abril", "junio"), 3: ("julio", "septiembre"), 4: ("octubre", "diciembre")}
ORDINAL_Q = {1: "1.er", 2: "2.º", 3: "3.er", 4: "4.º"}
# SIS region codes (1–16; 0 = not classified). Short labels (≤ 18 characters, chart rule).
REGIONS = {"1": "Tarapacá", "2": "Antofagasta", "3": "Atacama", "4": "Coquimbo", "5": "Valparaíso", "6": "O'Higgins",
           "7": "Maule", "8": "Biobío", "9": "La Araucanía", "10": "Los Lagos", "11": "Aysén", "12": "Magallanes",
           "13": "Metropolitana", "14": "Los Ríos", "15": "Arica y Parinacota", "16": "Ñuble", "0": "Sin región"}

DATASET_FILES = {
    "Prestaciones Bonificadas": ("prestaciones_{q}_resumen.json", "prestaciones_{q}_precios_fonasa_region.json",
                                 "prestaciones_{q}_indice_isapre_mismo_prestador.json", "prestaciones_{q}_top_codigos.json"),
    "Licencias Medicas": ("licencias_{q}.json",),
}


def load_json(path: Path) -> dict | None:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def quarter_parts(q: str) -> tuple[int, int]:
    m = QUARTER.match(str(q or ""))
    if not m:
        raise ValueError(f"invalid_quarter:{q}")
    return int(m.group(1)), int(m.group(2))


def previous_quarter(q: str) -> str:
    y, n = quarter_parts(q)
    return f"{y - 1}t4" if n == 1 else f"{y}t{n - 1}"


def next_quarter(q: str) -> str:
    y, n = quarter_parts(q)
    return f"{y + 1}t1" if n == 4 else f"{y}t{n + 1}"


def period_of(q: str) -> str:
    """The ficha period of a quarter: its last month ('2026t2' → '2026-06')."""
    y, n = quarter_parts(q)
    return f"{y}-{n * 3:02d}"


def quarter_label(q: str) -> str:
    """'2026t2' → 'abril–junio 2026'."""
    y, n = quarter_parts(q)
    a, b = QUARTER_MONTHS[n]
    return f"{a}–{b} {y}"


def quarter_short(q: str) -> str:
    """'2026t2' → 'abr–jun 2026' (Datos page)."""
    y, n = quarter_parts(q)
    a, b = QUARTER_MONTHS[n]
    return f"{a[:3]}–{b[:3]} {y}"


def quarter_tag(q: str) -> str:
    """'2026t1' → '1.er trim. 2026' (comparison lines)."""
    y, n = quarter_parts(q)
    return f"{ORDINAL_Q[n]} trim. {y}"


def quarters(root: Path) -> list[str]:
    """Quarter folders that carry a receipt, oldest first."""
    base = Path(root) / AGG_ROOT
    out = [p.name for p in base.glob("*") if p.is_dir() and QUARTER.match(p.name) and (p / f"receipts_{p.name}.json").exists()]
    return sorted(out, key=quarter_parts)


def isapre_names(root: Path) -> dict[str, str]:
    d = load_json(Path(root) / "data/entities/isapres.json") or {}
    return {str(e.get("official_code")): str(e.get("commercial_name")) for e in d.get("entities") or []
            if e.get("official_code") is not None and e.get("commercial_name")}


def isapre_types(root: Path) -> dict[str, str]:
    """official_code → 'open' / 'closed' (data/entities/isapres.json, isapre_type)."""
    d = load_json(Path(root) / "data/entities/isapres.json") or {}
    return {str(e.get("official_code")): str(e.get("isapre_type")) for e in d.get("entities") or []
            if e.get("official_code") is not None and e.get("isapre_type")}


def region_name(code: str) -> str | None:
    return REGIONS.get(str(code))


def receipt_failures(rec: dict | None, dataset: str, q: str) -> tuple[dict | None, list[str]]:
    """The receipt entry of one dataset and quarter, and why it cannot back a figure."""
    if not rec:
        return None, [f"receipt_missing:{q}"]
    f: list[str] = []
    if rec.get("script_version") != SCRIPT_VERSION:
        f.append(f"receipt_script_version:{q}:{rec.get('script_version')}")
    hits = [x for x in rec.get("files") or [] if x.get("dataset") == dataset and x.get("period") == q]
    if len(hits) != 1:
        return None, f + [f"receipt_file_not_unique:{dataset}:{q}:{len(hits)}"]
    x = hits[0]
    tag = f"{dataset}:{q}"
    url = str(x.get("url") or "")
    p = urlsplit(url)
    if p.scheme != "https" or p.hostname != FILE_HOST:
        f.append(f"source_not_sis_https:{tag}")
    if x.get("error"):
        f.append(f"download_error:{tag}:{x.get('error')}")
    if not sf.HEX64.fullmatch(str(x.get("sha256") or "")):
        f.append(f"source_without_hash:{tag}")
    b = x.get("bytes")
    if not isinstance(b, int) or b <= 0 or b > MAX_FILE_BYTES:
        f.append(f"bytes_out_of_range:{tag}")
    parse = x.get("parse") or {}
    ok, bad = parse.get("rows_ok"), parse.get("rows_malformed")
    if dataset != "Arancel Isapre":
        if not isinstance(ok, int) or ok <= 0 or not isinstance(bad, int):
            f.append(f"rows_not_parsed:{tag}")
        elif bad > MAX_MALFORMED_SHARE * (ok + bad):
            f.append(f"malformed_rows_over_0.1pct:{tag}:{bad}")
    return x, f


def load_quarter(root: Path, q: str, dataset: str) -> tuple[dict, list[str]]:
    """{'receipt': entry, 'files': {name: json}, 'arancel': entry|None} and the reconciliation failures."""
    folder = Path(root) / AGG_ROOT / q
    rec = load_json(folder / f"receipts_{q}.json")
    entry, failures = receipt_failures(rec, dataset, q)
    files: dict[str, dict] = {}
    for tpl in DATASET_FILES[dataset]:
        name = tpl.format(q=q)
        d = load_json(folder / name)
        if d is None:
            failures.append(f"aggregate_missing:{name}")
            continue
        files[name] = d
        if entry is None:
            continue
        if d.get("periodo") != q:
            failures.append(f"aggregate_period_mismatch:{name}:{d.get('periodo')}")
        if d.get("script_version") != SCRIPT_VERSION:
            failures.append(f"aggregate_script_version:{name}:{d.get('script_version')}")
        if d.get("sha256_archivo") != entry.get("sha256"):
            failures.append(f"aggregate_hash_mismatch:{name}")
        if d.get("filas") != (entry.get("parse") or {}).get("rows_ok"):
            failures.append(f"aggregate_rows_mismatch:{name}")
    arancel = None
    if dataset == "Prestaciones Bonificadas" and entry is not None:
        res = files.get(f"prestaciones_{q}_resumen.json") or {}
        periods = res.get("periodos_en_archivo") or {}
        if set(periods) != {q}:
            failures.append(f"file_period_not_quarter:{q}:{','.join(sorted(periods))}")
        top = files.get(f"prestaciones_{q}_top_codigos.json") or {}
        if top.get("sha256_arancel"):
            arancel, af = receipt_failures(rec, "Arancel Isapre", q[:4])
            failures += af
            if arancel and arancel.get("sha256") != top.get("sha256_arancel"):
                failures.append(f"arancel_hash_mismatch:{q}")
    return {"receipt": entry, "files": files, "arancel": arancel, "generated_at": (rec or {}).get("generated_at")}, failures


def evidence_sha256(sources: dict) -> str:
    lines = sorted(f"{s['url']} {s['sha256']}" for s in sources.values())
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def source_for(entry: dict, *, label: str, role: str, locator: str, detected: str | None) -> dict:
    return sf.source_ref(url=entry["url"], sha256=entry["sha256"], published_at=None, fetched_at=detected,
                         label=label, role=role, locator=locator)


def gate_open(cfg: dict, root: Path, sha: str | None, prefix: str) -> bool:
    if not cfg.get("first_pass_requires_review"):
        return True
    live = sf.load_live(Path(root), cfg["slug"]) or {}
    if str(live.get("builder_version") or "").startswith(prefix) and live.get("status") == "PASS":
        return True  # the first ficha was reviewed and published: later quarters follow the policy
    review = cfg.get("first_review") or {}
    return bool(review.get("reviewed_by") and sha and review.get("reviewed_sha256") == sha)


def first_review_gate(result: dict, cfg: dict, root: Path, family: str, prefix: str) -> dict:
    """Like F4/F7: while ``first_pass_requires_review`` is true and no ficha of the family is live, a PASS is written as
    HOLD ``awaiting_first_review`` with the full ficha (previewed on staging at web/preview.html); it publishes once
    ``families.<F>.first_review`` records ``reviewed_by`` and ``reviewed_sha256`` = the ficha's ``evidence_sha256``."""
    if result.get("status") != "pass":
        return result
    ficha = result["ficha"]
    sha = ficha.get("evidence_sha256")
    if gate_open(cfg, root, sha, prefix):
        return result
    decision = {**(result.get("decision") or {}), "decision": "HOLD",
                "holds": [*((result.get("decision") or {}).get("holds") or []), FIRST_REVIEW_HOLD]}
    candidate = {**ficha, "status": "AWAITING_FIRST_REVIEW", "review_request": {
        "evidence_sha256": sha, "period": ficha.get("period"),
        "to_publish": f"registro families.{family}.first_review: reviewed_by, reviewed_at y reviewed_sha256 = evidence_sha256"}}
    return {**{k: v for k, v in result.items() if k != "ficha"}, "status": "hold", "decision": decision,
            "errors": [FIRST_REVIEW_HOLD], "candidate": candidate}
