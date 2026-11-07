"""F12 report sections (Dirección, 6-nov-2026 21:54): funnel, stratified basket and the systemic findings.

The F12 ficha is a report: its title names the report and each section's own title states its finding. This module
adds to the F12 evidence package, from the committed aggregates only:

- the coverage funnel against FONASA's official Arancel MLE 2026 code list (``data/reference/fonasa_mle_2026.json``);
- a stratified basket: each MLE code goes to the world (ambulatorio / hospitalario) where most of its facturado is;
  in each world codes are ranked by national facturado and must have a published median price in the Metropolitana
  and in at least ``min_other_regions`` other regions; the two worlds combine with their share of MLE-coded facturado;
- within-region dispersion (p75/p25), regional index vs the Metropolitana, public vs private, the same-provider price
  change between quarters (each per world), regional and national concentration of facturado, and the national
  "veces el arancel" level of the ambulatory basket (descriptive).

Every number is a package value; derived counts are values too, so titles cite them. Robustness (weighted vs
unweighted, previous quarter) is computed and stored; a title states a finding only when the check holds.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median
from typing import Callable

from . import sis_open_data as so

MLE_REF = Path("data/reference/fonasa_mle_2026.json")
WORLDS = ("amb", "hosp")
WORLD_LABEL = {"amb": "ambulatorio", "hosp": "hospitalario"}
OTHER = [r for r in so.REGIONS if r not in ("13", "0")]
ALL16 = [r for r in so.REGIONS if r != "0"]
PAR_BAND = 1.0  # a region within ±1% of the Metropolitana is "a la par"


def load_mle(root: Path) -> tuple[dict | None, list[str]]:
    d = so.load_json(Path(root) / MLE_REF)
    if not d or not isinstance(d.get("codigos"), dict):
        return None, ["mle_reference_missing"]
    r = d.get("receipt") or {}
    f = []
    if not so.sf.HEX64.fullmatch(str(r.get("sha256") or "")) or not str(r.get("url") or "").startswith("https://"):
        f.append("mle_reference_without_hash")
    if r.get("codes") != len(d["codigos"]):
        f.append("mle_reference_count_mismatch")
    return d, f


def _meta_failures(d: dict | None, name: str, q: str, entry: dict) -> list[str]:
    if d is None:
        return [f"aggregate_missing:{name}"]
    f = []
    if d.get("periodo") != q:
        f.append(f"aggregate_period_mismatch:{name}")
    if d.get("script_version") != so.SCRIPT_VERSION:
        f.append(f"aggregate_script_version:{name}")
    if d.get("sha256_archivo") != entry.get("sha256"):
        f.append(f"aggregate_hash_mismatch:{name}")
    if d.get("filas") != (entry.get("parse") or {}).get("rows_ok"):
        f.append(f"aggregate_rows_mismatch:{name}")
    return f


def wavg(pairs: list[tuple[float, float]]) -> float | None:
    s = sum(w for w, _ in pairs)
    return sum(w * x for w, x in pairs) / s if pairs and s > 0 else None


def analyze(root: Path, cfg: dict, q: str, pq: str | None, cur: dict, prev: dict | None,
            put: Callable, derived: Callable, values: dict, sources: dict) -> tuple[dict, list[str]]:
    """Adds the report values to the package. Returns (kpis for compose, reconciliation failures)."""
    ref, failures = load_mle(root, )
    if ref is None:
        return {}, failures
    mle = ref["codigos"]
    rec = ref["receipt"]
    sources["arancel_mle_2026"] = so.sf.source_ref(
        url=rec["url"], sha256=rec["sha256"], published_at=None, fetched_at=str(rec.get("built_at") or "")[:10] or None,
        label="FONASA · Arancel MLE 2026 (Libro Arancel, entregado por Dirección)",
        role="lista oficial de códigos y valor nivel 1", locator=f"{rec.get('pages')} páginas; {rec.get('codes')} códigos")
    data = {q: cur, **({pq: prev} if prev else {})}
    files: dict[str, dict] = {}
    for qq, dd in data.items():
        for n in ("embudo_arancel_mle", "atencion_codigo", "precios_tipo_prestador"):
            files[f"{qq}.{n}"] = dd["files"][f"prestaciones_{qq}_{n}.json"]
        if files[f"{qq}.embudo_arancel_mle"].get("codigos_mle") != len(mle):
            failures.append(f"funnel_mle_list_mismatch:{qq}")
    cambio = so.load_json(Path(root) / so.AGG_ROOT / q / f"prestaciones_{q}_cambio_mismo_prestador.json")
    if cambio is not None:
        failures += _meta_failures(cambio, f"prestaciones_{q}_cambio_mismo_prestador.json", q, cur["receipt"])
        if prev and cambio.get("periodo_anterior") != pq:
            failures.append("change_previous_quarter_mismatch")
    if failures:
        return {}, failures
    k: dict = {}

    # 1. Funnel (system totals; both quarters).
    for qq, dd in data.items():
        fu = files[f"{qq}.embudo_arancel_mle"]["celdas"]
        loc = f"prestaciones_{qq}_embudo_arancel_mle.json"
        amb = lambda x: "mbul" in str(x["tipo_atencion"])  # noqa: E731
        for key in ("facturado", "frecuencia"):
            tot = sum(x[key] for x in fu)
            m = [x for x in fu if x["en_arancel_mle"]]
            mt = sum(x[key] for x in m)
            ma = sum(x[key] for x in m if amb(x))
            fl = sum(x[key] for x in fu if str(x["pertenencia"]).upper() == "FONASA")
            pab = sum(x[key] for x in m if x.get("grupo_mle") == "pabellon")
            pabh = sum(x[key] for x in m if x.get("grupo_mle") == "pabellon" and not amb(x))
            if tot <= 0 or mt <= 0:
                return {}, [f"funnel_empty:{qq}"]
            u = "MM$" if key == "facturado" else "atenciones"
            put(f"embudo.{qq}.{key}.total", round(tot / 1e6, 3) if key == "facturado" else tot, u, qq, dd, loc)
            put(f"embudo.{qq}.{key}.mle", round(mt / 1e6, 3) if key == "facturado" else mt, u, qq, dd, loc)
            derived(f"embudo.{qq}.{key}.pct_mle", mt / tot * 100, "%", "códigos MLE / total × 100",
                    [f"embudo.{qq}.{key}.mle", f"embudo.{qq}.{key}.total"], qq)
            derived(f"embudo.{qq}.{key}.pct_amb", ma / mt * 100, "%", "ambulatorio / total MLE × 100", [f"embudo.{qq}.{key}.mle"], qq)
            derived(f"embudo.{qq}.{key}.pct_hosp", (mt - ma) / mt * 100, "%", "hospitalario / total MLE × 100", [f"embudo.{qq}.{key}.mle"], qq)
            derived(f"embudo.{qq}.{key}.pct_flag", fl / tot * 100, "%", "marca SIS FONASA / total × 100", [f"embudo.{qq}.{key}.total"], qq)
            if pab > 0:
                derived(f"embudo.{qq}.{key}.pct_pab", pab / mt * 100, "%", "derechos de pabellón / total MLE × 100", [f"embudo.{qq}.{key}.mle"], qq)
                derived(f"embudo.{qq}.{key}.pct_pab_hosp", pabh / pab * 100, "%", "pabellón en atención hospitalaria / pabellón × 100",
                        [f"embudo.{qq}.{key}.mle"], qq)

    # 2. Strata: world of each code, facturado weights, baskets.
    strata = cfg.get("strata") or {"amb": {"size": 100, "min_other_regions": 13}, "hosp": {"size": 100, "min_other_regions": 8}}
    at = files[f"{q}.atencion_codigo"]
    fa: dict[str, dict] = {}
    for r in at["rows"]:
        x = dict(zip(at["columns"], r))
        w = "hosp" if "ospital" in str(x["tipo_atencion"]) else "amb"
        d = fa.setdefault(x["codigo_prestacion"], {"amb": 0.0, "hosp": 0.0})
        d[w] += x["facturado"] or 0
    fact = {c: d["amb"] + d["hosp"] for c, d in fa.items() if c in mle}
    world = {c: ("hosp" if fa[c]["hosp"] > fa[c]["amb"] else "amb") for c in fact}
    cells = cur["cells"]
    pcells = prev["cells"] if prev else {}
    wtot = {w: sum(f for c, f in fact.items() if world[c] == w) for w in WORLDS}
    basket: dict[str, list[str]] = {}
    for w in WORLDS:
        rule = int(strata[w]["min_other_regions"])
        ranked = sorted((c for c in fact if world[c] == w), key=lambda c: (-fact[c], c))
        ok = [c for c in ranked if (cells.get((c, "13")) or {}).get("precio_mediana")
              and sum(1 for r in OTHER if (cells.get((c, r)) or {}).get("precio_mediana")) >= rule]
        basket[w] = ok[: int(strata[w]["size"])]
        if len(basket[w]) < 10 or wtot[w] <= 0:
            return {}, [f"stratum_too_small:{w}:{len(basket[w])}"]
        loc = f"prestaciones_{q}_atencion_codigo.json + precios_fonasa_region.json"
        put(f"canasta.{w}.n", len(basket[w]), "códigos", q, cur, loc)
        put(f"canasta.{w}.facturado_mm", round(sum(fact[c] for c in basket[w]) / 1e6, 3), "MM$", q, cur, loc)
        put(f"canasta.{w}.mundo_mm", round(wtot[w] / 1e6, 3), "MM$", q, cur, loc)
        derived(f"canasta.{w}.cobertura", sum(fact[c] for c in basket[w]) / wtot[w] * 100, "%",
                "facturado de la canasta / facturado MLE del mundo × 100", [f"canasta.{w}.facturado_mm", f"canasta.{w}.mundo_mm"])
    wshare = {"amb": values[f"embudo.{q}.facturado.pct_amb"]["value"] / 100,
              "hosp": values[f"embudo.{q}.facturado.pct_hosp"]["value"] / 100}

    # 3. Within-region dispersion (p75/p25, cells with p25/p75 published = >= 4 providers).
    for qq, cc in ((q, cells), *(((pq, pcells),) if prev else ())):
        for w in WORLDS:
            per = {}
            for r in ALL16:
                pairs = [(fact[c], cc[(c, r)]["precio_p75"] / cc[(c, r)]["precio_p25"]) for c in basket[w]
                         if (cc.get((c, r)) or {}).get("precio_p25")]
                if pairs:
                    per[r] = (wavg(pairs), median(x for _, x in pairs), len(pairs))
            if len(per) < 8:
                return {}, [f"dispersion_regions_under_8:{w}:{qq}"]
            for r, (pw, pu, n) in per.items():
                derived(f"disp.{qq}.{w}.{r}", pw, "veces", "p75/p25 por código, ponderado por facturado nacional del código",
                        [f"canasta.{w}.n"], qq)
                if qq == q:
                    derived(f"disp.{qq}.{w}.{r}.n", n, "códigos", "códigos con p25 y p75 publicados", [f"canasta.{w}.n"], qq)
            derived(f"disp.{qq}.{w}.mediana", median(v[0] for v in per.values()), "veces", "mediana entre regiones (ponderado)",
                    [f"disp.{qq}.{w}.{r}" for r in per], qq)
            derived(f"disp.{qq}.{w}.mediana_unw", median(v[1] for v in per.values()), "veces",
                    "mediana entre regiones de la mediana simple por código", [f"canasta.{w}.n"], qq)
    k["disp_regions"] = {w: [r for r in ALL16 if f"disp.{q}.{w}.{r}" in values] for w in WORLDS}

    # 4. Regional index vs the Metropolitana, per world (simple average across the 15 regions).
    for qq, cc in ((q, cells), *(((pq, pcells),) if prev else ())):
        for w in WORLDS:
            per = {}
            for r in OTHER:
                pairs = [(fact[c], cc[(c, r)]["precio_mediana"] / cc[(c, "13")]["precio_mediana"]) for c in basket[w]
                         if (cc.get((c, r)) or {}).get("precio_mediana") and (cc.get((c, "13")) or {}).get("precio_mediana")]
                if pairs:
                    per[r] = ((wavg(pairs) - 1) * 100, (mean(x for _, x in pairs) - 1) * 100, len(pairs))
            for r, (iw, iu, n) in per.items():
                derived(f"idx.{qq}.{w}.{r}", iw, "%", "mediana regional / mediana RM − 1, ponderado por facturado del código",
                        [f"canasta.{w}.n"], qq)
                derived(f"idx.{qq}.{w}.{r}.unw", iu, "%", "ídem, promedio simple de códigos", [f"canasta.{w}.n"], qq)
                derived(f"idx.{qq}.{w}.{r}.n", n, "códigos", "códigos con precio en la región y en RM", [f"canasta.{w}.n"], qq)
            derived(f"idx.{qq}.{w}.media", mean(v[0] for v in per.values()), "%", "promedio simple de las regiones",
                    [f"idx.{qq}.{w}.{r}" for r in per], qq)
            derived(f"idx.{qq}.{w}.media_unw", mean(v[1] for v in per.values()), "%", "promedio simple, sin ponderar códigos",
                    [f"idx.{qq}.{w}.{r}.unw" for r in per], qq)
    k["idx_regions"] = {w: [r for r in OTHER if f"idx.{q}.{w}.{r}" in values] for w in WORLDS}
    # Robust discount: weighted and unweighted means agree in sign, in both quarters.
    k["idx_robust"] = {w: all(values[f"idx.{qq}.{w}.media"]["value"] < 0 and values[f"idx.{qq}.{w}.media_unw"]["value"] < 0
                              for qq in data) for w in WORLDS}

    # 5. Public vs private (same code and region), per world.
    tp = files[f"{q}.precios_tipo_prestador"]
    tr = {(r[0], r[1], r[2]): dict(zip(tp["columns"], r)) for r in tp["rows"]}
    for w in WORLDS:
        ok = lambda c, r, t: bool((tr.get((c, r, t)) or {}).get("precio_mediana")) and tr[(c, r, t)]["n_prestadores"] >= 3  # noqa: E731
        pairs = [(fact[c], tr[(c, r, "Público")]["precio_mediana"] / tr[(c, r, "Privado")]["precio_mediana"], r)
                 for c in basket[w] for r in ALL16 if ok(c, r, "Público") and ok(c, r, "Privado")]
        for r in ALL16:
            nr = sum(1 for p in pairs if p[2] == r)
            if nr:
                derived(f"pubpriv.{w}.{r}.celdas", nr, "celdas", "celdas con ≥ 3 prestadores públicos y ≥ 3 privados", [f"canasta.{w}.n"])
        pairs = [(a, b) for a, b, _ in pairs]
        if len(pairs) >= 10:
            derived(f"pubpriv.{w}.ponderado", (wavg(pairs) - 1) * 100, "%", "mediana pública / mediana privada − 1, ponderado",
                    [f"canasta.{w}.n"])
            derived(f"pubpriv.{w}.mediana", (median(x for _, x in pairs) - 1) * 100, "%", "mediana de las celdas", [f"canasta.{w}.n"])
            derived(f"pubpriv.{w}.celdas", len(pairs), "celdas", "celdas código × región con ambos precios", [f"canasta.{w}.n"])
    for x in tp.get("prestadores_por_region") or []:
        if x["region"] in ALL16:
            put(f"pubpriv.prest.{x['region']}.{x['tipo_prestador']}", x["prestadores"], "prestadores", q, cur,
                f"prestaciones_{q}_precios_tipo_prestador.json · prestadores_por_region")
    tot_tipo = {}
    for x in at.get("totales") or []:
        tot_tipo.setdefault(x["tipo_prestador"], 0)
        tot_tipo[x["tipo_prestador"]] += x["frecuencia"]
    if tot_tipo.get("Público"):
        derived("pubpriv.publico.pct_atenciones", tot_tipo["Público"] / sum(tot_tipo.values()) * 100, "%",
                "atenciones de prestadores públicos / atenciones con código Fonasa × 100 (totales del sistema)", [])

    # 6. Same-provider change (cambio file: providers present in both quarters).
    if cambio is not None:
        cr = {(r[0], r[1]): dict(zip(cambio["columns"], r)) for r in cambio["rows"]}
        for w in WORLDS:
            nat = [(fact[c], cr[(c, "NACIONAL")]) for c in basket[w] if (c, "NACIONAL") in cr]
            if len(nat) >= 10:
                derived(f"cambio.{w}.ponderado", wavg([(f, x["indice_laspeyres_pct"]) for f, x in nat]), "%",
                        "índice de cantidades fijas por código, ponderado por facturado", [f"canasta.{w}.n"])
                derived(f"cambio.{w}.mediana_prestador", median(x["mediana_relativos_pct"] for _, x in nat), "%",
                        "mediana entre códigos del cambio del prestador mediano", [f"canasta.{w}.n"])
                derived(f"cambio.{w}.codigos", len(nat), "códigos", "códigos con ≥ 4 prestadores en ambos trimestres", [f"canasta.{w}.n"])

    # 7. Concentration: top-3 per region (16 regions) and national top-10/top-50, both quarters.
    for qq, dd in data.items():
        conc = {str(r["region"]): r for r in (dd["resumen"].get("concentracion") or {}).get("regiones") or []}
        loc = f"prestaciones_{qq}_resumen.json · concentracion"
        for r in ALL16 + ["NACIONAL"]:
            if r in conc:
                for key in ("share_top1_pct", "share_top3_pct", "share_top10_pct", "share_top50_pct"):
                    if conc[r].get(key) is not None:
                        put(f"conc3.{qq}.{r}.{key.split('_')[1]}", conc[r][key], "%", qq, dd, loc)
                put(f"conc3.{qq}.{r}.facturado_mm", round(conc[r]["facturado"] / 1e6, 3), "MM$", qq, dd, loc)
        regs = [r for r in ALL16 if f"conc3.{qq}.{r}.top3" in values]
        over = [r for r in regs if values[f"conc3.{qq}.{r}.top3"]["value"] > 50]
        derived(f"conc3.{qq}.n_sobre_50", len(over), "regiones", "regiones donde los 3 mayores superan el 50%", [f"conc3.{qq}.{r}.top3" for r in regs], qq)
        derived(f"conc3.{qq}.n_regiones", len(regs), "regiones", "regiones con prestadores", [f"conc3.{qq}.{r}.top3" for r in regs], qq)
        derived(f"conc3.{qq}.media_top3", mean(values[f"conc3.{qq}.{r}.top3"]["value"] for r in regs), "%",
                "promedio simple entre regiones", [f"conc3.{qq}.{r}.top3" for r in regs], qq)
    if prev:
        derived("conc3.top10_cambio_pp", values[f"conc3.{q}.NACIONAL.top10"]["value"] - values[f"conc3.{pq}.NACIONAL.top10"]["value"],
                "pp", "top-10 nacional t − t−1", [f"conc3.{q}.NACIONAL.top10", f"conc3.{pq}.NACIONAL.top10"])

    # 8. "Veces el arancel" (descriptive, ambulatory only; hospital excluded by Dirección until explained).
    pairs = [(fact[c], cells[(c, "NACIONAL")]["precio_mediana"] / mle[c]["nivel1_total"]) for c in basket["amb"]
             if not c.startswith("00000") and (cells.get((c, "NACIONAL")) or {}).get("precio_mediana") and mle[c].get("nivel1_total")]
    if len(pairs) >= 10:
        derived("arancel.amb.veces", wavg(pairs), "veces", "mediana nacional del código / valor nivel 1 del Arancel MLE, ponderado",
                [f"canasta.amb.n"])
    # Thinnest hospital region (fewest codes with a price vs RM), for the note.
    hr = k["idx_regions"]["hosp"]
    k["hosp_thin"] = min(hr, key=lambda r: values[f"idx.{q}.hosp.{r}.n"]["value"]) if hr else None
    k.update(basket=basket, world_share=wshare, strata=strata)
    return k, []


# ---------------------------------------------------------------------------------------------------------------------
# Compose: report sections (order by strategic value; Dirección 6-nov-2026 21:54)


def _largest(values: dict, q: str, regs: list[str], n: int = 12) -> list[str]:
    """The n regions with most Isapre facturado (charts hold <= 12 rows; every region is in «Ver datos»)."""
    return sorted(regs, key=lambda r: -values.get(f"conc3.{q}.{r}.facturado_mm", {"value": 0})["value"])[:n]


def rm_phrase(world: str, wm: float, um: float, *, first: bool, fmt: Callable) -> tuple[str, bool]:
    """Title clause for one world vs. the Metropolitana. When the weighted and unweighted simple averages of the
    regions agree in sign it states the weighted figure ("en promedio" on the first clause); when they differ it says
    «mixto» and names both measures (review of PR #152). Returns (clause, measures agree)."""
    lab = world.capitalize() if first else world
    if (wm < 0) == (um < 0) and round(wm, 1) != 0:
        word = "más baratas" if wm < 0 else "más caras"
        return ((f"{lab}: regiones {fmt(abs(wm), 1)}% {word} que RM en promedio" if first
                 else f"{lab}, {fmt(abs(wm), 1)}% {word}"), True)
    return f"{lab}, mixto ({fmt(wm, 1, True)}% ponderado, {fmt(um, 1, True)}% sin ponderar)", False


def pubpriv_title(amb: float, hosp: float, fmt: Callable) -> str:
    """Section title (≤ 16 words, review of PR #152 round 3): the direction only when both worlds agree."""
    word = "más" if amb > 0 and hosp > 0 else "menos" if amb < 0 and hosp < 0 else "distinto"
    return (f"Mismo código y región: los públicos facturan {word} — ambulatorio {fmt(amb, 1, True)}%, "
            f"hospitalario {fmt(hosp, 1, True)}% (ponderado)")


def sections(package: dict, cfg: dict, fmt: Callable, topic_fields: Callable) -> dict:
    v = package["values"]
    k = package["kpis"]
    q, pq = k["q"], k["pq"]
    V = lambda vid: v[vid]["value"]  # noqa: E731
    pc = lambda vid: fmt(V(vid), 1) + "%"  # noqa: E731
    sg = lambda vid: fmt(V(vid), 1, True) + "%"  # noqa: E731
    R = so.REGIONS
    ql, qs = so.quarter_label(q), so.quarter_short(q)
    pqs = so.quarter_short(pq) if pq else None
    tabs, kpis, notes, paragraphs = [], [], [], []
    # "tres mayores" in a chart headline is the top-3 definition, a derived count like any other (lens check).
    package.setdefault("derived_ratios", []).append({"id": "conteo.top3", "value": 3, "unit": "count"})
    src = "SIS, datos abiertos de prestaciones bonificadas; canasta estratificada de códigos del Arancel MLE 2026 de FONASA."

    # 1. Within-region dispersion.
    charts = []
    for w in WORLDS:
        regs = k["disp_regions"][w]
        charts.append({"id": f"f12-disp-{w}", "form": "bars", "unit": "veces", "digits": 2,
                       "headline": f"Cuartil caro / cuartil barato, {WORLD_LABEL[w]}",
                       "subtitle": f"p75 / p25 del precio entre prestadores del mismo código, por región, {ql}; 12 regiones con más facturación",
                       "rows": [{"label": R[r], "value": V(f"disp.{q}.{w}.{r}"), "ref": f"disp.{q}.{w}.{r}"} for r in _largest(v, q, regs)],
                       "table": {"columns": ["Región", "p75 / p25", "Códigos"] + ([f"p75 / p25 {pqs}"] if pq else []),
                                 "rows": [[R[r], fmt(V(f"disp.{q}.{w}.{r}"), 2), fmt(V(f"disp.{q}.{w}.{r}.n"), 0)]
                                          + ([fmt(V(f"disp.{pq}.{w}.{r}"), 2) if f"disp.{pq}.{w}.{r}" in v else "sin dato"] if pq else [])
                                          for r in regs]},
                       "source": src + " Celdas con ≥ 4 prestadores."})
    tab = {"id": "dispersion", "label": "Dispersión en la región", "charts": charts, "text": [],
           "dek": (f"Mismo código, misma región: el cuartil caro factura {fmt(V(f'disp.{q}.amb.mediana'), 2)} veces el barato en "
                   f"ambulatorio y {fmt(V(f'disp.{q}.hosp.mediana'), 2)} en hospitalario"),
           "dek_refs": [f"disp.{q}.amb.mediana", f"disp.{q}.hosp.mediana"]}
    topic_fields(tab, f"p75/p25: {fmt(V(f'disp.{q}.amb.mediana'), 2)} ambulatorio · {fmt(V(f'disp.{q}.hosp.mediana'), 2)} hospitalario",
                 index_refs=[f"disp.{q}.amb.mediana", f"disp.{q}.hosp.mediana"], kpis=[])
    tabs.append(tab)

    # 2. Regional concentration.
    regs = [r for r in ALL16 if f"conc3.{q}.{r}.top3" in v]
    top = sorted(regs, key=lambda r: -V(f"conc3.{q}.{r}.top3"))
    charts = [{"id": "f12-conc-regional", "form": "bars", "unit": "%", "digits": 1,
               "headline": "Participación de los tres mayores prestadores",
               "subtitle": f"% de lo facturado a Isapres en la región del prestador, {ql}; 12 regiones más concentradas",
               "rows": [{"label": R[r], "value": V(f"conc3.{q}.{r}.top3"), "ref": f"conc3.{q}.{r}.top3"} for r in top[:12]],
               "table": {"columns": ["Región", "3 mayores", "Mayor"] + ([f"3 mayores {pqs}"] if pq else []),
                         "rows": [[R[r], pc(f"conc3.{q}.{r}.top3"), pc(f"conc3.{q}.{r}.top1")]
                                  + ([pc(f"conc3.{pq}.{r}.top3") if f"conc3.{pq}.{r}.top3" in v else "sin dato"] if pq else [])
                                  for r in top]},
               "source": "SIS, datos abiertos; prestadores seudónimos por región del prestador; todo lo facturado a Isapres."}]
    tab = {"id": "concentracion", "label": "Concentración regional", "charts": charts, "text": [],
           "dek": f"En {fmt(V(f'conc3.{q}.n_sobre_50'), 0)} de {fmt(V(f'conc3.{q}.n_regiones'), 0)} regiones, tres prestadores superan la mitad de lo facturado",
           "dek_refs": [f"conc3.{q}.n_sobre_50", f"conc3.{q}.n_regiones"]}
    topic_fields(tab, f"Tres mayores: {pc(f'conc3.{q}.media_top3')} de cada región, en promedio",
                 index_refs=[f"conc3.{q}.media_top3"], kpis=[])
    tabs.append(tab)

    # 3. National concentration.
    N = "NACIONAL"
    rows = []
    for size in ("top10", "top50"):
        for qq in ([pq] if pq else []) + [q]:
            if f"conc3.{qq}.{N}.{size}" in v:
                rows.append({"label": f"{size[3:]} mayores {so.quarter_short(qq)[:7]}", "value": V(f"conc3.{qq}.{N}.{size}"),
                             "ref": f"conc3.{qq}.{N}.{size}", "emphasis": qq == q})
    charts = [{"id": "f12-conc-nacional", "form": "bars", "unit": "%", "digits": 1,
               "headline": "Participación de los mayores prestadores, nacional",
               "subtitle": "% de todo lo facturado a Isapres en prestaciones, por trimestre",
               "rows": rows, "table": {"columns": ["Grupo", "% facturado"], "rows": [[r["label"], fmt(r["value"], 1) + "%"] for r in rows]},
               "source": "SIS, datos abiertos; cada prestador seudónimo sumado entre regiones."}]
    dek = f"Diez prestadores suman el {pc(f'conc3.{q}.{N}.top10')} de la facturación Isapre"
    refs = [f"conc3.{q}.{N}.top10"]
    if pq:
        d = V("conc3.top10_cambio_pp")
        if abs(d) < 0.05:
            dek += ", igual que el trimestre anterior"
        elif 0.5 <= abs(d) < 1.5:
            dek += f", un punto {'más' if d > 0 else 'menos'} que el trimestre anterior"
        else:
            dek += f", {fmt(abs(d), 1)} pp {'más' if d > 0 else 'menos'} que el trimestre anterior"
            refs.append("conc3.top10_cambio_pp")
    tab = {"id": "nacional", "label": "Concentración nacional", "charts": charts, "text": [], "dek": dek, "dek_refs": refs}
    topic_fields(tab, f"Diez mayores: {pc(f'conc3.{q}.{N}.top10')} · cincuenta: {pc(f'conc3.{q}.{N}.top50')}",
                 index_refs=[f"conc3.{q}.{N}.top10", f"conc3.{q}.{N}.top50"], kpis=[])
    tabs.append(tab)

    # 4. Regions vs the Metropolitana, by world (descriptive).
    charts, cards, phrase, drefs = [], [], [], []
    for w in WORLDS:
        regs = k["idx_regions"][w]
        charts.append({"id": f"f12-vs-rm-{w}", "form": "diverging", "unit": "%", "digits": 1,
                       "headline": f"Precio vs. Metropolitana, {WORLD_LABEL[w]}",
                       "subtitle": f"% sobre (+) o bajo (−) la mediana de la Metropolitana, canasta {WORLD_LABEL[w]}, {ql}; 12 regiones con más facturación",
                       "rows": [{"label": R[r], "value": V(f"idx.{q}.{w}.{r}"), "ref": f"idx.{q}.{w}.{r}"}
                                for r in sorted(_largest(v, q, regs), key=lambda r: V(f"idx.{q}.{w}.{r}"))],
                       "table": {"columns": ["Región", "Ponderado", "Sin ponderar", "Códigos"] + ([f"Ponderado {pqs}"] if pq else []),
                                 "rows": [[R[r], sg(f"idx.{q}.{w}.{r}"), sg(f"idx.{q}.{w}.{r}.unw"), fmt(V(f"idx.{q}.{w}.{r}.n"), 0)]
                                          + ([sg(f"idx.{pq}.{w}.{r}") if f"idx.{pq}.{w}.{r}" in v else "sin dato"] if pq else [])
                                          for r in sorted(regs, key=lambda r: V(f"idx.{q}.{w}.{r}"))]},
                       "source": src + " Mediana entre prestadores de cada código; promedio con el facturado nacional del código."})
        above = [r for r in regs if V(f"idx.{q}.{w}.{r}") >= PAR_BAND]
        par = [r for r in regs if abs(V(f"idx.{q}.{w}.{r}")) < PAR_BAND]
        cid = f"vs_rm_{w}_sobre"
        package["values"][cid] = {"id": cid, "value": len(above) + len(par), "unit": "regiones", "period": package["period"],
                                  "source": None, "locator": None, "formula": "regiones con índice ≥ −1%", "inputs": [],
                                  "kind": "derived", "revised": None}
        names_ = ", ".join(R[r] for r in above) or "ninguna"
        lines = [f"Sobre RM: {names_}"] + ([f"A la par: {', '.join(R[r] for r in par)}"] if par else [])
        cards.append({"id": f"tema-vs-rm-{w}", "label": f"{WORLD_LABEL[w].capitalize()}: a la par o sobre RM",
                      "value": f"{len(above) + len(par)} de {len(regs)} regiones", "lines": lines,
                      "refs": [cid, f"idx.{q}.{w}.media"] + [f"idx.{q}.{w}.{r}.n" for r in regs[:1]]})
        package["values"][f"vs_rm_{w}_n"] = {**package["values"][cid], "id": f"vs_rm_{w}_n", "value": len(regs)}
        cards[-1]["refs"].append(f"vs_rm_{w}_n")
        wm, um = V(f"idx.{q}.{w}.media"), V(f"idx.{q}.{w}.media_unw")
        text, agree = rm_phrase(WORLD_LABEL[w], wm, um, first=not phrase, fmt=fmt)
        phrase.append(text)
        drefs += [f"idx.{q}.{w}.media"] + ([] if agree else [f"idx.{q}.{w}.media_unw"])
    tab = {"id": "vs-rm", "label": "Regiones vs. RM", "charts": charts, "text": [],
           "dek": "; ".join(phrase), "dek_refs": drefs}
    topic_fields(tab, f"Ambulatorio {sg(f'idx.{q}.amb.media')} · hospitalario {sg(f'idx.{q}.hosp.media')} vs. RM, promedio",
                 index_refs=[f"idx.{q}.amb.media", f"idx.{q}.hosp.media"], kpis=cards)
    tabs.append(tab)

    # 5. Public vs private, by world (descriptive).
    if all(f"pubpriv.{w}.ponderado" in v for w in WORLDS):
        rows = [{"label": f"{'Amb.' if w == 'amb' else 'Hosp.'} {m}", "value": V(f"pubpriv.{w}.{key}"), "ref": f"pubpriv.{w}.{key}"}
                for w in WORLDS for m, key in (("ponderado", "ponderado"), ("mediana", "mediana"))]
        charts = [{"id": "f12-pub-priv", "form": "diverging", "unit": "%", "digits": 1,
                   "headline": "Mediana pública frente a la privada",
                   "subtitle": (f"% de diferencia en el mismo código y región, {ql}"
                                + (f"; los públicos tienen el {pc('pubpriv.publico.pct_atenciones')} de las atenciones Fonasa"
                                   if "pubpriv.publico.pct_atenciones" in v else "")),
                   "rows": rows,
                   "table": {"columns": ["Región", "Prestadores públicos", "Prestadores privados", "Celdas amb.", "Celdas hosp."],
                             "rows": [[R[r], fmt(V(f"pubpriv.prest.{r}.Público"), 0) if f"pubpriv.prest.{r}.Público" in v else "0",
                                       fmt(V(f"pubpriv.prest.{r}.Privado"), 0) if f"pubpriv.prest.{r}.Privado" in v else "0",
                                       fmt(V(f"pubpriv.amb.{r}.celdas"), 0) if f"pubpriv.amb.{r}.celdas" in v else "0",
                                       fmt(V(f"pubpriv.hosp.{r}.celdas"), 0) if f"pubpriv.hosp.{r}.celdas" in v else "0"]
                                      for r in ALL16 if f"pubpriv.prest.{r}.Público" in v]
                             + [[r["label"], fmt(r["value"], 1, True) + "%", "", "", ""] for r in rows]},
                   "source": src + " Tipo de prestador según la SIS; celdas con ≥ 3 prestadores públicos y ≥ 3 privados."}]
        tab = {"id": "publico-privado", "label": "Público y privado", "charts": charts, "text": [],
               "dek": pubpriv_title(V("pubpriv.amb.ponderado"), V("pubpriv.hosp.ponderado"), fmt),
               "dek_refs": ["pubpriv.amb.ponderado", "pubpriv.hosp.ponderado"]}
        # The medians go in the topic body (index line); the title carries the weighted figures (review round 3).
        topic_fields(tab, f"Medianas: ambulatorio {sg('pubpriv.amb.mediana')} · hospitalario {sg('pubpriv.hosp.mediana')}",
                     index_refs=["pubpriv.amb.mediana", "pubpriv.hosp.mediana"], kpis=[])
        tabs.append(tab)

    # 6. Same-provider change (descriptive).
    if all(f"cambio.{w}.ponderado" in v for w in WORLDS):
        rows = [{"label": f"{'Amb.' if w == 'amb' else 'Hosp.'} {m}", "value": V(f"cambio.{w}.{key}"), "ref": f"cambio.{w}.{key}"}
                for w in WORLDS for m, key in (("ponderado", "ponderado"), ("mediano", "mediana_prestador"))]
        charts = [{"id": "f12-cambio", "form": "diverging", "unit": "%", "digits": 1,
                   "headline": "Cambio de precio, mismos prestadores",
                   "subtitle": f"% entre {so.quarter_label(pq)} y {ql}; solo prestadores presentes en ambos trimestres",
                   "rows": rows, "table": {"columns": ["Mundo y medida", "Cambio"], "rows": [[r["label"], fmt(r["value"], 1, True) + "%"] for r in rows]},
                   "source": "SIS, datos abiertos; índice de cantidades fijas del trimestre anterior y mediana de los cambios por prestador."}]
        def med(w: str) -> str:
            m = V(f"cambio.{w}.mediana_prestador")
            return (f"no movió precios en {WORLD_LABEL[w]} ({fmt(m, 1)}%)" if round(m, 1) == 0
                    else f"{fmt(m, 1, True)}% en {WORLD_LABEL[w]}")
        first = f"El prestador mediano {med('amb')} y {med('hosp').replace('no movió precios en', 'sin cambio en')}"
        if round(V("cambio.amb.mediana_prestador"), 1) != 0:
            first = f"El prestador mediano cambió {med('amb')} y {med('hosp')}"
        dk = f"{first}; ponderado {sg('cambio.amb.ponderado')} y {sg('cambio.hosp.ponderado')}"
        still = False
        tab = {"id": "cambio", "label": "Cambio trimestral", "charts": charts, "text": [], "dek": dk,
               "dek_refs": ["cambio.amb.ponderado", "cambio.hosp.ponderado", "cambio.amb.mediana_prestador", "cambio.hosp.mediana_prestador"]}
        topic_fields(tab, f"Ponderado: {sg('cambio.amb.ponderado')} amb. · {sg('cambio.hosp.ponderado')} hosp.",
                     index_refs=["cambio.amb.ponderado", "cambio.hosp.ponderado"], kpis=[])
        tabs.append(tab)

    # KPI cards.
    kpis.append({"id": "dispersion_amb", "label": "Dispersión ambulatoria (p75/p25)", "value": f"{fmt(V(f'disp.{q}.amb.mediana'), 2)} veces",
                 "prov": "C", "lines": ["mediana entre regiones, mismo código"] + ([f"{pqs}: {fmt(V(f'disp.{pq}.amb.mediana'), 2)}"] if pq else []),
                 "refs": [f"disp.{q}.amb.mediana"] + ([f"disp.{pq}.amb.mediana"] if pq else [])})
    kpis.append({"id": "dispersion_hosp", "label": "Dispersión hospitalaria (p75/p25)", "value": f"{fmt(V(f'disp.{q}.hosp.mediana'), 2)} veces",
                 "prov": "C", "lines": ["mediana entre regiones, mismo código"] + ([f"{pqs}: {fmt(V(f'disp.{pq}.hosp.mediana'), 2)}"] if pq else []),
                 "refs": [f"disp.{q}.hosp.mediana"] + ([f"disp.{pq}.hosp.mediana"] if pq else [])})
    kpis.append({"id": "top10_nacional", "label": "Facturación de los 10 mayores", "value": pc(f"conc3.{q}.{N}.top10"),
                 "prov": "C", "lines": ["prestadores, nacional"] + ([f"{pqs}: {pc(f'conc3.{pq}.{N}.top10')}"] if pq else []),
                 "refs": [f"conc3.{q}.{N}.top10"] + ([f"conc3.{pq}.{N}.top10"] if pq else [])})
    kpis.append({"id": "facturado_mle", "label": "Facturado con código MLE", "value": pc(f"embudo.{q}.facturado.pct_mle"),
                 "prov": "C", "lines": [f"{pc(f'embudo.{q}.facturado.pct_amb')} ambulatorio · {pc(f'embudo.{q}.facturado.pct_hosp')} hospitalario"],
                 "refs": [f"embudo.{q}.facturado.pct_mle", f"embudo.{q}.facturado.pct_amb", f"embudo.{q}.facturado.pct_hosp"]})
    if "arancel.amb.veces" in v:
        kpis.append({"id": "arancel_amb", "label": "Ambulatorio: veces el arancel MLE", "value": f"{fmt(V('arancel.amb.veces'), 2)} veces",
                     "prov": "C", "lines": ["mediana nacional / valor nivel 1", "hospitalario: en revisión"], "refs": ["arancel.amb.veces"]})

    dek = (f"El {pc(f'embudo.{q}.facturado.pct_mle')} de lo facturado a las Isapres tiene código del arancel MLE de Fonasa "
           f"({pc(f'embudo.{q}.facturado.pct_amb')} ambulatorio, {pc(f'embudo.{q}.facturado.pct_hosp')} hospitalario). En un mismo "
           f"código y región, el cuartil caro factura {fmt(V(f'disp.{q}.amb.mediana'), 2)} veces el barato en ambulatorio "
           f"y {fmt(V(f'disp.{q}.hosp.mediana'), 2)} en hospitalario.")
    paragraphs.append(f"El {pc(f'embudo.{q}.facturado.pct_mle')} de lo facturado tiene código MLE; la canasta cubre "
                      f"{pc('canasta.amb.cobertura')} del mundo ambulatorio y {pc('canasta.hosp.cobertura')} del hospitalario.")
    st = k["strata"]
    thin = k.get("hosp_thin")
    notes += [
        {"id": "g1", "text": (f"Grupo de análisis: de lo facturado a las Isapres en prestaciones, el {pc(f'embudo.{q}.facturado.pct_mle')} "
                              "tiene un código de la lista oficial del Arancel MLE 2026 de FONASA (incluidos los derechos de pabellón); "
                              "el resto (códigos propios de las Isapres, de la Superintendencia o solo GES) queda fuera. Dentro de lo "
                              f"MLE, {pc(f'embudo.{q}.facturado.pct_amb')} es atención ambulatoria y {pc(f'embudo.{q}.facturado.pct_hosp')} "
                              "hospitalaria, según el campo «tipo de atención» del archivo SIS. La marca «FONASA» del archivo cubre el "
                              f"{pc(f'embudo.{q}.facturado.pct_flag')}.")},
        {"id": "g2", "text": (f"Canasta estratificada: cada código MLE va al mundo donde tiene más facturado. Ambulatorio: los "
                              f"{fmt(V('canasta.amb.n'), 0)} códigos con más facturado que tienen precio en la Metropolitana y en al menos "
                              f"{st['amb']['min_other_regions']} otras regiones ({pc('canasta.amb.cobertura')} del facturado del mundo). "
                              f"Hospitalario: {fmt(V('canasta.hosp.n'), 0)} códigos con precio en la Metropolitana y al menos "
                              f"{st['hosp']['min_other_regions']} otras regiones ({pc('canasta.hosp.cobertura')}). Dentro de cada mundo, cada "
                              "código pesa su facturado nacional; los totales combinan los mundos con su peso en lo facturado MLE. "
                              "Las regiones pesan igual en los promedios regionales; el promedio ponderado por región va en «Ver datos».")},
        {"id": "g3", "text": ("Dispersión: p75 / p25 del precio por unidad (facturado / frecuencia) entre prestadores de un mismo código y "
                              "región, solo con ≥ 4 prestadores; se informa la mediana entre regiones. Concentración: participación de "
                              "prestadores seudónimos en todo lo facturado a Isapres. Cambio trimestral: solo prestadores presentes en "
                              "ambos trimestres, con ≥ 4 por código.")},
        {"id": "g4", "text": ("El seudónimo de cada prestador es el que trae cada archivo trimestral; Alicanto verificó que se repite entre "
                              "trimestres, pero la SIS no lo garantiza. Si cambiara, la comparación entre trimestres se suspende.")},
        {"id": "g5", "text": ("Regiones con pocos códigos hospitalarios: " + (f"{R[thin]} tiene {fmt(V(f'idx.{q}.hosp.{thin}.n'), 0)} códigos con "
                              "precio frente a la Metropolitana; " if thin else "") + "en esas regiones el índice hospitalario se mueve con "
                              "pocos prestadores y se lee como descripción.")},
        {"id": "g6", "text": ("«Veces el arancel» divide el precio por el valor nivel 1 del Arancel MLE 2026 del mismo código y se muestra "
                              "solo para el mundo ambulatorio. En lo hospitalario, lo facturado por código probablemente incluye ítems "
                              "que el arancel no valoriza por separado (insumos, medicamentos, días cama asociados), por eso no se publica "
                              "hasta revisarlo.")},
    ]
    return {"tabs": tabs, "kpis": kpis, "dek": dek, "notes": notes, "paragraphs": paragraphs}
