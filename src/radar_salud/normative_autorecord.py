"""Automatic, verified V2.1 normative records (Dirección, 27-oct-2026).

Editorial control applied immediately and without human approval:
1. A strong model drafts the record ONLY from the regulator's official text
   captured as evidence (data/analysis_cache/normative_evidence).
2. Deterministic verification: the act identity heads the title once; subject
   and action terms appear in the title; every number/date in the record and
   every supporting quote appears literally in the official text.
3. A second, independent model checks the record against the text.
Repair loop (Dirección 9-nov-2026 20:35): a draft failing verification (or review) is re-prompted in the same
run with the exact problems and literal-only rules; acts stay eligible for up to 3 runs / 6 attempts, then
are final-rejected. Rejection history and detection→publication latency are kept per act in "acts".
Only records passing all three are written to
(data/analysis_cache/normative_auto_records.json, committed by the daily bot), read by the
exporter and the Reviewer next to the human config (human wins).
Budget: every call goes through openai_runtime (USD 10/month cap).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

AUTO_PATH = Path("data/analysis_cache/normative_auto_records.json")
EVIDENCE_DIR = Path("data/analysis_cache/normative_evidence")
# Acts started per run. Also bounded at run time by the paced budget: an act is started only when one worst-case
# run of it (cost_estimate()['act_worst_run_usd']) fits in budget_headroom_usd(). Dirección 9-nov-2026.
MAX_PER_RUN = 8
_TEXT_LIMIT = 24_000


def _norm(text: str) -> str:
    # Replace º before NFKC (NFKC turns "º" into "o"); accept "N.°".
    text = unicodedata.normalize("NFKC", str(text or "").replace("º", "°")).replace("N.°", "N°").replace("n.°", "n°")
    return re.sub(r"\s+", " ", text).strip().lower()


def _digits(label: str) -> str:
    return re.sub(r"\D", "", str(label or ""))


def _has_token(token: str, text: str) -> bool:
    return re.search(rf"(?<![\d.,]){re.escape(token)}(?![\d.,]*\d)", text) is not None


_MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre")
# Strong legal effects may only be stated when the official text uses them.
_STRONG = ("prohíbe", "prohibe", "sanciona", "multa", "deroga", "suspende", "revoca", "cancela", "exime",
           "deja sin efecto", "no exige")
# Obligated parties may only be named when the official text names them.
_ACTORS = ("isapre", "fonasa", "prestador", "clínica", "clinica", "hospital", "empleador", "mutualidad", "mutual",
           "compin", "aseguradora", "farmacia", "laboratorio", "médico", "medico", "dentista", "matrona",
           "trabajador", "beneficiario", "afiliado", "cotizante", "isl", "ccaf", "caja de compensación", "seremi",
           "establecimiento", "organismo administrador", "organismos administradores", "minsal", "superintendencia")
# Full dates and number+unit phrases are checked as one unit, literally in a quote.
_UNIT_RE = re.compile(r"\b\d{1,2} de (?:" + "|".join(("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                      "agosto", "septiembre", "octubre", "noviembre", "diciembre")) + r")(?: de \d{4})?\b"
                      r"|\b\d[\d.,]* (?:horas|días hábiles|dias habiles|días|dias|meses|años|anos|semanas|uf|%)")


def _stem(word: str) -> str:
    return _norm(word)[:6]


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d[\d.,/]*\d|\d", _norm(text)))


# Same identity rule as scripts/export_web_snapshot.py (_NORMATIVE_ID_RE/_normative_contract); a test guards drift.
# The exporter, and through it the reviewer's editorial gate, compares the record title with this canonical
# identity ("Circular N°3937"), not with the listing title ("Circular 3937", "Circular IF/N°541 - Emisión: 5/11/2026").
_IDENTITY_RE = re.compile(
    r"\b(Oficio\s+Circular|Ordinario\s+Circular|Circular\s+Interna|Resoluci[oó]n\s+Exenta|Resoluci[oó]n|"
    r"Decreto\s+Exento|Decreto|Dictamen|Oficio(?:\s+Ord(?:inario)?\.?)?|Circular)"
    r"\s+(?:SS\s+(?=I[FP]\b))?(?:(IF|IP|SS)\s*[/\-]?\s*)?(?:N\s*[°º]?\s*)?([\d\.]+)", re.I)
_IDENTITY_KINDS = {"oficio circular": "Oficio Circular", "ordinario circular": "Ordinario Circular",
                   "circular interna": "Circular Interna", "resolución exenta": "Resolución Exenta",
                   "resolucion exenta": "Resolución Exenta", "resolución": "Resolución", "resolucion": "Resolución",
                   "decreto exento": "Decreto Exento", "decreto": "Decreto", "dictamen": "Dictamen",
                   "circular": "Circular"}
_EMISION_RE = re.compile(r"\s*[-–]\s*Emisi[oó]n\s*:\s*\d{1,2}/\d{1,2}/\d{4}\s*$")


def canonical_identity(*texts: Any) -> str:
    """Canonical act identity, as the exporter derives it: the first text with a recognised act wins."""
    for text in texts:
        m = _IDENTITY_RE.search(str(text or ""))
        if m:
            kind = " ".join(m.group(1).split())
            kind = _IDENTITY_KINDS.get(kind.lower(), kind.rstrip("."))
            prefix = (m.group(2) or "").upper()
            return f"{kind} {prefix + '/' if prefix else ''}N°{m.group(3)}"
    for text in texts:
        if str(text or "").strip():
            return _EMISION_RE.sub("", str(text).strip())
    return ""


def _canonical_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Read-time fix for records written with a listing identity: rewrite only the identity prefix of the title."""
    old = str(rec.get("legal_identity") or "")
    new = canonical_identity(old)
    if not old or new == old:
        return rec
    rec = dict(rec, legal_identity=new, identity_from_listing=old)
    title = str(rec.get("plain_language_title") or "")
    if title.startswith(old) and not title[len(old):][:1].isalnum():  # «Circular 3937» ≠ «Circular 39370»
        rec["plain_language_title"] = new + title[len(old):]
    return rec


def load_auto_records(root: Path) -> dict[str, Any]:
    p = Path(root) / AUTO_PATH
    try:
        records = json.loads(p.read_text(encoding="utf-8")).get("source_records", {})
    except (OSError, ValueError):
        return {}
    return {url: _canonical_record(rec) if isinstance(rec, dict) else rec for url, rec in records.items()}


def merged_config(root: Path, human: dict[str, Any]) -> dict[str, Any]:
    """Human-reviewed records always win; verified auto records fill the gaps."""
    cfg = dict(human or {})
    numbered = {str(k) for k in (cfg.get("records") or {})}
    sources = {url: rec for url, rec in load_auto_records(root).items()
               if _digits(rec.get("legal_identity")) not in numbered}
    sources.update(cfg.get("source_records") or {})
    cfg["source_records"] = sources
    return cfg


def verify(record: dict[str, Any], label: str, evidence: str, official_subject: str = "") -> list[str]:
    problems = []
    title = str(record.get("plain_language_title") or "")
    context = str(record.get("normative_context") or "")
    nt, nc, ne = _norm(title), _norm(context), _norm(evidence)
    nl = _norm(label)
    # Whole identity only: «Circular IF/N°54» does not head «Circular IF/N°541 · …».
    if (not nt.startswith(nl) or nt[len(nl):][:1].isalnum()
            or len(re.findall(rf"(?<![^\W_]){re.escape(nl)}(?![^\W_])", nt)) != 1):
        problems.append("identity_must_head_title_once")
    subj, act = record.get("subject_terms"), record.get("action_terms")
    if not isinstance(subj, list) or not isinstance(act, list) or not all(
            isinstance(t, str) and len(t.strip()) >= 2 for t in [*(subj or []), *(act or [])]):
        problems.append("terms_must_be_lists_of_words")
        subj, act = [], []
    if not subj or not any(_norm(t) in nt for t in subj):
        problems.append("subject_term_missing_in_title")
    if not act or not any(_norm(t) in nt for t in act):
        problems.append("action_term_missing_in_title")
    ns = _norm(official_subject)
    for t in subj:
        if _stem(t) not in ne and _stem(t) not in ns:
            problems.append(f"subject_not_in_official_text:{t}")
    for t in act:
        if _stem(t) not in ne:
            problems.append(f"action_not_in_official_text:{t}")
    for verb in _STRONG:
        if verb in nt + " " + nc and verb[:6] not in ne:
            problems.append(f"strong_effect_not_in_text:{verb}")
    if not context or len(context) > 600 or nc in nt:
        problems.append("context_missing_or_redundant")
    quotes = [str(q) for q in record.get("evidence_quotes") or [] if str(q).strip()]
    if len(quotes) < 2:
        problems.append("needs_two_evidence_quotes")
    for q in quotes:
        if len(q.strip()) < 40 or len(q.split()) < 6:
            problems.append("quote_too_short")
        elif _norm(q) not in ne:
            problems.append("quote_not_literal")
    nq = " ".join(_norm(q) for q in quotes)
    for actor in _ACTORS:
        if re.search(rf"\b{re.escape(actor)}(?:es|s)?\b", nt + " " + nc) and not re.search(rf"\b{re.escape(actor)}(?:es|s)?\b", ne):
            problems.append(f"actor_not_in_official_text:{actor}")
    for unit in set(_UNIT_RE.findall(nt + " " + nc)):
        # Decision 7 (Dirección 11-nov-2026, Circular 3933): «6 meses corridos» in the record is backed by «6 meses
        # corridos» in a quote. A qualifier still never backs a bare figure («30 días» ≠ «30 días hábiles»).
        qual = {q for q in ("hábiles", "habiles", "corridos")
                if re.search(rf"(?<![\d.,]){re.escape(unit)} {q}\b", nt + " " + nc)}
        bare = re.search(rf"(?<![\d.,]){re.escape(unit)}(?! (?:h[aá]biles|habiles|corridos)\b)", nt + " " + nc)
        if qual and not bare and all(re.search(rf"(?<![\d.,]){re.escape(unit)} {q}\b", nq) for q in qual):
            continue  # every use of the figure carries its qualifier, and the quote says the same
        if not re.search(rf"(?<![\d.,]){re.escape(unit)}(?!\d| h[aá]biles| corridos| de \d{{4}})", nq) and not (
                re.search(r" de \d{4}$", unit) and re.search(rf"(?<![\d.,]){re.escape(unit)}", nq)):
            problems.append(f"date_or_quantity_not_literal_in_quote:{unit}")
    label_numbers = _numbers(label)
    for n in (_numbers(title) | _numbers(context)) - label_numbers:
        if not _has_token(n, ne):
            problems.append(f"number_not_in_official_text:{n}")
        elif not _has_token(n, nq):
            problems.append(f"number_not_backed_by_quote:{n}")
    for month in _MONTHS:
        if re.search(rf"\b{month}\b", nc):
            if not re.search(rf"\b{month}\b", ne):
                problems.append(f"month_not_in_official_text:{month}")
            elif not re.search(rf"\b{month}\b", nq):
                problems.append(f"month_not_backed_by_quote:{month}")
    return problems


_LITERAL_RULES = (
    "REGLAS ESTRICTAS:\n"
    "1. Copia cada cita de evidence_quotes LITERALMENTE del TEXTO OFICIAL, carácter por carácter (mínimo 6 palabras "
    "y 40 caracteres): sin resumir, sin unir frases, sin cambiar mayúsculas, puntuación, artículos ni números.\n"
    "2. Usa SOLO verbos, actores y cifras que aparecen literalmente en el TEXTO OFICIAL. subject_terms y action_terms "
    "deben ser palabras que estén en el texto oficial y en el título (p. ej. el verbo tal como lo usa el texto).\n"
    "3. Elimina toda afirmación que no puedas respaldar con una cita literal: cada cifra, fecha y mes del título o del "
    "contexto debe aparecer dentro de una de tus citas.\n"
    "4. Prefiere menos puntos, más cortos y literales, antes que completitud. normative_context no repite el título.\n")

_PROBLEM_HINTS = {
    "quote_not_literal": "una cita no aparece tal cual en el texto: cópiala exacta o quítala",
    "quote_too_short": "una cita tiene menos de 6 palabras o 40 caracteres: usa una oración completa literal",
    "needs_two_evidence_quotes": "se necesitan al menos 2 citas literales",
    "action_not_in_official_text": "ese verbo no está en el texto: usa un verbo que el texto use literalmente",
    "subject_not_in_official_text": "ese tema no está en el texto: usa palabras del texto o del asunto oficial",
    "actor_not_in_official_text": "ese actor no aparece en el texto: no lo nombres",
    "strong_effect_not_in_text": "ese efecto legal no está en el texto: no lo afirmes",
    "context_missing_or_redundant": "normative_context falta, supera 600 caracteres o repite el título",
    "number_not_in_official_text": "esa cifra no está en el texto: elimínala",
    "number_not_backed_by_quote": "esa cifra no está en tus citas: agrega la cita literal que la contiene o elimínala",
    "date_or_quantity_not_literal_in_quote": "esa fecha o cantidad debe aparecer igual (con año y unidad) en una cita",
    "month_not_in_official_text": "ese mes no está en el texto: elimínalo",
    "month_not_backed_by_quote": "ese mes no está en tus citas: agrega la cita o elimínalo",
    "identity_must_head_title_once": "el título debe empezar con la identidad del acto, una sola vez",
    "subject_term_missing_in_title": "algún subject_term debe aparecer en el título",
    "action_term_missing_in_title": "algún action_term debe aparecer en el título",
    "terms_must_be_lists_of_words": "subject_terms y action_terms deben ser listas de palabras",
    "independent_review": "el revisor independiente objetó la ficha: corrige exactamente lo que indica",
}


def _json_spec(label: str) -> str:
    return ("Responde SOLO JSON con: plain_language_title (empieza con "
            f"'{label} · ', luego tema y acción concreta en lenguaje simple, máx. 140 caracteres), subject_terms "
            "(1-3 palabras del tema presentes en el título), action_terms (1-3 verbos/efectos presentes en el título), "
            "normative_context (2-3 frases: qué cambia, a quién obliga y desde cuándo; cifras y fechas tal como en el "
            "texto), evidence_quotes (2-4 citas LITERALES del texto que respaldan el contexto).\n")


def _draft_prompt(label: str, issuer: str, subject: str, evidence: str) -> str:
    return (
        "Eres editor regulatorio de un servicio de inteligencia para ejecutivos de salud en Chile.\n"
        f"Acto: {label} · Emisor: {issuer}\nAsunto oficial: {subject}\n"
        "Usa SOLO el TEXTO OFICIAL. No inventes. " + _json_spec(label) + _LITERAL_RULES +
        f"TEXTO OFICIAL:\n{evidence[:_TEXT_LIMIT]}")


def _repair_prompt(label: str, issuer: str, subject: str, evidence: str, previous: dict[str, Any] | None,
                   problems: list[str]) -> str:
    """Stricter re-prompt (Dirección 9-nov 20:35): exact verifier problems + literal-only rules + official text."""
    lines = []
    for p in problems:
        hint = _PROBLEM_HINTS.get(p.split(":", 1)[0])
        lines.append(f"- {p}" + (f" → {hint}" if hint else ""))
    return (
        "Eres editor regulatorio de un servicio de inteligencia para ejecutivos de salud en Chile.\n"
        f"Acto: {label} · Emisor: {issuer}\nAsunto oficial: {subject}\n"
        "Tu borrador anterior FALLÓ la verificación automática contra el texto oficial. Rehazlo corrigiendo TODOS "
        "estos problemas (lista exacta del verificador):\n" + "\n".join(lines) + "\n" + _LITERAL_RULES +
        _json_spec(label) +
        "BORRADOR ANTERIOR (no lo copies si falla; corrígelo):\n" +
        json.dumps(previous or {}, ensure_ascii=False)[:4000] +
        f"\nTEXTO OFICIAL:\n{evidence[:_TEXT_LIMIT]}")


def _review_prompt(record: dict[str, Any], evidence: str) -> str:
    return ("Revisor independiente. ¿La ficha describe fielmente el TEXTO OFICIAL, sin agregar hechos, sin "
            "exagerar obligaciones y con fechas correctas? Responde SOLO JSON {\"verdict\":\"PASS\"|\"FAIL\","
            "\"reason\":\"...\"}.\nFICHA:\n" + json.dumps(record, ensure_ascii=False) +
            "\nTEXTO OFICIAL:\n" + evidence[:_TEXT_LIMIT])


# ---------------------------------------------------------------------------------------------------------------
# Cost, budget and latency (Dirección 9-nov-2026 20:35: stricter automatic retry, minimum detection→publication time)
# ---------------------------------------------------------------------------------------------------------------
LEDGER_PATH = Path("data/state/model_usage.json")
ROUTING_PATH = Path("config/model_routing_v1.json")
# Fallback per-call costs (USD, Terra) observed in the ledger 27-oct..9-nov-2026, used when the ledger has no rows.
_FALLBACK_DRAFT_USD = 0.0094
_FALLBACK_REVIEW_USD = 0.0052
_REPAIR_FACTOR = 1.35  # a repair prompt adds the previous draft and the problem list to the draft prompt


def _ledger_rows(root: Path) -> list[dict[str, Any]]:
    try:
        return json.loads((Path(root) / LEDGER_PATH).read_text(encoding="utf-8")).get("calls") or []
    except (OSError, ValueError):
        return []


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def cost_estimate(root: Path) -> dict[str, float]:
    """USD per call and per act, from the ledger's normative_autorecord rows (fallbacks when absent)."""
    rows = _ledger_rows(root)
    by = {f: [float(r.get("estimated_cost_usd") or 0) for r in rows if r.get("feature") == f]
          for f in (DRAFT_FEATURE, REPAIR_FEATURE, REVIEW_FEATURE)}
    draft = _mean(by[DRAFT_FEATURE]) or _FALLBACK_DRAFT_USD
    repair = _mean(by[REPAIR_FEATURE]) or draft * _REPAIR_FACTOR
    review = _mean(by[REVIEW_FEATURE]) or _FALLBACK_REVIEW_USD
    return {
        "draft_usd": round(draft, 6), "repair_usd": round(repair, 6), "review_usd": round(review, 6),
        # first draft passes verification and review
        "act_pass_first_usd": round(draft + review, 6),
        # one run where every attempt reaches the reviewer (upper bound of one act in one run)
        "act_worst_run_usd": round(draft + (MAX_ATTEMPTS_PER_RUN - 1) * repair + MAX_ATTEMPTS_PER_RUN * review, 6),
        # every attempt the caps allow, all reaching the reviewer (absolute upper bound per act)
        "act_worst_total_usd": round(draft + (MAX_ATTEMPTS_PER_ACT - 1) * repair + MAX_ATTEMPTS_PER_ACT * review, 6),
    }


def _weekly_spend(root: Path, now: datetime) -> float:
    cutoff = now - timedelta(days=7)
    total = 0.0
    for row in _ledger_rows(root):
        try:
            at = datetime.fromisoformat(str(row.get("at")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if at >= cutoff:
            total += float(row.get("estimated_cost_usd") or 0)
    return total


def budget_headroom_usd(root: Path, now: datetime | None = None) -> float:
    """Spend still allowed now: min(paced monthly budget − month spend, weekly guard − rolling 7-day spend).

    Same limits openai_runtime enforces (USD 10/month paced, weekly guard from config); read-only, never changes them."""
    from .ai_pricing import month_spend_usd, paced_budget_usd
    now = now or datetime.now(timezone.utc)
    try:
        cfg = json.loads((Path(root) / ROUTING_PATH).read_text(encoding="utf-8"))
        weekly = float(cfg.get("weekly_budget_usd") or cfg.get("cost_policy", {}).get(
            "hard_application_guard_usd_rolling_7d", 10))
    except (OSError, ValueError):
        weekly = 10.0
    return min(paced_budget_usd(now) - month_spend_usd(root, now), weekly - _weekly_spend(root, now))


def _parse_ts(value: Any) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def latency_summary(store: dict[str, Any]) -> dict[str, Any]:
    """Detection→publication latency (hours) over acts with both timestamps."""
    hours = []
    for act in (store.get("acts") or {}).values():
        a, b = _parse_ts(act.get("detected_at")), _parse_ts(act.get("published_at"))
        if a and b:
            hours.append(max(0.0, (b - a).total_seconds() / 3600))
    hours.sort()
    median = None
    if hours:
        mid = len(hours) // 2
        median = hours[mid] if len(hours) % 2 else (hours[mid - 1] + hours[mid]) / 2
    acts = (store.get("acts") or {}).values()
    return {"published_with_latency": len(hours),
            "latency_hours_median": round(median, 2) if median is not None else None,
            "latency_hours_max": round(max(hours), 2) if hours else None,
            "pending_retry": sum(a.get("status") == "rejected" for a in acts),
            "pending_review": sum(a.get("status") == "pending_review" for a in acts),
            "final_rejected": sum(a.get("status") == "final_rejected" for a in acts)}


# ---------------------------------------------------------------------------------------------------------------
DRAFT_FEATURE = "normative_autorecord"
REPAIR_FEATURE = "normative_autorecord_repair"
REVIEW_FEATURE = "normative_autorecord_review"
MAX_ATTEMPTS_PER_RUN = 3   # first draft + up to 2 repairs in the same run
MAX_RUNS_PER_ACT = 3       # after 3 runs (or 6 drafting attempts) without PASS the act is final-rejected
MAX_ATTEMPTS_PER_ACT = 6


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_parse_failure(exc: Exception) -> bool:
    """Billed but unusable output (counted as an attempt). Budget/provider failures stop the run instead."""
    msg = str(exc)
    if "pricing" in msg or "budget" in msg:
        return False
    return isinstance(exc, ValueError) or bool(re.match(r"model_call_failed:(JSONDecodeError|ValueError)", msg))


class _StopRun(Exception):
    pass


def _model_call(call: Callable[..., Any], prompt: str, feature: str) -> tuple[Any, float | None, str | None]:
    """Returns (output, cost, parse_problem). Raises _StopRun on budget/provider failure (not counted)."""
    try:
        res = call(prompt, feature=feature, preferred_model="gpt-5.6-terra", allow_luna_fallback=False)
    except (ValueError, RuntimeError) as exc:
        if not _is_parse_failure(exc):
            print("normative_autorecord deferred:", type(exc).__name__, str(exc)[:60])
            raise _StopRun from exc
        return None, None, f"unparseable_model_output:{str(exc)[:80]}"
    except Exception as exc:  # budget exhausted or model failure: stop, keep what was done
        print("normative_autorecord deferred:", type(exc).__name__)
        raise _StopRun from exc
    cost = getattr(res, "estimated_cost_usd", None)
    return getattr(res, "output", None), (float(cost) if isinstance(cost, (int, float)) else None), None


def build_auto_records(root: Path, signals: list[dict[str, Any]], *, call: Callable[..., Any] | None = None,
                       today: date | None = None, max_new: int = MAX_PER_RUN, run_id: str | None = None,
                       headroom: Callable[[], float] | None = None) -> list[str]:
    """Draft + verify (+ repair) + review records for recent general acts that lack one.

    Newest acts first. Each act gets up to MAX_ATTEMPTS_PER_RUN drafting attempts per run (first draft, then
    repairs fed with the verifier's exact problems), at most MAX_RUNS_PER_ACT runs or MAX_ATTEMPTS_PER_ACT
    attempts overall; then it is final-rejected with its reasons (re-opened only if the official text changes).
    The budget headroom is checked before every model call; a run starts an act only if one worst-case run of it
    is affordable."""
    from .normative_evidence import _key, _document_url
    from .normative_minimal import act_scope
    if call is None:
        from .openai_runtime import call_json as call
    root = Path(root)
    today = today or date.today()
    run_id = str(run_id or os.getenv("GITHUB_RUN_ID") or f"local-{_now().isoformat()}")
    if headroom is None:
        headroom = lambda: budget_headroom_usd(root)  # noqa: E731
    human = json.loads((root / "config/normative_editorial_v2.json").read_text(encoding="utf-8"))
    existing = merged_config(root, human)["source_records"]
    p = root / AUTO_PATH
    try:
        store = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        store = {"version": 1, "source_records": {}, "rejected": {}}
    store.setdefault("source_records", {})
    store.setdefault("rejected", {})
    acts = store.setdefault("acts", {})
    est = cost_estimate(root)
    written: list[str] = []
    numbered = {str(k) for k in (human.get("records") or {})}

    candidates = []
    for s in signals:
        url = str(s.get("source_url") or "")
        # Canonical identity, exactly as the exporter and the editorial gate derive it: the listing title's
        # "- Emisión: dd/mm/yyyy" is dropped (#155) and "Circular 3937" becomes "Circular N°3937".
        label = canonical_identity(s.get("source_title_full") or s.get("title"), s.get("normative_document_label"))
        if not url or _digits(label) in numbered:
            continue  # human records (by number) always win
        if "Normativa" not in (s.get("signal_types") or []):
            continue
        try:
            if today - date.fromisoformat(str(s.get("event_date"))[:10]) > timedelta(days=45):
                continue
        except ValueError:
            continue
        if act_scope(s, label) != "general":
            continue
        candidates.append((s, url, label))
    # Latency (Dirección 9-nov): newest acts first, then most recently detected.
    candidates.sort(key=lambda c: (str(c[0].get("event_date") or "")[:10], str(c[0].get("detected_at") or "")),
                    reverse=True)

    started = 0
    try:
        for s, url, label in candidates:
            act = acts.get(url)
            if act is None:
                act = acts[url] = {"legal_identity": label, "detected_at": s.get("detected_at"), "evidence_at": None,
                                   "first_attempt_at": None, "published_at": None, "runs": [], "attempts": 0,
                                   "status": "pending", "attempt_log": [], "rejection_history": []}
                old = store["rejected"].get(url)
                if old:  # rejections from before the retry policy stay in the history
                    act["rejection_history"].append({k: v for k, v in old.items() if k != "last_draft"})
                    act["status"] = "rejected"
            if not act.get("detected_at"):
                act["detected_at"] = s.get("detected_at")
            if url in existing:
                auto = store["source_records"].get(url)
                if auto and not act.get("published_at"):
                    act["published_at"] = auto.get("verified_at")
                    act["status"] = "published"
                continue  # already has a (human or auto) record
            doc, _kind = _document_url(s)
            ev_path = root / EVIDENCE_DIR / f"{_key(doc)}.json" if doc else None
            if not ev_path or not ev_path.exists():
                continue
            try:
                ev = json.loads(ev_path.read_text(encoding="utf-8"))
                evidence = str(ev.get("text") or "")
            except (OSError, ValueError, AttributeError):
                continue
            if len(evidence) < 200:
                continue
            act["evidence_at"] = act.get("evidence_at") or ev.get("fetched_at")
            evidence_hash = hashlib.sha256(evidence.encode("utf-8")).hexdigest()
            rejected = store["rejected"].get(url) or {}
            if act.get("status") == "final_rejected":
                if rejected.get("evidence_sha256") == evidence_hash:
                    continue  # final: re-opened only when the official text changes
                act.update(status="rejected", runs=[], attempts=0)  # new official text: fresh counters
                rejected = {}
            if act.get("last_run_id") == run_id:
                continue  # already worked in this run
            pending = act.get("pending_review")
            if pending and (pending.get("evidence_sha256") != evidence_hash or
                            verify(pending.get("record") or {}, label, evidence, str(s.get("official_subject") or ""))):
                act.pop("pending_review", None)  # stale: the official text or the verifier changed
                pending = None
            if not pending and (len(act["runs"]) >= MAX_RUNS_PER_ACT or
                                int(act.get("attempts") or 0) >= MAX_ATTEMPTS_PER_ACT):
                _finalize(store, act, url, rejected, evidence_hash)
                continue
            if started >= max_new:
                break
            if headroom() < (est["review_usd"] if pending else est["act_worst_run_usd"]):
                print("normative_autorecord deferred: budget headroom below one act run")
                break
            started += 1
            act["last_run_id"] = run_id
            subject = str(s.get("official_subject") or "")
            issuer = str(s.get("source_name"))
            previous, problems = rejected.get("last_draft"), list(rejected.get("problems") or [])
            if rejected.get("evidence_sha256") not in (None, evidence_hash):
                previous, problems = None, []  # official text changed: start from a fresh draft
            stop = published = failed_this_run = False
            record: dict[str, Any] = {}
            run_attempts = 0

            def count_failure() -> None:
                act["attempts"] = int(act.get("attempts") or 0) + 1
                if run_id not in act["runs"]:
                    act["runs"].append(run_id)

            def review(rec: dict[str, Any]) -> list[str] | None:
                """Independent review. None = deferred for budget/provider (the verified draft stays pending)."""
                if headroom() < est["review_usd"]:
                    print("normative_autorecord deferred: budget headroom before review")
                    return None
                rat = _now().isoformat()
                try:
                    out, rcost, rparse = _model_call(call, _review_prompt(rec, evidence), REVIEW_FEATURE)
                except _StopRun:
                    return None
                verdict = str(out.get("verdict") if isinstance(out, dict) else "").upper()
                probs = ([rparse] if rparse else [] if verdict == "PASS" else
                         ["independent_review:" + str(out.get("reason") if isinstance(out, dict) else None)[:200]])
                act["attempt_log"].append({"at": rat, "run_id": run_id, "attempt": act.get("attempts"),
                                           "kind": REVIEW_FEATURE, "cost_usd": rcost, "problems": probs})
                return probs

            if pending:  # verified draft whose review was deferred: only the review runs again
                record = dict(pending["record"])
                probs = review(record)
                if probs is None:
                    stop = True
                elif not probs:
                    act.pop("pending_review", None)
                    published = True
                else:
                    act.pop("pending_review", None)
                    count_failure()
                    failed_this_run = True
                    previous, problems = record, probs
            while not (stop or published) and run_attempts < MAX_ATTEMPTS_PER_RUN and \
                    int(act.get("attempts") or 0) < MAX_ATTEMPTS_PER_ACT:
                repair = bool(problems)
                feature = REPAIR_FEATURE if repair else DRAFT_FEATURE
                if headroom() < est["repair_usd" if repair else "draft_usd"] + est["review_usd"]:
                    print("normative_autorecord deferred: budget headroom before attempt")
                    stop = True
                    break
                prompt = (_repair_prompt(label, issuer, subject, evidence, previous, problems) if repair
                          else _draft_prompt(label, issuer, subject, evidence))
                at = _now().isoformat()
                try:
                    output, cost, parse_problem = _model_call(call, prompt, feature)
                except _StopRun:
                    stop = True
                    break
                run_attempts += 1
                act["first_attempt_at"] = act.get("first_attempt_at") or at
                record = {}
                if parse_problem:
                    new_problems = [parse_problem]
                else:
                    try:
                        record = dict(output)
                        new_problems = verify(record, label, evidence, subject)
                    except (TypeError, ValueError, AttributeError) as exc:
                        record, new_problems = {}, [f"unparseable_draft:{type(exc).__name__}"]
                log = {"at": at, "run_id": run_id, "attempt": int(act.get("attempts") or 0) + 1, "kind": feature,
                       "cost_usd": cost, "problems": new_problems}
                act["attempt_log"].append(log)
                if not new_problems:
                    probs = review(record)
                    if probs is None:
                        # Verified draft, review deferred: not a failed attempt; next run re-runs only the review.
                        act["pending_review"] = {"record": record, "evidence_sha256": evidence_hash, "at": at}
                        log["pending_review"] = True
                        stop = True
                        break
                    new_problems = probs
                if not new_problems:
                    published = True
                    break
                count_failure()
                failed_this_run = True
                previous, problems = (record or previous), new_problems
            if published:
                now = _now().isoformat()
                store["rejected"].pop(url, None)  # history stays in acts[url]["rejection_history"]
                store["source_records"][url] = {
                    "legal_identity": label,
                    "plain_language_title": record["plain_language_title"].strip(),
                    "subject_terms": record["subject_terms"], "action_terms": record["action_terms"],
                    "normative_context": record["normative_context"].strip(),
                    "evidence_quotes": record["evidence_quotes"],
                    "evidence_sha256": evidence_hash,
                    "origin": "auto_verified", "verified_at": now,
                    "attempts": int(act.get("attempts") or 0) + 1, "runs": len(set(act["runs"]) | {run_id}),
                }
                act.update(status="published", published_at=now)
                written.append(url)
            elif act.get("pending_review"):
                act["status"] = "pending_review"
            elif failed_this_run:
                entry = {"problems": problems, "evidence_sha256": evidence_hash, "at": _now().isoformat(),
                         "run_id": run_id, "attempts": act["attempts"], "runs": len(act["runs"]),
                         "last_draft": previous}
                store["rejected"][url] = entry
                act["rejection_history"].append({k: v for k, v in entry.items() if k != "last_draft"})
                act["status"] = "rejected"
                if len(act["runs"]) >= MAX_RUNS_PER_ACT or act["attempts"] >= MAX_ATTEMPTS_PER_ACT:
                    _finalize(store, act, url, entry, evidence_hash)
            if stop:
                break
    finally:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    return written


def _finalize(store: dict[str, Any], act: dict[str, Any], url: str, rejected: dict[str, Any], evidence_hash: str):
    entry = dict(rejected or {})
    entry.update(final=True, final_at=entry.get("final_at") or _now().isoformat(), evidence_sha256=evidence_hash,
                 problems=entry.get("problems") or ["attempt_cap_reached"])
    store["rejected"][url] = entry
    if act.get("status") != "final_rejected":
        act["status"] = "final_rejected"
        act["rejection_history"].append({"final": True, "at": entry["final_at"], "problems": entry["problems"],
                                         "attempts": act.get("attempts"), "runs": len(act.get("runs") or [])})


def run_step(root: Path, signals: list[dict[str, Any]], *, capture: Callable[..., list[str]] | None = None,
             **kwargs: Any) -> dict[str, Any]:
    """Capture missing official text (same run as detection) then build records; returns the run summary."""
    root = Path(root)
    ordered = sorted(signals, key=lambda s: (str(s.get("event_date") or "")[:10], str(s.get("detected_at") or "")),
                     reverse=True)
    captured: list[str] = []
    try:
        if capture is None:
            from .normative_evidence import capture_missing as capture
        captured = capture(root, ordered)
    except Exception as exc:  # evidence is best-effort, never blocks the records
        print("normative_evidence skipped:", type(exc).__name__)
    p = root / AUTO_PATH
    before = len(_ledger_rows(root))
    written = build_auto_records(root, ordered, **kwargs)
    try:
        store = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        store = {}
    run_rows = [r for r in _ledger_rows(root)[before:] if str(r.get("feature", "")).startswith("normative_autorecord")]
    return {"evidence_captured": len(captured), "records_written": len(written),
            "run_calls": len(run_rows), "run_cost_usd": round(sum(float(r.get("estimated_cost_usd") or 0)
                                                                   for r in run_rows), 6),
            **latency_summary(store), "cost_estimate": cost_estimate(root)}


def format_summary(summary: dict[str, Any]) -> str:
    est = summary.get("cost_estimate") or {}
    return "\n".join([
        "### Normativa: fichas automáticas verificadas",
        f"- Evidencia capturada: {summary.get('evidence_captured')} · fichas publicadas: {summary.get('records_written')}",
        f"- Llamadas IA en este run: {summary.get('run_calls')} · costo USD {summary.get('run_cost_usd')}",
        f"- Latencia detección→publicación (h): mediana {summary.get('latency_hours_median')} · "
        f"máx {summary.get('latency_hours_max')} (n={summary.get('published_with_latency')})",
        f"- En reintento: {summary.get('pending_retry')} · rechazo final: {summary.get('final_rejected')}",
        f"- Costo estimado por acto USD: pasa al primer intento {est.get('act_pass_first_usd')} · "
        f"peor run {est.get('act_worst_run_usd')} · peor total {est.get('act_worst_total_usd')}",
    ])
