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
    return r
