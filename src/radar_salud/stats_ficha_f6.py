"""F6 · Prestadores (Boletín Estadístico Informativo IP): evidence package, KPIs and ficha (no model numbers).

The Boletín IP is four PDFs per release (acreditación, mediación, reclamos, RNPI). Inputs:
- ``data/stats_fichas/captures/boletin_ip.json`` (``stats_capture``): per document, URL, SHA-256 and whether each
  independently verified figure is present in the captured PDF text;
- ``config/statistical_analysis_verified_v1.json``: the independent reading of the PDFs (figures by document URL).

A figure is used only when it was verified by that reading AND found in the hashed document. Stocks (acreditados,
solicitudes en tramitación, mediadores, títulos) are cuts at the release date and are never summed across releases;
the claims figure is a monthly average of a flow. Quarter-on-quarter comparisons need two verified releases; until a
second release is verified they stay 'pendiente' (never estimated).
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import stats_capture as cap
from . import stats_fichas as sf
from .stats_fichas import fmt_dec, fmt_int, value

FAMILY = "F6"
BUILDER_VERSION = "f6_boletin_ip_v1"
CAPTURE = Path("data/stats_fichas/captures/boletin_ip.json")
MONTH_EN = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august", "september",
                                         "october", "november", "december"), 1)}
TOPIC_LABEL = {"acreditacion": "Acreditación", "mediacion": "Mediación", "reclamos": "Reclamos", "rnpi": "RNPI"}


def _metric_id(topic: str, key: str, period: str) -> tuple[str, dict] | None:
    """Verified metric key → (package id, meta). Keys carrying a year are mapped by pattern, never by position."""
    y = int(period[:4])
    fixed = {
        ("acreditacion", "accredited_providers"): ("acr.acreditados", "prestadores", "stock_at"),
        ("acreditacion", "with_observations"): ("acr.con_observaciones", "prestadores", "stock_at"),
        ("acreditacion", "pending_applications"): ("acr.tramite", "solicitudes", "stock_at"),
        ("acreditacion", "private_pending"): ("acr.tramite.privadas", "solicitudes", "stock_at"),
        ("acreditacion", "public_pending"): ("acr.tramite.publicas", "solicitudes", "stock_at"),
        ("mediacion", "registered_mediators"): ("med.mediadores", "mediadores", "stock_at"),
        ("reclamos", "reported_growth_percent_rounded"): ("rec.pct_informado", "%", "ytd"),
        ("rnpi", "registered_titles"): ("rnpi.titulos", "titulos", "stock_at"),
        ("rnpi", "records_without_birth_date"): ("rnpi.sin_fecha_nacimiento", "titulos", "stock_at"),
    }
    if (topic, key) in fixed:
        vid, unit, kind = fixed[(topic, key)]
        return vid, {"unit": unit, "kind": kind}
    m = re.fullmatch(r"monthly_average_(20\d{2})", key)
    if topic == "reclamos" and m:
        yy = int(m[1])
        if yy == y:
            return f"rec.promedio.{yy}", {"unit": "reclamos", "kind": "ytd", "periods": [f"{yy}-01", period]}
        if yy == y - 1:
            return f"rec.promedio.{yy}", {"unit": "reclamos", "kind": "interval", "periods": [f"{yy}-01", f"{yy}-12"]}
    m = re.fullmatch(r"cumulative_requests_(20\d{2})_to_([a-z]+)(20\d{2})", key)
    month = MONTH_EN.get(m[2]) if m else None  # the verified keys use English month names ('…_to_june2026')
    if topic == "mediacion" and month and f"{m[3]}-{month:02d}" == period:
        return "med.solicitudes_acumuladas", {"unit": "solicitudes", "kind": "interval", "periods": [f"{m[1]}-01", period],
                                              "since": int(m[1])}
    return None


def build_package(root: Path, registry: dict | None = None, previous_live: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    root = Path(root)
    store = cap._load(root / CAPTURE, None)
    if not store or not store.get("releases"):
        raise ValueError("boletin_capture_missing")
    verified = cap.verified_metrics(root)
    failures: list[str] = []

    def release_state(rel: dict) -> list[str]:
        why = []
        docs = {d.get("topic"): d for d in rel.get("documents") or []}
        if sorted(docs) != sorted(cap.TOPICS):
            why.append("documents_not_one_per_topic")
        for topic, d in sorted(docs.items()):
            if d.get("status") != "captured" or not sf.HEX64.fullmatch(str(d.get("sha256") or "")):
                why.append(f"not_captured:{topic}")
            elif d.get("format") != "pdf":
                why.append(f"format_{d.get('format')}:{topic}")
            elif d.get("url") not in verified:
                why.append(f"not_verified:{topic}")
            elif (d.get("parse") or {}).get("status") != "verified":
                missing = [k for k, ok in ((d.get("parse") or {}).get("verified_present") or {}).items() if not ok]
                why.append(f"verified_figure_not_in_document:{topic}:{','.join(missing) or (d.get('parse') or {}).get('status')}")
        return why

    states = {rel["period"]: release_state(rel) for rel in store["releases"]}
    usable = [rel for rel in store["releases"] if not states[rel["period"]]]
    latest = max(store["releases"], key=lambda r: r["period"])
    rel = max(usable, key=lambda r: r["period"]) if usable else latest
    if not usable:
        failures += [f"{rel['period']}:{w}" for w in states[rel["period"]]] or ["no_verified_release"]
    t = rel["period"]
    values: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    docs = {d["topic"]: d for d in rel.get("documents") or [] if d.get("topic")}
    primary = docs.get("acreditacion") or {}
    package: dict[str, Any] = {
        "family": FAMILY, "period": t, "periods": [t], "published_at": rel.get("published_at"),
        "release_key": sf.release_key(t, primary.get("sha256") or "0" * 16),
        "primary_source": {"url": primary.get("url"), "sha256": primary.get("sha256")}, "sources": sources,
        "values": values, "entities": [], "entity_codes": [], "entity_keys": [], "causal_note": None,
        "provisional": False, "number": rel.get("number"),
        "group_markers": [
            [r"(?:los |las |de los |de las |entre los |entre las )?(?:prestadores |solicitudes )?privad[oa]s", "private"],
            [r"(?:los |las |de los |de las |entre los |entre las )?(?:prestadores |solicitudes )?public[oa]s", "public"],
            [r"(?:el|al|del) sistema|(?:el|al|del) total|(?:el|del) pais", "system"]],
        "prompt_rules": ("No nombres aseguradoras. 'Privadas' y 'públicas' son solicitudes de acreditación en tramitación; un "
                         "porcentaje nombra su denominador ('de los acreditados', 'de las solicitudes'). Acreditados, "
                         "solicitudes, mediadores y títulos son stocks al cierre del mes (nómbralo: 'a junio'); los "
                         "títulos no son profesionales únicos. Los reclamos son un promedio mensual: 'entre enero y junio'."),
        "reconciliation": {"ok": False, "failures": failures,
                           "checks": ["un PDF por tema (acreditación, mediación, reclamos, RNPI) del mismo boletín y período",
                                      "cada documento capturado con SHA-256 y formato PDF",
                                      "cada cifra viene de la lectura independiente y aparece en el texto del PDF capturado",
                                      "privadas + públicas = solicitudes en tramitación",
                                      "con observaciones ≤ acreditados",
                                      "variación de reclamos calculada = variación informada (redondeada)",
                                      "los stocks no se suman entre boletines"]},
        "rejected_releases": store.get("rejected_releases") or [],
        "releases_state": {p: (w or ["ok"]) for p, w in states.items()},
    }
    if failures:
        package.update(findings=[], kpis={}, revisions=[], constants=[])
        return package

    meta: dict[str, dict] = {}
    for topic, d in sorted(docs.items()):
        info = verified[d["url"]]
        sources[topic] = sf.source_ref(url=d["url"], sha256=d["sha256"], published_at=rel.get("published_at"),
                                       fetched_at=d.get("fetched_at"),
                                       label=f"SIS · Boletín IP {rel.get('number')} · {TOPIC_LABEL[topic]} (PDF)",
                                       role=f"{TOPIC_LABEL[topic].lower()}: cifras verificadas en el PDF capturado",
                                       locator="págs. " + ", ".join(str(p) for p in info.get("pages_1based") or []))
        for key, val in info["metrics"].items():
            mapped = _metric_id(topic, key, t)
            if not mapped:
                failures.append(f"unmapped_metric:{topic}:{key}")
                continue
            vid, m = mapped
            values[vid] = value(vid, val, unit=m["unit"], period=t, source=topic,
                                locator=f"págs. {','.join(str(p) for p in info.get('pages_1based') or [])}")
            meta[vid] = m

    def derived(vid, val, formula, inputs, unit, period=t):
        values[vid] = value(vid, val, unit=unit, period=period, source=None, formula=formula, inputs=inputs, kind="derived")
        return val

    need = ["acr.acreditados", "acr.con_observaciones", "acr.tramite", "acr.tramite.privadas", "acr.tramite.publicas",
            "med.mediadores", "rnpi.titulos"]
    failures += [f"metric_missing:{x}" for x in need if x not in values]
    y = int(t[:4])
    if not failures:
        V = lambda vid: values[vid]["value"]  # noqa: E731
        if V("acr.tramite.privadas") + V("acr.tramite.publicas") != V("acr.tramite"):
            failures.append("privadas_mas_publicas_distinto_de_tramite")
        if V("acr.con_observaciones") > V("acr.acreditados"):
            failures.append("observaciones_sobre_acreditados")
        if f"rec.promedio.{y}" in values and f"rec.promedio.{y - 1}" in values:
            pct = (V(f"rec.promedio.{y}") - V(f"rec.promedio.{y - 1}")) / V(f"rec.promedio.{y - 1}") * 100
            if "rec.pct_informado" in values and round(pct) != V("rec.pct_informado"):
                failures.append("variacion_reclamos_no_calza_con_la_informada")
    package["reconciliation"].update(ok=not failures, failures=failures)
    if failures:
        package.update(findings=[], kpis={}, revisions=[], constants=[])
        return package

    V = lambda vid: values[vid]["value"]  # noqa: E731
    derived("acr.sin_observaciones", V("acr.acreditados") - V("acr.con_observaciones"), "acreditados − con observaciones",
            ["acr.acreditados", "acr.con_observaciones"], "prestadores")
    derived("acr.observaciones_pct", V("acr.con_observaciones") / V("acr.acreditados") * 100, "con observaciones / acreditados × 100",
            ["acr.con_observaciones", "acr.acreditados"], "%")
    derived("acr.privadas_pct", V("acr.tramite.privadas") / V("acr.tramite") * 100, "privadas / en tramitación × 100",
            ["acr.tramite.privadas", "acr.tramite"], "%")
    has_rec = f"rec.promedio.{y}" in values and f"rec.promedio.{y - 1}" in values
    if has_rec:
        derived("rec.delta", V(f"rec.promedio.{y}") - V(f"rec.promedio.{y - 1}"), "promedio(t) − promedio(año anterior)",
                [f"rec.promedio.{y}", f"rec.promedio.{y - 1}"], "reclamos", t)
        derived("rec.pct", V("rec.delta") / V(f"rec.promedio.{y - 1}") * 100, "Δ / promedio mensual del año anterior × 100",
                ["rec.delta", f"rec.promedio.{y - 1}"], "%", t)
    # Quarter on quarter: only between two releases whose figures were verified (stocks compared, never summed).
    older = sorted((r for r in usable if r["period"] < t), key=lambda r: r["period"])
    comparisons = {}
    if older:
        prev = older[-1]
        for topic, d in {x["topic"]: x for x in prev["documents"]}.items():
            for key, val in verified[d["url"]]["metrics"].items():
                mapped = _metric_id(topic, key, prev["period"])
                if mapped and mapped[1]["kind"] == "stock_at" and mapped[0] in values:
                    pid = f"{mapped[0]}.{prev['period']}"
                    values[pid] = value(pid, val, unit=mapped[1]["unit"], period=prev["period"], source=f"prev_{topic}")
                    comparisons[mapped[0]] = derived(f"{mapped[0]}.qoq", V(mapped[0]) - val, "stock(t) − stock(boletín anterior)",
                                                     [mapped[0], pid], mapped[1]["unit"])
                    sources.setdefault(f"prev_{topic}", sf.source_ref(
                        url=d["url"], sha256=d["sha256"], published_at=prev.get("published_at"), fetched_at=d.get("fetched_at"),
                        label=f"SIS · Boletín IP {prev.get('number')} · {TOPIC_LABEL[topic]} (PDF)", role="boletín anterior",
                        locator="págs. " + ", ".join(str(p) for p in verified[d["url"]].get("pages_1based") or [])))
    since = (meta.get("med.solicitudes_acumuladas") or {}).get("since")
    newer = sorted(p for p in states if p > t)
    package.update(findings=[], revisions=sf.detect_revisions({"values": values}, (previous_live or {}).get("evidence")),
                   constants=[30, 2, 100], periods=sorted({t, f"{y}-01", f"{y - 1}-01", f"{y - 1}-12"}),
                   kpis={"y": y, "has_rec": has_rec, "comparisons": comparisons,
                         "prev": older[-1]["period"] if older else None, "since": since, "newer": newer,
                         "unverified": sorted(p for p, w in states.items() if w and p != t), "meta": meta})
    _lectura_material(package, values)
    return package


def _lectura_material(package: dict, values: dict) -> None:
    t, y = package["period"], package["kpis"]["y"]
    S = {"periods": [t], "period_kind": "stock_at"}
    P = lambda vid, **kw: sf.pool_entry(values, vid, **kw) if vid in values else None  # noqa: E731
    pool = [P("acr.acreditados", metric="prestadores", signed=False, scope="system", **S),
            P("acr.con_observaciones", metric="prestadores", signed=False, scope="system", **S),
            P("acr.sin_observaciones", metric="prestadores", signed=False, scope="system", **S),
            P("acr.observaciones_pct", signed=False, scope="system", base="acreditados", **S),
            P("acr.tramite", metric="solicitudes", signed=False, scope="system", **S),
            P("acr.tramite.privadas", metric="solicitudes", signed=False, scope="private", **S),
            P("acr.tramite.publicas", metric="solicitudes", signed=False, scope="public", **S),
            P("acr.privadas_pct", signed=False, scope="private", base="solicitudes_en_tramite", **S),
            P("med.mediadores", metric="mediadores", signed=False, scope="system", **S),
            P("rnpi.titulos", metric="titulos", signed=False, scope="system", **S),
            P("rnpi.sin_fecha_nacimiento", metric="titulos", signed=False, scope="system", **S)]
    if "med.solicitudes_acumuladas" in values:
        pool.append(P("med.solicitudes_acumuladas", metric="solicitudes", signed=False, scope="system",
                      periods=[f"{package['kpis']['since']}-01", t], period_kind="interval"))
    if package["kpis"]["has_rec"]:
        Y = {"periods": [f"{y}-01", t], "period_kind": "ytd"}
        pool += [P(f"rec.promedio.{y}", metric="reclamos", signed=False, scope="system", **Y),
                 P("rec.delta", metric="reclamos", scope="system", **Y),
                 P("rec.pct", scope="system", base="promedio_mensual_anio_anterior", **Y),
                 P(f"rec.promedio.{y - 1}", metric="reclamos", signed=False, scope="system",
                   periods=[f"{y - 1}-01", f"{y - 1}-12"], period_kind="interval")]
    package["lectura_pool"] = [e for e in pool if e]
    v = lambda vid: values[vid]["value"]  # noqa: E731
    ratios = [{"id": "ratio.privadas_por_publica", "value": v("acr.tramite.privadas") / v("acr.tramite.publicas"), "unit": "x",
               "entity": None, "signed": False, "periods": [t], "requires_period": False, "formula": "privadas / públicas",
               "inputs": ["acr.tramite.privadas", "acr.tramite.publicas"], "scope": "private", "period_kind": "stock_at",
               "trivial": False, "base": None},
              {"id": "fraccion.observaciones", "value": v("acr.con_observaciones") / v("acr.acreditados"), "unit": "share",
               "entity": None, "signed": False, "periods": [t], "requires_period": False, "formula": "con observaciones / acreditados",
               "inputs": ["acr.observaciones_pct"], "scope": "system", "period_kind": "stock_at", "trivial": False,
               "base": "acreditados"}]
    if package["kpis"]["has_rec"]:
        ratios.append({"id": "ratio.reclamos_vs_anio_anterior", "value": v(f"rec.promedio.{y}") / v(f"rec.promedio.{y - 1}"),
                       "unit": "x", "entity": None, "signed": False, "periods": [f"{y}-01", t], "requires_period": False,
                       "formula": "promedio(t) / promedio(año anterior)", "inputs": [f"rec.promedio.{y}", f"rec.promedio.{y - 1}"],
                       "scope": "system", "period_kind": "ytd", "trivial": False, "base": None})
    package["derived_ratios"] = ratios
    package["ranks"] = []


def compose(package: dict, registry: dict | None = None, *, today: date, decision: dict | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg = registry["families"][FAMILY]
    tpl = cfg["templates"]
    v = package["values"]
    k = package["kpis"]
    t, y = package["period"], k["y"]
    V = lambda vid: v[vid]["value"]  # noqa: E731
    month, mlabel = sf.month_name(t), sf.month_label(t)
    acc, obs, tram, priv, pub = (V(x) for x in ("acr.acreditados", "acr.con_observaciones", "acr.tramite",
                                                 "acr.tramite.privadas", "acr.tramite.publicas"))
    obs_pct, priv_pct = V("acr.observaciones_pct"), V("acr.privadas_pct")
    headline = tpl["headline"]["default"].format(month_label=mlabel, acreditados=fmt_int(acc), tramite=fmt_int(tram))
    rec_clause = (f"Los reclamos promediaron {fmt_int(V(f'rec.promedio.{y}'))} al mes entre enero y {month}, "
                  f"{fmt_dec(abs(V('rec.pct')), 1)}% {'más' if V('rec.delta') >= 0 else 'menos'} que el promedio mensual de {y - 1}."
                  if k["has_rec"] else "")
    dek = tpl["dek"].format(rec_clause=rec_clause, titulos=fmt_int(V("rnpi.titulos"))).strip()
    qoq = k["comparisons"]

    def qoq_line(vid):
        return (f"{sf.fmt_signed(qoq[vid])} vs. {sf.month_label(k['prev'])}" if vid in qoq else "vs. boletín anterior: pendiente")

    kpis = [{"id": "acreditados", "label": "Prestadores acreditados", "value": fmt_int(acc), "prov": "C",
             "lines": [f"{fmt_int(obs)} con observaciones ({fmt_dec(obs_pct, 1)}%)", qoq_line("acr.acreditados")],
             "refs": ["acr.acreditados", "acr.con_observaciones", "acr.observaciones_pct"]},
            {"id": "tramite", "label": "Solicitudes en trámite", "value": fmt_int(tram), "prov": "C",
             "lines": [f"{fmt_int(priv)} privadas · {fmt_int(pub)} públicas", qoq_line("acr.tramite")],
             "refs": ["acr.tramite", "acr.tramite.privadas", "acr.tramite.publicas"]}]
    if k["has_rec"]:
        kpis.append({"id": "reclamos", "label": "Reclamos al mes", "value": fmt_int(V(f"rec.promedio.{y}")), "prov": "C",
                     "lines": [f"promedio enero–{month}", f"{fmt_dec(V('rec.pct'), 1, signed=True)}% vs. {y - 1} ({fmt_int(V(f'rec.promedio.{y - 1}'))})"],
                     "refs": [f"rec.promedio.{y}", "rec.pct", f"rec.promedio.{y - 1}"]})
    kpis.append({"id": "rnpi", "label": "Títulos en el RNPI", "value": fmt_int(V("rnpi.titulos")), "prov": "C",
                 "lines": ["títulos, no profesionales únicos", qoq_line("rnpi.titulos")], "refs": ["rnpi.titulos"]})

    pending_qoq = ("La comparación con el boletín anterior queda pendiente: ese boletín no tiene cifras verificadas en un "
                   "documento capturado." if not qoq else
                   f"Frente al boletín de {sf.month_label(k['prev'])}: stocks comparados, nunca sumados.")
    c_tram = {"id": "f6-tramite", "form": "bars", "unit": "solicitudes", "headline": "Solicitudes en tramitación por sector",
              "subtitle": f"Solicitudes de acreditación en tramitación al cierre de {mlabel}",
              "rows": [{"label": "Privados", "value": priv, "ref": "acr.tramite.privadas", "emphasis": True},
                       {"label": "Públicos", "value": pub, "ref": "acr.tramite.publicas"}],
              "table": {"columns": ["Sector", "Solicitudes", "% del total"],
                        "rows": [["Privados", fmt_int(priv), fmt_dec(priv_pct, 1) + "%"],
                                 ["Públicos", fmt_int(pub), fmt_dec(100 - priv_pct, 1) + "%"],
                                 ["Total", fmt_int(tram), "100%"]]},
              "source": "SIS, Boletín IP, acreditación. Denominador del %: solicitudes en tramitación."}
    values_pub_pct = 100 - priv_pct
    package["values"]["acr.publicas_pct"] = value("acr.publicas_pct", values_pub_pct, unit="%", period=t, source=None,
                                                  formula="100 − % privadas", inputs=["acr.privadas_pct"], kind="derived")
    c_obs = {"id": "f6-observaciones", "form": "bars", "unit": "prestadores", "headline": "Prestadores acreditados y observaciones",
             "subtitle": f"Prestadores acreditados al cierre de {mlabel}",
             "rows": [{"label": "Sin observaciones", "value": V("acr.sin_observaciones"), "ref": "acr.sin_observaciones"},
                      {"label": "Con observaciones", "value": obs, "ref": "acr.con_observaciones", "emphasis": True}],
             "table": {"columns": ["Situación", "Prestadores", "% de los acreditados"],
                       "rows": [["Sin observaciones", fmt_int(V("acr.sin_observaciones")), fmt_dec(100 - obs_pct, 1) + "%"],
                                ["Con observaciones", fmt_int(obs), fmt_dec(obs_pct, 1) + "%"],
                                ["Acreditados", fmt_int(acc), "100%"]]},
             "source": "SIS, Boletín IP, acreditación. Denominador del %: prestadores acreditados."}
    package["values"]["acr.sin_observaciones_pct"] = value("acr.sin_observaciones_pct", 100 - obs_pct, unit="%", period=t, source=None,
                                                           formula="100 − % con observaciones", inputs=["acr.observaciones_pct"], kind="derived")
    tabs = [{"id": "acreditacion", "label": "Acreditación", "charts": [c_tram, c_obs],
             "text": [f"Al cierre de {mlabel} había {fmt_int(acc)} prestadores acreditados; {fmt_int(obs)} tenían observaciones, "
                      f"el {fmt_dec(obs_pct, 1)}% de los acreditados.",
                      f"De las {fmt_int(tram)} solicitudes en tramitación, {fmt_int(priv)} eran de prestadores privados y "
                      f"{fmt_int(pub)} de públicos. La división pública/privada del stock acreditado no está verificada.",
                      pending_qoq]}]
    med_text = [f"La SIS registraba {fmt_int(V('med.mediadores'))} mediadores inscritos al cierre de {mlabel}."]
    if "med.solicitudes_acumuladas" in v:
        med_text.append(f"Las solicitudes de mediación acumuladas desde enero de {k['since']} suman "
                        f"{fmt_int(V('med.solicitudes_acumuladas'))}: es un flujo acumulado, no un stock, y no se divide por "
                        "el número de mediadores.")
    tabs.append({"id": "mediacion", "label": "Mediación", "charts": [], "text": med_text})
    if k["has_rec"]:
        c_rec = {"id": "f6-reclamos", "form": "bars", "unit": "reclamos", "headline": "Promedio mensual de reclamos",
                 "subtitle": f"Reclamos por mes: promedio de {y - 1} y de enero a {month} de {y}",
                 "rows": [{"label": str(y - 1), "value": V(f"rec.promedio.{y - 1}"), "ref": f"rec.promedio.{y - 1}"},
                          {"label": f"Ene–{month[:3]} {y}", "value": V(f"rec.promedio.{y}"), "ref": f"rec.promedio.{y}", "emphasis": True}],
                 "table": {"columns": ["Período", "Reclamos al mes"],
                           "rows": [[str(y - 1), fmt_int(V(f"rec.promedio.{y - 1}"))],
                                    [f"Enero–{month} {y}", fmt_int(V(f"rec.promedio.{y}"))],
                                    ["Variación", fmt_dec(V("rec.pct"), 1, signed=True) + "%"]]},
                 "source": "SIS, Boletín IP, reclamos. Promedios mensuales de un flujo; la SIS informa la variación redondeada."}
        rec_text = [f"Entre enero y {month} ingresaron en promedio {fmt_int(V(f'rec.promedio.{y}'))} reclamos al mes, frente a "
                    f"{fmt_int(V(f'rec.promedio.{y - 1}'))} en {y - 1}: {fmt_int(abs(V('rec.delta')))} "
                    f"{'más' if V('rec.delta') >= 0 else 'menos'} al mes."]
        if "rec.pct_informado" in v:
            rec_text.append(f"La SIS informa la variación redondeada ({fmt_int(V('rec.pct_informado'))}%); Alicanto la recalcula "
                            f"con los promedios publicados ({fmt_dec(V('rec.pct'), 1, signed=True)}%).")
        tabs.append({"id": "reclamos", "label": "Reclamos", "charts": [c_rec], "text": rec_text})
    rnpi_text = [f"El Registro Nacional de Prestadores Individuales tenía {fmt_int(V('rnpi.titulos'))} títulos inscritos al cierre "
                 f"de {mlabel}. Son títulos, no profesionales únicos: una persona puede tener más de uno."]
    if "rnpi.sin_fecha_nacimiento" in v:
        rnpi_text.append(f"{fmt_int(V('rnpi.sin_fecha_nacimiento'))} registros no tienen fecha de nacimiento.")
    tabs.append({"id": "rnpi", "label": "RNPI", "charts": [], "text": rnpi_text})

    paragraphs = [tabs[0]["text"][0], tabs[0]["text"][1], rnpi_text[0]]
    published = date.fromisoformat(package["published_at"][:10])
    expected = date.fromordinal(published.toordinal() + int(cfg["calendar"]["expected_release_interval_days"]))
    nxt = sf.shift_period(t, 3)
    late = (decision or {}).get("late_release")
    rejected_next = [r for r in package.get("rejected_releases") or [] if "documents_belong_to_other_release" in r.get("reasons", [])]
    if rejected_next:
        r = rejected_next[-1]
        watch = [{"headline": f"{r['title'].split('–')[-1].strip()}: la página publicada enlaza los documentos de otro boletín.",
                  "explanation": f"Alicanto no la usa hasta que la SIS publique los PDF de enero a {sf.month_name(nxt)}."}]
    elif late:
        watch = [{"headline": f"Boletín IP a {sf.month_label(nxt)}: publicación atrasada.",
                  "explanation": f"Lleva {late['days_late']} días de atraso según el calendario histórico."}]
    else:
        watch = [{"headline": f"Boletín IP a {sf.month_label(nxt)} (la SIS lo publicaría hacia el {sf.day_label(expected)}).",
                  "explanation": "Con dos boletines verificados se comparan los stocks entre cortes."}]
    watch.append({"headline": "Comparación entre boletines." if not qoq else "Solicitudes en tramitación.",
                  "explanation": ("Se activa cuando un segundo boletín tenga sus cifras verificadas en el documento capturado."
                                  if not qoq else "Un aumento del stock en trámite anticipa más acreditaciones o más espera.")})
    notes = [
        {"id": "n1", "text": "Acreditados, solicitudes en tramitación, mediadores y títulos son stocks al cierre del boletín: nunca se "
                             "suman entre boletines. Los reclamos son un promedio mensual de un flujo."},
        {"id": "n2", "text": "Denominadores: el % con observaciones usa los prestadores acreditados; el % privado usa las solicitudes "
                             "en tramitación; la variación de reclamos usa el promedio mensual del año anterior."},
        {"id": "n3", "text": "Las cifras vienen de una lectura independiente de los PDF de la SIS y cada una se comprueba en el texto "
                             "del PDF capturado (hash en Fuentes). Nada se lee del PDF por inferencia."},
        {"id": "n4", "text": "RNPI: cuenta títulos, no personas; otros registros del boletín usan otro denominador."},
        {"id": "n5", "text": "Ningún dato de esta ficha establece por qué cambian la acreditación, los reclamos o la mediación."},
    ]
    if k["unverified"]:
        notes.append({"id": "n6", "text": "Boletines capturados sin cifras verificadas (no se usan): " +
                      ", ".join(sf.month_label(p) for p in k["unverified"]) + "."})
    sources = [{**src, "key": key} for key, src in package["sources"].items()]
    triggers = (decision or {}).get("triggers") or []
    rule = "nuevo período" if "new_period" in triggers else ("revisión" if "revision" in triggers else "publicación vigente")
    machine = (f"Ficha generada por la regla \"{rule}\" (boletín {package.get('number')}, publicado el "
               f"{sf.day_label(package['published_at'])}). Las cifras vienen del paquete de evidencia; solo la Lectura Alicanto "
               "puede escribirla un modelo, y pasa por un verificador.")
    return {
        "schema_version": sf.SCHEMA, "id": f"stats-ficha:{FAMILY}:{t}", "family": FAMILY, "family_label": cfg["label"],
        "slug": cfg["slug"], "period": t, "published_at": package["published_at"], "release_key": package["release_key"],
        "kicker": tpl["kicker"].format(label=cfg["label"]),
        "kicker_meta": tpl["kicker_meta"].format(period_label=mlabel, published_label=sf.day_label(package["published_at"]),
                                                 cadence_phrase=cfg["cadence_phrase"]),
        "headline": headline, "headline_type": "default", "dek": dek, "dek_emphasis": f"{fmt_int(acc)} prestadores acreditados",
        "kpis": kpis, "tabs": tabs,
        "facts": {"heading": "Qué muestran los datos", "paragraphs": paragraphs, "rendered_in_tabs": True},
        "watch": watch[:2], "notes": notes, "sources": sources, "machine_note": machine,
        "featured": bool((decision or {}).get("featured")), "triggers": triggers, "late_release": late,
        "revisions": package.get("revisions") or [],
    }


def run(root: Path, *, today: date, registry: dict | None = None, llm: bool = True,
        model_call: Callable[..., Any] | None = None, budget: Callable[[float], tuple[bool, str]] | None = None) -> dict:
    return sf.run_family(FAMILY, builder_version=BUILDER_VERSION, build_package=build_package, compose=compose, root=Path(root),
                         today=today, registry=registry, llm=llm, model_call=model_call, budget=budget)
