"""Automatic, verified V2.1 normative records (Dirección, 27-oct-2026).

Editorial control applied immediately and without human approval:
1. A strong model drafts the record ONLY from the regulator's official text
   captured as evidence (data/analysis_cache/normative_evidence).
2. Deterministic verification: the act identity heads the title once; subject
   and action terms appear in the title; every number/date in the record and
   every supporting quote appears literally in the official text.
3. A second, independent model checks the record against the text.
Only records passing all three are written to
(data/analysis_cache/normative_auto_records.json, committed by the daily bot), read by the
exporter and the Reviewer next to the human config (human wins).
Budget: every call goes through openai_runtime (USD 10/month cap).
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

AUTO_PATH = Path("data/analysis_cache/normative_auto_records.json")
EVIDENCE_DIR = Path("data/analysis_cache/normative_evidence")
MAX_PER_RUN = 6
_TEXT_LIMIT = 24_000


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).replace("º", "°")
    return re.sub(r"\s+", " ", text).strip().lower()


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d[\d.,/]*\d|\d", _norm(text)))


def load_auto_records(root: Path) -> dict[str, Any]:
    p = Path(root) / AUTO_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("source_records", {})
    except (OSError, ValueError):
        return {}


def merged_config(root: Path, human: dict[str, Any]) -> dict[str, Any]:
    """Human-reviewed records always win; verified auto records fill the gaps."""
    cfg = dict(human or {})
    sources = dict(load_auto_records(root))
    sources.update(cfg.get("source_records") or {})
    cfg["source_records"] = sources
    return cfg


def verify(record: dict[str, Any], label: str, evidence: str) -> list[str]:
    problems = []
    title = str(record.get("plain_language_title") or "")
    context = str(record.get("normative_context") or "")
    nt, ne = _norm(title), _norm(evidence)
    if not nt.startswith(_norm(label)) or nt.count(_norm(label)) != 1:
        problems.append("identity_must_head_title_once")
    subj = [t for t in record.get("subject_terms") or [] if str(t).strip()]
    act = [t for t in record.get("action_terms") or [] if str(t).strip()]
    if not subj or not any(_norm(t) in nt for t in subj):
        problems.append("subject_term_missing_in_title")
    if not act or not any(_norm(t) in nt for t in act):
        problems.append("action_term_missing_in_title")
    if not context or len(context) > 600 or _norm(context) in nt:
        problems.append("context_missing_or_redundant")
    label_numbers = _numbers(label)
    for n in (_numbers(title) | _numbers(context)) - label_numbers:
        if n not in ne:
            problems.append(f"number_not_in_official_text:{n}")
    quotes = [q for q in record.get("evidence_quotes") or [] if str(q).strip()]
    if len(quotes) < 2:
        problems.append("needs_two_evidence_quotes")
    for q in quotes:
        if _norm(q) not in ne:
            problems.append("quote_not_literal")
    return problems


def _draft_prompt(label: str, issuer: str, subject: str, evidence: str) -> str:
    return (
        "Eres editor regulatorio de un servicio de inteligencia para ejecutivos de salud en Chile.\n"
        f"Acto: {label} · Emisor: {issuer}\nAsunto oficial: {subject}\n"
        "Usa SOLO el TEXTO OFICIAL. No inventes. Responde SOLO JSON con: plain_language_title (empieza con "
        f"'{label} · ', luego tema y acción concreta en lenguaje simple, máx. 140 caracteres), subject_terms "
        "(1-3 palabras del tema presentes en el título), action_terms (1-3 verbos/efectos presentes en el título), "
        "normative_context (2-3 frases: qué cambia, a quién obliga y desde cuándo; cifras y fechas tal como en el "
        "texto), evidence_quotes (2-4 citas LITERALES del texto que respaldan el contexto).\n"
        f"TEXTO OFICIAL:\n{evidence[:_TEXT_LIMIT]}")


def _review_prompt(record: dict[str, Any], evidence: str) -> str:
    return ("Revisor independiente. ¿La ficha describe fielmente el TEXTO OFICIAL, sin agregar hechos, sin "
            "exagerar obligaciones y con fechas correctas? Responde SOLO JSON {\"verdict\":\"PASS\"|\"FAIL\","
            "\"reason\":\"...\"}.\nFICHA:\n" + json.dumps(record, ensure_ascii=False) +
            "\nTEXTO OFICIAL:\n" + evidence[:_TEXT_LIMIT])


def build_auto_records(root: Path, signals: list[dict[str, Any]], *, call: Callable[..., Any] | None = None,
                       today: date | None = None, max_new: int = MAX_PER_RUN) -> list[str]:
    """Draft + verify + review records for recent general acts that lack one."""
    from .normative_evidence import _key, _document_url
    from .normative_minimal import act_scope
    if call is None:
        from .openai_runtime import call_json as call
    root = Path(root)
    today = today or date.today()
    human = json.loads((root / "config/normative_editorial_v2.json").read_text(encoding="utf-8"))
    existing = merged_config(root, human)["source_records"]
    p = root / AUTO_PATH
    try:
        store = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        store = {"version": 1, "source_records": {}, "rejected": {}}
    written: list[str] = []
    for s in signals:
        if len(written) >= max_new:
            break
        url = str(s.get("source_url") or "")
        label = str(s.get("normative_document_label") or s.get("title") or "")
        if not url or url in existing or url in store.get("rejected", {}):
            continue
        if "Normativa" not in (s.get("signal_types") or []):
            continue
        try:
            if today - date.fromisoformat(str(s.get("event_date"))[:10]) > timedelta(days=45):
                continue
        except ValueError:
            continue
        if act_scope(s, label) != "general":
            continue
        doc, _kind = _document_url(s)
        ev_path = root / EVIDENCE_DIR / f"{_key(doc)}.json" if doc else None
        if not ev_path or not ev_path.exists():
            continue
        evidence = json.loads(ev_path.read_text(encoding="utf-8"))["text"]
        subject = str(s.get("official_subject") or "")
        try:
            draft = call(_draft_prompt(label, str(s.get("source_name")), subject, evidence),
                         feature="normative_autorecord", preferred_model="gpt-5.6-terra")
            record = dict(draft.output)
        except Exception as exc:  # budget exhausted or model failure: try next run
            print("normative_autorecord deferred:", type(exc).__name__)
            break
        problems = verify(record, label, evidence)
        if not problems:
            try:
                review = call(_review_prompt(record, evidence), feature="normative_autorecord_review",
                              preferred_model="gpt-5.6-luna", allow_luna_fallback=False).output
                if str(review.get("verdict")).upper() != "PASS":
                    problems.append("independent_review:" + str(review.get("reason"))[:200])
            except Exception as exc:
                print("normative_autorecord review deferred:", type(exc).__name__)
                break
        if problems:
            store.setdefault("rejected", {})[url] = {"problems": problems, "at": datetime.now(timezone.utc).isoformat()}
            continue
        store.setdefault("source_records", {})[url] = {
            "legal_identity": label,
            "plain_language_title": record["plain_language_title"].strip(),
            "subject_terms": record["subject_terms"], "action_terms": record["action_terms"],
            "normative_context": record["normative_context"].strip(),
            "evidence_quotes": record["evidence_quotes"],
            "evidence_sha256": hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
            "origin": "auto_verified", "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        written.append(url)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    return written
