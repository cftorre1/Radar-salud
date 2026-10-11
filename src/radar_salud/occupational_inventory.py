"""Bounded occupational-news inventories from captured, linked archive pages.

The loader returns HTML for the requested URL. Transport, redirects and saved
response evidence belong to that loader; this module never creates page URLs.
Every date and editorial decision comes from the shared detail-page extractor.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from types import SimpleNamespace
from urllib.parse import urljoin, urlsplit, urlunsplit

from . import occupational_sources as sources


class _Archive(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.anchor = None
        self.heading = False
        self.ignored = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"nav", "header", "footer", "aside", "script", "style"}:
            self.ignored.append(tag)
        if tag in {"h2", "h3"} and not self.ignored:
            self.heading = True
        if tag == "a":
            self.anchor = {"href": attrs.get("href"), "parts": [],
                           "rel": attrs.get("rel", "").casefold().split(),
                           "title": attrs.get("aria-label", "") or attrs.get("title", ""),
                           "heading": self.heading and not self.ignored}
        elif tag == "link" and "next" in attrs.get("rel", "").casefold().split():
            self.links.append({"href": attrs.get("href"), "text": "", "rel": ["next"],
                               "title": "", "heading": False})

    def handle_data(self, text):
        if self.anchor is not None:
            self.anchor["parts"].append(text)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            link = self.anchor
            link["text"] = " ".join(" ".join(link.pop("parts")).split())
            self.links.append(link)
            self.anchor = None
        if tag in {"h2", "h3"}:
            self.heading = False
        if self.ignored and self.ignored[-1] == tag:
            self.ignored.pop()


def _official(url, cfg):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.netloc in cfg["hosts"]
                and not parsed.username and not parsed.password)
    except (TypeError, ValueError):
        return False


def _canonical(url, *, article=False):
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                       "" if article else parsed.query, ""))


def _resolve(current, href, *, article=False):
    try:
        return _canonical(urljoin(current, href), article=article)
    except (TypeError, ValueError):
        return None


def _page_pattern(scout):
    configured = scout.cfg.get("next_page_pattern")
    if configured:
        return configured
    if scout.slug in {"achs_seguro_laboral", "clinicas_achs_salud"}:
        return r"/centro-de-noticias(?:/\d+)?/?"
    if scout.slug == "ist":
        return r"/(?:noticias|category/noticias)(?:/page/\d+)?/?"
    return None


def _ordinal(url):
    match = re.search(r"/(?:page/)?(\d+)/?$", urlsplit(url).path)
    return int(match.group(1)) if match else 1


def _next_page(scout, current, links):
    """Return only a next href present in this page, never an inferred URL."""
    pattern, current_number = _page_pattern(scout), _ordinal(current)
    choices, issues = [], []
    for link in links:
        if not link.get("href"):
            continue
        label = sources.fold(link.get("text", "") or link.get("title", "")).strip(" «»›→")
        explicit = ("next" in link["rel"] or bool(re.fullmatch(
            r"(?:entradas mas antiguas|older(?: entries| posts)?|(?:pagina )?siguiente|next(?: page)?)", label)))
        numeric = label.isdigit() and int(label) == current_number + 1
        if not explicit and not numeric:
            continue
        url = _resolve(current, link["href"])
        if url is None:
            if explicit:
                issues.append({"code": "malformed_next_page", "url": current})
            continue
        if not _official(url, scout.cfg):
            if explicit:
                issues.append({"code": "unsafe_next_page", "url": url})
            continue
        if not pattern or not re.fullmatch(pattern, urlsplit(url).path):
            if explicit:
                issues.append({"code": "unrecognized_next_page", "url": url})
            continue
        number = _ordinal(url)
        if number != current_number + 1:
            if explicit:
                issues.append({"code": "pagination_cycle" if number <= current_number else "pagination_gap",
                               "url": url})
            continue
        if url not in choices:
            choices.append(url)
    if len(choices) > 1:
        issues.append({"code": "ambiguous_next_page", "url": current, "choices": choices})
        return None, issues
    return (choices[0] if choices else None), issues


def _candidates(scout, current, links):
    items, seen = [], set()
    for link in links:
        if not link.get("href") or (scout.slug == "ist" and not link["heading"]):
            continue
        url = _resolve(current, link["href"], article=True)
        if url is None or not _official(url, scout.cfg) or not re.fullmatch(scout.cfg["path"], urlsplit(url).path):
            continue
        if scout.slug == "ist" and urlsplit(url).path.rstrip("/") in {
                "/noticias", "/contacto", "/historia", "/quienes-somos"}:
            continue
        if url not in seen:
            seen.add(url)
            items.append((url, link["text"]))
    return items


def _failure(exc, url, phase):
    return {"code": getattr(exc, "code", f"{phase}_failed"), "url": getattr(exc, "url", url),
            "phase": phase, "type": type(exc).__name__, "detail": str(exc)}


def _calendar(as_of):
    if as_of is None:
        return sources.chile_today()
    if isinstance(as_of, datetime):
        return as_of.date()
    return as_of if isinstance(as_of, date) else date.fromisoformat(as_of)


def discover_inventory(scout, loader, as_of=None, max_pages=20):
    """Return rows, raw items, page evidence and honest 30/90-day coverage.

    Windows retain the project's rolling elapsed-day convention: both ends are
    included, from ``as_of - timedelta(days=N)`` through ``as_of``. Consequently
    these are not claims of exactly N distinct calendar dates.

    Completion requires linked, contiguous pages in publication-date order,
    an article strictly before the 90-day start, and no extraction gaps. An
    archive ending inside the window does not establish the required boundary.
    ``raw_items`` contains RawItem objects; other report fields are JSON-ready.
    """
    if scout.slug not in sources.SOURCES:
        raise ValueError("Inventory is limited to configured occupational sources")
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")
    today = _calendar(as_of)
    accepted_roles = scout.cfg.get("accepted_roles", (scout.cfg["role"],))
    starts = {days: today - timedelta(days=days) for days in (30, 90)}
    report = {"source_slug": scout.slug, "as_of": today.isoformat(),
              "window": {"convention": "rolling_elapsed_days_inclusive",
                         "end": today.isoformat(), "start_30": starts[30].isoformat(),
                         "start_90": starts[90].isoformat()},
              "coverage_complete": False, "stop_reason": None, "rows": [],
              "raw_items": [], "pages": [], "errors": [], "outside_boundary": None}
    current, page_seen, article_seen, detail_cache = scout.cfg["page"], set(), set(), {}
    previous_day = None
    chronology_ok = True

    def detail_loader(url):
        if not _official(url, scout.cfg):
            raise ValueError("Detail URL must be official HTTPS")
        if url not in detail_cache:
            detail = loader(url)
            if not isinstance(detail, str):
                raise TypeError("Inventory loader must return HTML text")
            detail_cache[url] = detail
        return detail_cache[url]

    for page_index in range(max_pages):
        page = {"url": current, "page_number": None, "status": "pending"}
        report["pages"].append(page)
        if not _official(current, scout.cfg):
            error = {"code": "unsafe_archive_url", "url": current}
            report["errors"].append(error)
            page.update(status="blocked", error=error)
            report["stop_reason"] = "unsafe_archive_url"
            break
        current = _canonical(current)
        page.update(url=current, page_number=_ordinal(current))
        if current in page_seen:
            report["errors"].append({"code": "pagination_cycle", "url": current})
            report["stop_reason"] = "pagination_cycle"
            break
        page_seen.add(current)
        try:
            html = loader(current)
            if not isinstance(html, str):
                raise TypeError("Inventory loader must return HTML text")
            sources.assert_not_challenge(html, current)
        except Exception as exc:
            error = _failure(exc, current, "archive_fetch")
            report["errors"].append(error)
            page.update(status="blocked", error=error)
            report["stop_reason"] = error["code"]
            break
        page["sha256"] = hashlib.sha256(html.encode("utf-8")).hexdigest()
        archive = _Archive()
        archive.feed(html)
        candidates = _candidates(scout, current, archive.links)
        page["candidate_urls"] = [url for url, _ in candidates]
        next_url, pagination_errors = _next_page(scout, current, archive.links)
        report["errors"].extend(pagination_errors)
        page["next_url"] = next_url
        local = SimpleNamespace(slug=scout.slug, cfg={**scout.cfg, "page": current}, decisions=[], diagnostics=[])
        try:
            raw_items = sources.discover_items(local, html, detail_loader, as_of=today, max_items=None)
        except sources.SourceDiscoveryError as exc:
            raw_items = getattr(exc, "partial_items", [])
            diagnostics = getattr(exc, "diagnostics", None) or getattr(local, "diagnostics", [])
            report["errors"].extend(diagnostics or [_failure(exc, current, "detail_discovery")])
        except Exception as exc:
            raw_items = []
            report["errors"].append(_failure(exc, current, "detail_discovery"))
        decisions = {row["url"]: row for row in local.decisions}
        raw_by_url = {item.url: item for item in raw_items}
        page_days = []
        pending = 0
        for url, listing_title in candidates:
            if url in article_seen:
                continue
            article_seen.add(url)
            decision = decisions.get(url, {})
            title, published, body, evidence = decision.get("title") or listing_title, decision.get("event_date"), "", decision.get("date_evidence")
            if url in detail_cache:
                article = sources.Article(url=url)
                article.feed(detail_cache[url])
                title, published, body, evidence = article.result(today=today)
            day = date.fromisoformat(published) if published else None
            role = sources.market_role(title, body) if scout.slug in {"achs_seguro_laboral", "clinicas_achs_salud"} else "mutuality"
            accepted, material_reason = sources.materiality(role, title, body) if day and body else (None, None)
            reason = decision.get("reason") or "detail_not_attempted"
            status = decision.get("status", "pending")
            if day and day > today:
                day = None
                published, status, reason = None, "pending", "publication_after_as_of"
            elif not day or status == "pending":
                status = "pending"
            elif day < starts[90]:
                status, reason = "outside_window", "outside_90_day_horizon"
            elif role not in accepted_roles:
                status, reason = "excluded_role", "different_market_role"
            else:
                status, reason = ("candidate" if accepted else "rejected"), material_reason
            row = {"url": url, "title": title, "publication_date": published,
                   "event_date": published, "date_evidence": evidence, "listing_url": current,
                   "section": scout.cfg.get("section", "noticias"), "type": "article",
                   "source_type": scout.cfg["type"], "market_role": role,
                   "provider_subtype": "centros" if role == "provider_achs_centers" else "clinicas" if role == "provider_achs" else None,
                   "materiality_accepted": accepted, "materiality_reason": material_reason,
                   "status": status, "reason": reason,
                   "within_30_days": bool(day and starts[30] <= day <= today),
                   "within_90_days": bool(day and starts[90] <= day <= today)}
            if url in detail_cache:
                row["detail_sha256"] = hashlib.sha256(detail_cache[url].encode("utf-8")).hexdigest()
                row["publication_evidence"] = article.publication_evidence(today=today)
            report["rows"].append(row)
            if status == "pending":
                pending += 1
            if day:
                page_days.append(day)
                if previous_day is not None and day > previous_day:
                    chronology_ok = False
                    report["errors"].append({"code": "publication_order_not_monotonic", "url": url,
                                             "previous_date": previous_day.isoformat(), "date": day.isoformat()})
                previous_day = day
                if day < starts[90] and report["outside_boundary"] is None:
                    report["outside_boundary"] = {"url": url, "date": day.isoformat(), "listing_url": current,
                                                  "date_evidence": evidence}
            if url in raw_by_url and status in {"candidate", "rejected"}:
                report["raw_items"].append(raw_by_url[url])
        page.update(status="partial" if pending or pagination_errors else "captured",
                    dated_min=min(page_days).isoformat() if page_days else None,
                    dated_max=max(page_days).isoformat() if page_days else None,
                    new_items=sum(row["listing_url"] == current for row in report["rows"]),
                    pending_items=pending)
        if not candidates:
            page["status"] = "unrecognized"
            report["errors"].append({"code": "listing_structure_unrecognized", "url": current})
            report["stop_reason"] = "listing_structure_unrecognized"
            break
        all_dated = all(row["publication_date"] and row["status"] != "pending" for row in report["rows"])
        if report["outside_boundary"] and chronology_ok and all_dated and not report["errors"]:
            report["coverage_complete"] = True
            report["stop_reason"] = "verified_older_boundary"
            break
        if not next_url:
            report["stop_reason"] = (pagination_errors[0]["code"] if pagination_errors else
                                     "archive_ended_with_gaps" if not all_dated or report["errors"] else
                                     "no_verified_older_boundary")
            break
        if page_index == max_pages - 1:
            report["stop_reason"] = "max_pages_exhausted"
            break
        current = next_url

    report["metrics"] = {}
    for days in (30, 90):
        rows = [row for row in report["rows"] if row[f"within_{days}_days"]]
        report["metrics"][str(days)] = {"start": starts[days].isoformat(), "end": today.isoformat(),
                                        "dated_articles": len(rows),
                                        "expected_role": sum(row["market_role"] in accepted_roles for row in rows),
                                        "candidates": sum(row["status"] == "candidate" for row in rows),
                                        "rejected": sum(row["status"] == "rejected" for row in rows),
                                        "excluded_role": sum(row["status"] == "excluded_role" for row in rows),
                                        "pending": sum(row["status"] == "pending" for row in rows),
                                        "unknown_date_items": sum(not row["publication_date"] for row in report["rows"]),
                                        "complete": report["coverage_complete"]}
    report["unknown_publication_dates"] = sum(not row["publication_date"] for row in report["rows"])
    report["technical_status"] = ("ok" if report["coverage_complete"] else
                                   "partial" if report["rows"] else "blocked")
    return report
