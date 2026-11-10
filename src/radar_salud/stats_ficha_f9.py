"""F9 · Benchmark de planes de salud Isapre (SIS, datos abiertos): package, ficha and checks.

Input: ``data/sis_planes_aggregates/<yyyymm>/`` only, written by ``scripts/aggregate_sis_planes.py`` in GitHub Actions
(``.github/workflows/sis-planes-aggregates.yml``): the newest month ``t`` of "Planes de Salud", the month before and the
same month a year earlier, plus "Cobertura Planes" for the months the SIS page links. Nothing is downloaded here and no
plan-level row or plan identifier exists in these files.

What the ficha shows (latest month): the share of cotizantes in plans closed to sale ("planes que ya no se venden"),
the median base price in UF of plans on sale vs. plans in force, plans on sale vs. stock, the prestador-preferente
mix, and Libre Elección coverage of a standard basket of prestaciones. Comparisons in the headline, dek and section
titles use open Isapres only; closed Isapres appear in charts and tables marked «cerrada» with the note «Isapre cerrada
(afiliación restringida)».

Robustness (Dirección's brief, 10-nov-2026): each section title states its finding only when the weighted
(cotizantes) and unweighted (plans) versions agree and the finding also holds in the previous month or a year
earlier; otherwise the title only describes the section. The headline takes the first robust candidate of
``families.F9.headline_priority``.

Reconciliation (any failure → HOLD): every aggregate file names its month, the script version, the SHA-256 and the
row count of its receipt; ZIPs from https://datos.superdesalud.gob.cl, ≤ 1 GiB, ≤ 0,1 % malformed rows; the file holds
only its month; Isapres add up to the system and open + closed = system; on sale + not on sale = all plans; the
modality split adds up; each Isapre code has a name and a type; and the cotizantes and cargas per Isapre equal the SIS
monthly cartera workbook (F1 capture, ``data/market/isapre_portfolio*.json``) within 0,1 % in every month both cover
(at least one), which also confirms that open-data columns 32/33 are cotizantes/cargas.

First publication: like F12/F13, a PASS waits in ``hold/`` (``awaiting_first_review``, previewed on staging at
``web/preview.html``) until ``families.F9.first_review`` records ``reviewed_by`` and ``reviewed_sha256`` = the
ficha's ``evidence_sha256``. The Lectura stays off (``lectura_enabled: false``): no model call.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from . import sis_open_data as so
from . import stats_fichas as sf
from .stats_ficha_f12 import fmt
from .stats_fichas import value

FAMILY = "F9"
BUILDER_VERSION = "f9_planes_v1"
AGG_ROOT = Path("data/sis_planes_aggregates")
SCRIPT_VERSION = "sis_planes_agg_v2"  # mirrors scripts/aggregate_sis_planes.py SCRIPT_VERSION
FILE_HOST = "datos.superdesalud.gob.cl"
MAX_FILE_BYTES = 1 << 30
MAX_MALFORMED_SHARE = 0.001
F1_TOLERANCE_PCT = 0.1
MIN_PLANS = 5
MONTH = re.compile(r"^(20\d{2})(0[1-9]|1[0-2])$")
PLANES, COBERTURA = "Planes de Salud", "Cobertura Planes"
SETS = ("todos", "venta", "no_venta", "vigentes", "cerrados_con_cotizantes")
SET_ID = {"todos": "todos", "venta": "venta", "no_venta": "nv", "vigentes": "vig", "cerrados_con_cotizantes": "cerr"}
CANASTA = {"amb": "ambulatoria", "hosp": "quirúrgica"}
F1_FILES = ("data/market/isapre_portfolio.json", "data/market/isapre_portfolio_2025.json")


def period_of(m: str) -> str:
    return f"{m[:4]}-{m[4:]}"


def month_add(m: str, k: int) -> str:
    n = int(m[:4]) * 12 + int(m[4:]) - 1 + k
    return f"{n // 12}{n % 12 + 1:02d}"


def months(root: Path) -> list[str]:
    base = Path(root) / AGG_ROOT
    return sorted(p.name for p in base.glob("*") if p.is_dir() and MONTH.match(p.name) and (p / f"receipts_{p.name}.json").exists())


def receipt_entry(rec: dict | None, dataset: str, m: str) -> tuple[dict | None, list[str]]:
    if not rec:
        return None, [f"receipt_missing:{m}"]
    f: list[str] = []
    if rec.get("script_version") != SCRIPT_VERSION:
        f.append(f"receipt_script_version:{m}:{rec.get('script_version')}")
    hits = [x for x in rec.get("files") or [] if x.get("dataset") == dataset and x.get("period") == m]
    if len(hits) != 1:
        return None, f + [f"receipt_file_not_unique:{dataset}:{m}:{len(hits)}"]
    x = hits[0]
    tag = f"{dataset}:{m}"
    p = urlsplit(str(x.get("url") or ""))
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
    if not isinstance(ok, int) or ok <= 0 or not isinstance(bad, int):
        f.append(f"rows_not_parsed:{tag}")
    elif bad > MAX_MALFORMED_SHARE * (ok + bad):
        f.append(f"malformed_rows_over_0.1pct:{tag}:{bad}")
    return x, f


def file_failures(d: dict | None, entry: dict | None, name: str, m: str) -> list[str]:
    if d is None:
        return [f"aggregate_missing:{name}"]
    if entry is None:
        return []
    f = []
    if d.get("periodo") != m:
        f.append(f"aggregate_period_mismatch:{name}:{d.get('periodo')}")
    if d.get("script_version") != SCRIPT_VERSION:
        f.append(f"aggregate_script_version:{name}:{d.get('script_version')}")
    if d.get("sha256_archivo") != entry.get("sha256"):
        f.append(f"aggregate_hash_mismatch:{name}")
    if d.get("filas") != (entry.get("parse") or {}).get("rows_ok"):
        f.append(f"aggregate_rows_mismatch:{name}")
    if set(d.get("periodos_en_archivo") or {}) != {m}:
        f.append(f"file_period_not_month:{name}:{','.join(sorted(d.get('periodos_en_archivo') or {}))}")
    return f


def sum_failures(pl: dict, m: str, names: dict[str, str], types: dict[str, str]) -> list[str]:
    """Isapres add up to the system, open + closed = system, on sale + not on sale = all, modality split adds up."""
    g = pl.get("grupos") or {}
    f: list[str] = []
    if pl.get("filas_duplicadas_isapre_plan") or pl.get("errores_numericos") or pl.get("isapres_sin_tipo"):
        f.append(f"plan_file_quality:{m}")
    codes = [k.split(":", 1)[1] for k in g if k.startswith("isapre:")]
    for c in codes:
        if c not in names:
            f.append(f"isapre_without_name:{c}")
        if types.get(c) not in ("open", "closed"):
            f.append(f"isapre_without_type:{c}")
    for metric in ("planes", "cotizantes", "cargas"):
        for s in SETS:
            tot = (g.get("sistema") or {}).get(s, {}).get(metric)
            if sum(g[f"isapre:{c}"][s][metric] for c in codes) != tot:
                f.append(f"isapres_do_not_add:{m}:{s}:{metric}")
            if (g.get("abiertas") or {}).get(s, {}).get(metric, 0) + (g.get("cerradas") or {}).get(s, {}).get(metric, 0) != tot:
                f.append(f"open_closed_do_not_add:{m}:{s}:{metric}")
        for k, cell in g.items():
            if cell["venta"][metric] + cell["no_venta"][metric] != cell["todos"][metric]:
                f.append(f"sale_split_does_not_add:{m}:{k}:{metric}")
    for k, cell in g.items():
        for s in SETS:
            c = cell[s]
            for dim in ("por_modalidad", "por_tipo"):
                if sum(x["planes"] for x in (c.get(dim) or {}).values()) != c["planes"] or \
                        sum(x["cotizantes"] for x in (c.get(dim) or {}).values()) != c["cotizantes"]:
                    f.append(f"split_does_not_add:{m}:{k}:{s}:{dim}")
    if pl.get("filas") != (g.get("sistema") or {}).get("todos", {}).get("planes"):
        f.append(f"plans_not_rows:{m}")
    return f


def f1_observations(root: Path) -> tuple[dict, dict]:
    """(code, metric, 'yyyy-mm') → value and the source workbooks (url → sha256) of the F1 cartera capture."""
    obs, srcs = {}, {}
    for rel in F1_FILES:
        d = so.load_json(Path(root) / rel) or {}
        for o in d.get("observations") or []:
            if o.get("metric_id") in ("cotizantes", "cargas") and isinstance(o.get("official_code"), int):
                obs[(str(o["official_code"]), o["metric_id"], o.get("period"))] = o.get("value")
                if o.get("source_url") and o.get("source_sha256"):
                    srcs.setdefault(o.get("period"), (o["source_url"], o["source_sha256"]))
    return obs, srcs


def f1_failures(pl: dict, m: str, obs: dict) -> tuple[list[str], int]:
    """Cotizantes and cargas per Isapre (open-data columns 32/33) vs. the SIS monthly cartera workbook (F1)."""
    per = period_of(m)
    f, checked = [], 0
    for k, cell in (pl.get("grupos") or {}).items():
        if not k.startswith("isapre:"):
            continue
        code = k.split(":", 1)[1]
        for metric in ("cotizantes", "cargas"):
            ref = obs.get((code, metric, per))
            if ref is None:
                continue
            checked += 1
            got = cell["todos"][metric]
            if not ref or abs(got / ref - 1) * 100 > F1_TOLERANCE_PCT:
                f.append(f"f1_mismatch:{m}:{code}:{metric}:{got}:{ref}")
    return f, checked


def _hold(package: dict, failures: list[str]) -> dict:
    package["reconciliation"].update(ok=False, failures=sorted(set(failures)))
    package.update(findings=[], kpis={}, revisions=[], constants=[])
    return package


def build_package(root: Path, registry: dict | None = None, previous_live: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    root = Path(root)
    names, types = so.isapre_names(root), so.isapre_types(root)
    package: dict[str, Any] = {
        "family": FAMILY, "period": None, "periods": [], "published_at": None, "date_basis": "first_detected",
        "release_key": None, "primary_source": {}, "sources": {}, "values": {}, "entities": [], "entity_codes": [],
        "entity_keys": [], "causal_note": None, "provisional": False,
        "reconciliation": {"ok": False, "failures": [], "checks": [
            "cada archivo agregado nombra el mes, la versión del script y el SHA-256 y las filas del ZIP de su recibo",
            "ZIP ≤ 1 GiB desde https://datos.superdesalud.gob.cl; ≤ 0,1 % de filas malformadas; el archivo trae solo su mes",
            "Isapres = sistema; abiertas + cerradas = sistema; a la venta + no a la venta = todos; modalidad y tipo suman",
            "cotizantes y cargas por Isapre = planilla mensual de cartera SIS (F1) con tolerancia de 0,1 %, en cada mes común",
            "Cobertura: agregados del mismo mes que nombran el SHA-256 de su archivo de Planes",
            "toda Isapre con nombre y tipo (abierta/cerrada) en data/entities/isapres.json"]},
        "lectura_pool": [], "derived_ratios": [], "ranks": [],
    }
    ms = months(root)
    if not ms:
        package["reconciliation"]["failures"] = ["no_month_aggregated"]
        return package
    t = ms[-1]
    package["period"] = period_of(t)
    obs, f1_src = f1_observations(root)
    failures: list[str] = []
    data: dict[str, dict] = {}
    f1_checked = 0
    for m in (t, month_add(t, -1), month_add(t, -12)):
        if m not in ms:
            continue
        folder = root / AGG_ROOT / m
        rec = so.load_json(folder / f"receipts_{m}.json")
        entry, ff = receipt_entry(rec, PLANES, m)
        pl = so.load_json(folder / f"planes_{m}.json")
        ff += file_failures(pl, entry, f"planes_{m}.json", m)
        if not ff:
            ff += sum_failures(pl, m, names, types)
            fx, n = f1_failures(pl, m, obs)
            ff += fx
            f1_checked += n
        cob, centry = None, None
        if (folder / f"cobertura_{m}.json").exists():
            centry, cf = receipt_entry(rec, COBERTURA, m)
            cob = so.load_json(folder / f"cobertura_{m}.json")
            cf += file_failures(cob, centry, f"cobertura_{m}.json", m)
            if cob is not None and entry is not None and cob.get("sha256_planes") != entry.get("sha256"):
                cf.append(f"cobertura_planes_hash_mismatch:{m}")
            if cob is not None and (cob.get("planes_sin_fila_en_planes_de_salud") or 0) > 0.01 * (cob.get("planes_en_archivo") or 0):
                cf.append(f"cobertura_join_over_1pct:{m}")
            ff += cf
        failures += ff if m == t else [f"{'t1' if m == month_add(t, -1) else 't12'}:{x}" for x in ff]
        data[m] = {"rec": rec, "entry": entry, "pl": pl, "cob": cob, "centry": centry}
    if not f1_checked:
        failures.append("f1_no_common_month")
    if failures:
        return _hold(package, failures)

    values: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    ml = lambda m: sf.month_label(period_of(m))  # noqa: E731

    def src(m: str, kind: str) -> str:
        key = f"{kind}_{m}"
        if key not in sources:
            e = data[m]["entry" if kind == "planes" else "centry"]
            label = f"SIS · {'Planes de Salud' if kind == 'planes' else 'Cobertura de Planes'} {ml(m)} (datos abiertos)"
            role = ("ZIP mensual; agregados de Alicanto por Isapre (planes, cotizantes, precio base, modalidad)" if kind == "planes"
                    else "ZIP mensual; cobertura de libre elección por plan y prestación, agregada por Isapre")
            sources[key] = so.source_for(e, label=label, role=role,
                                         locator=f"{(e.get('parse') or {}).get('rows_ok')} filas; agregación en GitHub Actions",
                                         detected=str((data[m]["rec"] or {}).get("generated_at") or "")[:10] or None)
        return key

    def put(vid: str, x, unit: str, m: str, kind: str, loc: str) -> None:
        if x is None:
            return
        values[vid] = value(vid, x, unit=unit, period=period_of(m), source=src(m, kind), locator=loc)

    def derive(vid: str, num: str, den: str, m: str, formula: str) -> None:
        if num in values and den in values and values[den]["value"]:
            values[vid] = value(vid, round(100 * values[num]["value"] / values[den]["value"], 4), unit="%", period=period_of(m),
                                source=None, formula=formula, inputs=[num, den], kind="derived")

    gid = lambda k: {"sistema": "sist", "abiertas": "ab", "cerradas": "ce"}.get(k, k.split(":", 1)[-1])  # noqa: E731
    keys: list[str] = []
    for m, d in data.items():
        for k, cell in d["pl"]["grupos"].items():
            g = gid(k)
            if m == t and k.startswith("isapre:"):
                keys.append(g)
            for s in SETS:
                c, b = cell[s], f"pl.{m}.{g}.{SET_ID[s]}"
                loc = f"planes_{m}.json · {k} · {s}"
                put(f"{b}.planes", c["planes"], "planes", m, "planes", loc)
                put(f"{b}.cot", c["cotizantes"], "cotizantes", m, "planes", loc)
                pr = c["precio_uf"]
                put(f"{b}.med", pr.get("mediana"), "UF", m, "planes", loc + " · precio_uf.mediana")
                put(f"{b}.pond", pr.get("mediana_pond"), "UF", m, "planes", loc + " · precio_uf.mediana_pond")
                put(f"{b}.nprecio", pr.get("n"), "planes", m, "planes", loc + " · precio_uf.n")
                pp = (c.get("por_modalidad") or {}).get("PP") or {"planes": 0, "cotizantes": 0}
                put(f"{b}.pp_planes", pp["planes"], "planes", m, "planes", loc + " · por_modalidad.PP")
                put(f"{b}.pp_cot", pp["cotizantes"], "cotizantes", m, "planes", loc + " · por_modalidad.PP")
            p = f"pl.{m}.{g}"
            derive(f"sh.{m}.{g}.cot_nv", f"{p}.nv.cot", f"{p}.todos.cot", m, "cotizantes en planes no a la venta / cotizantes × 100")
            derive(f"sh.{m}.{g}.planes_nv", f"{p}.cerr.planes", f"{p}.vig.planes", m,
                   "planes con cotizantes no a la venta / planes con cotizantes × 100")
            derive(f"pp.{m}.{g}.venta_planes", f"{p}.venta.pp_planes", f"{p}.venta.planes", m,
                   "planes a la venta con prestador preferente / planes a la venta × 100")
            derive(f"pp.{m}.{g}.venta_cot", f"{p}.venta.pp_cot", f"{p}.venta.cot", m,
                   "cotizantes de planes a la venta con prestador preferente / cotizantes de planes a la venta × 100")
            derive(f"pp.{m}.{g}.vig_planes", f"{p}.vig.pp_planes", f"{p}.vig.planes", m,
                   "planes con cotizantes y prestador preferente / planes con cotizantes × 100")
            derive(f"pp.{m}.{g}.vig_cot", f"{p}.vig.pp_cot", f"{p}.vig.cot", m,
                   "cotizantes en planes con prestador preferente / cotizantes × 100")
        cob = d["cob"]
        if cob:
            for k, cell in cob["grupos"].items():
                g = gid(k)
                put(f"cov.{m}.{g}.planes", cell["planes"], "planes", m, "cobertura", f"cobertura_{m}.json · {k} · planes")
                for w in CANASTA:
                    x = cell["canasta"][w]
                    loc = f"cobertura_{m}.json · {k} · canasta.{w}"
                    put(f"cov.{m}.{g}.{w}.med", x.get("mediana"), "%", m, "cobertura", loc + ".mediana")
                    put(f"cov.{m}.{g}.{w}.pond", x.get("mediana_pond"), "%", m, "cobertura", loc + ".mediana_pond")
                    put(f"cov.{m}.{g}.{w}.media", x.get("media"), "%", m, "cobertura", loc + ".media")
                    put(f"cov.{m}.{g}.{w}.n", x.get("n"), "planes", m, "cobertura", loc + ".n")
    keys = sorted(set(keys), key=lambda c: (types.get(c) != "open", -values[f"pl.{t}.{c}.todos.cot"]["value"]))
    opened = [c for c in keys if types.get(c) == "open"]
    closed = [c for c in keys if types.get(c) == "closed"]
    # F1 workbooks (reconciliation only): shown in Fuentes so the cotizante check can be followed.
    f1_months = sorted((m for m in data if period_of(m) in f1_src), reverse=True)
    for m in f1_months:
        url, sha = f1_src[period_of(m)]
        if any(s["url"] == url for s in sources.values()):
            continue
        sources[f"f1_cartera_{m}"] = sf.source_ref(url=url, sha256=sha, published_at=None, fetched_at=None,
                                                   label=f"SIS · Estadística mensual de cartera de beneficiarios {m[:4]} (planilla)",
                                                   role=f"conciliación: cotizantes y cargas por Isapre, {ml(m)}", locator="hoja del mes")
    ev = so.evidence_sha256(sources)
    detected = str((data[t]["rec"] or {}).get("generated_at") or "")[:10] or None
    package.update(
        period=period_of(t), periods=[period_of(m) for m in sorted(data)], published_at=detected, date_basis="first_detected",
        release_key=sf.release_key(period_of(t), ev), evidence_sha256=ev,
        primary_source={"url": data[t]["entry"]["url"], "sha256": data[t]["entry"]["sha256"]},
        sources=sources, values=values, findings=[],
        entities=[{"code": int(c), "name": names[c]} for c in keys], entity_codes=[int(c) for c in keys],
        revisions=sf.detect_revisions({"values": values}, (previous_live or {}).get("evidence")),
        constants=[0, 1, 5, 7, 30, 50, 100, 256, F1_TOLERANCE_PCT],  # 7: planes al 7 % de la cotización legal; 256: SHA-256
        kpis={"t": t, "t1": month_add(t, -1) if month_add(t, -1) in data else None,
              "t12": month_add(t, -12) if month_add(t, -12) in data else None, "keys": keys, "open": opened, "closed": closed,
              "f1_months": f1_months, "f1_checked": f1_checked},
    )
    package["robustness"] = robustness(package)
    package["reconciliation"].update(ok=True, failures=[])
    return package


def robustness(package: dict) -> dict:
    """Each finding: does it hold weighted (cotizantes) and unweighted (plans), and in t-1 or t-12? (open Isapres)."""
    v, k = package["values"], package["kpis"]
    V = lambda vid: v[vid]["value"] if vid in v else None  # noqa: E731
    others = [m for m in (k["t1"], k["t12"]) if m]
    out: dict[str, dict] = {}

    def check(name: str, fn) -> None:
        now = fn(k["t"])
        then = {m: fn(m) for m in others}
        out[name] = {"t": now, "otros": then, "robusto": bool(now and any(then.values()))}

    def cerr(m):
        a, b = V(f"sh.{m}.ab.cot_nv"), V(f"sh.{m}.ab.planes_nv")
        return a is not None and b is not None and a >= 50 and b >= 50
    check("cerrados_venta", cerr)

    def price(m):
        a = [V(f"pl.{m}.ab.{s}.{x}") for s in ("venta", "vig") for x in ("med", "pond")]
        if None in a:
            return None
        s1, s2 = a[0] - a[2], a[1] - a[3]  # unweighted gap (venta.med − vig.med), weighted gap (venta.pond − vig.pond)
        return "sube" if s1 > 0 and s2 > 0 else "baja" if s1 < 0 and s2 < 0 else None
    sign = price(k["t"])
    now = {m: price(m) for m in others}
    out["precio_venta_vs_vigentes"] = {"t": sign, "otros": now, "robusto": bool(sign and any(x == sign for x in now.values()))}

    def pref(m):
        a, b, c = V(f"pp.{m}.ab.venta_planes"), V(f"pp.{m}.ab.venta_cot"), V(f"pp.{m}.ab.vig_cot")
        d = V(f"pp.{m}.ab.vig_planes")
        return None not in (a, b, c, d) and a > d and b > c
    check("preferente_venta", pref)

    def oferta(m):  # more plans on sale than a year earlier, and more cotizantes in plans on sale
        if not k["t12"] or m == k["t12"]:
            return False
        return V(f"pl.{m}.ab.venta.planes") > V(f"pl.{k['t12']}.ab.venta.planes") and \
            V(f"pl.{m}.ab.venta.cot") > V(f"pl.{k['t12']}.ab.venta.cot")
    o_now = oferta(k["t"])
    o_t1 = oferta(k["t1"]) if k["t1"] else False
    out["oferta_crece"] = {"t": o_now, "otros": {k["t1"]: o_t1} if k["t1"] else {}, "robusto": bool(o_now and o_t1)}

    def cov(m):
        r = {}
        for w in CANASTA:
            a, b = V(f"cov.{m}.ab.{w}.med"), V(f"cov.{m}.ab.{w}.pond")
            r[w] = a is not None and b is not None and a == b
        return all(r.values())
    c_now = cov(k["t"])
    c_then = {m: cov(m) and all(V(f"cov.{m}.ab.{w}.med") == V(f"cov.{k['t']}.ab.{w}.med") for w in CANASTA) for m in others}
    out["cobertura_canasta"] = {"t": c_now, "otros": c_then, "robusto": bool(c_now and any(c_then.values()))}
    return out


def compose(package: dict, registry: dict | None = None, *, today: date, decision: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    tpl = cfg["templates"]
    v, k, rb = package["values"], package["kpis"], package["robustness"]
    t, t1, t12 = k["t"], k["t1"], k["t12"]
    V = lambda vid: v[vid]["value"]  # noqa: E731
    has = lambda vid: vid in v  # noqa: E731
    pc = lambda vid: fmt(V(vid), 1) + "%"  # noqa: E731
    uf = lambda vid: fmt(V(vid), 2) + " UF"  # noqa: E731
    n0 = lambda vid: fmt(V(vid), 0)  # noqa: E731
    names = {str(e["code"]): e["name"] for e in package["entities"]}
    ml = sf.month_label(period_of(t))
    tag = lambda m: sf.month_label(period_of(m))  # noqa: E731
    keys, opened, closed = k["keys"], k["open"], k["closed"]
    src = "SIS, datos abiertos «Planes de Salud» (ZIP mensual); agregados de Alicanto."
    csrc = "SIS, datos abiertos «Cobertura de Planes» (ZIP mensual), unida a «Planes de Salud» del mismo mes; agregados de Alicanto."

    def row(c: str, vid: str) -> dict:
        return {"label": names[c], "value": V(vid), "ref": vid, **({"tag": "cerrada"} if c in closed else {})}

    def ordered(fn, ids) -> list[str]:
        """Open Isapres by value (descending), then closed ones; only those with a value."""
        o = sorted([c for c in opened if has(fn(c))], key=lambda c: -V(fn(c)))
        return o + sorted([c for c in closed if has(fn(c))], key=lambda c: -V(fn(c))) if ids is None else o

    def bars(cid, headline, subtitle, fn, table, source=src, unit="%", digits=1) -> dict:
        rows = [row(c, fn(c)) for c in ordered(fn, None)][:12]
        return {"id": cid, "form": "bars", "unit": unit, "digits": digits, "headline": headline, "subtitle": subtitle,
                "rows": rows, "table": table, "source": source}

    cell = lambda vid, f: f(vid) if has(vid) else "menos de 5 planes"  # noqa: E731
    lab = lambda c: names[c] + (" (cerrada)" if c in closed else "")  # noqa: E731
    tabs, paragraphs = [], []

    # 1. Plans closed to sale.
    fn = lambda c: f"sh.{t}.{c}.cot_nv"  # noqa: E731
    cols = ["Isapre", "Cotizantes", "En planes que ya no se venden", "Planes con cotizantes que ya no se venden"]
    cols += [f"Cotizantes en planes que ya no se venden, {tag(m)}" for m in (t1, t12) if m]
    trows = [[lab(c), n0(f"pl.{t}.{c}.todos.cot"), pc(f"sh.{t}.{c}.cot_nv"), pc(f"sh.{t}.{c}.planes_nv")]
             + [pc(f"sh.{m}.{c}.cot_nv") if has(f"sh.{m}.{c}.cot_nv") else "sin dato" for m in (t1, t12) if m] for c in keys]
    trows.append(["Isapres abiertas", n0(f"pl.{t}.ab.todos.cot"), pc(f"sh.{t}.ab.cot_nv"), pc(f"sh.{t}.ab.planes_nv")]
                 + [pc(f"sh.{m}.ab.cot_nv") for m in (t1, t12) if m])
    charts = [bars("f9-cerrados", "Cotizantes en planes que ya no se venden",
                   f"% de los cotizantes de cada Isapre en planes no comercializados en {ml}", fn, {"columns": cols, "rows": trows})]
    o = ordered(fn, "open")
    if rb["cerrados_venta"]["robusto"] and len(o) >= 2 and V(fn(o[-1])) > 50:  # "en todas": the lowest open Isapre > 50 %
        dek = (f"En todas las abiertas la mayoría de los cotizantes está en planes que ya no se venden: de {pc(fn(o[-1]))} "
               f"en {names[o[-1]]} a {pc(fn(o[0]))} en {names[o[0]]}")
        drefs = [fn(o[-1]), fn(o[0])]
    else:
        dek, drefs = "Cotizantes en planes que ya no se venden, por Isapre", []
    tab = {"id": "cerrados", "label": "Planes cerrados a venta", "charts": charts, "text": [], "dek": dek, "dek_refs": drefs}
    sf.topic_fields(tab, f"Abiertas: {pc(f'sh.{t}.ab.cot_nv')} de los cotizantes", index_refs=[f"sh.{t}.ab.cot_nv"], kpis=[])
    tabs.append(tab)

    # 2. Base price: on sale vs in force.
    fv = lambda c: f"pl.{t}.{c}.venta.med"  # noqa: E731
    cols = ["Isapre", "A la venta: mediana", "A la venta: mediana por cotizante", "Vigentes: mediana",
            "Vigentes: mediana por cotizante", "Planes a la venta con precio en UF o $"]
    trows = [[lab(c), cell(f"pl.{t}.{c}.venta.med", uf), cell(f"pl.{t}.{c}.venta.pond", uf), cell(f"pl.{t}.{c}.vig.med", uf),
              cell(f"pl.{t}.{c}.vig.pond", uf), n0(f"pl.{t}.{c}.venta.nprecio")] for c in keys]
    trows.append(["Isapres abiertas"] + [cell(f"pl.{t}.ab.{s}", uf) for s in ("venta.med", "venta.pond", "vig.med", "vig.pond")]
                 + [n0(f"pl.{t}.ab.venta.nprecio")])
    charts = [bars("f9-precio-venta", "Precio base de los planes a la venta",
                   f"Mediana del precio base en UF de los planes comercializados en {ml}", fv, {"columns": cols, "rows": trows},
                   unit="UF", digits=2),
              bars("f9-precio-vigentes", "Precio base de los planes vigentes",
                   f"Mediana por cotizante del precio base en UF de los planes con cotizantes, {ml}",
                   lambda c: f"pl.{t}.{c}.vig.pond",
                   {"columns": ["Isapre", "Mediana por cotizante", "Mediana por plan", "Planes con cotizantes"],
                    "rows": [[lab(c), cell(f"pl.{t}.{c}.vig.pond", uf), cell(f"pl.{t}.{c}.vig.med", uf), n0(f"pl.{t}.{c}.vig.planes")]
                             for c in keys]}, unit="UF", digits=2)]
    pr = rb["precio_venta_vs_vigentes"]
    a, b = f"pl.{t}.ab.venta.med", f"pl.{t}.ab.vig.med"
    if pr["robusto"]:
        word = "mayor" if pr["t"] == "sube" else "menor"
        dek = f"En las abiertas, los planes a la venta tienen un precio base {word} que los vigentes: mediana de {uf(a)} frente a {uf(b)}"
    else:
        dek = f"Mediana del precio base: {uf(a)} a la venta y {uf(b)} en los planes vigentes (abiertas)"
    tab = {"id": "precio", "label": "Precio base", "charts": charts, "text": [], "dek": dek, "dek_refs": [a, b]}
    sf.topic_fields(tab, f"A la venta {uf(a)} · vigentes {uf(b)}", index_refs=[a, b], kpis=[])
    tabs.append(tab)

    # 3. Plans on sale vs stock.
    fo = lambda c: f"pl.{t}.{c}.venta.planes"  # noqa: E731
    cols = ["Isapre", "Planes a la venta", "Planes con cotizantes", "Planes en el archivo"]
    if t12:
        cols.append(f"Planes a la venta, {tag(t12)}")
    trows = [[lab(c), n0(fo(c)), n0(f"pl.{t}.{c}.vig.planes"), n0(f"pl.{t}.{c}.todos.planes")]
             + ([n0(f"pl.{t12}.{c}.venta.planes") if has(f"pl.{t12}.{c}.venta.planes") else "sin dato"] if t12 else []) for c in keys]
    trows.append(["Isapres abiertas", n0(f"pl.{t}.ab.venta.planes"), n0(f"pl.{t}.ab.vig.planes"), n0(f"pl.{t}.ab.todos.planes")]
                 + ([n0(f"pl.{t12}.ab.venta.planes")] if t12 else []))
    charts = [bars("f9-oferta", "Planes a la venta", f"Planes comercializados por cada Isapre en {ml}", fo,
                   {"columns": cols, "rows": trows}, unit="planes", digits=0)]
    if rb["oferta_crece"]["robusto"]:
        dek = (f"Las abiertas tienen {n0(f'pl.{t}.ab.venta.planes')} planes a la venta, frente a "
               f"{n0(f'pl.{t12}.ab.venta.planes')} en {tag(t12)}")
        drefs = [f"pl.{t}.ab.venta.planes", f"pl.{t12}.ab.venta.planes"]
    else:
        dek = (f"Las abiertas tienen {n0(f'pl.{t}.ab.venta.planes')} planes a la venta y "
               f"{n0(f'pl.{t}.ab.vig.planes')} con cotizantes")
        drefs = [f"pl.{t}.ab.venta.planes", f"pl.{t}.ab.vig.planes"]
    tab = {"id": "oferta", "label": "Oferta y stock", "charts": charts, "text": [], "dek": dek, "dek_refs": drefs}
    sf.topic_fields(tab, f"{n0(f'pl.{t}.ab.venta.planes')} a la venta · {n0(f'pl.{t}.ab.vig.planes')} con cotizantes",
                    index_refs=[f"pl.{t}.ab.venta.planes", f"pl.{t}.ab.vig.planes"], kpis=[])
    tabs.append(tab)

    # 4. Modality: prestador preferente vs libre elección.
    fp = lambda c: f"pp.{t}.{c}.venta_planes"  # noqa: E731
    fq = lambda c: f"pp.{t}.{c}.vig_cot"  # noqa: E731
    cols = ["Isapre", "Preferente: % de planes a la venta", "Preferente: % de cotizantes de planes a la venta",
            "Preferente: % de cotizantes vigentes"]
    trows = [[lab(c), cell(fp(c), pc), cell(f"pp.{t}.{c}.venta_cot", pc), cell(fq(c), pc)] for c in keys]
    trows.append(["Isapres abiertas", pc(fp("ab")), pc(f"pp.{t}.ab.venta_cot"), pc(fq("ab"))])
    charts = [bars("f9-preferente-venta", "Prestador preferente en la venta", f"% de los planes a la venta con prestador preferente, {ml}",
                   fp, {"columns": cols, "rows": trows}),
              bars("f9-preferente-stock", "Prestador preferente en la cartera",
                   f"% de los cotizantes en planes con prestador preferente, {ml}", fq,
                   {"columns": ["Isapre", "% de cotizantes", "Cotizantes en preferente"],
                    "rows": [[lab(c), pc(fq(c)), n0(f"pl.{t}.{c}.vig.pp_cot")] for c in keys if has(fq(c))]})]
    if rb["preferente_venta"]["robusto"]:
        dek = (f"En las abiertas, el {pc(fp('ab'))} de los planes a la venta es con prestador preferente, frente al "
               f"{pc(fq('ab'))} de los cotizantes vigentes")
    else:
        dek = f"Prestador preferente: {pc(fp('ab'))} de los planes a la venta y {pc(fq('ab'))} de los cotizantes (abiertas)"
    tab = {"id": "modalidad", "label": "Modalidad de atención", "charts": charts, "text": [], "dek": dek,
           "dek_refs": [fp("ab"), fq("ab")]}
    sf.topic_fields(tab, f"Preferente: {pc(fp('ab'))} de la venta · {pc(fq('ab'))} de cotizantes", index_refs=[fp("ab"), fq("ab")], kpis=[])
    tabs.append(tab)

    # 5. Libre Elección coverage of the standard basket (only when Cobertura of t exists).
    has_cov = has(f"cov.{t}.ab.amb.med") and has(f"cov.{t}.ab.hosp.med")
    if has_cov:
        fa = lambda c: f"cov.{t}.{c}.amb.med"  # noqa: E731
        fh = lambda c: f"cov.{t}.{c}.hosp.med"  # noqa: E731
        cols = ["Isapre", "Canasta ambulatoria: mediana", "Ambulatoria: mediana por cotizante", "Canasta quirúrgica: mediana",
                "Quirúrgica: mediana por cotizante", "Planes con cobertura informada"]
        if t12:
            cols.append(f"Quirúrgica: mediana, {tag(t12)}")
        ck = [c for c in keys if has(f"cov.{t}.{c}.planes")]
        trows = [[lab(c), cell(fa(c), pc), cell(f"cov.{t}.{c}.amb.pond", pc), cell(fh(c), pc), cell(f"cov.{t}.{c}.hosp.pond", pc),
                  n0(f"cov.{t}.{c}.planes")] + ([cell(f"cov.{t12}.{c}.hosp.med", pc)] if t12 else []) for c in ck]
        trows.append(["Isapres abiertas", pc(fa("ab")), pc(f"cov.{t}.ab.amb.pond"), pc(fh("ab")), pc(f"cov.{t}.ab.hosp.pond"),
                      n0(f"cov.{t}.ab.planes")] + ([cell(f"cov.{t12}.ab.hosp.med", pc)] if t12 else []))
        charts = [bars("f9-cob-amb", "Cobertura de libre elección, canasta ambulatoria",
                       f"Mediana entre planes individuales a la venta del % bonificado promedio de la canasta, {ml}", fa,
                       {"columns": cols, "rows": trows}, source=csrc),
                  bars("f9-cob-hosp", "Cobertura de libre elección, canasta quirúrgica",
                       f"Mediana entre planes individuales a la venta del % bonificado promedio de la canasta, {ml}", fh,
                       {"columns": ["Isapre", "Mediana", "Media", "Planes"],
                        "rows": [[lab(c), cell(fh(c), pc), cell(f"cov.{t}.{c}.hosp.media", pc), cell(f"cov.{t}.{c}.hosp.n", n0)]
                                 for c in ck if has(f"cov.{t}.{c}.hosp.n")]}, source=csrc)]
        if rb["cobertura_canasta"]["robusto"]:
            dek = (f"Libre elección en las abiertas: mediana de {pc(fa('ab'))} en la canasta ambulatoria y "
                   f"{pc(fh('ab'))} en la quirúrgica, por plan y por cotizante")
        else:
            dek = f"Libre elección en las abiertas: canasta ambulatoria {pc(fa('ab'))}, quirúrgica {pc(fh('ab'))} (mediana por plan)"
        tab = {"id": "cobertura", "label": "Cobertura libre elección", "charts": charts, "text": [], "dek": dek,
               "dek_refs": [fa("ab"), fh("ab")]}
        sf.topic_fields(tab, f"Ambulatoria {pc(fa('ab'))} · quirúrgica {pc(fh('ab'))}", index_refs=[fa("ab"), fh("ab")], kpis=[])
        tabs.append(tab)

    # KPI cards.
    kp = []
    kp.append({"id": "cerrados", "label": "Cotizantes en planes que ya no se venden", "value": pc(f"sh.{t}.ab.cot_nv"), "prov": "C",
               "lines": [f"{n0(f'pl.{t}.ab.nv.cot')} de {n0(f'pl.{t}.ab.todos.cot')} cotizantes de Isapres abiertas"]
               + ([f"{tag(t12)}: {pc(f'sh.{t12}.ab.cot_nv')}"] if t12 else []),
               "refs": [f"sh.{t}.ab.cot_nv", f"pl.{t}.ab.nv.cot", f"pl.{t}.ab.todos.cot"] + ([f"sh.{t12}.ab.cot_nv"] if t12 else [])})
    kp.append({"id": "oferta", "label": "Planes a la venta", "value": n0(f"pl.{t}.ab.venta.planes"), "prov": "C",
               "lines": [f"{n0(f'pl.{t}.ab.vig.planes')} planes con cotizantes (abiertas)"]
               + ([f"{tag(t12)}: {n0(f'pl.{t12}.ab.venta.planes')} a la venta"] if t12 else []),
               "refs": [f"pl.{t}.ab.venta.planes", f"pl.{t}.ab.vig.planes"] + ([f"pl.{t12}.ab.venta.planes"] if t12 else [])})
    kp.append({"id": "precio", "label": "Precio base a la venta (mediana)", "value": uf(f"pl.{t}.ab.venta.med"), "prov": "C",
               "lines": [f"Vigentes: {uf(f'pl.{t}.ab.vig.med')} por plan, {uf(f'pl.{t}.ab.vig.pond')} por cotizante"],
               "refs": [f"pl.{t}.ab.venta.med", f"pl.{t}.ab.vig.med", f"pl.{t}.ab.vig.pond"]})
    kp.append({"id": "preferente", "label": "Planes a la venta con prestador preferente", "value": pc(f"pp.{t}.ab.venta_planes"),
               "prov": "C", "lines": [f"{pc(f'pp.{t}.ab.vig_cot')} de los cotizantes vigentes"],
               "refs": [f"pp.{t}.ab.venta_planes", f"pp.{t}.ab.vig_cot"]})
    if has_cov:
        kp.append({"id": "cobertura", "label": "Cobertura libre elección (mediana)", "value": pc(f"cov.{t}.ab.amb.med"), "prov": "C",
                   "lines": [f"Canasta ambulatoria; quirúrgica {pc(f'cov.{t}.ab.hosp.med')}"],
                   "refs": [f"cov.{t}.ab.amb.med", f"cov.{t}.ab.hosp.med"]})

    # Headline: first robust candidate of the configured priority.
    lead = None
    for cand in cfg.get("headline_priority") or []:
        if cand == "cerrados_venta" and rb["cerrados_venta"]["robusto"]:
            lead = f"El {pc(f'sh.{t}.ab.cot_nv')} de los cotizantes de Isapres abiertas está en planes que ya no se venden, {ml}"
        elif cand == "precio_venta_vs_vigentes" and rb["precio_venta_vs_vigentes"]["robusto"]:
            lead = (f"Los planes a la venta en Isapres abiertas tienen una mediana de {uf(f'pl.{t}.ab.venta.med')}, frente a "
                    f"{uf(f'pl.{t}.ab.vig.med')} de los vigentes, {ml}")
        elif cand == "preferente_venta" and rb["preferente_venta"]["robusto"]:
            lead = (f"El {pc(f'pp.{t}.ab.venta_planes')} de los planes a la venta en Isapres abiertas es con prestador preferente, "
                    f"{ml}")
        if lead and len(lead) <= 140:
            break
        lead = None
    headline = lead or f"Planes de salud Isapre, {ml}"
    dek = (f"Las Isapres abiertas venden {n0(f'pl.{t}.ab.venta.planes')} planes, con mediana de {uf(f'pl.{t}.ab.venta.med')}; "
           f"{n0(f'pl.{t}.ab.nv.cot')} cotizantes siguen en planes que ya no se ofrecen.")
    paragraphs.append(f"En {ml}, {n0(f'pl.{t}.ab.cerr.planes')} planes que ya no se venden aún tienen cotizantes en las Isapres abiertas.")

    rbx = {"cerrados_venta": "planes que ya no se venden", "precio_venta_vs_vigentes": "precio a la venta frente a vigentes",
           "preferente_venta": "prestador preferente en la venta", "oferta_crece": "más planes a la venta que hace un año",
           "cobertura_canasta": "cobertura de la canasta"}
    held = [rbx[x] for x, r in rb.items() if r["robusto"]]
    notes = [
        {"id": "n1", "text": "Base mensual: cada cifra es un stock al último día del mes (planes y cotizantes), no un flujo, y los meses "
                             "no se suman. «Vigente» es un plan con al menos un cotizante; «a la venta» es un plan comercializado en el "
                             "mes; «que ya no se vende» es un plan no comercializado."},
        {"id": "n2", "text": "Denominador: el % de cotizantes divide por todos los cotizantes de la Isapre; el % de planes divide por los "
                             "planes a la venta o por los planes con cotizantes, según el rótulo. La mediana «por plan» cuenta cada plan una "
                             "vez; la mediana «por cotizante» pondera cada plan por sus cotizantes."},
        {"id": "n3", "text": "Precio base: el del archivo maestro de planes (Compendio SIS), en UF; los planes en pesos los informa la "
                             "SIS convertidos a UF y los planes pactados al 7 % de la cotización legal quedan fuera de las medianas. No es el "
                             "precio final que paga cada persona (factor de riesgo, cargas, GES y beneficios adicionales)."},
        {"id": "n4", "text": "Robustez: un título de sección enuncia su hallazgo solo si coinciden la versión por plan y la ponderada por "
                             "cotizantes y si el hallazgo se repite en el mes anterior o un año antes; si no, el título solo describe. "
                             + ("Hallazgos que pasan: " + "; ".join(held) + "." if held else "Ningún hallazgo pasa en este mes.")},
        {"id": "n5", "text": "Celda mínima: una mediana se publica con al menos 5 planes y una mediana por cotizante con al menos 5 planes "
                             "con cotizantes y 30 cotizantes; si no, la tabla dice «menos de 5 planes»."},
        {"id": "n6", "text": "Conciliación: los cotizantes y las cargas por Isapre del archivo de planes calzan con la planilla mensual de "
                             "cartera de la SIS con tolerancia de 0,1 % en cada mes que ambos cubren (se ve en Fuentes)."},
    ]
    if has_cov:
        notes.append({"id": "n7", "text": "Cobertura: archivo maestro de coberturas (Título IV del Compendio), que informa la cobertura de libre "
                                          "elección de los planes individuales a la venta para cada prestación del arancel Fonasa. "
                                          "La cobertura preferente, que rige en la mayoría de los planes a la venta, no está en ese "
                                          "archivo. Canasta ambulatoria: consulta de medicina general, hemograma, perfil bioquímico, "
                                          "ecografía abdominal y consulta de psicólogo; quirúrgica: parto, cesárea y colecistectomía "
                                          "por videolaparoscopía. Cuando un plan informa más de un registro para una prestación, se "
                                          "toma el % más alto. No incluye topes."})
    if closed:
        notes.append({"id": "n0", "text": f"{', '.join(names[c] for c in closed)}: Isapre cerrada (afiliación restringida). Aparecen "
                                          "marcadas en los gráficos y tablas; las comparaciones del título, la bajada y los títulos de "
                                          "sección usan solo Isapres abiertas."})
    notes.append({"id": "n8", "text": "Archivos: ZIP mensuales de datos abiertos de la SIS. Su huella SHA-256 está en Fuentes; cada agregado "
                                      "nombra esa misma huella y, si no calza, la ficha queda retenida. La tabla de factores no se usa: "
                                      "la SIS dejó de publicarla tras la tabla única de factores."})
    nm = month_add(t, 1)
    late = (decision or {}).get("late_release")
    watch = [{"headline": f"Datos de {tag(nm)}.",
              "explanation": "La SIS publica un ZIP de planes por mes en datos abiertos; Alicanto lo agrega cuando aparece."}]
    if late:
        watch = [{"headline": f"Datos de {tag(nm)}: sin archivo nuevo.",
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
        "kicker": tpl["kicker"].format(label=cfg["label"], month_label=ml),
        "kicker_meta": tpl["kicker_meta"].format(month_label=ml, published_label=sf.day_label(package["published_at"])),
        "date_basis": "first_detected", "headline": headline, "headline_type": "default", "dek": dek, "dek_emphasis": None,
        "kpis": kp[:5], "tabs": tabs,
        "facts": {"heading": "Qué muestran los datos", "paragraphs": paragraphs, "rendered_in_tabs": True},
        "watch": watch[:2], "notes": notes, "sources": sources, "machine_note": machine, "robustness": package["robustness"],
        "featured": bool((decision or {}).get("featured")), "triggers": triggers, "late_release": late,
        "revisions": package.get("revisions") or [],
    }


def run(root: Path, *, today: date, registry: dict | None = None, llm: bool = True,
        model_call: Callable[..., Any] | None = None, budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    """The Lectura stays off for F9 (no paid call) until Dirección sets ``families.F9.lectura_enabled``."""
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    llm = llm and cfg.get("lectura_enabled") is True
    out = sf.run_family(FAMILY, builder_version=BUILDER_VERSION, build_package=build_package, compose=compose, root=Path(root),
                        today=today, registry=registry, llm=llm, model_call=model_call, budget=budget)
    return so.first_review_gate(out, cfg, Path(root), FAMILY, "f9_")
