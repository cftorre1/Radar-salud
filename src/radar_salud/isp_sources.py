"""ISP public sources with publication dates bound to official evidence.

The current public website uses ispch.cl.  Upload directories, report periods,
and dates mentioned in document titles are never publication dates.
"""
from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .models import RawItem
from .public_source_evidence import chile_today
from .scouts import fetch_html

ISP_HOSTS = frozenset({"www.ispch.cl", "ispch.cl"})


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

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = {"cells": [], "links": []}
        elif self.row is not None and tag in {"td", "th"}:
            self.cell = []
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
            self.row["cells"].append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = self.cell = self.anchor = None


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
    PAGES = (PAGE, "https://ispch.cl/categorias-alertas/anamed/")
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
            fields = [cell for cell in row["cells"] if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]20\d{2}", cell)]
            day = publication_date(fields[0]) if len(fields) == 1 else None
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
                                               **_date_evidence("listing:fecha_publicacion", fields[0], day, base_url)}))
        if not items:
            raise RuntimeError("ANAMED alert listing has no verified publication rows")
        items.sort(key=lambda item: item.event_date or "", reverse=True)
        return items[:30]

    def discover(self):
        self.diagnostics = []
        self.partial_failure = False
        for page in self.PAGES:
            try:
                items = self.discover_from_html(fetch_html(page), page)
            except Exception as exc:
                self.partial_failure = True
                self.diagnostics.append({"channel": "ANAMED", "url": page,
                                         "status": "blocked", "error_type": type(exc).__name__,
                                         "error": str(exc)})
                continue
            self.diagnostics.append({"channel": "ANAMED", "url": page,
                                     "status": "discovered", "items": len(items)})
            return items
        raise RuntimeError("ISP ANAMED official listings unavailable: " +
                           "; ".join(f"{row['url']}: {row['error_type']}: {row['error']}" for row in self.diagnostics))
