"""Period of a Superintendencia de Salud statistical bulletin, read from its own documents.

The biblioteca-digital page of the IP bulletin is titled with the month it was posted
("Boletín Estadístico Informativo IP – Septiembre 2026") while every PDF it carries is
"boletin-n2-2026-<tema>-enero-junio-2026.pdf" (Boletín N°2, enero–junio 2026). The card title
must state the period the documents cover (staging audit 29-oct-2026). Only the document file
names are read; when they disagree or do not state a period, nothing changes.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "setiembre", "octubre", "noviembre", "diciembre")
_M = "|".join(MONTHS)
_DOC = re.compile(rf"boletin-n[°º]?(\d{{1,2}})-(20\d{{2}})-[a-z0-9-]*?-?({_M})-({_M})-(20\d{{2}})(?:-\d+)?\.pdf$", re.I)
_TITLE = re.compile(r"^\s*bolet[ií]n\s+estad[ií]stico", re.I)
_TITLE_MONTH = re.compile(rf"\s*[-–—]\s*(?:{_M})\s+20\d{{2}}\s*$", re.I)


def documents_period(documents: Any) -> dict[str, str] | None:
    """{"number", "period"} when every PDF names the same bulletin number and period."""
    found = set()
    for d in documents or []:
        url = d.get("url") if isinstance(d, dict) else d
        name = urlsplit(str(url or "")).path.rsplit("/", 1)[-1].lower()
        m = _DOC.search(name)
        if not m:
            return None
        number, _, start, end, year = m.groups()
        found.add((str(int(number)), f"{start}–{end} {year}"))
    if len(found) != 1:
        return None
    number, period = found.pop()
    return {"number": number, "period": period}


def documents_release(documents: Any) -> dict[str, str] | None:
    """documents_period plus the bulletin year and the cut-off month ('2026-09'), all from the file names."""
    found = documents_period(documents)
    if not found:
        return None
    url = next(iter(documents or []))
    url = url.get("url") if isinstance(url, dict) else url
    m = _DOC.search(urlsplit(str(url or "")).path.rsplit("/", 1)[-1].lower())
    end = MONTHS.index(m[4].lower())
    end = end if end < MONTHS.index("setiembre") else end - 1  # 'setiembre' is September, not a 13th month
    return {**found, "year": m[2], "cutoff": f"{m[5]}-{end + 1:02d}"}


def apply_bulletin_period(record: dict[str, Any]) -> dict[str, Any]:
    """Display title "<bulletin name> N°<n> · <period>" from the documents; full title kept."""
    title = " ".join(str(record.get("title") or "").split())
    if record.get("display_title") or not _TITLE.match(title):
        return record
    found = documents_period(record.get("source_documents"))
    if not found:
        return record
    r = dict(record)
    base = _TITLE_MONTH.sub("", title).strip(" -–—")
    r["display_title"] = f"{base} N°{found['number']} · {found['period']}"
    r["data_period"] = found["period"]
    r["data_period_basis"] = "source_document_file_names"
    r["source_title_full"] = title
    release = documents_release(record.get("source_documents"))
    if release:  # the release a statistics ficha must cover before it absorbs this card (not the posting month)
        r["stat_period"] = release["cutoff"]
    return r


# ---------------------------------------------------------------------------------------------
# Loose bulletin PDFs (Dirección 1-nov-2026)
#
# The Intendencia de Prestadores listing links each PDF of a bulletin separately and the daily scout turns each into
# its own card ('Boletín N°3-2026 Acreditación enero-septiembre 2026', '… Mediación …', …). Until the F6 ficha covers
# that release, they are shown as ONE card titled from the documents, in the series' own name, listing every PDF and
# saying plainly that the figures are being verified. Nothing is read from the PDFs here and no figure is shown.

LOOSE_SOURCE = "Superintendencia de Salud · Intendencia de Prestadores"
TOPIC_NAMES = (("acreditacion", "acreditación"), ("mediacion", "mediación"), ("reclamos", "reclamos"), ("rnpi", "RNPI"))
F6_FAMILY = "boletin_ip"


def _topic(url: str) -> tuple[int, str] | None:
    name = urlsplit(str(url or "")).path.rsplit("/", 1)[-1].lower()
    for i, (key, label) in enumerate(TOPIC_NAMES):
        if re.search(rf"^boletin-n[°º]?\d{{1,2}}-20\d{{2}}-{key}-", name):
            return i, label
    return None


def loose_release(card: dict[str, Any]) -> dict[str, str] | None:
    """The bulletin release of a loose PDF card (one PDF of the Prestadores listing), else None."""
    if card.get("source_documents") or card.get("stats_ficha") or card.get("loose_bulletin"):
        return None
    if str(card.get("source_name") or "") != LOOSE_SOURCE:
        return None
    url = card.get("source_url")
    if not str(url or "").startswith("https://") or not str(url).lower().endswith(".pdf") or not _topic(url):
        return None
    return documents_release([url])


def series_name(history: Any) -> str | None:
    """Name of the bulletin series as the SIS titles it ('Boletín Estadístico Informativo IP'), read from the most
    recent release page in the history whose documents are bulletin PDFs. None when there is none."""
    best = None
    for s in history or []:
        title = " ".join(str(s.get("title") or "").split())
        if not _TITLE.match(title) or not documents_period(s.get("source_documents")):
            continue
        if not all(_topic(d.get("url") if isinstance(d, dict) else d) for d in s.get("source_documents") or []):
            continue
        day = str(s.get("event_date") or "")[:10]
        if best is None or day > best[0]:
            best = (day, _TITLE_MONTH.sub("", title).strip(" -–—"))
    return best[1] if best else None


def _f6_live(fichas: Any) -> dict | None:
    return next((f for f in fichas or [] if f.get("family") == "F6" and f.get("status") == "PASS"), None)


_MONTHS12 = tuple(m for m in MONTHS if m != "setiembre")


def _month_label(period: str) -> str:
    y, m = period.split("-")
    return f"{_MONTHS12[int(m) - 1]} {y}"


def collapse_loose_bulletins(cards: list[dict[str, Any]], *, history: Any = None, fichas: Any = None,
                             holds: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    """Replace the loose PDF cards of one bulletin release with one card (the loose cards stay in history).

    The card is titled '<series name> N°<n> · <period>' with the existing bulletin-title rule (apply_bulletin_period),
    lists the PDFs under their listing titles, links the current F6 ficha and says the figures are being verified. It is
    marked ``stat_family: boletin_ip`` / ``stat_period`` so the F6 ficha absorbs it once it covers that release, as it
    absorbed the N°2 release card. ``holds`` maps a release period to its recorded F6 HOLD reasons (kept as data)."""
    groups: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for c in cards:
        rel = loose_release(c)
        if rel:
            key = (rel["number"], rel["year"], rel["period"], rel["cutoff"])
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(c)
    if not groups:
        return cards
    from .editorial_committee import build_committee_artifact
    name = series_name(history)
    live = _f6_live(fichas)
    merged: dict[int, dict] = {}
    for key in order:
        members = sorted(groups[key], key=lambda c: _topic(c["source_url"])[0])
        number, year, period, cutoff = key
        docs = [{"url": c["source_url"], "title": " ".join(str(c.get("title") or "").split()) + " (PDF)",
                 "label": _topic(c["source_url"])[1], "document_sha256": c.get("document_sha256")} for c in members]
        base = apply_bulletin_period({"title": name or "Boletín", "source_documents": docs})
        title = base.get("display_title") or f"Boletín N°{number}-{year} · {period}"
        topics = [_topic(c["source_url"])[1] for c in members]
        listed = ", ".join(topics[:-1]) + " y " + topics[-1] if len(topics) > 1 else topics[0]
        detected = sorted(str(c.get("first_detected_at") or c.get("detected_at") or c.get("event_date") or "") for c in members)
        days = sorted(str(c.get("event_date") or "")[:10] for c in members if c.get("event_date"))
        what = (f"La Intendencia de Prestadores de la Superintendencia de Salud tiene disponible el Boletín N°{number}-{year} "
                f"({period}) en {len(docs)} PDF: {listed}.")
        covered = bool(live) and str(live.get("period") or "") >= cutoff
        status = None
        if not covered:
            status = {"status": "verifying", "period": cutoff,
                      "text": ("Alicanto está verificando las cifras de este boletín en los PDF originales. Hasta que pasen "
                               "la verificación, no se muestran cifras de este boletín."),
                      "hold_reasons": list((holds or {}).get(cutoff) or [])}
            if live:
                live_number = next((m[0] for s in live.get("sources") or []
                                    for m in [re.search(r"N°\d{1,2}-20\d{2}", str(s.get("label") or ""))] if m), None)
                status["live_ficha"] = {"id": f"stats-ficha:F6:{live['period']}", "period": live["period"],
                                        "label": "Ver la ficha vigente: " + (f"Boletín IP {live_number} · " if live_number else "Boletín IP · ")
                                                 + f"datos a {_month_label(live['period'])}"}
        lead = dict(members[0])
        for k in ("editorial_committee", "document_sha256", "key_facts", "key_points", "why_it_matters", "card_why",
                  "display_title", "source_title_full"):
            lead.pop(k, None)
        card = {**lead,
                "piece_id": f"sis-bulletin:{F6_FAMILY}:N{number}-{year}",
                "title": title, "display_title": title, "source_name": LOOSE_SOURCE,
                "source_url": docs[0]["url"], "source_documents": docs,
                "event_date": days[0] if days else lead.get("event_date"),
                "first_detected_at": detected[0] if detected and detected[0] else lead.get("first_detected_at"),
                "date_basis": "first_detected", "publication_date": None,
                "data_period": period, "data_period_basis": "source_document_file_names",
                "stat_family": F6_FAMILY, "stat_period": cutoff, "signal_types": ["Datos"],
                "what_happened": what, "card_what": what, "card_why_optional": True, "why_it_matters": "",
                "loose_bulletin": {"number": f"N°{number}-{year}", "period": period, "members": [c["source_url"] for c in members],
                                   "series_name_basis": "history_release_page" if name else "none"},
                "bulletin_status": status}
        card["editorial_committee"] = build_committee_artifact(card)
        merged[id(members[0])] = card
        for c in members[1:]:
            merged[id(c)] = None
    out = []
    for c in cards:
        if id(c) in merged:
            if merged[id(c)] is not None:
                out.append(merged[id(c)])
        else:
            out.append(c)
    return out
