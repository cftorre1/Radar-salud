"""DEIS document releases with dates asserted in their official listing.

The data hub's years describe coverage, not publication.  Centro FIC supplies
an additional official surface where individual PDF links have explicit dated
publication notices.  Discovery carries that notice; the pipeline must still
capture the linked PDF before publishing any signal.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from .models import RawItem


DEIS_DOCUMENT_LISTING = "https://deis.minsal.cl/centrofic/"
DEIS_OFFICIAL_HOSTS = frozenset({"deis.minsal.cl", "repositoriodeis.minsal.cl"})
_NOTICE = re.compile(
    r"\b(?P<label>publicad[oa]|actualizad[oa]|actualizaci[oó]n)\s*"
    r"(?:(?:el\s+)|:\s*)?(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{4})(?!\d)",
    re.I,
)
_EDITORIAL = re.compile(
    r"actualizaci[oó]n editorial|sin cambios en (?:el contenido|la tabla)|"
    r"revisi[oó]n de redacci[oó]n|ajuste en la presentaci[oó]n", re.I,
)
_SUBSTANTIVE_UPDATE = re.compile(
    r"(?:corregir|correcci[oó]n|incorpora|reemplaza|modifica|ampl[ií]a|"
    r"nuev[oa]s? (?:criterios|categor[ií]as|c[oó]digos|orientaciones))", re.I,
)


def official_deis_url(url: str, *, pdf: bool = False) -> bool:
    """Use exact authorities; reject credentials, ports and lookalike hosts."""
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https" and parsed.netloc.lower() in DEIS_OFFICIAL_HOSTS
        and (not pdf or parsed.path.lower().endswith(".pdf"))
    )


def _fetch_deis_html(url: str) -> str:
    # Import lazily so parser-only users need no transport initialization.
    from .public_source_transport import fetch_official_html
    return fetch_official_html(url, "deis")


class _DocumentBlocks(HTMLParser):
    """Keep the release notice inside its own leaf list item."""

    def __init__(self):
        super().__init__()
        self.blocks: list[dict] = []
        self._stack: list[dict] = []
        self._skip = 0
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        lower = tag.lower()
        if lower in {"script", "style"}:
            self._skip += 1
        if lower == "li":
            if self._stack:
                self._stack[-1]["nested"] = True
            self._stack.append({"parts": [], "links": [], "anchor": None, "nested": False})
        elif lower == "a" and self._stack and not self._skip:
            self._stack[-1]["anchor"] = {"href": dict(attrs).get("href", ""), "parts": []}

    def handle_data(self, data):
        if self._skip:
            return
        self.text.append(data)
        if self._stack:
            block = self._stack[-1]
            block["parts"].append(data)
            if block["anchor"] is not None:
                block["anchor"]["parts"].append(data)

    def handle_endtag(self, tag):
        lower = tag.lower()
        if lower in {"script", "style"}:
            self._skip = max(0, self._skip - 1)
        elif lower == "a" and self._stack:
            block = self._stack[-1]
            if block["anchor"] is not None:
                link = block["anchor"]
                block["links"].append((link["href"], " ".join("".join(link["parts"]).split())))
                block["anchor"] = None
        elif lower == "li" and self._stack:
            block = self._stack.pop()
            if not block["nested"]:
                self.blocks.append(block)


class DeisDocumentScout:
    """Discover dated official guidance, with PDF verification left to processing."""

    SOURCE_SLUG = "deis"
    SOURCE_NAME = "DEIS"
    SOURCE_TYPE = "official"
    PAGE = DEIS_DOCUMENT_LISTING

    def __init__(self, fetcher: Callable[[str], str] | None = None, today: date | None = None):
        self.fetcher = fetcher or _fetch_deis_html
        self.today = today
        self.diagnostics: dict = {}

    def discover_from_html(self, html: str, page: str | None = None) -> list[RawItem]:
        page = page or self.PAGE
        if page != self.PAGE:
            raise ValueError("DEIS document listing must be the verified Centro FIC endpoint")
        parser = _DocumentBlocks()
        parser.feed(html)
        plain = " ".join(" ".join(parser.text).split())
        if (not re.search(r"Departamento de Estad[ií]sticas", plain, re.I)
                or not re.search(r"Centro Nacional de Referencia", plain, re.I)
                or not re.search(r"Documentaci[oó]n y Normativa", plain, re.I)):
            raise RuntimeError("DEIS Centro FIC document listing structure unrecognized")
        today = self.today or datetime.now(ZoneInfo("America/Santiago")).date()
        self.diagnostics = {
            "listing_url": page, "listing_recognized": True,
            "document_blocks": 0, "dated_documents": 0,
            "rejected_missing_date": 0, "rejected_invalid_date": 0,
            "rejected_ambiguous_date": 0, "rejected_editorial_only": 0,
            "rejected_unproven_update": 0, "document_verification": "pending_pipeline",
        }
        digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
        out = []
        seen = set()
        for block in parser.blocks:
            links = [(urljoin(page, href), title) for href, title in block["links"]
                     if href and len(title) >= 12 and official_deis_url(urljoin(page, href), pdf=True)]
            if len({url for url, _ in links}) != 1:
                continue
            self.diagnostics["document_blocks"] += 1
            text = " ".join(" ".join(block["parts"]).split())
            if _EDITORIAL.search(text):
                self.diagnostics["rejected_editorial_only"] += 1
                continue
            notices = list(_NOTICE.finditer(text))
            published = [notice for notice in notices if notice["label"].lower().startswith("publicad")]
            selected = published or notices
            if not selected:
                self.diagnostics["rejected_missing_date"] += 1
                continue
            if len({(m["year"], m["month"], m["day"]) for m in selected}) != 1:
                self.diagnostics["rejected_ambiguous_date"] += 1
                continue
            if not published and not _SUBSTANTIVE_UPDATE.search(text):
                self.diagnostics["rejected_unproven_update"] += 1
                continue
            notice = selected[0]
            try:
                release_date = date(int(notice["year"]), int(notice["month"]), int(notice["day"]))
            except ValueError:
                self.diagnostics["rejected_invalid_date"] += 1
                continue
            if release_date > today:
                self.diagnostics["rejected_invalid_date"] += 1
                continue
            url, title = links[0]
            if url in seen:
                continue
            seen.add(url)
            kind = "official_document_listing:" + ("published" if published else "updated")
            out.append(RawItem(
                self.SOURCE_SLUG, title[:300], url, self.SOURCE_NAME, self.SOURCE_TYPE,
                event_date=release_date.isoformat(),
                metadata={
                    "discovered_from": page, "resource_kind": "dated_data_release",
                    "document_kind": "deis_classification_guidance", "pdf_url": url,
                    "document_verification": "pending_pipeline",
                    "publication_date_source": kind,
                    "publication_date_evidence": {
                        "kind": kind, "value": notice.group(0),
                        "date": release_date.isoformat(), "url": page,
                    },
                    "listing_sha256": digest,
                },
            ))
        self.diagnostics["dated_documents"] = len(out)
        self.diagnostics["coverage_status"] = "dated_documents_found" if out else "no_verifiable_documents"
        return sorted(out, key=lambda item: item.event_date, reverse=True)[:30]

    def discover(self) -> list[RawItem]:
        self.diagnostics = {"listing_url": self.PAGE, "listing_recognized": False}
        try:
            html = self.fetcher(self.PAGE)
            return self.discover_from_html(html)
        except Exception as exc:
            self.diagnostics.update(fetch_error=type(exc).__name__, fetch_error_detail=str(exc))
            raise
