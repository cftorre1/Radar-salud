from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from .models import RawItem


class _AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            text = " ".join("".join(self._text).split())
            self.links.append((self._href, text))
            self._href = None
            self._text = []


def fetch_html(url: str, timeout: int = 20) -> str:
    # Public ACHS links contain Unicode in their original slug. Encode the URI
    # for HTTP transport without changing its identity or escaping existing %.
    req = Request(quote(url,safe=':/?&=%+#;,@!$()*[]'), headers={"User-Agent": "RadarSaludBot/0.1 (+public-source-monitor)"})
    with urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _fingerprint(source_slug: str, url: str, title: str) -> str:
    base = f"{source_slug}|{url}|{title}".encode("utf-8")
    return hashlib.sha256(base).hexdigest()


class SeenStore:
    """Tiny JSON-backed dedup store for V0. Replace with Postgres in V1."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._seen = set(json.loads(self.path.read_text(encoding="utf-8")))
        else:
            self._seen = set()

    def is_seen(self, fp: str) -> bool:
        return fp in self._seen

    def add_many(self, fps: Iterable[str]) -> None:
        self._seen.update(fps)
        from .pending_queue import atomic_json
        atomic_json(self.path, sorted(self._seen))


_LISTING_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")
# Series the regulator updates in place every month/quarter under one URL.
_ROLLING = re.compile(r"\b(mensual|trimestral|semanal)\b.*\ba[ñn]o\s+20\d{2}\s*$", re.I)


def rolling_statistic(title: str) -> bool:
    return bool(_ROLLING.search(" ".join(str(title or "").split())))


class _DatedAnchorParser(_AnchorParser):
    """Anchors in document order, each with the last listing date seen before it."""

    def __init__(self):
        super().__init__()
        self._last_date = None
        self.links = []

    def handle_data(self, data):
        super().handle_data(data)
        if self._href is None:
            m = _LISTING_DATE.search(data)
            if m:
                day, month, year = (int(x) for x in m.groups())
                try:
                    from datetime import date as _d
                    self._last_date = _d(year, month, day).isoformat()
                except ValueError:
                    pass

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            text = " ".join("".join(self._text).split())
            href = self._href
            self._href = None
            self._text = []
            dated = self._last_date
            if "/biblioteca-digital/" in (href or "") and "/tax-biblioteca-digital/" not in (href or "") and text:
                # A date belongs to one row: consume it at the row's title link.
                if text and "descargar" not in text.lower():
                    self._last_date = None
                self.links.append((href, text, dated))
            else:
                self.links.append((href, text, None))


class SuperintendenciaStatsScout:
    """V0 scout for Superintendencia de Salud statistics listing pages.

    It deliberately discovers publication detail pages first. File downloads are
    handled later by the Extractor so Scout remains small and testable.
    """

    SOURCE_SLUG = "superintendencia_salud"
    SOURCE_NAME = "Superintendencia de Salud"
    SOURCE_TYPE = "official"
    DEFAULT_URL = "https://www.superdesalud.gob.cl/tax-biblioteca-digital/estadisticas-3724/"

    # Publication detail URLs consistently live under /biblioteca-digital/.
    DETAIL_RE = re.compile(r"/biblioteca-digital/", re.I)

    def discover_from_html(self, html: str, base_url: Optional[str] = None) -> List[RawItem]:
        """Detail pages with the listing's own "Fecha de publicación".

        Rows (table cells or stacked blocks) show the date before the linked
        title. Rolling series ("Estadística Mensual ... año 2026") keep their URL
        and are re-dated by the regulator on each monthly update, so the listing
        date is also the release identity of that update (``release_key``).
        """
        base_url = base_url or self.DEFAULT_URL
        parser = _DatedAnchorParser()
        parser.feed(html)

        items = []
        dedup = set()
        for href, text, listed in parser.links:
            if not href or not text:
                continue
            absolute = urljoin(base_url, href)
            if not self.DETAIL_RE.search(absolute):
                continue
            # Ignore taxonomy/navigation pages masquerading as biblioteca links.
            if "/tax-biblioteca-digital/" in absolute:
                continue
            if absolute in dedup:
                continue
            dedup.add(absolute)
            metadata = {"discovered_from": base_url}
            if listed:
                metadata.update(listing_publication_date=listed, event_date_basis="listing_publication")
                if rolling_statistic(text):
                    metadata["release_key"] = listed
            items.append(
                RawItem(
                    source_slug=self.SOURCE_SLUG,
                    title=text,
                    url=absolute,
                    source_name=self.SOURCE_NAME,
                    source_type=self.SOURCE_TYPE,
                    event_date=listed,
                    raw_text="",
                    metadata=metadata,
                )
            )
        return items

    # Dirección 12-nov-2026: the "Publicaciones" branch of the Biblioteca digital (documentos metodológicos such as
    # ICSA/IRCI, documentos de trabajo, ...) uses the same dated listing and /biblioteca-digital/ detail pages. Its
    # sub-listings are read from the hub's menu, so a new collection is picked up without a code change.
    PUBLICATIONS_URL = "https://www.superdesalud.gob.cl/tax-biblioteca-digital/publicaciones-6509/"
    PUBLICATION_LISTINGS = (
        "https://www.superdesalud.gob.cl/tax-biblioteca-digital/publicaciones-6509/documentos-metodologicos-7455/",
    )
    SUBLISTING_RE = re.compile(r"/tax-biblioteca-digital/publicaciones-6509/([a-z0-9-]+?)-\d+/?$", re.I)
    MAX_PAGES = 8  # 51 documentos metodológicos at 10 per page on 12-nov-2026; the cap bounds a runaway loop.

    def publication_listings(self, html: str, base_url: Optional[str] = None) -> List[str]:
        base_url = base_url or self.PUBLICATIONS_URL
        parser = _AnchorParser()
        parser.feed(html)
        out = []
        for href, _text in parser.links:
            absolute = urljoin(base_url, href or "").split("#")[0].split("?")[0]
            if self.SUBLISTING_RE.search(absolute) and "/page/" not in absolute and absolute not in out:
                out.append(absolute if absolute.endswith("/") else absolute + "/")
        return out

    @staticmethod
    def next_page(html: str, page_url: str) -> Optional[str]:
        """The next page of the same listing (WordPress ``/page/N/``), or None."""
        base = re.sub(r"page/\d+/?$", "", page_url.split("?")[0])
        if not base.endswith("/"):
            base += "/"
        current = re.search(r"/page/(\d+)/?$", page_url.split("?")[0])
        wanted = (int(current.group(1)) if current else 1) + 1
        parser = _AnchorParser()
        parser.feed(html)
        for href, _text in parser.links:
            absolute = urljoin(page_url, href or "").split("#")[0]
            m = re.search(r"/page/(\d+)/?(?:\?.*)?$", absolute)
            if m and int(m.group(1)) == wanted and absolute.split("?")[0].startswith(base):
                return absolute
        return None

    @classmethod
    def collection(cls, listing_url: str) -> str:
        m = cls.SUBLISTING_RE.search(listing_url)
        return m.group(1).lower() if m else "publicaciones"

    def discover_publications(self, fetch=None) -> List[RawItem]:
        """Detail pages from the Publicaciones hub and each of its sub-listings, all pages.

        A failing listing is recorded in ``publication_errors`` and skipped: it never blocks the statistics
        listing or the other collections."""
        fetch = fetch or fetch_html
        self.publication_errors = []
        listings = list(self.PUBLICATION_LISTINGS)
        try:
            hub = fetch(self.PUBLICATIONS_URL)
        except Exception as exc:  # noqa: BLE001 - network/HTTP errors are reported, not raised
            self.publication_errors.append((self.PUBLICATIONS_URL, type(exc).__name__))
            hub = None
        items: List[RawItem] = []
        if hub is not None:
            listings += [u for u in self.publication_listings(hub, self.PUBLICATIONS_URL) if u not in listings]
            for raw in self.discover_from_html(hub, self.PUBLICATIONS_URL):
                raw.metadata["collection"] = "publicaciones"
                items.append(raw)
        for listing in listings:
            page_url, pages = listing, 0
            while page_url and pages < self.MAX_PAGES:
                try:
                    html = fetch(page_url)
                except Exception as exc:  # noqa: BLE001
                    self.publication_errors.append((page_url, type(exc).__name__))
                    break
                for raw in self.discover_from_html(html, page_url):
                    raw.metadata["collection"] = self.collection(listing)
                    items.append(raw)
                pages += 1
                page_url = self.next_page(html, page_url)
        return items

    def discover(self, url: Optional[str] = None) -> List[RawItem]:
        target = url or self.DEFAULT_URL
        items = self.discover_from_html(fetch_html(target), target)
        if url is None:
            seen = {raw.url for raw in items}
            # A collection page (e.g. documentos metodológicos) wins over the hub for the same document.
            extra = {}
            for raw in self.discover_publications():
                if raw.url in seen:
                    continue
                if raw.url not in extra or extra[raw.url].metadata.get("collection") == "publicaciones":
                    extra[raw.url] = raw
            items += list(extra.values())
        return items

    def discover_new(self, store: SeenStore, url: Optional[str] = None) -> List[RawItem]:
        items = self.discover(url)
        new_items, new_fps = [], []
        for item in items:
            fp = _fingerprint(item.source_slug, item.url, item.title)
            if not store.is_seen(fp):
                new_items.append(item)
                new_fps.append(fp)
        store.add_many(new_fps)
        return new_items


def save_raw_items(items: List[RawItem], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([asdict(x) for x in items], ensure_ascii=False, indent=2), encoding="utf-8")


class SusesoScout:
    """Discovery scout for public SUSESO publication/statistics pages.

    It accepts any SUSESO listing page and extracts public article/detail pages.
    Restricted/login systems are intentionally ignored.
    """

    SOURCE_SLUG = "suseso"
    SOURCE_NAME = "SUSESO"
    SOURCE_TYPE = "official"
    DEFAULT_URL = "https://www.suseso.cl/607/w3-channel.html"
    DETAIL_RE = re.compile(r"suseso\.cl/(?:607|609)/(?:w3-article-|w3-propertyvalue-|w3-multipropertyvalues-|articles-)", re.I)

    def discover_from_html(self, html: str, base_url: Optional[str] = None) -> List[RawItem]:
        base_url = base_url or self.DEFAULT_URL
        parser = _AnchorParser()
        parser.feed(html)
        items: List[RawItem] = []
        seen_urls = set()
        for href, text in parser.links:
            if not href or not text:
                continue
            absolute = urljoin(base_url, href)
            if not self.DETAIL_RE.search(absolute):
                continue
            if any(x in absolute.lower() for x in ("/login", "istas.suseso", "sisesat.suseso", "gris.suseso")):
                continue
            if absolute in seen_urls:
                continue
            seen_urls.add(absolute)
            items.append(RawItem(
                source_slug=self.SOURCE_SLUG,
                title=text,
                url=absolute,
                source_name=self.SOURCE_NAME,
                source_type=self.SOURCE_TYPE,
                raw_text="",
                metadata={"discovered_from": base_url},
            ))
        return items

    def discover(self, url: Optional[str] = None) -> List[RawItem]:
        target = url or self.DEFAULT_URL
        return self.discover_from_html(fetch_html(target), target)

    def discover_new(self, store: SeenStore, url: Optional[str] = None) -> List[RawItem]:
        items = self.discover(url)
        new_items, new_fps = [], []
        for item in items:
            fp = _fingerprint(item.source_slug, item.url, item.title)
            if not store.is_seen(fp):
                new_items.append(item)
                new_fps.append(fp)
        store.add_many(new_fps)
        return new_items

class MinsalNewsScout:
    """Scout #4 for public MINSAL news pages."""
    SOURCE_SLUG = "minsal"
    SOURCE_NAME = "Ministerio de Salud"
    SOURCE_TYPE = "official"
    DEFAULT_URL = "https://www.minsal.cl/category/noticias/"

    def discover_from_html(self, html: str, base_url: Optional[str] = None) -> List[RawItem]:
        base_url = base_url or self.DEFAULT_URL
        parser = _AnchorParser(); parser.feed(html)
        items: List[RawItem] = []; seen_urls=set()
        from .source_urls import minsal_article_url
        for href,text in parser.links:
            if not href or not text: continue
            # Dirección 28-oct-2026: whitespace/%20 tails, minsal.cl without www,
            # tracking params, ?p= shortlinks, archives and retired portal paths
            # produced dead "fuente original" links. Only canonical slugs pass.
            absolute=minsal_article_url(href,base_url)
            if not absolute: continue
            if "/wp-content/" in absolute: continue
            if len(text) < 20 or absolute in seen_urls: continue
            seen_urls.add(absolute)
            items.append(RawItem(self.SOURCE_SLUG,text,absolute,self.SOURCE_NAME,self.SOURCE_TYPE,raw_text="",metadata={"discovered_from":base_url}))
        return items

    def discover(self, url: Optional[str] = None) -> List[RawItem]:
        # Timeouts since 27-oct-2026: retry with a longer timeout and backoff before failing.
        import time
        target=url or self.DEFAULT_URL
        last=None
        for attempt in range(3):
            try:
                html=fetch_html(target, timeout=45)
            except (OSError, TimeoutError) as exc:  # URLError/HTTPError are OSError; parse errors are not retried
                last=exc
                if attempt<2:time.sleep(5*(2**attempt))
                continue
            return self.discover_from_html(html,target)
        raise last

    def discover_new(self, store: SeenStore, url: Optional[str] = None) -> List[RawItem]:
        items=self.discover(url); new_items=[]; fps=[]
        for item in items:
            fp=_fingerprint(item.source_slug,item.url,item.title)
            if not store.is_seen(fp): new_items.append(item); fps.append(fp)
        store.add_many(fps); return new_items
