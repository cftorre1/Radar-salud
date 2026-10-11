"""La Tercera news discovery, with publication evidence bound to the article.

The listing is a candidate inventory, not an editorial approval. In particular,
neither navigation dates nor dates mentioned in the story establish publication.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

from .models import RawItem
from .scouts import fetch_html

HOSTS = {"www.latercera.com", "latercera.com"}
ARTICLE_PATH = re.compile(r"/[a-z0-9-]+/noticia/[^/]+(?:/[A-Za-z0-9]{26})?/?")
EXCLUDED_SECTIONS = {"opinion", "editorial", "columnas", "cartas-al-director"}
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
            or not ARTICLE_PATH.fullmatch(parsed.path)
            or parsed.path.split('/')[1] in EXCLUDED_SECTIONS):
        return None
    return "https://www.latercera.com" + parsed.path.rstrip("/") + "/"


def health_anchor(text):
    return bool(re.search(
        r"\bsalud\b|cl[ií]nica|hospital|isapre|fonasa|prestador|"
        r"medicamento|farmac|aseguramiento|seguro de salud|"
        r"banm[eé]dica|bupa|redsalud|consalud|colmena|cruz blanca|"
        r"masvida|uc christus|listas? de espera|senior housing|"
        r"residencias? (?:para|de) adultos mayores|eleam|"
        r"vacun|c[aá]ncer|oncolog|sanitari|atenci[oó]n primaria|"
        r"epidemi|trasplante|discapacidad|ley ricarte soto|cenabast|"
        r"insulina|diabetes|compin|licencias m[eé]dicas|ficha cl[ií]nica",
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
        self.byline_dates = []

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
                               heading=parent.get("heading", False) or tag == "h1",
                               byline_date=parent.get("byline_date", False) or (tag == "time" and "byline" in classes)))
        if tag == "script" and a.get("type") == "application/ld+json":
            self.script = []
        if (tag == "time" and in_article and not blocked and a.get("datetime")
                and a.get("itemprop") != "dateModified"):
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
        if frame["byline_date"]:
            self.byline_dates.append(value)
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


_SPANISH_MONTHS = {name: index for index, name in enumerate(
    ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"), 1)}


def _visible_byline_day(parts):
    text = " ".join(parts).lower()
    match = re.search(r"\b(\d{1,2})\s+(?:de\s+)?(" + "|".join(_SPANISH_MONTHS) + r")\s+(?:de\s+)?(\d{4})\b", text)
    if not match:
        return None
    try:
        return date(int(match[3]), _SPANISH_MONTHS[match[2]], int(match[1])).isoformat()
    except ValueError:
        raise ValueError("invalid_visible_publication_date")


def _publisher_day(value):
    if len(value) == 10:
        return publication_day(value)
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        return None
    return stamp.astimezone(ZoneInfo("America/Santiago")).date().isoformat()


class ExcludedArticle(ValueError):
    """An explicit publisher section exclusion with verified primary identity/date."""
    def __init__(self, reason, title, body, metadata):
        super().__init__(reason)
        self.title, self.body, self.metadata = title, body, metadata


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
                if not link or article_url(link, expected) != expected:
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
    visible_day = _visible_byline_day(parser.byline_dates)
    publisher_dates = [(kind, value, _publisher_day(value)) for kind, value, _ in dates]
    if len({day for _, _, day in publisher_dates}) != 1 or (
            visible_day and visible_day != publisher_dates[0][2]):
        raise ValueError("conflicting_publication_dates")
    date_source, timestamp, published = publisher_dates[0]
    if visible_day:
        published, date_source = visible_day, "visible_article_byline"
    now = datetime.now(ZoneInfo("UTC"))
    for _, value, _ in dates:
        if len(value) == 10:
            if date.fromisoformat(value) > now.astimezone(ZoneInfo("America/Santiago")).date():
                raise ValueError("future_publication_date")
        elif datetime.fromisoformat(value.replace("Z", "+00:00")) > now:
            raise ValueError("future_publication_date")
    title = node.get("headline") or " ".join(parser.headline) or parser.metas.get("og:title", "")
    title = re.sub(r"\s+-\s+La Tercera$", "", " ".join(title.split()))
    body = " ".join(parser.body or parser.paragraphs)
    # The original publisher emits its primary story in URL-bound NewsArticle
    # articleBody. Prefer it over broad HTML wrappers containing captions/tags.
    if isinstance(node.get("articleBody"), str) and len(node["articleBody"].strip()) >= 160:
        body = " ".join(node["articleBody"].split())
    section = node.get("articleSection") or parser.metas.get("article:section") or expected.split('/')[3]
    metadata = dict(section=section, keywords=node.get("keywords", []),
                            description=node.get("description", ""),
                            body_source="url_bound_json_ld_articleBody" if node.get("articleBody") else "article_html",
                            publication_date=published, publication_timestamp=timestamp,
                            publication_date_source=date_source, visible_publication_date=visible_day,
                            publication_evidence=[dict(source=kind, timestamp=value, publisher_day=day) for kind, value, day in publisher_dates], canonical_url=expected,
                            article_verified=True)
    if re.search(r"opini[oó]n|editorial|columna", str(section), re.I):
        raise ExcludedArticle("excluded_opinion_content", title, body, metadata)
    if len(title) < 18 or len(body) < 160:
        raise ValueError("incomplete_article_evidence")
    return title, body, metadata


def discover_listing(html, base, detail_loader, audit, visited):
    from .beta_sources import _Links
    parser = _Links()
    parser.feed(html)
    links = {}
    for href, title in parser.links:
        url = article_url(href, base)
        if url:
            links.setdefault(url, title)
    out = []
    for url in links:
        if url in visited:
            continue
        visited.add(url)
        try:
            title, body, metadata = extract_article(detail_loader(url), url)
            if not health_anchor(title + " " + body):
                audit.append(dict(url=url, listing=base, status="excluded", reason="no_health_anchor",
                                  publication_date=metadata["publication_date"], section=metadata["section"]))
                continue
            metadata.update(discovered_from=base, page_text=body[:18000], market_role="media",
                            source_quality_gate="passed", captured_at=datetime.now(ZoneInfo("UTC")).isoformat())
            out.append(RawItem("pulso_latercera", title, url, "Pulso / La Tercera", "press_high_trust",
                               event_date=metadata["publication_date"], raw_text=body[:1800], metadata=metadata))
            audit.append(dict(url=url, listing=base, status="discovered", section=metadata["section"],
                              publication_date=metadata["publication_date"]))
        except ExcludedArticle as exc:
            audit.append(dict(url=url, listing=base, status="excluded", reason=str(exc),
                              publication_date=exc.metadata["publication_date"], section=exc.metadata["section"]))
        except Exception as exc:
            audit.append(dict(url=url, listing=base, status="detail_error", reason=str(exc), error_type=type(exc).__name__))
    return out


SITEMAP_INDEX = "https://www.latercera.com/arc/outboundfeeds/sitemap-index/?outputType=xml"
SITEMAP_PAGE = "https://www.latercera.com/arc/outboundfeeds/sitemap/?outputType=xml"
_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"
_CACHE_VERSION = 1


def _archive_url(value):
    """Archive links must stay on the publisher's public XML endpoint."""
    parsed = urlparse(value or "")
    if (parsed.scheme != "https" or parsed.netloc not in HOSTS
            or parsed.path != "/arc/outboundfeeds/sitemap/"):
        return None
    query = parse_qs(parsed.query)
    if query.get("outputType") != ["xml"] or set(query) - {"outputType", "from"}:
        return None
    offset = query.get("from", ["0"])
    if len(offset) != 1 or not offset[0].isdigit():
        return None
    return SITEMAP_PAGE + ("&from=" + str(int(offset[0])) if int(offset[0]) else "")


def parse_sitemap(html):
    """Read primary <url>/<loc>, never an image or nested news location."""
    root = ET.fromstring(html)
    namespace = "{" + _SITEMAP_NS + "}"
    if root.tag == namespace + "sitemapindex":
        entries = []
        for node in root.findall(namespace + "sitemap"):
            value = node.findtext(namespace + "loc", "")
            url = _archive_url(value)
            if not url:
                raise ValueError("unexpected_sitemap_child_host_or_path")
            entries.append(dict(url=url, lastmod=node.findtext(namespace + "lastmod", "")))
        if not entries:
            raise ValueError("empty_sitemap_index")
        return "index", entries
    if root.tag != namespace + "urlset":
        raise ValueError("unexpected_sitemap_document")
    entries = []
    for node in root.findall(namespace + "url"):
        entries.append(dict(url=node.findtext(namespace + "loc", ""),
                            lastmod=node.findtext(namespace + "lastmod", ""),
                            archive_publication_timestamp=node.findtext(
                                "{" + _NEWS_NS + "}news/{" + _NEWS_NS + "}publication_date", "")))
    return "urls", entries


def health_topics(text):
    patterns = {
        "insurance": r"isapre|fonasa|aseguramiento|seguros? de salud|cotizantes?",
        "providers": r"cl[ií]nica|hospital|prestador|redsalud|uc christus|eleam|senior housing",
        "investment_ma": r"inversi[oó]n|adquisi|compra|fusi[oó]n|capital|patria|linzor",
        "financing": r"financi|deuda|presupuesto|recursos|gasto|bono|tarifa",
        "regulation": r"regul|ley|superintendencia|fne|fallo|suprema|decreto|congreso",
        "waiting_lists": r"listas? de espera|tiempos? de espera|oncolog",
        "competition": r"competen|mercado|ventas|afiliados?|cotizantes?|cobertura",
        "public_health": r"sanitari|vacun|c[aá]ncer|epidemi|medicamento|farmac|diabetes",
    }
    return [topic for topic, pattern in patterns.items() if re.search(pattern, text or "", re.I)] or ["health_general"]


class _FeedText(HTMLParser):
    """Full story RSS markup, with scripts removed but no topic/title gate."""
    def __init__(self):
        super().__init__()
        self.parts, self.blocked = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.blocked += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.blocked = max(0, self.blocked - 1)

    def handle_data(self, text):
        if not self.blocked:
            self.parts.append(text)


def _feed_text(value):
    parser = _FeedText()
    parser.feed(value or "")
    return " ".join(" ".join(parser.parts).split())


def parse_fulltext_rss(xml):
    """Official URL-bound story bodies are usable for recall-safe prescreening.

    pubDate is only inventory evidence. Any health candidate's final calendar
    date, title and body still come from its original URL-bound article detail.
    """
    root = ET.fromstring(xml)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("unexpected_rss_document")
    out = {}
    for node in root.findall("channel/item"):
        url = article_url(node.findtext("link", ""))
        if not url:
            continue
        body = _feed_text(node.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", ""))
        description = _feed_text(node.findtext("description", ""))
        title = _feed_text(node.findtext("title", ""))
        categories = [item.text or "" for item in node.findall("category")]
        timestamp = node.findtext("pubDate", "")
        try:
            stamp = parsedate_to_datetime(timestamp)
            provisional_day = stamp.astimezone(ZoneInfo("America/Santiago")).date().isoformat() if stamp.tzinfo else None
        except (ValueError, TypeError):
            provisional_day = None
        combined = title + " " + body + " " + description + " " + " ".join(categories)
        out[url] = dict(url=url, title=title, body=body, description=description, categories=categories,
                        rss_publication_timestamp=timestamp, rss_inventory_day=provisional_day,
                        fulltext_complete=len(body) >= 160 and len(title) >= 18,
                        rss_fulltext_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                        relevant=health_anchor(combined))
    return out


def _load_cache(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("version") == _CACHE_VERSION and isinstance(value.get("articles"), dict):
            return value
    except (OSError, ValueError, TypeError):
        pass
    return dict(version=_CACHE_VERSION, source="pulso_latercera", articles={})


def _verified_detail(entry, loader, cached):
    """Only successful URL-bound article evidence is eligible for reuse."""
    url = entry["url"]
    now = datetime.now(ZoneInfo("UTC")).isoformat()
    # lastmod is solely a change token: it never establishes publication date.
    if (cached and entry.get("lastmod") and cached.get("lastmod") == entry["lastmod"]
            and cached.get("metadata", {}).get("article_verified")
            and cached.get("url") == url):
        result = dict(cached)
        result["cache_hit"] = True
        return result
    try:
        html = loader(url)
        title, body, metadata = extract_article(html, url)
        digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
        combined = title + " " + body + " " + str(metadata.get("keywords", ""))
        relevant = health_anchor(combined)
        metadata.update(discovered_from=entry["listing"], page_text=body[:18000] if relevant else "",
                        market_role="media", source_quality_gate="passed", captured_at=now,
                        html_sha256=digest, publisher_lastmod=entry.get("lastmod", ""),
                        topics=health_topics(combined) if relevant else [])
        return dict(url=url, title=title, body=body[:1800] if relevant else "", metadata=metadata,
                    relevant=relevant, lastmod=entry.get("lastmod", ""), cache_hit=False)
    except ExcludedArticle as exc:
        metadata = dict(exc.metadata)
        metadata.update(discovered_from=entry["listing"], captured_at=now,
                        html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                        publisher_lastmod=entry.get("lastmod", ""), topics=[])
        return dict(url=url, title=exc.title, body="", metadata=metadata, relevant=False,
                    exclusion_reason=str(exc), lastmod=entry.get("lastmod", ""), cache_hit=False)
    except Exception as exc:
        return dict(url=url, status="detail_error", reason=str(exc), error_type=type(exc).__name__,
                    listing=entry["listing"], captured_at=now)


def discover_archive(detail_loader, audit, cache_path, *, today=None, workers=4,
                     max_pages=250, boundary_pages=3, use_rss=True):
    """Traverse the official archive and verify every factual article in detail.

    The advertised index currently exposes only 10,000 stories. Its own offset
    endpoint is extended beyond that index. A finite page cap is a degradation,
    not successful coverage. Modified dates are never final publication dates.
    """
    from .pending_queue import atomic_json
    today = today or datetime.now(ZoneInfo("America/Santiago")).date()
    cutoff = today - timedelta(days=90)
    cache = _load_cache(cache_path)
    articles = cache["articles"]
    visited, out, primary = set(), [], {}
    rss_exclusions, rss_inventory_days, verified_days = 0, [], []
    errors, pages, excluded, attempted_pages, consecutive_page_errors = 0, [], 0, 0, 0
    terminal, boundary, termination = False, False, "unproven"
    advertised = []
    try:
        kind, advertised = parse_sitemap(detail_loader(SITEMAP_INDEX))
        if kind != "index":
            raise ValueError("sitemap_index_not_index")
    except Exception as exc:
        audit.append(dict(listing=SITEMAP_INDEX, status="listing_error", reason=str(exc),
                          error_type=type(exc).__name__))
        return [], set(), dict(coverage_complete=False, termination="index_error")
    page_urls = sorted({x["url"] for x in advertised},
                       key=lambda url: int(parse_qs(urlparse(url).query).get("from", [0])[0]))
    # The publisher's observed endpoint uses 100 articles per offset. An index
    # with gaps is not silently interpolated as if the announced pages existed.
    offsets = [int(parse_qs(urlparse(url).query).get("from", [0])[0]) for url in page_urls]
    contiguous = offsets == list(range(0, max(offsets) + 1, 100))
    if not contiguous:
        errors += 1
        audit.append(dict(listing=SITEMAP_INDEX, status="listing_error", reason="noncontiguous_archive_index"))
    page_digests, older_pages = set(), 0
    worker_count = max(1, min(int(workers), 4))

    def consume_page(url):
        nonlocal errors, excluded, older_pages, terminal, boundary, termination, attempted_pages, consecutive_page_errors, rss_exclusions
        attempted_pages += 1
        try:
            xml = detail_loader(url)
            kind, entries = parse_sitemap(xml)
            if kind != "urls":
                raise ValueError("archive_page_not_urlset")
        except Exception as exc:
            errors += 1
            audit.append(dict(listing=url, status="listing_error", reason=str(exc), error_type=type(exc).__name__))
            older_pages = 0
            consecutive_page_errors += 1
            if consecutive_page_errors >= 3:
                terminal, termination = True, "consecutive_archive_page_errors"
            return
        consecutive_page_errors = 0
        identity = hashlib.sha256("\n".join(x["url"] for x in entries).encode()).hexdigest()
        if entries and identity in page_digests:
            errors += 1
            audit.append(dict(listing=url, status="listing_error", reason="archive_offset_repeats_previous_page"))
            termination = "repeated_page"
            terminal = True  # stop requests, but errors keep coverage incomplete
            return
        page_digests.add(identity)
        page = dict(url=url, status="archive_page", primary_entries=len(entries),
                    xml_sha256=hashlib.sha256(xml.encode("utf-8")).hexdigest(), offset=int(
                        parse_qs(urlparse(url).query).get("from", [0])[0]))
        pages.append(page)
        audit.append(page)
        if not entries:
            terminal, termination = True, "empty_official_archive_page"
            return
        rss_items = {}
        rss_url = url.replace("/sitemap/", "/rss/")
        if use_rss:
            try:
                rss_items = parse_fulltext_rss(detail_loader(rss_url))
            except Exception as exc:
                # This optimisation is optional. Missing/invalid RSS causes
                # direct detail verification for every primary archive URL.
                audit.append(dict(listing=rss_url, status="surface_error", reason=str(exc),
                                  error_type=type(exc).__name__, fallback="direct_article_detail"))
        candidates = []
        for entry in entries:
            canonical = article_url(entry["url"])
            if not canonical:
                excluded += 1
                audit.append(dict(url=entry["url"], listing=url, status="excluded_path", reason="nonfactual_or_unsupported_article_path"))
                continue
            entry.update(url=canonical, listing=url)
            if canonical in visited:
                continue
            visited.add(canonical)
            primary[canonical] = entry
            feed_item = rss_items.get(canonical)
            if feed_item:
                entry.update({key: feed_item[key] for key in ("rss_publication_timestamp", "rss_inventory_day", "rss_fulltext_sha256")})
                if feed_item["rss_inventory_day"]:
                    rss_inventory_days.append(feed_item["rss_inventory_day"])
            if feed_item and feed_item["fulltext_complete"] and not feed_item["relevant"]:
                rss_exclusions += 1
                # Deliberately no final publication_date: no health topic was
                # found anywhere in the original full story, and the detail
                # has not been opened. Inventory dates cannot masquerade as
                # verified bylines in the reconciled health article ledger.
                audit.append(dict(url=canonical, listing=url, status="excluded", reason="fulltext_rss_no_health_anchor",
                                  title=feed_item["title"], section=canonical.split('/')[3], topics=[],
                                  publication_date=None, publication_date_source="not_detail_verified",
                                  rss_publication_timestamp=feed_item["rss_publication_timestamp"],
                                  rss_inventory_day=feed_item["rss_inventory_day"],
                                  rss_fulltext_sha256=feed_item["rss_fulltext_sha256"],
                                  publisher_lastmod=entry.get("lastmod", ""), article_verified=False,
                                  captured_at=datetime.now(ZoneInfo("UTC")).isoformat(), rss_url=rss_url))
                continue
            candidates.append(entry)
        dates = []
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            results = list(pool.map(lambda entry: _verified_detail(entry, detail_loader, articles.get(entry["url"])), candidates))
        page_errors = False
        for entry, result in zip(candidates, results):
            if result.get("status") == "detail_error":
                errors += 1
                page_errors = True
                audit.append(result)
                continue
            articles[result["url"]] = {key: value for key, value in result.items() if key != "cache_hit"}
            metadata = result["metadata"]
            day = date.fromisoformat(metadata["publication_date"])
            dates.append(day)
            verified_days.append(day)
            status = "discovered" if result["relevant"] and cutoff <= day <= today else "excluded"
            reason = None if status == "discovered" else result.get("exclusion_reason", "no_health_anchor") if not result["relevant"] else "outside_90_day_window"
            trace = dict(url=result["url"], listing=url, status=status, reason=reason,
                         title=result["title"], section=metadata["section"], topics=metadata.get("topics", []),
                         publication_date=metadata["publication_date"], publication_timestamp=metadata["publication_timestamp"],
                         publication_date_source=metadata["publication_date_source"], html_sha256=metadata["html_sha256"],
                         captured_at=metadata["captured_at"], publisher_lastmod=entry.get("lastmod", ""),
                         cache_hit=result["cache_hit"], in_complete_30_days=today - timedelta(days=30) <= day < today,
                         in_complete_90_days=cutoff <= day < today, current_day_slice=day == today)
            audit.append(trace)
            if status == "discovered":
                out.append(RawItem("pulso_latercera", result["title"], result["url"], "Pulso / La Tercera",
                                   "press_high_trust", event_date=metadata["publication_date"], raw_text=result["body"], metadata=metadata))
        # A conservative observed boundary is based on verified detail dates,
        # with two additional calendar days for publisher/listing drift. It is
        # usable only beyond *all* advertised pages and after 3 full old pages.
        # No single index lastmod, partial page or detail failure can stop it.
        page["verified_details"] = len(dates)
        page["detail_errors"] = int(page_errors)
        page["publication_date_min"] = min(dates).isoformat() if dates else None
        page["publication_date_max"] = max(dates).isoformat() if dates else None
        full_old_page = (len(entries) == 100 and dates and not page_errors
                         and max(dates) < cutoff - timedelta(days=2))
        older_pages = older_pages + 1 if full_old_page else 0
        if page["offset"] > max(offsets) and older_pages >= max(3, boundary_pages):
            boundary, termination = True, "consecutive_detail_verified_older_pages"
        cache["updated_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
        atomic_json(cache_path, cache)

    # Advertised pages are always exhausted; reaching an old article on a
    # landing page or early index page must not skip the remaining inventory.
    for url in page_urls[:max_pages]:
        consume_page(url)
        if terminal:
            break
    next_offset = max(offsets) + 100
    while not terminal and not boundary and attempted_pages < max_pages:
        consume_page(SITEMAP_PAGE + "&from=" + str(next_offset))
        next_offset += 100
    if not terminal and not boundary:
        termination = "explicit_page_limit"
    covered_advertised = len(pages) >= len(page_urls)
    reached_verified_90_boundary = bool(verified_days and min(verified_days) < cutoff - timedelta(days=2))
    complete = bool(contiguous and covered_advertised and (terminal or boundary) and not errors
                    and reached_verified_90_boundary)
    if terminal and termination == "empty_official_archive_page" and not reached_verified_90_boundary:
        termination = "archive_exhausted_before_required_window"
    summary = dict(status="archive_coverage", mechanism="official_sitemap_offsets_detail_verification",
                   coverage_complete=complete, advertised_pages=len(page_urls), pages_read=len(pages), pages_attempted=attempted_pages,
                   primary_urls=len(primary), excluded_paths=excluded, errors=errors,
                   cache_path=str(cache_path), cache_entries=len(articles), workers=worker_count,
                   max_pages=max_pages, termination=termination, rss_fulltext_exclusions=rss_exclusions,
                   rss_inventory_day_min=min(rss_inventory_days) if rss_inventory_days else None,
                   rss_inventory_day_max=max(rss_inventory_days) if rss_inventory_days else None,
                   complete_30_days=dict(start=(today - timedelta(days=30)).isoformat(), end=(today - timedelta(days=1)).isoformat()),
                   complete_90_days=dict(start=cutoff.isoformat(), end=(today - timedelta(days=1)).isoformat()),
                   current_day_slice=today.isoformat(), verified_publication_day_min=min(verified_days).isoformat() if verified_days else None,
                   boundary_is_observed_not_global_completeness_proof=True)
    audit.append(summary)
    if not complete:
        audit.append(dict(listing=SITEMAP_INDEX, status="listing_error", reason="archive_coverage_incomplete", termination=termination))
    return out, visited, summary


def discover_pulso(detail_loader=None, audit=None, *, cache_path=None, today=None, workers=4,
                   max_pages=250, include_listings=True):
    """Normal daily source hook: historical inventory first, live surfaces second."""
    from pathlib import Path
    from .paths import project_root
    detail_loader = detail_loader or fetch_html
    audit = audit if audit is not None else []
    cache_path = Path(cache_path) if cache_path is not None else project_root() / "data/cache/pulso_discovery.json"
    out, visited, coverage = discover_archive(detail_loader, audit, cache_path, today=today,
                                             workers=workers, max_pages=max_pages)
    if include_listings:
        for listing in LISTINGS:
            try:
                html = detail_loader(listing)
            except Exception as exc:
                audit.append(dict(listing=listing, status="surface_error", reason=str(exc), error_type=type(exc).__name__))
                continue
            out.extend(discover_listing(html, listing, detail_loader, audit, visited))
    if not out:
        raise RuntimeError("Pulso / La Tercera has no verified, dated health articles")
    return sorted(out, key=lambda item: item.event_date, reverse=True)
