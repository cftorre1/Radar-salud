"""«El informe dice que…» for Congreso committee reports (Dirección 13-nov-2026, AI authorised within USD 10/month).

When a Congreso card is a committee report (trámite «… informe de comisión …»), the Senate's open data
(<informes><informe><FECHAINFORME>, <TRAMITE>, <LINK_INFORME>) points to the report PDF on tramitacion.senado.cl, a
public official document. One model call per report drafts one or two sentences of what the report says, from the
PDF text only; it is published only if:

1. deterministic checks pass: 2+ literal quotes (≥ 6 words) found in the PDF; every number in the sentence appears in
   the PDF; no strong legal effect absent from the text; 8–45 words, no line breaks;
2. an independent second call confirms it is faithful.

Results are cached per report (data/analysis_cache/congreso_informes/<boletin>_<fecha>.json, committed by the daily bot), so a report
is paid once. A report whose link is not published yet is retried on later runs; a failed or errored draft is final. Budget: every call goes through openai_runtime (weekly + paced monthly cap).
"""
from __future__ import annotations

import hashlib
import io
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .normative_autorecord import _STRONG, _has_token, _norm, _numbers

CACHE_DIR = Path("data/analysis_cache/congreso_informes")  # committed by the daily bot (paid outputs persist)
WS = "https://tramitacion.senado.cl/wspublico/tramitacion.php?boletin={n}"
DOC_HOST = "tramitacion.senado.cl"
DRAFT_FEATURE = "congreso_informe"
REVIEW_FEATURE = "congreso_informe_review"
MAX_PER_RUN = 4
WINDOW_DAYS = 30
_TEXT_HEAD, _TEXT_TAIL = 9_000, 13_000  # the mandate and the agreements/votes usually sit at the start and the end
_PDF_MAX_BYTES = 12 * 1024 * 1024


def _iso(ddmmyyyy: str) -> str | None:
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", str(ddmmyyyy or ""))
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def doc_url(link: str) -> str | None:
    """The Senate links reports on www.senado.cl (behind a browser challenge); the same document is served openly by
    tramitacion.senado.cl. Only the iddocto/tipodoc of an informe is kept."""
    from urllib.parse import urlsplit
    host = (urlsplit(str(link or "").strip()).hostname or "").lower()
    m = re.search(r"iddocto=(\d+)", str(link or ""))
    if not m or not (host == "senado.cl" or host.endswith(".senado.cl")):
        return None
    return f"https://{DOC_HOST}/appsenado/index.php?mo=tramitacion&ac=getDocto&iddocto={m.group(1)}&tipodoc=info"


def parse_informes(xml_bytes: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    out = []
    for node in root.iter("informe"):
        get = lambda tag: (node.findtext(tag) or "").strip()  # noqa: E731
        out.append({"date": _iso(get("FECHAINFORME")), "tramite": re.sub(r"\s+", " ", get("TRAMITE")),
                    "etapa": get("ETAPA"), "url": doc_url(get("LINK_INFORME"))})
    return out


def _fold(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", _norm(s).translate(str.maketrans("áéíóúüñ", "aeiouun")))


def match_informe(informes: list[dict[str, Any]], day: str, tramite: str) -> dict[str, Any] | None:
    """The one linked report of the card's day whose whole trámite (committee included) equals the card's. Two
    different documents for the same day and trámite are ambiguous: nothing is attached (review of #205)."""
    want = " ".join(_fold(tramite).split())
    if not want:
        return None
    hits = [i for i in informes if i.get("url") and i.get("date") == day and " ".join(_fold(i.get("tramite")).split()) == want]
    return hits[0] if len({i["url"] for i in hits}) == 1 else None


def is_report(row: dict[str, Any]) -> bool:
    return bool(row.get("bill_boletin")) and row.get("bill_milestone") == "informe_comision"


def official_tramite(row: dict[str, Any]) -> str:
    for f in row.get("key_facts") or []:
        if str(f).startswith("Trámite oficial: «"):
            return str(f).split("«", 1)[1].rsplit("»", 1)[0]
    m = re.search(r"Trámite oficial: «(.*?)»", str(row.get("what_happened") or ""))
    return m.group(1).rstrip(". ") if m else ""


def cache_key(boletin: str, day: str, tramite: str) -> str:
    """One file per report: bill, day and the committee's trámite (two committees the same day are two reports)."""
    tag = hashlib.sha1(" ".join(_fold(tramite).split()).encode("utf-8")).hexdigest()[:10]
    return f"{re.sub(r'[^0-9-]', '', str(boletin))}_{day}_{tag}"


def load_summary(root: Path, boletin: str, day: str, tramite: str) -> dict[str, Any] | None:
    try:
        rec = json.loads((Path(root) / CACHE_DIR / f"{cache_key(boletin, day, tramite)}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    s = rec.get("summary") or {}
    same = " ".join(_fold(rec.get("card_tramite")).split()) == " ".join(_fold(tramite).split())
    return rec if same and s.get("status") == "pass" and str(s.get("dice") or "").strip() else None


def fact(rec: dict[str, Any] | None) -> str | None:
    """«El informe dice que …» (the sentence always ends with a period)."""
    if not rec:
        return None
    dice = str((rec.get("summary") or {}).get("dice") or "").strip().rstrip(".")
    if not dice:
        return None
    first, _, rest = dice.partition(" ")
    if first in _LOWER_FIRST:  # «La comisión…» → «la comisión…»; never «FONASA», «Hacienda», «Comisión de Salud»
        dice = first.lower() + (" " + rest if rest else "")
    return f"El informe dice que {dice}."


_LOWER_FIRST = {"La", "El", "Los", "Las", "Se", "Un", "Una", "En", "Con", "Por", "Tras", "Al", "Ambas", "Ambos"}


# ------------------------------------------------------------------------------------------------------------------
# Draft + verify + review
# ------------------------------------------------------------------------------------------------------------------

def verify(draft: dict[str, Any], text: str) -> list[str]:
    problems = []
    dice = str(draft.get("dice") or "").strip()
    words = len(dice.split())
    if not dice or "\n" in dice or not 8 <= words <= 45:
        problems.append("dice_length")
    norm_text = _norm(text)
    quotes = [q for q in (draft.get("quotes") or []) if isinstance(q, str)]
    if len(quotes) < 2:
        problems.append("needs_two_quotes")
    for q in quotes:
        if len(q.split()) < 6:
            problems.append("quote_too_short")
        elif _norm(q) not in norm_text:
            problems.append("quote_not_literal")
    text_numbers = _numbers(text)
    for n in sorted(_numbers(dice)):
        if n not in text_numbers:
            problems.append(f"number_not_in_report:{n}")
    low = _norm(dice)
    for verb in _STRONG:
        if _has_token(verb, low) and not _has_token(verb, norm_text):
            problems.append(f"strong_effect_not_in_report:{verb}")
    if re.search(r"(?i)\b(creemos|consideramos|alicanto|debería|debiera|probablemente|posiblemente)\b", dice):
        problems.append("opinion_or_guess")
    return sorted(set(problems))


def _excerpt(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    return text if len(text) <= _TEXT_HEAD + _TEXT_TAIL else text[:_TEXT_HEAD] + "\n[…]\n" + text[-_TEXT_TAIL:]


def draft_prompt(title: str, tramite: str, text: str) -> str:
    return ("Eres editor legislativo de un servicio de inteligencia para ejecutivos de salud en Chile.\n"
            f"Proyecto: {title}\nTrámite: {tramite}\n"
            "Lee el INFORME DE COMISIÓN y responde SOLO JSON {\"dice\": \"...\", \"quotes\": [\"...\", \"...\"]}.\n"
            "- dice: 1 o 2 frases (máx. 45 palabras) que completen «El informe dice que …»: qué acordó o propone la "
            "comisión (aprobado en general o en particular, votación, cambios o indicaciones principales). Sin "
            "opiniones, sin predecir, sin repetir el título del proyecto. Cifras y votaciones tal como en el texto.\n"
            "- quotes: 2 a 3 citas LITERALES del informe (mínimo 6 palabras cada una), copiadas carácter por carácter, "
            "que respalden lo que dices.\n"
            "Usa SOLO el texto del informe. No inventes.\nINFORME:\n" + _excerpt(text))


def review_prompt(draft: dict[str, Any], text: str) -> str:
    return ("Revisor independiente. ¿La frase describe fielmente el INFORME, sin agregar hechos, sin exagerar y con "
            "cifras y votaciones correctas? Responde SOLO JSON {\"verdict\":\"PASS\"|\"FAIL\",\"reason\":\"...\"}.\n"
            "FRASE: El informe dice que " + str(draft.get("dice") or "") + "\nINFORME:\n" + _excerpt(text))


def summarize(text: str, title: str, tramite: str, call: Callable[..., Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "fail", "cost_usd": 0.0}
    res = call(draft_prompt(title, tramite, text), feature=DRAFT_FEATURE, preferred_model="gpt-5.6-terra",
               allow_luna_fallback=False)
    out["cost_usd"] += float(getattr(res, "estimated_cost_usd", 0) or 0)
    draft = getattr(res, "output", None)
    if not isinstance(draft, dict):
        out["problems"] = ["unparseable_draft"]
        return out
    problems = verify(draft, text)
    out["draft"] = draft
    if problems:
        out["problems"] = problems
        return out
    rev = call(review_prompt(draft, text), feature=REVIEW_FEATURE, preferred_model="gpt-5.6-terra",
               allow_luna_fallback=False)
    out["cost_usd"] += float(getattr(rev, "estimated_cost_usd", 0) or 0)
    verdict = getattr(rev, "output", None) or {}
    if str(verdict.get("verdict") or "").upper() != "PASS":
        out["problems"] = [f"independent_review:{str(verdict.get('reason') or '')[:160]}"]
        return out
    out.update(status="pass", dice=str(draft["dice"]).strip(), quotes=draft.get("quotes"))
    return out


# ------------------------------------------------------------------------------------------------------------------
# Run step (online export only; offline exports and tests never fetch nor call a model)
# ------------------------------------------------------------------------------------------------------------------

def _doc_kind(data: bytes) -> str:
    head = data[:8]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "docx"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "doc"
    if data[:5].lstrip().startswith(b"{\\rtf"):
        return "rtf"
    if b"<html" in data[:2048].lower() or b"<!doctype" in data[:2048].lower():
        return "html"
    return "unknown:" + head.hex()


def _pdf_text(data: bytes) -> str:
    """Text of the report. The Senate serves «getDocto» as PDF or as Word; an HTML page or a legacy .doc is reported
    (18-nov: a non-PDF body raised PdfStreamError and the summary never ran)."""
    kind = _doc_kind(data)
    if kind == "pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    if kind == "docx":
        import zipfile
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        xml = re.sub(r"</w:p>", "\n", xml)
        return html.unescape(re.sub(r"<[^>]+>", "", xml))
    raise ValueError(f"unsupported_report_format:{kind}")


def refresh(root: Path, signals: list[dict[str, Any]], *, today: date, fetch: Callable[..., bytes] | None = None,
            call: Callable[..., Any] | None = None, max_new: int = MAX_PER_RUN,
            robots: Callable[[str], bool] | None = None) -> dict[str, int]:
    """Draft summaries for recent report cards that lack one. Returns counters for the run log."""
    root = Path(root)
    stats = {"candidates": 0, "no_link_yet": 0, "written": 0, "failed": 0, "errors": 0}
    reasons: list[str] = []
    if fetch is None:
        from .official_open import fetch as _fetch

        def fetch(url, accept):
            return _fetch(url, (DOC_HOST,), timeout=60, max_bytes=_PDF_MAX_BYTES, accept=accept)[0]
    if call is None:
        from .openai_runtime import call_json as call
    if robots is None:
        from .official_open import RobotsGate, fetch as _robots_fetch
        gate = RobotsGate(lambda url: _robots_fetch(url, (DOC_HOST,), accept="text/plain"))
        robots = lambda url: gate.allowed(url)  # noqa: E731
    done = 0
    for s in signals:
        if done >= max_new:
            break
        if not is_report(s):
            continue
        day = str(s.get("event_date") or "")[:10]
        try:
            if (today - date.fromisoformat(day)).days > WINDOW_DAYS:
                continue
        except ValueError:
            continue
        boletin = str(s.get("bill_boletin"))
        tramite = official_tramite(s)
        path = root / CACHE_DIR / f"{cache_key(boletin, day, tramite)}.json"
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rec = {"boletin": boletin, "date": day, "card_tramite": tramite}
        if (rec.get("summary") or {}).get("status") in ("pass", "fail"):
            continue  # paid once per PDF (a changed PDF re-opens below)
        stats["candidates"] += 1
        try:
            ws = WS.format(n=boletin.split("-")[0])
            if not robots(ws):
                stats["errors"] += 1
                reasons.append(f"{boletin}:robots_ws")
                continue
            xml = fetch(ws, "application/xml")
            inf = match_informe(parse_informes(xml if isinstance(xml, bytes) else str(xml).encode("utf-8")), day,
                                tramite)
            if not inf:
                stats["no_link_yet"] += 1
                reasons.append(f"{boletin}:no_link_yet")
                continue
            if not robots(inf["url"]):
                stats["errors"] += 1
                reasons.append(f"{boletin}:robots_pdf")
                continue
            pdf = fetch(inf["url"], "application/pdf")
            pdf = pdf if isinstance(pdf, bytes) else str(pdf).encode("latin-1", "ignore")
            sha = hashlib.sha256(pdf).hexdigest()
            text = _pdf_text(pdf)
            if len(text) < 800:
                rec.update(url=inf["url"], sha256=sha, summary={"status": "fail", "problems": ["no_text_layer"]})
            else:
                done += 1  # every paid attempt counts toward the run cap, even if it errors (review of #205)
                try:
                    summary = summarize(text, str(s.get("bill_title") or s.get("title") or ""), inf["tramite"], call)
                except RuntimeError as exc:
                    if "budget" in str(exc):
                        raise
                    # A provider/parse error after a billed call is final for this report: never paid twice.
                    summary = {"status": "fail", "problems": [f"model_error:{str(exc)[:160]}"]}
                summary["at"] = datetime.now(timezone.utc).isoformat()
                rec.update(url=inf["url"], sha256=sha, chars=len(text), tramite=inf["tramite"], summary=summary)
                stats["written" if summary["status"] == "pass" else "failed"] += 1
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        except RuntimeError as exc:  # budget exhausted or provider failure: stop, nothing is published
            stats["errors"] += 1
            reasons.append(f"{boletin}:{type(exc).__name__}:{str(exc)[:80]}")
            if "budget" in str(exc):
                break
        except Exception as exc:  # noqa: BLE001 - one bad report never stops the export
            stats["errors"] += 1
            reasons.append(f"{boletin}:{type(exc).__name__}:{str(exc)[:80]}")
    if stats["candidates"]:
        # Actions logs are not readable from the agent environment: the last run's counters stay next to the cache.
        try:
            (root / CACHE_DIR).mkdir(parents=True, exist_ok=True)
            (root / CACHE_DIR / "_last_run.json").write_text(json.dumps(
                {"day": today.isoformat(), **stats, "reasons": reasons[:20]}, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
        except OSError:
            pass
    return stats
