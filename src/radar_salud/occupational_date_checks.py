"""Read-only diagnostics for unresolved official publication date fields.

These checks never create RawItems, advance watermarks, or resolve an ambiguous
publisher date by preferring the day that happens to fit a reporting window.
"""
from __future__ import annotations

import json
import re
from datetime import timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from .achs_blog import BLOG_URL, _BlogRecords, _cms_date, _one, _publication, _url
from .occupational_inventory import _calendar, _IstHeaderDateObservation
from .occupational_sources import Article, valid_date

TPS_URL = "https://ist.cl/realizamos-una-exitosa-jornada-preventiva-en-tps/"


def blog_publication_date_issues(html, *, as_of=None):
    """Retain unresolved exact dates and bound only their observed possibilities."""
    today = _calendar(as_of)
    parser = _BlogRecords()
    parser.feed(html)
    parser.finish()
    rows = []
    for fields in parser.records:
        day, reason, observations = _publication(fields, today)
        if day:
            continue
        values = [(field, value) for field in ("PublicationDate", "FechaArticulo")
                  for value in fields.get(field, [])]
        dates = [_cms_date(value, today=today) for _, value in values]
        bounded = bool(fields.get("PublicationDate") and fields.get("FechaArticulo")
                       and values and all(stamp is not None for stamp in dates))
        observed = sorted({stamp.date().isoformat() for stamp in dates if stamp})
        row = {"url": _url(_one(fields, "navigateUrl")), "title": _one(fields, "Title"),
               "publication_date": None, "event_date": None, "status": "pending", "reason": reason,
               "date_observations": observations, "observed_publication_days": observed,
               "all_observed_publication_fields_parseable": bounded,
               "ignored_for_publication": ["LastModified", "DateCreated"]}
        for days in (30, 90):
            start = (today - timedelta(days=days)).isoformat()
            row[f"potentially_within_{days}_days"] = (not bounded or
                any(start <= value <= today.isoformat() for value in observed))
            row[f"all_observed_days_before_{days}_day_boundary"] = bool(bounded and observed and max(observed) < start)
        rows.append(row)
    return {"url": BLOG_URL, "as_of": today.isoformat(), "records": len(parser.records),
            "date_issues": rows, "parser_errors": parser.errors,
            "unknown_exact_publication_dates": len(rows),
            "potentially_current_90_day_issues": sum(row["potentially_within_90_days"] for row in rows),
            "historical_90_day_issues": sum(row["all_observed_days_before_90_day_boundary"] for row in rows),
            "no_publication_dates_assigned": True}


def _same_document(value, url):
    try:
        left, right = urlsplit(value), urlsplit(url)
        return (left.scheme == right.scheme == "https" and left.netloc == right.netloc
                and not left.username and not left.password and not left.query
                and left.path.rstrip("/") == right.path.rstrip("/"))
    except (ValueError, TypeError):
        return False


class _Disclosures(HTMLParser):
    def __init__(self, url):
        super().__init__()
        self.url, self.links, self.jsonld, self.ignored_meta = url, [], [], []
        self.script = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and attrs.get("href"):
            linked = urljoin(self.url, attrs["href"])
            target = urlsplit(linked)
            if target.scheme == "https" and target.netloc == urlsplit(self.url).netloc and not target.username and not target.password:
                self.links.append({"url": linked, "type": attrs.get("type"), "rel": attrs.get("rel"), "title": attrs.get("title")})
        elif tag == "script" and attrs.get("type", "").casefold() == "application/ld+json":
            self.script = []
        elif tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").casefold()
            if key in {"article:modified_time", "datemodified", "datecreated"}:
                self.ignored_meta.append({"kind": key, "value": attrs.get("content")})

    def handle_data(self, value):
        if self.script is not None:
            self.script.append(value)

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            self.jsonld.append("".join(self.script))
            self.script = None


def _jsonld_publications(payloads, url, today):
    evidence, errors, ignored = [], [], []
    def visit(node):
        if isinstance(node, list):
            for child in node:
                visit(child)
        elif isinstance(node, dict):
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            entity = node.get("mainEntityOfPage")
            entity = entity.get("@id") or entity.get("url") if isinstance(entity, dict) else entity
            bound = any(_same_document(value, url) for value in (node.get("url"), node.get("@id"), entity) if isinstance(value, str))
            if bound and set(types or []) & {"Article", "NewsArticle", "BlogPosting"}:
                if "datePublished" in node:
                    evidence.append({"kind": "jsonld:datePublished", "url": url,
                                     "value": node["datePublished"], "date": valid_date(node["datePublished"], today=today)})
                for field in ("dateModified", "dateCreated"):
                    if field in node:
                        ignored.append({"kind": "jsonld:" + field, "value": node[field]})
            for child in node.values():
                if isinstance(child, (dict, list)):
                    visit(child)
    for payload in payloads:
        try:
            visit(json.loads(payload))
        except (ValueError, TypeError):
            errors.append("invalid_jsonld")
    return evidence, errors, ignored


def ist_publication_date_issue(html, api_payload, feed_xml, *, as_of=None, url=TPS_URL):
    """Inspect linked alternatives; leave unlabelled content dates unresolved."""
    today = _calendar(as_of)
    payload = json.loads(api_payload) if isinstance(api_payload, str) else api_payload
    posts = payload if isinstance(payload, list) else [payload]
    matches = [post for post in posts if isinstance(post, dict) and _same_document(post.get("link"), url)]
    if len(matches) != 1:
        raise ValueError("API must contain exactly one post bound to the inspected detail")
    post = matches[0]
    native = post.get("date")
    native_day = (valid_date(native, today=today) if isinstance(native, str) and
                  re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", native) and post.get("status") == "publish" else None)
    article = Article(url=url)
    article.feed(html)
    html_dates = [dict(candidate, date=valid_date(candidate["value"], today=today)) for candidate in article.date_candidates]
    disclosures = _Disclosures(url)
    disclosures.feed(html)
    jsonld, jsonld_errors, ignored_jsonld = _jsonld_publications(disclosures.jsonld, url, today)
    observation = _IstHeaderDateObservation()
    observation.feed(post.get("content", {}).get("rendered", ""))
    header_dates = [{"kind": "rendered_content:unlabelled_date_before_h1", "value": value,
                     "date": valid_date(value, today=today)} for value in observation.observations]
    root = ElementTree.fromstring(feed_xml)
    items = root.findall("./channel/item")
    rss_dates = []
    for item in items:
        if _same_document(item.findtext("link"), url):
            value, day = item.findtext("pubDate"), None
            try:
                stamp = parsedate_to_datetime(value)
                if stamp.tzinfo is not None and stamp.astimezone(ZoneInfo("America/Santiago")).date() <= today:
                    day = stamp.astimezone(ZoneInfo("America/Santiago")).date().isoformat()
            except (TypeError, ValueError):
                pass
            rss_dates.append({"kind": "rss:item.pubDate", "value": value, "date": day})
    return {"url": url, "as_of": today.isoformat(), "publication_date": None, "event_date": None,
            "status": "pending", "reason": "official_publication_date_ambiguity_requires_review",
            "api_native_publication": {"value": native, "date": native_day, "field": "date", "post_id": post.get("id")},
            "html_publication_fields": html_dates, "jsonld_publication_fields": jsonld,
            "jsonld_present": bool(disclosures.jsonld), "jsonld_errors": jsonld_errors,
            "unlabelled_content_header_dates": header_dates,
            "unlabelled_date_semantics": "Neither publication nor event date is assigned without an explicit publisher label",
            "rss": {"returned_items": len(items), "matching_post_publications": rss_dates,
                    "can_resolve_this_post": bool(rss_dates)},
            "official_disclosed_links": disclosures.links,
            "official_api_self_links": post.get("_links", {}).get("self", []),
            "ignored_publication_fields": {"api": {key: post.get(key) for key in ("modified", "modified_gmt", "date_gmt")},
                                           "html": disclosures.ignored_meta, "jsonld": ignored_jsonld},
            "no_automatic_date_selection": True}
