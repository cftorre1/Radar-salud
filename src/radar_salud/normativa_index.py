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
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .cl_calendar import add_term

SCHEMA = "normativa_v1"
REGISTRY = Path("data/normativa/registry.json")
REVIEW = Path("data/normativa/review.json")

MONTHS = {m: i for i, m in enumerate(("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                      "septiembre", "octubre", "noviembre", "diciembre"), 1)}
_M = "|".join(MONTHS)
_DAY_DATE = re.compile(rf"\b(\d{{1,2}})\s*(?:[°º]|ro)?\s+de\s+({_M})\s+(?:de|del)\s+(?:a[ñn]o\s+)?(\d{{4}})\b", re.I)
_MONTH_DATE = re.compile(rf"\bmes\s+de\s+({_M})\s+(?:de|del)\s+(?:a[ñn]o\s+)?(\d{{4}})\b", re.I)
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
_NUM = r"(?:\d+|un[oa]?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|quince|veinte|treinta|sesenta|noventa)"
# Review round 2: «en el plazo de 30 días desde su notificación», «dentro de cinco días hábiles desde la notificación»
# (a reporting or payment deadline) and «seis meses contados desde» are terms, never «vigente desde su notificación».
_RELATIVE = re.compile(rf"\b{_NUM}\s+(?:d[ií]as|meses|a[ñn]os)(?:\s+(?:h[aá]biles|corridos))?\s+(?:contad[oa]s\s+)?(?:desde|a\s+contar)\b", re.I)
_DEADLINE = re.compile(r"\b(?:dentro\s+de|en\s+el\s+plazo\s+de|plazo\s+de)\b[^.;]*$", re.I)
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
    if ev and _DEADLINE.search(t[max(0, ev.start() - 80):ev.start()]):
        return out  # «dentro de cinco días hábiles desde la notificación»: a deadline, not the entry into force
    exc = _EXCEPTION.search(t)
    if ev and exc and exc.start() < ev.start() and any(m.start() < exc.start() and _CUE.search(t[:m.start()][-60:])
                                                       for m in _DAY_DATE.finditer(t)):
        ev = None  # «rige desde el 31 de marzo de 2025, con excepción de … que rigen desde su publicación»: the date is the rule
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
        cue = _CUE.search(re.sub(r"\s*mes\s*$", "", before[-60:].rstrip()) + " ") or re.search(r"a\s+contar\s+del\s*$", before[-20:], re.I)
        if cue and not _BAD.search(before[-80:]):
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
    from .health_scope import outside_health
    verdict = str((s.get("editorial_committee") or {}).get("verdict") or "PASS").upper()
    return (not outside_health(s) and s.get("feed_visibility") is not False and verdict not in ("HOLD", "REJECT")
            and bool((s.get("display_title") or s.get("title")) and s.get("normative_document_label") and s.get("source_url")))


# Dirección 20-nov-2026: «Sin fecha» only when the text truly gives none. A term counted from the publication
# («6 meses corridos contados desde su publicación») is computed from the act's date; counted from the Diario Oficial,
# from the Diario Oficial edition Alicanto captured for that same act (the publication stamp, not the detection day).
# Dirección 21-nov-2026: business days are computed (cl_calendar); «N días» with no qualifier are calendar days, except
# when the text invokes Ley 19.880, whose day terms are business days (art. 25).
_WORDNUM = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
            "nueve": 9, "diez": 10, "quince": 15, "veinte": 20, "treinta": 30, "sesenta": 60, "noventa": 90,
            "veinticuatro": 24, "cuarenta y ocho": 48, "setenta y dos": 72}
_NUM2 = r"(?:\d+|un[oa]?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|quince|veinte|treinta|sesenta|noventa|veinticuatro|cuarenta\s+y\s+ocho|setenta\s+y\s+dos)"
_TERM_FROM_PUB = re.compile(rf"\b({_NUM})\s+(d[ií]as?|mes(?:es)?|a[ñn]os?)(?:\s+(corridos?|h[aá]biles))?\s+(?:contad[oa]s?\s+)?(?:desde|a\s+contar\s+de)\s+(?:su|la)\s+(?:fecha\s+de\s+(?:su\s+)?)?publicaci[oó]n\b", re.I)


def _n(word: str) -> int | None:
    w = " ".join(word.lower().split())
    return int(w) if w.isdigit() else _WORDNUM.get(w)


def term_from_publication(text: Any, published: Any, do_date: Any = None) -> dict | None:
    """«6 meses corridos contados desde su publicación» + the act's date → the computed day. A term counted from the
    Diario Oficial uses ``do_date``; while that edition is not captured the norm is «pendiente de Diario Oficial»."""
    t = " ".join(str(text or "").split())
    m = _TERM_FROM_PUB.search(t)
    if not m:
        return None
    start = t.rfind('.', 0, m.start()) + 1
    end = t.find('.', m.end())
    sentence = t[start:end if end >= 0 else len(t)]
    # review of #221: a deadline («plazo de seis meses … para adecuar», «deberán … dentro de») is not the entry into force.
    if _BAD.search(t[start:m.start()]) or re.search(r"\b(?:dentro\s+de|para\s+\w+r)\b", sentence, re.I):
        return None
    n = _n(m.group(1))
    if not n:
        return None
    do = bool(_DIARIO_OFICIAL.search(sentence))
    base_s = do_date if do else published
    if do and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(base_s or "")):
        return {"kind": "on_publication_do", "eff": None, "prec": None}
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(base_s or "")):
        return None
    business = bool(m.group(3) and m.group(3).lower().startswith("h")) or (not m.group(3) and "19.880" in t)
    eff = add_term(date.fromisoformat(str(base_s)), n, m.group(2), business)
    if eff is None:
        return None  # a year whose holidays are not listed: never guessed
    return {"kind": "date", "eff": eff.isoformat(), "prec": "day", "computed": f"{m.group(0)} ({base_s})"}


# Dirección 21-nov-2026: compliance deadlines («informar dentro de los diez días hábiles siguientes a la vigencia»)
# are shown apart from the entry into force, with their own countdown. Only from the official text Alicanto stored
# (normative_evidence), only sentences that impose a duty; a per-case term («dentro de cinco días hábiles contado desde
# su presentación», «24 horas») has no countdown.
_DUTY = re.compile(r"\bdeber[aá]n?\b|\bdeben\b|\btendr[aá]n?\s+(?:un\s+)?plazo\b|^\s*[a-z]\)\s+[A-ZÁÉÍÓÚ][a-záéíóú]+r(?:se)?\b")
_RECITAL = re.compile(r"recurso|reposici[oó]n|jer[aá]rquico|solicita|OBJETIVO|se\s+computa|transitorio\s+de\s+la\s+Ley|aludía", re.I)
_TERM = re.compile(rf"(?:dentro\s+(?:del\s+plazo\s+)?de(?:\s+(?:los|las))?|en\s+(?:un|el)\s+plazo\s+(?:m[aá]ximo\s+)?de|a\s+m[aá]s\s+tardar\s+(?:dentro\s+de|en))\s+"
                   rf"({_NUM2})\s+(d[ií]as|meses|a[ñn]os|horas)(?:\s+(h[aá]biles|corridos))?"
                   r"(?:\s+((?:siguientes|posteriores)\s+a|contad[oa]s?\s+desde|a\s+contar\s+de(?:sde)?|desde)\s+([^,.;]{3,90}))?", re.I)
_BY_DATE = re.compile(r"\b(?:a\s+m[aá]s\s+tardar|no\s+m[aá]s\s+all[aá])\s+(?:del?|el)\s+", re.I)
_A_VIG = re.compile(r"^(?:la\s+)?(?:entrada\s+en\s+)?vigencia\b", re.I)
_A_ACT = re.compile(r"^(?:la\s+fecha\s+de(?:l)?\s+)?(?:la\s+|el\s+)?(?:presente|este|esta)\s+(?:oficio|circular|resoluci[oó]n|dictamen)|^la\s+fecha\s+del?\s+presente|^(?:su|la)\s+publicaci[oó]n", re.I)
_A_NOTIF = re.compile(r"^(?:su|la)\s+notificaci[oó]n", re.I)
_SPLIT_FIX_MIN = 4
_STOP = {"a", "al", "de", "del", "el", "en", "la", "las", "lo", "los", "y", "e", "o", "u", "un", "una", "se", "su", "sus",
         "que", "con", "por", "es", "le", "les", "ni", "no", "si", "ya"}


def _vocab(evidence_dir: Path | None) -> set[str]:
    out: set[str] = set()
    if evidence_dir is None or not evidence_dir.is_dir():
        return out
    for f in sorted(evidence_dir.glob("*.json")):
        out.update(w.lower() for w in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñÜü]{%d,}" % _SPLIT_FIX_MIN, str(_read(f, {}).get("text") or "")))
    return out


def unsplit(text: str, vocab: set[str]) -> str:
    """Rejoin words the PDF capture split («cobertu ra», «comunicac ión»): two pieces join only when the whole word is
    in the vocabulary of the official texts and at least one piece is not a word by itself."""
    toks = text.split(" ")
    out: list[str] = []
    i = 0
    while i < len(toks):
        a = toks[i]
        while i + 1 < len(toks):
            b = toks[i + 1]
            wa, wb = re.match(r"^([A-Za-zÁÉÍÓÚáéíóúÑñ]*)$", a), re.match(r"^([A-Za-zÁÉÍÓÚáéíóúÑñ]+)([^A-Za-zÁÉÍÓÚáéíóúÑñ]*)$", b)
            if not (wa and wb and a and b[:1].islower()) or a.lower() in _STOP or wb.group(1).lower() in _STOP:
                break
            whole = (a + wb.group(1)).lower()
            if whole in vocab and not (a.lower() in vocab and wb.group(1).lower() in vocab):
                a, i = a + b, i + 1
            else:
                break
        out.append(a)
        i += 1
    return " ".join(out)


def _action(sentence: str, at: int) -> str:
    head = sentence[:at]
    m = re.search(r"\bdeber[aá]n?\s+(?:\w+\s+)?(\w+r(?:se|le|les)?)\b", head) or re.search(r"\bdeben\s+(\w+r(?:se)?)\b", head) \
        or re.match(r"^\s*[a-z]\)\s+([A-ZÁÉÍÓÚ]\w+r(?:se)?)\b", head)
    if not m:
        return ""
    act = head[m.start(1):].strip()
    act = re.split(r",\s+|\s+mediante\s|\s+a\s+trav[eé]s\s+de\s", act)[0].strip(" ,;:")
    if len(act) > 140:
        act = act[:140].rsplit(" ", 1)[0] + "…"
    return act[:1].upper() + act[1:]


def compliance_terms(text: Any, vocab: set[str] | None = None) -> list[dict]:
    """Duties with a term in the official text: [{accion, n, unit, habiles, anchor, desde, quote} | {accion, due, quote}].
    anchor: vigencia | acto | do | notif | caso."""
    t = " ".join(str(text or "").split())
    if vocab:
        t = unsplit(t, vocab)
    out: list[dict] = []
    for sent in re.split(r"(?<=[.;])\s+", t):
        if not _DUTY.search(sent) or _RECITAL.search(sent):
            continue
        for m in _TERM.finditer(sent):
            n = _n(m.group(1))
            if not n:
                continue
            tail = re.split(r"\s+(?:y|e|o)\s+", (m.group(5) or "").strip())[0]
            unit = m.group(2).lower()
            if unit.startswith("h") or not m.group(4):
                anchor = "caso"
            elif _A_VIG.search(tail):
                anchor = "vigencia"
            elif _A_ACT.search(tail):
                anchor = "do" if _DIARIO_OFICIAL.search(tail) else "acto"
            elif _A_NOTIF.search(tail):
                anchor = "notif"
            else:
                anchor = "caso"
            action = _action(sent, m.start())
            if not action:
                continue
            desde = {"vigencia": "desde la entrada en vigencia", "acto": "desde la fecha de la norma",
                     "do": "desde su publicación en Diario Oficial", "notif": "desde su notificación"}.get(anchor)
            if anchor == "caso" and m.group(4):
                desde = re.sub(r"\s+(?:y|e|o)$", "", " ".join(f"{m.group(4)} {tail}".split())[:60])
                desde = re.sub(r"^contad[oa]s?\s+", "", desde)
            out.append({"accion": action, "n": n, "unit": "días" if unit.startswith("d") else unit.replace("anos", "años"),
                        "habiles": bool(m.group(3) and m.group(3).lower().startswith("h")) or (not m.group(3) and "19.880" in t),
                        "anchor": anchor, "desde": desde, "quote": sent[:400]})
        for m in _BY_DATE.finditer(sent):
            dm = _DAY_DATE.match(sent, m.end())
            d = dm and _as_date(dm.group(3), dm.group(2), dm.group(1))
            action = _action(sent, m.start())
            if d and action:
                out.append({"accion": action, "due": d.isoformat(), "anchor": "fecha", "quote": sent[:400]})
    seen, uniq = set(), []
    for x in out:
        k = (x["accion"].lower(), x.get("n"), x.get("unit"), x.get("due"))
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq[:4]


def _evidence_text(url: Any, evidence_dir: Path | None) -> str:
    if not url or evidence_dir is None or not evidence_dir.is_dir():
        return ""
    for f in sorted(evidence_dir.glob("*.json")):
        d = _read(f, {})
        if url in (d.get("page_url"), d.get("document_url")):
            return str(d.get("text") or "")
    return ""


PLAZOS_V = 1


def _plus_days(d: Any, n: int) -> str:
    try:
        return (date.fromisoformat(str(d)[:10]) + timedelta(days=n)).isoformat()
    except ValueError:
        return ""


def _same_year(title: str, d: Any) -> bool:
    """«Circular número IF/539, de 2026.-»: the act's year must be the norm's (review of #221)."""
    m = re.search(r",\s*de\s+((?:19|20)\d\d)\b", title)
    return bool(m) and m.group(1) == str(d or "")[:4]


def _act_number(label: str) -> tuple[str, str] | None:
    m = re.search(r"\b(IF|IP|SS)?\s*/?\s*N\s*[°º]?\s*([\d\.]+)", label or "")
    return ((m.group(1) or "").upper(), m.group(2).replace(".", "")) if m else None


def diario_oficial_date(rec: dict, rows: list[dict]) -> str | None:
    """Date of the Diario Oficial edition that published this act, from Alicanto's own DO captures."""
    num = _act_number(rec.get("label") or "")
    typ = str(rec.get("type") or "").split()[0].lower()
    if "exenta" in str(rec.get("type") or "").lower():
        typ = typ + r"\w*\s+exenta"  # exenta and non-exenta resolutions are numbered apart
    if not num or not typ:
        return None
    pre, n = num
    pat = re.compile(rf"\b{typ if 'exenta' in typ else re.escape(typ)}\w*\s+(?:n[uú]mero|N\s*[°º])\s*{re.escape(pre)}\s*/?\s*{re.escape(n)}\b", re.I)
    days = sorted(str(r.get("event_date") or "")[:10] for r in rows
                  if "Diario Oficial" in str(r.get("source_name") or "") and str(r.get("event_date") or "")[:10] >= str(rec.get("date") or "")
                  and str(r.get("event_date") or "")[:10] <= _plus_days(rec.get("date"), 120)
                  and pat.search(str(r.get("title") or r.get("source_title_full") or ""))
                  and _same_year(str(r.get("title") or r.get("source_title_full") or ""), rec.get("date")))
    return days[0] if days else None


def evidence_validity(url: Any, evidence_dir: Path | None) -> str | None:
    """«Observación: Vigencia desde su publicación» on the issuer's own page (SUSESO), from Alicanto's stored evidence of
    that same URL. Literal text only; nothing is inferred (Dirección 20-nov-2026, Circular 3935)."""
    if not url or evidence_dir is None or not evidence_dir.is_dir():
        return None
    for f in sorted(evidence_dir.glob("*.json")):
        d = _read(f, {})
        if url not in (d.get("page_url"), d.get("document_url")):
            continue
        m = re.search(r"Observaci[oó]n:\s*(Vigencia\s+(?:desde|a\s+contar)[^.;]{3,120}?)(?=\s+(?:Acci[oó]n|Fuentes|Materia|Destinatarios|Vigencia|Departamento|Estado|Fecha):|[.;]|$)", str(d.get("text") or ""))
        if m:
            return " ".join(m.group(1).split())
    return None


def update_registry(registry: dict, signals: list[dict], today: date, history: list[dict] | None = None,
                    evidence_dir: Path | None = None) -> dict:
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
        if (prev or {}).get("do_date"):
            rec["do_date"] = prev["do_date"]  # the Diario Oficial date stays once found (review of #221)
        if not rec["validity"] and (prev or {}).get("validity"):
            rec["validity"] = prev["validity"]  # a later capture without the text never erases what was literal
        if not rec["validity"]:
            rec["validity"] = evidence_validity(rec.get("url"), evidence_dir)
        if prev != rec:
            items[rec["id"]] = rec
    # Review round 2: curation drops hidden/rejected cards before they reach this function, so a norm withdrawn later
    # would keep its last PASS record. The newest history record of each source URL decides: not publishable (and not
    # in today's feed) → withheld.
    if history:
        live = {s.get("source_url") for s in signals}
        newest: dict[str, dict] = {}
        for h in history:
            if h.get("source_url") and (h.get("event_type") == "REGULATION" or "Normativa" in (h.get("signal_types") or [])):
                newest[h["source_url"]] = h
        for rid, rec in list(items.items()):
            h = newest.get(rec.get("url"))
            if h is not None and rec.get("url") not in live and not rec.get("withheld") and (
                    h.get("feed_visibility") is False
                    or str((h.get("editorial_committee") or {}).get("verdict") or "PASS").upper() in ("HOLD", "REJECT")):
                items[rid] = {**rec, "withheld": True}
    # Diario Oficial date for «rige desde su publicación en el Diario Oficial» (Dirección 20-nov-2026).
    rows = [*signals, *(history or [])]
    for rid, rec in list(items.items()):
        if not rec.get("do_date") and _DIARIO_OFICIAL.search(str(rec.get("validity") or "")):
            d = diario_oficial_date(rec, rows)
            if d:
                items[rid] = {**rec, "do_date": d}
    # Dirección 21-nov-2026: compliance deadlines from the official text, read once per extraction version.
    vocab: set[str] | None = None
    for rid, rec in list(items.items()):
        if rec.get("plazos_v") != PLAZOS_V and evidence_dir is not None:
            if vocab is None:
                vocab = _vocab(evidence_dir)
            items[rid] = {**rec, "plazos": compliance_terms(_evidence_text(rec.get("url"), evidence_dir), vocab), "plazos_v": PLAZOS_V}
    # Dirección 12-nov-2026: norms outside health leave the index too (kept in the registry as withheld).
    from .health_scope import outside_health
    for rid, rec in list(items.items()):
        if not rec.get("withheld") and (outside_health(rec) or outside_health(rec.get("card") or {})):
            items[rid] = {**rec, "withheld": True}
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
        if v.get("kind") == "none":
            v = {**v, **(term_from_publication(rec.get("validity"), rec.get("date"), rec.get("do_date")) or {})}
        if v.get("kind") == "none" and _RELATIVE.search(" ".join(str(rec.get("validity") or "").split())):
            v["unclear"] = True  # «seis meses desde su notificación»: a term Alicanto cannot date → «en revisión»
        rv = _review_entry(decisions.get(rec["id"]))
        if rec.get("withheld") or (rv or {}).get("kind") == "retirada":
            continue  # not public: withheld by Al día's gates or withdrawn by Dirección
        item = {k: rec.get(k) for k in ("id", "label", "type", "emisor", "date", "subject", "url", "validity", "related", "signal_id", "do_date") if k != "do_date" or rec.get(k)}
        item.update(v, tema=topic(rec.get("subject") or "", rec.get("emisor")))
        if rv:
            item["review"] = rv
        plazos = due_dates(rec.get("plazos") or [], effective_base(item), rec.get("date"), rec.get("do_date"))
        if plazos:
            item["plazos"] = plazos
        # «Ver ficha» always opens the Al día ficha: from the live feed, or from normativa_cards.json once it left it.
        item["ficha"] = f"index.html?abrir=1&desde=normativa&n={rec['id']}#sig-{rec['signal_id']}" if rec.get("signal_id") else None
        item["in_feed"] = rec.get("signal_id") in feed_ids
        out.append(item)
    out.sort(key=lambda x: (str(x.get("date") or ""), x["id"]), reverse=True)
    pending = [x["id"] for x in out if x.get("unclear") and not x.get("review")]
    return {"schema": SCHEMA, "generated_at": generated_at, "count": len(out), "review_pending": len(pending),
            "topic_rule": "keywords_on_official_subject_v1 (a validar por el comité)", "items": out}


def effective_base(item: dict) -> str | None:
    """The day a norm entered (or enters) into force, by the same rules as the page: a literal or computed date, the
    Diario Oficial edition, else the act's own date (Dirección 21-nov-2026: «si no dicen fecha, vigentes desde su
    fecha»). None while pending (Diario Oficial not yet captured, or a term Alicanto cannot date)."""
    r = item.get("review") or {}
    if r.get("kind") == "date":
        return r.get("eff")
    k = item.get("kind")
    if k == "date":
        return item.get("eff")
    if k == "on_publication_do":
        return item.get("do_date")
    if k == "on_notification" or item.get("unclear"):
        return None
    return item.get("date")


def due_dates(plazos: list[dict], vig: str | None, act: Any, do: Any) -> list[dict]:
    """Public compliance deadlines: {accion, plazo, desde, due|None, caso, pendiente}."""
    out = []
    for p in plazos:
        if p.get("anchor") == "fecha":
            out.append({"accion": p["accion"], "plazo": None, "desde": None, "due": p["due"], "caso": False, "pendiente": False})
            continue
        base = {"vigencia": vig, "acto": act, "do": do}.get(p.get("anchor"))
        caso = p.get("anchor") in ("caso", "notif")
        due = None
        if base and not caso and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(base)):
            d = add_term(date.fromisoformat(str(base)), int(p["n"]), p["unit"], bool(p.get("habiles")))
            due = d.isoformat() if d else None
        n, unit = int(p["n"]), p["unit"]
        unit = {"días": "día", "meses": "mes", "años": "año", "horas": "hora"}.get(unit, unit) if n == 1 else unit
        plazo = f"{n} {unit}{' hábiles' if p.get('habiles') else (' corridos' if unit.startswith('d') else '')}"
        if n == 1 and p.get("habiles"):
            plazo = f"1 {unit} hábil"
        out.append({"accion": p["accion"], "plazo": plazo, "desde": p.get("desde"), "due": due, "caso": caso,
                    "pendiente": not caso and due is None})
    return out


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def export(signals: list[dict], root: Path, out_dir: Path, today: date, generated_at: str | None = None,
           persist: bool = True, history: list[dict] | None = None, archive: list[dict] | None = None) -> dict:
    """Update the registry with today's signals and write web/data/normativa.json (+ normativa_cards.json).

    ``persist`` is False for offline or back-dated builds (tests, QA, --as-of): they read the registry but never write
    it, so a fixture date cannot rewrite the committed repository (review of #180)."""
    reg_path, rev_path = root / REGISTRY, root / REVIEW
    # ``archive``: publishable norms from history that Al día no longer shows because they are older than its window
    # (decision 7, Dirección 11-nov-2026: Circular IF/N°532). They join the standing registry; never the feed.
    # Only the norms Dirección listed in review.json «archive_include» (by registry id): an older norm can carry a later
    # suspension or derogation that the registry does not read yet, so none enters by itself.
    review = _read(rev_path, {"decisions": {}})
    wanted = set(review.get("archive_include") or [])
    old = [a for a in (archive or []) if (r := record_from_signal(a)) and r["id"] in wanted]
    registry = update_registry(_read(reg_path, {"items": {}}), list(signals) + old, today, history,
                               evidence_dir=root / "data" / "analysis_cache" / "normative_evidence")
    if persist:
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(registry, ensure_ascii=False, indent=2) + "\n"
        if not reg_path.exists() or reg_path.read_text(encoding="utf-8") != text:
            reg_path.write_text(text, encoding="utf-8")
    feed = index_feed_ids(signals)
    index = build(registry, review, feed, generated_at)
    (out_dir / "normativa.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    public = {x["id"] for x in index["items"]}
    cards = {"schema": SCHEMA, "cards": [rec["card"] for rid, rec in registry["items"].items()
                                          if rid in public and isinstance(rec.get("card"), dict) and rec.get("signal_id") not in feed]}
    (out_dir / "normativa_cards.json").write_text(json.dumps(cards, ensure_ascii=False) + "\n", encoding="utf-8")
    return index


def index_feed_ids(signals: list[dict]) -> set[str]:
    return {signal_id(s) for s in signals}
