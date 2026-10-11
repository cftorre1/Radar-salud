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
from .public_source_transport import normalized_official_url


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
        self.catalog = None
        self.catalog_scout = DeisCatalogScout() if fetcher is None else None

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
            "excluded_documents": [],
            "reference_only_resources": [],
        }
        digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
        out = []
        seen = set()
        for block in parser.blocks:
            for href, title in block['links']:
                reference = urljoin(page, href)
                if (href and official_deis_url(reference)
                        and urlsplit(reference).path.lower().endswith(('.xlsx', '.xls', '.zip'))):
                    self.diagnostics['reference_only_resources'].append({
                        'url': normalized_official_url(reference, self.SOURCE_SLUG),
                        'title': title, 'listing_url': page, 'publication_date': None,
                        'reason': 'non_pdf_reference_outside_dated_document_lane',
                        'listing_notice': ' '.join(' '.join(block['parts']).split())[:600]})
            links = [(urljoin(page, href), title) for href, title in block["links"]
                     if href and len(title) >= 12 and official_deis_url(urljoin(page, href), pdf=True)]
            if len({url for url, _ in links}) != 1:
                continue
            self.diagnostics["document_blocks"] += 1
            text = " ".join(" ".join(block["parts"]).split())
            def reject(reason):
                self.diagnostics['excluded_documents'].append({
                    'url': normalized_official_url(links[0][0], self.SOURCE_SLUG),
                    'title': links[0][1], 'listing_url': page,
                    'reason': reason, 'publication_date': None,
                    'listing_notice': text[:600], 'listing_sha256': digest,
                    'listing_sha256_kind': 'utf8_decoded_listing'})
            if _EDITORIAL.search(text):
                self.diagnostics["rejected_editorial_only"] += 1
                reject('editorial_only_without_material_change')
                continue
            notices = list(_NOTICE.finditer(text))
            published = [notice for notice in notices if notice["label"].lower().startswith("publicad")]
            selected = published or notices
            if not selected:
                self.diagnostics["rejected_missing_date"] += 1
                reject('missing_explicit_publication_date')
                continue
            if len({(m["year"], m["month"], m["day"]) for m in selected}) != 1:
                self.diagnostics["rejected_ambiguous_date"] += 1
                reject('ambiguous_publication_dates')
                continue
            if not published and not _SUBSTANTIVE_UPDATE.search(text):
                self.diagnostics["rejected_unproven_update"] += 1
                reject('update_without_proven_material_change')
                continue
            notice = selected[0]
            try:
                release_date = date(int(notice["year"]), int(notice["month"]), int(notice["day"]))
            except ValueError:
                self.diagnostics["rejected_invalid_date"] += 1
                reject('invalid_publication_date')
                continue
            if release_date > today:
                self.diagnostics["rejected_invalid_date"] += 1
                reject('future_publication_date')
                continue
            url, title = links[0]
            url = normalized_official_url(url, self.SOURCE_SLUG)
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
        document_error = None
        try:
            html = self.fetcher(self.PAGE)
            items = self.discover_from_html(html)
        except Exception as exc:
            self.diagnostics.update(fetch_error=type(exc).__name__, fetch_error_detail=str(exc))
            document_error = exc
        # The statistical catalog is independent of the dated document lane.
        # Preserve either capture when the other surface fails.
        if self.catalog_scout is not None:
            try:
                self.catalog = self.catalog_scout.discover()
                self.diagnostics['catalog_summary'] = {
                    'catalogs': len(self.catalog['catalogs']),
                    'resources': sum(c['rows'] for c in self.catalog['catalogs']),
                    'partial_failure': self.catalog['partial_failure'],
                    'errors': self.catalog['errors'],
                    'feed_eligible': False,
                }
                if self.catalog['partial_failure']:
                    self.diagnostics['partial_failure'] = True
            except Exception as exc:
                self.diagnostics.update(partial_failure=True, catalog_error=str(exc))
        if document_error is not None:
            raise document_error
        return items


class DeisCatalogScout:
    """Read the five public Ninja Tables URLs declared in the current homepage.

    Catalog periods and HTTP timestamps do not establish release dates. These
    resources support indicators/Trend/Benchmark and never enter the feed queue
    merely because a catalog or file was reachable.
    """
    PAGE = "https://deis.minsal.cl/"
    PURPOSES = {"Estadísticas": "indicator", "Datos Abiertos": "trend_benchmark_dataset",
                "Publicaciones e Infografías": "report_reference", "Estándares y normativas": "normative_reference",
                "Tableros DEIS": "indicator_dashboard"}

    @classmethod
    def surfaces_from_html(cls, html):
        import json
        from urllib.parse import parse_qs
        surfaces = []
        for match in re.finditer(r"window\['ninja_table_instance_\d+'\]\s*=\s*", html):
            table, _ = json.JSONDecoder().raw_decode(html[match.end():])
            title = table.get("title")
            if title not in cls.PURPOSES:
                continue
            url = table.get("init_config", {}).get("data_request_url", "")
            parsed = urlsplit(url)
            query = parse_qs(parsed.query)
            if (not official_deis_url(url) or parsed.hostname != "deis.minsal.cl"
                    or parsed.path != "/deisajax"
                    or query.get("action") != ["wp_ajax_ninja_tables_public_action"]
                    or query.get("target_action") != ["get-all-data"]
                    or query.get("table_id") != [str(table.get("table_id"))]):
                raise ValueError("DEIS public table URL does not match its declared identity")
            surfaces.append({"title": title, "table_id": str(table["table_id"]),
                             "url": url, "purpose": cls.PURPOSES[title]})
        if len(surfaces) != len(cls.PURPOSES) or len({x['title'] for x in surfaces}) != len(cls.PURPOSES):
            raise RuntimeError("DEIS homepage does not declare all five official catalogs")
        return surfaces

    @staticmethod
    def resources_from_json(payload, surface):
        if not isinstance(payload, list):
            raise ValueError("DEIS public table response must be a row list")
        resources = []
        for row in payload:
            if not isinstance(row, dict):
                raise ValueError("DEIS catalog row is not an object")
            # Ninja Tables' actual public response wraps cells under value;
            # options carries presentation classes, never publication metadata.
            row = row.get("value", row)
            if not isinstance(row, dict):
                raise ValueError("DEIS catalog cells are not an object")
            name, link = row.get("nombre"), row.get("ver")
            if not isinstance(name, str) or not isinstance(link, str) or not name.strip():
                continue
            parsed = urlsplit(link.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                continue
            resources.append({"source": "deis", "title": name.strip(), "url": link.strip(),
                              "catalog": surface["title"], "purpose": surface["purpose"],
                              "format": row.get("formato"), "tags": row.get("tags"),
                              "period_fields": {k: v for k, v in row.items() if k.startswith("filtro_")},
                              "publication_date": None, "feed_eligible": False,
                              "reason": "catalog_period_is_not_publication_date",
                              "publisher_linked_external_host": parsed.hostname not in DEIS_OFFICIAL_HOSTS})
        if not resources:
            raise RuntimeError("DEIS catalog has no usable resource rows")
        return resources

    def discover(self):
        import json
        from .public_source_transport import download_official
        surfaces = self.surfaces_from_html(_fetch_deis_html(self.PAGE))
        result = {"source": "deis", "homepage": self.PAGE, "catalogs": [],
                  "errors": [], "partial_failure": False,
                  "release_inventory_30_90": "not_applicable_to_undated_catalog_resources"}
        for surface in surfaces:
            try:
                capture = {}
                body, _ = download_official(surface["url"], "deis", capture_metadata=capture)
                resources = self.resources_from_json(json.loads(body), surface)
                result["catalogs"].append({**surface, "capture": capture, "resources": resources,
                                           "rows": len(resources)})
            except Exception as exc:
                from .public_source_evidence import failure_details
                result['partial_failure'] = True
                result['errors'].append({**surface, **failure_details(exc)})
        return result
