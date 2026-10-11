"""FONASA discovery with explicit publication dates and transport diagnostics.

Parser regression fixtures are synthetic: they do not establish that a blocked
live endpoint has this HTML structure. No alternative route is enabled without
a successful official capture.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from .models import RawItem
from .public_source_transport import fetch_official_html


NEWS_HOSTS = frozenset(("www.fonasa.gob.cl", "fonasa.gob.cl"))
DATA_HOSTS = frozenset(("datosabiertos.fonasa.cl", "www.datosabiertos.fonasa.cl"))


def _official(url: str, hosts: frozenset[str]) -> bool:
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.netloc in hosts
                and not parsed.username and not parsed.password)
    except (ValueError, TypeError):
        return False


def _publication_date(value: str, today: date | None = None) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?", value.strip()
    ):
        return None
    try:
        parsed = (datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
                  if "T" in value else date.fromisoformat(value.strip()))
    except ValueError:
        return None
    today = today or datetime.now(ZoneInfo("America/Santiago")).date()
    return parsed.isoformat() if date(2000, 1, 1) <= parsed <= today else None


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.dates: list[tuple[str, str]] = []
        self.text: list[str] = []
        self.description = ""
        self._anchor: tuple[str, list[str]] | None = None
        self._scripts: list[str] = []
        self._script: list[str] | None = None
        self._hidden = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        tag = tag.lower()
        if tag in ("script", "style", "noscript"):
            self._hidden += 1
            if tag == "script" and attributes.get("type", "").lower() == "application/ld+json":
                self._script = []
        if tag == "meta":
            key = (attributes.get("property") or attributes.get("name")
                   or attributes.get("itemprop") or "").lower()
            value = attributes.get("content") or ""
            if key in ("article:published_time", "datepublished"):
                self.dates.append(("article:published_time" if key.startswith("article:") else "datePublished", value))
            if key in ("description", "og:description") and not self.description:
                self.description = " ".join(value.split())
        if tag == "a" and not self._hidden and attributes.get("href"):
            self._anchor = (attributes["href"], [])

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
        if not self._hidden:
            self.text.append(data)
            if self._anchor is not None:
                self._anchor[1].append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "a" and self._anchor is not None:
            self.links.append((self._anchor[0], " ".join("".join(self._anchor[1]).split())))
            self._anchor = None
        if tag == "script" and self._script is not None:
            self._scripts.append("".join(self._script))
            self._script = None
        if tag in ("script", "style", "noscript"):
            self._hidden = max(0, self._hidden - 1)


def publication_evidence_from_html(html: str, url: str, today: date | None = None) -> dict | None:
    """Ignore period/title/body/modified dates; reject invalid or conflicting dates."""
    if not _official(url, NEWS_HOSTS | DATA_HOSTS):
        return None
    page = _Page()
    page.feed(html)
    dates = list(page.dates)
    for script in page._scripts:
        try:
            payload = json.loads(script)
        except (ValueError, TypeError):
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get("@graph"), list):
                nodes = nodes + node["@graph"]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if not isinstance(types, list) or not set(types).intersection(("Article", "NewsArticle", "BlogPosting")):
                continue
            identity = node.get("url") or node.get("mainEntityOfPage") or node.get("@id")
            if isinstance(identity, dict):
                identity = identity.get("@id")
            if isinstance(identity, str) and urljoin(url, identity).split("#")[0] == url.split("#")[0]:
                if "datePublished" in node:
                    dates.append(("jsonld.datePublished", node["datePublished"]))
    normalized = [_publication_date(value, today) for _, value in dates]
    if not normalized or None in normalized or len(set(normalized)) != 1:
        return None
    kind, value = dates[0]
    return {"kind": kind, "value": value, "date": normalized[0], "url": url}


class FonasaDiscoveryError(RuntimeError):
    def __init__(self, message: str, diagnostics: list[dict]):
        super().__init__(message)
        self.diagnostics = diagnostics


def _failure(stage: str, url: str, exc: Exception, channel: str = "Noticias") -> dict:
    return {"stage": stage, "url": url, "channel": channel,
            "exception": type(exc).__name__, "message": str(exc),
            "http_status": getattr(exc, "code", None)}


class FonasaNewsScout:
    SOURCE_SLUG = "fonasa"
    SOURCE_NAME = "Fondo Nacional de Salud (FONASA)"
    SOURCE_TYPE = "official"
    PAGE = "https://www.fonasa.gob.cl/noticias/"

    def __init__(self, fetcher: Callable[[str], str] | None = None):
        self.fetcher = fetcher or (lambda url: fetch_official_html(url, self.SOURCE_SLUG))
        self.diagnostics: list[dict] = []

    def discover_from_html(self, html):
        page = _Page()
        page.feed(html)
        result = []
        seen = set()
        for href, title in page.links:
            try:
                url = urljoin(self.PAGE, href)
            except ValueError:
                continue
            if len(title) < 18 or not _official(url, NEWS_HOSTS):
                continue
            parsed = urlsplit(url)
            if not re.fullmatch(r"/noticias/[^/]+/?", parsed.path) or parsed.fragment or parsed.query or url in seen:
                continue
            seen.add(url)
            result.append(RawItem(self.SOURCE_SLUG, title, url, self.SOURCE_NAME, self.SOURCE_TYPE,
                                  metadata={"discovered_from": self.PAGE}))
        return result

    def discover(self):
        self.diagnostics = []
        try:
            items = self.discover_from_html(self.fetcher(self.PAGE))[:15]
        except Exception as exc:
            self.diagnostics.append(_failure("listing", self.PAGE, exc))
            raise FonasaDiscoveryError("FONASA newsroom listing unavailable", self.diagnostics) from exc
        if not items:
            self.diagnostics.append({"stage": "listing", "url": self.PAGE, "reason": "no_article_links"})
            raise FonasaDiscoveryError("FONASA newsroom listing has no verifiable article links", self.diagnostics)
        for item in items:
            try:
                html = self.fetcher(item.url)
                page = _Page()
                page.feed(html)
                body = " ".join(" ".join(page.text).split())
                evidence = publication_evidence_from_html(html, item.url)
                item.raw_text = page.description or body[:1800]
                item.metadata["page_text"] = body[:18000]
                if evidence:
                    item.event_date = evidence["date"]
                    item.metadata.update(publication_date_evidence=evidence, publication_date_source=evidence["kind"])
                self.diagnostics.append({"stage": "detail", "url": item.url,
                                         "publication_date_verified": bool(evidence)})
            except Exception as exc:
                self.diagnostics.append(_failure("detail", item.url, exc))
                raise FonasaDiscoveryError("FONASA newsroom detail unavailable", self.diagnostics) from exc
        return items


class FonasaDataHubScout:
    """Evaluate every hub, preserving a partial transport failure as failure.

    File titles, upload directories, report periods and dates elsewhere on the
    listing cannot establish a document's publication date. Document discovery
    stays undated until an item-bound official publication record is captured.
    """
    SOURCE_SLUG = "fonasa_datos_abiertos"
    SOURCE_NAME = "Fondo Nacional de Salud (FONASA)"
    SOURCE_TYPE = "official"
    PAGES = [
        ("Noticias", "https://datosabiertos.fonasa.cl/noticias/"),
        ("Biblioteca / Cuenta Pública", "https://datosabiertos.fonasa.cl/biblioteca-cuenta-publica/"),
        ("Boletines estadísticos", "https://datosabiertos.fonasa.cl/boletines-estadisticos/"),
        ("Análisis", "https://datosabiertos.fonasa.cl/analysis/"),
    ]
    HOSTS = tuple(sorted(DATA_HOSTS))

    def __init__(self, fetcher: Callable[[str], str] | None = None):
        self.fetcher = fetcher or (lambda url: fetch_official_html(url, self.SOURCE_SLUG))
        self.diagnostics: list[dict] = []

    def discover(self):
        self.diagnostics = []
        out = []
        seen = set()
        failures = []
        hubs = {urlsplit(url).path.rstrip("/") for _, url in self.PAGES}
        for channel, listing in self.PAGES:
            try:
                page = _Page()
                page.feed(self.fetcher(listing))
            except Exception as exc:
                diagnostic = _failure("listing", listing, exc, channel)
                self.diagnostics.append(diagnostic)
                failures.append(diagnostic)
                continue
            candidates = 0
            for href, title in page.links:
                try:
                    url = urljoin(listing, href)
                    parsed = urlsplit(url)
                except ValueError:
                    continue
                path = parsed.path.lower()
                if len(title) < 12 or not _official(url, DATA_HOSTS) or url in seen:
                    continue
                if parsed.fragment or parsed.query or not path.rstrip("/") or path.rstrip("/") in hubs:
                    continue
                if any(token in path for token in (
                    "/wp-admin", "/wp-login", "/author/", "/tag/", "/category/", "/feed", "/wp-json",
                    "/contacto", "/politica-de-privacidad", "/privacy-policy",
                )):
                    continue
                seen.add(url)
                candidates += 1
                item = RawItem(self.SOURCE_SLUG, title, url, self.SOURCE_NAME, self.SOURCE_TYPE,
                               metadata={"discovered_from": listing, "fonasa_channel": channel})
                if path.endswith((".pdf", ".xlsx", ".xls", ".csv")):
                    item.metadata["date_blocker"] = "document_has_no_item_bound_publication_date"
                else:
                    try:
                        html = self.fetcher(url)
                        detail = _Page()
                        detail.feed(html)
                        body = " ".join(" ".join(detail.text).split())
                        item.raw_text = detail.description or body[:1800]
                        item.metadata["page_text"] = body[:18000]
                        evidence = publication_evidence_from_html(html, url)
                        if evidence:
                            item.event_date = evidence["date"]
                            item.metadata.update(publication_date_evidence=evidence, publication_date_source=evidence["kind"])
                        self.diagnostics.append({"stage": "detail", "url": url, "channel": channel,
                                                 "publication_date_verified": bool(evidence)})
                    except Exception as exc:
                        diagnostic = _failure("detail", url, exc, channel)
                        self.diagnostics.append(diagnostic)
                        failures.append(diagnostic)
                        continue
                out.append(item)
            self.diagnostics.append({"stage": "listing", "url": listing,
                                     "channel": channel, "candidate_count": candidates})
        if failures:
            raise FonasaDiscoveryError(
                f"FONASA Datos Abiertos incomplete capture ({len(failures)} listing/detail failures)", self.diagnostics
            )
        if not out:
            raise FonasaDiscoveryError("FONASA Datos Abiertos has no verifiable publication links", self.diagnostics)
        return out[:80]
