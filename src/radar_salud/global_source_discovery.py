"""Official WHO/PAHO discovery. Produces evidence candidates, never Global cards."""
from __future__ import annotations

import hashlib
import json
import re
from html import unescape
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .global_discovery_common import CaptureClient, Document, canonical_url, publication_day
from .pending_queue import atomic_json


def in_window(day, as_of: date, days: int):
    return bool(day and (as_of - timedelta(days=days-1)).isoformat() <= day <= as_of.isoformat())

def classify(title, section):
    text = title.casefold()
    noise = r"\b(welcomes? .{0,30}members|appointed|appointment|elected president|anniversary|webinar|training|celebrates|congratulates)\b"
    if re.search(noise, text):
        return {"materiality": "routine", "priority": 0, "category": "institutional_routine", "reason": "ceremony_training_or_appointment"}
    rules = [
        ("emergency", 95, r"alert|outbreak|disease outbreak|epidemiological update|public health emergency|measles|avian influenza|ebola"),
        ("policy_guidelines", 90, r"guideline|recommendation|regulat|policy|mental health care|community-based|framework|roadmap"),
        ("financing_systems", 88, r"financ|funding|budget|investment|health system|workforce|health coverage|social protection"),
        ("epidemiology", 85, r"influenza|respiratory|epidemiolog|surveillance|intelligence|deaths|cases|burden|eliminat|mortality|immuniz|vaccin"),
        ("technical_document", 75, r"report|strategy|evaluation|technical|research|monitoring|data|survey"),
    ]
    if section == "disease_outbreak_news":
        return {"materiality": "candidate", "priority": 95, "category": "emergency", "reason": "official_disease_outbreak_notification"}
    for category, priority, pattern in rules:
        if re.search(pattern, text):
            return {"materiality": "candidate", "priority": priority, "category": category, "reason": "material_topic_requires_editorial_fact_and_consequence_review"}
    return {"materiality": "undetermined", "priority": 0, "category": "context", "reason": "metadata_insufficient_to_establish_business_materiality"}

def entities(title, source, section):
    found = [{"name": source.upper(), "kind": "publisher", "basis": "official_origin", "independence_group": "WHO_UN_SYSTEM"}]
    for name, pattern in [("Chile", r"\bChile(?:an)?\b"), ("Americas", r"\bAmericas\b|Américas"),
                          ("Democratic Republic of the Congo", r"Democratic Republic of the Congo"),
                          ("Russian Federation", r"Russian Federation")]:
        if re.search(pattern, title, re.I):
            found.append({"name": name, "kind": "geography", "basis": "publisher_title"})
    if section == "chile_news" and not any(x["name"] == "Chile" for x in found):
        found.append({"name": "Chile", "kind": "taxonomy_scope", "basis": "official_country_filter_c65", "direct_local_effect_verified": False})
    return found

def reporting_period(title):
    match = re.search(r"(?:Semana Epidemiológica|Epidemiological Week)\s*(\d{1,2})", title, re.I)
    return {"label": match.group(0), "week": int(match[1]), "year": None, "basis": "publisher_title"} if match else None

def parse_who_index(payload, section, as_of):
    if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
        raise ValueError("WHO API schema changed")
    prefix = {"news": "/news/item", "publications": "/publications/i/item", "disease_outbreak_news": "/emergencies/disease-outbreak-news/item"}[section]
    rows = []
    for item in payload["value"]:
        title = unescape(str((item.get("OverrideTitle") if item.get("UseOverrideTitle") else item.get("Title")) or ""))
        suffix = str(item.get("ItemDefaultUrl") or "")
        if not title or not suffix.startswith("/"):
            raise ValueError("WHO missing official identity")
        url = canonical_url("https://www.who.int" + (suffix if suffix.startswith(prefix + "/") else prefix + suffix))
        raw_dates = [str(item[k]) for k in ("FormatedDate", "FormattedDate", "PublicationDateAndTime") if item.get(k)]
        dates = {publication_day(day, as_of) for day in raw_dates}; dates.discard(None)
        valid = len(dates) == 1 and all(publication_day(day, as_of) for day in raw_dates)
        row = {"url": url, "title": title, "source": "who", "section": section,
               "index_published_at": next(iter(dates)) if valid else None,
               "raw_publication_dates": raw_dates, "publication_date_basis": "official_API_publication_field",
               "publication_date_error": None if valid else "missing_future_or_conflicting_index_date",
               "event_date": (item.get("EmergencyEvent") or {}).get("EmergencyEventStartDate"),
               "event_id": (item.get("EmergencyEvent") or {}).get("EventId"),
               "effective_date": None, "reporting_period": reporting_period(title),
               "document_links": [item["DownloadUrl"]] if item.get("DownloadUrl") else []}
        rows.append(row)
    return rows

def parse_paho_index(html, section, as_of, base):
    document = Document(html).root
    rows = []
    for field in document.nodes():
        if not field.has_class("views-field-title"):
            continue
        anchors = [a for a in field.nodes("a") if a.text() and a.attrs.get("href")]
        if len(anchors) != 1:
            raise ValueError("PAHO title card structure changed")
        anchor = anchors[0]
        parent = field.parent
        dates = list(parent.nodes("time")) if parent else []
        if len(dates) != 1:
            raise ValueError("PAHO card has ambiguous publication date")
        raw_date = dates[0].attrs.get("datetime", dates[0].text())
        day = publication_day(raw_date, as_of)
        rows.append({"url": canonical_url(anchor.attrs["href"], base), "title": anchor.text(),
                     "source": "paho", "section": section, "index_published_at": day,
                     "raw_publication_dates": [raw_date], "publication_date_basis": "official_list_displayed_created_time",
                     "publication_date_error": None if day else "missing_or_future_index_date",
                     "event_date": None, "event_id": None, "effective_date": None,
                     "reporting_period": reporting_period(anchor.text()), "document_links": []})
    next_links = [a.attrs["href"] for a in document.nodes("a") if "next" in a.attrs.get("rel", "").split() and a.attrs.get("href")]
    if len(set(next_links)) > 1:
        raise ValueError("PAHO ambiguous pagination")
    return rows, canonical_url(next_links[0], base) if next_links else None

def detail_metadata(html, as_of, url):
    document = Document(html).root
    h1 = [node.text() for node in document.nodes("h1") if node.text()]
    if len(h1) != 1:
        raise ValueError("detail missing unique H1 / challenge suspected")
    raw_dates = []
    for node in document.nodes("meta"):
        key = (node.attrs.get("property") or node.attrs.get("name") or "").lower()
        if key in {"article:published_time", "datepublished", "citation_publication_date", "dc.date.issued"}:
            raw_dates.append(node.attrs.get("content", ""))
    for node in document.nodes():
        if node.has_class("date") or node.has_class("field--name-created"):
            match = re.match(r"\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", node.text())
            if match:
                raw_dates.append(match[1])
    canonical = [node.attrs["href"] for node in document.nodes("link") if node.attrs.get("rel") == "canonical" and node.attrs.get("href")]
    alternates = [node.attrs["href"] for node in document.nodes("link") if node.attrs.get("rel") == "alternate" and node.attrs.get("hreflang") and node.attrs.get("href")]
    docs = []
    for node in document.nodes("a"):
        href = node.attrs.get("href", "")
        if ".pdf" in href.lower() or "/bitstreams/" in href or "/bitstream/" in href:
            absolute = __import__('urllib.parse', fromlist=['urljoin']).urljoin(url, href)
            if urlsplit(absolute).scheme == "https" and urlsplit(absolute).hostname in {"www.who.int", "cdn.who.int", "iris.who.int", "www.paho.org", "iris.paho.org"}:
                docs.append(absolute)
    return {"title": h1[0], "publication_dates": sorted({day for value in raw_dates if (day := publication_day(value, as_of))}),
            "raw_publication_dates": raw_dates, "canonical_url": canonical_url(canonical[0], url) if canonical else url,
            "alternate_language_urls": sorted({canonical_url(value, url) for value in alternates if urlsplit(value).hostname in {"www.who.int", "www.paho.org"}}),
            "document_links": sorted(set(docs))}

def collect_route(client, route, as_of, max_pages):
    rows, pages, seen = [], [], set()
    cutoff = (as_of - timedelta(days=89)).isoformat()
    complete, stop = False, "page_limit"
    url = route["url"]
    if route["format"] == "who_api":
        body, _ = client.fetch(url)
        match = re.search(r'hubsfiltering\([^,]+,\s*"[^"]+",\s*"([^"]+)"', body.decode(errors="replace"))
        if not match:
            raise ValueError("observed public API missing from official landing")
        url = canonical_url(match[1], "https://www.who.int")
    for page in range(max_pages):
        page_url = url
        if route["format"] == "who_api":
            parts = urlsplit(url); query = [(k,v) for k,v in parse_qsl(parts.query) if k not in {"$top", "$skip"}]
            page_url = urlunsplit((*parts[:3], urlencode(query + [("$skip", str(page*50)), ("$top", "50")]), ""))
        try:
            raw, capture = client.fetch(page_url)
        except Exception as exc:
            stop = "page_fetch_failure: " + type(exc).__name__ + ": " + str(exc)[:200]
            break
        if route["format"] == "who_api":
            found = parse_who_index(json.loads(raw), route["section"], as_of); next_url = True
        else:
            found, next_url = parse_paho_index(raw.decode(errors="replace"), route["section"], as_of, page_url)
        ids = tuple(item["url"] for item in found)
        for item in found:
            item["index_evidence"] = [{"listing_url": page_url, "body_sha256": capture["body_sha256"], "fetched_at": capture["fetched_at"], "http_status":capture["http_status"], "tls_verified":capture["tls_verified"]}]
        pages.append({"url": page_url, "capture": capture, "native_records": len(found), "items": found})
        if not found:
            complete, stop = page > 0, "empty_native_page" if page > 0 else "empty_initial_page_unverified"; break
        if ids in seen:
            stop = "repeated_pagination_page"; break
        seen.add(ids); rows.extend(found)
        dates = [item["index_published_at"] for item in found if item["index_published_at"]]
        if len(dates) == len(found) and dates == sorted(dates, reverse=True) and min(dates) < cutoff:
            complete, stop = True, "verified_older_boundary"; break
        if not next_url:
            complete, stop = True, "native_archive_exhausted"; break
        if route["format"] != "who_api":
            url = next_url
    return {"route": route, "pages": pages, "items": rows, "archive_complete": complete,
            "stop_reason": stop, "date_pending": sum(not x["index_published_at"] for x in rows)}

def verify_item(client, row, as_of):
    item = dict(row); item["published_at"] = row["index_published_at"]
    item["source_aliases"] = [row["url"]]; item["sections"] = row.get("discovered_sections", [row["section"]])
    item["publication_ready"] = False; item["content_use"] = "metadata_and_link_only"
    item["classification"] = classify(row["title"], row["section"])
    item["entities"] = entities(row["title"], row["source"], "chile_news" if "chile_news" in item["sections"] else row["section"])
    item["reason"] = row["publication_date_error"]
    item["status"] = "pending" if item["reason"] else "discovered"
    try:
        raw, capture = client.fetch(row["url"])
        metadata = detail_metadata(raw.decode(errors="replace"), as_of, row["url"])
        normalize = lambda title: re.sub(r"\W+", "", title.casefold())
        if normalize(metadata["title"]) != normalize(row["title"]):
            raise ValueError("index_detail_title_mismatch")
        if metadata["canonical_url"].rstrip("/") != row["url"].rstrip("/"):
            raise ValueError("detail_canonical_identity_mismatch")
        item["detail_evidence"] = {"capture": capture, "metadata": metadata}
        item["document_links"] = sorted(set(row["document_links"] + metadata["document_links"]))
        observed = metadata["publication_dates"]
        if len(observed) > 1 or (observed and observed[0] != row["index_published_at"]):
            item.update(published_at=None, status="pending", reason="index_detail_publication_conflict")
        elif item["published_at"]:
            material = item["classification"]["materiality"]
            item.update(status="pending" if material != "routine" else "rejected",
                        reason="awaiting_editorial_corroboration_and_rights_review" if material == "candidate" else item["classification"]["reason"])
        item["detail_verified"] = True
    except Exception as exc:
        item.update(status="pending", reason="detail_evidence_unavailable", detail_verified=False,
                    technical_error=type(exc).__name__ + ": " + str(exc)[:250])
    return item

def discover(config, client, as_of):
    routes, failures, indexed = [], [], {}
    for route in config["routes"]:
        try:
            result = collect_route(client, route, as_of, config["max_pages_per_route"])
            routes.append(result)
            if result["stop_reason"].startswith("page_fetch_failure"):
                failures.append({"route": route, "error": result["stop_reason"]})
            for row in result["items"]:
                if row["index_published_at"] is None or in_window(row["index_published_at"], as_of, 90):
                    if row["url"] not in indexed:
                        indexed[row["url"]] = dict(row, discovered_sections=[row["section"]])
                    else:
                        previous = indexed[row["url"]]
                        previous["discovered_sections"] = sorted(set(previous["discovered_sections"]+[row["section"]]))
                        previous["index_evidence"].extend(row["index_evidence"])
                        if previous["index_published_at"] != row["index_published_at"]:
                            previous.update(index_published_at=None, publication_date_error="conflicting_official_listing_dates")
        except Exception as exc:
            failures.append({"route": route, "error": type(exc).__name__ + ": " + str(exc)[:250]})
    with ThreadPoolExecutor(max_workers=3) as pool:
        verified = list(pool.map(lambda row: verify_item(client, row, as_of), indexed.values()))
    return routes, verified, failures
