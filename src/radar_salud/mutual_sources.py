"""Mutual's native news cards, query detail URLs and category inventories.

The site's client paginator unions all server category components, deduplicates
their article links and chunks them into five-card pages.  A ninety-day audit
must also follow each observed category's server next link until its dates cross
the cutoff or the branch ends.  Dates are never read from CMS modification time.
"""
from __future__ import annotations

import hashlib
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import RawItem
from .occupational_sources import Article, SourceDiscoveryError, assert_not_challenge, chile_today, fold, materiality, valid_date

PAGE = "https://www.mutual.cl/portal/publico/empresa/home/nuestra-mutual/noticias/"
DETAIL_PAGE = "publico.empresa.home.nuestraMutual.noticias.noticiasDetalle"
HOSTS = {"mutual.cl", "www.mutual.cl"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
IGNORE = {"script", "style", "nav", "footer", "aside", "noscript"}


def _official(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in HOSTS
                and not parsed.username and not parsed.password and parsed.port in (None, 443)
                and not parsed.path.casefold().startswith("/portal/privado/"))
    except (ValueError, TypeError):
        return False


class _OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not _official(newurl):
            raise SourceDiscoveryError("redirect_outside_public_official_scope", newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch_mutual_html(url):
    if not _official(url):
        raise SourceDiscoveryError("unverified_official_url", url)
    request = Request(url, headers={"User-Agent": "RadarSaludBot/0.3 (+public-source-monitor)", "Accept": "text/html"})
    with build_opener(_OfficialRedirect()).open(request, timeout=30) as response:
        if not _official(response.url):
            raise SourceDiscoveryError("redirect_outside_public_official_scope", response.url)
        html = response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")
    assert_not_challenge(html, url)
    return html


@dataclass
class _Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    parent: "_Node | None" = field(default=None, repr=False)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield from child.walk()

    def text(self):
        if self.tag in IGNORE:
            return ""
        return " ".join(" ".join(child.text() if isinstance(child, _Node) else child for child in self.children).split())

    def classes(self):
        return set((self.attrs.get("class") or "").split())

    def ignored_ancestor(self):
        node = self
        while node:
            if node.tag in IGNORE or "card-noticia" in node.classes():
                return True
            node = node.parent
        return False


class _Tree(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.root = _Node("document")
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, dict(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def _detail_url(href):
    url = urljoin(PAGE, href or "")
    if not _official(url):
        return None
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    content = query.get("urile", [])
    marker = "/sa_noticias/sa_noticias_detalle/"
    if (query.get("page") != [DETAIL_PAGE] or len(content) != 1
            or not content[0].lower().startswith("wcm:path:")
            or marker not in content[0].lower()
            or not content[0].lower().split(marker, 1)[1].strip("/")):
        return None
    # The query selects the article. Removing it turns every article into the
    # same listing URL. Use the stable listing route, preserving its bytes.
    return urlunsplit(("https", "www.mutual.cl", urlsplit(PAGE).path, parsed.query, ""))


def same_article_url(requested, final):
    """Accept observed official query-to-permalink redirects for the same item.

    Mutual's 302 maps the decoded WCM article slug to an official permalink
    followed by opaque IBM state. A different slug, private route or host never
    preserves identity. This helper does not discover or invent a new URL.
    """
    if not _official(final) or not _detail_url(requested):
        return False
    if requested == final:
        return True
    content = parse_qs(urlsplit(requested).query)["urile"][0]
    slug = content.rstrip("/").rsplit("/", 1)[-1]
    prefix = urlsplit(PAGE).path + "noticias_detalle/"
    path = unquote(urlsplit(final).path)
    if not path.startswith(prefix):
        return False
    remainder = path[len(prefix):]
    parts = remainder.split("/", 1)
    return (parts[0] == slug and not urlsplit(final).query
            and len(parts) == 2 and (parts[1] == "" or parts[1].startswith("!ut/p/")))


def parse_listing(html, page_url=PAGE, *, as_of=None):
    """Expose observed category cards and next URLs for live capture loaders."""
    assert_not_challenge(html, page_url)
    tree = _Tree(html)
    branches = {}
    for node in tree.root.walk():
        branch = node.attrs.get("id", "")
        if not re.fullmatch(r"component-\d+", branch) or "cards-noticias" not in node.classes():
            continue
        cards, card_errors, next_links, has_later_page = [], [], [], False
        for child in node.walk():
            if "card-noticia" in child.classes():
                fields = list(child.walk())
                titles = [item.text() for item in fields if "title-card" in item.classes()]
                dates = [item.text() for item in fields if "fecha" in item.classes()]
                links = [_detail_url(item.attrs.get("href")) for item in fields
                         if item.tag == "a" and "href-button" in item.classes()]
                links = list(dict.fromkeys(link for link in links if link))
                if len(links) != 1 or len(titles) != 1:
                    card_errors.append({"reason": "listing_card_identity_unrecognized", "branch": branch,
                                        "url": page_url, "titles": titles, "detail_links": links})
                    continue
                published = valid_date(dates[0], today=as_of) if len(dates) == 1 else None
                cards.append({"url": links[0], "title": titles[0], "listing_date": published,
                              "date_value": dates[0] if len(dates) == 1 else "", "listing_url": page_url,
                              "listing_sha256": hashlib.sha256(html.encode()).hexdigest(), "branch": branch})
            if child.tag == "a" and child.attrs.get("id", "").endswith("_nextPage"):
                next_links.append(child.attrs.get("href"))
            if child.tag == "a" and child.attrs.get("id", "").endswith("_lastPage"):
                has_later_page = True
        next_links = list(dict.fromkeys(next_links))
        if len(next_links) > 1:
            raise SourceDiscoveryError("ambiguous_pagination", page_url)
        next_href = next_links[0] if next_links else None
        if (next_links or has_later_page) and not next_href:
            card_errors.append({"reason": "pagination_next_link_missing", "branch": branch, "url": page_url})
        next_url = urljoin(page_url, next_href) if next_href else None
        if next_url and not _official(next_url):
            raise SourceDiscoveryError("pagination_outside_official_scope", next_url)
        branches[branch] = {"id": branch, "cards": cards, "next_url": next_url, "errors": card_errors}
    if not branches or not any(branch["cards"] for branch in branches.values()):
        raise SourceDiscoveryError("listing_structure_unrecognized", page_url)
    expected = {"component-" + option.attrs["value"] for select in tree.root.walk()
                if select.tag == "select" and select.attrs.get("id") == "product-select"
                for option in select.walk() if option.tag == "option" and option.attrs.get("value", "").isdigit()}
    listing_errors = [{"code": "listed_category_component_missing", "reason": "listed_category_component_missing",
                       "url": page_url, "branch": branch} for branch in sorted(expected - branches.keys())]
    return {"url": page_url, "branches": branches, "sha256": hashlib.sha256(html.encode()).hexdigest(),
            "errors": listing_errors, "client_union_pagination": "collectUniqueCards" in html and "chunkArray" in html}


def parse_detail(html, url, *, as_of=None):
    """Bind native header publication fields, excluding related cards and menus."""
    assert_not_challenge(html, url)
    article = Article(url=url)
    article.feed(html)
    title, published, body, kind = article.result(today=as_of)
    evidence = article.publication_evidence(today=as_of)
    tree = _Tree(html)
    containers = [node for node in tree.root.walk() if "noticia-conteiner" in node.classes()]
    if containers:
        if len(containers) != 1:
            return {"title": title, "event_date": None, "body": "", "reason": "ambiguous_article_container"}
        headers = [node for node in containers[0].walk() if "cabecera-noticia" in node.classes()]
        bodies = [node for node in containers[0].walk() if "text-noticia" in node.classes()]
        titles = [node.text() for header in headers for node in header.walk()
                  if node.tag == "h1" and "titulo-noticia" in node.classes()]
        if len(headers) != 1 or len(titles) != 1 or len(bodies) != 1:
            return {"title": title, "event_date": None, "body": "", "reason": "article_structure_unrecognized"}
        title, body = titles[0], bodies[0].text()
        native = [node.text() for node in headers[0].walk() if "fecha-noticia" in node.classes()]
        native_kind = "publisher:mutual_detail_fecha"
    else:
    # Only a visible header field after the selected H1 and before article body
    # can complement publisher metadata. Unrelated cards and later event dates
    # never supply publication evidence.
        native, in_header = [], False
        native_kind = "publisher:mutual_div_fecha"
        for node in tree.root.walk():
            if node.ignored_ancestor():
                continue
            if node.tag == "h1":
                if in_header:
                    break
                in_header = node.text() == title
                continue
            if not in_header:
                continue
            if node.tag in ("p", "h2", "h3", "h4", "h5", "h6") and node.text():
                break
            if node.tag == "div" and "fecha" in node.classes():
                native.append(node.text())
    native_dates = [valid_date(value, today=as_of) for value in native]
    if any(day is None for day in native_dates):
        return {"title": title, "event_date": None, "body": body, "reason": "invalid_publication_date"}
    declared = native_dates + ([published] if published else [])
    if len(set(declared)) > 1:
        return {"title": title, "event_date": None, "body": body, "reason": "conflicting_publication_dates"}
    if article.date_candidates and not published:
        return {"title": title, "event_date": None, "body": body, "reason": kind}
    if not published and native_dates:
        published = native_dates[0]
        evidence = {"url": url, "kind": native_kind, "value": native[0], "date": published}
    return {"title": title, "event_date": published, "body": body, "evidence": evidence,
            "reason": "verified_publication" if published else "missing_publication_date"}


def _metrics(rows, as_of):
    result = {}
    for days in (30, 90):
        cutoff = as_of - timedelta(days=days)
        window = [row for row in rows if row.get("event_date") and cutoff <= date.fromisoformat(row["event_date"]) <= as_of]
        result[str(days)] = {"start": cutoff.isoformat(), "end": as_of.isoformat(),
                            "dated_articles": len(window), "expected_role": len(window),
                            "candidates": sum(row["status"] == "candidate" for row in window),
                            "rejected": sum(row["status"] == "rejected" for row in window),
                            "pending": sum(row["status"] == "pending" for row in window),
                            "excluded_role": 0,
                            "unknown_date_items": sum(not row.get("event_date") for row in rows)}
    return result


def _error(exc, url, reason, **extra):
    code = (exc.code if isinstance(exc, SourceDiscoveryError) else
            "executor_proxy_denied" if "Tunnel connection failed: 403" in str(exc) else
            "origin_http_status" if isinstance(getattr(exc, "code", None), int) else reason)
    result = {"url": url, "reason": code, "code": code,
              "detail": str(exc), "exception_type": type(exc).__name__, **extra}
    if code == "origin_http_status":
        result["http_status"] = exc.code
    return result


class MutualNewsScout:
    SOURCE_SLUG = "mutual_seguridad"
    SOURCE_NAME = "Mutual de Seguridad CChC"
    SOURCE_TYPE = "mutuality"
    PAGE = PAGE

    def __init__(self, fetcher=None, as_of=None, *, max_pages=100):
        self.fetcher = fetcher or fetch_mutual_html
        self.as_of = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of or chile_today()
        if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
            raise ValueError("max_pages must be a positive integer")
        self.max_pages = max_pages
        self.report = None
        self.diagnostics = []

    def discover_inventory(self):
        cutoff = self.as_of - timedelta(days=90)
        pages, errors, observed, state = [], [], {}, {}
        queue = deque([(self.PAGE, None)])
        fetched = {}
        while queue and len(pages) < self.max_pages:
            url, target = queue.popleft()
            if target and state.get(target, {}).get("done"):
                continue
            try:
                if url not in fetched:
                    fetched[url] = parse_listing(self.fetcher(url), url, as_of=self.as_of)
                parsed = fetched[url]
            except Exception as exc:
                errors.append(_error(exc, url, "listing_fetch_failed", branch=target))
                if target:
                    state[target]["done"] = True
                    state[target]["complete"] = False
                continue
            branches = parsed["branches"] if target is None else {target: parsed["branches"].get(target)}
            errors.extend(parsed["errors"])
            pages.append({"url": url, "branch": target, "sha256": parsed["sha256"], "client_union_pagination": parsed["client_union_pagination"]})
            for branch_id, branch in branches.items():
                current = state.setdefault(branch_id, {"seen": set(), "done": False, "complete": True,
                                                        "chronology_ok": True, "oldest": None})
                if not branch:
                    current.update(done=True, complete=False, reason="pagination_branch_missing")
                    errors.append({"url": url, "branch": branch_id, "reason": "pagination_branch_missing"})
                    continue
                cards = branch["cards"]
                if branch["errors"]:
                    current["complete"] = False
                    errors.extend(branch["errors"])
                fingerprint = tuple((card["url"], card["listing_date"]) for card in cards)
                if fingerprint in current["seen"]:
                    current.update(done=True, complete=False, reason="repeated_pagination_page")
                    errors.append({"url": url, "branch": branch_id, "reason": "repeated_pagination_page"})
                    continue
                current["seen"].add(fingerprint)
                dates = [card["listing_date"] for card in cards]
                valid = bool(dates) and all(dates)
                ordered = valid and dates == sorted(dates, reverse=True)
                chronological = ordered and (current["oldest"] is None or max(dates) <= current["oldest"])
                current["chronology_ok"] = current["chronology_ok"] and chronological
                if not valid:
                    current["complete"] = False
                for card in cards:
                    existing = observed.get(card["url"])
                    if existing and (existing["listing_date"] != card["listing_date"] or existing["title"] != card["title"]):
                        existing["conflicting_listing_identity"] = True
                    elif not existing:
                        observed[card["url"]] = dict(card)
                if current["chronology_ok"] and min(dates) < cutoff.isoformat():
                    current.update(done=True, reason="crossed_90_day_cutoff")
                elif not branch["next_url"]:
                    current.update(done=True, reason="branch_exhausted")
                else:
                    current["oldest"] = min(dates) if valid else None
                    queue.append((branch["next_url"], branch_id))
        if queue:
            errors.append({"reason": "max_pages_reached", "remaining_branches": len(queue), "limit": self.max_pages})
        rows, raws = [], []
        for card in sorted(observed.values(), key=lambda item: item["listing_date"] or "", reverse=True):
            row = {"source_slug": self.SOURCE_SLUG, "url": card["url"], "title": card["title"],
                   "event_date": card["listing_date"], "publication_date": card["listing_date"],
                   "listing_date": card["listing_date"], "listing_url": card["listing_url"], "market_role": "mutuality",
                   "listing_date_evidence": {"url": card["listing_url"], "item_url": card["url"],
                                              "kind": "publisher:mutual_card_fecha", "value": card["date_value"],
                                              "date": card["listing_date"], "listing_sha256": card["listing_sha256"]},
                   "within_30_days": bool(card["listing_date"] and card["listing_date"] >= (self.as_of - timedelta(days=30)).isoformat()),
                   "within_90_days": bool(card["listing_date"] and card["listing_date"] >= cutoff.isoformat())}
            rows.append(row)
            if not card["listing_date"] or card.get("conflicting_listing_identity"):
                row.update(status="pending", reason="invalid_or_conflicting_listing_date", date_verified=False)
                errors.append({"url": card["url"], "reason": row["reason"], "code": row["reason"],
                               "listing_url": card["listing_url"], "date_value": card["date_value"]})
                continue
            if date.fromisoformat(card["listing_date"]) < cutoff:
                row.update(status="rejected", reason="outside_90_day_horizon", date_verified=False)
                continue
            try:
                detail_html = self.fetcher(card["url"])
                detail = parse_detail(detail_html, card["url"], as_of=self.as_of)
            except Exception as exc:
                diagnostic = _error(exc, card["url"], "detail_fetch_failed")
                row.update(status="pending", reason=diagnostic["reason"], date_verified=False)
                errors.append(diagnostic)
                continue
            published = detail["event_date"]
            normalized = lambda value: re.sub(r"\W+", " ", fold(value)).strip()
            identity_verified = (normalized(detail["title"]) == normalized(card["title"]) and len(detail["body"]) >= 160)
            if not published and detail["reason"] == "missing_publication_date" and identity_verified:
                # The explicit card date belongs to this exact query-selected
                # article. Do not pretend the detail page declared that date.
                published = card["listing_date"]
                detail["evidence"] = {"url": card["listing_url"], "item_url": card["url"],
                                      "kind": "publisher:mutual_card_fecha", "value": card["date_value"],
                                      "date": published, "listing_sha256": card["listing_sha256"],
                                      "detail_sha256": hashlib.sha256(detail_html.encode()).hexdigest()}
            if (not published or published != card["listing_date"]
                    or not identity_verified):
                row.update(status="pending", reason=detail["reason"] if not published else
                           "listing_detail_date_conflict" if published != card["listing_date"] else
                           "article_identity_or_content_unrecognized", date_verified=False)
                errors.append({"url": card["url"], "reason": row["reason"], "code": row["reason"],
                               "listing_url": card["listing_url"], "listing_date": card["listing_date"],
                               "detail_date": published})
                continue
            accepted, reason = materiality("mutuality", detail["title"], detail["body"])
            row.update(status="candidate" if accepted else "rejected", reason=reason, date_verified=True,
                       publication_date_evidence=detail["evidence"], market_role="mutuality")
            raws.append(RawItem(self.SOURCE_SLUG, detail["title"][:350], card["url"], self.SOURCE_NAME, self.SOURCE_TYPE,
                event_date=published, raw_text=detail["body"][:1800], metadata={
                    "discovered_from": card["listing_url"], "page_text": detail["body"][:18000],
                    "market_role": "mutuality", "article_extraction": "occupational_v1",
                    "date_evidence": detail["evidence"]["kind"], "publication_date": published,
                    "publication_date_source": detail["evidence"]["kind"],
                    "publication_date_evidence": detail["evidence"],
                    "listing_date_evidence": {"url": card["listing_url"], "kind": "publisher:mutual_card_fecha",
                                              "value": card["date_value"], "date": card["listing_date"]},
                    "source_quality_gate": "audit_pending_90_day", "materiality_accepted": accepted,
                    "materiality_reason": reason,
                }))
        complete = (bool(state) and not queue and not errors and all(branch["done"] and branch["complete"] for branch in state.values())
                    and not any(row["status"] == "pending" for row in rows))
        for diagnostic in errors:
            diagnostic.setdefault("code", diagnostic["reason"])
        summary = [{"branch": key, "complete": value["complete"], "done": value["done"], "reason": value.get("reason")}
                   for key, value in state.items()]
        self.report = {"source_slug": self.SOURCE_SLUG, "raw_items": raws, "rows": rows, "pages": pages,
            "metrics": _metrics(rows, self.as_of), "coverage_complete": complete, "errors": errors,
            "stop_reason": "all_category_branches_exhausted_or_cutoff" if complete else "inventory_incomplete",
            "window": {"as_of_chile": self.as_of.isoformat(), "30_day_start": (self.as_of - timedelta(days=30)).isoformat(),
                       "90_day_start": cutoff.isoformat()}, "branches": summary}
        for metric in self.report["metrics"].values():
            metric["complete"] = complete
        self.report["unknown_publication_dates"] = sum(not row["publication_date"] for row in rows)
        self.report["technical_status"] = "ok" if complete else "partial" if rows else "blocked"
        self.diagnostics = errors + [{"code": "inventory_complete" if complete else "coverage_gap", "branches": summary}]
        self.discovery_incomplete = not complete
        self.coverage_status = "complete" if complete else "incomplete"
        self.decisions = rows
        return self.report

    def discover(self):
        return self.discover_inventory()["raw_items"]
