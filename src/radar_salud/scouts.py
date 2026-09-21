from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urljoin
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
    req = Request(url, headers={"User-Agent": "RadarSaludBot/0.1 (+public-source-monitor)"})
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
        self.path.write_text(json.dumps(sorted(self._seen), ensure_ascii=False, indent=2), encoding="utf-8")


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
        base_url = base_url or self.DEFAULT_URL
        parser = _AnchorParser()
        parser.feed(html)

        items = []
        dedup = set()
        for href, text in parser.links:
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
            items.append(
                RawItem(
                    source_slug=self.SOURCE_SLUG,
                    title=text,
                    url=absolute,
                    source_name=self.SOURCE_NAME,
                    source_type=self.SOURCE_TYPE,
                    raw_text="",
                    metadata={"discovered_from": base_url},
                )
            )
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
        for href,text in parser.links:
            if not href or not text: continue
            absolute=urljoin(base_url,href)
            if not absolute.startswith("https://www.minsal.cl/"): continue
            if any(x in absolute for x in ("/category/","/page/","/author/","/tag/","wp-content")): continue
            if absolute.rstrip('/') == "https://www.minsal.cl": continue
            if len(text) < 20 or absolute in seen_urls: continue
            seen_urls.add(absolute)
            items.append(RawItem(self.SOURCE_SLUG,text,absolute,self.SOURCE_NAME,self.SOURCE_TYPE,raw_text="",metadata={"discovered_from":base_url}))
        return items

    def discover(self, url: Optional[str] = None) -> List[RawItem]:
        target=url or self.DEFAULT_URL
        return self.discover_from_html(fetch_html(target),target)

    def discover_new(self, store: SeenStore, url: Optional[str] = None) -> List[RawItem]:
        items=self.discover(url); new_items=[]; fps=[]
        for item in items:
            fp=_fingerprint(item.source_slug,item.url,item.title)
            if not store.is_seen(fp): new_items.append(item); fps.append(fp)
        store.add_many(fps); return new_items
