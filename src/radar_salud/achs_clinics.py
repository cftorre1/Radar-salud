"""Inventories for the nine clinical publishers linked by Clínicas Achs Salud.

Identity and newsroom routes were verified in achs_additional_surfaces.json.
Only linked pagination, feeds and explicitly advertised API routes are followed.
The loader owns robots, redirect authority, TLS and durable response artifacts.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html import escape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from .occupational_inventory import _calendar, _failure, _official, _resolve
from .occupational_sources import Article, RawItem, assert_not_challenge, materiality, valid_date

NETWORK_IDENTITY_URL = "https://www.clinicasachssalud.cl/"
CLINICS = (
    {"id": "portada", "name": "Clínica Portada", "home": "https://clinicaportada.cl/", "news": "https://clinicaportada.cl/noticias/", "hosts": ("www.clinicaportada.cl", "clinicaportada.cl")},
    {"id": "atacama", "name": "Clínica Atacama", "home": "https://clinicaatacama.cl/", "news": "https://clinicaatacama.cl/noticias/", "hosts": ("clinicaatacama.cl", "www.clinicaatacama.cl")},
    {"id": "los_coihues", "name": "Clínica Los Coihues", "home": "https://clinicaloscoihues.cl/", "news": "https://clinicaloscoihues.cl/noticias", "hosts": ("clinicaloscoihues.cl",)},
    {"id": "maitenes", "name": "Clínica Maitenes", "home": "https://clinicamaitenes.cl/", "news": "https://clinicamaitenes.cl/noticias/", "hosts": ("www.clinicamaitenes.cl", "clinicamaitenes.cl")},
    {"id": "lircay", "name": "Clínica Lircay", "home": "https://clinicalircay.cl/", "news": "https://clinicalircay.cl/noticias/", "hosts": ("www.clinicalircay.cl", "clinicalircay.cl")},
    {"id": "los_andes", "name": "Clínica Los Andes", "home": "https://www.clinicalosandes.cl/", "news": "https://www.clinicalosandes.cl/noticias/", "hosts": ("clinicalosandes.cl", "www.clinicalosandes.cl")},
    {"id": "del_sur", "name": "Clínica Del Sur", "home": "https://www.clinicasur.cl/", "news": "https://www.clinicasur.cl/noticias/", "hosts": ("www.clinicasur.cl",)},
    {"id": "puerto_montt", "name": "Clínica Puerto Montt", "home": "https://clinicapuertomontt.cl/", "news": "https://clinicapuertomontt.cl/noticias/", "hosts": ("www.clinicapuertomontt.cl", "clinicapuertomontt.cl")},
    {"id": "curico", "name": "Clínica Curicó", "home": "https://clinica-curico.cl/", "news": "https://clinica-curico.cl/noticias/", "hosts": ("www.clinica-curico.cl", "clinica-curico.cl")},
)


def clinic_for_host(host):
    return next((clinic for clinic in CLINICS if host in clinic["hosts"]), None)


def is_static_service_surface(row):
    """Validate the explicit non-publication exception before merging rows."""
    url = urlsplit(row.get("url") or "")
    clinic = clinic_for_host(url.hostname)
    evidence = row.get("publisher_surface_evidence")
    if (not clinic or not isinstance(evidence, dict) or row.get("status") != "excluded_surface"
            or row.get("type") != "service_page" or row.get("reason") != "publisher_declares_static_service_page"
            or row.get("market_role") != "provider_achs" or row.get("provider_subtype") != "clinicas"
            or row.get("clinic_id") != clinic["id"] or row.get("publication_date") is not None
            or row.get("event_date") is not None or row.get("provider_identity_url") != NETWORK_IDENTITY_URL
            or not _official(row["url"], clinic) or url.query or url.fragment
            or evidence.get("kind") != "wordpress:static_page" or evidence.get("url") != row["url"]):
        return False
    identifier = evidence.get("object_id")
    if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier < 1:
        return False
    api_url = evidence.get("official_api_url")
    if not isinstance(api_url, str) or not _official(api_url, clinic):
        return False
    api = urlsplit(api_url)
    return bool(api.hostname == url.hostname and api.path == "/wp-json/wp/v2/pages/" + str(identifier)
                and not api.query and not api.fragment and evidence.get("body_class") == "page page-id-" + str(identifier))


class _ContentScope(HTMLParser):
    """Preserve publisher metadata and the native WordPress article body."""
    VOID = Article.VOID
    IGNORE = {"nav", "footer", "aside", "script", "style", "noscript"}

    def __init__(self):
        super().__init__()
        self.stack, self.entries, self.articles, self.meta, self.headers, self.headings = [], [], [], [], [], []
        self.entry, self.article, self.header, self.heading = None, None, None, None
        self.body_seen = False
        self.wordpress_single = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").casefold().split())
        ignored = any(frame["ignored"] for frame in self.stack) or tag in self.IGNORE or bool(classes & {"site-header", "site-footer", "sidebar", "widget-area", "elementor-location-header", "elementor-location-footer", "reply-button", "comments", "comment-form"})
        if tag == "body":
            self.body_seen = True
            self.wordpress_single = "single-post" in classes
        if tag == "meta" and not ignored:
            key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").casefold()
            if key in {"article:published_time", "datepublished", "publishdate"} and (not self.body_seen or any(frame["tag"] == "head" for frame in self.stack)):
                self.meta.append(self.get_starttag_text())
        depth = len(self.stack) + 1
        if not ignored:
            medicenter_post = ("post-content" in classes and self.wordpress_single and
                               any(frame["tag"] == "li" and {"single", "post"} <= frame["classes"]
                                   for frame in self.stack))
            if self.entry is None and ("entry-content" in classes or medicenter_post):
                self.entry = {"depth": depth, "parts": [], "heading_index": len(self.headings),
                              "scope": "wordpress:medicenter_post-content" if medicenter_post else "wordpress:entry-content"}
                self.entries.append(self.entry)
            if self.article is None and tag == "article":
                self.article = {"depth": depth, "parts": []}
                self.articles.append(self.article)
            if self.header is None and classes & {"entry-header", "entry-meta", "post-meta"} and self.entry is None:
                self.header = {"depth": depth, "parts": []}
                self.headers.append(self.header)
            if tag == "h1":
                self.heading = {"depth": depth, "parts": [], "entry_title": bool(classes & {"entry-title", "post-title"}),
                                "in_entry": self.entry is not None, "in_article": self.article is not None}
                self.headings.append(self.heading)
            for field in (self.entry, self.article, self.header):
                if field is not None:
                    field["parts"].append(self.get_starttag_text())
        if tag not in self.VOID:
            self.stack.append({"tag": tag, "ignored": ignored, "classes": classes})

    def handle_data(self, text):
        if any(frame["ignored"] for frame in self.stack):
            return
        for field in (self.entry, self.article, self.header):
            if field is not None:
                field["parts"].append(escape(text))
        if self.heading is not None:
            self.heading["parts"].append(text)

    def handle_endtag(self, tag):
        if not self.stack or tag not in [frame["tag"] for frame in self.stack]:
            return
        index = len(self.stack) - 1 - [frame["tag"] for frame in self.stack][::-1].index(tag)
        if not any(frame["ignored"] for frame in self.stack):
            for field in (self.entry, self.article, self.header):
                if field is not None:
                    field["parts"].append(f"</{tag}>")
        depth = index + 1
        for name in ("entry", "article", "header", "heading"):
            field = getattr(self, name)
            if field is not None and field["depth"] >= depth:
                setattr(self, name, None)
        del self.stack[index:]

    def selected(self):
        headings = [heading for heading in self.headings if heading["entry_title"] or heading["in_entry"] or heading["in_article"]]
        if not headings and self.entries:
            headings = self.headings[:self.entries[0]["heading_index"]][-1:]
        title = " ".join(" ".join(headings[0]["parts"]).split()) if headings else ""
        if self.entries:
            body, scope = "".join(self.entries[0]["parts"]), self.entries[0]["scope"]
        elif self.articles:
            body, scope = "".join(self.articles[0]["parts"]), "html:article"
        else:
            body, scope = "", "missing_native_article_container"
        return "".join(self.meta) + f"<h1>{escape(title)}</h1>" + "".join("".join(field["parts"]) for field in self.headers) + body, scope


class ClinicArticle(Article):
    """Shared date rules with clinic-specific body scope and verified tail titles."""
    STOP = Article.STOP + ("lo mas visto", "photostream", "archivos", "noticias que te podrian interesar", "leave a reply")

    def __init__(self, url=None):
        super().__init__(url=url)
        # The Drupal publisher places this native field in article.single-noticia
        # before its H1. Reconstructing the scoped article activates the shared
        # publication-container rule; sibling card dates never enter that scope.
        if urlsplit(url or "").hostname == "clinicaloscoihues.cl":
            self.PUBLICATION_CLASSES = Article.PUBLICATION_CLASSES | {"date-noticia"}
        self._captured_parts, self._clinic_parsed = [], False
        self.content_scope = "not_parsed"

    def feed(self, data):
        if self._clinic_parsed:
            raise ValueError("ClinicArticle requires the complete captured document before extraction")
        self._captured_parts.append(data)

    def _parse_clinic(self):
        if not self._clinic_parsed:
            if not clinic_for_host(urlsplit(self.url or "").hostname):
                raise ValueError("ClinicArticle requires an officially linked clinic publisher")
            parser = _ContentScope()
            parser.feed("".join(self._captured_parts))
            selected, self.content_scope = parser.selected()
            self._clinic_parsed = True
            super().feed(selected)

    def result(self, *, today=None):
        self._parse_clinic()
        return super().result(today=today)


class _Links(HTMLParser):
    """Collect article-card links separately from feeds, archives and pagination."""
    def __init__(self):
        super().__init__()
        self.stack, self.links, self.disclosed, self.anchor = [], [], [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set(a.get("class", "").casefold().split())
        ignored = tag in {"nav", "header", "footer", "aside", "script", "style"} or bool(classes & {"sidebar", "widget", "widget-area", "related-posts", "related-articles"})
        article = tag == "article" or bool(classes & {"entry-title", "post-title", "elementor-post__title", "et_pb_post"})
        if tag == "link" and a.get("href"):
            self.disclosed.append(a)
        if tag == "a":
            self.anchor = {"href": a.get("href"), "parts": [], "rel": a.get("rel", "").casefold().split(),
                           "type": a.get("type", ""), "title": a.get("title", ""),
                           "article": (article or any(frame["article"] or re.fullmatch(r"h[2-5]", frame["tag"]) for frame in self.stack)) and
                                      not (ignored or any(frame["ignored"] for frame in self.stack))}
        if tag not in Article.VOID:
            self.stack.append({"tag": tag, "ignored": ignored, "article": article})

    def handle_data(self, value):
        if self.anchor is not None:
            self.anchor["parts"].append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            self.anchor["text"] = " ".join(" ".join(self.anchor.pop("parts")).split())
            self.links.append(self.anchor)
            self.anchor = None
        if tag in [frame["tag"] for frame in self.stack]:
            index = len(self.stack) - 1 - [frame["tag"] for frame in self.stack][::-1].index(tag)
            del self.stack[index:]


def _page_number(url, clinic=None):
    query = dict(parse_qsl(urlsplit(url).query))
    # The captured Drupal pager labels ?page=0 as Página1 and ?page=1
    # as Página2. Only this verified publisher uses the zero-based contract.
    if clinic and clinic["id"] == "los_coihues" and query.get("page", "").isdigit():
        return int(query["page"]) + 1
    if query.get("paged", "").isdigit():
        return int(query["paged"])
    match = re.search(r"/page/(\d+)/?$", urlsplit(url).path)
    return int(match[1]) if match else 1


def _next_link(current, parser, clinic):
    choices, errors = [], []
    current_number = _page_number(current, clinic)
    base = re.sub(r"/page/\d+/?$", "", urlsplit(current).path).rstrip("/")
    for link in parser.links + [{"href": item.get("href"), "rel": item.get("rel", "").split(), "text": ""} for item in parser.disclosed]:
        label = link.get("text", "").casefold().strip(" «»›→")
        explicit = "next" in link.get("rel", []) or label in {"siguiente", "next", "older posts", "entradas más antiguas", "artículos anteriores"}
        if not explicit and not (label.isdigit() and int(label) == current_number + 1):
            continue
        url = _resolve(current, link.get("href"))
        if not url or not _official(url, clinic):
            if explicit:
                errors.append({"code": "unsafe_clinic_next_page", "url": url or current})
            continue
        path = re.sub(r"/page/\d+/?$", "", urlsplit(url).path).rstrip("/")
        if path != base or _page_number(url, clinic) != current_number + 1:
            if explicit:
                errors.append({"code": "clinic_pagination_gap_or_cycle", "url": url})
            continue
        if url not in choices:
            choices.append(url)
    if len(choices) > 1:
        errors.append({"code": "clinic_pagination_ambiguous", "url": current})
        return None, errors
    return choices[0] if choices else None, errors


def _headers(loader, url):
    record = getattr(loader, "records", {}).get(url, {})
    return {key.casefold(): value for block in record.get("hops", [{}])[-1].get("headers", []) for key, value in block.items()}


def _metrics(report, today):
    report["metrics"] = {}
    for days in (30, 90):
        start = today - timedelta(days=days)
        for row in report["rows"]:
            day = datetime.fromisoformat(row["publication_date"]).date() if row.get("publication_date") else None
            row[f"within_{days}_days"] = bool(day and start <= day <= today)
        rows = [row for row in report["rows"] if row[f"within_{days}_days"]]
        report["metrics"][str(days)] = {"start": start.isoformat(), "end": today.isoformat(), "dated_articles": len(rows),
                                       "expected_role": len(rows), "candidates": sum(row["status"] == "candidate" for row in rows),
                                       "rejected": sum(row["status"] == "rejected" for row in rows), "excluded_role": 0,
                                       "pending": sum(row["status"] == "pending" for row in rows),
                                       "unknown_date_items": sum(not row.get("publication_date") and row["status"] != "excluded_surface" for row in report["rows"]),
                                       "complete": report["coverage_complete"]}
    report["unknown_publication_dates"] = sum(not row.get("publication_date") and row["status"] != "excluded_surface" for row in report["rows"])
    report["excluded_non_publication_surfaces"] = sum(row["status"] == "excluded_surface" for row in report["rows"])
    report["technical_status"] = "ok" if report["coverage_complete"] else "partial" if report["rows"] else "blocked"


class _StaticPublisherPage(HTMLParser):
    """Identify a declared WP page object without dating service content."""
    def __init__(self):
        super().__init__()
        self.object_id, self.links = None, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "body":
            classes = set(attrs.get("class", "").split())
            identities = [value[8:] for value in classes if re.fullmatch(r"page-id-\d+", value)]
            if "page" in classes and "single-post" not in classes and len(identities) == 1:
                self.object_id = identities[0]
        elif tag == "link" and attrs.get("type") == "application/json" and "alternate" in attrs.get("rel", "").split():
            self.links.append(attrs.get("href"))

    def evidence(self, url, clinic):
        for href in self.links:
            parsed = urlsplit(href or "")
            if (self.object_id and _official(href, clinic) and parsed.hostname == urlsplit(url).hostname
                    and parsed.path == "/wp-json/wp/v2/pages/" + self.object_id
                    and not parsed.query and not parsed.fragment):
                return {"kind": "wordpress:static_page", "url": url, "object_id": int(self.object_id),
                        "official_api_url": href, "body_class": "page page-id-" + self.object_id}
        return None


def discover_clinics_inventory(scout, loader, as_of=None, max_pages=20, manifest=None):
    """Return one report per official clinic and the compatible lane aggregate.

    Native article dates are mandatory even when a feed supplies pubDate.
    A captured main feed supplements HTML discovery; RSS alone is a bounded
    sample and does not establish complete source coverage. API links are
    evaluated only when disclosed by a captured homepage/listing.
    """
    if scout.slug != "clinicas_achs_salud":
        raise ValueError("Clinical publisher inventory is restricted to the provider lane")
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")
    today, clinics = _calendar(as_of), list(CLINICS if manifest is None else manifest)
    if not clinics or len({clinic["id"] for clinic in clinics}) != len(clinics):
        raise ValueError("Clinic manifest must contain distinct official publishers")
    known = {clinic["id"]: clinic for clinic in CLINICS}
    for clinic in clinics:
        if clinic["id"] not in known or set(clinic["hosts"]) - set(known[clinic["id"]]["hosts"]):
            raise ValueError("Clinic manifest contains an unverified official publisher")
        if not all(_official(clinic[key], clinic) for key in ("home", "news")):
            raise ValueError("Clinic manifest routes must use the verified publisher's HTTPS hosts")
    start90 = today - timedelta(days=90)
    report = {"source_slug": scout.slug, "surface_slug": "achs_clinics_network", "as_of": today.isoformat(),
              "window": {"convention": "rolling_elapsed_days_inclusive", "start_30": (today - timedelta(days=30)).isoformat(),
                         "start_90": start90.isoformat(), "end": today.isoformat()},
              "rows": [], "raw_items": [], "pages": [], "errors": [], "clinic_reports": [], "coverage_complete": False,
              "stop_reason": "clinic_inventory_incomplete", "outside_boundary": None}
    cache = {}
    def load(url, clinic, surface, branch):
        if not _official(url, clinic):
            raise ValueError("Clinic URL must belong to this officially linked publisher")
        if url not in cache:
            body = loader(url)
            if not isinstance(body, str):
                raise TypeError("Clinical loader must return captured text")
            assert_not_challenge(body, url)
            cache[url] = body
        page = {"url": url, "clinic_id": clinic["id"], "surface": surface, "status": "captured",
                "sha256": hashlib.sha256(cache[url].encode("utf-8")).hexdigest()}
        branch["pages"].append(page)
        return cache[url], page
    for clinic in clinics:
        branch = {"clinic_id": clinic["id"], "name": clinic["name"], "identity_url": NETWORK_IDENTITY_URL,
                  "home_url": clinic["home"], "newsroom_url": clinic["news"], "rows": [], "raw_items": [], "pages": [],
                  "errors": [], "route_errors": [], "disclosed_feeds": [], "disclosed_apis": [],
                  "outside_boundary": None, "api_collection_attempted": False, "api_window_complete": False,
                  "coverage_complete": False, "stop_reason": None}
        rows, raw_by_url, feeds, apis = {}, {}, set(), set()
        def disclose(parser, current):
            for item in parser.disclosed + parser.links:
                url = _resolve(current, item.get("href"))
                if not url or not _official(url, clinic):
                    continue
                kind, title = item.get("type", "").casefold(), item.get("title", "").casefold()
                rel = item.get("rel", "")
                rel = " ".join(rel).casefold() if isinstance(rel, list) else rel.casefold()
                if kind in {"application/rss+xml", "application/atom+xml"} and "comment" not in title and "/comments/" not in url:
                    feeds.add(url)
                if item.get("text", "").casefold() in {"rss", "rss feed", "feed"} and "/comments/" not in url:
                    feeds.add(url)
                if "https://api.w.org/" in rel or (kind == "application/json" and urlsplit(url).path.rstrip("/").endswith("/wp-json")):
                    apis.add(url)
        def detail(url, title, listing_url, listed_date=None, listing_evidence=None):
            existing = rows.get(url)
            if existing is not None:
                if listing_evidence:
                    existing["listing_publication_evidence"] = listing_evidence
                if listed_date and existing.get("publication_date") and existing["publication_date"] != listed_date:
                    existing.update(publication_date=None, event_date=None, status="pending", reason="clinic_listing_detail_date_conflict")
                    raw_by_url.pop(url, None)
                    branch["errors"].append({"code": "clinic_listing_detail_date_conflict", "url": url, "listing_evidence": listing_evidence})
                return existing
            row = {"url": url, "title": title, "publication_date": None, "event_date": None, "date_evidence": None,
                   "listing_url": listing_url, "section": "noticias", "type": "article", "source_type": scout.cfg["type"],
                   "market_role": "provider_achs", "provider_subtype": "clinicas", "clinic_id": clinic["id"],
                   "clinic_name": clinic["name"], "provider_identity_url": NETWORK_IDENTITY_URL,
                   "materiality_accepted": None, "materiality_reason": None, "status": "pending", "reason": "detail_not_attempted"}
            rows[url] = row
            if listing_evidence:
                row["listing_publication_evidence"] = listing_evidence
            try:
                html, page = load(url, clinic, "article_detail", branch)
                publisher_page = _StaticPublisherPage()
                publisher_page.feed(html)
                surface_evidence = publisher_page.evidence(url, clinic)
                if surface_evidence:
                    row.update(status="excluded_surface", reason="publisher_declares_static_service_page",
                               type="service_page", section="servicios_permanentes",
                               publisher_surface_evidence=surface_evidence, detail_sha256=page["sha256"])
                    return row
                article = ClinicArticle(url=url)
                article.feed(html)
                actual_title, published, body, evidence = article.result(today=today)
                row.update(title=actual_title or title, content_scope=article.content_scope)
                # A native publisher headline can be short ("Nuevo Mamógrafo").
                # The scoped body and explicit publication field supply proof.
                if not published or len(actual_title) < 5 or len(body) < 160:
                    raise ValueError(f"Clinic detail extraction unverified: {evidence}; scope={article.content_scope}")
                if listed_date and published != listed_date:
                    raise ValueError(f"Clinic listing/detail publication conflict: listing={listed_date}, detail={published}")
                accepted, reason = materiality("provider_achs", actual_title, body)
                row.update(publication_date=published, event_date=published, date_evidence=evidence,
                           publication_evidence=article.publication_evidence(today=today), detail_sha256=page["sha256"],
                           materiality_accepted=accepted, materiality_reason=reason,
                           status="candidate" if accepted else "rejected", reason=reason)
                if datetime.fromisoformat(published).date() < start90:
                    row.update(status="outside_window", reason="outside_90_day_horizon")
                else:
                    raw_by_url[url] = RawItem(scout.slug, actual_title[:350], url, clinic["name"], scout.cfg["type"],
                                              event_date=published, raw_text=body[:1800], metadata={
                        "discovered_from": listing_url, "page_text": body[:18000], "market_role": "provider_achs",
                        "provider_subtype": "clinicas", "clinic_id": clinic["id"], "clinic_name": clinic["name"],
                        "provider_identity_url": NETWORK_IDENTITY_URL, "content_scope": article.content_scope,
                        "article_extraction": "occupational_v1", "date_evidence": evidence, "publication_date": published,
                        "publication_date_source": evidence, "publication_evidence": article.publication_evidence(today=today),
                        "listing_publication_evidence": listing_evidence, "source_quality_gate": "audit_pending_90_day",
                        "materiality_accepted": accepted, "materiality_reason": reason})
            except Exception as exc:
                error = _failure(exc, url, "clinic_detail_extraction")
                branch["errors"].append(error)
                row["reason"] = error["code"]
            return row
        try:
            html, _ = load(clinic["home"], clinic, "home", branch)
            parser = _Links(); parser.feed(html); disclose(parser, clinic["home"])
        except Exception as exc:
            branch["route_errors"].append(_failure(exc, clinic["home"], "clinic_home_fetch"))
        current, visited, previous_day, chronological = clinic["news"], set(), None, True
        for page_index in range(max_pages):
            if current in visited:
                branch["errors"].append({"code": "clinic_pagination_cycle", "url": current})
                break
            visited.add(current)
            try:
                html, page = load(current, clinic, "newsroom", branch)
                parser = _Links(); parser.feed(html); disclose(parser, current)
                next_url, issues = _next_link(current, parser, clinic)
                branch["errors"].extend(issues)
                candidates = []
                for link in parser.links:
                    url = _resolve(current, link.get("href"))
                    if (link["article"] and url and _official(url, clinic) and url not in visited
                            and urlsplit(url).path.rstrip("/") not in {"", "/noticias", "/blog"}
                            and not re.search(r"\.(?:pdf|jpe?g|png|gif|svg)$", urlsplit(url).path, re.I)):
                        if url not in [item[0] for item in candidates]:
                            candidates.append((url, link["text"]))
                page.update(candidate_urls=[url for url, _ in candidates], next_url=next_url)
                if not candidates:
                    raise ValueError("No recognized clinical article-card links")
                for url, title in candidates:
                    if url in rows:
                        continue
                    row = detail(url, title, current)
                    published = row.get("publication_date")
                    if published:
                        day = datetime.fromisoformat(published).date()
                        if previous_day and day > previous_day:
                            chronological = False
                            branch["errors"].append({"code": "clinic_publication_order_not_monotonic", "url": url})
                        previous_day = day
                        if day < start90 and branch["outside_boundary"] is None:
                            branch["outside_boundary"] = {"url": url, "date": published, "listing_url": current,
                                                          "publication_evidence": row["publication_evidence"]}
                if branch["outside_boundary"] and chronological:
                    branch["stop_reason"] = "verified_older_boundary" if not branch["errors"] else "older_boundary_with_pending_issues"
                    break
                if not next_url:
                    branch["stop_reason"] = "no_verified_older_boundary"
                    break
                if page_index == max_pages - 1:
                    branch["errors"].append({"code": "clinic_max_pages_exhausted", "url": current})
                    branch["stop_reason"] = "max_pages_exhausted"
                    break
                current = next_url
            except Exception as exc:
                branch["errors"].append(_failure(exc, current, "clinic_newsroom_fetch"))
                branch["stop_reason"] = "clinic_newsroom_unavailable"
                break
        for feed in sorted(feeds):
            branch["disclosed_feeds"].append(feed)
            try:
                body, page = load(feed, clinic, "disclosed_feed", branch)
                root = ElementTree.fromstring(body)
                items = root.findall("./channel/item")
                if root.tag != "rss" or root.find("channel") is None:
                    raise ValueError("Disclosed feed is not a recognized RSS channel")
                page["returned_items"] = len(items)
                if not items:
                    page.update(empty_feed=True, coverage_complete=False)
                for item in items:
                    url = _resolve(feed, item.findtext("link"))
                    if not url or not _official(url, clinic):
                        raise ValueError("Feed contains a nonofficial clinical article")
                    value = item.findtext("pubDate")
                    try:
                        instant = parsedate_to_datetime(value)
                        if instant.tzinfo is None:
                            raise ValueError("Feed publication timezone is missing")
                        day = instant.astimezone(ZoneInfo("America/Santiago")).date()
                        if day > today:
                            raise ValueError("Feed publication date is after as_of")
                    except Exception as exc:
                        row = detail(url, item.findtext("title") or "", feed)
                        row.update(publication_date=None, event_date=None, status="pending", reason="clinic_feed_publication_unverified")
                        raw_by_url.pop(url, None)
                        branch["errors"].append({"code": "clinic_feed_publication_unverified", "url": url,
                                                  "feed_url": feed, "value": value, "detail": str(exc)})
                        continue
                    evidence = {"kind": "rss:item.pubDate", "url": feed, "document_url": url, "value": value, "date": day.isoformat()}
                    if url not in rows and day >= start90:
                        branch["errors"].append({"code": "clinic_feed_html_discovery_gap", "url": url, "feed_url": feed})
                    detail(url, item.findtext("title") or "", feed, day.isoformat(), evidence)
            except Exception as exc:
                branch["route_errors"].append(_failure(exc, feed, "clinic_feed_capture"))
        for api_url in sorted(apis):
            branch["disclosed_apis"].append(api_url)
            try:
                body, page = load(api_url, clinic, "disclosed_api", branch)
                api_root = json.loads(body)
                routes = api_root.get("routes", {}) if isinstance(api_root, dict) else {}
                page["posts_route_advertised"] = "/wp/v2/posts" in routes
                page["coverage_complete"] = False
                page["next_action"] = "Capture the explicitly advertised native posts listing and verify publication bounds, total/page headers and linked details" if page["posts_route_advertised"] else "No native posts listing was advertised by this captured API surface"
                post_route = routes.get("/wp/v2/posts", {})
                endpoints = [endpoint for endpoint in post_route.get("endpoints", []) if "GET" in endpoint.get("methods", [])]
                endpoint = next((endpoint for endpoint in endpoints if {"after", "before", "per_page", "page"} <= set(endpoint.get("args", {}))), None)
                if endpoint is None:
                    continue
                branch["api_collection_attempted"] = True
                if urlsplit(api_url).query or not urlsplit(api_url).path.rstrip("/").endswith("/wp-json"):
                    raise ValueError("Advertised API route form does not establish a posts collection URL")
                limit = min(100, endpoint["args"]["per_page"].get("maximum", 100))
                if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
                    raise ValueError("Native API per_page schema is invalid")
                query = {"per_page": limit, "after": (start90 - timedelta(days=1)).isoformat() + "T23:59:59",
                         "before": (today + timedelta(days=1)).isoformat() + "T00:00:00"}
                posts_base = api_url.rstrip("/") + "/wp/v2/posts"
                seen_api, seen_api_ids, expected_total, expected_pages = set(), set(), None, None
                for api_page in range(1, max_pages + 1):
                    if api_page > 1:
                        query["page"] = api_page
                    posts_url = posts_base + "?" + urlencode(query)
                    text, api_page_evidence = load(posts_url, clinic, "native_api_posts", branch)
                    posts = json.loads(text)
                    if not isinstance(posts, list):
                        raise ValueError("Native API posts response is not a list")
                    headers = _headers(loader, posts_url)
                    if not {"x-wp-total", "x-wp-totalpages"} <= headers.keys():
                        branch["route_errors"].append({"code": "clinic_api_total_headers_missing", "url": posts_url})
                        total, total_pages = None, None
                    else:
                        total, total_pages = int(headers["x-wp-total"]), int(headers["x-wp-totalpages"])
                        if total < 0 or total_pages < 0 or total_pages != (total + limit - 1) // limit:
                            raise ValueError("Native API total/page headers are inconsistent")
                        if expected_total is not None and (total, total_pages) != (expected_total, expected_pages):
                            raise ValueError("Native API totals changed between captures")
                        expected_total, expected_pages = total, total_pages
                    api_page_evidence.update(header_total=total, header_total_pages=total_pages, returned_posts=len(posts))
                    for post in posts:
                        if not isinstance(post, dict):
                            raise ValueError("Native API post is malformed")
                        url = _resolve(posts_url, post.get("link"))
                        identifier = post.get("id")
                        if (not url or not _official(url, clinic) or url in seen_api or
                                not isinstance(identifier, int) or isinstance(identifier, bool) or identifier < 1 or identifier in seen_api_ids):
                            raise ValueError("Native API has a duplicate or nonofficial article link")
                        seen_api.add(url)
                        seen_api_ids.add(identifier)
                        value = post.get("date")
                        day = valid_date(value, today=today) if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value) and post.get("status") == "publish" else None
                        if not day or not start90 <= datetime.fromisoformat(day).date() <= today:
                            branch["errors"].append({"code": "clinic_api_publication_unverified", "url": url, "value": value})
                            row = detail(url, post.get("title", {}).get("rendered", ""), posts_url)
                            row.update(publication_date=None, event_date=None, status="pending", reason="clinic_api_publication_unverified")
                            raw_by_url.pop(url, None)
                            continue
                        evidence = {"kind": "wordpress:post.date", "url": posts_url, "document_url": url,
                                    "post_id": post.get("id"), "value": value, "date": day}
                        if url not in rows:
                            branch["errors"].append({"code": "clinic_api_html_discovery_gap", "url": url, "api_url": posts_url})
                        detail(url, post.get("title", {}).get("rendered", ""), posts_url, day, evidence)
                    if total_pages is None:
                        break
                    if api_page >= total_pages:
                        if len(seen_api) != total:
                            raise ValueError("Native API post count does not match header total")
                        branch["api_window_complete"] = True
                        api_page_evidence["coverage_complete"] = True
                        page["next_action"] = "Native API window was captured; require every linked detail date to remain verified"
                        break
                    if api_page == max_pages:
                        branch["route_errors"].append({"code": "clinic_api_max_pages_exhausted", "url": posts_url})
            except Exception as exc:
                branch["route_errors"].append(_failure(exc, api_url, "clinic_api_capture"))
        branch["rows"], branch["raw_items"] = list(rows.values()), list(raw_by_url.values())
        if branch["api_window_complete"]:
            branch["errors"] = [error for error in branch["errors"] if error["code"] not in {"clinic_feed_html_discovery_gap", "clinic_api_html_discovery_gap"}]
        elif branch["api_collection_attempted"]:
            branch["errors"].append({"code": "clinic_api_window_incomplete", "url": branch["disclosed_apis"][-1]})
        branch["coverage_complete"] = bool((branch["outside_boundary"] and chronological or branch["api_window_complete"]) and not branch["errors"] and
                                            all(row["status"] == "excluded_surface" or row.get("publication_date") and row["status"] != "pending" for row in branch["rows"]))
        if branch["route_errors"] and not branch["rows"]:
            branch["errors"].extend(branch["route_errors"])
        _metrics(branch, today)
        report["raw_items"].extend(branch.pop("raw_items"))
        report["clinic_reports"].append(branch)
        for key in ("rows", "pages", "errors"):
            report[key].extend(branch[key])
    report["coverage_complete"] = all(branch["coverage_complete"] for branch in report["clinic_reports"])
    report["stop_reason"] = "all_clinics_verified_older_boundary" if report["coverage_complete"] else "clinic_inventory_incomplete"
    _metrics(report, today)
    return report
