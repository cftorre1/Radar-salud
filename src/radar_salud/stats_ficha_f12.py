"""F12 · Prestaciones bonificadas (SIS, datos abiertos): package, ficha and checks.

Input: ``data/sis_open_data_aggregates/<quarter>/`` only (``sis_open_data.load_quarter``): the latest quarter and the
one before, aggregated in GitHub Actions from the SIS quarterly ZIP "Prestaciones Bonificadas" (and the Arancel Isapre
for code descriptions). Nothing is downloaded here; no provider, beneficiary or folio identifier exists in the input.

What the ficha shows (Dirección 5-nov-2026):

- % bonificado and % copago over facturado, by Isapre and for the system (Σ bonificado / Σ facturado);
- the same provider, a different Isapre: for every pseudonymous provider × Fonasa code billed by ≥ 2 Isapres, each
  Isapre's bonificado per unit against the mean of the Isapres of that cell (median per Isapre). The coverage gap is
  the highest minus the lowest median among Isapres with at least ``cross_min_cells`` cells;
- prices of the most frequent Fonasa codes: national median, p25–p75 and p75/p25 (dispersion), and by region under
  the disclosure rule: a price only with ≥ 2 distinct providers and ≥ 30 frecuencia (p25–p75 only with ≥ 3); with
  exactly 1 provider no price, only a concentration flag; every provider counts nationally; the top provider's share
  of frecuencia is always shown;
- concentration of facturado among providers by region (HHI, top-1, top-5).

Reconciliation (any failure → HOLD): the files of both quarters match their receipts (``sis_open_data``); the
Isapre table adds up (ambulatoria + hospitalaria = total per Isapre); every Isapre code has a name; every price row
obeys the disclosure rule (re-checked here, not trusted); the national cell of a code counts at least as many
providers as any of its regions; the cross-Isapre index is valid only when the aggregator's ID check says so.

First publication: like F4/F7, a PASS waits in ``hold/`` (``awaiting_first_review``, previewed on staging) until
``families.F12.first_review`` records ``reviewed_by`` and ``reviewed_sha256`` = the ficha's ``evidence_sha256``. The
Lectura stays off (``lectura_enabled: false``): no model call.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from statistics import median
from typing import Any, Callable

from . import sis_open_data as so
from . import stats_fichas as sf
from .stats_fichas import value
from .weekly_freshness import numbers_in

FAMILY = "F12"
BUILDER_VERSION = "f12_prestaciones_v1"
DATASET = "Prestaciones Bonificadas"
PRICE_MIN_PROVIDERS, PRICE_MIN_FREQ, IQR_MIN_PROVIDERS = 2, 30, 3
NATIONAL = "NACIONAL"
AMB, HOSP = "amb", "hosp"
# "Casi no cambia" is written only when every qualified Isapre's median facturado index is within ± this many %.
FACT_STABLE_MAX = 5.0


def fmt(x: float, digits: int = 1, signed: bool = False) -> str:
    """Half-up rounding (the verifier's rule), Chilean separators, typographic minus."""
    q = Decimal(str(float(x))).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    if q == 0:
        q = abs(q)
    s = f"{abs(q):,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return ("−" if q < 0 else "+" if signed and q > 0 else "") + s


def money(x: float) -> str:
    return "$" + fmt(x, 0)


def attention(label: str) -> str | None:
    n = sf._fold(label)
    return AMB if "ambul" in n else HOSP if "hospital" in n else None


def disclosure_failures(cols: list[str], rows: list[list]) -> list[str]:
    """The disclosure rule is re-checked on every price row, never trusted from the aggregator."""
    f = []
    for raw in rows:
        r = dict(zip(cols, raw))
        tag = f"{r.get('codigo_prestacion')}:{r.get('region')}"
        n, freq, est = r.get("n_prestadores"), r.get("frecuencia"), r.get("estado")
        price = [r.get(k) for k in ("precio_mediana", "precio_p25", "precio_p75")]
        if not isinstance(n, int) or not isinstance(freq, int) or n < 1:
            f.append(f"price_row_counts_invalid:{tag}")
            continue
        sh = r.get("share_prestador_mayor_pct")
        if not isinstance(sh, (int, float)) or not 0 < sh <= 100:
            f.append(f"price_row_without_top_share:{tag}")
        if n == 1:
            if est != "concentracion_un_prestador" or any(x is not None for x in price) or r.get("facturado") is not None \
                    or r.get("pct_bonificado") is not None:
                f.append(f"single_provider_with_price:{tag}")
        elif n >= PRICE_MIN_PROVIDERS and freq >= PRICE_MIN_FREQ:
            if est != "publicable" or price[0] is None or ((price[1] is None) != (n < IQR_MIN_PROVIDERS)) \
                    or ((price[2] is None) != (n < IQR_MIN_PROVIDERS)):
                f.append(f"publishable_row_inconsistent:{tag}")
        elif est != "suprimido_frecuencia_menor_30" or any(x is not None for x in price):
            f.append(f"suppressed_row_with_price:{tag}")
    return f


def _quarter(root: Path, q: str, names: dict[str, str]) -> tuple[dict, list[str]]:
    data, failures = so.load_quarter(root, q, DATASET)
    if failures:
        return data, failures
    files = data["files"]
    res = files[f"prestaciones_{q}_resumen.json"]
    prices = files[f"prestaciones_{q}_precios_fonasa_region.json"]
    cross = files[f"prestaciones_{q}_indice_isapre_mismo_prestador.json"]
    by: dict[str, dict] = {}
    for row in res.get("por_isapre_tipo_atencion") or []:
        code = str(row.get("isapre"))
        kind = "total" if row.get("tipo_atencion") == "TOTAL" else attention(str(row.get("tipo_atencion")))
        if kind is None:
            failures.append(f"attention_unknown:{code}:{row.get('tipo_atencion')}")
            continue
        by.setdefault(code, {})[kind] = row
    for code, kinds in sorted(by.items()):
        if code not in names:
            failures.append(f"isapre_without_name:{code}")
        tot = kinds.get("total")
        parts = [kinds[k] for k in (AMB, HOSP) if k in kinds]
        if not tot or len(parts) != 2:
            failures.append(f"isapre_table_incomplete:{code}")
            continue
        for key in ("frecuencia", "facturado", "bonificado", "copago", "registros"):
            if abs(sum(p.get(key) or 0 for p in parts) - (tot.get(key) or 0)) > 1:
                failures.append(f"isapre_split_mismatch:{code}:{key}")
        if not (tot.get("facturado") or 0) > 0:
            failures.append(f"isapre_facturado_not_positive:{code}")
    cols = prices.get("columns") or []
    if (prices.get("regla") or {}).get("version") != "precio_v2_dir_2026_11_05":
        failures.append(f"disclosure_rule_version:{q}")
    failures += disclosure_failures(cols, prices.get("rows") or [])
    cells: dict[tuple, dict] = {(r[0], r[1]): dict(zip(cols, r)) for r in prices.get("rows") or []}
    for code in {c for c, _ in cells}:
        regs = [v for (c, reg), v in cells.items() if c == code and reg != NATIONAL]
        nat = cells.get((code, NATIONAL))
        if regs and (not nat or nat["n_prestadores"] < max(v["n_prestadores"] for v in regs)):
            failures.append(f"national_cell_smaller_than_region:{code}")
    for row in cross.get("resumen_por_isapre") or []:
        if str(row.get("isapre")) not in names:
            failures.append(f"isapre_without_name:{row.get('isapre')}")
    data.update(by_isapre=by, cells=cells, cross=cross, resumen=res, prices=prices,
                top=files[f"prestaciones_{q}_top_codigos.json"],
                consistency=so.load_json(Path(root) / so.AGG_ROOT / q / f"prestaciones_{q}_consistencia_ids.json"))
    return data, sorted(set(failures))


def _hold(package: dict, failures: list[str]) -> dict:
    package["reconciliation"].update(ok=False, failures=failures)
    package.update(findings=[], kpis={}, revisions=[], constants=[])
    return package


def build_package(root: Path, registry: dict | None = None, previous_live: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    root = Path(root)
    names = so.isapre_names(root)
    qs = [q for q in so.quarters(root)
          if (so.load_json(root / so.AGG_ROOT / q / f"receipts_{q}.json") or {}).get("script_version") == so.SCRIPT_VERSION
          and any(f.get("dataset") == DATASET for f in (so.load_json(root / so.AGG_ROOT / q / f"receipts_{q}.json") or {}).get("files") or [])]
    package: dict[str, Any] = {
        "family": FAMILY, "period": None, "periods": [], "published_at": None, "date_basis": "first_detected",
        "release_key": None, "primary_source": {}, "sources": {}, "values": {}, "entities": [], "entity_codes": [],
        "entity_keys": [], "causal_note": None, "provisional": False,
        "reconciliation": {"ok": False, "failures": [], "checks": [
            "cada archivo agregado nombra el trimestre, la versión del script y el SHA-256 del ZIP de su recibo",
            "filas agregadas = filas leídas del ZIP; ≤ 0,1 % de filas malformadas; ZIP ≤ 1 GiB desde datos.superdesalud.gob.cl",
            "el trimestre declarado dentro del archivo es el de la carpeta",
            "ambulatoria + hospitalaria = total, por Isapre y por cada monto",
            "regla de divulgación re-verificada en cada fila de precios (1 prestador: sin precio)",
            "la celda nacional de un código cuenta al menos tantos prestadores como cualquiera de sus regiones",
            "toda Isapre con nombre en data/entities/isapres.json"]},
        "lectura_pool": [], "derived_ratios": [], "ranks": [],
    }
    if not qs:
        package["reconciliation"]["failures"] = ["no_quarter_aggregated"]
        return package
    q = qs[-1]
    package["period"] = so.period_of(q)
    cur, failures = _quarter(root, q, names)
    pq = so.previous_quarter(q)
    prev = None
    if pq in qs:
        prev, pf = _quarter(root, pq, names)
        failures += [f"previous:{x}" for x in pf]
    if failures:
        return _hold(package, failures)

    values: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    detected = str(cur.get("generated_at") or "")[:10] or None

    def src(data: dict, qq: str) -> str:
        e = data["receipt"]
        key = "prest_" + qq
        if key not in sources:
            sources[key] = so.source_for(e, label=f"SIS · Prestaciones bonificadas {so.quarter_label(qq)} (datos abiertos)",
                                         role="ZIP trimestral; agregados de Alicanto por Isapre, prestador seudónimo, código y región",
                                         locator=f"{(e.get('parse') or {}).get('rows_ok')} filas; agregación en GitHub Actions",
                                         detected=str(data.get("generated_at") or "")[:10] or None)
        return key

    def put(vid: str, val: float, unit: str, qq: str, data: dict | None, locator: str | None = None) -> float:
        values[vid] = value(vid, val, unit=unit, period=so.period_of(qq), source=src(data, qq) if data else None,
                            locator=locator)
        return val

    def derived(vid: str, val: float, unit: str, formula: str, inputs: list[str], qq: str = q) -> float:
        values[vid] = value(vid, val, unit=unit, period=so.period_of(qq), source=None, formula=formula, inputs=inputs,
                            kind="derived")
        return val

    # 1. Coverage by Isapre (both quarters).
    isapres = sorted(cur["by_isapre"], key=lambda c: -cur["by_isapre"][c]["total"]["facturado"])
    for qq, data in ((q, cur), (pq, prev)):
        if not data:
            continue
        sums = {"facturado": 0, "bonificado": 0, "copago": 0, "frecuencia": 0}
        for code, kinds in data["by_isapre"].items():
            for kind, row in kinds.items():
                loc = f"prestaciones_{qq}_resumen.json · por_isapre_tipo_atencion · {code} · {kind}"
                put(f"isapre.{code}.{qq}.{kind}.pct_bonif", row["pct_bonificado"], "%", qq, data, loc)
                put(f"isapre.{code}.{qq}.{kind}.pct_copago", row["pct_copago"], "%", qq, data, loc)
                if kind == "total":
                    put(f"isapre.{code}.{qq}.total.facturado_mm", round(row["facturado"] / 1e6, 3), "MM$", qq, data, loc)
                    for k in sums:
                        sums[k] += row[k]
        for k in ("facturado", "bonificado", "copago"):
            put(f"sistema.{qq}.{k}_mm", round(sums[k] / 1e6, 3), "MM$", qq, data, "Σ Isapres, fila TOTAL")
        derived(f"sistema.{qq}.pct_bonif", sums["bonificado"] / sums["facturado"] * 100, "%",
                "Σ bonificado / Σ facturado × 100 (todas las Isapres, ambulatoria + hospitalaria)",
                [f"sistema.{qq}.bonificado_mm", f"sistema.{qq}.facturado_mm"], qq)
        derived(f"sistema.{qq}.pct_copago", sums["copago"] / sums["facturado"] * 100, "%",
                "Σ copago / Σ facturado × 100", [f"sistema.{qq}.copago_mm", f"sistema.{qq}.facturado_mm"], qq)
    hi_b = max(isapres, key=lambda c: values[f"isapre.{c}.{q}.total.pct_bonif"]["value"])
    lo_b = min(isapres, key=lambda c: values[f"isapre.{c}.{q}.total.pct_bonif"]["value"])

    # 2. Same provider, different Isapre.
    min_cells = int(cfg.get("cross_min_cells") or 1000)
    cons = cur.get("consistency") or {}
    cross_valid = (cons.get("veredicto") or {}).get("cross_isapre_valido") is True
    cross_rows = {str(r["isapre"]): r for r in cur["cross"].get("resumen_por_isapre") or []}
    qualified = []
    if cross_valid:
        loc = f"prestaciones_{q}_indice_isapre_mismo_prestador.json · resumen_por_isapre"
        for code, r in cross_rows.items():
            if r.get("indice_bonif_unit_mediana_pct") is None:
                continue
            for k, vid in (("indice_bonif_unit_mediana_pct", "mediana"), ("p25", "p25"), ("p75", "p75"),
                           ("indice_facturado_unit_mediana_pct", "fact_mediana"),
                           ("indice_bonif_unit_media_ponderada_frec_pct", "ponderada")):
                if r.get(k) is not None:
                    put(f"cruce.{code}.{vid}", r[k], "%", q, cur, loc)
            put(f"cruce.{code}.celdas", r["celdas_prestador_prestacion"], "celdas", q, cur, loc)
            if r["celdas_prestador_prestacion"] >= min_cells:
                qualified.append(code)
        put("cruce.celdas_multi", cur["cross"].get("celdas_con_2_o_mas_isapres"), "celdas", q, cur, loc)
        idsum = (cons.get("trimestre_actual") or {}).get("pct_facturado_de_codigos_en_2_o_mas_isapres")
        if idsum is not None:
            put("ids.pct_facturado_multi", idsum, "%", q, cur, f"prestaciones_{q}_consistencia_ids.json")
    gap = None
    if len(qualified) >= 2:
        hi_c = max(qualified, key=lambda c: values[f"cruce.{c}.mediana"]["value"])
        lo_c = min(qualified, key=lambda c: values[f"cruce.{c}.mediana"]["value"])
        gap = derived("cruce.brecha_pp", values[f"cruce.{hi_c}.mediana"]["value"] - values[f"cruce.{lo_c}.mediana"]["value"], "pp",
                      f"mediana más alta − más baja del índice de bonificado por unidad, Isapres con ≥ {min_cells} celdas",
                      [f"cruce.{hi_c}.mediana", f"cruce.{lo_c}.mediana"])
        fact_meds = [values[f"cruce.{c}.fact_mediana"]["value"] for c in qualified if f"cruce.{c}.fact_mediana" in values]
        derived("cruce.fact_mediana_max_abs", max(abs(x) for x in fact_meds), "%",
                "máximo |mediana del índice de facturado por unidad| entre las Isapres calificadas",
                [f"cruce.{c}.fact_mediana" for c in qualified])
    else:
        hi_c = lo_c = None

    # 3. Prices of the most frequent Fonasa codes.
    top = [c for c in cur["top"].get("codigos") or [] if isinstance(c, dict)]
    n_top = int(cfg.get("top_codes") or 15)
    top = sorted(top, key=lambda c: c.get("rank") or 99)[:n_top]
    if len(top) < 3:
        return _hold(package, ["top_codes_under_3"])
    arancel = cur.get("arancel")
    if arancel:
        sources["arancel_" + q[:4]] = so.source_for(arancel, label=f"SIS · Arancel Isapre {q[:4]} (datos abiertos)",
                                                    role="descripción literal de cada código", locator="campo 8 del archivo",
                                                    detected=detected)
    desc_numbers: list[float] = []
    codes = []
    ratios = []
    status_count: dict[str, int] = {}
    for c in top:
        code = str(c["codigo_prestacion"])
        d = (c.get("descripcion_arancel_isapre") or [{}])[0].get("descripcion") if arancel else None
        desc_numbers += [v for _, v, _ in numbers_in(d or "")]
        codes.append({"code": code, "desc": d, "rank": c["rank"]})
        put(f"top.{code}.frecuencia", c["frecuencia"], "atenciones", q, cur, f"prestaciones_{q}_top_codigos.json")
        if c.get("pct_bonificado") is not None:
            put(f"top.{code}.pct_bonif", c["pct_bonificado"], "%", q, cur, f"prestaciones_{q}_top_codigos.json")
        for (cc, reg), cell in cur["cells"].items():
            if cc != code:
                continue
            loc = f"prestaciones_{q}_precios_fonasa_region.json · {code} · {reg}"
            base = f"precio.{code}.{reg}"
            put(f"{base}.n", cell["n_prestadores"], "prestadores", q, cur, loc)
            put(f"{base}.frec", cell["frecuencia"], "atenciones", q, cur, loc)
            put(f"{base}.share_top", cell["share_prestador_mayor_pct"], "%", q, cur, loc)
            for k in ("precio_mediana", "precio_p25", "precio_p75"):
                if cell.get(k) is not None:
                    put(f"{base}.{k.split('_')[1]}", cell[k], "$", q, cur, loc)
            if reg != NATIONAL:
                status_count[cell["estado"]] = status_count.get(cell["estado"], 0) + 1
        nat = f"precio.{code}.{NATIONAL}"
        if f"{nat}.p25" in values and values[f"{nat}.p25"]["value"] > 0:
            ratios.append(derived(f"{nat}.ratio", values[f"{nat}.p75"]["value"] / values[f"{nat}.p25"]["value"], "veces",
                                  "p75 / p25 del precio por unidad entre prestadores, nacional", [f"{nat}.p75", f"{nat}.p25"]))
    if len(ratios) < 3:
        return _hold(package, ["dispersion_under_3_codes"])
    derived("dispersion.mediana", median(ratios), "veces", "mediana de p75/p25 entre los códigos más frecuentes con precio nacional",
            [f"precio.{c['code']}.{NATIONAL}.ratio" for c in codes if f"precio.{c['code']}.{NATIONAL}.ratio" in values])
    for est, n in status_count.items():
        derived(f"conteo.celdas.{est}", n, "count", f"celdas región × código (top) con estado {est}",
                [f"precio.{c['code']}" for c in codes])
    estados = {(e["estado"], e["nacional"]): e for e in cur["prices"].get("conteo_estados") or []}
    reg_freq = sum(e.get("frecuencia") or 0 for (est, nat), e in estados.items() if not nat)
    pub_freq = (estados.get(("publicable", False)) or {}).get("frecuencia") or 0
    one = estados.get(("concentracion_un_prestador", False)) or {}
    put("divulgacion.frec_regional", reg_freq, "atenciones", q, cur, f"prestaciones_{q}_precios_fonasa_region.json · conteo_estados")
    put("divulgacion.frec_publicable", pub_freq, "atenciones", q, cur, f"prestaciones_{q}_precios_fonasa_region.json · conteo_estados")
    put("divulgacion.celdas_un_prestador", one.get("celdas") or 0, "celdas", q, cur, "conteo_estados")
    if reg_freq <= 0:
        return _hold(package, ["regional_frecuencia_not_positive"])
    derived("divulgacion.pct_publicable", pub_freq / reg_freq * 100, "%",
            "frecuencia de celdas región × código con precio publicable / frecuencia de todas las celdas regionales × 100",
            ["divulgacion.frec_publicable", "divulgacion.frec_regional"])

    # 4. Concentration by region.
    conc = {str(r["region"]): r for r in (cur["resumen"].get("concentracion") or {}).get("regiones") or []}
    for reg, r in conc.items():
        loc = f"prestaciones_{q}_resumen.json · concentracion · {reg}"
        put(f"conc.{reg}.hhi", r["hhi"], "HHI", q, cur, loc)
        put(f"conc.{reg}.top1", r["share_top1_pct"], "%", q, cur, loc)
        put(f"conc.{reg}.top5", r["share_top5_pct"], "%", q, cur, loc)
        put(f"conc.{reg}.n", r["n_prestadores"], "prestadores", q, cur, loc)
    put("filas", cur["receipt"]["parse"]["rows_ok"], "filas", q, cur, "recibo del ZIP")

    ev = so.evidence_sha256(sources)
    cnt = {"isapres": len(isapres), "qualified": len(qualified)}
    for k, n in cnt.items():
        package["derived_ratios"].append({"id": f"conteo.{k}", "value": n, "unit": "count"})
    package.update(
        period=so.period_of(q), periods=[so.period_of(x) for x in (pq, q) if x == q or prev],
        published_at=detected, date_basis="first_detected", release_key=sf.release_key(so.period_of(q), ev),
        evidence_sha256=ev, primary_source={"url": cur["receipt"]["url"], "sha256": cur["receipt"]["sha256"]},
        sources=sources, values=values, findings=[],
        entities=[{"code": int(c), "name": names[c]} for c in isapres if c.isdigit()],
        entity_codes=[int(c) for c in isapres if c.isdigit()],
        revisions=sf.detect_revisions({"values": values}, (previous_live or {}).get("evidence")),
        constants=[0, 1, 2, 3, 4, 5, 30, 10, 100, 256, 10000, FACT_STABLE_MAX, n_top, min_cells, len(top), *[int(c["code"]) for c in codes if c["code"].isdigit()],
                   *desc_numbers],
        kpis={"q": q, "pq": pq if prev else None, "isapres": isapres, "hi_b": hi_b, "lo_b": lo_b, "cross_valid": cross_valid,
              "qualified": qualified, "hi_c": hi_c, "lo_c": lo_c, "gap": gap, "codes": codes, "status_count": status_count,
              "regions": sorted(conc, key=lambda r: (r == NATIONAL, -(conc[r]["hhi"] or 0)))},
    )
    package["reconciliation"].update(ok=True, failures=[])
    return package


def compose(package: dict, registry: dict | None = None, *, today: date, decision: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    tpl = cfg["templates"]
    v = package["values"]
    k = package["kpis"]
    q, pq = k["q"], k["pq"]
    V = lambda vid: v[vid]["value"]  # noqa: E731
    pc = lambda vid, d=1: fmt(V(vid), d) + "%"  # noqa: E731
    names = {e["code"]: e["name"] for e in package["entities"]}
    nm = lambda code: names[int(code)]  # noqa: E731
    ql = so.quarter_label(q)
    tabs, paragraphs, notes, kpis = [], [], [], []

    # KPI cards.
    lines = [f"del facturado, {ql}", f"copago: {pc(f'sistema.{q}.pct_copago')}"]
    refs = [f"sistema.{q}.pct_bonif", f"sistema.{q}.pct_copago"]
    if pq:
        lines.append(f"{so.quarter_tag(pq)}: {pc(f'sistema.{pq}.pct_bonif')}")
        refs.append(f"sistema.{pq}.pct_bonif")
    kpis.append({"id": "bonificado_sistema", "label": "Bonificado por las Isapres", "value": pc(f"sistema.{q}.pct_bonif"),
                 "prov": "C", "lines": lines, "refs": refs})
    if k["gap"] is not None:
        hi, lo = k["hi_c"], k["lo_c"]
        kpis.append({"id": "brecha_mismo_prestador", "label": "Brecha de cobertura, mismo prestador",
                     "value": f"{fmt(V('cruce.brecha_pp'), 1)} pp", "prov": "C",
                     "lines": [f"{nm(hi)} {fmt(V(f'cruce.{hi}.mediana'), 1, True)}% · {nm(lo)} {fmt(V(f'cruce.{lo}.mediana'), 1, True)}%",
                               "mediana del bonificado por unidad vs. promedio"],
                     "refs": ["cruce.brecha_pp", f"cruce.{hi}.mediana", f"cruce.{lo}.mediana"]})
    c1 = k["codes"][0]["code"]
    n1 = f"precio.{c1}.{NATIONAL}"
    kpis.append({"id": "dispersion_precios", "label": "Dispersión de precios (p75/p25)", "value": f"{fmt(V('dispersion.mediana'), 1)} veces",
                 "prov": "C", "lines": [f"mediana de los {len(k['codes'])} códigos Fonasa más frecuentes",
                                        f"código {c1}: {money(V(f'{n1}.p25'))} a {money(V(f'{n1}.p75'))}"],
                 "refs": ["dispersion.mediana", f"{n1}.p25", f"{n1}.p75"]})
    kpis.append({"id": "precio_publicable", "label": "Atenciones con precio publicable", "value": pc("divulgacion.pct_publicable"),
                 "prov": "C", "lines": ["celdas región × código Fonasa",
                                        f"{fmt(V('divulgacion.celdas_un_prestador'), 0)} celdas con 1 prestador: sin precio"],
                 "refs": ["divulgacion.pct_publicable", "divulgacion.celdas_un_prestador"]})

    # Topic 1: coverage by Isapre.
    iss = sorted(k["isapres"], key=lambda c: -V(f"isapre.{c}.{q}.total.pct_bonif"))
    head = ["Isapre", "Bonificado", "Copago", "Ambulatoria", "Hospitalaria", "Facturado (MM$)"] + ([so.quarter_tag(pq)] if pq else [])

    def row_cov(c: str) -> list[str]:
        out = [nm(c), pc(f"isapre.{c}.{q}.total.pct_bonif"), pc(f"isapre.{c}.{q}.total.pct_copago"),
               pc(f"isapre.{c}.{q}.amb.pct_bonif"), pc(f"isapre.{c}.{q}.hosp.pct_bonif"),
               fmt(V(f"isapre.{c}.{q}.total.facturado_mm"), 0)]
        if pq:
            out.append(pc(f"isapre.{c}.{pq}.total.pct_bonif") if f"isapre.{c}.{pq}.total.pct_bonif" in v else "sin dato")
        return out
    table = {"columns": head, "rows": [row_cov(c) for c in iss]
             + [["Sistema", pc(f"sistema.{q}.pct_bonif"), pc(f"sistema.{q}.pct_copago"), "", "", fmt(V(f"sistema.{q}.facturado_mm"), 0)]
                + ([pc(f"sistema.{pq}.pct_bonif")] if pq else [])]}
    charts = [{"id": "f12-bonif-isapre", "form": "bars", "unit": "%", "digits": 1,
               "headline": "Bonificado sobre lo facturado, por Isapre",
               "subtitle": f"% de lo facturado por los prestadores que pagó la Isapre, {ql}",
               "rows": [{"label": nm(c), "value": V(f"isapre.{c}.{q}.total.pct_bonif"), "ref": f"isapre.{c}.{q}.total.pct_bonif",
                         "emphasis": c in (k["hi_b"], k["lo_b"])} for c in iss[:12]],
               "table": table,
               "source": "SIS, datos abiertos de prestaciones bonificadas (ZIP trimestral); agregados por Isapre."},
              {"id": "f12-bonif-amb", "form": "bars", "unit": "%", "digits": 1,
               "headline": "Bonificado en atención ambulatoria",
               "subtitle": f"% de lo facturado en atención ambulatoria, {ql}",
               "rows": [{"label": nm(c), "value": V(f"isapre.{c}.{q}.amb.pct_bonif"), "ref": f"isapre.{c}.{q}.amb.pct_bonif"}
                        for c in sorted(iss, key=lambda c: -V(f"isapre.{c}.{q}.amb.pct_bonif"))[:12]],
               "table": {"columns": ["Isapre", "Ambulatoria", "Hospitalaria"],
                         "rows": [[nm(c), pc(f"isapre.{c}.{q}.amb.pct_bonif"), pc(f"isapre.{c}.{q}.hosp.pct_bonif")] for c in iss]},
               "source": "SIS, datos abiertos de prestaciones bonificadas; tipo de atención declarado en cada fila."}]
    tab = {"id": "cobertura", "label": "Cobertura por Isapre", "charts": charts, "text": [], "dek": None}
    hi_b, lo_b = k["hi_b"], k["lo_b"]
    sf.topic_fields(tab, f"De {pc(f'isapre.{lo_b}.{q}.total.pct_bonif')} ({nm(lo_b)}) a {pc(f'isapre.{hi_b}.{q}.total.pct_bonif')} ({nm(hi_b)})",
                    index_refs=[f"isapre.{lo_b}.{q}.total.pct_bonif", f"isapre.{hi_b}.{q}.total.pct_bonif"], kpis=[])
    tabs.append(tab)
    paragraphs.append(f"En {ql}, las Isapres bonificaron el {pc(f'sistema.{q}.pct_bonif')} de lo facturado por los prestadores.")

    # Topic 2: same provider, different Isapre.
    if k["gap"] is not None:
        qual = sorted(k["qualified"], key=lambda c: -V(f"cruce.{c}.mediana"))
        rows = [{"label": nm(c), "value": V(f"cruce.{c}.mediana"), "ref": f"cruce.{c}.mediana"} for c in qual[:12]]
        tbl = {"columns": ["Isapre", "Mediana", "p25", "p75", "Ponderada por frecuencia", "Celdas"],
               "rows": [[nm(c), fmt(V(f"cruce.{c}.mediana"), 1, True) + "%", fmt(V(f"cruce.{c}.p25"), 1, True) + "%",
                         fmt(V(f"cruce.{c}.p75"), 1, True) + "%", fmt(V(f"cruce.{c}.ponderada"), 1, True) + "%",
                         fmt(V(f"cruce.{c}.celdas"), 0)] for c in qual]}
        charts = [{"id": "f12-mismo-prestador", "form": "diverging", "unit": "%", "digits": 1,
                   "headline": "Mismo prestador y código, distinta Isapre",
                   "subtitle": "Bonificado por unidad vs. el promedio de las Isapres del mismo prestador y código; mediana, %",
                   "rows": rows, "table": tbl,
                   "source": f"SIS, datos abiertos; prestadores seudónimos con ≥ 2 Isapres en el mismo código Fonasa. Isapres con ≥ {fmt(cfg.get('cross_min_cells') or 1000, 0)} celdas."}]
        fq = [c for c in qual if f"cruce.{c}.fact_mediana" in v]
        charts.append({"id": "f12-mismo-prestador-fact", "form": "diverging", "unit": "%", "digits": 1,
                       "headline": ("Lo que cobra el prestador casi no cambia" if V("cruce.fact_mediana_max_abs") <= FACT_STABLE_MAX
                                    else "Facturado por unidad, mismo prestador y código"),
                       "subtitle": "Facturado por unidad vs. el promedio de las Isapres del mismo prestador y código; mediana, %",
                       "rows": [{"label": nm(c), "value": V(f"cruce.{c}.fact_mediana"), "ref": f"cruce.{c}.fact_mediana"} for c in fq[:12]],
                       "table": {"columns": ["Isapre", "Facturado por unidad (mediana)"],
                                 "rows": [[nm(c), fmt(V(f"cruce.{c}.fact_mediana"), 1, True) + "%"] for c in fq]},
                       "source": "SIS, datos abiertos; mismo cálculo con el facturado en vez del bonificado."})
        tab = {"id": "mismo-prestador", "label": "Mismo prestador", "charts": charts, "text": [], "dek": None}
        hi, lo = k["hi_c"], k["lo_c"]
        sf.topic_fields(tab, f"{nm(hi)} {fmt(V(f'cruce.{hi}.mediana'), 1, True)}% · {nm(lo)} {fmt(V(f'cruce.{lo}.mediana'), 1, True)}%",
                        index_refs=[f"cruce.{hi}.mediana", f"cruce.{lo}.mediana"], kpis=[])
        tabs.append(tab)
        paragraphs.append(f"En un mismo prestador y código, la mediana del bonificado por unidad de {nm(hi)} queda "
                          f"{fmt(V('cruce.brecha_pp'), 1)} puntos sobre la de {nm(lo)}.")

    # Topic 3: price dispersion (national) of the most frequent codes.
    codes = k["codes"]
    with_ratio = [c for c in codes if f"precio.{c['code']}.{NATIONAL}.ratio" in v]
    nat_rows = []
    for c in codes:
        b = f"precio.{c['code']}.{NATIONAL}"
        has = f"{b}.mediana" in v
        nat_rows.append([c["code"], (c["desc"] or "sin descripción en el arancel")[:60],
                         fmt(V(f"top.{c['code']}.frecuencia"), 0), fmt(V(f"{b}.n"), 0),
                         money(V(f"{b}.mediana")) if has else "sin precio",
                         f"{money(V(f'{b}.p25'))}–{money(V(f'{b}.p75'))}" if f"{b}.p25" in v else "",
                         fmt(V(f"{b}.ratio"), 1) if f"{b}.ratio" in v else "", pc(f"{b}.share_top")])
    charts = [{"id": "f12-dispersion", "form": "bars", "unit": "veces", "digits": 1,
               "headline": "Cuánto varía el precio entre prestadores",
               "subtitle": f"p75 / p25 del precio por unidad, nacional, {ql}",
               "rows": [{"label": c["code"], "value": V(f"precio.{c['code']}.{NATIONAL}.ratio"),
                         "ref": f"precio.{c['code']}.{NATIONAL}.ratio", "emphasis": c["code"] == codes[0]["code"]} for c in with_ratio[:12]],
               "table": {"columns": ["Código", "Descripción (Arancel Isapre)", "Atenciones", "Prestadores", "Mediana", "p25–p75",
                                     "p75/p25", "Mayor prestador (% atenciones)"], "rows": nat_rows},
               "source": "SIS, datos abiertos de prestaciones bonificadas (códigos del arancel Fonasa) y Arancel Isapre para la descripción."}]
    tab = {"id": "precios", "label": "Precios", "charts": charts, "text": [], "dek": None}
    sf.topic_fields(tab, f"p75/p25 mediano: {fmt(V('dispersion.mediana'), 1)} veces", index_refs=["dispersion.mediana"], kpis=[])
    tabs.append(tab)
    paragraphs.append(f"Entre prestadores, el precio por unidad de los códigos Fonasa más frecuentes varía {fmt(V('dispersion.mediana'), 1)} "
                      "veces entre el percentil 25 y el 75 (mediana de los códigos).")

    # Topic 4: prices by region (top codes), disclosure rule applied.
    reg_rows = []
    for c in codes:
        for reg in sorted(so.REGIONS, key=lambda r: (r == "0", int(r))):
            b = f"precio.{c['code']}.{reg}"
            if f"{b}.n" not in v:
                continue
            n = V(f"{b}.n")
            if f"{b}.mediana" in v:
                state = money(V(f"{b}.mediana")) + (f" ({money(V(f'{b}.p25'))}–{money(V(f'{b}.p75'))})" if f"{b}.p25" in v else "")
            elif n == 1:
                state = "1 prestador: sin precio"
            else:
                state = f"menos de {PRICE_MIN_FREQ} atenciones: sin precio"
            reg_rows.append([c["code"], so.REGIONS[reg], fmt(n, 0), fmt(V(f"{b}.frec"), 0), state, pc(f"{b}.share_top")])
    c1 = codes[0]["code"]
    pub = [r for r in so.REGIONS if f"precio.{c1}.{r}.mediana" in v and r != "0"]
    pub = sorted(pub, key=lambda r: -V(f"precio.{c1}.{r}.frec"))[:12]
    charts = [{"id": "f12-precio-region", "form": "bars", "unit": "$", "digits": 0,
               "headline": f"Precio mediano del código {c1} por región",
               "subtitle": f"$ por unidad, mediana entre prestadores, {ql}; regiones con precio publicable",
               "rows": [{"label": so.REGIONS[r], "value": V(f"precio.{c1}.{r}.mediana"), "ref": f"precio.{c1}.{r}.mediana"} for r in pub],
               "table": {"columns": ["Código", "Región", "Prestadores", "Atenciones", "Precio (p25–p75)", "Mayor prestador"],
                         "rows": reg_rows},
               "source": "SIS, datos abiertos. Regla: precio con ≥ 2 prestadores y ≥ 30 atenciones; p25–p75 con ≥ 3; con 1 prestador, sin precio."}]
    st = k["status_count"]
    lab = {"publicable": "Con precio", "concentracion_un_prestador": "1 prestador", "suprimido_frecuencia_menor_30": "Menos de 30"}
    st_rows = [(lab[e], f"conteo.celdas.{e}") for e in lab if e in st]
    if len(st_rows) >= 2:
        charts.append({"id": "f12-divulgacion", "form": "bars", "unit": "celdas",
                       "headline": "Celdas región × código, según la regla",
                       "subtitle": f"Los {len(codes)} códigos más frecuentes, {ql}",
                       "rows": [{"label": lb, "value": V(ref), "ref": ref} for lb, ref in st_rows],
                       "table": {"columns": ["Estado", "Celdas"], "rows": [[lb, fmt(V(ref), 0)] for lb, ref in st_rows]},
                       "source": "Regla de divulgación de Alicanto aplicada a los agregados SIS."})
    for e, n in st.items():
        package["derived_ratios"].append({"id": f"conteo.celdas.{e}", "value": n, "unit": "count"})
    tab = {"id": "regiones", "label": "Precios por región", "charts": charts, "text": [], "dek": None}
    rr = pub[0] if pub else None
    if rr:
        sf.topic_fields(tab, f"Código más frecuente en {so.REGIONS[rr]}: {money(V(f'precio.{c1}.{rr}.mediana'))}",
                        index_refs=[f"precio.{c1}.{rr}.mediana"], kpis=[])
    else:
        sf.topic_fields(tab, None, kpis=[])
    tabs.append(tab)

    # Topic 5: concentration by region.
    regs = [r for r in k["regions"] if r not in (NATIONAL, "0") and r in so.REGIONS][:12]
    charts = [{"id": "f12-concentracion", "form": "bars", "unit": "HHI", "digits": 0,
               "headline": "Concentración del facturado entre prestadores",
               "subtitle": f"Índice HHI (0 a 10.000) por región del prestador, {ql}",
               "rows": [{"label": so.REGIONS[r], "value": V(f"conc.{r}.hhi"), "ref": f"conc.{r}.hhi"} for r in regs],
               "table": {"columns": ["Región", "HHI", "Mayor prestador", "5 mayores", "Prestadores"],
                         "rows": [[so.REGIONS.get(r, "Nacional") if r != NATIONAL else "Nacional", fmt(V(f"conc.{r}.hhi"), 0),
                                   pc(f"conc.{r}.top1"), pc(f"conc.{r}.top5"), fmt(V(f"conc.{r}.n"), 0)]
                                  for r in k["regions"] if r in so.REGIONS or r == NATIONAL]},
               "source": "SIS, datos abiertos; prestadores seudónimos agrupados por región del prestador. HHI sobre el facturado."}]
    tab = {"id": "concentracion", "label": "Concentración", "charts": charts, "text": [], "dek": None}
    if regs:
        r0 = regs[0]
        sf.topic_fields(tab, f"{so.REGIONS[r0]}: HHI {fmt(V(f'conc.{r0}.hhi'), 0)}; nacional {fmt(V(f'conc.{NATIONAL}.hhi'), 0)}",
                        index_refs=[f"conc.{r0}.hhi", f"conc.{NATIONAL}.hhi"], kpis=[])
    tabs.append(tab)

    # Headline: the first candidate of the configured priority that the verified data supports.
    lead = None
    for cand in cfg.get("headline_priority") or []:
        if cand == "brecha_mismo_prestador" and k["gap"] is not None:
            hi, lo = k["hi_c"], k["lo_c"]
            a, b = V(f"cruce.{hi}.mediana"), V(f"cruce.{lo}.mediana")
            if a > 0 > b:
                lead = (f"En el mismo prestador y código, {nm(hi)} bonifica {fmt(a, 1)}% más que el promedio de las Isapres "
                        f"y {nm(lo)}, {fmt(abs(b), 1)}% menos")
            else:
                lead = f"En el mismo prestador y código, la cobertura por unidad separa {fmt(V('cruce.brecha_pp'), 1)} puntos a {nm(hi)} de {nm(lo)}"
        elif cand == "bonificado_por_isapre":
            lead = (f"{nm(hi_b)} bonifica el {pc(f'isapre.{hi_b}.{q}.total.pct_bonif')} de lo facturado y {nm(lo_b)} "
                    f"el {pc(f'isapre.{lo_b}.{q}.total.pct_bonif')} en {ql}")
        elif cand == "dispersion_precios":
            lead = (f"El precio de las prestaciones Fonasa más frecuentes varía {fmt(V('dispersion.mediana'), 1)} veces "
                    f"entre prestadores en {ql}")
        if lead and len(lead) <= 140:
            break
        lead = None
    headline = lead or f"Prestaciones bonificadas por las Isapres en {ql}"
    dek_parts = [f"Las Isapres bonificaron el {pc(f'sistema.{q}.pct_bonif')} de lo facturado; "
                 f"por Isapre, de {pc(f'isapre.{lo_b}.{q}.total.pct_bonif')} a {pc(f'isapre.{hi_b}.{q}.total.pct_bonif')}."]
    if k["gap"] is not None and V("cruce.fact_mediana_max_abs") <= FACT_STABLE_MAX:
        dek_parts.append(f"Lo que cobra el prestador por unidad casi no cambia entre Isapres (mediana dentro de ±{fmt(V('cruce.fact_mediana_max_abs'), 1)}%).")
    dek = " ".join(dek_parts)

    notes += [
        {"id": "n1", "text": f"Base trimestral: cada cifra es un flujo de {ql}, no un stock; los trimestres no se suman. "
                             + (f"La comparación con el {so.quarter_tag(pq)} no está ajustada por estacionalidad." if pq else "")},
        {"id": "n2", "text": "Denominador: el % bonificado y el % de copago dividen por lo facturado por el prestador a la Isapre. "
                             "Facturado no es gasto de bolsillo: el copago puede reducirse después con seguros complementarios "
                             "u otros reembolsos que estos datos no registran."},
        {"id": "n3", "text": f"Regla de divulgación (Dirección): el precio de una región y código del arancel Fonasa se muestra solo con "
                             f"≥ 2 prestadores distintos y ≥ 30 atenciones (mediana; p25–p75 solo con ≥ 3). Con 1 prestador no hay "
                             "precio, solo la marca de concentración. Todos los prestadores cuentan en el total nacional. Siempre se "
                             "informa el % de atenciones del mayor prestador."},
        {"id": "n4", "text": "Los prestadores llegan con su RUT cifrado por la SIS: aparecen solo como agregados seudónimos. "
                             "Alicanto nunca intenta revertir el cifrado y nunca muestra nombres de prestadores."},
        {"id": "n5", "text": "Precio por unidad = facturado / frecuencia de cada prestador en el código; la mediana y los percentiles "
                             "son entre prestadores, no ponderados por atenciones."},
        {"id": "n6", "text": f"Mismo prestador: para cada prestador seudónimo y código Fonasa con ≥ 2 Isapres, el bonificado por unidad "
                             "de cada Isapre se compara con el promedio simple de las Isapres de esa celda. No ajusta por plan ni por "
                             "bonificación restringida."},
        {"id": "n7", "text": f"Archivo: ZIP trimestral de datos abiertos de la SIS ({fmt(V('filas'), 0)} filas). Su huella SHA-256 está "
                             "en Fuentes; cada agregado nombra esa misma huella y, si no calza, la ficha queda retenida."},
    ]
    if not k["cross_valid"]:
        notes.append({"id": "n8", "text": "La comparación por mismo prestador queda fuera: la verificación de los RUT cifrados entre Isapres no se cumplió."})
    nq = so.next_quarter(q)
    watch = [{"headline": f"Datos de {so.quarter_label(nq)}.",
              "explanation": "La SIS publica un ZIP por trimestre; Alicanto lo agrega cuando aparece en datos abiertos."}]
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
        "date_basis": "first_detected", "headline": headline, "headline_type": "default", "dek": dek, "dek_emphasis": None,
        "kpis": kpis[:5], "tabs": tabs,
        "facts": {"heading": "Qué muestran los datos", "paragraphs": paragraphs, "rendered_in_tabs": True},
        "watch": watch[:2], "notes": notes, "sources": sources, "machine_note": machine,
        "featured": bool((decision or {}).get("featured")), "triggers": triggers, "late_release": late,
        "revisions": package.get("revisions") or [],
    }


def run(root: Path, *, today: date, registry: dict | None = None, llm: bool = True,
        model_call: Callable[..., Any] | None = None, budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    """The Lectura stays off for F12 (no paid call) until Dirección sets ``families.F12.lectura_enabled``."""
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    llm = llm and cfg.get("lectura_enabled") is True
    out = sf.run_family(FAMILY, builder_version=BUILDER_VERSION, build_package=build_package, compose=compose, root=Path(root),
                        today=today, registry=registry, llm=llm, model_call=model_call, budget=budget)
    return so.first_review_gate(out, cfg, Path(root), FAMILY, "f12_")
