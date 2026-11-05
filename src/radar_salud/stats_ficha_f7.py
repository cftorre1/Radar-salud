"""F7 · Financiamiento público: ejecución presupuestaria de Salud (DIPRES, Partida 16): package, ficha and checks.

Input: ``data/market/dipres_health_budget.json`` only, the DIPRES lane built by ``market_sources.collect_dipres``
(``dipres_sources.parse_execution`` / ``parse_comparative``). Nothing is downloaded here. Each record carries its PDF's
URL and SHA-256, its fiscal level (partida / subpartida / capítulo / programa), its state (``approved_initial``,
``modified`` = presupuesto vigente, ``executed`` = gasto devengado acumulado), its cut (``period_end``) and its unit
(miles de $ nominales). The lane declares ``coverage_complete: false`` and its rule "Do not sum nested fiscal levels or
transfer-financed programs. Execution is accumulated, not monthly flow."

What the ficha shows (incremento 3 of the data roadmap, PLAYBOOK §6):

- % de ejecución = gasto devengado acumulado / presupuesto vigente, both read from the **same document**, for the
  Partida 16 and for the Fonasa programme (capítulo 02, programa 01) at their latest cut; the capítulo 02 monthly
  series when the lane has it. Never against 100 % of the year, never against the initial law.
- Year on year only against the same month of the previous year, same entity and same kind of document (monthly
  execution report vs. comparative table); otherwise "sin comparación". Amounts are nominal (no UF series yet).

Reconciliation (any failure → HOLD; the ficha never publishes):

- ejecutado ≤ vigente, vigente > 0, units/basis verified (miles de $, nominal, price base = fiscal year);
- the accumulated executed amount never decreases between cuts of the same entity and fiscal year;
- the same entity and cut read from two documents agree;
- nested levels are never summed: every captured value equals exactly one lane record of its own entity, and a
  derived value only combines inputs of one entity (``trace_failures``); a level without its own record has no figure;
- every record is traced to a DIPRES https URL and a SHA-256 that the lane's document ledger confirms;
- cut ≠ publication: the cut is the last day of the month, the accumulation starts on 1 January; a publication date
  is shown only when the lane verified one (and it is after the cut). Otherwise the ficha is dated by Alicanto's
  capture of the document (``date_basis: first_detected``), never as a publication.

Freshness copy: the lane is refreshed by ``dipres_refresh`` in the daily statistics step. The ficha says "se revisa a
diario; DIPRES publica mensualmente" only while that check completed within ``REFRESH_MAX_AGE_DAYS``; if it stopped it
says so, and before it ever ran it keeps "captura manual". The cut stays in the kicker and the meta line.

First publication (Dirección's review, like F4): while ``families.F7.first_pass_requires_review`` is true and no F7
ficha is live, a PASS is written as HOLD ``awaiting_first_review`` with the full ficha in ``hold/``. It publishes only
when ``families.F7.first_review`` records ``reviewed_by`` and ``reviewed_sha256`` equal to the ficha's
``evidence_sha256`` (SHA-256 of the sorted URL+SHA-256 list of the documents it uses). The Lectura stays off
(``lectura_enabled: false``): no model call.
"""
from __future__ import annotations

import hashlib
import json
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from . import stats_fichas as sf
from .stats_fichas import fmt_dec, fmt_int, value

FAMILY = "F7"
BUILDER_VERSION = "f7_ejecucion_v2"  # v2 (5-nov-2026): latest report first in sources
LANE = Path("data/market/dipres_health_budget.json")
DIPRES_HOSTS = ("www.dipres.gob.cl", "dipres.gob.cl")
MM = "MM$"
# Entities shown, by their own fiscal key (partida, subpartida, capítulo, programa). A level is read only from records
# of exactly this key: the partida is never the sum of its capítulos, nor the capítulo of its programas.
ENTITIES = {
    "partida": ("16", None, None, None),
    "cap02": ("16", None, "02", None),
    "prog0201": ("16", None, "02", "01"),
}
LEVEL = {"partida": "partida", "cap02": "chapter", "prog0201": "program"}
FIRST_REVIEW_HOLD = "HOLD_FIRST_REVIEW:awaiting_first_review"
REFRESH_STATE = Path("data/market/dipres_refresh_state.json")  # written by dipres_refresh (daily statistics step)
REFRESH_MAX_AGE_DAYS = 3
# Names of other perimeters, as printed in the PDF (independent review of PR #139, 4-nov-2026: articles-431115 reads
# "SUBPARTIDA : 1603 SERVICIOS DE SALUD"). The lane stores only the code; a code without a name here is shown bare.
SUBPARTIDA_NAMES = {"1603": "Servicios de Salud"}
MONTH_WORDS = {1: "un mes", 2: "dos meses", 3: "tres meses", 4: "cuatro meses", 5: "cinco meses", 6: "seis meses"}


def _load(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _refresh_last_ok(root: Path) -> str | None:
    state = _load(Path(root) / REFRESH_STATE) or {}
    return str(state.get("last_ok_on") or "") or None  # the Chile day of the last OK check (last_ok_at is UTC)


def refresh_mode(package: dict, today: date) -> tuple[str, str | None]:
    """'daily' only when the automatic DIPRES check completed within REFRESH_MAX_AGE_DAYS of today; otherwise 'manual'
    (never ran) or 'stale' (it ran, but not recently). The copy never claims a refresh that did not happen."""
    last = (package.get("lane") or {}).get("refresh_last_ok_on")
    try:
        age = (today - date.fromisoformat(str(last))).days
    except ValueError:
        return "manual", None
    return ("daily" if 0 <= age <= REFRESH_MAX_AGE_DAYS else "stale"), last


def entity_key(r: dict) -> tuple:
    return (r.get("partida"), r.get("subpartida"), r.get("chapter"), r.get("program"))


def mm(thousands: int | float) -> float:
    """Miles de $ → millones de $ (the view rounds; the evidence keeps three decimals, i.e. the exact thousand)."""
    return round(thousands / 1000, 3)


def doc_kind(url: str, ledger: dict[str, dict], record: dict) -> str:
    kind = str((ledger.get(url) or {}).get("kind") or "")
    if "Informe Ejecuci" in kind:
        return "informe"
    if "Comparativo" in kind:
        return "comparativo"
    return "comparativo" if "source_column" in record else "informe"


def _last_day(period: str) -> str:
    y, m = sf.period_parts(period)
    return date(y, m, monthrange(y, m)[1]).isoformat()


def cuts(records: list[dict], ent: tuple, ledger: dict[str, dict]) -> tuple[list[dict], list[str]]:
    """Every (document, cut) of one entity: executed and vigente from the same document. Returns cuts and failures."""
    failures: list[str] = []
    out = []
    mine = [r for r in records if entity_key(r) == ent]
    for ex in (r for r in mine if r.get("budget_state") == "executed"):
        per = str(ex.get("period") or "")
        try:
            sf.period_parts(per)
        except ValueError:
            failures.append(f"cut_period_invalid:{ex.get('source_url')}:{per}")
            continue
        same_doc = [r for r in mine if r.get("source_sha256") == ex.get("source_sha256")
                    and r.get("fiscal_year") == ex.get("fiscal_year")]
        vig = [r for r in same_doc if r.get("budget_state") == "modified" and str(r.get("period")) in (per, per[:4])]
        ini = [r for r in same_doc if r.get("budget_state") == "approved_initial" and str(r.get("period")) in (per, per[:4])]
        if len(vig) != 1:
            failures.append(f"vigente_not_unique:{per}:{ex.get('source_url')}:{len(vig)}")
            continue
        out.append({"period": per, "year": int(ex.get("fiscal_year") or 0), "executed": ex, "vigente": vig[0],
                    "initial": ini[0] if len(ini) == 1 else None, "url": ex.get("source_url"),
                    "sha256": ex.get("source_sha256"), "kind": doc_kind(ex.get("source_url"), ledger, ex)})
    return out, failures


def cut_failures(name: str, cs: list[dict], ledger: dict[str, dict]) -> list[str]:
    """Reconciliation of one entity's cuts (HOLD on any failure)."""
    f: list[str] = []
    for c in cs:
        tag = f"{name}:{c['period']}"
        for r in (c["executed"], c["vigente"], *([c["initial"]] if c["initial"] else [])):
            if (r.get("unit") != "thousand_CLP" or r.get("currency") != "CLP" or r.get("measurement_basis") != "nominal"
                    or r.get("price_base_year") != r.get("fiscal_year")):
                f.append(f"unit_or_basis_unverified:{tag}:{r.get('budget_state')}")
            if not isinstance(r.get("value"), int) or isinstance(r.get("value"), bool):
                f.append(f"value_not_integer:{tag}:{r.get('budget_state')}")
        url, sha = str(c["url"] or ""), str(c["sha256"] or "")
        p = urlsplit(url)
        if p.scheme != "https" or p.hostname not in DIPRES_HOSTS:
            f.append(f"source_not_dipres_https:{tag}")
        if not sf.HEX64.fullmatch(sha):
            f.append(f"source_without_hash:{tag}")
        led = ledger.get(url)
        if not led:
            f.append(f"source_not_in_ledger:{tag}")
        elif led.get("source_sha256") != sha:
            f.append(f"source_hash_mismatch:{tag}")
        ex, vg = c["executed"].get("value"), c["vigente"].get("value")
        if isinstance(ex, int) and isinstance(vg, int):
            if vg <= 0:
                f.append(f"vigente_not_positive:{tag}")
            elif ex > vg:
                f.append(f"executed_over_vigente:{tag}")
            if ex < 0:
                f.append(f"executed_negative:{tag}")
        # Cut ≠ publication: an accumulated cut runs from 1 January to the last day of its month; a publication date,
        # when the lane verified one, is after the cut; the capture is after the cut.
        e = c["executed"]
        if e.get("period_start") != f"{c['year']}-01-01" or e.get("period_end") != _last_day(c["period"]):
            f.append(f"cut_not_accumulated_to_month_end:{tag}")
        pub = str(e.get("published_at") or "")[:10]
        if pub and pub <= str(e.get("period_end") or ""):
            f.append(f"publication_not_after_cut:{tag}")
        fetched = str((led or {}).get("fetched_at") or "")[:10]
        if fetched and fetched <= str(e.get("period_end") or ""):
            f.append(f"captured_before_cut:{tag}")
    # The same cut read from two documents agrees; accumulated execution never decreases within a fiscal year.
    by_period: dict[str, set] = {}
    for c in cs:  # executed and vigente: two documents for one cut must agree on both
        by_period.setdefault(c["period"], set()).add((c["executed"].get("value"), c["vigente"].get("value")))
    f += [f"same_cut_conflict:{name}:{p}" for p, vals in sorted(by_period.items()) if len(vals) > 1]
    for year in sorted({c["year"] for c in cs}):
        seq = sorted(((c["period"], c["executed"].get("value")) for c in cs if c["year"] == year))
        for (p0, v0), (p1, v1) in zip(seq, seq[1:]):
            if isinstance(v0, int) and isinstance(v1, int) and v1 < v0:
                f.append(f"executed_decreases:{name}:{p0}>{p1}")
    return f


def pick(cs: list[dict], period: str) -> dict | None:
    """One cut per period: the monthly execution report first, then the comparative table (values agree, checked)."""
    same = [c for c in cs if c["period"] == period]
    return sorted(same, key=lambda c: (c["kind"] != "informe", c["url"]))[0] if same else None


def trace_failures(values: dict, records: list[dict]) -> list[str]:
    """No nested sum, ever: a captured value equals exactly one lane record of its own entity (same document, cut and
    state), and a derived value only combines inputs of a single entity."""
    errors = []
    for vid, v in values.items():
        rec = v.get("record")
        if v.get("kind") == "captured":
            if not rec:
                errors.append(f"value_without_record:{vid}")
                continue
            ent = ENTITIES.get(v.get("entity"))
            hits = [r for r in records if r.get("source_sha256") == rec["sha256"] and r.get("source_url") == rec["url"]
                    and r.get("metric") == "gastos" and entity_key(r) == ent and r.get("budget_state") == rec["state"] and str(r.get("period")) == rec["period"]]
            if len(hits) != 1 or mm(hits[0]["value"]) != v["value"]:
                errors.append(f"value_not_single_record:{vid}")
        elif v.get("kind") == "derived":
            ents = {values[i].get("entity") for i in v.get("inputs") or [] if i in values}
            if len(ents) != 1 or ents != {v.get("entity")}:
                errors.append(f"nested_levels_mixed:{vid}")
    return errors


def evidence_sha256(sources: dict) -> str:
    lines = sorted(f"{s['url']} {s['sha256']}" for s in sources.values())
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _hold(package: dict, failures: list[str]) -> dict:
    package["reconciliation"].update(ok=False, failures=failures)
    package.update(findings=[], kpis={}, revisions=[], constants=[])
    return package


def build_package(root: Path, registry: dict | None = None, previous_live: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    root = Path(root)
    lane = _load(root / LANE)
    if not lane or not isinstance(lane.get("records"), list):
        raise ValueError("dipres_lane_missing")
    ledger = {d.get("source_url"): d for d in lane.get("document_ledger") or [] if d.get("source_url")}
    records = [r for r in lane["records"] if r.get("metric") == "gastos" and r.get("partida") == "16"
               and r.get("budget_state") in ("executed", "modified", "approved_initial")]
    failures: list[str] = []
    series: dict[str, list[dict]] = {}
    for name, ent in ENTITIES.items():
        cs, errs = cuts(records, ent, ledger)
        failures += errs + cut_failures(name, cs, ledger)
        series[name] = cs
    package: dict[str, Any] = {
        "family": FAMILY, "period": None, "periods": [], "published_at": None, "date_basis": "first_detected",
        "release_key": None, "primary_source": {}, "sources": {}, "values": {}, "entities": [], "entity_codes": [],
        "entity_keys": [], "causal_note": None, "provisional": False,
        "lane": {"coverage_complete": lane.get("coverage_complete"), "coverage_reason": lane.get("coverage_reason"),
                 "aggregation_rule": lane.get("aggregation_rule"),
                 # Operational state of the daily refresh (dipres_refresh, 4-nov-2026), for the freshness copy only: it
                 # is not evidence and never enters evidence_sha256.
                 "refresh_last_ok_on": _refresh_last_ok(root)},
        "reconciliation": {"ok": False, "failures": failures, "checks": [
            "ejecutado ≤ presupuesto vigente, ambos del mismo documento; vigente > 0",
            "unidad miles de $ nominales y base de precios = año fiscal",
            "el devengado acumulado no baja entre cortes de una misma entidad y año",
            "un mismo corte leído de dos documentos coincide",
            "niveles anidados nunca se suman: cada cifra es un registro de su propia entidad (partida, capítulo o programa)",
            "cada registro con URL https de DIPRES y SHA-256 confirmado por el ledger de documentos",
            "corte = último día del mes, acumulado desde el 1 de enero; fecha de publicación solo si está verificada y "
            "es posterior al corte; si no, fecha de captura rotulada como detección"]},
        "lectura_pool": [], "derived_ratios": [], "ranks": [],
    }
    part = sorted({c["period"] for c in series["partida"]}, key=sf.period_parts)
    if not part:
        failures.append("no_partida_cut")
    else:
        package["period"] = part[-1]  # a HOLD is filed under the cut it would have shown (hold/<slug>-<period>.json)
    if failures:
        return _hold(package, failures)
    t = part[-1]
    year = sf.period_parts(t)[0]
    prog = sorted({c["period"] for c in series["prog0201"]}, key=sf.period_parts)
    tp = prog[-1] if prog else None
    cap = sorted({c["period"] for c in series["cap02"] if c["year"] == year}, key=sf.period_parts)
    if not prog and len(cap) < 2:
        return _hold(package, ["fonasa_without_cut"])

    values: dict[str, dict] = {}
    sources: dict[str, dict] = {}

    def src(c: dict) -> str:
        key = "doc_" + c["sha256"][:12]
        if key not in sources:
            led = ledger[c["url"]]
            sources[key] = sf.source_ref(url=c["url"], sha256=c["sha256"], published_at=c["executed"].get("published_at"),
                                         fetched_at=led.get("fetched_at"),
                                         label=f"DIPRES · {str(led.get('kind') or '').replace('Documento PDF : ', '')} "
                                               f"(corte {sf.month_label(c['period'])})",
                                         role=("gasto devengado acumulado y presupuesto vigente del mismo informe" if c["kind"] == "informe"
                                               else "columnas 'vigente' y 'ejecución' del mismo cuadro comparativo"),
                                         locator=f"partida {c['executed'].get('partida')}"
                                                 + (f", capítulo {c['executed']['chapter']}" if c["executed"].get("chapter") else "")
                                                 + (f", programa {c['executed']['program']}" if c["executed"].get("program") else "")
                                                 + "; total GASTOS")
        return key

    def captured(vid: str, ent: str, c: dict, state: str) -> float:
        rec = c["executed"] if state == "executed" else c["vigente"] if state == "modified" else c["initial"]
        v = value(vid, mm(rec["value"]), unit=MM, period=c["period"], source=src(c),
                  locator=f"{rec.get('budget_state')} · miles de $ / 1.000")
        v.update(entity=ent, record={"url": c["url"], "sha256": c["sha256"], "state": rec["budget_state"],
                                     "period": str(rec.get("period"))})
        values[vid] = v
        return v["value"]

    def derived(vid: str, ent: str, val: float, formula: str, inputs: list[str], unit: str, period: str) -> float:
        values[vid] = {**value(vid, val, unit=unit, period=period, source=None, formula=formula, inputs=inputs,
                               kind="derived"), "entity": ent}
        return val

    def add_cut(ent: str, c: dict) -> None:
        p = c["period"]
        e = captured(f"{ent}.{p}.ejecutado", ent, c, "executed")
        vg = captured(f"{ent}.{p}.vigente", ent, c, "modified")
        formula = ("gasto devengado acumulado / presupuesto vigente × 100 (mismo informe de ejecución)" if c["kind"] == "informe" else
                   "ejecución acumulada (columna 'Ejecución', base contable no declarada) / presupuesto vigente × 100 (mismo cuadro)")
        derived(f"{ent}.{p}.pct", ent, e / vg * 100, formula,
                [f"{ent}.{p}.ejecutado", f"{ent}.{p}.vigente"], "%", p)

    def add_yoy(ent: str, c: dict) -> str | None:
        p1 = sf.shift_period(c["period"], -12)
        prev = [x for x in series[ent] if x["period"] == p1 and x["kind"] == c["kind"]]
        if not prev:
            return None
        add_cut(ent, prev[0])
        p = c["period"]
        derived(f"{ent}.yoy.pp", ent, round(values[f"{ent}.{p}.pct"]["value"], 1) - round(values[f"{ent}.{p1}.pct"]["value"], 1),
                "redondeo(% ejecución t, 1) − redondeo(% ejecución t−12, 1)", [f"{ent}.{p}.pct", f"{ent}.{p1}.pct"], "pp", p)
        e0 = values[f"{ent}.{p1}.ejecutado"]["value"]
        if e0 > 0:
            derived(f"{ent}.yoy.ejecutado_pct", ent, (values[f"{ent}.{p}.ejecutado"]["value"] - e0) / e0 * 100,
                    "(devengado t − devengado t−12) / devengado t−12 × 100, nominal",
                    [f"{ent}.{p}.ejecutado", f"{ent}.{p1}.ejecutado"], "%", p)
        return p1

    for p in part:
        if sf.period_parts(p)[0] == year:
            add_cut("partida", pick(series["partida"], p))
    latest = pick(series["partida"], t)
    yoy = {"partida": add_yoy("partida", latest)}
    if latest["initial"]:
        ini = captured(f"partida.{t}.ley_inicial", "partida", latest, "approved_initial")
        vg = values[f"partida.{t}.vigente"]["value"]
        derived(f"partida.{t}.modificaciones", "partida", vg - ini, "presupuesto vigente − ley inicial (mismo informe)",
                [f"partida.{t}.vigente", f"partida.{t}.ley_inicial"], MM, t)
        if ini > 0:
            derived(f"partida.{t}.modificaciones_pct", "partida", (vg - ini) / ini * 100, "(vigente − ley inicial) / ley inicial × 100",
                    [f"partida.{t}.modificaciones", f"partida.{t}.ley_inicial"], "%", t)
    for p in cap:
        add_cut("cap02", pick(series["cap02"], p))
    if tp:
        cp = pick(series["prog0201"], tp)
        add_cut("prog0201", cp)
        yoy["prog0201"] = add_yoy("prog0201", cp)
    errs = trace_failures(values, records)
    if errs:
        return _hold(package, errs)
    package["reconciliation"].update(ok=True, failures=[])

    # Other perimeters of the same partida (e.g. a subpartida in the 2027 project's comparative table) are never
    # read as the partida: listed for the notes, never shown as figures.
    excluded = sorted({(r.get("subpartida"), str(r.get("period"))) for r in records
                       if r.get("partida") == "16" and r.get("subpartida") and r.get("budget_state") == "executed"})
    pub = latest["executed"].get("published_at")
    detected = not pub
    ev_sha = evidence_sha256(sources)
    package.update(
        period=t, periods=[p for p in part if sf.period_parts(p)[0] == year],
        published_at=(str(pub)[:10] if pub else str(ledger[latest["url"]].get("fetched_at") or "")[:10] or None),
        date_basis="first_detected" if detected else "publication",
        release_key=sf.release_key(t, ev_sha), evidence_sha256=ev_sha,
        primary_source={"url": latest["url"], "sha256": latest["sha256"]}, sources=sources, values=values,
        findings=[], revisions=sf.detect_revisions({"values": values}, (previous_live or {}).get("evidence")),
        constants=[16, 2, 1, 100, 1000, *[int(s) for s, _ in excluded if str(s).isdigit()]],
        kpis={"t": t, "year": year, "tp": tp, "cap": cap, "yoy": yoy, "kinds": {"partida": latest["kind"],
              "prog0201": pick(series["prog0201"], tp)["kind"] if tp else None},
              "has_initial": bool(latest["initial"]), "excluded": [list(x) for x in excluded]},
    )
    return package


def compose(package: dict, registry: dict | None = None, *, today: date, decision: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    tpl = cfg["templates"]
    v = package["values"]
    k = package["kpis"]
    t, tp, year, cap, yoy = k["t"], k["tp"], k["year"], k["cap"], k["yoy"]
    V = lambda vid: v[vid]["value"]  # noqa: E731
    month, mlabel = sf.month_name(t), sf.month_label(t)
    pct = lambda vid: fmt_dec(V(vid), 1) + "%"  # noqa: E731
    span = f"enero–{month} {year}"
    cut_label = f"{sf.day_label(_last_day(t))} {year}"  # '31 jul 2026': the data cut, shown in the kicker and meta line
    kpis, tabs, paragraphs, notes = [], [], [], []

    def at(p: str) -> str:
        """Cut label of a figure. A cut other than the partida's always says how far it is (review of PR #139: two
        cuts are never side by side without a label)."""
        if p == t:
            return f"a {sf.month_label(p)}"
        n = abs((sf.period_parts(p)[0] - year) * 12 + sf.period_parts(p)[1] - sf.period_parts(t)[1])
        gap = MONTH_WORDS.get(n, f"{n} meses")
        return f"a {sf.month_label(p)}, {gap} {'después' if p > t else 'antes'} del corte de la partida"

    prog_kind = k["kinds"]["prog0201"]
    exec_word = lambda kind: "devengado" if kind == "informe" else "ejecutado"  # noqa: E731  (comparative: basis not declared)

    def yoy_line(ent: str) -> tuple[str, list[str]]:
        p1 = yoy.get(ent)
        if not p1:
            return "sin comparación a/a", []
        return (f"{sf.month_label(p1)}: {pct(f'{ent}.{p1}.pct')} ({fmt_dec(V(f'{ent}.yoy.pp'), 1, signed=True)} pp)",
                [f"{ent}.{p1}.pct", f"{ent}.yoy.pp"])

    # KPI cards (the Datos page copies the first two by id).
    yl, yr = yoy_line("partida")
    kpis.append({"id": "ejecucion_partida", "label": "Ejecución Salud (Partida 16)", "value": pct(f"partida.{t}.pct"), "prov": "C",
                 "lines": [at(t), f"devengado {fmt_int(V(f'partida.{t}.ejecutado'))} de {fmt_int(V(f'partida.{t}.vigente'))} {MM}", yl],
                 "refs": [f"partida.{t}.pct", f"partida.{t}.ejecutado", f"partida.{t}.vigente", *yr]})
    # Fonasa card: the programme only at the partida's cut; else capítulo 02 at that cut; else whichever exists, with
    # its own cut and its distance to the partida's written on the card.
    if tp == t or (tp and t not in cap):
        pl, pr = yoy_line("prog0201")
        kpis.append({"id": "ejecucion_fonasa", "label": "Ejecución programa Fonasa", "value": pct(f"prog0201.{tp}.pct"), "prov": "C",
                     "lines": [at(tp), f"{exec_word(prog_kind)} {fmt_int(V(f'prog0201.{tp}.ejecutado'))} de "
                               f"{fmt_int(V(f'prog0201.{tp}.vigente'))} {MM}", pl],
                     "refs": [f"prog0201.{tp}.pct", f"prog0201.{tp}.ejecutado", f"prog0201.{tp}.vigente", *pr]})
    else:
        c_t = t if t in cap else cap[-1]
        kpis.append({"id": "ejecucion_fonasa", "label": "Ejecución Fonasa (capítulo 02)", "value": pct(f"cap02.{c_t}.pct"), "prov": "C",
                     "lines": [at(c_t), f"devengado {fmt_int(V(f'cap02.{c_t}.ejecutado'))} de "
                               f"{fmt_int(V(f'cap02.{c_t}.vigente'))} {MM}"],
                     "refs": [f"cap02.{c_t}.pct", f"cap02.{c_t}.ejecutado", f"cap02.{c_t}.vigente"]})
    has_ini = k["has_initial"]
    kpis.append({"id": "vigente_partida", "label": "Presupuesto vigente Salud", "value": f"{fmt_int(V(f'partida.{t}.vigente'))} {MM}",
                 "prov": "C", "lines": [at(t)] + ([f"ley inicial: {fmt_int(V(f'partida.{t}.ley_inicial'))} {MM}"] if has_ini else ["nominal"]),
                 "refs": [f"partida.{t}.vigente", *([f"partida.{t}.ley_inicial"] if has_ini else [])]})
    kpis.append({"id": "devengado_partida", "label": "Gasto devengado Salud", "value": f"{fmt_int(V(f'partida.{t}.ejecutado'))} {MM}",
                 "prov": "C", "lines": [f"acumulado {span}, nominal"], "refs": [f"partida.{t}.ejecutado"]})

    # Topic 1: Salud (Partida 16).
    months = [p for p in package["periods"]]
    charts = []
    if len(months) >= 2:
        charts.append({"id": "f7-partida-ejecucion", "form": "line", "unit": "%", "digits": 1,
                       "headline": "Ejecución acumulada de la Partida 16",
                       "subtitle": f"% del presupuesto vigente de cada corte, {span}",
                       "rows": [{"label": sf.month_short(p), "value": V(f"partida.{p}.pct"), "ref": f"partida.{p}.pct",
                                 "emphasis": p == t} for p in months],
                       "table": {"columns": ["Corte", f"Devengado ({MM})", f"Vigente ({MM})", "Ejecución"],
                                 "rows": [[sf.month_label(p), fmt_int(V(f"partida.{p}.ejecutado")), fmt_int(V(f"partida.{p}.vigente")),
                                           pct(f"partida.{p}.pct")] for p in months]},
                       "source": "DIPRES, informes de ejecución de la Partida 16: gasto devengado acumulado y presupuesto vigente del mismo informe."})
    lvl = ([("Ley inicial", f"partida.{t}.ley_inicial")] if has_ini else []) + [("Vigente", f"partida.{t}.vigente"),
                                                                                ("Devengado", f"partida.{t}.ejecutado")]
    charts.append({"id": "f7-partida-niveles", "form": "bars", "unit": MM, "digits": 0,
                   "headline": "Ley inicial, vigente y devengado" if has_ini else "Vigente y devengado",
                   "subtitle": f"Millones de pesos nominales, Partida 16, a {mlabel}",
                   "rows": [{"label": lab, "value": V(ref), "ref": ref, "emphasis": lab == "Devengado"} for lab, ref in lvl],
                   "table": {"columns": ["Concepto", MM], "rows": [[lab, fmt_int(V(ref))] for lab, ref in lvl]
                             + ([["Vigente − ley inicial", sf.fmt_signed(V(f"partida.{t}.modificaciones"))]] if has_ini else [])},
                   "source": "DIPRES, informe de ejecución de la Partida 16. Los niveles no se suman entre sí."})
    tab = {"id": "salud", "label": "Salud (Partida 16)", "charts": charts, "text": [], "dek": None}
    line = f"{pct(f'partida.{t}.pct')} del vigente a {month}"
    refs = [f"partida.{t}.pct"]
    if yoy.get("partida"):
        line += f" · {fmt_dec(V('partida.yoy.pp'), 1, signed=True)} pp a/a"
        refs.append("partida.yoy.pp")
    sf.topic_fields(tab, line, index_refs=refs, kpis=[])
    tabs.append(tab)
    paragraphs.append(f"Entre enero y {month} de {year}, Salud devengó el {pct(f'partida.{t}.pct')} de su presupuesto vigente.")

    # Topic 2: Fonasa (capítulo 02 monthly series; programa 02.01 at its latest cut).
    charts = []
    if len(cap) >= 2:
        charts.append({"id": "f7-cap02-ejecucion", "form": "line", "unit": "%", "digits": 1,
                       "headline": "Ejecución acumulada del capítulo 02 (Fonasa)",
                       "subtitle": f"% del presupuesto vigente de cada corte, enero–{sf.month_name(cap[-1])} {year}",
                       "rows": [{"label": sf.month_short(p), "value": V(f"cap02.{p}.pct"), "ref": f"cap02.{p}.pct",
                                 "emphasis": p == cap[-1]} for p in cap],
                       "table": {"columns": ["Corte", f"Devengado ({MM})", f"Vigente ({MM})", "Ejecución"],
                                 "rows": [[sf.month_label(p), fmt_int(V(f"cap02.{p}.ejecutado")), fmt_int(V(f"cap02.{p}.vigente")),
                                           pct(f"cap02.{p}.pct")] for p in cap]},
                       "source": "DIPRES, informes de ejecución del capítulo 02. Capítulo y programa vienen de documentos distintos: no se comparan ni se suman."})
    if tp:
        ew = exec_word(prog_kind).capitalize()
        rows = [("Vigente", f"prog0201.{tp}.vigente"), (ew, f"prog0201.{tp}.ejecutado")]
        charts.append({"id": "f7-prog0201-niveles", "form": "bars", "unit": MM, "digits": 0,
                       "headline": f"Programa Fonasa a {sf.month_label(tp)}",
                       "subtitle": "Millones de pesos nominales, capítulo 02, programa 01"
                                   + ("" if tp == t else f"; {at(tp).split(', ', 1)[1]}"),
                       "rows": [{"label": lab, "value": V(ref), "ref": ref, "emphasis": lab == ew} for lab, ref in rows],
                       "table": {"columns": ["Concepto", MM], "rows": [[lab, fmt_int(V(ref))] for lab, ref in rows]
                                 + [["Ejecución", pct(f"prog0201.{tp}.pct")]]},
                       "source": ("DIPRES, cuadro comparativo del proyecto de presupuestos: columnas de presupuesto vigente y de ejecución "
                                  "de la misma tabla." if k["kinds"]["prog0201"] == "comparativo"
                                  else "DIPRES, informe de ejecución del programa.")})
    tab = {"id": "fonasa", "label": "Fonasa", "charts": charts, "text": [], "dek": None}
    if t in cap and tp != t:  # the index line stays on the partida's cut
        fl, fr = f"Capítulo Fonasa: {pct(f'cap02.{t}.pct')} del vigente a {month}", [f"cap02.{t}.pct"]
        paragraphs.append(f"El capítulo 02 (Fonasa) devengó el {pct(f'cap02.{t}.pct')} de su presupuesto vigente {at(t)}.")
    elif tp:
        fl, fr = f"Programa Fonasa: {pct(f'prog0201.{tp}.pct')} del vigente a {sf.month_name(tp)}", [f"prog0201.{tp}.pct"]
    else:
        fl, fr = f"Capítulo Fonasa: {pct(f'cap02.{cap[-1]}.pct')} del vigente a {sf.month_name(cap[-1])}", [f"cap02.{cap[-1]}.pct"]
    if tp:
        paragraphs.append(f"El programa Fonasa ejecutó el {pct(f'prog0201.{tp}.pct')} de su presupuesto vigente {at(tp)}.")
    sf.topic_fields(tab, fl, index_refs=fr, kpis=[])
    tabs.append(tab)

    # Headline and dek: the dek adds what the KPI cards do not (budget changes since the initial law, YoY status).
    # The headline speaks of the partida only, at its own cut (review of PR #139).
    lead = f"Salud ejecutó el {pct(f'partida.{t}.pct')} de su presupuesto vigente a {mlabel}"
    headline = tpl["headline"].format(lead=lead)
    dek_parts = []
    if has_ini:
        d = V(f"partida.{t}.modificaciones")
        word = "más" if d > 0 else "menos"
        if round(d) == 0:
            dek_parts.append("El presupuesto vigente de la Partida 16 es igual a la ley inicial.")
        else:
            dek_parts.append(f"El presupuesto vigente de la Partida 16 suma {fmt_int(abs(d))} {MM} {word} que la ley inicial"
                             + (f" ({fmt_dec(V(f'partida.{t}.modificaciones_pct'), 1, signed=True)}%)." if f"partida.{t}.modificaciones_pct" in v else "."))
    if yoy.get("partida"):
        dek_parts.append(f"Frente a {sf.month_label(yoy['partida'])}, la ejecución cambia {fmt_dec(V('partida.yoy.pp'), 1, signed=True)} pp.")
    else:
        dek_parts.append(f"Montos nominales; sin comparación con {year - 1} por falta del mismo corte.")
    dek = " ".join(dek_parts)

    # Notes (method, denominators, dates, coverage). Every figure in them traces to the package or its constants.
    notes.append({"id": "n1", "text": "Montos acumulados de enero al corte: un flujo acumulado, no un stock. No se suman entre meses ni entre "
                                      "niveles anidados (partida, capítulo y programa); cada nivel se lee de su propio registro."})
    notes.append({"id": "n2", "text": "Denominador: el % de ejecución divide el gasto devengado acumulado (en el cuadro comparativo, la columna "
                                      "«Ejecución», que no declara su base contable) por el presupuesto vigente que informa el mismo documento; "
                                      "nunca por la ley inicial ni por el año completo."})
    notes.append({"id": "n3", "text": "Montos nominales en millones de pesos: DIPRES publica miles de pesos y Alicanto divide por 1.000. "
                                      "El valor real (UF) queda pendiente."})
    notes.append({"id": "n4", "text": "Fechas: el corte es el último día del mes informado. Los PDF de DIPRES no traen fecha de publicación "
                                      "verificada; la ficha usa la fecha en que Alicanto capturó el documento y la rotula como detección."
                  if package.get("date_basis") == "first_detected" else
                  "Fechas: el corte es el último día del mes informado; la fecha de publicación es la que verificó la captura."})
    if tp and k["kinds"]["prog0201"] == "comparativo":
        notes.append({"id": "n5", "text": "El programa Fonasa sale del cuadro comparativo del proyecto de presupuestos (ejecución y vigente de la "
                                          "misma tabla)" + ("" if tp == t else f", con otro corte ({sf.month_label(tp)})")
                                          + "; la partida y el capítulo 02, de los informes de ejecución. No se comparan entre sí."})
    if not yoy.get("partida"):
        notes.append({"id": "n6", "text": f"Sin comparación con {year - 1}: no hay un corte del mismo mes de {year - 1} en el mismo tipo de "
                                          "documento. Cortes de otros meses no se comparan."})
    if k["excluded"]:
        subs = ", ".join(f"{s} ({SUBPARTIDA_NAMES[s]})" if s in SUBPARTIDA_NAMES else str(s)
                         for s in sorted({str(s) for s, _ in k["excluded"]}))
        notes.append({"id": "n7", "text": f"Los cortes de la subpartida {subs} no se usan como Partida 16: son otro perímetro, "
                                          "menor que la partida."})
    if package["lane"].get("coverage_complete") is False:
        notes.append({"id": "n8", "text": "La captura DIPRES de Alicanto declara cobertura incompleta: no todas las versiones del presupuesto "
                                          "ni las fechas de publicación están verificadas."})
    notes.append({"id": "n9", "text": "Ningún dato de esta ficha establece por qué cambia la ejecución del gasto."})

    nxt = sf.shift_period(t, 1)
    mode, checked = refresh_mode(package, today)
    late = (decision or {}).get("late_release")
    captured = sf.day_label(package["published_at"]) if detected_basis(package) else None
    if mode == "daily":
        pending = {"headline": f"Informe de ejecución de la Partida 16 a {sf.month_label(nxt)}: aún no publicado por DIPRES.",
                   "explanation": f"Alicanto revisa DIPRES a diario (última revisión: {sf.day_label(checked)}); "
                                  "la ficha cambia cuando aparece el informe del mes siguiente."}
    elif mode == "stale":
        pending = {"headline": f"Informe de ejecución de la Partida 16 a {sf.month_label(nxt)}: revisión automática detenida.",
                   "explanation": f"La revisión diaria de DIPRES no se completa desde el {sf.day_label(checked)}."}
    else:
        pending = {"headline": f"Informe de ejecución de la Partida 16 a {sf.month_label(nxt)}: captura pendiente.",
                   "explanation": "La captura DIPRES de Alicanto es manual" + (f" (última: {captured})" if captured else "")
                                  + "; ninguna corrida la actualiza sola."}
    watch = [({"headline": f"Informe de ejecución de la Partida 16 a {sf.month_label(nxt)}: sin captura nueva.",
               "explanation": f"Lleva {late['days_late']} días más allá del intervalo esperado desde la última captura."} if late else
              pending)]
    if not yoy.get("partida"):
        watch.append({"headline": f"Comparación con {year - 1}.",
                      "explanation": f"Se activa con el corte del mismo mes de {year - 1} en el mismo tipo de informe."})
    detected = package.get("date_basis") == "first_detected"
    triggers = (decision or {}).get("triggers") or []
    rule = "nuevo período" if "new_period" in triggers else ("revisión" if "revision" in triggers else "publicación vigente")
    machine = (f"Ficha generada por la regla \"{rule}\" (documento {'capturado por Alicanto el' if detected else 'publicado el'} "
               f"{sf.day_label(package['published_at'])}). Las cifras vienen del paquete de evidencia, sin descargas nuevas; "
               "la Lectura Alicanto está desactivada para esta familia.")
    # The latest report first: the card's "Fuente original" is the first source, and each DIPRES report is cumulative
    # to its cut (devengado acumulado and vigente at that date), so it alone backs the headline (Dirección 5-nov-2026).
    prim = (package.get("primary_source") or {}).get("url")
    sources = sorted(({**src, "key": key} for key, src in package["sources"].items()),
                     key=lambda x: (x.get("url") != prim,))
    return {
        "schema_version": sf.SCHEMA, "id": f"stats-ficha:{FAMILY}:{t}", "family": FAMILY, "family_label": cfg["label"],
        "slug": cfg["slug"], "period": t, "published_at": package["published_at"], "release_key": package["release_key"],
        "evidence_sha256": package["evidence_sha256"],
        "kicker": tpl["kicker"].format(label=cfg["label"], cut_label=cut_label),
        "kicker_meta": tpl["kicker_meta_detected" if detected else "kicker_meta"].format(
            period_label=mlabel, cut_label=cut_label, published_label=sf.day_label(package["published_at"]),
            cadence_phrase={"daily": cfg["cadence_phrase_auto"], "stale": cfg["cadence_phrase_stale"]}.get(mode, cfg["cadence_phrase"])),
        **({"date_basis": "first_detected"} if detected else {}),
        "headline": headline, "headline_type": "default", "dek": dek, "dek_emphasis": None,
        "kpis": kpis[:5], "tabs": tabs,
        "facts": {"heading": "Qué muestran los datos", "paragraphs": paragraphs, "rendered_in_tabs": True},
        "watch": watch[:2], "notes": notes, "sources": sources, "machine_note": machine,
        "featured": bool((decision or {}).get("featured")), "triggers": triggers, "late_release": late,
        "revisions": package.get("revisions") or [],
    }


def detected_basis(package: dict) -> bool:
    return package.get("date_basis") == "first_detected"


def _gate_open(cfg: dict, root: Path, sha: str | None) -> bool:
    if not cfg.get("first_pass_requires_review"):
        return True
    live = sf.load_live(Path(root), cfg["slug"]) or {}
    if str(live.get("builder_version") or "").startswith("f7_") and live.get("status") == "PASS":
        return True  # the first ficha was reviewed and published: later releases follow the policy
    review = cfg.get("first_review") or {}
    return bool(review.get("reviewed_by") and sha and review.get("reviewed_sha256") == sha)


def first_review_gate(result: dict, cfg: dict, root: Path) -> dict:
    """While ``first_pass_requires_review`` is true and no F7 ficha is live, a PASS is written as HOLD
    (``awaiting_first_review``) with the full rendered ficha; it publishes once ``first_review`` records who reviewed it
    and ``reviewed_sha256`` equal to the ficha's ``evidence_sha256``."""
    if result.get("status") != "pass":
        return result
    ficha = result["ficha"]
    sha = ficha.get("evidence_sha256")
    if _gate_open(cfg, root, sha):
        return result
    decision = {**(result.get("decision") or {}), "decision": "HOLD",
                "holds": [*((result.get("decision") or {}).get("holds") or []), FIRST_REVIEW_HOLD]}
    candidate = {**ficha, "status": "AWAITING_FIRST_REVIEW", "review_request": {
        "evidence_sha256": sha, "period": ficha.get("period"),
        "to_publish": "registro families.F7.first_review: reviewed_by, reviewed_at y reviewed_sha256 = evidence_sha256"}}
    return {**{k: v for k, v in result.items() if k != "ficha"}, "status": "hold", "decision": decision,
            "errors": [FIRST_REVIEW_HOLD], "candidate": candidate}


def run(root: Path, *, today: date, registry: dict | None = None, llm: bool = True,
        model_call: Callable[..., Any] | None = None, budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    """The Lectura stays off for F7 (no paid call) until Dirección sets ``families.F7.lectura_enabled``."""
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    llm = llm and cfg.get("lectura_enabled") is True
    out = sf.run_family(FAMILY, builder_version=BUILDER_VERSION, build_package=build_package, compose=compose, root=Path(root),
                        today=today, registry=registry, llm=llm, model_call=model_call, budget=budget)
    return first_review_gate(out, cfg, Path(root))
