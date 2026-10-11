"""Independent saved-byte QA. Reads captures/inventory; writes only its work report.

No collector imports, no network client, no AI, no canonical-state mutations.
TLS checks validate recorded verified-TLS evidence; they do not retransmit requests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

UA = "AlicantoHealthRadar/1.0 (+https://github.com/cftorre1/Radar-salud; metadata monitoring, no model training)"
HOSTS = {"www.who.int", "who.int", "www.paho.org", "paho.org", "iris.paho.org"}
DOC_HOSTS = HOSTS | {"cdn.who.int", "iris.who.int"}
SAFE_HEADERS = {"content-type", "last-modified", "date", "server", "retry-after"}
MONTHS = {}
for number, words in enumerate([
    "January Jan enero", "February Feb febrero", "March Mar marzo", "April Apr abril",
    "May mayo", "June Jun junio", "July Jul julio", "August Aug agosto",
    "September Sep Sept septiembre", "October Oct octubre", "November Nov noviembre",
    "December Dec diciembre"], 1):
    MONTHS.update({word.casefold(): number for word in words.split()})
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def official_url(value, base=""):
    parts = urlsplit(urljoin(base, str(value)))
    if parts.scheme != "https" or parts.hostname not in HOSTS or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError("URL outside approved HTTPS public origins")
    query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"gclid", "fbclid"}]
    return urlunsplit(("https", parts.netloc.lower(), parts.path or "/", urlencode(query), ""))


def calendar_day(value, as_of):
    value = str(value or "").strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            result = date.fromisoformat(value)
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?", value):
            result = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        else:
            match = re.fullmatch(r"(\d{1,2})\s+(?:de\s+)?([A-Za-z]+)\.?\s+(?:(?:de|del)\s+)?(\d{4})", value)
            if not match or match[2].casefold() not in MONTHS:
                return None
            result = date(int(match[3]), MONTHS[match[2].casefold()], int(match[1]))
        return result.isoformat() if result <= as_of else None
    except (ValueError, TypeError):
        return None


def in_window(value, as_of, days):
    return bool(value and (as_of - timedelta(days=days - 1)).isoformat() <= value <= as_of.isoformat())


class NativeHTML(HTMLParser):
    """Streaming card/header reader; no collector DOM implementation is used."""
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.cards, self.h1, self.meta_dates, self.visible_dates = [], [], [], []
        self.canonical, self.alternates, self.documents = [], [], []
        self.forms, self.inputs, self.links, self.empty_messages = [], [], [], []
        self.feed(raw.decode("utf-8", errors="replace"))
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        if tag == "input":
            self.inputs.append(attrs)
            for frame in self.stack:
                if frame["tag"] == "form":
                    frame["inputs"].append(attrs)
        if tag == "meta":
            name = (attrs.get("property") or attrs.get("name") or "").casefold()
            if name in {"article:published_time", "datepublished", "citation_publication_date", "dc.date.issued"}:
                self.meta_dates.append(attrs.get("content", ""))
        if tag == "link":
            rel = set(attrs.get("rel", "").casefold().split())
            if "canonical" in rel and attrs.get("href"):
                self.canonical.append(attrs["href"])
            if "alternate" in rel and attrs.get("hreflang") and attrs.get("href"):
                self.alternates.append(attrs["href"])
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs)
            href = attrs["href"]
            if "language-link" in classes and attrs.get("hreflang"):
                self.alternates.append(href)
            if ".pdf" in href.casefold() or "/bitstream/" in href or "/bitstreams/" in href:
                self.documents.append(href)
        if tag == "time":
            for frame in self.stack:
                frame["times"].append(attrs.get("datetime", ""))
        if tag not in VOID:
            self.stack.append({"tag": tag, "attrs": attrs, "classes": classes,
                               "text": [], "links": [], "times": [], "inputs": []})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_data(self, text):
        for frame in self.stack:
            if frame["tag"] in {"a", "h1"} or frame["classes"] & {"date", "field--name-created", "views-field-title", "view-empty"}:
                frame["text"].append(text)

    def handle_endtag(self, tag):
        position = next((n for n in range(len(self.stack)-1, -1, -1) if self.stack[n]["tag"] == tag), None)
        if position is None:
            return
        while len(self.stack) > position:
            frame = self.stack.pop()
            text = " ".join(" ".join(frame["text"]).split())
            if frame["tag"] == "form":
                self.forms.append({"attrs": frame["attrs"], "inputs": frame["inputs"]})
            if "view-empty" in frame["classes"] and text:
                self.empty_messages.append(text)
            if frame["tag"] == "a":
                for parent in self.stack:
                    parent["links"].append((frame["attrs"].get("href", ""), text))
            if frame["tag"] == "h1" and text:
                self.h1.append(text)
            if frame["classes"] & {"date", "field--name-created"}:
                match = re.match(r"\s*(\d{1,2}\s+(?:de\s+)?[A-Za-z]+\s+(?:(?:de|del)\s+)?\d{4})\b", text)
                if match:
                    self.visible_dates.append(match[1])
            if "views-field-title" in frame["classes"]:
                links = [(href, title) for href, title in frame["links"] if href and title]
                times = list(self.stack[-1]["times"]) if self.stack else []
                self.cards.append({"links": links, "times": times})


def independent_index(raw, route, page_url, as_of):
    rows = []
    if route["format"] == "who_api":
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise ValueError("WHO native value array missing")
        prefix = {"news": "/news/item", "publications": "/publications/i/item",
                  "disease_outbreak_news": "/emergencies/disease-outbreak-news/item"}[route["section"]]
        for item in payload["value"]:
            suffix = str(item.get("ItemDefaultUrl") or "")
            if not suffix.startswith("/"):
                raise ValueError("WHO native item path missing")
            path = suffix if suffix.startswith(prefix + "/") else prefix + suffix
            raw_dates = [str(item[key]) for key in ("FormatedDate", "FormattedDate", "PublicationDateAndTime") if item.get(key)]
            values = [calendar_day(value, as_of) for value in raw_dates]
            day = values[0] if values and None not in values and len(set(values)) == 1 else None
            event = item.get("EmergencyEvent") or {}
            rows.append({"url": official_url(path, "https://www.who.int"), "published_at": day,
                         "event_id": event.get("EventId"), "event_date": event.get("EmergencyEventStartDate")})
    else:
        document = NativeHTML(raw)
        for card in document.cards:
            if len(card["links"]) != 1 or len(card["times"]) != 1:
                raise ValueError("native PAHO card date/title identity ambiguous")
            rows.append({"url": official_url(card["links"][0][0], page_url),
                         "published_at": calendar_day(card["times"][0], as_of),
                         "event_id": None, "event_date": None})
    return rows


def title_key(value):
    return "".join(char for char in str(value).casefold() if char.isalnum() or char == "_")


def title_equal(actual, expected, source, section):
    if title_key(actual) == title_key(expected):
        return True
    if source == "who" and section == "disease_outbreak_news":
        strip = lambda text: re.sub(r"\bthe (?=Russian Federation\s*$)", "", text, flags=re.I)
        return title_key(strip(actual)) == title_key(strip(expected))
    return False


def audit(captures, inventory_path, output):
    captures, inventory_path, output = captures.resolve(), inventory_path.resolve(), output.resolve()
    work = (Path.cwd() / "work").resolve()
    if not output.is_relative_to(work) or output.is_relative_to(captures) or output == inventory_path:
        raise ValueError("output must be a separate work report")
    inventory_bytes = inventory_path.read_bytes()
    inventory = json.loads(inventory_bytes)
    as_of = date.fromisoformat(inventory["as_of"])
    errors, records, bodies, input_hashes, matrix = [], {}, {}, {str(inventory_path): digest(inventory_bytes)}, []

    def check(condition, code, context):
        if not condition:
            errors.append({"code": code, "context": context})

    for path in sorted(captures.glob("*.json")):
        try:
            raw_json = path.read_bytes()
            record = json.loads(raw_json)
            url = official_url(record["requested_url"])
            key = digest(url.encode())[:24]
            if path.name != key + ".json" or record["body_file"] != key + ".body":
                raise ValueError("URL-derived capture filename binding failed")
            body_path = captures / record["body_file"]
            if body_path.resolve().parent != captures:
                raise ValueError("body path escaped captures")
            body = body_path.read_bytes()
            check(digest(body) == record["body_sha256"], "body_hash", path.name)
            check(len(body) == record["body_bytes"], "body_bytes", path.name)
            check(record["tls_verified"] is True, "recorded_tls", path.name)
            check(record["user_agent"] == UA, "declared_user_agent", path.name)
            check(set(record.get("headers", {})) <= SAFE_HEADERS, "unsafe_header_keys", path.name)
            stamp = datetime.fromisoformat(record["fetched_at"].replace("Z", "+00:00"))
            check(stamp.utcoffset() is not None, "capture_timestamp_offset", path.name)
            final_url = official_url(record["final_url"])
            previous = url
            chain = record.get("redirect_chain", [])
            check(len(chain) <= 10, "redirect_bound", path.name)
            is_robots = urlsplit(url).path == "/robots.txt"
            for hop in chain:
                check(official_url(hop["from_url"]) == previous, "redirect_chain_from", path.name)
                check(hop["http_status"] in {301, 302, 303, 307, 308}, "redirect_http_status", path.name)
                check(hop.get("tls_verified") is True, "redirect_recorded_tls", path.name)
                previous = official_url(hop["location"])
                if is_robots:
                    check(urlsplit(previous).path == "/robots.txt", "robots_redirect_to_content", path.name)
                else:
                    check(hop.get("destination_robots_checked") is True, "redirect_robots_marker", path.name)
            check(previous == final_url, "redirect_final_binding", path.name)
            records[url], bodies[url] = record, body
            input_hashes[str(path)] = digest(raw_json)
            input_hashes[str(body_path)] = digest(body)
            matrix.append({"url": url, "final_url": final_url, "http_status": record["http_status"],
                           "origin_json_sha256": digest(raw_json), "body_sha256": digest(body),
                           "body_bytes": len(body), "recorded_tls_verified": record["tls_verified"],
                           "redirect_hops": len(chain), "robots_policy_checked": is_robots})
        except Exception as exc:
            errors.append({"code": "capture_record_invalid", "context": path.name, "error": str(exc)[:200]})
    check(bool(records), "capture_records_missing", str(captures))
    robots_cache = {}
    for entry in matrix:
        url = entry["url"]
        if urlsplit(url).path == "/robots.txt":
            continue
        try:
            for target in [url] + [hop["location"] for hop in records[url].get("redirect_chain", [])] + [entry["final_url"]]:
                target = official_url(target)
                origin = urlunsplit((*urlsplit(target)[:2], "", "", ""))
                if origin not in robots_cache:
                    policy_url = origin + "/robots.txt"
                    policy = records[policy_url]
                    if policy["http_status"] != 200 or policy["tls_verified"] is not True:
                        raise ValueError("robots capture unavailable/unverified")
                    text = bodies[policy_url].decode("utf-8", errors="replace")
                    if re.search(r"<(?:!doctype|html|script|h1)\b", text, re.I):
                        raise ValueError("robots response is HTML")
                    parser = RobotFileParser()
                    parser.parse(text.splitlines())
                    robots_cache[origin] = parser
                check(robots_cache[origin].can_fetch(UA, target), "robots_disallowed", target)
            entry["robots_policy_checked"] = True
        except Exception as exc:
            errors.append({"code": "robots_evidence_invalid", "context": url, "error": str(exc)[:200]})

    pages, index_rows, page_readers, page_rows, partition_results = [], {}, {}, {}, []
    native_90 = {"who": set(), "paho": set()}
    for route_result in inventory["routes"]:
        route = route_result["route"]
        for page in route_result["pages"]:
            try:
                url = official_url(page["url"])
                record = records[url]
                check(page["capture"] == record, "page_capture_metadata", url)
                check(record["http_status"] == 200, "claimed_index_http", url)
                rows = independent_index(bodies[url], route, url, as_of)
                page_rows[url] = rows
                if route["format"] == "paho_html":
                    reader = page_readers.setdefault(url, NativeHTML(bodies[url]))
                    query = parse_qsl(urlsplit(url).query, keep_blank_values=True)
                    bounds = {key: value for key, value in query if key in {"date[min]", "date[max]"}}
                    if bounds:
                        check(len([key for key, _ in query if key in bounds]) == 2 and set(bounds) == {"date[min]", "date[max]"}, "date_query_unambiguous", url)
                        echoed = {node.get("name"): node.get("value") for node in reader.inputs if node.get("name") in bounds}
                        check(echoed == bounds, "date_query_echo", url)
                        check(all(row["published_at"] and bounds["date[min]"] <= row["published_at"] <= bounds["date[max]"] for row in rows), "native_dates_inside_query_bounds", url)
                control = [{"url": row["url"], "published_at": row["published_at"]} for row in rows]
                check(control == page.get("native_control"), "independent_native_control", url)
                check(len(rows) == page["native_records"], "native_record_count", url)
                parsed = {row["url"]: row for row in page["items"]}
                check(set(parsed) == {row["url"] for row in rows}, "native_collector_URL_coverage", url)
                for row in rows:
                    if row["url"] in parsed:
                        check(parsed[row["url"]]["index_published_at"] == row["published_at"], "native_collector_date", row["url"])
                    index_rows[(url, row["url"])] = row
                    if in_window(row["published_at"], as_of, 90):
                        native_90[route["source"]].add(row["url"])
                pages.append({"source": route["source"], "section": route["section"], "url": url,
                              "native_records": len(rows), "body_sha256": digest(bodies[url])})
            except Exception as exc:
                errors.append({"code": "native_page_invalid", "context": page.get("url"), "error": str(exc)[:200]})

        if route_result.get("date_partitions"):
            try:
                form_capture = route_result["date_filter_form_evidence"]
                landing = official_url(route["url"])
                check(form_capture == records[landing], "date_form_capture_binding", landing)
                forms = NativeHTML(bodies[landing]).forms
                forms = [form for form in forms if form["attrs"].get("method", "").casefold() == "get"
                         and {"date[min]", "date[max]"} <= {node.get("name") for node in form["inputs"]}]
                check(len(forms) == 1 and official_url(forms[0]["attrs"].get("action", ""), landing).split("?")[0] == landing.split("?")[0], "official_date_form_identity", landing)
                slices = sorted(route_result["date_partitions"], key=lambda part: part["from"])
                contiguous = (date.fromisoformat(slices[0]["from"]) == as_of - timedelta(days=89)
                              and date.fromisoformat(slices[-1]["to"]) == as_of
                              and all(date.fromisoformat(a["to"]) + timedelta(days=1) == date.fromisoformat(b["from"]) for a, b in zip(slices, slices[1:])))
                if route_result["archive_complete"]:
                    check(contiguous and route_result.get("unvisited_partitions") == 0 and all(part["archive_complete"] for part in slices), "partition_full_window_claim", landing)
                for part in slices:
                    requested = official_url(part["url"])
                    expected = {"date[min]": part["query_from"], "date[max]": part["query_to"]}
                    span = (date.fromisoformat(part["to"]) - date.fromisoformat(part["from"])).days + 1
                    check(0 < span <= route["date_slice_days"], "partition_slice_span_contract", requested)
                    check(date.fromisoformat(part["query_from"]) == date.fromisoformat(part["from"]) - timedelta(days=1)
                          and date.fromisoformat(part["query_to"]) == date.fromisoformat(part["to"]) + timedelta(days=1), "declared_one_day_query_overlap", requested)
                    matching = [official_url(page["url"]) for page in route_result["pages"]
                                if {k: v for k, v in parse_qsl(urlsplit(page["url"]).query) if k in expected} == expected]
                    check(len(matching) == part["pages"] and requested in matching, "partition_page_receipts", requested)
                    ordered = sorted(matching, key=lambda url: int(dict(parse_qsl(urlsplit(url).query)).get("page", 0)))
                    indices = [int(dict(parse_qsl(urlsplit(url).query)).get("page", 0)) for url in ordered]
                    check(indices == list(range(len(indices))), "partition_contiguous_page_numbers", requested)
                    if part["archive_complete"]:
                        check(bool(ordered), "complete_partition_missing_pages", requested)
                        terminal = ordered[-1]
                        if part["stop_reason"] == "date_partition_official_empty":
                            check(not page_rows[terminal] and bool(page_readers[terminal].empty_messages), "partition_native_empty_evidence", terminal)
                        elif part["stop_reason"] == "date_partition_native_archive_exhausted_after_public_end_probe":
                            previous = ordered[:-1]
                            check(bool(page_rows[terminal]) and any(page_rows[old] == page_rows[terminal] for old in previous), "partition_terminal_repeat_dates_and_urls", terminal)
                        elif part["stop_reason"] == "verified_older_boundary":
                            dates = [row["published_at"] for page_url in ordered for row in page_rows[page_url]]
                            check(bool(dates) and all(dates) and dates == sorted(dates, reverse=True)
                                  and min(dates) < (as_of - timedelta(days=89)).isoformat(), "partition_verified_older_calendar_boundary", terminal)
                        else:
                            check(False, "unrecognized_partition_completion_contract", terminal)
                        for page_url in ordered:
                            last = [anchor["href"] for anchor in page_readers[page_url].links if "last" in anchor.get("rel", "").split()]
                            check(all(int(dict(parse_qsl(urlsplit(href).query)).get("page", 0)) < 8 for href in last), "complete_partition_native_cap_reached", page_url)
                    partition_results.append({"source": route["source"], "section": route["section"], "from": part["from"], "to": part["to"],
                                              "query_from": part["query_from"], "query_to": part["query_to"], "pages": len(matching),
                                              "archive_complete": part["archive_complete"], "stop_reason": part["stop_reason"]})
            except Exception as exc:
                errors.append({"code": "partition_evidence_invalid", "context": route["url"], "error": str(exc)[:200]})

    detail_results, readers = [], {}
    detected = {"who": set(), "paho": set()}
    for item in inventory["items"]:
        check(item.get("publication_ready") is False, "automatic_publication_ready", item["url"])
        check(item.get("content_use") == "metadata_and_link_only", "item_content_mode", item["url"])
        aliases = item.get("source_aliases", [item["url"]])
        check(item["url"] in aliases and len(aliases) == len(set(aliases)), "alias_identity", item["url"])
        detected[item["source"]].update(aliases)
        members = item.get("translation_members") or [item]
        check({member["url"] for member in members} == set(aliases), "translation_member_aliases", item["url"])
        for member in members:
            url = member["url"]
            try:
                dates = []
                for evidence in member["index_evidence"]:
                    listing = official_url(evidence["listing_url"])
                    record = records[listing]
                    check(all(evidence.get(key) == record.get(key) for key in ("body_sha256", "fetched_at", "http_status", "tls_verified")), "index_evidence_binding", url)
                    dates.append(index_rows[(listing, url)]["published_at"])
                expected = dates[0] if dates and None not in dates and len(set(dates)) == 1 else None
                check(member["index_published_at"] == expected, "item_native_publication_date", url)
                all_observed = [row["published_at"] for (_, native_url), row in index_rows.items() if native_url == url]
                all_day = all_observed[0] if all_observed and None not in all_observed and len(set(all_observed)) == 1 else None
                check(member["index_published_at"] == all_day, "all_observed_index_dates_fail_closed", url)
                detail = member.get("detail_evidence")
                if member.get("detail_verified"):
                    check(bool(detail), "verified_detail_missing", url)
                    record = records[official_url(url)]
                    check(detail["capture"] == record, "detail_capture_metadata", url)
                    check(record["http_status"] == 200, "verified_detail_http", url)
                    check(official_url(record["final_url"]).rstrip("/") == official_url(url).rstrip("/"), "verified_detail_final_identity", url)
                    reader = readers.setdefault(url, NativeHTML(bodies[official_url(url)]))
                    check(len(reader.h1) == 1, "verified_detail_unique_H1", url)
                    check(title_equal(reader.h1[0], member["title"], item["source"], item["section"]), "verified_detail_native_title", url)
                    meta = detail["metadata"]
                    check(meta["title"] == reader.h1[0], "detail_metadata_title", url)
                    raw_dates = reader.meta_dates + reader.visible_dates
                    valid_dates = sorted({value for raw in raw_dates if (value := calendar_day(raw, as_of))})
                    invalid = [raw for raw in raw_dates if calendar_day(raw, as_of) is None]
                    check(meta["publication_dates"] == valid_dates, "detail_metadata_dates", url)
                    check(meta.get("invalid_or_future_publication_fields", []) == invalid, "detail_metadata_invalid_dates", url)
                    canonical = {official_url(value, url) for value in reader.canonical} or {official_url(url)}
                    check(len(canonical) == 1 and official_url(meta["canonical_url"], url) in canonical, "detail_canonical_metadata", url)
                    check(canonical == {official_url(url)}, "verified_detail_canonical_identity", url)
                    alternatives = sorted({official_url(value, url) for value in reader.alternates
                                           if urlsplit(urljoin(url, value)).hostname in {"www.who.int", "www.paho.org"}})
                    check(meta["alternate_language_urls"] == alternatives, "native_language_aliases", url)
                    docs = sorted({urljoin(url, value) for value in reader.documents
                                   if urlsplit(urljoin(url, value)).scheme == "https" and urlsplit(urljoin(url, value)).hostname in DOC_HOSTS})
                    check(meta["document_links"] == docs, "native_document_links", url)
                    published = member.get("published_at")
                    if published:
                        check(not invalid and len(valid_dates) <= 1 and (not valid_dates or valid_dates[0] == expected) and published == expected,
                              "claimed_exact_publication", url)
                    detail_results.append({"url": url, "native_publication_day": expected,
                                           "publication_day": published, "body_sha256": digest(bodies[official_url(url)]),
                                           "identity_verified": True, "declared_date_fields": len(raw_dates)})
                else:
                    check(not member.get("published_at") or member.get("technical_error"), "unverified_detail_not_declared", url)
            except Exception as exc:
                errors.append({"code": "detail_invalid", "context": url, "error": str(exc)[:200]})
        if len(aliases) > 1:
            connected = {item["url"]}
            while True:
                larger = connected | {b for a in connected for b in aliases if a in readers and b in readers
                                      and b in {official_url(x, a) for x in readers[a].alternates if urlsplit(urljoin(a,x)).hostname in {"www.who.int","www.paho.org"}}
                                      and a in {official_url(x, b) for x in readers[b].alternates if urlsplit(urljoin(b,x)).hostname in {"www.who.int","www.paho.org"}}}
                if larger == connected:
                    break
                connected = larger
            check(connected == set(aliases), "reciprocal_language_alias_group", item["url"])
            if len({member.get("published_at") for member in members}) > 1:
                check(item.get("published_at") is None and item.get("reason") == "translation_publication_date_conflict", "translation_date_conflict", item["url"])

    health_summary = {}
    for source in ("who", "paho"):
        source_items = [item for item in inventory["items"] if item["source"] == source]
        health = inventory["source_health"][source]
        counts = {str(days): sum(bool(item.get("detail_verified") and in_window(item.get("published_at"), as_of, days)) for item in source_items) for days in (30, 90)}
        check(health["counts"] == counts and health["recent_items"] == counts["30"] and health["unique_items"] == counts["90"], "verified_health_counts", source)
        recall = health["discovery_recall_90"]
        check(recall.get("inventory_url_count", recall.get("inventory_90_url_count")) == len(native_90[source]) and recall["detected"] == len(native_90[source] & detected[source])
              and recall["omitted_urls"] == sorted(native_90[source] - detected[source]), "native_recall_health", source)
        check(recall["whole_source_archive_claim"] is False, "whole_source_archive_claim", source)
        check(health["published"] == 0 and health["publication_activation"] is False, "health_publication_activation", source)
        check(health["pages_checked"] == sum(page["source"] == source for page in pages), "pages_checked_health", source)
        health_summary[source] = {"counts": counts, "native_90_URLs": len(native_90[source]),
                                  "detected_native_90_URLs": len(native_90[source] & detected[source]),
                                  "coverage_completeness": health["coverage_completeness"],
                                  "recurrent_operation_proven": health["recurrent_operation_proven"]}
    reuters = inventory["source_health"]["reuters"]
    check(reuters["checked_at"] is None and reuters["counts"] == {"30": None, "90": None}
          and reuters["technical_status"] == "not_polled_license_hold" and reuters["pages_checked"] == 0,
          "reuters_license_hold", "reuters")
    check(inventory["paid_ai_calls"] == 0 and inventory["publication_count"] == 0 and inventory["default_window_days"] == 30
          and inventory["maximum_editorial_topics"] == 10 and inventory["content_use"] == "metadata_and_link_only",
          "global_contract", "inventory")
    topics = inventory["editorial_topics"]
    check(len(topics) <= 10, "topic_limit", "topics")
    item_by_url = {item["url"]: item for item in inventory["items"]}
    for topic in topics:
        item = item_by_url.get(topic["representative_url"])
        check(bool(item and item["detail_verified"] and in_window(item["published_at"], as_of, 30)
                   and item["classification"]["materiality"] == "candidate"), "topic_eligible_metadata", topic["topic_id"])
        check(topic["publication_ready"] is False and topic["status"] == "pending_editorial"
              and topic["chile_transfer"] == "hypothesis_only" and topic["independence_groups"] == ["WHO_UN_SYSTEM"],
              "topic_no_false_publication_corroboration", topic["topic_id"])
    after = {path: digest(Path(path).read_bytes()) for path in input_hashes}
    check(after == input_hashes, "audit_mutated_inputs", "all_input_files")
    report = {"result": "FAIL" if errors else "PASS", "reviewer": "independent /root/reviewer",
              "created_at": datetime.now(timezone.utc).isoformat(), "run_id": inventory["run_id"],
              "auditor_script_sha256": digest(Path(__file__).read_bytes()),
              "inventory_sha256": digest(inventory_bytes), "captures": len(records),
              "captured_http_statuses": dict(Counter(str(entry["http_status"]) for entry in matrix)),
              "native_pages": len(pages), "verified_language_detail_checks": len(detail_results),
              "deduplicated_items": len(inventory["items"]), "editorial_topics": len(topics),
              "source_summary": health_summary, "records": matrix, "pages": pages, "details": detail_results, "date_partitions": partition_results,
              "network_requests": 0, "paid_ai_calls": 0, "canonical_state_writes": 0,
              "inputs_unchanged": after == input_hashes, "input_file_count": len(input_hashes),
              "TLS_scope": "Recorded verified-TLS evidence and redirect binding; no retransmission or independent new certificate handshake.",
              "historical_archive_scope": "Recalls declared observed native surfaces; does not prove a complete historical publisher archive.",
              "errors": errors}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("result", "run_id", "captures", "native_pages", "verified_language_detail_checks", "network_requests", "paid_ai_calls")}, ensure_ascii=False))
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return audit(args.captures, args.inventory, args.output)


if __name__ == "__main__":
    sys.exit(main())
