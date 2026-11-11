"""Normativa section, phase 1 (Dirección, 10–11-nov-2026): a standing repository of SIS and SUSESO norms.

Unlike Al día, nothing leaves by age: every norm that Al día publishes as Normativa enters ``data/normativa/registry.json``
and stays there. Effective dates come ONLY from the literal text captured from the norm (``validity_text``); when that text
gives no date, the norm is still listed, marked «Vigencia no informada en la fuente · en revisión», and goes to the manual
review of Dirección (``data/normativa/review.json``). Suspensions and repeals are never inferred: they enter only through
that review file, with the act that orders them and a literal quote.

Groups (computed by the page against the reader's date, so they move without a rebuild): próximos 30 días, más de 30 días,
vigentes últimos 30 días, vigentes histórico, sin fecha, implementadas (a per-reader mark), suspendidas, derogadas o sin
efecto. Topics come from a keyword rule on the official subject (``TOPIC_RULES``), to be validated by the editorial board.

Nothing here calls a model or the network.
"""
from __future__ import annotations

import base64
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

SCHEMA = "normativa_v1"
REGISTRY = Path("data/normativa/registry.json")
REVIEW = Path("data/normativa/review.json")

MONTHS = {m: i for i, m in enumerate(("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                      "septiembre", "octubre", "noviembre", "diciembre"), 1)}
_M = "|".join(MONTHS)
_DAY_DATE = re.compile(rf"\b(\d{{1,2}})\s*[°º]?\s+de\s+({_M})\s+(?:de|del)\s+(\d{{4}})\b", re.I)
_MONTH_DATE = re.compile(rf"\bmes\s+de\s+({_M})\s+(?:de|del)\s+(\d{{4}})\b", re.I)
# «desde su publicación», «a contar de su notificación», «desde la fecha de su publ icació n en el Diario Oficial»…
_ON_PUBLICATION = re.compile(r"\b(?:desde|a\s+contar\s+de|a\s+partir\s+de)\s+(?:la\s+fecha\s+de\s+)?(?:su|la)\s+"
                             r"(?:publ\s*i\s*caci\s*[oó]\s*n|notificaci[oó]n)", re.I)
_NOTIFICATION = re.compile(r"\bnotificaci[oó]n\b", re.I)
_DIARIO_OFICIAL = re.compile(r"\bDiario\s+Ofi", re.I)
# Not a statement of entry into force («Inicio operativo informado: …» is a paraphrase of an operational start).
_NOT_VALIDITY = re.compile(r"^\s*Inicio\s+operativo", re.I)
# An exception («salvo …») or a text cut mid-sentence: the date is shown with «con excepciones / texto incompleto».
_EXCEPTION = re.compile(r"\bsalvo\b|\bexcepto\b|\bcon\s+excepci[oó]n", re.I)
# A capture cut mid-sentence (ends on a connector or a clipped word: «…cuya», «…Diario Ofi»).
_CUT = re.compile(r"\b(?:cuy[oa]s?|que|de|del|la|el|y|en|los|las|con|a|por|para|Ofi)\s*$", re.I)
# A relative term («6 meses corridos contados desde su publicación») is not a literal date: it goes to review.
_RELATIVE = re.compile(r"\b\d+\s+(?:d[ií]as|meses|años)\b.*\bcontad[oa]s\b", re.I)
_TARGET = re.compile(r"\b(Circular|Resoluci[oó]n Exenta|Oficio Circular|Oficio)\s+(IF|IP|SS)?\s*/?\s*N\s*[°º]?\s*([\d\.]+)\s+"
                     r"(?:difiri[oó]|posterg[oó]|aplaz[oó])\s+su\s+entrada\s+en\s+vigencia", re.I)

TOPIC_RULES: list[tuple[str, re.Pattern]] = [
    ("Licencias médicas y SIL", re.compile(r"licencia|\bSIL\b|subsidio por incapacidad|COMPIN", re.I)),
    ("Seguridad laboral (Ley 16.744)", re.compile(r"16\.744|riesgos|accidente|incidentes peligrosos|asistencia t[eé]cnica|"
                                                  r"buceo|calificaci[oó]n de patolog|enfermedades profesionales", re.I)),
    ("Cajas, bienestar y beneficios", re.compile(r"C\.C\.A\.F|\bCCAF\b|cr[eé]dito social|\bcajas?\b|bienestar|\bbono\b|"
                                                 r"subsidio al empleo|desafiliaci[oó]n|remuneraciones", re.I)),
    ("Prestadores", re.compile(r"prestador|acreditaci[oó]n", re.I)),
    # Editorial review 11-nov: Isapre operation and debt (bonos, reembolsos, compensaciones, Ley 21.674 plans) is not
    # «planes, GES y CAEC».
    ("Isapres: operación y deuda", re.compile(r"\bbonos?\b|reembols|compens|\bdeuda|MAS20\d\d|21\.674|Ley de Isapres", re.I)),
]
TOPIC_SIS_DEFAULT = "Isapres: planes, GES y CAEC"
TOPIC_OTHER = "Otros"


def issuer(source_name: Any) -> str | None:
    s = str(source_name or "")
    if "SUSESO" in s or "Seguridad Social" in s:
        return "SUSESO"
    if "Superintendencia de Salud" in s or s.strip() in ("SIS", "Superintendencia de Salud"):
        return "SIS"
    return None


def topic(subject: str, emisor: str | None) -> str:
    for name, rx in TOPIC_RULES:
        if rx.search(subject or ""):
            return name
    return TOPIC_SIS_DEFAULT if emisor == "SIS" else TOPIC_OTHER


_SP = r"\s*"
# «notificación»/«publicación» also in the OCR-spaced form of the captured PDFs («not ificació n», «publ icació n»).
_NOTIF_W = _SP.join("notificaci") + r"\s*[oó]\s*n"
_PUBL_W = _SP.join("publicaci") + r"\s*[oó]\s*n"
_ON_EVENT = re.compile(r"\b(?:desde|a\s+contar\s+de|a\s+partir\s+de)\s+(?:la\s+fecha\s+de\s+)?(?:su\s+|la\s+)?(?:fecha\s+de\s+)?(?:su\s+)?"
                       rf"({_PUBL_W}|{_NOTIF_W})", re.I)
_ON_THIS_DATE = re.compile(r"\b(?:desde|a\s+contar\s+de|a\s+partir\s+de)\s+esta\s+fecha\b", re.I)
# A date counts as the entry into force only right after one of these cues (review of #180, 11-nov-2026).
_CUE = re.compile(r"(?:entra(?:n|r[aá]n?)?\s+en\s+vigencia|vigencia|comenzar[aá]n?\s+a\s+regir|comienzan?\s+a\s+regir|"
                  r"rigen?|regir[aá]n?|a\s+partir\s+del?|a\s+contar\s+del?|desde\s+el|desde|difiri[oó]\s+su\s+entrada\s+en\s+vigencia\s+hasta)"
                  r"(?:\s+(?:el|del|día))*\s*$", re.I)
# Never an entry into force: deadlines, expiries, sending duties, operational starts.
_BAD = re.compile(r"(?:hasta(?!.*\bentrada\s+en\s+vigencia)|deber[aá]n?\b|remitir|enviar|informar|plazo|vence|Inicio\s+operativo|"
                  r"se\s+mantiene|prórroga)[^.;]*$", re.I)


def _as_date(y: str, month: str, d: str = "1") -> date | None:
    try:
        return date(int(y), MONTHS[month.lower()], int(d))
    except (ValueError, KeyError):
        return None  # «31 de febrero»: not a date, the norm goes to review


def parse_validity(text: Any) -> dict:
    """Literal effective date from the captured validity text. kind: date | on_publication | on_notification |
    on_publication_do | on_emission | none.

    Review of #180 (11-nov-2026): a date counts only right after an entry-into-force cue («entra en vigencia el»,
    «comenzarán a regir a partir del», «rige desde el», «a contar del mes de»), or when the whole text is the date.
    Deadlines («deberán remitir … hasta»), expiries, «Inicio operativo» and emission dates never count. When the text
    says «desde su publicación/notificación», that is the rule even if other dates appear (then ``partial``).
    ``target`` names another norm whose entry into force the act refers to («La Circular IF/N° 532 difirió su entrada
    en vigencia hasta el 1 de enero de 2027»)."""
    t = " ".join(str(text or "").split())
    out = {"kind": "none", "eff": None, "prec": None, "target": None}
    if not t or _NOT_VALIDITY.search(t):
        return out
    if _EXCEPTION.search(t) or _CUT.search(t):
        out["partial"] = True
    tm = _TARGET.search(t)
    if tm:
        out["target"] = f"{tm.group(1).replace('Resolucion', 'Resolución')} {tm.group(2).upper() + '/' if tm.group(2) else ''}N°{tm.group(3)}"
    if _RELATIVE.search(t):
        return out  # «6 meses contados desde su publicación»: a term, not a literal date
    ev = _ON_EVENT.search(t)
    others = bool(_DAY_DATE.search(t) or _MONTH_DATE.search(t))
    if ev:
        kind = ("on_notification" if re.fullmatch(_NOTIF_W, ev.group(1), re.I)
                else "on_publication_do" if _DIARIO_OFICIAL.search(t) else "on_publication")
        return {**out, "kind": kind, **({"partial": True} if others else {})}
    if _ON_THIS_DATE.search(t):
        return {**out, "kind": "on_emission", **({"partial": True} if others else {})}
    if _RELATIVE.search(t):
        return out
    bare = _DAY_DATE.fullmatch(t.rstrip(". "))
    for m in _DAY_DATE.finditer(t):
        before = t[:m.start()]
        deferred = re.search(r"entrada\s+en\s+vigencia\s+hasta(?:\s+el)?\s*$", before, re.I)  # «difirió su entrada en vigencia hasta el …»
        if deferred or ((bare or _CUE.search(before[-60:])) and not _BAD.search(before[-80:])):
            d = _as_date(m.group(3), m.group(2), m.group(1))
            if d:
                # Several dates with their own cue («Capítulo I desde …, Capítulo II desde …»): the first, marked partial.
                if len({x.group(0) for x in _DAY_DATE.finditer(t)}) > 1 and not deferred:
                    out["partial"] = True
                return {**out, "kind": "date", "eff": d.isoformat(), "prec": "day"}
    for m in _MONTH_DATE.finditer(t):
        before = t[:m.start()]
        if _CUE.search(before[-60:] + " desde") or re.search(r"a\s+contar\s+del\s*$", before[-20:], re.I):
            d = _as_date(m.group(2), m.group(1))
            if d:
                return {**out, "kind": "date", "eff": d.isoformat(), "prec": "month"}
    return out


def signal_id(s: dict) -> str:
    """Same id as Al día's ``idFor`` (web/app.js): piece_id, else base64(utf-8 of url|event_date|event_type)."""
    if s.get("piece_id"):
        return str(s["piece_id"])
    raw = f"{s.get('source_url') or ''}|{s.get('event_date') or ''}|{s.get('event_type') or 'OTHER'}"
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def _subject(s: dict, label: str) -> str:
    title = str(s.get("display_title") or (s.get("normative_editorial") or {}).get("plain_language_title") or s.get("title") or "")
    title = re.sub(rf"^\s*{re.escape(label)}\s*[·:\-–]\s*", "", title).strip()
    return title or label


def _key(label: str, emisor: str | None) -> str:
    # «IF/N°10.670» and «IF/N° 10670» are the same norm: the number loses dots and spaces.
    label = re.sub(r"(\d)[.\s](?=\d)", r"\1", re.sub(r"N\s*[°º]\s*", "N°", label))
    base = unicodedata.normalize("NFKD", f"{emisor or 'x'}-{label}").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


def record_from_signal(s: dict) -> dict | None:
    """A registry record from one Al día Normativa signal, or None when it is not an identified SIS/SUSESO norm."""
    label = str(s.get("normative_document_label") or "").strip()
    kind = str(s.get("normative_document_type") or "").strip()
    if not kind:  # e.g. «Dictamen O-02-S-03153-2026»: the label starts with its type
        kind = next((k for k in ("Resolución Exenta", "Oficio Circular", "Circular", "Resolución", "Dictamen", "Oficio", "Decreto")
                     if label.startswith(k + " ")), "")
    emisor = issuer(s.get("source_name"))
    if not (label and kind and emisor):
        return None
    return {"id": _key(label, emisor), "label": label, "type": kind, "emisor": emisor,
            "date": s.get("emission_date") or s.get("issued_on") or s.get("event_date"),
            "subject": _subject(s, label), "url": s.get("source_url"), "validity": s.get("validity_text") or None,
            "related": [str(x) for x in (s.get("related_reference_ids") or []) if isinstance(x, str)][:6],
            "signal_id": signal_id(s), "signal_event_date": s.get("event_date"),
            # The public Al día card as published, so «Ver ficha» still opens it after it leaves the 90-day feed.
            "card": s}


def publishable(s: dict) -> bool:
    """Same gates as Al día's individualCardAllowed for a norm: visible, not on committee HOLD/REJECT, identified."""
    verdict = str((s.get("editorial_committee") or {}).get("verdict") or "PASS").upper()
    return (s.get("feed_visibility") is not False and verdict not in ("HOLD", "REJECT")
            and bool((s.get("display_title") or s.get("title")) and s.get("normative_document_label") and s.get("source_url")))


def update_registry(registry: dict, signals: list[dict], today: date) -> dict:
    """Upsert today's Normativa signals; never drop a record by age (no 90-day logic).

    A record changes only when its captured fields change (no daily churn). A norm that Al día stops showing (HOLD,
    REJECT, hidden) is marked ``withheld`` and leaves the public index until it is publishable again (review of #180)."""
    items = dict(registry.get("items") or {})
    for s in signals:
        if s.get("event_type") != "REGULATION" and "Normativa" not in (s.get("signal_types") or []):
            continue
        rec = record_from_signal(s)
        if not rec:
            continue
        prev = items.get(rec["id"])
        if not publishable(s):
            if prev and not prev.get("withheld"):
                items[rec["id"]] = {**prev, "withheld": True}
            continue
        rec["first_seen"] = (prev or {}).get("first_seen") or today.isoformat()
        if not rec["validity"] and (prev or {}).get("validity"):
            rec["validity"] = prev["validity"]  # a later capture without the text never erases what was literal
        if prev != rec:
            items[rec["id"]] = rec
    return {"schema": SCHEMA, "items": dict(sorted(items.items()))}


def _review_entry(r: Any) -> dict | None:
    """Dirección's manual decisions. kind: date (eff + literal quote) | nofija | susp | sinef (by + literal quote)."""
    if not isinstance(r, dict) or r.get("kind") not in ("date", "nofija", "susp", "sinef", "retirada"):
        return None
    if r["kind"] == "date" and not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("eff") or "")) and len(str(r.get("quote") or "")) >= 12):
        return None
    if r["kind"] in ("susp", "sinef") and not (len(str(r.get("by") or "")) >= 4 and len(str(r.get("quote") or "")) >= 12):
        return None
    if not r.get("on"):
        return None
    return {k: r[k] for k in ("kind", "eff", "quote", "by", "on", "decided_by") if r.get(k)}


def build(registry: dict, review: dict, feed_ids: set[str], generated_at: str | None = None) -> dict:
    """The public index (web/data/normativa.json). ``feed_ids`` are the Al día ids live today: «Ver ficha» opens the
    Al día ficha only while the norm is still there."""
    decisions = (review or {}).get("decisions") or {}
    out = []
    for rec in (registry.get("items") or {}).values():
        v = parse_validity(rec.get("validity"))
        rv = _review_entry(decisions.get(rec["id"]))
        if rec.get("withheld") or (rv or {}).get("kind") == "retirada":
            continue  # not public: withheld by Al día's gates or withdrawn by Dirección
        item = {k: rec.get(k) for k in ("id", "label", "type", "emisor", "date", "subject", "url", "validity", "related", "signal_id")}
        item.update(v, tema=topic(rec.get("subject") or "", rec.get("emisor")))
        if rv:
            item["review"] = rv
        # «Ver ficha» always opens the Al día ficha: from the live feed, or from normativa_cards.json once it left it.
        item["ficha"] = f"index.html?abrir=1&desde=normativa&n={rec['id']}#sig-{rec['signal_id']}" if rec.get("signal_id") else None
        item["in_feed"] = rec.get("signal_id") in feed_ids
        out.append(item)
    out.sort(key=lambda x: (str(x.get("date") or ""), x["id"]), reverse=True)
    pending = [x["id"] for x in out if x["kind"] == "none" and not x.get("review")]
    return {"schema": SCHEMA, "generated_at": generated_at, "count": len(out), "review_pending": len(pending),
            "topic_rule": "keywords_on_official_subject_v1 (a validar por el comité)", "items": out}


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def export(signals: list[dict], root: Path, out_dir: Path, today: date, generated_at: str | None = None,
           persist: bool = True) -> dict:
    """Update the registry with today's signals and write web/data/normativa.json (+ normativa_cards.json).

    ``persist`` is False for offline or back-dated builds (tests, QA, --as-of): they read the registry but never write
    it, so a fixture date cannot rewrite the committed repository (review of #180)."""
    reg_path, rev_path = root / REGISTRY, root / REVIEW
    registry = update_registry(_read(reg_path, {"items": {}}), signals, today)
    if persist:
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(registry, ensure_ascii=False, indent=2) + "\n"
        if not reg_path.exists() or reg_path.read_text(encoding="utf-8") != text:
            reg_path.write_text(text, encoding="utf-8")
    feed = index_feed_ids(signals)
    index = build(registry, _read(rev_path, {"decisions": {}}), feed, generated_at)
    (out_dir / "normativa.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    public = {x["id"] for x in index["items"]}
    cards = {"schema": SCHEMA, "cards": [rec["card"] for rid, rec in registry["items"].items()
                                          if rid in public and isinstance(rec.get("card"), dict) and rec.get("signal_id") not in feed]}
    (out_dir / "normativa_cards.json").write_text(json.dumps(cards, ensure_ascii=False) + "\n", encoding="utf-8")
    return index


def index_feed_ids(signals: list[dict]) -> set[str]:
    return {signal_id(s) for s in signals}
