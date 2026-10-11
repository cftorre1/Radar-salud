"""La Tercera news discovery, with publication evidence bound to the article.

The listing is a candidate inventory, not an editorial approval. In particular,
neither navigation dates nor dates mentioned in the story establish publication.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from .models import RawItem
from .scouts import fetch_html

HOSTS = {"www.latercera.com", "latercera.com"}
ARTICLE_PATH = re.compile(r"/(?:pulso|nacional)/noticia/[^/]+(?:/[A-Za-z0-9]{26})?/?")
LISTINGS = (
    "https://www.latercera.com/canal/pulso/",
    "https://www.latercera.com/canal/nacional/",
    "https://www.latercera.com/etiqueta/isapres/",
    "https://www.latercera.com/etiqueta/fonasa/",
    "https://www.latercera.com/etiqueta/clinicas/",
    "https://www.latercera.com/etiqueta/salud/",
)


def article_url(value, base=LISTINGS[0]):
    parsed = urlparse(urljoin(base, value or ""))
    if (parsed.scheme != "https" or parsed.netloc not in HOSTS
            or not ARTICLE_PATH.fullmatch(parsed.path)):
        return None
    return "https://www.latercera.com" + parsed.path.rstrip("/") + "/"


def health_anchor(text):
    return bool(re.search(
        r"\bsalud\b|cl[ií]nica|hospital|isapre|fonasa|prestador|"
        r"medicamento|farmac|aseguramiento|seguro de salud|"
        r"banm[eé]dica|bupa|redsalud|consalud|colmena|cruz blanca|"
        r"masvida|uc christus|listas? de espera|senior housing|"
        r"residencias? (?:para|de) adultos mayores|eleam",
        text or "", re.I))


def publication_day(value):
    """Use the calendar date exposed by the publisher's timestamp.

    La Tercera listings and article bylines can disagree by a day. Preserve the
    timestamp/offset; silently converting it to another timezone hides that gap.
    """
    try:
        if len(value) == 10:
            return date.fromisoformat(value).isoformat()
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return stamp.date().isoformat()
    except (ValueError, TypeError, AttributeError):
        return None


class _Article(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.metas = {}
        self.canonical = ""
        self.scripts = []
        self.script = None
        self.body = []
        self.paragraphs = []
        self.headline = []
        self.times = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            self.metas.setdefault(a.get("property") or a.get("name"), a.get("content", ""))
        if tag == "link" and "canonical" in (a.get("rel") or "").split():
            self.canonical = a.get("href", "")
        if tag in self.VOID:
            return
        classes = (a.get("class", "") + " " + a.get("id", "")).lower()
        parent = self.stack[-1] if self.stack else {}
        blocked = parent.get("blocked", False) or tag in ("nav", "aside", "footer", "style", "script", "noscript") or any(
            word in classes for word in ("related", "newsletter", "comments", "most-read", "latest-news"))
        body = parent.get("body", False) or a.get("itemprop") == "articleBody" or any(
            word in classes for word in ("body-chain", "article-body", "article__body"))
        in_article = parent.get("article", False) or tag == "article"
        self.stack.append(dict(tag=tag, blocked=blocked, body=body, article=in_article,
                               paragraph=parent.get("paragraph", False) or tag == "p",
                               heading=parent.get("heading", False) or tag == "h1"))
        if tag == "script" and a.get("type") == "application/ld+json":
            self.script = []
        if tag == "time" and in_article and not blocked and a.get("datetime"):
            self.times.append(a["datetime"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            self.scripts.append("".join(self.script))
            self.script = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
        if not self.stack or self.stack[-1]["blocked"]:
            return
        value = " ".join(data.split())
        if not value:
            return
        frame = self.stack[-1]
        if frame["heading"]:
            self.headline.append(value)
        if frame["body"]:
            self.body.append(value)
        elif frame["article"] and frame["paragraph"]:
            self.paragraphs.append(value)


def _nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from _nodes(item)
    elif isinstance(value, dict):
        yield value
        yield from _nodes(value.get("@graph", []))


def extract_article(html, expected_url):
    expected = article_url(expected_url)
    if not expected:
        raise ValueError("unexpected_article_host_or_path")
    parser = _Article()
    parser.feed(html)
    identity = parser.canonical or parser.metas.get("og:url")
    if not identity or article_url(identity, expected) != expected:
        raise ValueError("article_identity_mismatch")
    articles = []
    for script in parser.scripts:
        try:
            nodes = _nodes(json.loads(script))
            for node in nodes:
                types = node.get("@type", [])
                types = [types] if isinstance(types, str) else types
                if not any(t in ("NewsArticle", "Article", "ReportageNewsArticle") for t in types):
                    continue
                link = node.get("url") or node.get("mainEntityOfPage") or node.get("@id")
                if isinstance(link, dict):
                    link = link.get("@id")
                if link and article_url(link, expected) != expected:
                    continue
                articles.append(node)
        except (ValueError, TypeError):
            continue
    if len(articles) > 1:
        raise ValueError("ambiguous_article_metadata")
    node = articles[0] if articles else {}
    evidence = [("json_ld_datePublished", node.get("datePublished")),
                ("article_published_time", parser.metas.get("article:published_time"))]
    evidence.extend(("article_time", value) for value in parser.times)
    dates = [(kind, value, publication_day(value)) for kind, value in evidence if value]
    if not dates or any(not day for _, _, day in dates):
        raise ValueError("missing_or_invalid_publication_date")
    if len({day for _, _, day in dates}) != 1:
        raise ValueError("conflicting_publication_dates")
    date_source, timestamp, published = dates[0]
    if date.fromisoformat(published) > datetime.now(ZoneInfo("America/Santiago")).date():
        raise ValueError("future_publication_date")
    title = node.get("headline") or " ".join(parser.headline) or parser.metas.get("og:title", "")
    title = re.sub(r"\s+-\s+La Tercera$", "", " ".join(title.split()))
    body = " ".join(parser.body or parser.paragraphs)
    if not body and isinstance(node.get("articleBody"), str):
        body = " ".join(node["articleBody"].split())
    if len(title) < 18 or len(body) < 160:
        raise ValueError("incomplete_article_evidence")
    return title, body, dict(publication_date=published, publication_timestamp=timestamp,
                            publication_date_source=date_source, canonical_url=expected,
                            article_verified=True)


def discover_listing(html, base, detail_loader, audit, visited):
    from .beta_sources import _Links
    parser = _Links()
    parser.feed(html)
    links = {}
    for href, title in parser.links:
        url = article_url(href, base)
        if url and health_anchor(title):
            links.setdefault(url, title)
    out = []
    for url in links:
        if url in visited:
            continue
        visited.add(url)
        try:
            title, body, metadata = extract_article(detail_loader(url), url)
            if not health_anchor(title + " " + body):
                raise ValueError("no_health_anchor")
            metadata.update(discovered_from=base, page_text=body[:18000], market_role="media",
                            source_quality_gate="passed", captured_at=datetime.now(ZoneInfo("UTC")).isoformat())
            out.append(RawItem("pulso_latercera", title, url, "Pulso / La Tercera", "press_high_trust",
                               event_date=metadata["publication_date"], raw_text=body[:1800], metadata=metadata))
            audit.append(dict(url=url, listing=base, status="discovered", publication_date=metadata["publication_date"]))
        except Exception as exc:
            audit.append(dict(url=url, listing=base, status="detail_error", reason=str(exc), error_type=type(exc).__name__))
    return out


def discover_pulso(detail_loader=fetch_html, audit=None):
    audit = audit if audit is not None else []
    visited, out = set(), []
    for listing in LISTINGS:
        try:
            html = detail_loader(listing)
        except Exception as exc:
            audit.append(dict(listing=listing, status="listing_error", error_type=type(exc).__name__))
            continue
        out.extend(discover_listing(html, listing, detail_loader, audit, visited))
    if not out:
        raise RuntimeError("Pulso / La Tercera has no verified, dated health articles")
    return sorted(out, key=lambda item: item.event_date, reverse=True)
