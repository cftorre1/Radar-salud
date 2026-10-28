"""ISP public sources with publication dates bound to official evidence.

The publisher serves indexed official pages under ispch.gob.cl and ispch.cl.
Both exact HTTPS authorities are supported. Upload directories, report periods,
and dates mentioned in document titles are never publication dates.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .models import RawItem
from .public_source_evidence import chile_today
from .public_source_transport import fetch_official_html

ISP_HOSTS = frozenset({"www.ispch.cl", "ispch.cl", "www.ispch.gob.cl", "ispch.gob.cl"})


def fetch_html(url: str, source_slug: str = "isp_surveillance") -> str:
    return fetch_official_html(url, source_slug)


def official_isp_url(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.scheme == "https" and parsed.netloc in ISP_HOSTS
            and not parsed.username and not parsed.password)


def publication_date(value: str) -> str | None:
    """Parse an entire publication field, never an arbitrary body substring."""
    value = " ".join(value.split()).strip()
    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2})", value)
    if match:
        day, month, year = map(int, match.groups())
    else:
        match = re.fullmatch(r"(20\d{2})-(\d{2})-(\d{2})(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?", value)
        if match:
            if "T" in value:
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return None
            year, month, day = map(int, match.groups())
        else:
            match = re.fullmatch(r"(\d{1,2})\s+(?:de\s+)?([a-záéíóú]+),?\s+(?:de\s+)?(20\d{2})", value, re.I)
            months = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
                      "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
                      "septiembre": 9, "setiembre": 9, "octubre": 10,
                      "noviembre": 11, "diciembre": 12}
            if not match or match.group(2).lower() not in months:
                return None
            day, month, year = int(match.group(1)), months[match.group(2).lower()], int(match.group(3))
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    return parsed.isoformat() if parsed <= chile_today() else None


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = self.cell = self.anchor = None
        self.headers = []
        self.colspan = 1

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.headers = []
        elif tag == "tr":
            self.row = {"cells": [], "links": [], "is_header": False}
        elif self.row is not None and tag in {"td", "th"}:
            self.cell = []
            self.row["is_header"] |= tag == "th"
            try:
                self.colspan = min(20, max(1, int(dict(attrs).get("colspan", "1"))))
            except ValueError:
                self.colspan = 1
        elif self.row is not None and tag == "a":
            self.anchor = [dict(attrs).get("href"), []]

    def handle_data(self, value):
        if self.cell is not None:
            self.cell.append(value)
        if self.anchor is not None:
            self.anchor[1].append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            self.row["links"].append((self.anchor[0], " ".join(" ".join(self.anchor[1]).split())))
            self.anchor = None
        elif tag in {"td", "th"} and self.cell is not None:
            self.row["cells"].extend([" ".join(" ".join(self.cell).split())] * self.colspan)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row["is_header"]:
                self.headers = self.row["cells"][:]
            self.row["headers"] = self.headers[:]
            self.rows.append(self.row)
            self.row = self.cell = self.anchor = None


def _publication_cell(row):
    headers = row.get("headers", [])
    columns = [index for index, value in enumerate(headers)
               if value.casefold() == "fecha publicación"]
    if len(columns) != 1 or len(headers) != len(row["cells"]):
        return None
    value = row["cells"][columns[0]]
    day = publication_date(value)
    return (value, day) if day else None


def _listing_shape(html, parser, laboratory):
    """Structural fingerprint of a listing that yielded no rows.

    The 28-oct-2026 respiratory listing answered on four hosts but matched no
    row; only the bare message was kept. Record what the page *did* contain so
    the next run separates a markup change (e.g. "Semana" cells or document
    links outside a table, a renamed slug) from a script-rendered empty table.
    """
    rows = parser.rows
    hrefs = re.findall(r"""href=["']([^"']+)["']""", html)
    wanted = r"/boletin/" if laboratory else r"/documento/"
    links = [href for href in hrefs if re.search(wanted, href)]
    semana = re.findall(r"Semana\s*\d{1,2}[^<]{0,12}", html, re.I)
    headers = sorted({" / ".join(row.get("headers", [])) for row in rows if row.get("headers")})[:3]
    return (f" (bytes={len(html)}, tables={len(re.findall(r'<table', html, re.I))}, rows={len(rows)}, "
            f"headers={headers}, semana_texts={len(semana)} sample={semana[:2]}, "
            f"{wanted.strip('/')}_links={len(links)} sample={[href[:200] for href in links[:2]]})")


def _date_evidence(kind: str, value: str, day: str, url: str) -> dict:
    return {"publication_date_source": kind,
            "publication_date_evidence": {"kind": kind, "value": value,
                                          "date": day, "url": url}}


class IspAnamedAlertScout:
    """Discover dated alerts and notes from the official ANAMED row listing."""
    SOURCE_SLUG = "isp_anamed"
    SOURCE_NAME = "ISP / ANAMED"
    SOURCE_TYPE = "official"
    PAGE = "https://www.ispch.cl/categorias-alertas/anamed/"
    PAGES = (PAGE, "https://ispch.cl/categorias-alertas/anamed/",
             "https://www.ispch.gob.cl/categorias-alertas/anamed/",
             "https://ispch.gob.cl/categorias-alertas/anamed/")
    ATTACHMENT_LABELS = {"publicación isp", "alerta", "nota informativa"}

    def __init__(self):
        self.diagnostics = []
        self.partial_failure = False

    def discover_from_html(self, html: str, base_url: str | None = None):
        base_url = base_url or self.PAGE
        if not official_isp_url(base_url):
            raise ValueError("ANAMED listing must be an official HTTPS ISP URL")
        parser = _Rows()
        parser.feed(html)
        items, seen = [], set()
        for row in parser.rows:
            field = _publication_cell(row)
            day = field[1] if field else None
            body = " | ".join(row["cells"])
            if not day or not re.search(r"retiro del mercado|nota informativa|falsificad|seguridad|vigilancia de cosméticos", body, re.I):
                continue
            titles = [cell for cell in row["cells"] if len(cell) > 25
                      and cell.lower() not in self.ATTACHMENT_LABELS]
            if not titles:
                continue
            title = max(titles, key=len)
            for href, label in row["links"]:
                if not href or label.casefold() not in self.ATTACHMENT_LABELS:
                    continue
                url = urljoin(base_url, href)
                if (not official_isp_url(url) or not urlparse(url).path.lower().endswith(".pdf")
                        or url in seen):
                    continue
                seen.add(url)
                items.append(RawItem(self.SOURCE_SLUG, title[:300], url, self.SOURCE_NAME,
                                     self.SOURCE_TYPE, event_date=day,
                                     metadata={"discovered_from": base_url, "listing_text": body,
                                               "attachment_label": label,
                                               **_date_evidence("listing:fecha_publicacion", field[0], day, base_url)}))
        if not items:
            raise RuntimeError("ANAMED alert listing has no verified publication rows")
        items.sort(key=lambda item: item.event_date or "", reverse=True)
        return items[:30]

    def discover(self):
        self.diagnostics = []
        self.partial_failure = False
        last_error = None
        for page in self.PAGES:
            try:
                items = self.discover_from_html(fetch_html(page, self.SOURCE_SLUG), page)
            except Exception as exc:
                last_error = exc
                self.partial_failure = True
                self.diagnostics.append({"channel": "ANAMED", "url": page,
                                         "status": "blocked", "error_type": type(exc).__name__,
                                         "error": str(exc)})
                continue
            self.diagnostics.append({"channel": "ANAMED", "url": page,
                                     "status": "discovered", "items": len(items)})
            return items
        raise RuntimeError("ISP ANAMED official listings unavailable: " +
                           "; ".join(f"{row['url']}: {row['error_type']}: {row['error']}" for row in self.diagnostics)) from last_error


class _Document(HTMLParser):
    """Collect explicitly declared publication fields and official PDF anchors."""
    def __init__(self):
        super().__init__()
        self.publication_fields = []
        self.links = []
        self.anchor = None
        self._published_time = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and (attrs.get("property", "").lower() == "article:published_time"
                              or attrs.get("itemprop", "").lower() == "datepublished"):
            if attrs.get("content"):
                self.publication_fields.append(attrs["content"])
        elif tag == "time" and (attrs.get("itemprop", "").lower() == "datepublished"
                                or "published" in attrs.get("class", "").lower().split()):
            self._published_time = True
            if attrs.get("datetime"):
                self.publication_fields.append(attrs["datetime"])
                self._published_time = False
        elif tag == "a":
            self.anchor = [attrs.get("href"), []]

    def handle_data(self, value):
        if self.anchor is not None:
            self.anchor[1].append(value)
        if self._published_time:
            self.publication_fields.append(value.strip())

    def handle_endtag(self, tag):
        if tag == "time":
            self._published_time = False
        elif tag == "a" and self.anchor is not None:
            self.links.append((self.anchor[0], " ".join(" ".join(self.anchor[1]).split())))
            self.anchor = None

    def published(self):
        fields = [field for field in self.publication_fields if field.strip()]
        parsed = [publication_date(field) for field in fields]
        if not parsed or None in parsed or len(set(parsed)) != 1:
            return None
        return parsed[0], fields[0]


class IspSurveillanceScout:
    """Independently inspect laboratory listings and dated respiratory details.

    The year/week in respiratory tables is a report period.  A respiratory
    document needs an explicitly declared publication field on its detail page.
    The runtime never turns the dated PDF filename into publication evidence.
    """
    SOURCE_SLUG = "isp_surveillance"
    SOURCE_NAME = "Instituto de Salud Pública de Chile (ISP)"
    SOURCE_TYPE = "official"
    HOSTS = ISP_HOSTS
    RESPIRATORY_ARCHIVE = ("/biomedico/vigilancia-de-laboratorio/ambitos-de-vigilancia/"
                           "vigilancia-virus-respiratorios/informes-virus-respiratorios/")
    PAGES = [
        ("Boletines de vigilancia de laboratorios", "https://www.ispch.cl/boletin/"),
        ("Vigilancia de virus respiratorios", "https://www.ispch.cl" + RESPIRATORY_ARCHIVE),
    ]

    def __init__(self):
        self.diagnostics = []
        self.partial_failure = False

    def discover_from_html(self, html: str, base_url: str, channel: str):
        if not official_isp_url(base_url):
            raise ValueError("ISP surveillance listing must be official HTTPS")
        parser = _Rows()
        parser.feed(html)
        items, seen = [], set()
        laboratory = "/boletin/" in urlparse(base_url).path
        for row in parser.rows:
            field = _publication_cell(row)
            if laboratory:
                if not field:
                    continue
                titles = [cell for cell in row["cells"] if len(cell) > 15
                          and cell != field[0]]
            else:
                # This is a coverage-period label, deliberately not a date.
                titles = [field for field in row["cells"]
                          if re.fullmatch(r"Semana\s+\d{1,2},?\s+20\d{2}", field, re.I)]
            if not titles:
                continue
            title = max(titles, key=len)
            for href, label in row["links"]:
                if not href:
                    continue
                url = urljoin(base_url, href)
                if not official_isp_url(url) or url in seen:
                    continue
                path = urlparse(url).path
                expected = (re.fullmatch(r"/boletin/[^/]+/?", path) if laboratory else
                            re.fullmatch(r"/documento/semana-\d{1,2}-20\d{2}/?", path))
                if not expected and not (laboratory and path.lower().endswith(".pdf")):
                    continue
                metadata = {"discovered_from": base_url, "isp_channel": channel,
                            "listing_text": " | ".join(row["cells"])}
                day = field[1] if laboratory else None
                if laboratory:
                    metadata.update(_date_evidence("listing:fecha_publicacion", field[0], day, base_url))
                seen.add(url)
                items.append(RawItem(self.SOURCE_SLUG, title, url, self.SOURCE_NAME,
                                     self.SOURCE_TYPE, event_date=day, metadata=metadata))
        if not items:
            raise RuntimeError(f"ISP {channel} listing has no verified document rows"
                               + _listing_shape(html, parser, laboratory))
        return items[:20]

    def document_from_html(self, item: RawItem, html: str):
        """Resolve one official PDF, preserving its detail publication evidence."""
        if not official_isp_url(item.url):
            raise ValueError("ISP detail must be official HTTPS")
        parser = _Document()
        parser.feed(html)
        published = parser.published()
        if parser.publication_fields and not published:
            raise RuntimeError("ISP detail without explicit verified publication date")
        if item.event_date:
            if published and published[0] != item.event_date:
                raise RuntimeError("ISP listing/detail publication dates disagree")
        elif published:
            item.event_date = published[0]
            item.metadata.update(_date_evidence("detail:published_time", published[1], item.event_date, item.url))
        else:
            raise RuntimeError("ISP detail without explicit verified publication date")
        pdfs = {}
        for href, label in parser.links:
            if not href:
                continue
            url = urljoin(item.url, href)
            parsed = urlparse(url)
            if (official_isp_url(url) and parsed.path.lower().endswith(".pdf")
                    and parsed.path.startswith(("/wp-content/uploads/", "/sites/default/files/"))):
                pdfs[url] = label
        if len(pdfs) != 1:
            raise RuntimeError("ISP detail must identify exactly one official PDF")
        item.metadata["document_detail_url"] = item.url
        item.metadata["publication_detail_url"] = item.url
        item.url, label = next(iter(pdfs.items()))
        item.metadata["publication_document_url"] = item.url
        item.metadata["publication_document_link_evidence"] = {
            "detail_url": item.metadata["publication_detail_url"],
            "document_url": item.url, "anchor_text": label}
        item.metadata["document_link_text"] = label
        return item

    def discover(self):
        self.diagnostics = []
        self.partial_failure = False
        items, seen = [], set()
        last_error = None
        # Request the explicit current-year archive; the unfiltered archive can
        # serve an older snapshot. The query year is never a publication date.
        pages = [self.PAGES[0], (self.PAGES[1][0], self.PAGES[1][1] + f"?y={chile_today().year}")]
        for channel, primary in pages:
            candidates = []
            for page in (primary,
                         primary.replace("https://www.ispch.cl/", "https://ispch.cl/"),
                         primary.replace("https://www.ispch.cl/", "https://www.ispch.gob.cl/"),
                         primary.replace("https://www.ispch.cl/", "https://ispch.gob.cl/")):
                try:
                    candidates = self.discover_from_html(fetch_html(page, self.SOURCE_SLUG), page, channel)
                except Exception as exc:
                    last_error = exc
                    self.partial_failure = True
                    self.diagnostics.append({"channel": channel, "url": page, "status": "blocked",
                                             "error_type": type(exc).__name__, "error": str(exc)})
                    continue
                self.diagnostics.append({"channel": channel, "url": page,
                                         "status": "listing_discovered", "items": len(candidates)})
                break
            for item in candidates:
                detail_url = item.url
                try:
                    if not urlparse(item.url).path.lower().endswith(".pdf"):
                        item = self.document_from_html(item, fetch_html(item.url, self.SOURCE_SLUG))
                    if not item.event_date:
                        raise RuntimeError("ISP document without publication evidence")
                except Exception as exc:
                    last_error = exc
                    self.partial_failure = True
                    self.diagnostics.append({"channel": channel, "url": detail_url, "status": "blocked",
                                             "error_type": type(exc).__name__, "error": str(exc)})
                    continue
                if item.url not in seen:
                    seen.add(item.url)
                    items.append(item)
            count = sum(item.metadata["isp_channel"] == channel for item in items)
            self.diagnostics.append({"channel": channel, "url": primary,
                                     "status": "discovered" if count else "blocked", "items": count})
        if not items:
            errors = [f"{row['url']}: {row['error_type']}: {row['error']}"
                      for row in self.diagnostics if row.get("error_type")]
            raise RuntimeError("ISP surveillance has no verified dated official documents: " +
                               "; ".join(errors)) from last_error
        items.sort(key=lambda item: item.event_date or "", reverse=True)
        return items
