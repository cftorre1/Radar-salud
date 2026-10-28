"""Statistics fichas by family (Dirección, 28-oct-2026): one live ficha per family.

Framework shared by every family (F1 Cartera first; see ``stats_ficha_f1``):

1. Registry      ``config/stats_fichas_v1.json``: formulas, denominators, thresholds, pitfalls,
                  calendar and headline templates per family.
2. Evidence      a deterministic package: every value carries provenance (URL, SHA-256, sheet/cell
                  locator, period, publication date, fetch date) and revision flags. Derived values
                  record their formula and input ids. Nothing is computed by a model.
3. Triggers      new period, threshold crossed, revision (> 0,5 %), late release, and HOLD on a
                  reconciliation failure, an older period or a missing hash.
4. Templates     headline / dek / facts filled by code from the package.
5. Lectura       the only model-written block (≤ 90 words). ``verify_lectura`` rejects numbers
                  outside the package, causal verbs without a causal note, Isapres outside the
                  package and texts over 90 words. No budget or a FAIL → the block is omitted and the
                  ficha still publishes (decision 3).
6. Publication   PASS (deterministic verification + reconciliation) replaces the live ficha and
                  archives the previous one (decisions 1 and 2). FAIL → HOLD file, live untouched.
7. Snapshot      ``apply_to_snapshot`` emits live fichas as feed cards and removes the loose cards
                  and legacy pulses they supersede.
"""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .weekly_freshness import number_traces, numbers_in

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config/stats_fichas_v1.json"
STORE = Path("data/stats_fichas")
SCHEMA = "stats_ficha_v1"
HEX64 = re.compile(r"[0-9a-f]{64}")
REVISION_REPUBLISH_PCT = 0.5

MONTHS_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
             "octubre", "noviembre", "diciembre")
ORDINAL_WORDS = {2: "segundo", 3: "tercer", 4: "cuarto", 5: "quinto", 6: "sexto", 7: "séptimo", 8: "octavo"}


# ---------------------------------------------------------------------------------------------
# Registry and formatting


def load_registry(path: Path | None = None) -> dict:
    return json.loads(Path(path or REGISTRY_PATH).read_text(encoding="utf-8"))


def family_config(family: str, registry: dict | None = None) -> dict:
    return (registry or load_registry())["families"][family]


def fmt_int(n: float) -> str:
    """Chilean thousands separator and typographic minus: −27.355."""
    v = int(round(n))
    return ("−" if v < 0 else "") + f"{abs(v):,}".replace(",", ".")


def fmt_signed(n: float) -> str:
    v = int(round(n))
    return ("+" if v > 0 else "") + fmt_int(v)


def fmt_dec(x: float, digits: int = 1, signed: bool = False) -> str:
    q = round(float(x), digits)
    if q == 0:
        q = 0.0
    text = f"{abs(q):,.{digits}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    sign = "−" if q < 0 else ("+" if signed and q > 0 else "")
    return sign + text


def period_parts(period: str) -> tuple[int, int]:
    m = re.fullmatch(r"(20\d{2})-(\d{2})", str(period or ""))
    if not m or not 1 <= int(m[2]) <= 12:
        raise ValueError(f"invalid_period:{period}")
    return int(m[1]), int(m[2])


def month_name(period: str) -> str:
    return MONTHS_ES[period_parts(period)[1] - 1]


def month_label(period: str) -> str:
    y, m = period_parts(period)
    return f"{MONTHS_ES[m - 1]} {y}"


def month_short(period: str) -> str:
    return month_name(period)[:3].capitalize()


def shift_period(period: str, months: int) -> str:
    y, m = period_parts(period)
    k = y * 12 + (m - 1) + months
    return f"{k // 12}-{k % 12 + 1:02d}"


def day_label(day: str | date) -> str:
    d = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
    return f"{d.day} {MONTHS_ES[d.month - 1][:3]}"


def ordinal(n: int) -> str:
    return ORDINAL_WORDS.get(n, f"{n}.º")


# ---------------------------------------------------------------------------------------------
# Evidence package


def source_ref(*, url: str, sha256: str, published_at: str | None, fetched_at: str | None, label: str,
               role: str, locator: str) -> dict:
    return {"url": url, "sha256": sha256, "published_at": published_at, "fetched_at": fetched_at,
            "label": label, "role": role, "locator": locator}


def value(vid: str, val: float, *, unit: str, period: str, source: str | None, locator: str | None = None,
          formula: str | None = None, inputs: list[str] | None = None, kind: str = "captured") -> dict:
    """One evidence entry. ``kind`` is 'captured' (read from a file) or 'derived' (formula + inputs)."""
    return {"id": vid, "value": val, "unit": unit, "period": period, "source": source, "locator": locator,
            "formula": formula, "inputs": inputs or [], "kind": kind, "revised": None}


def number_pool(package: dict) -> list[float]:
    """Every number a ficha or a Lectura may show: package values, derived values and rule constants."""
    pool: set[float] = set()
    for v in (package.get("values") or {}).values():
        x = v.get("value")
        if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x):
            pool.add(abs(float(x)))
    for x in package.get("constants") or []:
        pool.add(abs(float(x)))
    return sorted(pool)


def text_numbers_trace(text: str, pool: list[float]) -> list[str]:
    """Tokens in ``text`` that do not equal a pool value rounded to the shown precision."""
    return [tok for tok, val, dec in numbers_in(text) if not number_traces(val, dec, pool)]


def release_key(period: str, sha256: str) -> str:
    return f"{period}:{sha256[:16]}"


def detect_revisions(current: dict, previous: dict | None) -> list[dict]:
    """Compare captured values for periods present in both releases (same id)."""
    out = []
    for vid, prev in ((previous or {}).get("values") or {}).items():
        cur = (current.get("values") or {}).get(vid)
        if not cur or prev.get("kind") != "captured" or cur.get("kind") != "captured":
            continue
        a, b = prev.get("value"), cur.get("value")
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or a == b:
            continue
        pct = (b - a) / abs(a) * 100 if a else math.inf
        rev = {"id": vid, "period": cur.get("period"), "from": a, "to": b, "pct": round(pct, 4),
               "material": abs(pct) > REVISION_REPUBLISH_PCT, "previous_source": prev.get("source")}
        cur["revised"] = {"from": a, "pct": rev["pct"]}
        current["values"][f"{vid}.previous"] = value(f"{vid}.previous", a, unit=cur.get("unit"), period=cur.get("period"),
                                                     source=prev.get("source"), locator=prev.get("locator"), kind="previous_release")
        out.append(rev)
    return out


# ---------------------------------------------------------------------------------------------
# Triggers (deterministic)


def evaluate_triggers(package: dict, previous_live: dict | None, *, today: date, calendar: dict) -> dict:
    """Return the publication decision for one family run.

    decision: 'HOLD' (never publishes), 'PUBLISH' (replace live) or 'NO_CHANGE' (keep live).
    """
    holds: list[str] = []
    rec = package.get("reconciliation") or {}
    if rec.get("ok") is not True:
        holds.append("HOLD_RECONCILIATION:" + ",".join(rec.get("failures") or ["unknown"]))
    primary = package.get("primary_source") or {}
    if not HEX64.fullmatch(str(primary.get("sha256") or "")):
        holds.append("HOLD_MISSING_HASH")
    prev_period = (previous_live or {}).get("period")
    try:
        if prev_period and period_parts(package["period"]) < period_parts(prev_period):
            holds.append("HOLD_OLDER_PERIOD")
    except (KeyError, ValueError):
        holds.append("HOLD_INVALID_PERIOD")
    triggers: list[str] = []
    material_revisions = [r for r in package.get("revisions") or [] if r.get("material")]
    if not previous_live or previous_live.get("release_key") != package.get("release_key"):
        if not previous_live or prev_period != package.get("period"):
            triggers.append("new_period")
        elif material_revisions:
            triggers.append("revision")
        else:
            triggers.append("new_release_same_period")
    elif material_revisions:
        triggers.append("revision")
    crossed = [f for f in package.get("findings") or [] if f.get("crossed")]
    if crossed:
        triggers.append("threshold_crossed")
    late = late_release(package.get("published_at"), today=today, calendar=calendar)
    if late:
        triggers.append("late_release")
    publishing = {"new_period", "revision", "new_release_same_period"} & set(triggers)
    if late and previous_live and not (previous_live.get("late_release") or {}).get("days_late"):
        publishing = publishing | {"late_release"}
    decision = "HOLD" if holds else ("PUBLISH" if publishing else "NO_CHANGE")
    return {"decision": decision, "holds": holds, "triggers": triggers, "featured": bool(crossed),
            "late_release": late, "material_revisions": material_revisions}


def late_release(published_at: str | None, *, today: date, calendar: dict) -> dict | None:
    try:
        last = date.fromisoformat(str(published_at)[:10])
    except ValueError:
        return None
    expected = last + timedelta(days=int(calendar.get("expected_release_interval_days") or 31))
    days = (today - expected).days
    if days > int(calendar.get("late_tolerance_days") or 21):
        return {"expected_on": expected.isoformat(), "days_late": days}
    return None


# ---------------------------------------------------------------------------------------------
# Lectura Alicanto: verifier and budgeted generation


def _isapre_catalog(root: Path = ROOT) -> list[dict]:
    try:
        return json.loads((root / "data/entities/isapres.json").read_text(encoding="utf-8"))["entities"]
    except (OSError, ValueError, KeyError):
        return []


def _fold(text: str) -> str:
    return str(text or "").casefold().translate(str.maketrans("áéíóúü", "aeiouu"))


def isapres_mentioned(text: str, catalog: list[dict]) -> set[int]:
    folded = _fold(text)
    found = set()
    for e in catalog:
        names = {e.get("commercial_name"), *(e.get("aliases") or [])}
        for name in filter(None, names):
            n = _fold(name)
            if len(n) >= 4 and re.search(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", folded):
                found.add(int(e["official_code"]))
                break
    return found


def verify_lectura(text: str, package: dict, *, registry: dict | None = None, catalog: list[dict] | None = None) -> dict:
    cfg = (registry or load_registry())["lectura"]
    errors: list[str] = []
    text = str(text or "").strip()
    if not text:
        return {"verdict": "FAIL", "errors": ["empty"]}
    words = len(text.split())
    if words > int(cfg["max_words"]):
        errors.append(f"over_{cfg['max_words']}_words:{words}")
    for tok in text_numbers_trace(text, number_pool(package)):
        errors.append(f"number_not_in_evidence:{tok}")
    if not package.get("causal_note"):
        folded = _fold(text)
        for pat in cfg["causal_patterns"]:
            stem = pat.endswith("*")
            rx = r"(?<![a-z])" + re.escape(_fold(pat.rstrip("*"))) + ("" if stem else r"(?![a-z])")
            if re.search(rx, folded):
                errors.append(f"causal_without_note:{pat}")
    allowed = {int(c) for c in package.get("entity_codes") or []}
    for code in sorted(isapres_mentioned(text, catalog if catalog is not None else _isapre_catalog())):
        if code not in allowed:
            errors.append(f"isapre_not_in_package:{code}")
    if re.search(r"https?://", text):
        errors.append("url_in_lectura")
    if not any(a in _fold(text) for a in AUDIENCE):
        errors.append("business_lens_no_audience")
    return {"verdict": "PASS" if not errors else "FAIL", "errors": errors, "words": words}


def lectura_prompt(ficha: dict, package: dict) -> str:
    facts = " ".join(ficha.get("facts", {}).get("paragraphs") or [])
    tabs = [{"tema": t.get("label"), "lectura": t.get("text")} for t in ficha.get("tabs") or []]
    kpis = [{"kpi": k.get("label"), "valor": k.get("value"), "detalle": k.get("lines")} for k in ficha.get("kpis") or []]
    names = sorted({e.get("name") for e in package.get("entities") or [] if e.get("name")})
    return (
        "Escribe la 'Lectura Alicanto' de una ficha estadística de Alicanto Salud (inteligencia de negocios de salud en Chile). "
        "Es lo que convierte los datos en una decisión: el valor está en la implicancia, no en repetir cifras.\n"
        "Aplica a la vez cuatro miradas expertas:\n"
        "- Negocio de salud: qué significa para aseguradores, prestadores o inversionistas (ingresos, competencia, riesgo).\n"
        "- Analítica de datos: respeta denominadores y períodos; un stock no se suma; no confundas correlación con causa.\n"
        "- Editorial: directo, sin repetir el titular ni 'Qué muestran los datos', sin relleno.\n"
        "- UI/UX: dos o tres frases cortas que se lean en el celular de un vistazo.\n"
        "Reglas que se verifican de forma automática (si fallas, el texto se descarta):\n"
        "1. Máximo 80 palabras, en español de Chile, sin títulos ni viñetas.\n"
        "2. Solo puedes usar cifras que aparecen abajo, escritas igual (formato 1.234 y 12,3). Mejor si no usas cifras.\n"
        "3. No afirmes causas: no uses 'debido a', 'explica', 'provoca', 'gracias a', 'producto de', 'se debe'.\n"
        f"4. Solo puedes nombrar estas Isapres: {', '.join(names)}.\n"
        "5. Nombra al menos un actor afectado (Isapres, aseguradores, prestadores, inversionistas o cotizantes).\n"
        "6. No inventes hechos, fechas ni fuentes.\n"
        'Devuelve solo JSON: {"lectura": "..."}\n\n'
        f"Titular: {ficha.get('headline')}\nBajada: {ficha.get('dek')}\nQué muestran los datos: {facts}\n"
        f"Temas: {json.dumps(tabs, ensure_ascii=False)}\nKPI: {json.dumps(kpis, ensure_ascii=False)}\n"
    )


def _default_model_call(prompt: str, **kw):
    from . import openai_runtime as rt  # lazy: only live runs need the openai package
    return rt.call_json(prompt, **kw)


def _default_budget(worst_usd: float) -> tuple[bool, str]:
    """Shared AI budget machinery: run/month counters (ai_budget) and the paced monthly budget.

    The weekly cap is enforced again inside ``openai_runtime.call_json``.
    """
    try:
        from .ai_budget import allow_call, has_capacity
        from .ai_pricing import month_spend_usd, paced_budget_usd
        if not has_capacity("fast"):
            return False, "no_capacity"
        if month_spend_usd(ROOT) + worst_usd > paced_budget_usd():
            return False, "paced_budget_would_be_exceeded"
        return (True, "ok") if allow_call("fast") else (False, "budget_deferred")
    except Exception as exc:  # unreadable ledger blocks spend
        return False, f"budget_unreadable:{type(exc).__name__}"


def _record(success: bool) -> None:
    try:
        from .ai_budget import record_result
        record_result("fast", success)
    except Exception:
        pass


def _route_model(route: str) -> str:
    try:
        cfg = json.loads((ROOT / "config/model_routing_v1.json").read_text(encoding="utf-8"))
        return cfg["routes"][route]["model"]
    except (OSError, ValueError, KeyError):
        return "gpt-5.6-luna"


def generate_lectura(ficha: dict, package: dict, *, registry: dict | None = None, enabled: bool = True,
                     model_call: Callable[..., Any] | None = None,
                     budget: Callable[[float], tuple[bool, str]] | None = None,
                     catalog: list[dict] | None = None) -> dict:
    """One cheap call per ficha; any failure omits the block (the ficha still publishes)."""
    registry = registry or load_registry()
    cfg = registry["lectura"]
    if not enabled:
        return {"status": "not_attempted", "text": None, "cost_usd": 0.0}
    prompt = lectura_prompt(ficha, package)
    model = _route_model(cfg.get("route", "luna"))
    try:
        from .ai_pricing import estimate as price_estimate
        worst = price_estimate(model, math.ceil(len(prompt) / 3.2), int(cfg["max_output_tokens"]))
    except Exception:
        worst = float(cfg.get("max_run_usd", 0.05))
    if worst > float(cfg.get("max_run_usd", 0.05)):
        return {"status": "no_budget", "reason": "run_cap_would_be_exceeded", "text": None, "cost_usd": 0.0}
    ok, reason = (budget or _default_budget)(worst)
    if not ok:
        return {"status": "no_budget", "reason": reason, "text": None, "cost_usd": 0.0}
    try:
        result = (model_call or _default_model_call)(prompt, feature="stats_ficha_lectura", preferred_model=model,
                                                     allow_luna_fallback=False, max_output_tokens=int(cfg["max_output_tokens"]))
    except Exception as exc:
        _record(False)
        return {"status": "generation_error", "reason": f"{type(exc).__name__}:{exc}"[:200], "text": None,
                "cost_usd": float(getattr(exc, "estimated_cost_usd", 0) or 0)}
    output = getattr(result, "output", None) or {}
    text = str(output.get("lectura") or "").strip() if isinstance(output, dict) else ""
    cost = float(getattr(result, "estimated_cost_usd", 0) or 0)
    verification = verify_lectura(text, package, registry=registry, catalog=catalog)
    _record(verification["verdict"] == "PASS")
    base = {"model": getattr(result, "model", model), "response_id": getattr(result, "response_id", None),
            "cost_usd": round(cost, 6), "verification": verification}
    if verification["verdict"] != "PASS":
        return {**base, "status": "verifier_fail", "text": None, "rejected_text": text}
    return {**base, "status": "pass", "text": text}


# ---------------------------------------------------------------------------------------------
# Deterministic verification of the code-written ficha


def all_charts(ficha: dict) -> list[dict]:
    return [c for tab in ficha.get("tabs") or [] for c in tab.get("charts") or []] + list(ficha.get("charts") or [])


def displayed_texts(ficha: dict) -> list[str]:
    out = [ficha.get("headline"), ficha.get("dek")]
    for k in ficha.get("kpis") or []:
        out += [k.get("value"), *(k.get("lines") or []), k.get("badge")]
    out += list((ficha.get("facts") or {}).get("paragraphs") or [])
    for w in ficha.get("watch") or []:
        out += [w.get("headline"), w.get("explanation")]
    for tab in ficha.get("tabs") or []:
        out += [tab.get("label"), *(tab.get("text") or [])]
    for c in all_charts(ficha):
        out += [c.get("headline"), c.get("subtitle"), c.get("legend"), c.get("source")]
        for row in (c.get("table") or {}).get("rows") or []:
            out += [str(cell) for cell in row]
    out += [n.get("text") for n in ficha.get("notes") or []]
    lect = ficha.get("lectura") or {}
    if lect.get("status") == "pass":
        out.append(lect.get("text"))
    return [str(x) for x in out if x]


AUDIENCE = ("isapre", "asegurador", "prestador", "inversionista", "cotizante", "cartera", "ingreso", "competencia")


def _sentences(text: str) -> list[str]:
    return [_fold(x).strip(" .") for x in re.split(r"(?<=[.;])\s+", str(text or "")) if len(x.split()) >= 6]


def lens_checks(ficha: dict, package: dict) -> dict:
    """Four lenses (Dirección 28-oct 04:59) as deterministic checks; numbers already trace separately.

    - data: KPI refs exist in the package; share/ratio denominators are stated; stocks are labelled.
    - editorial: headline ≤ 140, dek ≤ 40 words, no sentence repeated across blocks.
    - ui: 3–5 KPIs, 2–6 tabs, ≤ 2 charts per tab, ≤ 12 rows per chart, every chart has a data table,
      subtitle and short labels.
    - business: 'Qué mirar' has 2–3 items with the next release; the Lectura (if any) names an audience.
    """
    values = package.get("values") or {}
    out = {"data": [], "editorial": [], "ui": [], "business": []}
    for k in ficha.get("kpis") or []:
        for ref in k.get("refs") or []:
            if ref not in values:
                out["data"].append(f"kpi_ref_missing:{k.get('id')}:{ref}")
    notes = " ".join(n.get("text", "") for n in ficha.get("notes") or []).casefold()
    if "denominador" not in notes:
        out["data"].append("denominator_not_stated")
    if "stock" not in notes:
        out["data"].append("stock_rule_not_stated")
    if len(str(ficha.get("headline") or "")) > 140:
        out["editorial"].append("headline_over_140")
    if len(str(ficha.get("dek") or "").split()) > 40:
        out["editorial"].append("dek_over_40_words")
    blocks = [ficha.get("dek"), *((ficha.get("facts") or {}).get("paragraphs") or []),
              *[x for tab in ficha.get("tabs") or [] for x in tab.get("text") or []],
              *[n.get("text") for n in ficha.get("notes") or []]]
    lect = ficha.get("lectura") or {}
    if lect.get("status") == "pass":
        blocks.append(lect.get("text"))
    seen: set[str] = set()
    for block in blocks:
        for sent in _sentences(block):
            if sent in seen:
                out["editorial"].append(f"repeated_sentence:{sent[:40]}")
            seen.add(sent)
    if not 3 <= len(ficha.get("kpis") or []) <= 5:
        out["ui"].append("kpis_out_of_range")
    tabs = ficha.get("tabs") or []
    if tabs and not 2 <= len(tabs) <= 6:
        out["ui"].append("tabs_out_of_range")
    for tab in tabs:
        if len(tab.get("charts") or []) > 2:
            out["ui"].append(f"tab_over_2_charts:{tab.get('id')}")
        if len(str(tab.get("label") or "")) > 24:
            out["ui"].append(f"tab_label_long:{tab.get('id')}")
        if not tab.get("charts") and not tab.get("text"):
            out["ui"].append(f"tab_empty:{tab.get('id')}")
    if len(all_charts(ficha)) < 2:
        out["ui"].append("charts_under_2")
    for c in all_charts(ficha):
        rows = c.get("rows") or []
        if not rows or len(rows) > 12:
            out["ui"].append(f"chart_rows_out_of_range:{c.get('id')}")
        if not (c.get("table") or {}).get("rows") or not c.get("subtitle"):
            out["ui"].append(f"chart_without_table_or_subtitle:{c.get('id')}")
        if any(len(str(r.get("label") or "")) > 18 for r in rows):
            out["ui"].append(f"chart_label_long:{c.get('id')}")
    watch = ficha.get("watch") or []
    if not 2 <= len(watch) <= 3:
        out["business"].append("watch_out_of_range")
    if lect.get("status") == "pass" and not any(a in _fold(lect.get("text")) for a in AUDIENCE):
        out["business"].append("lectura_without_audience")
    return out


def verify_ficha(ficha: dict, package: dict) -> dict:
    errors: list[str] = []
    for key in ("headline", "dek", "kpis", "facts", "sources"):
        if not ficha.get(key):
            errors.append(f"missing:{key}")
    pool = number_pool(package)
    for text in displayed_texts(ficha):
        for tok in text_numbers_trace(text, pool):
            errors.append(f"number_not_in_evidence:{tok}")
    values = package.get("values") or {}
    for chart in all_charts(ficha):
        for row in chart.get("rows") or []:
            for key, ref_key in (("value", "ref"), ("base", "base_ref")):
                ref = row.get(ref_key)
                if ref_key == "base_ref" and ref is None:
                    continue
                if ref not in values or values[ref]["value"] * row.get("sign", 1) != row.get(key):
                    errors.append(f"chart_row_not_in_evidence:{chart.get('id')}:{row.get('label')}")
    for src in ficha.get("sources") or []:
        if not str(src.get("url") or "").startswith("https://") or not HEX64.fullmatch(str(src.get("sha256") or "")):
            errors.append(f"source_without_hash:{src.get('label')}")
    lenses = lens_checks(ficha, package)
    for lens, errs in lenses.items():
        errors += [f"{lens}:{e}" for e in errs]
    return {"verdict": "PASS" if not errors else "FAIL", "errors": errors,
            "lenses": {k: ("PASS" if not v else "FAIL") for k, v in lenses.items()}}


# ---------------------------------------------------------------------------------------------
# Storage: one live ficha per family, archive and HOLD


def paths(root: Path, slug: str) -> dict:
    base = Path(root) / STORE
    return {"live": base / "live" / f"{slug}.json", "archive": base / "archive" / slug, "hold": base / "hold"}


def load_live(root: Path, slug: str) -> dict | None:
    try:
        return json.loads(paths(root, slug)["live"].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def publish(result: dict, root: Path) -> dict:
    """PASS replaces the live ficha (the previous one goes to the archive); HOLD never publishes."""
    slug = result["slug"]
    p = paths(root, slug)
    if result.get("status") == "pass" and result.get("ficha"):
        previous = load_live(root, slug)
        archived = None
        if previous and previous.get("release_key") != result["ficha"].get("release_key"):
            key = re.sub(r"[^0-9A-Za-z_-]+", "-", f"{previous.get('period')}-{previous.get('release_key', '')}")
            archived = p["archive"] / f"{key}.json"
            if not archived.exists():
                _write(archived, previous)
        _write(p["live"], result["ficha"])
        return {"published": True, "live": str(p["live"]), "archived": str(archived) if archived else None}
    if result.get("status") == "hold":
        out = p["hold"] / f"{slug}-{result.get('period') or 'unknown'}.json"
        _write(out, {k: result.get(k) for k in ("status", "family", "period", "generated_at", "decision",
                                                "verification", "errors", "candidate")})
        return {"published": False, "hold": str(out)}
    return {"published": False}


# ---------------------------------------------------------------------------------------------
# Web snapshot


PUBLIC_KEYS = ("schema_version", "id", "family", "family_label", "period", "published_at", "generated_at",
               "release_key", "featured", "triggers", "kicker", "kicker_meta", "headline", "headline_type", "dek",
               "dek_emphasis", "kpis", "tabs", "charts", "facts", "lectura", "watch", "notes", "sources", "machine_note",
               "status", "late_release", "revisions")


def live_fichas(root: Path = Path("."), registry: dict | None = None) -> list[dict]:
    registry = registry or load_registry()
    out = []
    for fam, cfg in registry["families"].items():
        if cfg.get("status") != "active":
            continue
        live = load_live(Path(root), cfg["slug"])
        if live and live.get("status") == "PASS" and live.get("family") == fam:
            out.append(live)
    return out


def public_ficha(ficha: dict) -> dict:
    pub = {k: deepcopy(ficha.get(k)) for k in PUBLIC_KEYS if k in ficha}
    lect = pub.get("lectura") or {}
    pub["lectura"] = {"status": lect.get("status"), "text": lect.get("text")} if lect.get("status") == "pass" and lect.get("text") else None
    return pub


def ficha_card(ficha: dict, cfg: dict) -> dict:
    from .editorial_committee import build_committee_artifact
    pub = public_ficha(ficha)
    card = {
        "piece_id": f"stats-ficha:{ficha['family']}:{ficha['period']}",
        "title": ficha["headline"], "display_title": ficha["headline"],
        "source_name": "Superintendencia de Salud", "source_type": "official",
        "source_url": cfg.get("release_page") or (ficha.get("sources") or [{}])[0].get("url"),
        "event_date": ficha["published_at"], "publication_date": ficha["published_at"],
        "validation_date": str(ficha.get("generated_at") or "")[:10] or None,
        "data_period": ficha["period"], "event_type": "DATA_PULSE", "category": "Datos sectoriales",
        "signal_types": ["Datos"], "scopes": ["Isapres"], "ingestion_mode": "BACKFILL", "distribution": "archive",
        "radar_score": 86 if ficha.get("featured") else 72, "confidence_score": 100,
        "what_happened": ficha["dek"], "card_what": ficha["dek"], "card_why_optional": True, "why_it_matters": "",
        "statistical_value_level": "stats_ficha", "feed_visibility": True, "editorial_decision": "accept",
        "publication_gate_reason": "stats_ficha_pass", "publication_ready_score": 100,
        "stats_ficha": pub,
        # Stable per-family share page with OG preview; it redirects to the current ficha.
        "share_url": f"data/fichas/{cfg['slug']}.html",
    }
    card["editorial_committee"] = build_committee_artifact(card)
    return card


def _stat_family(s: dict) -> str | None:
    if s.get("source_name") != "Superintendencia de Salud" or "Datos" not in (s.get("signal_types") or []):
        return None
    t = str(s.get("title") or "").lower()
    if "movilidad" in t:
        return "movilidad"
    if "cartera" in t and "regional" in t:
        return "cartera_regional"
    if "cartera" in t:
        return "cartera_total"
    if "suscripciones" in t or "desahucios" in t:
        return "suscripciones"
    return None


def apply_to_snapshot(cards: list[dict], fichas: list[dict], registry: dict | None = None) -> list[dict]:
    """One live ficha per family: add its card and drop the loose cards and pulses it supersedes."""
    registry = registry or load_registry()
    out = list(cards)
    for ficha in fichas:
        cfg = registry["families"][ficha["family"]]
        sup = cfg.get("supersedes") or {}
        prefixes = tuple(sup.get("event_titles_prefix") or ())
        fams = set(sup.get("stat_families") or ())
        out = [c for c in out if not ((prefixes and str(c.get("title") or "").startswith(prefixes) and c.get("event_type") == "DATA_PULSE")
                                      or (_stat_family(c) in fams) or str(c.get("piece_id") or "").startswith(f"stats-ficha:{ficha['family']}:"))]
        out.append(ficha_card(ficha, cfg))
    return out


SITE_URL = "https://cftorre1.github.io/Radar-salud/"
OG_IMAGE = SITE_URL + "assets/alicanto-logo-header.png"


def share_page(card: dict) -> str:
    """Static page for 'Compartir informe': OG title/description/image, then a redirect to the ficha."""
    import base64
    from html import escape
    ficha = card["stats_ficha"]
    target_id = "sig-" + (card.get("piece_id") or base64.b64encode(str(card.get("source_url")).encode()).decode())
    target = "../../index.html#" + target_id
    page_url = SITE_URL + card["share_url"]
    title = escape(f"{ficha['headline']} · Alicanto Salud", quote=True)
    desc = escape(ficha.get("dek") or "", quote=True)
    return (
        "<!doctype html>\n<html lang=\"es\"><head><meta charset=\"utf-8\"/>"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
        f"<title>{title}</title><meta name=\"description\" content=\"{desc}\"/>"
        f"<link rel=\"canonical\" href=\"{escape(page_url, quote=True)}\"/>"
        "<meta property=\"og:type\" content=\"article\"/><meta property=\"og:site_name\" content=\"Alicanto Salud\"/>"
        f"<meta property=\"og:title\" content=\"{title}\"/><meta property=\"og:description\" content=\"{desc}\"/>"
        f"<meta property=\"og:url\" content=\"{escape(page_url, quote=True)}\"/><meta property=\"og:image\" content=\"{OG_IMAGE}\"/>"
        "<meta name=\"twitter:card\" content=\"summary_large_image\"/>"
        f"<meta http-equiv=\"refresh\" content=\"0; url={escape(target, quote=True)}\"/>"
        "<style>body{margin:0;padding:24px 16px;background:#FAF9F5;color:#1D3345;font-family:Inter,ui-sans-serif,system-ui,sans-serif}"
        "h1{font:400 26px/1.2 Georgia,serif;max-width:28ch}a{color:#1D3345;text-decoration-color:#C37C37}</style></head><body>"
        f"<p>{escape(ficha.get('kicker') or '')}</p><h1>{escape(ficha['headline'])}</h1><p>{desc}</p>"
        f"<p><a href=\"{escape(target, quote=True)}\">Abrir la ficha en Alicanto Salud</a></p></body></html>\n")


def write_share_pages(cards: list[dict], web_data_dir: Path) -> list[str]:
    out = []
    for card in cards:
        if card.get("stats_ficha") and card.get("share_url"):
            path = Path(web_data_dir) / "fichas" / Path(card["share_url"]).name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(share_page(card), encoding="utf-8")
            out.append(str(path))
    return out


# ---------------------------------------------------------------------------------------------
# GES card (F4 interim): a finding is shown only when the corrected parser reconciled it


GES_PARSER = "ges_pinned_year_reconciled_v2"
GES_HOLD_REASON = "HOLD_GES_UNPINNED_OR_UNRECONCILED"


def ges_finding_valid(meta: dict | None) -> bool:
    meta = meta or {}
    return (meta.get("family") == "ges" and meta.get("status") == "validated" and meta.get("parser") == GES_PARSER
            and (meta.get("reconciliation") or {}).get("ok") is True)


def sanitize_ges_signal(signal: dict) -> dict:
    """Old GES findings (e.g. sheet 'Año 2005' → '21 presenta el mayor volumen…') go to HOLD."""
    meta = signal.get("data_insight_meta") or {}
    if meta.get("family") != "ges" or ges_finding_valid(meta):
        return signal
    if meta.get("status") == "HOLD" and not signal.get("data_insights"):
        return signal
    r = dict(signal)
    held = {"family": "ges", "status": "HOLD", "hold_reason": GES_HOLD_REASON, "parser": GES_PARSER,
            "superseded_meta": {**{k: v for k, v in meta.items() if k not in ("superseded_meta", "insights")},
                                "withdrawn_insights": len(meta.get("insights") or [])}}
    r["data_insights"] = []
    r["data_insight_meta"] = held
    r["statistical_view"] = {
        "family": "ges", "publication_status": "HOLD", "hold_reason": GES_HOLD_REASON,
        "limitations": ["La lectura automática de la planilla GES no fijó la hoja del año en curso ni concilió la suma "
                        "con el total declarado; el hallazgo queda retenido hasta la ficha GES (F4)."],
        "source_url": r.get("source_url")}
    return r


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
