"""Read-only directed QA of original Pulso runtime evidence.

A discovery PASS is not end-to-end acceptance. Even automated processing PASS
requires independent review of the actual published facts on the final SHA.
The frozen controls are a recall benchmark, never an inventory or publication
quota. This reader cannot change the queue, history, budget or source code.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

SOURCE = "pulso_latercera"
ROOT = Path(__file__).resolve().parents[1]
FROZEN_CONTROL_SHA256 = "b9c3ce2aea38107797fc19572581f27884d15611214fd2328d458bd35e906374"
WINDOWS = {"30": ("2026-09-11", "2026-10-10", 29), "90": ("2026-07-13", "2026-10-10", 79)}
REQUIRED_FEEDS = {"section:" + name for name in (
    "pulso", "nacional", "politica", "tendencias", "que-pasa", "paula", "sustentabilidad",
    "lt-board", "sociales", "servicios", "tecnologia", "la-tercera-pm", "horizontes",
)} | {"tag:" + name for name in ("salud", "isapres", "fonasa", "clinicas", "hospitales", "listas-de-espera", "banmedica")}
PRIMARY_DATE_SOURCES = {"visible_article_byline", "json_ld_datePublished", "article_published_time", "article_time"}
VIDEO_HOLD = "publisher_video_text_unavailable"
DATE_HOLD = "publisher_conflicting_publication_dates"
SHA = re.compile(r"[0-9a-f]{64}")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def normalized_url(value):
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value or "")
    if parsed.scheme != "https" or parsed.netloc not in {"www.latercera.com", "latercera.com"}:
        return None
    return urlunsplit(("https", "www.latercera.com", parsed.path.rstrip("/") + "/", "", ""))


def stamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def publisher_day(value):
    try:
        return date.fromisoformat(value).isoformat() if len(value) == 10 else (
            stamp(value).astimezone(ZoneInfo("America/Santiago")).date().isoformat())
    except (ValueError, TypeError, AttributeError):
        return None


def timestamp_calendar_day(value):
    """Keep the publisher's explicit ISO calendar; never infer a naive zone."""
    if isinstance(value, str) and len(value) == 10:
        return publisher_day(value)
    parsed = stamp(value)
    return parsed.date().isoformat() if parsed else None


def date_convention(values, visible_day):
    """All primary timestamps must corroborate one calendar convention."""
    if not values or not visible_day:
        return None
    calendar = [timestamp_calendar_day(value) for value in values]
    santiago = [publisher_day(value) for value in values]
    calendar_matches = all(day == visible_day for day in calendar)
    santiago_matches = all(day == visible_day for day in santiago)
    return ("calendar_agreement" if calendar_matches and santiago_matches else
            "timestamp_calendar" if calendar_matches else "america_santiago" if santiago_matches else None)


def visible_byline_day(text):
    months = {name: index for index, name in enumerate((
        "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
        "septiembre", "octubre", "noviembre", "diciembre"), 1)}
    match = re.fullmatch(r"\s*(\d{1,2})\s+(?:de\s+)?(" + "|".join(months) +
                         r")\s+(?:de\s+)?(\d{4})\s*", text.casefold())
    try:
        return date(int(match[3]), months[match[2]], int(match[1])).isoformat() if match else None
    except ValueError:
        return None


def queue_timestamp_corroborates(metadata, day):
    values = [entry.get("timestamp") for entry in metadata.get("publication_evidence", [])
              if isinstance(entry, dict)] or [metadata.get("publication_timestamp")]
    if metadata.get("publication_date_source") == "visible_article_byline":
        return (metadata.get("visible_publication_date") == day and
                date_convention(values, day) is not None)
    return all(publisher_day(value) == day for value in values)


def section_slug(value):
    if not isinstance(value, str):
        return None
    text = "".join(character for character in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


class PrimaryDates(HTMLParser):
    """Independent URL/date projection, without importing the source parser."""
    def __init__(self):
        super().__init__()
        self.canonical, self.published, self.nodes, self.parts = None, [], [], None
        self.article_depth, self.article_text, self.title_text = 0, [], []
        self.in_title, self.blocked = False, 0
        self.contexts, self.bylines, self.byline = [], [], None
        self.paragraph, self.primary_paragraphs, self.body_contexts = None, [], []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        classes = attr.get("class", "").split()
        blocked_context = (self.contexts[-1][1] if self.contexts else False) or tag in {
            "nav", "aside", "footer", "script", "style", "noscript"} or any(
            term in attr.get("class", "") for term in ("latest-news", "related", "story-card"))
        if tag not in {"meta", "link", "br", "hr", "img", "input", "source", "area", "base", "wbr", "embed", "param", "track", "col"}:
            self.contexts.append((tag, blocked_context))
            parent_body = self.body_contexts[-1][1] if self.body_contexts else False
            body = parent_body or tag == "article" or attr.get("itemprop") == "articleBody" or any(
                term in attr.get("class", "") for term in ("article-body__raw-html", "article-body__content", "body-chain", "article__body"))
            self.body_contexts.append((tag, body))
            if tag == "p" and body and not blocked_context:
                self.paragraph = []
        if (tag == "time" and "article-body__byline__date" in classes and not blocked_context
                and self.title_text and attr.get("itemprop") != "dateModified"):
            self.byline = dict(timestamp=attr.get("datetime"), text=[])
        if tag == "link" and "canonical" in attr.get("rel", "").split():
            self.canonical = normalized_url(attr.get("href"))
        if tag == "meta" and (attr.get("property") or attr.get("name")) == "article:published_time":
            self.published.append(attr.get("content"))
        if tag == "script" and attr.get("type") == "application/ld+json":
            self.parts = []
        if tag in {"script", "style", "noscript"}:
            self.blocked += 1
        if tag == "article":
            self.article_depth += 1
        if tag == "h1":
            self.in_title = True

    def handle_data(self, data):
        if self.parts is not None:
            self.parts.append(data)
        if not self.blocked and self.article_depth:
            self.article_text.append(data)
        if not self.blocked and self.in_title:
            self.title_text.append(data)
        if self.byline is not None and not self.blocked:
            self.byline["text"].append(data)
        if self.paragraph is not None and not self.blocked and not (self.contexts and self.contexts[-1][1]):
            self.paragraph.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.parts is not None:
            try:
                self.nodes.extend(self.walk(json.loads("".join(self.parts))))
            except (ValueError, TypeError):
                pass
            self.parts = None
        if tag in {"script", "style", "noscript"}:
            self.blocked = max(0, self.blocked - 1)
        if tag == "article":
            self.article_depth = max(0, self.article_depth - 1)
        if tag == "h1":
            self.in_title = False
        if tag == "time" and self.byline is not None:
            self.bylines.append(dict(timestamp=self.byline["timestamp"], text=" ".join(self.byline["text"])))
            self.byline = None
        if tag == "p" and self.paragraph is not None:
            self.primary_paragraphs.append(" ".join(" ".join(self.paragraph).split()))
            self.paragraph = None
        for index in range(len(self.contexts) - 1, -1, -1):
            if self.contexts[index][0] == tag:
                del self.contexts[index:]
                break
        for index in range(len(self.body_contexts) - 1, -1, -1):
            if self.body_contexts[index][0] == tag:
                del self.body_contexts[index:]
                break

    @classmethod
    def walk(cls, node):
        if isinstance(node, list):
            return [value for child in node for value in cls.walk(child)]
        if not isinstance(node, dict):
            return []
        return [node] + cls.walk(node.get("@graph", []))

    def publication_evidence_for(self, url):
        dates = list(self.published) if self.canonical == url else []
        for node in self.nodes:
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            entity = node.get("mainEntityOfPage")
            entity = entity.get("@id") if isinstance(entity, dict) else entity
            identities = (node.get("url"), node.get("@id"), entity)
            if "NewsArticle" in types and any(normalized_url(value) == url for value in identities if isinstance(value, str)):
                dates.append(node.get("datePublished"))
        if self.canonical == url and self.bylines:
            visible = {visible_byline_day(value["text"]) for value in self.bylines}
            if None in visible or len(visible) != 1:
                return dict(reason="ambiguous_or_invalid_primary_visible_byline")
            day = visible.pop()
            # The captured primary <time datetime> must identify the same
            # publication instant as URL-bound metadata, not a nearby event.
            instants = {stamp(value) for value in dates if stamp(value)}
            if any(not stamp(value["timestamp"]) or stamp(value["timestamp"]) not in instants for value in self.bylines):
                return dict(reason="primary_byline_timestamp_not_bound_to_metadata")
            convention = date_convention(dates + [value["timestamp"] for value in self.bylines], day)
            if not convention:
                return dict(reason="visible_byline_not_consistent_with_one_timestamp_convention")
            return dict(publication_date=day, publisher_date_convention=convention,
                        visible_bylines=self.bylines, primary_timestamps=dates)
        days = {publisher_day(value) for value in dates if publisher_day(value)}
        if len(days) == 1:
            return dict(publication_date=days.pop(), publisher_date_convention="america_santiago_metadata_only",
                        primary_timestamps=dates)
        return dict(reason="missing_or_conflicting_url_bound_primary_timestamps")

    def days_for(self, url):
        day = self.publication_evidence_for(url).get("publication_date")
        return {day} if day else set()

    def primary_text(self, url):
        for node in self.nodes:
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if "NewsArticle" in types and normalized_url(node.get("url") or node.get("@id")) == url:
                body, title = node.get("articleBody"), node.get("headline")
                if isinstance(body, str) and len(body.strip()) >= 160 and isinstance(title, str):
                    return title, body
        if self.canonical == url:
            return " ".join(self.title_text), " ".join(self.article_text)
        return "", ""

    def bound_nodes(self, url, required_type):
        result = []
        for node in self.nodes:
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            entity = node.get("mainEntityOfPage")
            entity = entity.get("@id") if isinstance(entity, dict) else entity
            if required_type in types and any(normalized_url(value) == url for value in (
                    node.get("url"), node.get("@id"), entity) if isinstance(value, str)):
                result.append(node)
        return result

    def strict_original_projection(self, url):
        """Expose publisher facts even when no publication day can be adopted."""
        articles = self.bound_nodes(url, "NewsArticle")
        if self.canonical != url or len(articles) != 1:
            raise ValueError("exception_original_identity_ambiguous_or_unbound")
        article = articles[0]
        values = [article.get("datePublished")] + self.published
        if not values or any(not timestamp_calendar_day(value) or not publisher_day(value) for value in values):
            raise ValueError("exception_original_timestamps_missing_or_invalid")
        visible = {visible_byline_day(value["text"]) for value in self.bylines}
        if not self.bylines or None in visible or len(visible) != 1:
            raise ValueError("exception_original_visible_byline_missing_or_ambiguous")
        instants = {stamp(value) for value in values if stamp(value)}
        if any(not stamp(value["timestamp"]) or stamp(value["timestamp"]) not in instants for value in self.bylines):
            raise ValueError("exception_original_byline_instant_unbound")
        title = article.get("headline") or " ".join(self.title_text)
        json_body = article.get("articleBody")
        body = " ".join(json_body.split()) if isinstance(json_body, str) and json_body.strip() else " ".join(self.primary_paragraphs)
        if not isinstance(title, str) or not title.strip():
            raise ValueError("exception_original_primary_title_missing")
        return dict(article=article, primary_timestamps=values, visible_publication_date=visible.pop(),
                    title=title, body=body)


def local_capture_path(root, relative):
    path = Path(relative or "")
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("unsafe_capture_path")
    if path.parts[0] == "responses":
        path = Path("data/audits/pulso_runtime_capture") / path
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("unsafe_capture_path")
    return target


def verify_primary_capture(row, root, date_evidence=None):
    """Require original bytes matching the primary detail hash and URL/date."""
    url, expected = row["url"], row.get("primary_detail_sha256")
    errors = []
    for record in row.get("original_http_captures", []):
        if record.get("status") != 200 or normalized_url(record.get("url")) != url:
            continue
        if expected not in {record.get("sha256"), record.get("returned_text_utf8_sha256")}:
            continue
        try:
            compressed = local_capture_path(root, record.get("gzip_file")).read_bytes()
            if record.get("gzip_sha256") and digest(compressed) != record["gzip_sha256"]:
                raise ValueError("gzip_sha256_mismatch")
            raw = gzip.decompress(compressed)
            if digest(raw) != record.get("sha256"):
                raise ValueError("original_bytes_sha256_mismatch")
            text = raw.decode(record.get("charset") or "utf-8", errors="replace")
            if digest(text.encode()) != expected:
                raise ValueError("primary_returned_text_sha256_mismatch")
            parser = PrimaryDates()
            parser.feed(text)
            if parser.canonical != url or parser.days_for(url) != {row.get("publication_date")}:
                raise ValueError("independent_primary_url_or_publication_date_mismatch")
            title, body = parser.primary_text(url)
            if len(title.strip()) < 18 or len(body.strip()) < 160:
                raise ValueError("original_primary_title_or_body_missing")
            if row.get("primary_detail_cache_hit"):
                if record.get("capture_provenance") != "preserved_original_http_response":
                    raise ValueError("cached_primary_capture_provenance_missing")
                if not SHA.fullmatch(str(record.get("original_capture_manifest_sha256", ""))):
                    raise ValueError("cached_primary_manifest_sha256_missing")
            if date_evidence is not None:
                date_evidence.update(parser.publication_evidence_for(url), url=url, original_html_sha256=expected)
            return None
        except (OSError, ValueError, TypeError, UnicodeError, EOFError) as error:
            errors.append(type(error).__name__ + ":" + str(error))
    return errors or ["matching_original_primary_capture_missing"]


def verify_publisher_exception(row, metadata, traces, root):
    """Verify a bounded publisher limitation against exact original HTML.

    This cannot excuse transport/parser failures or verify a textual control.
    The returned proof explicitly keeps publication and content availability
    separate; a conflicting original never acquires a convenient date.
    """
    url, expected = row.get("url"), row.get("primary_detail_sha256")
    reason = metadata.get("publisher_exception_reason") or metadata.get("source_content_unavailable_reason")
    errors = []
    if reason not in {VIDEO_HOLD, DATE_HOLD}:
        return None, ["unsupported_publisher_exception"]
    if (metadata.get("primary_identity_verified") is not True or metadata.get("article_verified") is not False
            or normalized_url(metadata.get("canonical_url")) != url or metadata.get("html_sha256") != expected
            or not SHA.fullmatch(str(expected or ""))):
        return None, ["exception_queue_identity_or_original_hash_unverified"]
    if not traces or any(trace.get("status") != "discovered_metadata_only" or trace.get("reason") != reason
                          or trace.get("primary_identity_verified") is not True
                          or trace.get("article_verified") is not False
                          or trace.get("html_sha256") != expected for trace in traces):
        return None, ["exception_not_bound_to_actual_core_traces"]
    for record in row.get("original_http_captures", []):
        if (record.get("status") != 200 or normalized_url(record.get("url")) != url
                or expected not in {record.get("sha256"), record.get("returned_text_utf8_sha256")}):
            continue
        try:
            base = Path(record.get("_capture_root") or root)
            compressed = local_capture_path(base, record.get("gzip_file")).read_bytes()
            if record.get("gzip_sha256") and digest(compressed) != record["gzip_sha256"]:
                raise ValueError("exception_original_gzip_hash_mismatch")
            raw = gzip.decompress(compressed)
            text = raw.decode(record.get("charset") or "utf-8", errors="replace")
            if digest(raw) != record.get("sha256") or digest(text.encode()) != expected:
                raise ValueError("exception_original_html_hash_mismatch")
            if row.get("primary_detail_cache_hit") and (
                    record.get("capture_provenance") != "preserved_original_http_response"
                    or not SHA.fullmatch(str(record.get("original_capture_manifest_sha256", "")))):
                raise ValueError("exception_cached_original_provenance_missing")
            parser = PrimaryDates()
            parser.feed(text)
            projection = parser.strict_original_projection(url)
            body, visible = projection["body"], projection["visible_publication_date"]
            values = projection["primary_timestamps"]
            queued_values = [entry.get("timestamp") for entry in metadata.get("publication_evidence", []) if isinstance(entry, dict)]
            if (not queued_values or not set(values) <= set(queued_values)
                    or any(value not in set(values) | {entry["timestamp"] for entry in parser.bylines} for value in queued_values)
                    or metadata.get("visible_publication_date") != visible):
                raise ValueError("exception_original_date_evidence_not_preserved")
            if (metadata.get("page_text") != body or metadata.get("article_body_characters") != len(body)
                    or metadata.get("article_body_sha256") != digest(body.encode())):
                raise ValueError("exception_primary_body_hash_or_text_disagrees")
            convention = date_convention(values + [entry["timestamp"] for entry in parser.bylines], visible)
            if reason == VIDEO_HOLD:
                videos = parser.bound_nodes(url, "VideoObject")
                if (urlsplit(url).path.split("/")[1] != "videos" or len(videos) != 1
                        or normalized_url(videos[0].get("url")) != url or videos[0].get("@id") != url + "#video"
                        or not videos[0].get("embedUrl") or convention is None or len(body.strip()) >= 160):
                    raise ValueError("exception_original_video_identity_date_or_unavailable_text_unverified")
                expected_video = dict(type="VideoObject", url=videos[0].get("url"), id=videos[0].get("@id"),
                                      embed_url=videos[0].get("embedUrl"), upload_date=videos[0].get("uploadDate"))
                if (metadata.get("video_evidence") != expected_video or metadata.get("video_identity_verified") is not True
                        or metadata.get("publisher_document_type") != "video" or metadata.get("article_body_complete") is not False
                        or metadata.get("publication_date_verified") is not True or metadata.get("publication_date") != visible
                        or row.get("publication_date") != visible or row.get("publication_date_verified") is not True
                        or metadata.get("source_quality_gate") != "deferred_video_text"
                        or any(trace.get("publication_date") != visible or trace.get("publication_date_verified") is not True
                               or trace.get("article_body_complete") is not False or trace.get("video_evidence") != expected_video for trace in traces)):
                    raise ValueError("exception_video_claims_do_not_match_original")
                publication_verified, content_verified = True, False
            else:
                possible = sorted({visible} | {timestamp_calendar_day(value) for value in values}
                                  | {publisher_day(value) for value in values})
                if convention is not None or len(body.strip()) < 160:
                    raise ValueError("exception_genuine_primary_date_conflict_not_proven")
                if (metadata.get("publication_date") is not None or metadata.get("publication_timestamp") is not None
                        or metadata.get("publication_date_verified") is not False or metadata.get("article_body_complete") is not True
                        or metadata.get("possible_publication_days") != possible or row.get("publication_date") is not None
                        or row.get("publication_date_verified") is not False
                        or metadata.get("publication_date_source") != "unresolved_primary_publisher_date_conflict"
                        or metadata.get("source_quality_gate") != "deferred_publication_date"
                        or metadata.get("editorial_hold") != DATE_HOLD
                        or any(trace.get("publication_date") is not None or trace.get("publication_date_verified") is not False
                               or trace.get("possible_publication_days") != possible for trace in traces)):
                    raise ValueError("exception_conflict_adopted_date_or_lost_original_days")
                publication_verified, content_verified = False, True
            return dict(url=url, reason=reason, original_html_sha256=expected,
                        publication_date_verified=publication_verified, article_content_verified=content_verified,
                        publication_date=visible if publication_verified else None,
                        visible_publication_date=visible, original_primary_timestamps=values,
                        publisher_date_convention=convention, body_characters=len(body)), None
        except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, EOFError) as error:
            errors.append(type(error).__name__ + ":" + str(error))
    return None, errors or ["matching_original_publisher_exception_capture_missing"]


def budget_delta(execution):
    delta = {}
    try:
        for tier in ("fast", "deep"):
            delta[tier] = {}
            for metric in ("attempted", "successful", "failed"):
                values = []
                for scope in ("run", "month"):
                    before = execution["budget_before"][scope][tier][metric]
                    after = execution["budget_after"][scope][tier][metric]
                    if type(before) is not int or type(after) is not int or before < 0 or after < before:
                        raise ValueError("ledger_counter_decreased_or_invalid")
                    values.append(after - before)
                if values[0] != values[1]:
                    raise ValueError("run_and_month_delta_disagree")
                delta[tier][metric] = values[0]
            if delta[tier]["attempted"] != delta[tier]["successful"] + delta[tier]["failed"]:
                raise ValueError("attempts_without_recorded_results")
        return delta, None
    except (KeyError, TypeError, ValueError) as error:
        return delta, str(error)


def workflow_limits(path):
    text = path.read_text()
    return dict(re.findall(r"^\s+(RADAR_(?:FAST|DEEP)_PER_(?:RUN|MONTH)):\s*(\d+)\s*$", text, re.M))


def api_page_key(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "www.latercera.com":
            return None
        query = json.loads(parse_qs(parsed.query)["query"][0])
        if parsed.path.endswith("/story-feed-sections-fetch"):
            feed = "section:" + query["includeSections"].lstrip("/")
        elif parsed.path.endswith("/story-feed-tag-fetch"):
            feed = "tag:" + query["tagSlug"]
        else:
            return None
        return feed, query["feedOffset"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def factual_api_urls(entries):
    urls = []
    for entry in entries:
        site = entry.get("websites", {}).get("la-tercera", {})
        candidate = site.get("website_url") or entry.get("website_url") or entry.get("canonical_url")
        url = normalized_url(urljoin("https://www.latercera.com/", candidate)) if isinstance(candidate, str) else None
        if not url:
            continue
        path = urlsplit(url).path
        if re.fullmatch(r"/[a-z0-9-]+/noticia/[^/]+(?:/[A-Za-z0-9]{26})?/", path) and path.split("/")[1] not in {
                "opinion", "editorial", "columnas", "cartas-al-director"}:
            urls.append(url)
    return urls


def verify_api_pages(pages, records, root, details=()):
    """HTTP hashes for the cursor chain; original JSON for first/boundary pages."""
    failures = []
    proof_offsets = {row.get("offset") for row in pages[:1] + pages[-3:]}
    for index, page in enumerate(pages):
        key = (page.get("feed"), page.get("offset"))
        if not SHA.fullmatch(str(page.get("json_sha256", ""))):
            failures.append(dict(code="public_api_page_hash_missing", offset=page.get("offset")))
            continue
        candidates = [record for record in records if api_page_key(record.get("url", "")) == key
                      and record.get("status") == 200
                      and page.get("json_sha256") in {record.get("sha256"), record.get("returned_text_utf8_sha256")}
                      and stamp(record.get("captured_at"))]
        if not candidates:
            failures.append(dict(code="public_api_http_chain_unproven", offset=page.get("offset")))
            continue
        if index and (pages[index - 1].get("next") != page.get("offset") or page.get("offset", -1) <= pages[index - 1].get("offset", -1)):
            failures.append(dict(code="public_api_cursor_chain_nonadvancing", offset=page.get("offset")))
        if page.get("offset") not in proof_offsets:
            continue
        verified = False
        for record in candidates:
            try:
                base = Path(record.get("_capture_root") or root)
                relative = Path(record.get("gzip_file") or "")
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("unsafe_capture_path")
                path = (base / relative).resolve()
                if not path.is_relative_to(base.resolve()):
                    raise ValueError("unsafe_capture_path")
                compressed = path.read_bytes()
                raw = gzip.decompress(compressed)
                text = raw.decode(record.get("charset") or "utf-8", errors="replace")
                if digest(raw) != record.get("sha256") or digest(text.encode()) != page.get("json_sha256"):
                    raise ValueError("raw_api_sha256_mismatch")
                if record.get("gzip_sha256") and digest(compressed) != record["gzip_sha256"]:
                    raise ValueError("raw_api_gzip_sha256_mismatch")
                document = json.loads(text)
                document = document.get("data", document)
                entries = document["content_elements"]
                if (not isinstance(entries, list) or len(entries) != page.get("primary_entries")
                        or document.get("count") != page.get("count") or document.get("next") != page.get("next")):
                    raise ValueError("raw_api_inventory_or_cursor_disagrees")
                days = [publisher_day(entry.get("first_publish_date")) for entry in entries]
                if page.get("inventory_day_max") and (None in days or max(days) != page["inventory_day_max"]):
                    raise ValueError("raw_api_publication_boundary_disagrees")
                if page.get("boundary_pages", 0) > 0:
                    cutoff = (date.fromisoformat(WINDOWS["90"][0]) - timedelta(days=2)).isoformat()
                    urls = factual_api_urls(entries)
                    if page.get("verified_details") != len(urls):
                        failures.append(dict(code="public_api_boundary_factual_details_incomplete", offset=page.get("offset")))
                    for url in urls:
                        traces = [row for row in details if normalized_url(row.get("url")) == url
                                  and row.get("status") in {"discovered", "discovered_metadata_only", "excluded"}]
                        if (not traces or any(row.get("publication_date_source") not in PRIMARY_DATE_SOURCES
                                              or row.get("publication_date_verified") is False
                                              or not SHA.fullmatch(str(row.get("html_sha256", "")))
                                              or not publisher_day(row.get("publication_date")) for row in traces)):
                            failures.append(dict(code="public_api_boundary_original_detail_date_unverified", offset=page.get("offset"), url=url))
                        elif len({row["publication_date"] for row in traces}) != 1 or traces[0]["publication_date"] >= cutoff:
                            failures.append(dict(code="public_api_boundary_detail_dates_not_old", offset=page.get("offset"), url=url))
                verified = True
                break
            except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, EOFError):
                continue
        if not verified:
            failures.append(dict(code="public_api_original_boundary_json_missing_or_invalid", offset=page.get("offset")))
    return failures


def capture_records(root, artifact=None):
    """Read live, retained or downloaded original proof without restoring state."""
    paths = [root / "data/audits/pulso_runtime_capture/manifest.json"] + [
        root / "tests/fixtures" / directory / "manifest.json" for directory in (
            "pulso_runtime_real", "pulso_editorial_exception_real", "pulso_thin_primary_real", "pulso_targeted_primary_real")]
    if artifact and artifact.exists():
        paths.extend(artifact.rglob("manifest.json"))
    records = []
    for path in paths:
        if not path.exists():
            continue
        value = json.loads(path.read_text())
        if value.get("source") == SOURCE:
            records.extend(dict(record, _capture_root=str(path.parent)) for record in value.get("requests", []))
    return records


def count_exhaustion_proven(summary, pages):
    """An exact, stable publisher total must bound a gap-free position traversal.

    A small invented summary total cannot override the original API count.
    Moving counts, gaps, overlaps or a capped total require another traversal;
    reaching an offset greater than the summary is not proof of exhaustion.
    Original first/last JSON counts are separately bound by verify_api_pages.
    """
    total = summary.get("publisher_count")
    if type(total) is not int or not 0 <= total < 10000 or not pages:
        return False
    expected_offset = 0
    for page in pages:
        entries, offset, count = page.get("primary_entries"), page.get("offset"), page.get("count")
        if (type(entries) is not int or not 0 <= entries <= 24
                or type(offset) is not int or offset != expected_offset
                or type(count) is not int or count != total):
            return False
        expected_offset += entries
        if expected_offset > total:
            return False
    return expected_offset == total


def evaluate(report, control, *, root, discovery, queue, history, snapshot, telemetry=(), control_sha=None, captures=(), phase="auto"):
    findings, checks = [], {}
    def fail(domain, code, **evidence):
        findings.append(dict(domain=domain, code=code, **evidence))
    execution = report.get("last_core_execution") or report.get("execution", {})
    mode = execution.get("mode")
    actual_processing = mode == "real_core_processing"
    processing = actual_processing and phase != "discovery"
    if mode not in {"discovery_only", "real_core_processing"}:
        fail("discovery", "genuine_core_execution_missing", mode=mode)
    if phase == "processing" and not actual_processing:
        fail("processing", "requested_processing_has_no_actual_processing_execution")
    if not execution.get("engine_called") or not execution.get("engine_completed"):
        fail("discovery", "core_did_not_complete", error=execution.get("error_type"))
    start, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    discovered_at = stamp(report.get("discovery_run_at"))
    if not start or not end or end < start or not discovered_at or not start <= discovered_at <= end:
        fail("discovery", "stale_or_unbound_discovery_timestamp")
    if report.get("runtime") != "daily_core" or report.get("selected_sources") != [SOURCE] or not report.get("core_source_present"):
        fail("discovery", "real_source_scoped_core_missing")
    if report.get("audit_discovery_error"):
        fail("discovery", "audit_discovery_error", error=report["audit_discovery_error"])
    if report.get("unrelated_queue_unchanged") is not True:
        fail("discovery", "other_source_queue_changed_or_unproven")
    if execution.get("ai_guardrails_modified") is not False:
        fail("discovery", "ai_guardrails_preservation_unproven")
    try:
        daily = workflow_limits(root / ".github/workflows/daily-radar.yml")
        recovery = workflow_limits(root / ".github/workflows/pulso-runtime-recovery.yml")
        if len(daily) != 4 or daily != recovery:
            fail("discovery", "recovery_budget_limits_differ_from_daily_core", daily=daily, recovery=recovery)
    except OSError as error:
        fail("discovery", "budget_workflow_evidence_missing", error=str(error))
    delta, error = budget_delta(execution)
    checks["actual_ai_budget_delta"] = delta
    if error:
        fail("discovery", "ai_ledger_invalid", error=error)
    elif not actual_processing and any(value for tier in delta.values() for value in tier.values()):
        fail("discovery", "discovery_consumed_analysis_budget")
    if control_sha != FROZEN_CONTROL_SHA256:
        fail("discovery", "independent_control_identity_not_frozen", expected_sha256=FROZEN_CONTROL_SHA256, observed_sha256=control_sha)
    if report.get("external_control_sha256") != control_sha:
        fail("discovery", "frozen_control_hash_mismatch")
    controls = {normalized_url(row.get("url")): row for row in control.get("articles", [])}
    rows = {row.get("url"): row for row in report.get("matrix", [])}
    details = discovery.get("source_details", {}).get(SOURCE, [])
    actual = {normalized_url(row.get("url")) for row in details if row.get("status") == "discovered"}
    metadata_only = {normalized_url(row.get("url")) for row in details if row.get("status") == "discovered_metadata_only"}
    if None in actual | metadata_only or actual & metadata_only:
        fail("discovery", "core_inventory_identity_or_text_metadata_partition_invalid")
    enumerated = actual | metadata_only
    for key, expected in (("current_core_discovered_urls", len(enumerated)),
                          ("current_core_verified_health_urls", len(actual)), ("metadata_only_candidates", len(metadata_only))):
        if key in report.get("counts", {}) and report["counts"][key] != expected:
            fail("discovery", "reported_inventory_partition_not_supported_by_core", field=key, expected=expected)
    errors = [row for row in details if row.get("status") == "detail_error"]
    if errors:
        fail("discovery", "unresolved_transport_or_primary_parser_errors", errors=errors)
    for days, (first, last, count) in WINDOWS.items():
        expected = {url for url, article in controls.items() if url and article.get("recall_expected")
                    and first <= (article.get("publication_date") or "") <= last}
        window = report.get("windows", {}).get(days, {})
        misses = sorted(expected - actual)
        checks["window_" + days] = dict(start=first, end=last, frozen_expected=len(expected), detected=len(expected & actual), misses=misses)
        if control.get("window_" + days, {}).get("start") != first or control.get("window_" + days, {}).get("end") != last:
            fail("discovery", "complete_calendar_window_changed", days=days)
        if (len(expected) != count or control.get("counts", {}).get("primary_recall_expected_" + days) != count
                or window.get("control_expected") != count or window.get("control_declared_expected") != count
                or window.get("control_denominator_consistent") is not True):
            fail("discovery", "frozen_control_denominator_changed", days=days, expected=count, observed=len(expected))
        if window.get("start") != first or window.get("end") != last:
            fail("discovery", "reported_window_incomplete", days=days)
        actual_recall = len(expected & actual) / len(expected) if expected else None
        if window.get("control_detected_by_current_core") != len(expected & actual) or window.get("recall") != actual_recall:
            fail("discovery", "reported_recall_not_supported_by_core_traces", days=days)
        if misses:
            fail("discovery", "important_external_control_omissions", days=days,
                 omissions=[dict(url=url, explanation=rows.get(url, {}).get("omission")) for url in misses])
        if window.get("date_conflicts"):
            fail("discovery", "external_publication_date_conflicts", days=days, urls=window["date_conflicts"])
    coverage = report.get("primary_coverage") or {}
    declared = set(coverage.get("required_feeds", []))
    summaries = {row.get("feed"): row for row in report.get("coverage", []) if row.get("status") == "public_feed_coverage"}
    if coverage.get("status") != "runtime_coverage" or coverage.get("coverage_complete") is not True or declared != REQUIRED_FEEDS:
        fail("discovery", "primary_required_public_feed_coverage_incomplete", missing=sorted(REQUIRED_FEEDS - declared))
    date_exception_count = 0
    feeds_without_content = []
    for name in REQUIRED_FEEDS:
        summary = summaries.get(name, {})
        ending = summary.get("termination")
        pages = [row for row in details if row.get("status") == "public_feed_page" and row.get("feed") == name]
        if not pages or pages[0].get("offset") != 0 or len(pages) != summary.get("pages_attempted"):
            fail("discovery", "complete_public_api_page_chain_missing", feed=name)
        for problem in verify_api_pages(pages, captures, root, details):
            fail("discovery", problem.pop("code"), feed=name, **problem)
        if not summary.get("coverage_complete") or summary.get("errors") != 0:
            fail("discovery", "feed_incomplete_or_errors", feed=name, summary=summary)
        elif ending == "three_publication_ordered_detail_verified_old_pages":
            boundary = pages[-3:]
            cutoff = (date.fromisoformat(WINDOWS["90"][0]) - timedelta(days=2)).isoformat()
            if len(boundary) != 3 or any(row.get("primary_entries") != 24 or not row.get("inventory_day_max")
                                       or row["inventory_day_max"] >= cutoff for row in boundary) or boundary[-1].get("boundary_pages", 0) < 3:
                fail("discovery", "three_old_pages_boundary_unproven", feed=name)
        elif ending == "all_feed_count_delimited_articles":
            if not count_exhaustion_proven(summary, pages):
                fail("discovery", "count_delimited_feed_exhaustion_unproven", feed=name,
                     summary_publisher_count=summary.get("publisher_count"),
                     last_page_count=pages[-1].get("count") if pages else None,
                     enumerated_entries=sum(row.get("primary_entries", 0) for row in pages if type(row.get("primary_entries")) is int))
        else:
            fail("discovery", "feed_cap_or_unknown_boundary", feed=name, termination=ending)
        conflicts = [row for row in details if row.get("feed") == name and row.get("publisher_exception_reason") == DATE_HOLD]
        videos = [row for row in details if row.get("feed") == name and row.get("status") == "discovered_metadata_only"
                  and row.get("source_content_unavailable_reason") == VIDEO_HOLD]
        date_exception_count += len(conflicts)
        if conflicts or videos:
            feeds_without_content.append(name)
        if conflicts and (summary.get("publisher_exceptions") != len(conflicts)
                          or summary.get("enumerated_with_editorial_exceptions") is not True
                          or summary.get("publication_date_coverage_complete") is not False):
            fail("discovery", "feed_date_exceptions_erased_or_falsely_verified", feed=name)
        if (conflicts or videos) and summary.get("article_content_coverage_complete") is not False:
            fail("discovery", "feed_exception_content_falsely_complete", feed=name)
    if date_exception_count and (coverage.get("publisher_exceptions") != date_exception_count
                                 or coverage.get("enumerated_with_editorial_exceptions") is not True
                                 or coverage.get("publication_date_coverage_complete") is not False):
        fail("discovery", "aggregate_date_exceptions_erased_or_falsely_verified")
    if feeds_without_content and coverage.get("article_content_coverage_complete") is not False:
        fail("discovery", "aggregate_exception_content_falsely_complete")
    checks["coverage_dimensions"] = dict(enumeration_complete=coverage.get("coverage_complete") is True,
        publication_dates_complete=coverage.get("publication_date_coverage_complete", not date_exception_count),
        article_content_complete=coverage.get("article_content_coverage_complete", not feeds_without_content),
        date_conflict_occurrences=date_exception_count, feeds_with_editorial_content_exceptions=sorted(feeds_without_content))
    current_queue = {}
    for fingerprint, item in queue.items():
        if item.get("source") == SOURCE:
            url = normalized_url(item.get("raw", {}).get("url"))
            current_queue.setdefault(url, []).append((fingerprint, item))
    for baseline in report.get("baseline_queue", []):
        candidates = current_queue.get(baseline.get("url"), [])
        item = next((item for key, item in candidates if key == baseline.get("fingerprint")), None)
        if (not item or any(item.get(key) != baseline.get(key) for key in ("lane", "detected_at"))
                or item.get("attempts", 0) < baseline.get("attempts", 0)
                or baseline.get("status") in {"published", "rejected", "archived"} and item.get("status") != baseline["status"]):
            fail("discovery", "baseline_queue_identity_or_bookkeeping_changed", url=baseline.get("url"))
    historical_urls = {normalized_url(row.get("source_url")) for row in history}
    feed_urls = {normalized_url(row.get("source_url")) for row in snapshot.get("signals", [])}
    for url in metadata_only:
        row = rows.get(url, {})
        traces = [trace for trace in details if normalized_url(trace.get("url")) == url
                  and trace.get("status") == "discovered_metadata_only"]
        if (row.get("current_core_detected") is not True or row.get("current_core_verified_health") is not False
                or row.get("metadata_only_candidate") is not True):
            fail("discovery", "metadata_inventory_falsely_labeled_verified_text", url=url)
        candidates = current_queue.get(url, [])
        if len(candidates) != 1:
            fail("discovery", "canonical_queue_missing_or_duplicated", url=url, count=len(candidates))
            continue
        item = candidates[0][1]
        raw = item.get("raw", {})
        metadata = raw.get("metadata", {})
        proof, error = verify_publisher_exception(row, metadata, traces, root)
        if error:
            fail("discovery", "publisher_exception_original_not_verified", url=url, errors=error)
        else:
            checks.setdefault("original_publisher_exception_validation", []).append(proof)
        reason = metadata.get("publisher_exception_reason") or metadata.get("source_content_unavailable_reason")
        assessment = metadata.get("editorial_assessment") or {}
        if (raw.get("event_date") != metadata.get("publication_date") or item.get("status") not in {"pending", "retry"}
                or assessment.get("decision") != "pending" or assessment.get("reason") != reason
                or any(assessment.get(key) is not None for key in ("relevance_score", "analysis_reason"))
                or row.get("exact_reason") != reason or row.get("passed_gate") is not None):
            fail("discovery", "publisher_exception_exact_editorial_hold_missing", url=url)
        if (url in historical_urls | feed_urls or row.get("history_present") or row.get("feed_present")
                or row.get("editorial_outcome") not in {"pending", "deferred"}):
            fail("discovery", "unverified_publisher_exception_published_or_terminal", url=url)
        captured = stamp(row.get("primary_detail_captured_at"))
        if not captured or end and captured > end or not row.get("primary_detail_cache_hit") and start and captured < start:
            fail("discovery", "publisher_exception_capture_freshness_unproven", url=url)
        if row.get("primary_detail_cache_hit") and not row.get("publisher_lastmod"):
            fail("discovery", "publisher_exception_cached_original_lastmod_missing", url=url)
        if reason == VIDEO_HOLD and row.get("publication_date_evidence") != (
                "reused_verified_primary_byline_unchanged_publisher_lastmod" if row.get("primary_detail_cache_hit") else "current_verified_detail"):
            fail("discovery", "publisher_video_date_falsely_labeled_fresh_or_unverified", url=url)
        if reason == DATE_HOLD and row.get("publication_date_evidence") != "unverified":
            fail("discovery", "publisher_conflict_falsely_labeled_verified_date", url=url)
    for url in actual:
        row = rows.get(url, {})
        if row.get("current_core_detected") is not True:
            fail("discovery", "matrix_not_bound_to_actual_discovery", url=url)
        if row.get("metadata_only_candidate") or row.get("current_core_verified_health") is False:
            fail("discovery", "verified_text_falsely_labeled_metadata_only", url=url)
        if row.get("publication_date_source") not in PRIMARY_DATE_SOURCES or not SHA.fullmatch(str(row.get("primary_detail_sha256", ""))):
            fail("discovery", "primary_publication_evidence_missing", url=url)
        if url in controls and controls[url].get("publication_date") != row.get("publication_date"):
            fail("discovery", "original_control_date_disagrees", url=url)
        if url in controls:
            canonical_section = urlsplit(url).path.strip("/").split("/")[0]
            control_section = section_slug(controls[url].get("section"))
            if control_section != canonical_section:
                fail("discovery", "external_control_section_not_bound_to_original_url", url=url)
            if section_slug(row.get("section")) != canonical_section:
                checks.setdefault("publisher_section_taxonomy_review", []).append(dict(
                    url=url, canonical_section=canonical_section, reported_section=row.get("section")))
            checks.setdefault("external_topic_comparison", []).append(dict(
                url=url, independent_topic=controls[url].get("topic"), publisher_topics=row.get("topics", []),
                policy="Independent topic and publisher taxonomy may be aliases; semantic comparison requires reviewer, not literal equality."))
        captured = stamp(row.get("primary_detail_captured_at"))
        if not captured or end and captured > end:
            fail("discovery", "primary_capture_timestamp_invalid", url=url)
        if row.get("primary_detail_cache_hit"):
            if (row.get("publication_date_evidence") != "reused_verified_primary_byline_unchanged_publisher_lastmod"
                    or not row.get("publisher_lastmod")):
                fail("discovery", "cached_primary_falsely_labeled_fresh_or_unbound", url=url)
        elif row.get("publication_date_evidence") != "current_verified_detail" or start and captured and captured < start:
            fail("discovery", "current_primary_capture_freshness_unproven", url=url)
        # Original bytes for every independent important control, not just a
        # manually chosen tiny positive sample. Other positives keep SHA traces.
        if url in controls and controls[url].get("recall_expected"):
            date_evidence = {}
            error = verify_primary_capture(row, root, date_evidence)
            if error:
                fail("discovery", "original_primary_capture_not_verified", url=url, errors=error)
            else:
                checks.setdefault("original_publication_date_validation", []).append(date_evidence)
        candidates = current_queue.get(url, [])
        if len(candidates) != 1:
            fail("discovery", "canonical_queue_missing_or_duplicated", url=url, count=len(candidates))
            continue
        metadata = candidates[0][1].get("raw", {}).get("metadata", {})
        if (metadata.get("article_verified") is not True or metadata.get("source_quality_gate") != "passed"
                or normalized_url(metadata.get("canonical_url")) != url
                or metadata.get("publication_date") != row.get("publication_date")
                or metadata.get("publication_date_source") not in PRIMARY_DATE_SOURCES
                or not queue_timestamp_corroborates(metadata, row.get("publication_date"))
                or metadata.get("html_sha256") != row.get("primary_detail_sha256")
                or len(str(metadata.get("page_text") or "").strip()) < 160):
            fail("discovery", "queue_primary_detail_evidence_unverified", url=url)
    if processing:
        if not delta.get("fast", {}).get("attempted") or not delta.get("fast", {}).get("successful"):
            fail("processing", "no_actual_successful_fast_editorial_analysis")
        events = [row for row in telemetry if stamp(row.get("at")) and start and end and start <= stamp(row["at"]) <= end and row.get("kind") == "fast"]
        if len(events) != delta.get("fast", {}).get("attempted") or sum(row.get("success") is True for row in events) != delta.get("fast", {}).get("successful"):
            fail("processing", "actual_api_telemetry_and_ledger_delta_disagree")
        if any(row.get("success") is True and not row.get("response_id") for row in events):
            fail("processing", "successful_analysis_without_actual_api_response_id")
        checks["actual_fast_response_events"] = len(events)
        feed = {normalized_url(row.get("source_url")): row for row in snapshot.get("signals", [])}
        historical = {normalized_url(row.get("source_url")): row for row in history}
        feed_evidence = report.get("feed_evidence", {})
        if not feed_evidence.get("serialized_feed_verified") or feed_evidence.get("generated_after_current_history") is not True:
            fail("processing", "actual_serialized_feed_missing_or_stale")
        if report.get("source_attribution_findings") or report.get("unresolved_recent_feed_exclusions"):
            fail("processing", "unresolved_media_attribution_or_feed_loss")
        if report.get("unresolved_pending_operational_reasons"):
            fail("processing", "pending_operational_reasons_unresolved")
        for url in actual:
            row = rows.get(url, {})
            reason = row.get("exact_reason") or ""
            if not reason or any(term in reason for term in ("no_editorial_verdict", "processor_rejected", "reason_missing", "unknown", "specific exclusion is not emitted")):
                fail("processing", "outcome_reason_unresolved", url=url, reason=reason)
            if row.get("consistency_findings") or row.get("traceability_unresolved"):
                fail("processing", "queue_history_feed_inconsistent", url=url)
            if bool(row.get("feed_present")) != (url in feed) or bool(row.get("history_present")) != (url in historical):
                fail("processing", "reported_history_or_feed_presence_not_actual", url=url)
            if len(current_queue.get(url, [])) != 1:
                continue
            item = current_queue[url][0][1]
            assessment = item.get("raw", {}).get("metadata", {}).get("editorial_assessment") or {}
            score = assessment.get("relevance_score")
            if score is not None and assessment.get("threshold") != 72:
                fail("processing", "media_editorial_threshold_changed", url=url, assessment=assessment)
            if url in controls and controls[url].get("recall_expected") and WINDOWS["30"][0] <= controls[url].get("publication_date", "") <= WINDOWS["30"][1]:
                if item.get("status") == "pending" or reason in {"analysis_unavailable", "article_verification_failed", "budget_or_analysis_deferred"}:
                    fail("processing", "recent_important_control_not_editorially_processed", url=url, reason=reason)
            if item.get("status") == "published":
                if assessment.get("decision") != "published" or type(score) is not int or score < 72 or not assessment.get("analysis_reason"):
                    fail("processing", "published_without_unchanged_editorial_gate_trace", url=url)
                published = historical.get(url, {})
                text = " ".join(str(published.get(key) or "") for key in ("title", "what_happened", "why_it_matters"))
                if (published.get("evidence_maturity") != "media_reported"
                        or not re.search(r"seg[uú]n\s+(?:pulso|la tercera)|(?:pulso|la tercera).*(?:report|inform|public|señal)", str(published.get("what_happened") or ""), re.I)
                        or published.get("publication_date") != row.get("publication_date")):
                    fail("processing", "published_media_attribution_or_real_date_invalid", url=url)
                if "presupuesto-salud-2027-rebajas" in url and not re.search(r"propuest|proyect|discusi|tramit", text, re.I):
                    fail("processing", "budget_proposal_presented_as_enacted", url=url)
                if "isapres-logran-detener-la-fuga" in url and (not re.search(r"mayo", text, re.I) or not re.search(r"contrat|suscrip|firm", text, re.I)):
                    fail("processing", "historical_contract_flow_period_or_metric_lost", url=url)
                if "senior-housing-los-grupos" in url and re.search(r"fne\s+(?:aprob[oó]|autoriz[oó])", text, re.I):
                    fail("processing", "publisher_fne_notification_upgraded_to_approval", url=url)
            elif item.get("status") == "rejected" and (assessment.get("decision") != "rejected" or not assessment.get("reason")):
                fail("processing", "rejection_without_exact_assessment", url=url)
            elif item.get("status") == "retry" and (assessment.get("decision") != "pending" or assessment.get("reason") != reason):
                fail("processing", "deferred_without_exact_assessment", url=url)
    discovery_failures = [row for row in findings if row["domain"] == "discovery"]
    processing_failures = [row for row in findings if row["domain"] == "processing"]
    return dict(schema_version=1, source=SOURCE, reviewed_code_sha=report.get("code_sha"), phase=mode, requested_phase=phase,
                discovery_qa="FAIL" if discovery_failures else "PASS",
                processing_qa=("FAIL" if processing_failures or discovery_failures else "PASS") if processing else "NOT_RUN",
                verdict="FAIL" if findings else "PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW" if processing else "PASS_DISCOVERY_ONLY_NOT_END_TO_END_ACCEPTANCE",
                acceptance="NOT_ACCEPTED" if findings or not processing else "PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW",
                findings=findings, checks=checks,
                limitations=["Frozen 29/79 controls benchmark recall; they are not a publication quota or proof of every publisher article.",
                             "Enumeration can pass with byte-verified publisher limitations; unresolved original dates and missing video text remain explicit editorial holds, not verified health coverage.",
                             "An automated PASS cannot settle semantic editorial correctness, final staging QA, or close issues/PR acceptance."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path, default=Path("data/audits/pulso_runtime_2026_10_11.json"))
    parser.add_argument("--control", type=Path, default=Path("data/audits/pulso_external_control_2026_10_11.json"))
    parser.add_argument("--output", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--discovery", action="store_true", help="Check discovery only; never infer end-to-end acceptance")
    modes.add_argument("--processing", action="store_true", help="Require a genuine processing execution and editorial outcomes")
    parser.add_argument("--capture-artifact", type=Path, default=Path(".scratch/pulso-prior-capture"))
    args = parser.parse_args()
    root = args.root.resolve()
    def path(value):
        return value if value.is_absolute() else root / value
    def read(value):
        return json.loads(path(Path(value)).read_text())
    try:
        report, control = read(args.report), read(args.control)
        history = read("data/history/superintendencia_signals.json")
        history = history.get("signals", []) if isinstance(history, dict) else history
        telemetry_path = root / "data/ai_usage/responses.jsonl"
        telemetry = [json.loads(line) for line in telemetry_path.read_text().splitlines() if line.strip()] if telemetry_path.exists() else []
        result = evaluate(report, control, root=root, discovery=read("data/state/discovery_run.json"),
                          queue=read("data/state/pending_queue.json"), history=history,
                          snapshot=read("web/data/radar_today.json"), telemetry=telemetry,
                          control_sha=digest(path(args.control).read_bytes()),
                          captures=capture_records(root, path(args.capture_artifact)),
                          phase="processing" if args.processing else "discovery" if args.discovery else "auto")
        if not args.discovery and (report.get("last_core_execution") or report.get("execution", {})).get("mode") == "real_core_processing":
            if report.get("feed_evidence", {}).get("sha256") != digest((root / "web/data/radar_today.json").read_bytes()):
                result["findings"].append(dict(domain="processing", code="serialized_feed_hash_changed_after_audit"))
                result.update(processing_qa="FAIL", verdict="FAIL", acceptance="NOT_ACCEPTED")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        result = dict(discovery_qa="FAIL", processing_qa="NOT_RUN", verdict="FAIL", acceptance="NOT_ACCEPTED",
                      findings=[dict(domain="evidence", code="required_evidence_unreadable", error=type(error).__name__ + ":" + str(error))])
    if args.output:
        destination = path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["verdict"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
