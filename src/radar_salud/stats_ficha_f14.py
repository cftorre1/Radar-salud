"""F14 · GES por patología (SIS, datos abiertos de Prestaciones Bonificadas): package, ficha and checks.

Input: ``data/sis_open_data_history/<quarter>/`` only: ``receipts_<q>.json`` (URL, bytes, SHA-256 and rows of the SIS
quarterly ZIP) and ``ges_gpp_publicable_<q>.json`` (``scripts/ges_f14_publicable.py`` / ``scripts/sis_historico_ges.py``
through ``ges_privacy.sanitize``). Nothing is downloaded here and no row-level data or identifier exists in the input.

What the ficha shows: GES spend (facturado) and distinct GES cases with a bonified service in the quarter, by family of
problems (Alicanto's analytic grouping), by problem (numeric prefix of ``codigo_gpp``), by Isapre (family level) and
by region of the provider (problem level), the latest quarter against the same quarter one year earlier, and the
third-quarter series since 2021.

Headline (deterministic, systemic): the gap between spend growth and case growth across all GES, stated only when
(a) the weighted measure (Σ facturado / Σ casos) rises by at least ``HEADLINE_MIN_GAP_PP`` points more for spend than
for cases, (b) the unweighted measure (median across problems of the change in facturado per case) is positive and
the per-case spend rises in more than half of the comparable problems, and (c) (a) and (b) also hold one year earlier.
Otherwise the headline states the level and its year-on-year change only.

Reconciliation (any failure → HOLD): receipts from ``https://datos.superdesalud.gob.cl`` with SHA-256, ≤ 1 GiB,
≤ 0,1 % malformed rows and a valid schema; each GES file names its quarter, the receipt's SHA-256 and row count; the
privacy check re-run here (``ges_privacy.check``: ≥ 10 cases and ≥ 3 providers per row, nothing recoverable by
subtraction); families add up to the GES total; the GES share recomputes from the receipt's totals; every problem name
equals the DS 29 reference; every Isapre code has a name.

First publication (Dirección, 10-nov-2026): new fichas publish without her personal approval once they have a
deterministic PASS, reconciliation and an independent review. Until the integration owner records
``families.F14.first_review`` (``reviewed_by``, ``reviewed_sha256`` = ``evidence_sha256``) a PASS waits in ``hold/`` as
``awaiting_first_review`` (previewed at web/preview.html). The Lectura stays off: no model call.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any, Callable
from urllib.parse import urlsplit

from . import ges_privacy as gp
from . import sis_open_data as so
from . import stats_fichas as sf
from .stats_ficha_f12 import fmt, money
from .stats_fichas import value
from .weekly_freshness import numbers_in

FAMILY = "F14"
BUILDER_VERSION = "f14_ges_patologia_v2"  # v2 (Dirección 13-nov-2026): «#. Nombre» in charts; «Nuevos problemas» topic (decree 2025–2028)
SCRIPT_VERSION = "sis_historico_v3"  # GES part of scripts/sis_historico_ges.py (same code as the backfill)
ROOT_DIR = Path("data/sis_open_data_history")
REF = Path("data/reference/ges_problemas_ds29_2025.json")
HEADLINE_MIN_GAP_PP = 3.0
TAB_ORDER = ["familias", "por-caso", "problemas", "nuevos", "serie", "isapres", "regiones"]
CPC_SMALL_BASE = 300  # cases: under this in either quarter, the per-case change carries a small-base caution
NUMBER_WORD = {10: "Diez"}
FAMILY_LABEL = {"cancer": "Cáncer", "cardiometabolico": "Cardiometabólico", "salud_mental": "Salud mental",
                "respiratorio": "Respiratorio", "musculoesqueletico": "Musculoesquelético",
                "materno_perinatal": "Materno-perinatal", "otros": "Otros"}
# Chart labels (≤ 18 characters); tables use the reference name.
SHORT = {1: "Renal crónica 4-5", 2: "Cardiop. congénita", 3: "Cáncer cervicout.", 4: "Paliativos cáncer",
         5: "Infarto", 6: "Diabetes tipo 1", 7: "Diabetes tipo 2", 8: "Cáncer de mama", 9: "Disrafias espinales",
         10: "Escoliosis", 11: "Cataratas", 12: "Prótesis cadera", 13: "Fisura labiopal.", 14: "Cáncer < 15 años",
         15: "Esquizofrenia", 16: "Cáncer testículo", 17: "Linfomas", 18: "VIH/SIDA", 19: "IRA < 5 años",
         20: "Neumonía 65+", 21: "Hipertensión", 22: "Epilepsia 1-14", 23: "Salud oral 6 años", 24: "Parto prematuro",
         25: "Marcapasos", 26: "Colecistectomía", 27: "Cáncer gástrico", 28: "Cáncer próstata", 29: "Refracción 65+",
         30: "Estrabismo", 31: "Retinop. diabética", 32: "Desprend. retina", 33: "Hemofilia", 34: "Depresión 15+",
         35: "Hiperplasia próst.", 36: "Ayudas técnicas", 37: "ACV isquémico", 38: "EPOC", 39: "Asma < 15 años",
         40: "Distrés neonatal", 41: "Artrosis 55+", 42: "Hemorr. subaracn.", 43: "Tumores SNC", 44: "Hernia núcleo",
         45: "Leucemia 15+", 46: "Urgencia dental", 47: "Salud oral 60", 48: "Politraumatizado", 49: "TEC grave",
         50: "Trauma ocular", 51: "Fibrosis quística", 52: "Artritis reumat.", 53: "Alcohol/drogas <20",
         54: "Analgesia parto", 55: "Gran quemado", 56: "Hipoacusia 65+", 57: "Retinop. prematuro",
         58: "Displasia bronc.", 59: "Hipoacusia prem.", 60: "Epilepsia 15+", 61: "Asma 15+", 62: "Parkinson",
         63: "Artritis juvenil", 64: "Prev. renal crón.", 65: "Displasia cadera", 66: "Salud oral gestante",
         67: "Esclerosis múlt.", 68: "Hepatitis B", 69: "Hepatitis C", 70: "Cáncer colorrectal", 71: "Cáncer ovario",
         72: "Cáncer vesical", 73: "Osteosarcoma", 74: "Válvula aórtica", 75: "Trastorno bipolar", 76: "Hipotiroidismo",
         77: "Hipoacusia < 4", 78: "Lupus", 79: "Válv. mitral/tric.", 80: "H. pylori", 81: "Cáncer pulmón",
         82: "Cáncer tiroides", 83: "Cáncer renal", 84: "Mieloma múltiple", 85: "Alzheimer", 86: "Agresión sexual",
         87: "Rehab. COVID-19", 88: "Cirrosis post alta", 89: "Depresión grave <15", 90: "Cesación tabaco"}


def quarters(root: Path) -> list[str]:
    base = Path(root) / ROOT_DIR
    out = [p.name for p in base.glob("*") if p.is_dir() and so.QUARTER.match(p.name)
           and (p / f"receipts_{p.name}.json").exists() and (p / f"ges_gpp_publicable_{p.name}.json").exists()]
    return sorted(out, key=so.quarter_parts)


def year_before(q: str) -> str:
    y, n = so.quarter_parts(q)
    return f"{y - 1}t{n}"


def short(p: int) -> str:
    """Chart label «#. Nombre» (Dirección 13-nov-2026: the system names GES problems by number)."""
    return f"{p}. {SHORT[p]}" if p in SHORT else f"Problema {p}"


def receipt_failures(rec: dict | None, q: str) -> list[str]:
    if not rec:
        return [f"receipt_missing:{q}"]
    f = []
    a = rec.get("archivo") or {}
    if rec.get("script_version") != SCRIPT_VERSION:
        f.append(f"receipt_script_version:{q}")
    if rec.get("periodo") != q or rec.get("estado") != "ok" or not (rec.get("esquema") or {}).get("ok"):
        f.append(f"receipt_not_ok:{q}")
    p = urlsplit(str(a.get("url") or ""))
    if p.scheme != "https" or p.hostname != so.FILE_HOST:
        f.append(f"source_not_sis_https:{q}")
    if not sf.HEX64.fullmatch(str(a.get("sha256") or "")):
        f.append(f"source_without_hash:{q}")
    b = a.get("bytes")
    if not isinstance(b, int) or not 0 < b <= so.MAX_FILE_BYTES:
        f.append(f"bytes_out_of_range:{q}")
    parse = a.get("parse") or {}
    ok, bad = parse.get("rows_ok"), parse.get("rows_malformed")
    if not isinstance(ok, int) or ok <= 0 or not isinstance(bad, int):
        f.append(f"rows_not_parsed:{q}")
    elif bad > so.MAX_MALFORMED_SHARE * (ok + bad):
        f.append(f"malformed_rows_over_0.1pct:{q}")
    return f


def load_quarter(root: Path, q: str, ref: dict, names: dict[str, str]) -> tuple[dict, list[str]]:
    folder = Path(root) / ROOT_DIR / q
    rec = so.load_json(folder / f"receipts_{q}.json")
    failures = receipt_failures(rec, q)
    raw = (folder / f"ges_gpp_publicable_{q}.json").read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if failures:
        return {}, failures
    a = rec["archivo"]
    if doc.get("periodo") != q:
        failures.append(f"aggregate_period_mismatch:{q}")
    if doc.get("script_version") != SCRIPT_VERSION:
        failures.append(f"aggregate_script_version:{q}")
    if doc.get("sha256_zip") != a["sha256"]:
        failures.append(f"aggregate_hash_mismatch:{q}")
    if doc.get("filas_zip") != a["parse"]["rows_ok"]:
        failures.append(f"aggregate_rows_mismatch:{q}")
    failures += [f"privacy:{q}:{x}" for x in gp.check(doc, ref)][:20]
    fams = doc["por_familia_nacional"]["filas"]
    tot = doc.get("totales") or {}
    if abs(sum(r["facturado"] for r in fams) - (tot.get("facturado") or 0)) > len(fams) + 1:
        failures.append(f"families_dont_add_to_total:{q}")
    total_fact = sum((v or {}).get("facturado") or 0 for v in (rec.get("totales_por_tipo_atencion") or {}).values())
    if total_fact <= 0 or abs((tot.get("facturado") or 0) / total_fact * 100 - (tot.get("pct_facturado_del_trimestre") or -1)) > 0.01:
        failures.append(f"ges_share_mismatch:{q}")
    pnames = {int(k): v for k, v in ref["problemas"].items()}
    for r in doc["por_problema_nacional"]["filas"]:
        if pnames.get(r["problema"], f"problema {r['problema']}") != r["nombre"]:
            failures.append(f"problem_name_mismatch:{q}:{r['problema']}")
    for r in doc["por_familia_isapre"]["filas"]:
        if r["isapre"] not in names:
            failures.append(f"isapre_without_name:{r['isapre']}")
    return {"receipt": rec, "doc": doc, "sha256_file": hashlib.sha256(raw).hexdigest(), "total_fact": total_fact}, sorted(set(failures))


def _hold(package: dict, failures: list[str]) -> dict:
    package["reconciliation"].update(ok=False, failures=failures)
    package.update(findings=[], kpis={}, revisions=[], constants=[])
    return package


def pct_change(a: float, b: float) -> float:
    return (b / a - 1) * 100


def build_package(root: Path, registry: dict | None = None, previous_live: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    root = Path(root)
    names = so.isapre_names(root)
    types = so.isapre_types(root)
    package: dict[str, Any] = {
        "family": FAMILY, "period": None, "periods": [], "published_at": None, "date_basis": "first_detected",
        "release_key": None, "primary_source": {}, "sources": {}, "values": {}, "entities": [], "entity_codes": [],
        "entity_keys": [], "causal_note": None, "provisional": False,
        "reconciliation": {"ok": False, "failures": [], "checks": [
            "recibo del ZIP SIS: https://datos.superdesalud.gob.cl, SHA-256, ≤ 1 GiB, ≤ 0,1 % de filas malformadas, esquema válido",
            "cada archivo GES nombra el trimestre, el SHA-256 del ZIP y sus filas",
            "chequeo de privacidad re-ejecutado: ≥ 10 casos y ≥ 3 prestadores por fila; nada recuperable por resta",
            "las familias suman el total GES; el % GES se recalcula con los totales del recibo",
            "nombres de problemas = referencia DS 29; toda Isapre con nombre"]},
        "lectura_pool": [], "derived_ratios": [], "ranks": [],
    }
    ref = so.load_json(root / REF)
    if not ref or not isinstance(ref.get("problemas"), dict) or len(ref["problemas"]) != 90:
        return _hold(package, ["ges_reference_missing"])
    qs = quarters(root)
    if not qs:
        return _hold(package, ["no_quarter_aggregated"])
    q = qs[-1]
    py, ppy = year_before(q), year_before(year_before(q))
    package["period"] = so.period_of(q)
    if py not in qs:
        return _hold(package, [f"previous_year_missing:{py}"])
    data: dict[str, dict] = {}
    failures: list[str] = []
    for qq in qs:
        d, f = load_quarter(root, qq, ref, names)
        failures += f
        data[qq] = d
    if failures:
        return _hold(package, failures)
    values: dict[str, dict] = {}
    sources: dict[str, dict] = {}

    def src(qq: str) -> str:
        key = "ges_" + qq
        if key not in sources:
            d = data[qq]
            a = d["receipt"]["archivo"]
            sources[key] = sf.source_ref(
                url=a["url"], sha256=a["sha256"], published_at=None,
                fetched_at=str(d["receipt"].get("generated_at") or "")[:10] or None,
                label=f"SIS · Prestaciones bonificadas {so.quarter_label(qq)} (datos abiertos)",
                role="ZIP trimestral; agregados GES de Alicanto por problema (código GPP), familia, Isapre y región",
                locator=(f"{a['parse']['rows_ok']} filas; agregado ges_gpp_publicable_{qq}.json SHA-256 {d['sha256_file']}; "
                         f"fuente ges_gpp_{qq}.json SHA-256 {(d['doc'].get('fuente_agregada') or {}).get('sha256') or 'no registrada'}"))
        return key

    def put(vid: str, val: float, unit: str, qq: str, locator: str) -> float:
        values[vid] = value(vid, val, unit=unit, period=so.period_of(qq), source=src(qq), locator=locator)
        return val

    def derived(vid: str, val: float, unit: str, formula: str, inputs: list[str], qq: str = q) -> float:
        values[vid] = value(vid, val, unit=unit, period=so.period_of(qq), source=None, formula=formula, inputs=inputs,
                            kind="derived")
        return val

    def cell(prefix: str, row: dict, qq: str, loc: str) -> None:
        put(f"{prefix}.{qq}.facturado_mm", round(row["facturado"] / 1e6, 3), "MM$", qq, loc)
        put(f"{prefix}.{qq}.casos", row["casos"], "casos", qq, loc)
        derived(f"{prefix}.{qq}.por_caso", row["facturado"] / row["casos"], "$", "facturado / casos",
                [f"{prefix}.{qq}.facturado_mm", f"{prefix}.{qq}.casos"], qq)

    # 1. Totals and families, every quarter (series); casos = Σ families (cases are distinct per problem).
    fam_rows = {qq: {r["familia"]: r for r in data[qq]["doc"]["por_familia_nacional"]["filas"]} for qq in qs}
    for qq in qs:
        doc = data[qq]["doc"]
        loc = f"ges_gpp_publicable_{qq}.json · por_familia_nacional"
        for f, r in fam_rows[qq].items():
            cell(f"fam.{f}", r, qq, loc)
        tot = doc["totales"]
        put(f"tot.{qq}.facturado_mm", round(tot["facturado"] / 1e6, 3), "MM$", qq, f"ges_gpp_publicable_{qq}.json · totales")
        put(f"tot.{qq}.casos", sum(r["casos"] for r in fam_rows[qq].values()), "casos", qq, loc + " (suma)")
        derived(f"tot.{qq}.por_caso", tot["facturado"] / values[f"tot.{qq}.casos"]["value"], "$", "facturado GES / casos",
                [f"tot.{qq}.facturado_mm", f"tot.{qq}.casos"], qq)
        put(f"tot.{qq}.pct_ges", tot["pct_facturado_del_trimestre"], "%", qq,
            f"ges_gpp_publicable_{qq}.json · totales; denominador: facturado total del ZIP (recibo)")
        put(f"tot.{qq}.filas_gpp_no_parseable", int((data[qq]["receipt"]["esquema"].get("gpp_no_parseable") or {}).get("no_parseable") or 0),
            "filas", qq, f"receipts_{qq}.json · esquema.gpp_no_parseable")
    fams = sorted(fam_rows[q], key=lambda f: -fam_rows[q][f]["facturado"])
    if set(fams) != set(fam_rows[py]):
        return _hold(package, ["family_set_changed"])

    # 2. Year on year: system (weighted) and per problem (unweighted), this year and one year earlier.
    def yoy(prefix: str, a: str, b: str, tag: str) -> None:
        for m in ("facturado_mm", "casos", "por_caso"):
            derived(f"{prefix}.{tag}.{m}", pct_change(values[f"{prefix}.{a}.{m}"]["value"], values[f"{prefix}.{b}.{m}"]["value"]), "%",
                    f"({m} {b} / {m} {a} − 1) × 100", [f"{prefix}.{a}.{m}", f"{prefix}.{b}.{m}"], b)
        derived(f"{prefix}.{tag}.brecha_pp", values[f"{prefix}.{tag}.facturado_mm"]["value"] - values[f"{prefix}.{tag}.casos"]["value"],
                "pp", "variación del facturado − variación de los casos", [f"{prefix}.{tag}.facturado_mm", f"{prefix}.{tag}.casos"], b)

    pairs = [("yoy", py, q)] + ([("yoy_prev", ppy, py)] if ppy in qs else [])
    for tag, a, b in pairs:
        yoy("tot", a, b, tag)
        for f in fams:
            if f in fam_rows[a]:
                yoy(f"fam.{f}", a, b, tag)
    prob_rows = {qq: {r["problema"]: r for r in data[qq]["doc"]["por_problema_nacional"]["filas"]} for qq in (q, py, ppy) if qq in qs}
    for qq, rows in prob_rows.items():
        for p, r in rows.items():
            cell(f"prob.{p}", r, qq, f"ges_gpp_publicable_{qq}.json · por_problema_nacional · {p}")
    comparable = {}
    for tag, a, b in pairs:
        comp = sorted(p for p in prob_rows[b] if p in prob_rows[a])
        comparable[tag] = comp
        for p in comp:
            yoy(f"prob.{p}", a, b, tag)
        ch = [values[f"prob.{p}.{tag}.por_caso"]["value"] for p in comp]
        if len(ch) < 10:
            return _hold(package, [f"comparable_problems_under_10:{tag}"])
        derived(f"prob.{tag}.mediana_por_caso", median(ch), "%", "mediana entre problemas comparables del cambio a/a del facturado por caso",
                [f"prob.{p}.{tag}.por_caso" for p in comp], b)
        derived(f"prob.{tag}.n_suben", sum(1 for x in ch if round(x, 1) > 0), "problemas", "problemas cuyo facturado por caso sube",
                [f"prob.{p}.{tag}.por_caso" for p in comp], b)
        derived(f"prob.{tag}.n_comparables", len(ch), "problemas", "problemas con fila publicada en ambos trimestres",
                [f"prob.{p}.{tag}.por_caso" for p in comp], b)

    def systemic(tag: str) -> bool:
        if f"tot.{tag}.brecha_pp" not in values:
            return False
        V = lambda k: values[k]["value"]  # noqa: E731
        return (V(f"tot.{tag}.brecha_pp") >= HEADLINE_MIN_GAP_PP and V(f"tot.{tag}.por_caso") > 0
                and V(f"prob.{tag}.mediana_por_caso") > 0 and V(f"prob.{tag}.n_suben") * 2 > V(f"prob.{tag}.n_comparables"))
    checks = {"actual": systemic("yoy"), "anio_anterior": systemic("yoy_prev")}

    # 3. Top problems by spend and fastest-growing cost per case (base: ≥ cpc_min_cases cases in both quarters).
    top = sorted(prob_rows[q], key=lambda p: -prob_rows[q][p]["facturado"])[: int(cfg.get("top_problems") or 10)]
    derived("prob.top.n", len(top), "problemas", "problemas con más facturado mostrados", [f"prob.{p}.{q}.facturado_mm" for p in top])
    derived("prob.top.share", sum(prob_rows[q][p]["facturado"] for p in top) / data[q]["doc"]["totales"]["facturado"] * 100, "%",
            "facturado de los problemas con más facturado / facturado GES × 100", [f"prob.{p}.{q}.facturado_mm" for p in top])
    min_cases = int(cfg.get("cpc_min_cases") or 100)
    based = [p for p in comparable["yoy"] if min(prob_rows[q][p]["casos"], prob_rows[py][p]["casos"]) >= min_cases]
    risers = sorted(based, key=lambda p: -values[f"prob.{p}.yoy.por_caso"]["value"])
    derived("prob.base_cpc.n", len(based), "problemas", f"problemas comparables con ≥ {min_cases} casos en ambos trimestres",
            [f"prob.{p}.yoy.por_caso" for p in based])
    if len(risers) < 5:
        return _hold(package, ["cpc_base_under_5"])

    # 4. Isapre cut: the largest family, open and closed Isapres with a row in both quarters.
    fi = {qq: {(r["familia"], r["isapre"]): r for r in data[qq]["doc"]["por_familia_isapre"]["filas"]} for qq in (q, py)}
    lead = fams[0]
    isas = sorted((i for (f, i) in fi[q] if f == lead), key=lambda i: -fi[q][(lead, i)]["facturado"])
    for i in isas:
        cell(f"fi.{lead}.{i}", fi[q][(lead, i)], q, f"ges_gpp_publicable_{q}.json · por_familia_isapre · {lead} · {i}")
        if (lead, i) in fi[py]:
            cell(f"fi.{lead}.{i}", fi[py][(lead, i)], py, f"ges_gpp_publicable_{py}.json · por_familia_isapre · {lead} · {i}")
            yoy(f"fi.{lead}.{i}", py, q, "yoy")
    for (f, i), r in fi[q].items():
        if f != lead:
            cell(f"fi.{f}.{i}", r, q, f"ges_gpp_publicable_{q}.json · por_familia_isapre · {f} · {i}")
    opens_yoy = [i for i in isas if types.get(i) == "open" and f"fi.{lead}.{i}.yoy.por_caso" in values]
    derived("fi.abiertas_suben", sum(1 for i in opens_yoy if round(values[f"fi.{lead}.{i}.yoy.por_caso"]["value"], 1) > 0),
            "Isapres", "Isapres abiertas cuyo facturado por caso sube", [f"fi.{lead}.{i}.yoy.por_caso" for i in opens_yoy])
    derived("fi.abiertas_n", len(opens_yoy), "Isapres", "Isapres abiertas con fila en ambos trimestres",
            [f"fi.{lead}.{i}.yoy.por_caso" for i in opens_yoy])
    missing = [i for i in {i for (_, i) in fi[q]} if types.get(i) not in ("open", "closed")]
    if missing:
        return _hold(package, [f"isapre_without_type:{i}" for i in missing])

    # 5. Region cut: the problem with most spend among those with ≥ region_min_regions published regions (provider's region).
    rr = {}
    for r in data[q]["doc"]["por_problema_region"]["filas"]:
        rr.setdefault(r["problema"], {})[r["region"]] = r
    min_regs = int(cfg.get("region_min_regions") or 12)
    cand = [p for p in sorted(prob_rows[q], key=lambda p: -prob_rows[q][p]["facturado"])
            if len([x for x in rr.get(p, {}) if x != "0"]) >= min_regs]
    region_problem = cand[0] if cand else None
    if region_problem is not None:
        for reg, r in rr[region_problem].items():
            if reg in so.REGIONS:
                cell(f"reg.{region_problem}.{reg}", r, q, f"ges_gpp_publicable_{q}.json · por_problema_region · {region_problem} · {reg}")
        regs = [x for x in rr[region_problem] if x not in ("0", "13") and x in so.REGIONS]
        cpcs = [values[f"reg.{region_problem}.{x}.{q}.por_caso"]["value"] for x in regs]
        derived("reg.min", min(cpcs), "$", "mínimo regional del facturado por caso (sin Metropolitana ni región 0)",
                [f"reg.{region_problem}.{x}.{q}.por_caso" for x in regs])
        derived("reg.max", max(cpcs), "$", "máximo regional del facturado por caso (sin Metropolitana ni región 0)",
                [f"reg.{region_problem}.{x}.{q}.por_caso" for x in regs])
        derived("reg.n", len(regs) + (1 if "13" in rr[region_problem] else 0), "regiones", "regiones con fila publicada (sin región 0)",
                [f"reg.{region_problem}.{x}.{q}.por_caso" for x in regs])

    # 6. Series: third quarter (same quarter as q) of each year; share of GES range across every quarter.
    same_q = [qq for qq in qs if so.quarter_parts(qq)[1] == so.quarter_parts(q)[1]]
    first = same_q[0]
    for f in fams:
        if f in fam_rows[first]:
            derived(f"fam.{f}.serie.por_caso", pct_change(values[f"fam.{f}.{first}.por_caso"]["value"], values[f"fam.{f}.{q}.por_caso"]["value"]),
                    "%", f"(facturado por caso {q} / {first} − 1) × 100", [f"fam.{f}.{first}.por_caso", f"fam.{f}.{q}.por_caso"])
            derived(f"fam.{f}.serie.casos", pct_change(values[f"fam.{f}.{first}.casos"]["value"], values[f"fam.{f}.{q}.casos"]["value"]),
                    "%", f"(casos {q} / {first} − 1) × 100", [f"fam.{f}.{first}.casos", f"fam.{f}.{q}.casos"])
    derived("tot.serie.facturado", pct_change(values[f"tot.{first}.facturado_mm"]["value"], values[f"tot.{q}.facturado_mm"]["value"]), "%",
            f"(facturado {q} / {first} − 1) × 100", [f"tot.{first}.facturado_mm", f"tot.{q}.facturado_mm"])
    derived("tot.serie.casos", pct_change(values[f"tot.{first}.casos"]["value"], values[f"tot.{q}.casos"]["value"]), "%",
            f"(casos {q} / {first} − 1) × 100", [f"tot.{first}.casos", f"tot.{q}.casos"])
    shares = [values[f"tot.{qq}.pct_ges"]["value"] for qq in qs]
    derived("tot.pct_ges.min", min(shares), "%", "mínimo trimestral del % GES", [f"tot.{qq}.pct_ges" for qq in qs])
    derived("tot.pct_ges.max", max(shares), "%", "máximo trimestral del % GES", [f"tot.{qq}.pct_ges" for qq in qs])

    counts = {"familias_brecha": sum(1 for f in fams if f"fam.{f}.yoy.brecha_pp" in values and values[f"fam.{f}.yoy.brecha_pp"]["value"] > 0),
              "familias": len(fams)}
    for k, n in counts.items():
        derived(f"conteo.{k}", n, "count", k, [])
        package["derived_ratios"].append({"id": f"conteo.{k}", "value": n, "unit": "count"})
    ev = so.evidence_sha256(sources)
    detected = str(data[q]["receipt"].get("generated_at") or "")[:10] or None
    isapres = sorted({i for (_, i) in fi[q]}, key=int)
    package.update(
        period=so.period_of(q), periods=[so.period_of(x) for x in (py, q)], published_at=detected,
        release_key=sf.release_key(so.period_of(q), ev), evidence_sha256=ev,
        primary_source={"url": data[q]["receipt"]["archivo"]["url"], "sha256": data[q]["receipt"]["archivo"]["sha256"]},
        sources=sources, values=values, findings=[],
        entities=[{"code": int(c), "name": names[c]} for c in isapres], entity_codes=[int(c) for c in isapres],
        revisions=sf.detect_revisions({"values": values}, (previous_live or {}).get("evidence")),
        # Problem numbers and the numbers inside problem names ("15 años y más") are labels, not figures.
        constants=[0, 1, 2, 3, 10, 12, 100, HEADLINE_MIN_GAP_PP, gp.MIN_CASES, gp.MIN_PROVIDERS, min_cases, min_regs, len(top),
                   *sorted({*top, *risers, *([region_problem] if region_problem else [])}),
                   *[x for r in [*SHORT.values(), *(str(n) for n in ref["problemas"].values())] for _, x, _ in numbers_in(r)]],
        kpis={"q": q, "py": py, "ppy": ppy if ppy in qs else None, "qs": qs, "same_q": same_q, "fams": fams, "top": top,
              "risers": risers, "lead": lead, "isas": isas, "region_problem": region_problem, "checks": checks,
              "comparable": comparable, "closed": [i for i in isapres if types[i] == "closed"],
              "supresion": {qq: data[qq]["doc"].get("supresion") for qq in (q, py)},
              "pnames": {p: r["nombre"] for qq in prob_rows for p, r in prob_rows[qq].items()},
              "pfam": {p: r["familia"] for qq in prob_rows for p, r in prob_rows[qq].items()}},
    )
    package["reconciliation"].update(ok=True, failures=[])
    return package


def compose(package: dict, registry: dict | None = None, *, today: date, decision: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    tpl = cfg["templates"]
    v = package["values"]
    k = package["kpis"]
    q, py, ppy = k["q"], k["py"], k["ppy"]
    V = lambda vid: v[vid]["value"]  # noqa: E731
    pc = lambda vid: fmt(V(vid), 1) + "%"  # noqa: E731
    sg = lambda vid: fmt(V(vid), 1, True) + "%"  # noqa: E731
    mm = lambda vid: fmt(V(vid), 0) + " MM$"  # noqa: E731
    names = {e["code"]: e["name"] for e in package["entities"]}
    nm = lambda code: names[int(code)]  # noqa: E731
    ql, qs_, pys = so.quarter_label(q), so.quarter_short(q), so.quarter_short(py)
    closed = set(k["closed"])
    tag = lambda i: {"tag": "cerrada"} if i in closed else {}  # noqa: E731
    fams, top, lead = k["fams"], k["top"], k["lead"]
    src = "SIS, datos abiertos de prestaciones bonificadas; filas con código GPP de problema GES; agregados de Alicanto."
    tabs, notes, paragraphs = [], [], []

    def change_word(vid: str, verb_up: str = "sube", verb_down: str = "baja") -> str:
        x = V(vid)
        if round(x, 1) == 0:
            return "no cambia"
        return f"{verb_up if x > 0 else verb_down} {fmt(abs(x), 1)}%"

    # Headline and dek.
    systemic = k["checks"]["actual"] and k["checks"]["anio_anterior"]
    if systemic:
        headline = (f"GES en Isapres: facturado {sg('tot.yoy.facturado_mm')}, casos {sg('tot.yoy.casos')}; por caso sube en "
                    f"{fmt(V('prob.yoy.n_suben'), 0)} de {fmt(V('prob.yoy.n_comparables'), 0)}")
        smaller = V("tot.yoy_prev.brecha_pp") < V("tot.yoy.brecha_pp")
        dek = (f"El facturado (lo cobrado por prestadores, no lo pagado) por caso {change_word('tot.yoy.por_caso')} en el total y "
               f"{fmt(abs(V('prob.yoy.mediana_por_caso')), 1)}% en la mediana de los problemas. "
               + ("Un año antes la brecha era menor" if smaller else "Un año antes")
               + f": facturado {sg('tot.yoy_prev.facturado_mm')}, casos {sg('tot.yoy_prev.casos')}.")
        htype = "gap_spend_cases"
    else:
        headline = f"GES en Isapres: {mm(f'tot.{q}.facturado_mm')} facturados en {qs_}, {change_word('tot.yoy.facturado_mm')} en un año"
        dek = (f"Los casos {change_word('tot.yoy.casos', 'suben', 'bajan')} y el facturado por caso {change_word('tot.yoy.por_caso')}; "
               f"el GES es el {pc(f'tot.{q}.pct_ges')} de lo facturado a las Isapres.")
        htype = "default"

    # KPIs.
    kpis = [
        {"id": "facturado_ges", "label": "Facturado GES", "value": mm(f"tot.{q}.facturado_mm"), "prov": "C",
         "lines": [f"{sg('tot.yoy.facturado_mm')} vs. {pys}"], "refs": [f"tot.{q}.facturado_mm", "tot.yoy.facturado_mm"]},
        {"id": "casos_ges", "label": "Casos GES con prestación", "value": fmt(V(f"tot.{q}.casos"), 0), "prov": "C",
         "lines": [f"{sg('tot.yoy.casos')} vs. {pys}"], "refs": [f"tot.{q}.casos", "tot.yoy.casos"]},
        {"id": "por_caso", "label": "Facturado por caso", "value": money(V(f"tot.{q}.por_caso")), "prov": "C",
         "lines": [f"{sg('tot.yoy.por_caso')} vs. {pys}"], "refs": [f"tot.{q}.por_caso", "tot.yoy.por_caso"]},
        {"id": "peso_ges", "label": "GES en lo facturado Isapre", "value": pc(f"tot.{q}.pct_ges"), "prov": "C",
         "lines": [f"{pys}: {pc(f'tot.{py}.pct_ges')}"], "refs": [f"tot.{q}.pct_ges", f"tot.{py}.pct_ges"]},
    ]

    # Topic 1: families.
    fl = lambda f: FAMILY_LABEL.get(f, f)  # noqa: E731
    fam_table = {"columns": ["Familia", f"Casos {qs_}", f"Casos {pys}", "Casos a/a", f"Facturado {qs_} (MM$)", f"Facturado {pys} (MM$)",
                             "Facturado a/a", "Por caso a/a"],
                 "rows": [[fl(f), fmt(V(f"fam.{f}.{q}.casos"), 0), fmt(V(f"fam.{f}.{py}.casos"), 0), sg(f"fam.{f}.yoy.casos"),
                           fmt(V(f"fam.{f}.{q}.facturado_mm"), 0), fmt(V(f"fam.{f}.{py}.facturado_mm"), 0),
                           sg(f"fam.{f}.yoy.facturado_mm"), sg(f"fam.{f}.yoy.por_caso")] for f in fams]
                 + [["Total GES", fmt(V(f"tot.{q}.casos"), 0), fmt(V(f"tot.{py}.casos"), 0), sg("tot.yoy.casos"),
                     fmt(V(f"tot.{q}.facturado_mm"), 0), fmt(V(f"tot.{py}.facturado_mm"), 0), sg("tot.yoy.facturado_mm"),
                     sg("tot.yoy.por_caso")]]}
    charts = [{"id": "f14-familias-facturado", "form": "diverging", "unit": "%", "digits": 1,
               "headline": "Facturado, variación en un año",
               "subtitle": f"% {qs_} vs. {pys}, por familia de problemas GES",
               "rows": [{"label": fl(f), "value": V(f"fam.{f}.yoy.facturado_mm"), "ref": f"fam.{f}.yoy.facturado_mm"}
                        for f in sorted(fams, key=lambda f: -V(f"fam.{f}.yoy.facturado_mm"))],
               "table": fam_table, "source": src + " Familias: agrupación analítica de Alicanto."},
              {"id": "f14-familias-casos", "form": "diverging", "unit": "%", "digits": 1,
               "headline": "Casos, variación en un año",
               "subtitle": f"% {qs_} vs. {pys}; casos = id GES distintos con prestación en el trimestre",
               "rows": [{"label": fl(f), "value": V(f"fam.{f}.yoy.casos"), "ref": f"fam.{f}.yoy.casos"}
                        for f in sorted(fams, key=lambda f: -V(f"fam.{f}.yoy.facturado_mm"))],
               "table": {"columns": ["Familia", "Casos a/a", "Facturado a/a", "Brecha (pp)"],
                         "rows": [[fl(f), sg(f"fam.{f}.yoy.casos"), sg(f"fam.{f}.yoy.facturado_mm"), fmt(V(f"fam.{f}.yoy.brecha_pp"), 1, True)]
                                  for f in fams]},
               "source": src}]
    tab = {"id": "familias", "label": "Familias", "charts": charts, "text": [],
           "dek": (f"En {fmt(V('conteo.familias_brecha'), 0)} de {fmt(V('conteo.familias'), 0)} familias, el facturado crece más que los casos"),
           "dek_refs": ["conteo.familias_brecha", "conteo.familias"]}
    sf.topic_fields(tab, f"{fl(fams[0])}: {mm(f'fam.{fams[0]}.{q}.facturado_mm')}, {sg(f'fam.{fams[0]}.yoy.facturado_mm')} a/a",
                    index_refs=[f"fam.{fams[0]}.{q}.facturado_mm", f"fam.{fams[0]}.yoy.facturado_mm"], kpis=[])
    tabs.append(tab)

    # Topic 2: top problems by spend.
    p0 = top[0]
    pr_table = {"columns": ["Problema", "Familia", "Casos", "Facturado (MM$)", "Por caso", "Facturado a/a", "Casos a/a"],
                "rows": [[f"{p}. {package_name(package, p, q)}", fl(fam_of(package, p, q)), fmt(V(f"prob.{p}.{q}.casos"), 0),
                          fmt(V(f"prob.{p}.{q}.facturado_mm"), 0), money(V(f"prob.{p}.{q}.por_caso")),
                          sg(f"prob.{p}.yoy.facturado_mm") if f"prob.{p}.yoy.facturado_mm" in v else "sin comparación",
                          sg(f"prob.{p}.yoy.casos") if f"prob.{p}.yoy.casos" in v else "sin comparación"] for p in top]}
    charts = [{"id": "f14-top-facturado", "form": "bars", "unit": "MM$", "digits": 0,
               "headline": "Problemas con más facturado",
               "subtitle": f"MM$ facturados a las Isapres, {ql}",
               "rows": [{"label": short(p), "value": V(f"prob.{p}.{q}.facturado_mm"), "ref": f"prob.{p}.{q}.facturado_mm",
                         "emphasis": p == p0} for p in top],
               "table": pr_table, "source": src + " Problema = número del decreto GES (prefijo del código GPP)."},
              {"id": "f14-top-por-caso", "form": "bars", "unit": "$", "digits": 0,
               "headline": "Facturado por caso en esos problemas",
               "subtitle": f"$ por caso, {ql}",
               "rows": [{"label": short(p), "value": V(f"prob.{p}.{q}.por_caso"), "ref": f"prob.{p}.{q}.por_caso"}
                        for p in sorted(top, key=lambda p: -V(f"prob.{p}.{q}.por_caso"))],
               "table": {"columns": ["Problema", "Por caso", f"Por caso {pys}"],
                         "rows": [[f"{p}. {package_name(package, p, q)}", money(V(f"prob.{p}.{q}.por_caso")),
                                   money(V(f"prob.{p}.{py}.por_caso")) if f"prob.{p}.{py}.por_caso" in v else "sin dato"] for p in top]},
               "source": src}]
    n_top = NUMBER_WORD.get(len(top)) or f"Los {fmt(len(top), 0)}"
    tab = {"id": "problemas", "label": "Problemas principales", "charts": charts, "text": [],
           "dek": (f"{n_top} problemas concentran {pc('prob.top.share')} del facturado GES; "
                   f"«{p0}. {plain(package, p0, q)}» lidera con {mm(f'prob.{p0}.{q}.facturado_mm')}"),
           "dek_refs": ["prob.top.n", "prob.top.share", f"prob.{p0}.{q}.facturado_mm", *label_refs(package, plain(package, p0, q))]}
    sf.topic_fields(tab, f"{p0}. {plain(package, p0, q)}: {mm(f'prob.{p0}.{q}.facturado_mm')}",
                    index_refs=[f"prob.{p0}.{q}.facturado_mm", *label_refs(package, plain(package, p0, q))], kpis=[])
    tabs.append(tab)

    # Topic 3: fastest-growing cost per case (≥ cpc_min_cases cases in both quarters).
    rs = k["risers"]
    r0 = rs[0]
    charts = [{"id": "f14-por-caso-sube", "form": "diverging", "unit": "%", "digits": 1,
               "headline": "Facturado por caso: los que más suben",
               "subtitle": f"% {qs_} vs. {pys}; problemas con ≥ {fmt(cfg.get('cpc_min_cases') or 100, 0)} casos en ambos trimestres",
               "rows": [{"label": short(p), "value": V(f"prob.{p}.yoy.por_caso"), "ref": f"prob.{p}.yoy.por_caso"} for p in rs[:10]],
               "table": {"columns": ["Problema", f"Casos {pys}", f"Casos {qs_}", f"Por caso {pys}", f"Por caso {qs_}", "Por caso a/a",
                                     "Casos a/a", "Facturado a/a"],
                         "rows": [[f"{p}. {package_name(package, p, q)}", fmt(V(f"prob.{p}.{py}.casos"), 0), fmt(V(f"prob.{p}.{q}.casos"), 0),
                                   money(V(f"prob.{p}.{py}.por_caso")), money(V(f"prob.{p}.{q}.por_caso")),
                                   sg(f"prob.{p}.yoy.por_caso"), sg(f"prob.{p}.yoy.casos"), sg(f"prob.{p}.yoy.facturado_mm")] for p in rs]},
               "source": src},
              {"id": "f14-por-caso-medidas", "form": "diverging", "unit": "%", "digits": 1,
               "headline": "Facturado por caso: total y mediana",
               "subtitle": "% a/a; total del GES (ponderado) y mediana entre problemas (sin ponderar)",
               "rows": [{"label": f"Total {so.quarter_short(q)[-4:]}", "value": V("tot.yoy.por_caso"), "ref": "tot.yoy.por_caso", "emphasis": True},
                        {"label": f"Mediana {so.quarter_short(q)[-4:]}", "value": V("prob.yoy.mediana_por_caso"), "ref": "prob.yoy.mediana_por_caso"}]
               + ([{"label": f"Total {so.quarter_short(py)[-4:]}", "value": V("tot.yoy_prev.por_caso"), "ref": "tot.yoy_prev.por_caso"},
                   {"label": f"Mediana {so.quarter_short(py)[-4:]}", "value": V("prob.yoy_prev.mediana_por_caso"), "ref": "prob.yoy_prev.mediana_por_caso"}]
                  if ppy else []),
               "table": {"columns": ["Medida", "Variación a/a", "Problemas que suben"],
                         "rows": [[f"Total GES {qs_}", sg("tot.yoy.por_caso"), ""],
                                  [f"Mediana entre problemas {qs_}", sg("prob.yoy.mediana_por_caso"),
                                   f"{fmt(V('prob.yoy.n_suben'), 0)} de {fmt(V('prob.yoy.n_comparables'), 0)}"]]
                         + ([[f"Total GES {pys}", sg("tot.yoy_prev.por_caso"), ""],
                             [f"Mediana entre problemas {pys}", sg("prob.yoy_prev.mediana_por_caso"),
                              f"{fmt(V('prob.yoy_prev.n_suben'), 0)} de {fmt(V('prob.yoy_prev.n_comparables'), 0)}"]] if ppy else [])},
               "source": src + " Mediana entre problemas con fila publicada en ambos trimestres."}]
    r0name = f"{r0}. {plain(package, r0, q)}"  # «#. Nombre» (Dirección 13-nov-2026)
    if not any(e.get("id") == "umbral.base_chica" for e in package["derived_ratios"]):
        package["derived_ratios"].append({"id": "umbral.base_chica", "value": CPC_SMALL_BASE, "unit": "count"})
    n_py, n_q = V(f"prob.{r0}.{py}.casos"), V(f"prob.{r0}.{q}.casos")
    r0_text = (f"{r0name}: de {money(V(f'prob.{r0}.{py}.por_caso'))} a {money(V(f'prob.{r0}.{q}.por_caso'))} por caso, con "
               f"{fmt(n_py, 0)} casos en {pys} y {fmt(n_q, 0)} en {qs_}.")
    r0_n = f"Casos: {fmt(n_py, 0)} ({so.quarter_short(py)[-4:]}) y {fmt(n_q, 0)} ({so.quarter_short(q)[-4:]})."
    if min(n_py, n_q) < CPC_SMALL_BASE:
        r0_n += f" Base chica (menos de {fmt(CPC_SMALL_BASE, 0)} casos): léase como señal."
    tab = {"id": "por-caso", "label": "Facturado por caso", "charts": charts, "text": [r0_text],
           "dek": (f"Facturado por caso: {sg('tot.yoy.por_caso')} en el total; «{r0name}» lidera con "
                   f"{sg(f'prob.{r0}.yoy.por_caso')}. {r0_n}"),
           "dek_refs": ["tot.yoy.por_caso", f"prob.{r0}.yoy.por_caso", f"prob.{r0}.{py}.casos", f"prob.{r0}.{q}.casos",
                        *label_refs(package, r0name)] + (["umbral.base_chica"] if min(n_py, n_q) < CPC_SMALL_BASE else [])}
    sf.topic_fields(tab, f"Total {sg('tot.yoy.por_caso')} · mediana {sg('prob.yoy.mediana_por_caso')} por caso",
                    index_refs=["tot.yoy.por_caso", "prob.yoy.mediana_por_caso"], kpis=[])
    tabs.append(tab)

    # Topic 4: Isapres (largest family).
    isas = k["isas"]
    yo = [i for i in isas if f"fi.{lead}.{i}.yoy.por_caso" in v]
    all_fi = sorted({(vid.split(".")[1], vid.split(".")[2]) for vid in v if vid.startswith("fi.") and vid.endswith(f".{q}.por_caso")})
    charts = [{"id": "f14-isapre-por-caso", "form": "bars", "unit": "$", "digits": 0,
               "headline": f"{fl(lead)}: facturado por caso, por Isapre",
               "subtitle": f"$ por caso, {ql}",
               "rows": [{"label": nm(i), "value": V(f"fi.{lead}.{i}.{q}.por_caso"), "ref": f"fi.{lead}.{i}.{q}.por_caso", **tag(i)}
                        for i in sorted(isas, key=lambda i: -V(f"fi.{lead}.{i}.{q}.por_caso"))],
               "table": {"columns": ["Familia", "Isapre", "Casos", "Facturado (MM$)", "Por caso"],
                         "rows": [[fl(f), nm(i), fmt(V(f"fi.{f}.{i}.{q}.casos"), 0), fmt(V(f"fi.{f}.{i}.{q}.facturado_mm"), 0),
                                   money(V(f"fi.{f}.{i}.{q}.por_caso"))] for f, i in sorted(all_fi, key=lambda x: (fams.index(x[0]), nm(x[1])))]},
               "source": src + " Isapres con ≥ 10 casos y ≥ 3 prestadores en la familia; las demás quedan ocultas."}]
    if len(yo) >= 2:
        charts.append({"id": "f14-isapre-por-caso-aa", "form": "diverging", "unit": "%", "digits": 1,
                       "headline": f"{fl(lead)}: facturado por caso, variación",
                       "subtitle": f"% {qs_} vs. {pys}, por Isapre",
                       "rows": [{"label": nm(i), "value": V(f"fi.{lead}.{i}.yoy.por_caso"), "ref": f"fi.{lead}.{i}.yoy.por_caso", **tag(i)}
                                for i in sorted(yo, key=lambda i: -V(f"fi.{lead}.{i}.yoy.por_caso"))],
                       "table": {"columns": ["Isapre", "Por caso a/a", "Casos a/a", "Facturado a/a"],
                                 "rows": [[nm(i), sg(f"fi.{lead}.{i}.yoy.por_caso"), sg(f"fi.{lead}.{i}.yoy.casos"),
                                           sg(f"fi.{lead}.{i}.yoy.facturado_mm")] for i in yo]},
                       "source": src})
    tab = {"id": "isapres", "label": "Por Isapre", "charts": charts, "text": [],
           "dek": (f"{fl(lead)} por Isapre: el facturado por caso sube en {fmt(V('fi.abiertas_suben'), 0)} de "
                   f"{fmt(V('fi.abiertas_n'), 0)} abiertas"),
           "dek_refs": ["fi.abiertas_suben", "fi.abiertas_n"]}
    opens = [i for i in isas if i not in closed]
    if len(opens) >= 2:
        hi = max(opens, key=lambda i: V(f"fi.{lead}.{i}.{q}.por_caso"))
        lo = min(opens, key=lambda i: V(f"fi.{lead}.{i}.{q}.por_caso"))
        sf.topic_fields(tab, f"{fl(lead)}, abiertas: {money(V(f'fi.{lead}.{lo}.{q}.por_caso'))} a {money(V(f'fi.{lead}.{hi}.{q}.por_caso'))} por caso",
                        index_refs=[f"fi.{lead}.{lo}.{q}.por_caso", f"fi.{lead}.{hi}.{q}.por_caso"], kpis=[])
    else:
        sf.topic_fields(tab, None, kpis=[])
    if not V("fi.abiertas_n"):
        tab["dek"], tab["dek_refs"] = None, []
    tabs.append(tab)

    # Topic 5: regions (one problem, provider's region).
    rp = k["region_problem"]
    if rp is not None:
        regs = [r for r in so.REGIONS if f"reg.{rp}.{r}.{q}.por_caso" in v and r != "0"]
        big = sorted(regs, key=lambda r: -V(f"reg.{rp}.{r}.{q}.casos"))[:12]
        rname = f"{rp}. {plain(package, rp, q)}"
        charts = [{"id": "f14-region-por-caso", "form": "bars", "unit": "$", "digits": 0,
                   "headline": f"{short(rp)}: facturado por caso por región",
                   "subtitle": f"$ por caso, región del prestador, {ql}; 12 regiones con más casos",
                   "rows": [{"label": so.REGIONS[r], "value": V(f"reg.{rp}.{r}.{q}.por_caso"), "ref": f"reg.{rp}.{r}.{q}.por_caso",
                             "emphasis": r == "13"} for r in sorted(big, key=lambda r: -V(f"reg.{rp}.{r}.{q}.por_caso"))],
                   "table": {"columns": ["Región", "Casos", "Facturado (MM$)", "Por caso"],
                             "rows": [[so.REGIONS[r], fmt(V(f"reg.{rp}.{r}.{q}.casos"), 0), fmt(V(f"reg.{rp}.{r}.{q}.facturado_mm"), 0),
                                       money(V(f"reg.{rp}.{r}.{q}.por_caso"))] for r in sorted(regs, key=lambda r: -V(f"reg.{rp}.{r}.{q}.casos"))]},
                   "source": src + " Región del prestador; un caso con prestadores en dos regiones cuenta en ambas."}]
        tab = {"id": "regiones", "label": "Por región", "charts": charts, "text": [],
               "dek": f"{rname}: el facturado por caso va de {money(V('reg.min'))} a {money(V('reg.max'))} fuera de la RM",
               "dek_refs": ["reg.min", "reg.max", *label_refs(package, rname)]}
        sf.topic_fields(tab, f"{rname}: {fmt(V('reg.n'), 0)} regiones con datos publicables", index_refs=["reg.n", *label_refs(package, rname)], kpis=[])
        tabs.append(tab)

    # Topic 6: series (same quarter each year) and the GES share.
    same_q = k["same_q"]
    first = same_q[0]
    yl = lambda qq: so.quarter_short(qq)[-4:]  # noqa: E731
    charts = [{"id": "f14-serie-facturado", "form": "line", "unit": "MM$", "digits": 0,
               "headline": f"Facturado GES, {so.quarter_short(q)[:7]} de cada año",
               "subtitle": "MM$ nominales facturados a las Isapres con código GPP",
               "rows": [{"label": yl(qq), "value": V(f"tot.{qq}.facturado_mm"), "ref": f"tot.{qq}.facturado_mm"} for qq in same_q],
               "table": {"columns": ["Trimestre", "Total (MM$)", "% GES"] + [fl(f) for f in fams],
                         "rows": [[so.quarter_tag(qq), fmt(V(f"tot.{qq}.facturado_mm"), 0), pc(f"tot.{qq}.pct_ges")]
                                  + [fmt(V(f"fam.{f}.{qq}.facturado_mm"), 0) if f"fam.{f}.{qq}.facturado_mm" in v else "sin dato" for f in fams]
                                  for qq in k["qs"]]},
               "source": src + " «Ver datos»: todos los trimestres, MM$ por familia."},
              {"id": "f14-serie-familias", "form": "diverging", "unit": "%", "digits": 1,
               "headline": f"Facturado por caso, {yl(first)} a {yl(q)}",
               "subtitle": f"% de cambio entre {so.quarter_short(first)} y {qs_}, por familia (nominal)",
               "rows": [{"label": fl(f), "value": V(f"fam.{f}.serie.por_caso"), "ref": f"fam.{f}.serie.por_caso"}
                        for f in sorted((f for f in fams if f"fam.{f}.serie.por_caso" in v), key=lambda f: -V(f"fam.{f}.serie.por_caso"))],
               "table": {"columns": ["Trimestre"] + [f"{fl(f)} casos" for f in fams] + [f"{fl(f)} por caso" for f in fams],
                         "rows": [[so.quarter_tag(qq)] + [fmt(V(f"fam.{f}.{qq}.casos"), 0) if f"fam.{f}.{qq}.casos" in v else "sin dato" for f in fams]
                                  + [money(V(f"fam.{f}.{qq}.por_caso")) if f"fam.{f}.{qq}.por_caso" in v else "sin dato" for f in fams]
                                  for qq in k["qs"]]},
               "source": src}]
    tab = {"id": "serie", "label": "Serie desde 2021", "charts": charts,
           "text": [f"Compara el mismo trimestre: {so.quarter_short(first)} con {qs_} (montos nominales). El peso del GES en lo "
                    f"facturado a las Isapres va de {pc('tot.pct_ges.min')} a {pc('tot.pct_ges.max')} entre trimestres."],
           "dek": (f"Desde {yl(first)}: facturado GES {sg('tot.serie.facturado')}, casos {sg('tot.serie.casos')}; peso en Isapres, "
                   f"{pc(f'tot.{q}.pct_ges')}"),
           "dek_refs": ["tot.serie.facturado", "tot.serie.casos", f"tot.{q}.pct_ges"]}
    sf.topic_fields(tab, f"GES: {pc(f'tot.{q}.pct_ges')} de lo facturado en {qs_}", index_refs=[f"tot.{q}.pct_ges"], kpis=[])
    tabs.append(tab)

    # Topic · Nuevos problemas (Dirección 13-nov-2026): the problems the GES 2025–2028 decree added, on their own.
    from .stats_ficha_f4 import GES_DECREE
    new = [p for p in GES_DECREE["added"] if f"prob.{p}.{q}.facturado_mm" in v and f"prob.{p}.{q}.casos" in v]
    if new:
        charts = [{"id": "f14-nuevos-facturado", "form": "bars", "unit": "MM$", "digits": 1,
                   "headline": "Facturado de los problemas nuevos",
                   "subtitle": f"MM$ facturados a las Isapres, {ql}",
                   "rows": [{"label": short(p), "value": V(f"prob.{p}.{q}.facturado_mm"), "ref": f"prob.{p}.{q}.facturado_mm"} for p in new],
                   "table": {"columns": ["Problema", "Casos", "Facturado (MM$)", "Por caso"],
                             "rows": [[f"{p}. {package_name(package, p, q)}", fmt(V(f"prob.{p}.{q}.casos"), 0),
                                       fmt(V(f"prob.{p}.{q}.facturado_mm"), 1), money(V(f"prob.{p}.{q}.por_caso"))] for p in new]},
                   "source": src + " Problema = número del decreto GES (prefijo del código GPP)."}]
        hi = max(new, key=lambda p: V(f"prob.{p}.{q}.por_caso"))
        package.setdefault("constants", []).extend([*GES_DECREE["added"], 29, 2025, 2028, 1])
        tab = {"id": "nuevos", "label": "Nuevos problemas", "charts": charts,
               "text": [f"El {GES_DECREE['name']} ({GES_DECREE['number']}) rige desde el {GES_DECREE['in_force_label']} y sumó "
                        f"los problemas {', '.join(str(p) for p in GES_DECREE['added'][:-1])} y {GES_DECREE['added'][-1]}; no "
                        f"tienen base comparable en {pys}.",
                        f"En {ql} el de mayor facturado por caso es el «{short(hi)}»: {money(V(f'prob.{hi}.{q}.por_caso'))} "
                        f"por caso, con {fmt(V(f'prob.{hi}.{q}.casos'), 0)} casos."],
               "dek": None}
        sf.topic_fields(tab, None, text_refs=[f"prob.{hi}.{q}.por_caso", f"prob.{hi}.{q}.casos"],
                        headline_refs=[], kpis=[])
        tabs.append(tab)

    paragraphs.append(f"En {ql}, las Isapres registraron {mm(f'tot.{q}.facturado_mm')} facturados con código de problema GES, el "
                      f"{pc(f'tot.{q}.pct_ges')} de todo lo facturado en prestaciones bonificadas.")
    sup = k["supresion"][q] or {}
    nq = so.next_quarter(q)
    notes += [
        {"id": "n1", "text": (f"Base trimestral: cada cifra es un flujo del trimestre de bonificación, no un stock; los trimestres no "
                              f"se suman. La comparación es con el mismo trimestre de un año antes ({pys}), sin ajuste estacional; "
                              "los montos son nominales.")},
        {"id": "n2", "text": ("Denominador: el % GES divide lo facturado en filas con código GPP de problema GES por todo lo facturado "
                              "del archivo trimestral de prestaciones bonificadas. Facturado no es lo pagado: es lo que el prestador "
                              "cobró a la Isapre; lo bonificado y el copago son otra cosa.")},
        {"id": "n3", "text": ("Casos = identificadores GES distintos (campo id GES) con al menos una prestación bonificada en el "
                              "trimestre, contados por Isapre y por problema. No son personas (una persona puede tener más de un "
                              "caso) ni casos nuevos. El identificador llega cifrado por la SIS: Alicanto lo usa solo en memoria como "
                              "llave opaca, nunca lo revierte ni lo escribe. Un caso con prestadores en dos regiones cuenta en ambas.")},
        {"id": "n4", "text": ("Problema GES = prefijo numérico del código GPP que cada Isapre informa en la fila (Compendio SIS, "
                              "campo 34). Depende de que la Isapre lo informe: filas GES sin código GPP o con un código ilegible quedan "
                              f"fuera ({fmt(V(f'tot.{q}.filas_gpp_no_parseable'), 0)} filas con código ilegible en {qs_}, "
                              f"{fmt(V(f'tot.{py}.filas_gpp_no_parseable'), 0)} en {pys}).")},
        {"id": "n5", "text": ("El código de problema GES aparece en los archivos SIS desde 2018; antes de 2018 esas columnas vienen "
                              "vacías, por eso no hay serie GES por problema anterior. Esta ficha usa los trimestres desde 2021.")},
        {"id": "n6", "text": ("Cambios de codificación: la imputación al problema usa el código GPP de la fila, no el código de la "
                              "prestación, así que un cambio en los códigos de prestación (por ejemplo, los de quimioterapia) no cambia "
                              "a qué problema se asigna una fila, aunque sí puede cambiar lo facturado. Los nombres de los problemas siguen "
                              "el DS 29 de 2025 (90 problemas); los problemas 88 a 90 rigen desde diciembre de 2025 y no tienen "
                              "comparación anual.")},
        {"id": "n7", "text": (f"Familias: agrupación analítica de Alicanto, no oficial. Regla de publicación: una fila se muestra con "
                              f"≥ {gp.MIN_CASES} casos y ≥ {gp.MIN_PROVIDERS} prestadores distintos; se ocultan además filas para que "
                              "ninguna celda oculta se pueda despejar restando. Por eso la suma de las filas visibles puede ser menor "
                              f"que el total. En {qs_} quedaron ocultas {fmt(sup.get('suprimidas_por_prestadores', 0), 0)} filas por "
                              f"tener menos de {gp.MIN_PROVIDERS} prestadores y {fmt(sup.get('suprimidas_complementarias', 0), 0)} por "
                              "supresión complementaria. Los prestadores llegan con su RUT cifrado y nunca se muestran.")},
        {"id": "n8", "text": ("Archivos: la huella SHA-256 de cada ZIP trimestral de la SIS está en Fuentes, junto con la del archivo "
                              "agregado que usa la ficha y la del agregado de origen; si una no calza, la ficha queda retenida.")},
    ]
    notes.append({"id": "n10", "text": ("Isapre abierta: acepta como afiliado a cualquier persona. Isapre cerrada: solo afilia a "
                                         "trabajadores de una empresa o sector (afiliación restringida). «Abiertas» en el tema por "
                                         "Isapre cuenta las abiertas con fila publicada en ambos años.")})
    if k["closed"]:
        notes.append({"id": "n9", "text": f"{', '.join(nm(i) for i in k['closed'])}: Isapre cerrada (afiliación restringida); aparece marcada."})
    package["constants"] += [sup.get("suprimidas_por_prestadores", 0), sup.get("suprimidas_complementarias", 0), 88, 90, 29, 34, 2018,
                             CPC_SMALL_BASE]
    watch = [{"headline": f"Datos de {so.quarter_label(nq)}.",
              "explanation": "La SIS publica un archivo por trimestre; Alicanto agrega los códigos GES cuando aparece."}]
    late = (decision or {}).get("late_release")
    if late:
        watch = [{"headline": f"Datos de {so.quarter_label(nq)}: sin archivo nuevo.",
                  "explanation": f"Lleva {late['days_late']} días más allá del intervalo esperado."}]
    triggers = (decision or {}).get("triggers") or []
    rule = "nuevo período" if "new_period" in triggers else ("revisión" if "revision" in triggers else "publicación vigente")
    machine = (f"Ficha generada por la regla \"{rule}\" (agregados calculados por Alicanto el {sf.day_label(package['published_at'])}). "
               "Las cifras vienen del paquete de evidencia, sin descargas en este paso; la Lectura Alicanto está desactivada.")
    prim = package["primary_source"]["url"]
    sources = sorted(({**s, "key": key} for key, s in package["sources"].items()), key=lambda x: (x.get("url") != prim, x["key"]))
    return {
        "schema_version": sf.SCHEMA, "id": f"stats-ficha:{FAMILY}:{package['period']}", "family": FAMILY,
        "family_label": cfg["label"], "slug": cfg["slug"], "period": package["period"], "published_at": package["published_at"],
        "release_key": package["release_key"], "evidence_sha256": package["evidence_sha256"],
        "kicker": tpl["kicker"].format(label=cfg["label"], quarter_label=ql),
        "kicker_meta": tpl["kicker_meta"].format(quarter_label=ql, published_label=sf.day_label(package["published_at"])),
        "date_basis": "first_detected", "headline": headline, "headline_type": htype, "dek": dek, "dek_emphasis": None,
        "kpis": kpis[:5], "tabs": sorted(tabs, key=lambda t: TAB_ORDER.index(t["id"])),
        "facts": {"heading": "Qué muestran los datos", "paragraphs": paragraphs, "rendered_in_tabs": True},
        "watch": watch[:2], "notes": notes, "sources": sources, "machine_note": machine,
        "featured": bool((decision or {}).get("featured")), "triggers": triggers, "late_release": late,
        "revisions": package.get("revisions") or [],
    }


def package_name(package: dict, p: int, q: str) -> str:
    return (package.get("kpis") or {}).get("pnames", {}).get(p) or f"Problema {p}"


def label_refs(package: dict, text: str) -> list[str]:
    """Numbers that belong to a problem's name ('Diabetes mellitus tipo 2') are labels, not figures: each becomes a
    package value of unit 'etiqueta' that the line cites, so the verifier still traces every number it reads."""
    out = []
    for _, x, _ in numbers_in(text):
        vid = f"etiqueta.{fmt(x, 0)}"
        package["values"][vid] = value(vid, x, unit="etiqueta", period=package["period"], source=None,
                                       formula="número que forma parte del nombre de un problema GES", kind="derived")
        out.append(vid)
    return out


def plain(package: dict, p: int, q: str) -> str:
    """'Depresión en personas de 15 años y más' → 'Depresión' (prose and index lines: no age figures to trace)."""
    return re.split(r" (?:en|para|de) (?:personas|niños|la persona)| \(| tras | de manejo", package_name(package, p, q))[0]


def fam_of(package: dict, p: int, q: str) -> str:
    return (package.get("kpis") or {}).get("pfam", {}).get(p) or "otros"


def run(root: Path, *, today: date, registry: dict | None = None, llm: bool = True,
        model_call: Callable[..., Any] | None = None, budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    """The Lectura stays off for F14 (no paid call) until Dirección sets ``families.F14.lectura_enabled``."""
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    llm = llm and cfg.get("lectura_enabled") is True
    out = sf.run_family(FAMILY, builder_version=BUILDER_VERSION, build_package=build_package, compose=compose, root=Path(root),
                        today=today, registry=registry, llm=llm, model_call=model_call, budget=budget)
    return so.first_review_gate(out, cfg, Path(root), FAMILY, "f14_")
