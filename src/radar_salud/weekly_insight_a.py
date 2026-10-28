"""Weekly insight generator, presentation A (Dirección, 27-oct-2026: renewed every Monday).

Pipeline (one run per Monday, fail-closed):

1. ``select_topic``      deterministic ranking of the feed in the 14 days before the anchor Monday.
2. ``build_evidence``    candidate + related signals + deterministic statistical series from the
                          repo; every number available to the writer is collected in ``numbers``.
3. drafting model       writes format A as JSON (headline, dek, charts, essay.facts/reading,
                          watch, notes, estimates, key_figures, sources) from that evidence only.
4. ``normalize_draft``   recomputes estimates from their formulas, fills chart rows that point to a
                          deterministic series, keeps only evidence URLs, stamps Monday dates.
5. ``verify_candidate``  deterministic gate: presentation-A rules 1–6 (rule 3 traceability and
                          rule 5 normative IDs included) plus key_figures/estimate inputs traced to
                          the evidence numbers, sources restricted to the evidence package.
6. review model         an independent second model (different from the writer) returns PASS/FAIL.
7. ``publish``           PASS → archive the previous approved file and write the new one;
                          FAIL → the approved file is untouched (it expires by the Monday rule) and
                          the candidate with its verification and review goes to ``candidates/``.

Model calls go through an injectable ``model_call(prompt, *, feature, preferred_model,
allow_luna_fallback, max_output_tokens)`` so tests use fake models; the default is
``openai_runtime.call_json``, which enforces the weekly and the paced monthly budget.
"""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .ai_pricing import estimate as price_estimate
from .weekly_freshness import (
    MONDAY_EVIDENCE_DAYS, SAFE_FORMULA, WINDOW_DAYS, chile_today, iso_day, monday_anchor,
    number_traces, numbers_in, presentation_a_errors, chart_repetition_warnings,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "weekly_insight_a_v1"
ROUTING = ROOT / "config/model_routing_v1.json"
# Best available writer in the routing table, and a different family member as reviewer.
DRAFT_ROUTE, REVIEW_ROUTE = "astra", "terra"
DRAFT_MAX_OUTPUT, REVIEW_MAX_OUTPUT = 6000, 3000
MAX_RUN_USD = 1.0          # per weekly run, worst case (prompt + full max_output on every call)
CHARS_PER_TOKEN = 3.2      # conservative for Spanish JSON

# ---------------------------------------------------------------------------------------------
# 1. Topic selection


def _day(value: Any) -> date | None:
    return iso_day(str(value)[:10]) if value else None


def _https(url: Any) -> bool:
    return isinstance(url, str) and url.startswith("https://") and len(url) > 12


def _text(signal: dict) -> str:
    return " ".join(str(signal.get(k) or "") for k in (
        "title", "display_title", "what_happened", "card_what", "why_it_matters", "card_why"))


def _quantities(signal: dict) -> int:
    return len(numbers_in(_text(signal)))


WORD = re.compile(r"[a-záéíóúñ]{5,}", re.I)
STOP = set("""según sobre entre desde hasta porque donde cuando mientras también además personas
nota informó señaló reportó durante través mismo otros otras puede pueden podría salud chile chilena
chileno nacional pública público sistema servicio ministerio millones pulso tercera diario financiero
artículo publicación octubre septiembre noviembre""".split())


def _keywords(signal: dict) -> set[str]:
    return {w.casefold() for w in WORD.findall(_text(signal))} - STOP


def _stems(text: str) -> set[str]:
    """Crude 6-letter stems so envejecer/envejecimiento or licencia/licencias match."""
    return {w.casefold()[:6] for w in WORD.findall(text or "") if w.casefold() not in STOP}


def related_signals(candidate: dict, signals: list[dict], anchor: date, days: int = 45, limit: int = 6,
                    min_weight: float = 9.0) -> list[dict]:
    """Context signals in the ``days`` before the anchor about the same subject: they must share at
    least one distinctive stem of the candidate's TITLE, and enough distinctive stems overall,
    weighted by inverse document frequency over the window (common words weigh ~0)."""
    window = [s for s in signals if (d := _day(s.get("event_date"))) and anchor - timedelta(days=days) <= d <= anchor
              and s.get("feed_visibility") is not False]
    vocab = [_stems(_text(s)) for s in window]
    df: dict[str, int] = {}
    for words in vocab:
        for w in words:
            df[w] = df.get(w, 0) + 1
    n = max(len(window), 1)
    idf = lambda w: math.log(n / df[w]) if df.get(w) and df[w] <= max(3, 0.08 * n) else 0.0
    title = {w for w in _stems(candidate.get("title") or "") if idf(w) > 0}
    body = {w: idf(w) for w in _stems(_text(candidate))}
    out = []
    for s, words in zip(window, vocab):
        if s is candidate or s.get("source_url") == candidate.get("source_url"):
            continue
        shared_title = title & words
        weight = sum(body.get(w, 0.0) for w in words) + sum(idf(w) for w in shared_title)
        if shared_title and weight >= min_weight:
            out.append((weight + min(_quantities(s), 6), s))
    out.sort(key=lambda x: (-x[0], str(x[1].get("event_date"))))
    return [s for _, s in out[:limit]]


def select_topic(signals: list[dict], anchor: date, *, recent_urls: set[str] | None = None,
                 recent_scopes: list[str] | None = None, recent_text: str = "",
                 window_days: int = MONDAY_EVIDENCE_DAYS) -> list[dict]:
    """Rank the feed of the ``window_days`` before the anchor Monday. Deterministic; no model.

    Score: editorial relevance and economic impact, source quality, number density (charts need
    numbers), corroboration by related signals, recency (last 7 days preferred), and a penalty
    for repeating last week's scope or source."""
    recent_urls, recent_scopes = recent_urls or set(), recent_scopes or []
    recent_words = _keywords({"title": recent_text})
    ranked = []
    for s in signals:
        d = _day(s.get("event_date"))
        if not d or not (anchor - timedelta(days=window_days) <= d < anchor):
            continue
        if not _https(s.get("source_url")) or not s.get("title") or s.get("feed_visibility") is False:
            continue
        if s.get("source_url") in recent_urls or s.get("editorial_hold") or s.get("hold"):
            continue
        if str(s.get("system_domain") or "HEALTH") == "OCCUPATIONAL_HEALTH" and not s.get("scopes"):
            continue
        related = related_signals(s, signals, anchor)
        score = (0.30 * float(s.get("editorial_relevance") or s.get("radar_score") or 0)
                 + 0.20 * float(s.get("economic_impact_score") or 0)
                 + 0.10 * float(s.get("source_quality_score") or 0)
                 + 3.0 * min(_quantities(s) + sum(min(_quantities(r), 3) for r in related), 12)
                 + 2.0 * min(len(related), 4)
                 + (5.0 if (anchor - d).days <= 7 else 0.0)
                 - (8.0 if set(s.get("scopes") or []) & set(recent_scopes) else 0.0)
                 - (20.0 if len(_keywords(s) & recent_words) >= 4 else 0.0))
        ranked.append({"score": round(score, 2), "signal": s, "related": related})
    ranked.sort(key=lambda x: (-x["score"], str(x["signal"].get("event_date"))))
    return ranked


# ---------------------------------------------------------------------------------------------
# 2. Evidence package with deterministic statistical series


def _isapre_series(root: Path, candidate: dict) -> list[dict]:
    """Open-isapre beneficiaries (SIS monthly portfolio) when the topic concerns isapres."""
    scopes = " ".join(candidate.get("scopes") or []) + " " + _text(candidate)
    if "isapre" not in scopes.casefold():
        return []
    path = root / "data/market/isapre_portfolio.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    series = [{"id": "isapres_abiertas_beneficiarios", "label": "Beneficiarios de isapres abiertas",
               "unit": "personas", "source_url": None,
               "rows": [{"label": c["period"], "value": c["total_beneficiaries"]} for c in data.get("coverage") or []
                        if isinstance(c, dict) and c.get("total_beneficiaries")]}]
    codes = {str(r.get("canonical_id", "")).rsplit(":", 1)[-1] for r in candidate.get("entity_refs") or []
             if str(r.get("canonical_id", "")).startswith("cl:isapre:")}
    for code in sorted(codes):
        rows = [o for o in data.get("observations") or [] if str(o.get("official_code")) == code]
        for metric, unit in (("beneficiarios", "personas"), ("beneficiary_share", "%")):
            pts = [{"label": o["period"], "value": round(float(o["value"]), 2)} for o in rows if o.get("metric_id") == metric]
            if pts:
                series.append({"id": f"isapre_{code}_{metric}", "label": f"Isapre código {code}: {metric}",
                               "unit": unit, "source_url": rows[0].get("source_url"), "rows": pts})
    if series and series[0]["rows"]:
        series[0]["source_url"] = (data.get("observations") or [{}])[0].get("source_url")
    return [s for s in series if s["rows"]]


def _verified_metrics_series(root: Path, urls: set[str]) -> list[dict]:
    path = root / "config/statistical_analysis_verified_v1.json"
    try:
        docs = json.loads(path.read_text(encoding="utf-8")).get("primary_review", {}).get("documents") or []
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for doc in docs:
        if doc.get("url") in urls and isinstance(doc.get("verified_metrics"), dict):
            rows = [{"label": k, "value": v} for k, v in doc["verified_metrics"].items() if isinstance(v, (int, float))]
            out.append({"id": "verified:" + doc["url"].rsplit("/", 1)[-1], "label": "Métricas verificadas",
                        "unit": None, "source_url": doc["url"], "rows": rows})
    return out


STAT_PROVIDERS: list[Callable[[Path, dict, set[str]], list[dict]]] = [
    lambda root, c, urls: _isapre_series(root, c),
    lambda root, c, urls: _verified_metrics_series(root, urls),
]


# Small counts are often written in words in the press ("solo una de 24", "ninguna de las nueve").
WORD_NUMBERS = {"ninguna": 0, "ninguno": 0, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
                "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12}


def evidence_numbers(text: str) -> set[float]:
    found = {abs(n) for _, n, _ in numbers_in(text)}
    found |= {float(WORD_NUMBERS[w.casefold()]) for w in re.findall(r"[a-záéíóúñ]+", text, re.I) if w.casefold() in WORD_NUMBERS}
    return found


def _brief(s: dict) -> dict:
    return {"title": s.get("display_title") or s.get("title"), "source_name": s.get("source_name"),
            "source_type": s.get("source_type"), "url": s.get("source_url"), "event_date": s.get("event_date"),
            "what": s.get("card_what") or s.get("what_happened"), "why": s.get("card_why") or s.get("why_it_matters"),
            "evidence_maturity": s.get("evidence_maturity"),
            **{k: s[k] for k in ("key_numbers", "data_insights", "summary_table") if s.get(k)}}


def build_evidence(choice: dict, root: Path = ROOT) -> dict:
    candidate, related = choice["signal"], choice["related"]
    items = [_brief(candidate)] + [_brief(r) for r in related]
    urls = {x["url"] for x in items if _https(x["url"])}
    series = [s for p in STAT_PROVIDERS for s in p(root, candidate, urls)]
    numbers = sorted(set().union(*[evidence_numbers(json.dumps(x, ensure_ascii=False)) for x in items])
                     | {abs(float(r["value"])) for s in series for r in s["rows"]})
    sources = [{"label": x["title"], "url": x["url"], "source_name": x["source_name"],
                "source_type": x["source_type"], "event_date": x["event_date"]} for x in items if _https(x["url"])]
    sources += [{"label": s["label"], "url": s["source_url"], "source_name": "Serie Alicanto", "source_type": "statistical_series",
                 "event_date": None} for s in series if _https(s.get("source_url")) and s["source_url"] not in urls]
    return {"candidate": items[0], "related": items[1:], "series": series, "numbers": numbers,
            "sources": sources, "allowed_urls": sorted({s["url"] for s in sources}), "score": choice.get("score")}


# ---------------------------------------------------------------------------------------------
# 3. Prompts

FORMAT_A = """Formato A (aprobado por Dirección; JSON puro, sin texto fuera del JSON):
{"headline": "≤140 caracteres; toma posición, sin causalidad no demostrada",
 "dek": "≤40 palabras; SOLO hechos",
 "key_figures": ["cifra textual de la evidencia, con su fuente y fecha", ...],
 "estimates": [{"id","label","value","unit","display","formula":"solo dígitos y + - * / ( )","inputs":["cifra de la evidencia"],"note_ref":"nX"}],
 "charts": [{"id","form":"paired_bars|columns","headline":"titular afirmativo","subtitle","unit",
             "series_ref":"id de una serie de EVIDENCIA.series (opcional; sus filas se copian tal cual)",
             "series":[{"key","label","emphasis"}] (solo paired_bars), "rows":[{"label","value"} | {"label","values":{key:valor}}],
             "source","note_refs":[]}],   // barras desde cero; período parcial: "style":"partial" + "partial_label"
 "essay": {"facts": {"heading":"Qué pasó","paragraphs":[...]}, "reading": {"heading":"Lectura Alicanto","paragraphs":[...]}},
 "watch": [{"headline","explanation":"≥12 palabras, autoexplicativa"}],
 "notes": [{"id":"n1","kind":"estimate|causality|press|coverage|non_final|survey","text"}],
 "sources": [{"label","url","role","short_label","short_role"}],
 "insight_teaser": "≤30 palabras para la tarjeta"}"""

RULES = """Reglas (se verifican de forma determinista; si fallas, no se publica):
1. Usa EXCLUSIVAMENTE la EVIDENCIA. Cada número de headline, dek, ensayo, qué mirar y gráficos debe estar
   literalmente en key_figures (copiado de la evidencia) o ser una estimación declarada con fórmula.
2. essay.facts: solo hechos; prohibido "sugiere", "podría", "estimamos", "Alicanto". essay.reading: la
   interpretación de Alicanto; nunca empieza con "Hecho:". Ensayo total 150–250 palabras.
3. Todo [^nX] del ensayo, de charts[].note_refs y de estimates[].note_ref existe en notes, y toda nota se usa.
4. No repitas en essay.facts las cifras que ya muestran los gráficos.
5. Si nombras una Circular, Ley, DS, artículo o Resolución, la MISMA frase explica en lenguaje llano qué
   exige o permite la norma. Si no puedes explicarla en una línea, no la nombres.
6. Prensa se declara como prensa en notes; una encuesta, como percepción; una meta anunciada, como meta.
7. No inventes causalidad; sources solo con URLs de la EVIDENCIA. Español de Chile, formato 12,3% y 5.155.495."""


def draft_prompt(evidence: dict, anchor: date) -> str:
    payload = {k: evidence[k] for k in ("candidate", "related", "series", "sources")}
    return ("Eres el editor senior de Alicanto Salud (inteligencia de mercado de salud en Chile, lectores "
            "ejecutivos de Isapres, Fonasa, prestadores, mutualidades y laboratorios). Escribe el Insight "
            f"semanal del lunes {anchor.isoformat()}. Prioriza claridad ejecutiva e información incremental, "
            "no extensión.\n" + FORMAT_A + "\n" + RULES + "\nEVIDENCIA:\n" + json.dumps(payload, ensure_ascii=False))


def review_prompt(weekly: dict, evidence: dict, verification: dict) -> str:
    shown = {k: weekly.get(k) for k in ("headline", "dek", "key_figures", "estimates", "charts", "essay", "watch", "notes", "sources")}
    return ("Eres un revisor editorial independiente de Alicanto Salud (no escribiste este texto). Revisa el "
            "Insight semanal contra la EVIDENCIA con cinco lentes: editorial, negocio de salud, datos, evidencia y "
            "decisión. Falla (FAIL) si hay una cifra que no está en la evidencia, una causalidad no demostrada, "
            "una inferencia presentada como hecho, una norma sin explicar, prensa o encuesta no declarada como tal, "
            "o si la lectura no aporta información incremental a un ejecutivo del sector. "
            'Devuelve JSON puro: {"verdict":"PASS|FAIL","issues":[{"severity":"blocker|major|minor","where","text"}],'
            '"lenses":{"editorial","health_business","data","evidence","decision_intelligence"}}.\n'
            "VERIFICACIÓN DETERMINISTA: " + json.dumps(verification, ensure_ascii=False) +
            "\nINSIGHT:\n" + json.dumps(shown, ensure_ascii=False) +
            "\nEVIDENCIA:\n" + json.dumps({k: evidence[k] for k in ("candidate", "related", "series")}, ensure_ascii=False))


# ---------------------------------------------------------------------------------------------
# 4. Normalisation (deterministic)


def _eval_formula(formula: str) -> float | None:
    if not formula or not SAFE_FORMULA.match(formula):
        return None
    try:
        value = eval(formula, {"__builtins__": {}}, {})  # digits and arithmetic only (SAFE_FORMULA)
    except Exception:
        return None
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "").casefold().translate(str.maketrans("áéíóúñ", "aeioun")))
    return s.strip("-")[:48] or "insight"


def normalize_draft(raw: dict, evidence: dict, anchor: date) -> dict:
    w = deepcopy(raw) if isinstance(raw, dict) else {}
    series = {s["id"]: s for s in evidence.get("series") or []}
    for chart in w.get("charts") or []:
        ref = chart.pop("series_ref", None) if isinstance(chart, dict) else None
        if ref in series:  # rows come from the repo, never from the model
            chart["rows"] = deepcopy(series[ref]["rows"])
            chart["deterministic_series"] = ref
    for est in w.get("estimates") or []:
        if isinstance(est, dict):
            value = _eval_formula(str(est.get("formula") or ""))
            if value is not None:
                est["value"] = round(value, 2)
    allowed = set(evidence.get("allowed_urls") or [])
    w["sources"] = [s for s in w.get("sources") or [] if isinstance(s, dict) and s.get("url") in allowed]
    w["source_refs"] = [s["url"] for s in w["sources"]]
    cand = evidence.get("candidate") or {}
    words = sum(len(str(x).split()) for x in [w.get("headline"), w.get("dek")]
                + list(((w.get("essay") or {}).get("facts") or {}).get("paragraphs") or [])
                + list(((w.get("essay") or {}).get("reading") or {}).get("paragraphs") or []))
    w.update({
        "id": f"weekly-insight:{anchor.isoformat()}:{_slug(w.get('headline'))[:32]}",
        "schema_version": SCHEMA,
        "title": w.get("headline"), "insight_title": w.get("headline"),
        "event_date": cand.get("event_date"), "freshness_anchor_date": anchor.isoformat(),
        "anchor_kind": "monday", "expires_on": (anchor + timedelta(days=WINDOW_DAYS)).isoformat(),
        "source_name": cand.get("source_name"), "source_url": cand.get("url"),
        "summary": w.get("dek"), "weekly_mode": "monday_format_a",
        "watch_heading": w.get("watch_heading") or "Qué mirar en las próximas semanas",
        "reading_time_min": max(1, round(words / 200)) if words else 1,
    })
    return w


# ---------------------------------------------------------------------------------------------
# 5. Deterministic verification


def verify_candidate(weekly: dict, evidence: dict, anchor: date) -> dict:
    errors = list(presentation_a_errors(weekly))
    for key in ("headline", "dek", "essay", "notes", "sources", "key_figures"):
        if not weekly.get(key):
            errors.append(f"missing:{key}")
    pool = [float(n) for n in evidence.get("numbers") or []]
    # key_figures and estimate inputs must come from the evidence package (not from the model).
    for fig in weekly.get("key_figures") or []:
        for token, value, decimals in numbers_in(fig):
            if not number_traces(value, decimals, pool):
                errors.append(f"key_figure_not_in_evidence:{token}")
    estimate_values = [abs(float(e.get("value"))) for e in weekly.get("estimates") or []
                       if isinstance(e, dict) and isinstance(e.get("value"), (int, float))]
    for est in weekly.get("estimates") or []:
        if not isinstance(est, dict):
            continue
        formula = str(est.get("formula") or "")
        if _eval_formula(formula) is None:
            errors.append(f"estimate_formula_invalid:{est.get('id')}")
            continue
        for token in re.findall(r"\d+(?:\.\d+)?", formula):
            value = float(token)
            if value in (100.0, 1.0, 0.0) or number_traces(value, len(token.split(".")[1]) if "." in token else 0, pool + estimate_values):
                continue
            # rates written as factors (0.877 = 1 − 12,3%) trace through their complement
            if 0 < value < 1 and number_traces(round((1 - value) * 100, 6), 1, pool):
                continue
            errors.append(f"estimate_input_not_in_evidence:{est.get('id')}:{token}")
    allowed = set(evidence.get("allowed_urls") or [])
    if not weekly.get("source_refs") or any(u not in allowed for u in weekly["source_refs"]):
        errors.append("sources_outside_evidence")
    if len(weekly.get("watch") or []) > 3:
        errors.append("watch_over_3")
    if not 1 <= len(weekly.get("charts") or []) <= 2:
        errors.append("charts_count_out_of_range")
    for chart in weekly.get("charts") or []:
        if not isinstance(chart, dict) or chart.get("form") not in ("paired_bars", "columns"):
            errors.append("chart_form_invalid")
        elif chart.get("form") == "paired_bars" and len(chart.get("series") or []) < 2:
            errors.append(f"paired_bars_without_two_series:{chart.get('id')}")
    if weekly.get("freshness_anchor_date") != anchor.isoformat() or anchor.weekday() != 0:
        errors.append("anchor_not_monday")
    event = iso_day(weekly.get("event_date"))
    if not event or not 0 <= (anchor - event).days <= MONDAY_EVIDENCE_DAYS:
        errors.append("event_outside_14_day_window")
    return {"verdict": "PASS" if not errors else "FAIL", "errors": errors,
            "warnings": chart_repetition_warnings(weekly)}


# ---------------------------------------------------------------------------------------------
# 6. Orchestration with cost guard


def _routes(path: Path = ROUTING) -> dict[str, str]:
    try:
        return {k: v["model"] for k, v in json.loads(path.read_text(encoding="utf-8"))["routes"].items()}
    except (OSError, ValueError, KeyError, TypeError):
        return {"luna": "gpt-5.6-luna", "terra": "gpt-5.6-terra", "astra": "gpt-6-astra"}


def worst_case_cost(model: str, prompt: str, max_output_tokens: int) -> float:
    return price_estimate(model, math.ceil(len(prompt) / CHARS_PER_TOKEN), max_output_tokens)


def estimate_run_cost(evidence: dict, routes: dict[str, str] | None = None, *, draft_output_tokens: int = 3500,
                      review_output_tokens: int = 1200, anchor: date | None = None) -> dict:
    """Expected (typical output) and worst case (full max_output on every call) for one Monday run."""
    routes = routes or _routes()
    anchor = anchor or date(2026, 11, 2)
    dp = draft_prompt(evidence, anchor)
    din = math.ceil(len(dp) / CHARS_PER_TOKEN)
    rin = din + 3500  # review prompt carries the evidence plus the draft
    draft, review = routes[DRAFT_ROUTE], routes[REVIEW_ROUTE]
    typical = price_estimate(draft, din, draft_output_tokens) + price_estimate(review, rin, review_output_tokens)
    worst = price_estimate(draft, din, DRAFT_MAX_OUTPUT) + price_estimate(review, rin, REVIEW_MAX_OUTPUT)
    return {"draft_model": draft, "review_model": review, "draft_input_tokens": din, "review_input_tokens": rin,
            "typical_usd": round(typical, 4), "worst_case_usd": round(worst, 4), "cap_usd": MAX_RUN_USD}


def _default_model_call(prompt, **kw):
    from .openai_runtime import call_json  # lazy: the openai package is only needed for live runs
    return call_json(prompt, **kw)


def run_weekly_a(signals: list[dict], *, as_of: date | None = None, root: Path = ROOT,
                 model_call: Callable[..., Any] | None = None, previous: dict | None = None,
                 max_run_usd: float = MAX_RUN_USD) -> dict:
    as_of = as_of or chile_today()
    anchor = monday_anchor(as_of)
    prev = (previous or {}).get("weekly_insight") or {}
    ranked = select_topic(signals, anchor, recent_urls=set(prev.get("source_refs") or []),
                          recent_scopes=list((previous or {}).get("recent_scopes") or []),
                          recent_text=" ".join(str(prev.get(k) or "") for k in ("headline", "dek", "summary")))
    base = {"anchor_date": anchor.isoformat(), "expires_on": (anchor + timedelta(days=WINDOW_DAYS)).isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "topic_ranking": [{"score": r["score"], "title": r["signal"].get("title"), "url": r["signal"].get("source_url"),
                               "event_date": r["signal"].get("event_date"), "related": len(r["related"])} for r in ranked[:5]]}
    if not ranked:
        return {**base, "status": "no_candidate", "weekly_insight": None}
    evidence = build_evidence(ranked[0], root)
    routes = _routes()
    base["cost_estimate"] = estimate_run_cost(evidence, routes, anchor=anchor)
    base["evidence"] = evidence
    model_call = model_call or _default_model_call
    spent, calls = 0.0, []

    def call(route: str, prompt: str, feature: str, max_out: int):
        nonlocal spent
        model = routes[route]
        if spent + worst_case_cost(model, prompt, max_out) > max_run_usd:
            raise RuntimeError("weekly_run_cap_would_be_exceeded")
        result = model_call(prompt, feature=feature, preferred_model=model, allow_luna_fallback=False,
                            max_output_tokens=max_out)
        cost = float(getattr(result, "estimated_cost_usd", 0) or 0)
        spent += cost
        calls.append({"feature": feature, "model": getattr(result, "model", model), "cost_usd": cost,
                      "response_id": getattr(result, "response_id", None)})
        return result

    try:
        drafted = call(DRAFT_ROUTE, draft_prompt(evidence, anchor), "weekly_insight_a_draft", DRAFT_MAX_OUTPUT)
    except Exception as exc:  # budget, provider or parse error: nothing is published
        return {**base, "status": "generation_error", "error": f"{type(exc).__name__}:{exc}"[:300],
                "weekly_insight": None, "model_calls": calls}
    weekly = normalize_draft(drafted.output, evidence, anchor)
    verification = verify_candidate(weekly, evidence, anchor)
    out = {**base, "candidate": weekly, "verification": verification, "model_calls": calls}
    if verification["verdict"] != "PASS":
        return {**out, "status": "deterministic_fail", "weekly_insight": None,
                "review": {"verdict": "NOT_RUN", "reason": "deterministic_fail"}}
    try:
        reviewed = call(REVIEW_ROUTE, review_prompt(weekly, evidence, verification), "weekly_insight_a_review", REVIEW_MAX_OUTPUT)
        review = reviewed.output if isinstance(reviewed.output, dict) else {}
    except Exception as exc:
        return {**out, "status": "review_error", "weekly_insight": None, "model_calls": calls,
                "review": {"verdict": "NOT_RUN", "reason": f"{type(exc).__name__}:{exc}"[:300]}}
    blockers = [i for i in review.get("issues") or [] if isinstance(i, dict) and i.get("severity") == "blocker"]
    review_model = calls[-1]["model"]
    independent = review_model != calls[0]["model"]
    passed = review.get("verdict") == "PASS" and not blockers and independent
    out.update(review=review, model_calls=calls, total_cost_usd=round(spent, 6))
    if not passed:
        return {**out, "status": "review_fail", "weekly_insight": None}
    weekly["model_trace"] = {"api_call": True, "draft_model": calls[0]["model"], "review_model": review_model,
                             "response_ids": [c["response_id"] for c in calls], "estimated_cost_usd": round(spent, 6)}
    weekly["editorial_review_pass"] = True
    out.update(status="pass", weekly_insight=weekly, audit={
        "verdict": "PASS", "editorial_business_review_pass": True, "independent_second_reviewer": True,
        "reviewer": f"{review_model} (revisor independiente del redactor {calls[0]['model']})",
        "deterministic_verification": verification, "lenses": review.get("lenses") or {},
        "minor_issues": [i for i in review.get("issues") or [] if isinstance(i, dict) and i.get("severity") != "blocker"],
        "presentation": {"format": SCHEMA, "approved_by": "pipeline (verificación determinista + revisor independiente)"}})
    return out


# ---------------------------------------------------------------------------------------------
# 7. Publication (PASS) or candidate for the coordinator (FAIL)


def publish(result: dict, root: Path = ROOT) -> dict:
    """Write files. Only a PASS replaces editorial_approved.json; FAIL never publishes."""
    folder = root / "data/weekly_insight"
    approved_path = folder / "editorial_approved.json"
    anchor = result.get("anchor_date") or "unknown"
    if result.get("status") == "pass" and result.get("weekly_insight"):
        try:
            previous = json.loads(approved_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = None
        archived = None
        if previous:
            pw = previous.get("weekly_insight") or {}
            key = pw.get("freshness_anchor_date") or pw.get("event_date") or "unknown"
            archived = folder / "archive" / f"{key}.json"
            archived.parent.mkdir(parents=True, exist_ok=True)
            if not archived.exists():
                archived.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        weekly = result["weekly_insight"]
        payload = {"status": "pass", "generated_at": result.get("generated_at"),
                   "top3": [{"url": r["url"], "title": r["title"]} for r in result.get("topic_ranking", [])[:3]],
                   "weekly_insight": weekly, "audit": result["audit"],
                   "freshness_gate": {"anchor": weekly["freshness_anchor_date"], "anchor_kind": "monday",
                                      "expires_on": weekly["expires_on"]},
                   "model": weekly.get("model_trace")}
        approved_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"published": True, "approved": str(approved_path), "archived": str(archived) if archived else None}
    out = folder / "candidates" / f"{anchor}-candidate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {k: result.get(k) for k in ("status", "anchor_date", "expires_on", "generated_at", "topic_ranking",
                                          "cost_estimate", "candidate", "verification", "review", "model_calls",
                                          "total_cost_usd", "error")}
    record["coordinator_note"] = ("No publicado: el insight aprobado anterior se mantiene en editorial_approved.json "
                                  "y vence por la regla del lunes; requiere revisión del coordinador.")
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"published": False, "candidate": str(out)}
