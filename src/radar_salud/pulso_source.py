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
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from zoneinfo import ZoneInfo

from .models import RawItem
from .scouts import fetch_html

HOSTS = {"www.latercera.com", "latercera.com"}
ARTICLE_PATH = re.compile(r"/[a-z0-9-]+/noticia/[^/]+(?:/[A-Za-z0-9]{26})?/?")
EXCLUDED_SECTIONS = {"opinion", "editorial", "columnas", "cartas-al-director"}
_OPINION_LABELS = {"opinión", "opinion", "columna", "columna de opinión", "columna de opinion", "editorial"}
_SPONSORED_SECTIONS = {"branded", "publirreportajes"}
LISTINGS = (
    "https://www.latercera.com/canal/pulso/",
    "https://www.latercera.com/canal/nacional/",
    "https://www.latercera.com/etiqueta/isapres/",
    "https://www.latercera.com/etiqueta/fonasa/",
    "https://www.latercera.com/etiqueta/clinicas/",
    "https://www.latercera.com/etiqueta/salud/",
)


_RETRY_HTTP_CODES = {408, 429, 500, 502, 503, 504}


def _request_with_retries(loader, url, audit=None, *, scope="article_detail", feed=None):
    """Retry only temporary transport failures on the identical public URL."""
    events = []
    for attempt in range(1, 4):
        try:
            payload = loader(url)
        except Exception as exc:
            transient = (exc.code in _RETRY_HTTP_CODES if isinstance(exc, HTTPError) else
                         isinstance(exc, (URLError, TimeoutError, ConnectionError)))
            if not transient:
                raise
            event = dict(url=url, status="request_retry", scope=scope, feed=feed,
                         attempt=attempt, max_attempts=3, will_retry=attempt < 3,
                         recovered=False, reason=str(exc), error_type=type(exc).__name__,
                         http_status=exc.code if isinstance(exc, HTTPError) else None)
            events.append(event)
            if audit is not None:
                audit.append(event)
            if attempt == 3:
                raise
            sleep(attempt)  # bounded one/two-second backoff, preserving URL/query
        else:
            for event in events:
                event.update(recovered=True, succeeded_on_attempt=attempt)
            return payload


def article_url(value, base=LISTINGS[0]):
    parsed = urlparse(urljoin(base, value or ""))
    if (parsed.scheme != "https" or parsed.netloc not in HOSTS
            or not ARTICLE_PATH.fullmatch(parsed.path)
            or parsed.path.split('/')[1] in EXCLUDED_SECTIONS):
        return None
    return "https://www.latercera.com" + parsed.path.rstrip("/") + "/"


def health_anchor(text):
    return bool(re.search(
        r"\bsalud\b|\bcesfam\b|cl[ií]nica|hospital|isapre|fonasa|prestador|"
        r"medicamento|farmac|aseguramiento|seguro de salud|"
        r"banm[eé]dica|bupa|redsalud|consalud|colmena|cruz blanca|"
        r"masvida|uc christus|listas? de espera|senior housing|"
        r"residencias? (?:para|de) adultos mayores|eleam|"
        r"vacun|c[aá]ncer|oncolog|sanitari|atenci[oó]n primaria|"
        r"epidemi|trasplante|discapacidad|ley ricarte soto|cenabast|"
        r"insulina|diabetes|compin|licencias m[eé]dicas|ficha cl[ií]nica",
        text or "", re.I))


def article_body_evidence(body):
    """Retain all primary text emitted by the verified article extractor."""
    return dict(page_text=body, article_body_characters=len(body),
                article_body_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest())


def complete_article_body(metadata):
    """A saved excerpt cannot stand in for the original primary body.

    Earlier caches retained only 18,000 characters while hashing the full
    article. Missing or inconsistent proof requires fresh original extraction.
    """
    body, expected = metadata.get("page_text"), metadata.get("article_body_sha256")
    return (isinstance(body, str) and len(body.strip()) >= 160
            and isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected) is not None
            and hashlib.sha256(body.encode("utf-8")).hexdigest() == expected
            and metadata.get("article_body_characters", len(body)) == len(body))


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
        self.body_paragraphs = []
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
            if frame["paragraph"]:
                self.body_paragraphs.append(value)
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


class _LiveblogEntries(HTMLParser):
    """Bind displayed entry dates, headings and primary text to one fragment."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.entries, self.duplicates = [], {}, set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in _Article.VOID:
            return
        parent = self.stack[-1] if self.stack else {}
        entry = parent.get("entry")
        if "liveblog-entry" in attrs.get("class", "").split():
            fragment = attrs.get("id", "")
            if fragment in self.entries:
                self.duplicates.add(fragment)
            entry = self.entries.setdefault(fragment, dict(times=[], headline=[], paragraphs=[], heading_seen=False))
        first_heading = (entry is not None and not entry["heading_seen"] and tag in ("h1", "h2", "h3"))
        if first_heading:
            # Historical liveblogs use H3; a later heading can introduce a
            # subsection inside this same update, rather than its headline.
            entry["heading_seen"] = True
        frame = dict(tag=tag, entry=entry,
                     blocked=parent.get("blocked", False) or tag in ("script", "style", "noscript"),
                     heading=parent.get("heading", False) or first_heading,
                     time=parent.get("time"), paragraph=parent.get("paragraph"))
        if entry is not None and tag == "time" and "liveblog-entry__date" in attrs.get("class", "").split():
            frame["time"] = dict(timestamp=attrs.get("datetime"), visible=[])
            entry["times"].append(frame["time"])
        if entry is not None and tag == "p" and "article-body__paragraph" in attrs.get("class", "").split():
            frame["paragraph"] = []
            entry["paragraphs"].append(frame["paragraph"])
        self.stack.append(frame)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _Article.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if not self.stack or self.stack[-1]["blocked"]:
            return
        frame = self.stack[-1]
        if frame["entry"] is None:
            return
        if frame["heading"]:
            frame["entry"]["headline"].append(data)
        if frame["time"] is not None:
            frame["time"]["visible"].append(data)
        if frame["paragraph"] is not None:
            frame["paragraph"].append(data)


def _liveblog_visible_day(text, timestamp):
    match = re.fullmatch(r"(\d{1,2})\s+(" + "|".join(_SPANISH_MONTHS)
                         + r")(?:\s+(\d{4})(?:\s+a las\s+(\d{1,2}):(\d{2}))?)?", text.lower())
    day = _publisher_day(timestamp)
    if not match or not day or (int(match[1]), _SPANISH_MONTHS[match[2]]) != (
            date.fromisoformat(day).day, date.fromisoformat(day).month):
        raise ValueError("liveblog_visible_entry_day_mismatch")
    local = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Santiago"))
    if ((match[3] and int(match[3]) != local.year)
            or (match[4] and (int(match[4]), int(match[5])) != (local.hour, local.minute))):
        raise ValueError("liveblog_visible_entry_time_mismatch")
    return day


def _liveblog_temporal_evidence(node, html, expected, metadata, body, parser=None):
    """Entry timestamps supplement, and never replace, the document's date.

    Preserve raw JSON articleBody bytes for each hash, even trailing spaces.
    Entries may precede initial document publication or repeat another entry;
    neither condition is evidence of a publisher publication-date conflict.
    """
    if parser is None:
        parser = _LiveblogEntries()
        parser.feed(html)
    proof = dict(source="url_bound_json_ld_and_liveblog_entry_html", canonical_url=expected,
                 original_html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                 base_article_body_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                 document_publication_timestamp=node.get("datePublished"),
                 document_modified_timestamp=node.get("dateModified"),
                 document_publication_date=metadata.get("publication_date"),
                 publisher_entry_timezone="America/Santiago", entries=[], errors=[])
    updates = node.get("liveBlogUpdate")
    if not isinstance(updates, list) or not updates:
        proof["errors"].append("missing_liveblog_updates")
        updates = []
    proof["entry_count"] = len(updates)
    known_document_timestamps = {row.get("timestamp") for row in metadata.get("publication_evidence", [])}
    if node.get("datePublished") not in known_document_timestamps:
        proof["errors"].append("liveblog_document_publication_timestamp_uncorroborated")
    modified = node.get("dateModified")
    if modified is not None:
        try:
            stamp = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp > datetime.now(ZoneInfo("UTC")):
                raise ValueError("invalid_or_future_liveblog_document_modified_timestamp")
        except (ValueError, TypeError, AttributeError):
            proof["errors"].append("invalid_or_future_liveblog_document_modified_timestamp")
    seen = set()
    for index, entry in enumerate(updates):
        try:
            if not isinstance(entry, dict) or entry.get("@type") != "BlogPosting":
                raise ValueError("invalid_liveblog_entry_type")
            url = entry.get("url")
            parsed = urlparse(url or "")
            fragment = parsed.fragment
            if (article_url(url) != expected or not fragment.startswith("lbp-")
                    or entry.get("mainEntityOfPage") != expected or fragment in seen
                    or fragment in parser.duplicates):
                raise ValueError("liveblog_entry_identity_mismatch")
            seen.add(fragment)
            displayed = parser.entries.get(fragment, {})
            times = displayed.get("times", [])
            timestamp = entry.get("datePublished")
            if (len(times) != 1 or times[0]["timestamp"] != timestamp
                    or not isinstance(timestamp, str) or len(timestamp) <= 10 or not publication_day(timestamp)):
                raise ValueError("liveblog_entry_timestamp_uncorroborated")
            stamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp > datetime.now(ZoneInfo("UTC")):
                raise ValueError("invalid_or_future_liveblog_entry_timestamp")
            visible = " ".join(" ".join(times[0]["visible"]).split())
            publisher_day = _liveblog_visible_day(visible, timestamp)
            headline, entry_body = entry.get("headline"), entry.get("articleBody")
            if not isinstance(headline, str) or not isinstance(entry_body, str):
                raise ValueError("invalid_liveblog_entry_primary_text")
            if " ".join(headline.split()) != " ".join(" ".join(displayed.get("headline", [])).split()):
                raise ValueError("liveblog_entry_headline_mismatch")
            html_body = " ".join("".join(paragraph) for paragraph in displayed.get("paragraphs", []))
            normalized_body = " ".join(entry_body.split())
            normalized_html_body = " ".join(html_body.split())
            body_corroboration = "primary_entry_paragraphs"
            if not normalized_html_body and normalized_body == " ".join(headline.split()):
                # Publisher embed-only updates repeat the bound heading in
                # articleBody without an accompanying prose paragraph.
                normalized_html_body = " ".join(headline.split())
                body_corroboration = "bound_heading_without_primary_paragraphs"
            if normalized_body != normalized_html_body:
                raise ValueError("liveblog_entry_body_mismatch")
            proof["entries"].append(dict(index=index, id=entry.get("@id"), url=url,
                timestamp=timestamp, html_datetime=times[0]["timestamp"],
                timestamp_calendar_day=publication_day(timestamp), publisher_day=publisher_day,
                visible_entry_day_month=visible, headline=headline, body=entry_body,
                body_characters=len(entry_body), body_sha256=hashlib.sha256(entry_body.encode("utf-8")).hexdigest(),
                html_body_corroboration=body_corroboration,
                html_primary_text_sha256=hashlib.sha256(normalized_html_body.encode("utf-8")).hexdigest()))
        except (ValueError, TypeError) as exc:
            proof["errors"].append(dict(index=index, reason=str(exc)))
    if seen != set(parser.entries):
        proof["errors"].append("liveblog_json_html_entry_set_mismatch")
    proof["entries_sha256"] = hashlib.sha256(json.dumps(proof["entries"], ensure_ascii=False,
                                            sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    proof["verified"] = not proof["errors"] and len(proof["entries"]) == proof["entry_count"] > 0
    return proof


def verified_liveblog_temporal_evidence(metadata):
    proof = metadata.get("liveblog_temporal_evidence", {})
    if not (metadata.get("publisher_document_type") == "liveblog"
            and metadata.get("primary_identity_verified") is True
            and metadata.get("publication_date_verified") is True
            and metadata.get("article_verified") is True
            and metadata.get("liveblog_temporal_evidence_verified") is True
            and complete_article_body(metadata) and isinstance(proof, dict)
            and proof.get("verified") is True and proof.get("errors") == []
            and proof.get("canonical_url") == metadata.get("canonical_url")
            and proof.get("original_html_sha256") == metadata.get("html_sha256")
            and re.fullmatch(r"[0-9a-f]{64}", str(metadata.get("html_sha256", "")))
            and proof.get("base_article_body_sha256") == metadata.get("article_body_sha256")
            and proof.get("document_publication_date") == metadata.get("publication_date")
            and proof.get("document_publication_timestamp") == metadata.get("publication_timestamp")
            and isinstance(metadata.get("publication_evidence"), list)
            and proof.get("document_publication_timestamp") in {
                row.get("timestamp") for row in metadata.get("publication_evidence", []) if isinstance(row, dict)}
            and proof.get("source") == "url_bound_json_ld_and_liveblog_entry_html"
            and proof.get("publisher_entry_timezone") == "America/Santiago"):
        return False
    entries = proof.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) != proof.get("entry_count"):
        return False
    digest = hashlib.sha256(json.dumps(entries, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode("utf-8")).hexdigest()
    if digest != proof.get("entries_sha256"):
        return False
    try:
        modified = proof.get("document_modified_timestamp")
        if modified is not None:
            stamp = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp > datetime.now(ZoneInfo("UTC")):
                return False
        urls = set()
        for index, entry in enumerate(entries):
            url, timestamp, text = entry["url"], entry["timestamp"], entry["body"]
            if (entry.get("index") != index or url in urls or not urlparse(url).fragment.startswith("lbp-")
                    or article_url(url) != metadata["canonical_url"]
                    or entry["html_datetime"] != timestamp
                    or entry["timestamp_calendar_day"] != publication_day(timestamp)
                    or entry["publisher_day"] != _liveblog_visible_day(entry["visible_entry_day_month"], timestamp)
                    or entry["body_characters"] != len(text)
                    or entry["body_sha256"] != hashlib.sha256(text.encode("utf-8")).hexdigest()
                    or entry.get("html_body_corroboration") not in {
                        "primary_entry_paragraphs", "bound_heading_without_primary_paragraphs"}
                    or entry.get("html_primary_text_sha256") != hashlib.sha256(
                        " ".join(text.split()).encode("utf-8")).hexdigest()
                    or (entry["html_body_corroboration"] == "bound_heading_without_primary_paragraphs"
                        and " ".join(text.split()) != " ".join(entry["headline"].split()))):
                return False
            stamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp > datetime.now(ZoneInfo("UTC")):
                return False
            urls.add(url)
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    return True


def liveblog_requires_revalidation(metadata):
    if metadata.get("publisher_document_type") == "liveblog":
        return not verified_liveblog_temporal_evidence(metadata)
    if metadata.get("publisher_document_type") in {"article", "video"}:
        return False
    # Earlier HTML-body caches omitted the publisher format. Revalidate these
    # once from primary structure, irrespective of title/path vocabulary.
    # Fresh ordinary HTML articles save an explicit article classification.
    return metadata.get("body_source") == "article_html"


def liveblog_analysis_text(metadata):
    if not verified_liveblog_temporal_evidence(metadata):
        raise ValueError("publisher_liveblog_entry_dates_unverified")
    proof = metadata["liveblog_temporal_evidence"]
    parts = ["CUERPO PRIMARIO COMPLETO (sin modificaciones):", metadata["page_text"],
             "CRONOLOGÍA PRIMARIA VERIFICADA DE LA COBERTURA EN VIVO:",
             f"Publicación del documento: {proof['document_publication_timestamp']} (día {proof['document_publication_date']}).",
             f"Última modificación del documento: {proof.get('document_modified_timestamp')}.",
             "La fecha del documento NO reemplaza la fecha de cada entrada. Usa el día visible corroborado en America/Santiago; "
             "distingue fecha del reporte y fechas/condiciones de acciones anunciadas en su texto. No sumes balances repetidos ni conviertas preparación en ejecución."]
    for entry in proof["entries"]:
        parts.extend([f"ENTRADA {entry['index']} | {entry['url']}",
                      f"Timestamp original: {entry['timestamp']} | fecha visible: {entry['publisher_day']} "
                      f"({entry['visible_entry_day_month']}, America/Santiago) | día calendario del timestamp: {entry['timestamp_calendar_day']}",
                      f"Titular: {entry['headline']}", f"Texto primario íntegro de la entrada: {entry['body']}"])
    return "\n".join(parts)


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


def _reconcile_publication_dates(dates, visible_day):
    """Require one consistent convention for all primary timestamps.

    Real originals expose an editorial byline matching the UTC calendar at
    00:xxZ; others match Santiago. A per-field choice could mask conflicting
    metadata, so the complete evidence must corroborate the same convention.
    """
    native_days = {day for _, _, day in dates}
    chile_days = {_publisher_day(value) for _, value, _ in dates}
    native_match = len(native_days) == 1 and (not visible_day or visible_day in native_days)
    chile_match = len(chile_days) == 1 and (not visible_day or visible_day in chile_days)
    if visible_day:
        if not (native_match or chile_match):
            raise ValueError("conflicting_publication_dates")
        published = visible_day
        convention = ("calendar_agreement" if native_match and chile_match else
                      "timestamp_calendar" if native_match else "america_santiago")
    else:
        # Without a displayed byline, preserve the publisher-local fallback;
        # a timezone switch cannot resolve contradictory primary timestamps.
        if not chile_match:
            raise ValueError("conflicting_publication_dates")
        published = next(iter(chile_days))
        convention = "calendar_agreement" if native_match and native_days == chile_days else "america_santiago"
    evidence = [dict(source=kind, timestamp=value, publisher_day=published,
                     timestamp_calendar_day=day, america_santiago_day=_publisher_day(value))
                for kind, value, day in dates]
    return published, convention, evidence


class ExcludedArticle(ValueError):
    """An explicit publisher section exclusion with verified primary identity/date."""
    def __init__(self, reason, title, body, metadata):
        super().__init__(reason)
        self.title, self.body, self.metadata = title, body, metadata


class TextUnavailableArticle(ValueError):
    """Verified publisher identity/date/format, with insufficient factual text."""
    def __init__(self, reason, title, body, metadata):
        super().__init__(reason)
        self.title, self.body, self.metadata = title, body, metadata


def verified_video_without_text(metadata):
    """Structural evidence allows a pending candidate, never editorial approval."""
    evidence = metadata.get("video_evidence", {})
    canonical = metadata.get("canonical_url")
    if not (metadata.get("primary_identity_verified") is True
            and metadata.get("publication_date_verified") is True
            and metadata.get("article_verified") is False
            and publication_day(metadata.get("publication_date")) == metadata.get("publication_date")
            and article_url(canonical) == canonical and canonical is not None
            and urlparse(canonical).path.startswith("/videos/")
            and metadata.get("article_body_complete") is False
            and metadata.get("publisher_document_type") == "video"
            and metadata.get("video_identity_verified") is True
            and metadata.get("source_content_unavailable_reason") == "publisher_video_text_unavailable"
            and isinstance(evidence, dict) and evidence.get("type") == "VideoObject"
            and article_url(evidence.get("url")) == canonical
            and evidence.get("id") == str(canonical) + "#video" and bool(evidence.get("embed_url"))):
        return False
    try:
        rows = metadata["publication_evidence"]
        dates = [(row["source"], row["timestamp"], publication_day(row["timestamp"])) for row in rows]
        if not dates or any(not day for _, _, day in dates):
            return False
        published, _, expected = _reconcile_publication_dates(dates, metadata.get("visible_publication_date"))
        if metadata.get("publication_date") != published or metadata.get("publication_timestamp") != dates[0][1]:
            return False
        if rows != expected:
            return False
        now = datetime.now(ZoneInfo("UTC"))
        for _, value, _ in dates:
            if len(value) == 10:
                if date.fromisoformat(value) > now.astimezone(ZoneInfo("America/Santiago")).date():
                    return False
            elif datetime.fromisoformat(value.replace("Z", "+00:00")) > now:
                return False
    except (KeyError, ValueError, TypeError):
        return False
    return True


class ConflictingPublicationArticle(ValueError):
    """A complete primary text whose original publisher dates contradict."""
    def __init__(self, title, body, metadata):
        super().__init__("conflicting_publication_dates")
        self.title, self.body, self.metadata = title, body, metadata


class SponsoredArticle(ValueError):
    """Complete publisher-declared commercial content requires human review."""
    def __init__(self, title, body, metadata):
        super().__init__("publisher_sponsored_content_review_required")
        self.title, self.body, self.metadata = title, body, metadata


def _primary_taxonomy(section, keywords, canonical, article_type):
    labels = [value.strip() for value in keywords.split(',')] if isinstance(keywords, str) else keywords
    labels = [value.strip() for value in labels if isinstance(value, str)] if isinstance(labels, list) else []
    matched = [value for value in labels if value.casefold() in _OPINION_LABELS]
    section_key = str(section).strip().casefold()
    classification = ("opinion" if matched or section_key in _OPINION_LABELS else
                      "sponsored" if section_key in _SPONSORED_SECTIONS
                      and urlparse(canonical).path.split('/')[1] == section_key else "factual")
    return dict(source="url_bound_json_ld", canonical_url=canonical, article_type=article_type,
                section=section, labels=labels, matched_opinion_labels=matched, classification=classification)


def _matching_primary_taxonomy(metadata):
    canonical = metadata.get("canonical_url")
    if not canonical or article_url(canonical) != canonical:
        return False
    expected = _primary_taxonomy(metadata.get("section"), metadata.get("keywords", []), canonical, None)
    saved = metadata.get("publisher_taxonomy", {})
    article_type = saved.get("article_type") if isinstance(saved, dict) else None
    types = [article_type] if isinstance(article_type, str) else article_type
    return (isinstance(saved, dict) and saved.get("source") == "url_bound_json_ld"
                and isinstance(types, list) and any(value in ("NewsArticle", "Article", "ReportageNewsArticle") for value in types)
                and saved.get("canonical_url") == canonical
                and all(saved.get(key) == expected[key] for key in
                        ("section", "labels", "matched_opinion_labels", "classification")))


class _CommercialPrimaryText(HTMLParser):
    """Observe real text in the publisher body region, excluding UI wrappers."""
    def __init__(self):
        super().__init__()
        self.stack, self.parts, self.regions = [], [], 0

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "").split()
        region = "article-right-rail__body" in classes
        self.regions += int(region)
        active = region or bool(self.stack and self.stack[-1][1])
        excluded = bool(self.stack and self.stack[-1][2]) or tag in {
            "script", "style", "svg", "noscript", "nav", "footer", "aside"} or any(
            value.startswith(("article-body__byline", "article-body__social", "article-body__tags",
                              "article-body__figure", "coral__")) for value in classes)
        if tag not in _Article.VOID:
            self.stack.append((tag, active, excluded))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1][1] and not self.stack[-1][2] and data.strip():
            self.parts.append(data)


def _sponsored_empty_text_evidence(html, expected, node, parser):
    """Prove the observed commercial document has no primary text to recover.

    A missing articleBody alone is not proof: the publisher's bound ANS story
    and actual primary paragraphs must also expose no text. Descriptions,
    subtitles and navigation are never substituted for the absent body.
    """
    matches = list(re.finditer(r"\bFusion\.globalContent\s*=\s*", html))
    if len(matches) != 1 or parser.body_paragraphs or parser.paragraphs:
        return None
    json_body = node.get("articleBody")
    if json_body is not None and (not isinstance(json_body, str) or json_body.strip()):
        return None
    displayed = _CommercialPrimaryText()
    displayed.feed(html)
    if displayed.regions != 1 or displayed.parts:
        return None
    try:
        story, _ = json.JSONDecoder().raw_decode(html[matches[0].end():])
        elements = story.get("content_elements")
        if not (story.get("type") == "story" and isinstance(story.get("_id"), str) and story["_id"]
                and article_url(story.get("canonical_url")) == expected
                and article_url(story.get("websites", {}).get("la-tercera", {}).get("website_url")) == expected
                and story.get("first_publish_date") == node.get("datePublished")
                and story.get("headlines", {}).get("basic") == node.get("headline")
                and isinstance(elements, list) and elements
                and all(isinstance(entry, dict) and entry.get("type") == "text"
                        and isinstance(entry.get("content"), str) and not entry["content"].strip()
                        for entry in elements)):
            return None
        return dict(source="url_bound_json_ld_and_empty_fusion_story", canonical_url=expected,
                    article_type=node.get("@type"), fusion_story_id=story["_id"],
                    fusion_canonical_url=article_url(story["canonical_url"]),
                    fusion_first_publish_date=story["first_publish_date"],
                    json_article_body_available=False, primary_paragraph_count=0,
                    primary_body_region_count=1, primary_body_region_text_characters=0,
                    fusion_content_element_count=len(elements), fusion_text_characters=0,
                    original_html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest())
    except (ValueError, TypeError, AttributeError):
        return None


def verified_sponsored_without_text(metadata):
    """A byte-bound commercial limitation is not verified factual content."""
    reason = "publisher_sponsored_text_unavailable"
    canonical = metadata.get("canonical_url")
    proof = metadata.get("sponsored_text_evidence", {})
    taxonomy = metadata.get("publisher_taxonomy", {})
    if not (canonical and article_url(canonical) == canonical and _matching_primary_taxonomy(metadata)
            and taxonomy.get("classification") == "sponsored"
            and metadata.get("publisher_content_classification") == "sponsored"
            and metadata.get("primary_identity_verified") is True
            and metadata.get("publication_date_verified") is True
            and metadata.get("article_verified") is False and metadata.get("article_body_complete") is False
            and metadata.get("publisher_document_type") == "sponsored_without_text"
            and metadata.get("body_source") == "publisher_sponsored_no_textual_article_body"
            and metadata.get("publisher_exception_reason") == reason
            and metadata.get("source_content_unavailable_reason") == reason and metadata.get("editorial_hold") == reason
            and metadata.get("page_text") == "" and metadata.get("article_body_characters") == 0
            and metadata.get("article_body_sha256") == hashlib.sha256(b"").hexdigest()
            and re.fullmatch(r"[0-9a-f]{64}", str(metadata.get("html_sha256", "")))
            and isinstance(proof, dict) and proof.get("source") == "url_bound_json_ld_and_empty_fusion_story"
            and proof.get("canonical_url") == proof.get("fusion_canonical_url") == canonical
            and proof.get("article_type") == taxonomy.get("article_type")
            and isinstance(proof.get("fusion_story_id"), str) and proof["fusion_story_id"]
            and proof.get("original_html_sha256") == metadata.get("html_sha256")
            and proof.get("json_article_body_available") is False
            and type(proof.get("primary_paragraph_count")) is int and proof["primary_paragraph_count"] == 0
            and type(proof.get("primary_body_region_count")) is int and proof["primary_body_region_count"] == 1
            and type(proof.get("primary_body_region_text_characters")) is int and proof["primary_body_region_text_characters"] == 0
            and type(proof.get("fusion_content_element_count")) is int and proof["fusion_content_element_count"] > 0
            and type(proof.get("fusion_text_characters")) is int and proof["fusion_text_characters"] == 0
            and metadata.get("visible_publication_date")):
        return False
    try:
        rows = metadata["publication_evidence"]
        dates = [(row["source"], row["timestamp"], publication_day(row["timestamp"])) for row in rows]
        if not dates or any(not day for _, _, day in dates):
            return False
        published, _, expected = _reconcile_publication_dates(dates, metadata["visible_publication_date"])
        return (metadata.get("publication_date") == published
                and metadata.get("publication_timestamp") == dates[0][1]
                and proof.get("fusion_first_publish_date") == dates[0][1]
                and rows == expected and _cached_capture_dates_valid(metadata))
    except (KeyError, ValueError, TypeError):
        return False


def publisher_taxonomy_requires_revalidation(metadata):
    """Legacy successful caches must not bypass newly verified publisher labels."""
    canonical = metadata.get("canonical_url")
    if not canonical or article_url(canonical) != canonical:
        return False
    expected = _primary_taxonomy(metadata.get("section"), metadata.get("keywords", []), canonical, None)
    if expected["classification"] == "factual":
        return False
    if not _matching_primary_taxonomy(metadata):
        return True
    if expected["classification"] == "opinion":
        return not (metadata.get("publisher_exclusion_reason") in ("publisher_opinion_taxonomy", "excluded_opinion_content")
                    and metadata.get("primary_identity_verified") is True
                    and metadata.get("publication_date_verified") is True)
    return not (verified_sponsored_content(metadata) or verified_publication_date_conflict(metadata)
                or verified_sponsored_without_text(metadata))


def verified_sponsored_content(metadata):
    """Verify commercial provenance, never establish editorial eligibility."""
    canonical = metadata.get("canonical_url")
    taxonomy = metadata.get("publisher_taxonomy", {})
    expected_taxonomy = _primary_taxonomy(metadata.get("section"), metadata.get("keywords", []), canonical, None) if canonical else {}
    if not (canonical and article_url(canonical) == canonical
            and metadata.get("primary_identity_verified") is True
            and metadata.get("publication_date_verified") is True
            and metadata.get("article_verified") is True
            and metadata.get("article_body_complete") is True and complete_article_body(metadata)
            and metadata.get("publisher_content_classification") == "sponsored"
            and metadata.get("publisher_exception_reason") == "publisher_sponsored_content_review_required"
            and metadata.get("editorial_hold") == "publisher_sponsored_content_review_required"
            and isinstance(taxonomy, dict) and taxonomy.get("classification") == "sponsored"
            and expected_taxonomy.get("classification") == "sponsored"
            and taxonomy.get("source") == "url_bound_json_ld" and taxonomy.get("canonical_url") == canonical
            and _matching_primary_taxonomy(metadata)):
        return False
    try:
        rows = metadata["publication_evidence"]
        dates = [(row["source"], row["timestamp"], publication_day(row["timestamp"])) for row in rows]
        if not dates or any(not day for _, _, day in dates):
            return False
        published, _, expected = _reconcile_publication_dates(dates, metadata.get("visible_publication_date"))
        if not (metadata.get("publication_date") == published
                and metadata.get("publication_timestamp") == dates[0][1] and rows == expected):
            return False
        now = datetime.now(ZoneInfo("UTC"))
        for _, value, _ in dates:
            if len(value) == 10:
                if date.fromisoformat(value) > now.astimezone(ZoneInfo("America/Santiago")).date():
                    return False
            elif datetime.fromisoformat(value.replace("Z", "+00:00")) > now:
                return False
        return True
    except (KeyError, ValueError, TypeError):
        return False


def verified_publication_date_conflict(metadata):
    """Verify the exception proof without adopting any publication date."""
    canonical = metadata.get("canonical_url")
    visible = metadata.get("visible_publication_date")
    if not (canonical and article_url(canonical) == canonical
            and metadata.get("primary_identity_verified") is True
            and metadata.get("publication_date_verified") is False
            and metadata.get("publication_date") is None
            and metadata.get("publication_timestamp") is None
            and metadata.get("article_verified") is False
            and metadata.get("publisher_exception_reason") == "publisher_conflicting_publication_dates"
            and complete_article_body(metadata) and isinstance(visible, str)
            and len(visible) == 10 and publication_day(visible) == visible):
        return False
    try:
        rows = metadata["publication_evidence"]
        dates = [(row["source"], row["timestamp"], publication_day(row["timestamp"])) for row in rows]
        if not dates or any(not day for _, _, day in dates):
            return False
        possible = {visible}
        for row, (_, value, day) in zip(rows, dates):
            chile_day = _publisher_day(value)
            if (row.get("publisher_day") is not None or row.get("timestamp_calendar_day") != day
                    or row.get("america_santiago_day") != chile_day):
                return False
            possible.update((day, chile_day))
        if metadata.get("possible_publication_days") != sorted(possible):
            return False
        _reconcile_publication_dates(dates, visible)
    except ValueError as exc:
        return str(exc) == "conflicting_publication_dates"
    except (KeyError, TypeError):
        return False
    return False


def _inventory_disposition(result, cutoff, today):
    """Separate enumerated publisher limitations from verified-text candidates."""
    metadata = result["metadata"]
    value = metadata.get("publication_date")
    day = date.fromisoformat(value) if value else None
    if day is None:
        if not verified_publication_date_conflict(metadata):
            raise ValueError("unverified_missing_publication_date")
        possible = metadata["possible_publication_days"]
        if possible and max(possible) < cutoff.isoformat():
            return None, "excluded", "all_primary_publication_evidence_before_90_day_window"
        return None, "discovered_metadata_only", result["deferred_reason"]
    if not cutoff <= day <= today:
        return day, "excluded", "outside_90_day_window"
    if result.get("deferred_reason") == "publisher_sponsored_content_review_required" and not result["relevant"]:
        return day, "excluded", "no_health_anchor"
    if result.get("deferred_reason"):
        return day, "discovered_metadata_only", result["deferred_reason"]
    if result["relevant"]:
        return day, "discovered", None
    return day, "excluded", result.get("exclusion_reason", "no_health_anchor")


def extract_article(html, expected_url):
    expected = article_url(expected_url)
    if not expected:
        raise ValueError("unexpected_article_host_or_path")
    parser = _Article()
    parser.feed(html)
    identity = parser.canonical or parser.metas.get("og:url")
    if not identity or article_url(identity, expected) != expected:
        raise ValueError("article_identity_mismatch")
    articles, videos, liveblogs = [], [], []
    for script in parser.scripts:
        try:
            nodes = _nodes(json.loads(script))
            for node in nodes:
                types = node.get("@type", [])
                types = [types] if isinstance(types, str) else types
                if not any(t in ("NewsArticle", "Article", "ReportageNewsArticle", "VideoObject", "LiveBlogPosting") for t in types):
                    continue
                link = node.get("url") or node.get("mainEntityOfPage") or node.get("@id")
                if isinstance(link, dict):
                    link = link.get("@id")
                if not link or article_url(link, expected) != expected:
                    continue
                if "LiveBlogPosting" in types:
                    liveblogs.append(node)
                elif "VideoObject" in types:
                    videos.append(node)
                else:
                    articles.append(node)
        except (ValueError, TypeError):
            continue
    if len(articles) > 1:
        raise ValueError("ambiguous_article_metadata")
    if len(liveblogs) > 1:
        raise ValueError("ambiguous_liveblog_metadata")
    node = articles[0] if articles else {}
    evidence = [("json_ld_datePublished", node.get("datePublished")),
                ("article_published_time", parser.metas.get("article:published_time"))]
    evidence.extend(("article_time", value) for value in parser.times)
    dates = [(kind, value, publication_day(value)) for kind, value in evidence if value]
    if not dates or any(not day for _, _, day in dates):
        raise ValueError("missing_or_invalid_publication_date")
    visible_day = _visible_byline_day(parser.byline_dates)
    conflicting = False
    try:
        published, convention, dated_evidence = _reconcile_publication_dates(dates, visible_day)
    except ValueError as exc:
        if str(exc) != "conflicting_publication_dates":
            raise
        conflicting = True
        published, convention = None, "unresolved_primary_publisher_date_conflict"
        dated_evidence = [dict(source=kind, timestamp=value, publisher_day=None,
                              timestamp_calendar_day=day, america_santiago_day=_publisher_day(value))
                          for kind, value, day in dates]
    date_source, timestamp, _ = dates[0]
    if visible_day:
        date_source = "visible_article_byline"
    if conflicting:
        date_source, timestamp = "unresolved_primary_publisher_date_conflict", None
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
    # A short URL-bound primary body must not be padded with wrapper text.
    # Publisher videos can expose only a headline as articleBody, or no body;
    # byline/share/tags are not a transcript even when their length exceeds160.
    json_body = node.get("articleBody")
    primary_video = (len(articles) == 1 and len(videos) == 1
                     and expected.split('/')[3] == "videos"
                     and article_url(videos[0].get("url")) == expected
                     and videos[0].get("@id") == expected + "#video"
                     and bool(videos[0].get("embedUrl")))
    if isinstance(json_body, str) and json_body.strip():
        body = " ".join(json_body.split())
        body_source = "url_bound_json_ld_articleBody"
    elif primary_video:
        body = " ".join(parser.body_paragraphs or parser.paragraphs)
        body_source = "publisher_video_html_transcript" if body else "publisher_video_no_textual_article_body"
    else:
        body_source = "article_html"
    section = node.get("articleSection") or parser.metas.get("article:section") or expected.split('/')[3]
    metadata = dict(section=section, keywords=node.get("keywords", []),
                            description=node.get("description", ""),
                            body_source=body_source,
                            publication_date=published, publication_timestamp=timestamp,
                            publication_date_source=date_source, visible_publication_date=visible_day,
                            publisher_date_convention=convention, publication_evidence=dated_evidence,
                            canonical_url=expected, primary_identity_verified=True,
                            publication_date_verified=not conflicting, article_verified=not conflicting)
    if liveblogs:
        timeline = _liveblog_temporal_evidence(liveblogs[0], html, expected, metadata, body)
        metadata.update(publisher_document_type="liveblog", liveblog_temporal_evidence=timeline,
                        liveblog_temporal_evidence_verified=timeline["verified"],
                        html_sha256=timeline["original_html_sha256"])
    elif body_source == "article_html":
        displayed_entries = _LiveblogEntries()
        displayed_entries.feed(html)
        if displayed_entries.entries:
            # A structured timeline whose JSON identity/date proof vanished
            # remains a liveblog with unverified entry dates, not an ordinary
            # article eligible to reuse the document date for every event.
            timeline = _liveblog_temporal_evidence({}, html, expected, metadata, body, displayed_entries)
            metadata.update(publisher_document_type="liveblog", liveblog_temporal_evidence=timeline,
                            liveblog_temporal_evidence_verified=False,
                            html_sha256=timeline["original_html_sha256"])
        else:
            metadata["publisher_document_type"] = "article"
    if len(articles) == 1:
        taxonomy = _primary_taxonomy(section, metadata["keywords"], expected, node.get("@type"))
        metadata.update(publisher_taxonomy=taxonomy, publisher_content_classification=taxonomy["classification"])
    if conflicting:
        # Only a complete, URL-bound original with a displayed byline can be
        # classified as a publisher editorial exception. Unknown/partial
        # documents retain the strict technical error; no date is selected.
        if not (len(articles) == 1 and visible_day and title.strip() and len(body) >= 160):
            raise ValueError("conflicting_publication_dates")
        possible = {visible_day}
        possible.update(row["timestamp_calendar_day"] for row in dated_evidence)
        possible.update(row["america_santiago_day"] for row in dated_evidence)
        metadata.update(article_body_complete=True, possible_publication_days=sorted(possible),
                        publisher_exception_reason="publisher_conflicting_publication_dates",
                        editorial_hold="publisher_conflicting_publication_dates",
                        editorial_assessment=dict(decision="pending", reason="publisher_conflicting_publication_dates"))
        raise ConflictingPublicationArticle(title, body, metadata)
    if metadata.get("publisher_taxonomy", {}).get("matched_opinion_labels"):
        metadata["publisher_exclusion_reason"] = "publisher_opinion_taxonomy"
        raise ExcludedArticle("publisher_opinion_taxonomy", title, body, metadata)
    if re.search(r"opini[oó]n|editorial|columna", str(section), re.I):
        metadata["publisher_exclusion_reason"] = "excluded_opinion_content"
        raise ExcludedArticle("excluded_opinion_content", title, body, metadata)
    if primary_video:
        video = videos[0]
        metadata.update(publisher_document_type="video", video_identity_verified=True,
                        video_evidence=dict(type="VideoObject", url=video.get("url"),
                                            id=video.get("@id"), embed_url=video["embedUrl"],
                                            upload_date=video.get("uploadDate")))
        if title.strip() and len(body) < 160:
            metadata.update(article_verified=False, article_body_complete=False,
                            source_content_unavailable_reason="publisher_video_text_unavailable",
                            editorial_assessment=dict(decision="pending", reason="publisher_video_text_unavailable"))
            raise TextUnavailableArticle("publisher_video_text_unavailable", title, body, metadata)
    if (title.strip() and visible_day and len(articles) == 1
            and metadata.get("publisher_content_classification") == "sponsored"):
        proof = _sponsored_empty_text_evidence(html, expected, node, parser)
        if proof:
            reason = "publisher_sponsored_text_unavailable"
            metadata.update(article_body_evidence(""), article_verified=False, article_body_complete=False,
                            publisher_document_type="sponsored_without_text",
                            body_source="publisher_sponsored_no_textual_article_body",
                            sponsored_text_evidence=proof, html_sha256=proof["original_html_sha256"],
                            publisher_exception_reason=reason, source_content_unavailable_reason=reason,
                            editorial_hold=reason, editorial_assessment=dict(decision="pending", reason=reason))
            raise TextUnavailableArticle(reason, title, "", metadata)
    # A brief primary headline is not missing evidence: real publisher stories
    # such as "Vivir con TOC" contain complete, URL-bound factual article bodies.
    if not title.strip() or len(body) < 160:
        raise ValueError("incomplete_article_evidence")
    if metadata.get("publisher_content_classification") == "sponsored":
        metadata.update(article_body_complete=True, publisher_exception_reason="publisher_sponsored_content_review_required",
                        editorial_hold="publisher_sponsored_content_review_required",
                        editorial_assessment=dict(decision="pending", reason="publisher_sponsored_content_review_required"))
        raise SponsoredArticle(title, body, metadata)
    return title, body, metadata


def _project_missing_body_completeness(metadata):
    """Recover absent legacy counters from the bound complete primary text.

    The cached article's short display preview is never evidence. This projection
    changes no capture, hash, publication date or explicit completeness verdict.
    """
    projected = dict(metadata)
    if (metadata.get("source_quality_gate") == "passed"
            and all(metadata.get(flag) is True for flag in (
                "article_verified", "primary_identity_verified", "publication_date_verified"))
            and complete_article_body(metadata)):
        projected.setdefault("article_body_characters", len(metadata["page_text"]))
        projected.setdefault("article_body_complete", True)
    return projected


def _primary_trace(metadata):
    """One primary-evidence contract for listings, archives and public feeds."""
    metadata = _project_missing_body_completeness(metadata)
    keys = ("canonical_url", "section", "body_source", "publication_date", "publication_timestamp",
            "publication_date_source", "visible_publication_date", "publisher_date_convention",
            "publication_evidence", "source_content_unavailable_reason", "publisher_exception_reason",
            "publisher_exclusion_reason", "publisher_taxonomy", "publisher_content_classification",
            "possible_publication_days", "video_evidence", "html_sha256", "captured_at",
            "article_body_characters", "article_body_sha256", "source_quality_gate",
            "liveblog_temporal_evidence", "liveblog_temporal_evidence_verified", "sponsored_text_evidence")
    trace = {key: metadata.get(key) for key in keys}
    trace.update(topics=metadata.get("topics", []),
                 primary_identity_verified=metadata.get("primary_identity_verified", False),
                 publication_date_verified=metadata.get("publication_date_verified", False),
                 article_verified=metadata.get("article_verified", False),
                 article_body_complete=metadata.get("article_body_complete", False),
                 publisher_document_type=metadata.get("publisher_document_type", "article"),
                 publisher_lastmod=metadata.get("publisher_lastmod", ""))
    return trace


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
            html = _request_with_retries(detail_loader, url, audit)
            title, body, metadata = extract_article(html, url)
            metadata.update(article_body_evidence(body), discovered_from=base, market_role="media",
                            captured_at=datetime.now(ZoneInfo("UTC")).isoformat(),
                            html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest())
            if not health_anchor(title + " " + body):
                audit.append(dict(_primary_trace(metadata), url=url, listing=base, title=title,
                                  status="excluded", reason="no_health_anchor", cache_hit=False))
                continue
            metadata["source_quality_gate"] = "passed"
            out.append(RawItem("pulso_latercera", title, url, "Pulso / La Tercera", "press_high_trust",
                               event_date=metadata["publication_date"], raw_text=body[:1800], metadata=metadata))
            audit.append(dict(_primary_trace(metadata), url=url, listing=base, title=title,
                              status="discovered", reason=None, cache_hit=False))
        except (TextUnavailableArticle, ConflictingPublicationArticle, SponsoredArticle) as exc:
            result = _verified_detail(dict(url=url, listing=base), lambda _: html, None, audit)
            metadata = result["metadata"]
            if not result["relevant"]:
                audit.append(dict(_primary_trace(metadata), url=url, listing=base, title=result["title"],
                                  status="excluded", reason="no_health_anchor", cache_hit=False))
                continue
            out.append(RawItem("pulso_latercera", result["title"], url, "Pulso / La Tercera", "press_high_trust",
                               event_date=metadata["publication_date"], raw_text=result["body"], metadata=metadata))
            audit.append(dict(_primary_trace(metadata), url=url, listing=base, title=result["title"],
                              status="discovered_metadata_only", reason=result["deferred_reason"], cache_hit=False))
        except ExcludedArticle as exc:
            metadata = dict(exc.metadata)
            metadata.update(article_body_evidence(exc.body), captured_at=datetime.now(ZoneInfo("UTC")).isoformat(),
                            html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest())
            audit.append(dict(_primary_trace(metadata), url=url, listing=base, title=exc.title,
                              status="excluded", reason=str(exc), cache_hit=False))
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


def _cached_capture_dates_valid(metadata, now=None):
    """Reuse only an original aware capture with nonfuture primary timestamps."""
    now = now or datetime.now(ZoneInfo("UTC"))
    try:
        captured = metadata.get("captured_at")
        if not isinstance(captured, str):
            return False
        captured = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        if captured.tzinfo is None or captured.utcoffset() is None or captured > now:
            return False
        evidence = metadata.get("publication_evidence")
        if not isinstance(evidence, list) or not evidence:
            return False
        for row in evidence:
            value = row.get("timestamp")
            if not publication_day(value):
                return False
            if len(value) == 10:
                if date.fromisoformat(value) > now.astimezone(ZoneInfo("America/Santiago")).date():
                    return False
            elif datetime.fromisoformat(value.replace("Z", "+00:00")) > now:
                return False
        return True
    except (AttributeError, ValueError, TypeError, OverflowError):
        return False


def _verified_detail(entry, loader, cached, audit=None):
    """Only successful URL-bound article evidence is eligible for reuse."""
    url = entry["url"]
    now = datetime.now(ZoneInfo("UTC")).isoformat()
    # lastmod is solely a change token: it never establishes publication date.
    if (cached and article_url(url) == url
            and entry.get("lastmod") and cached.get("lastmod") == entry["lastmod"]
            and cached.get("metadata", {}).get("canonical_url") == url
            and re.fullmatch(r"[0-9a-f]{64}", str(cached.get("metadata", {}).get("html_sha256", "")))
            and _cached_capture_dates_valid(cached.get("metadata", {}))
            and not publisher_taxonomy_requires_revalidation(cached.get("metadata", {}))
            and not liveblog_requires_revalidation(cached.get("metadata", {}))
            and (cached.get("metadata", {}).get("article_verified")
                 or verified_video_without_text(cached.get("metadata", {}))
                 or verified_publication_date_conflict(cached.get("metadata", {}))
                 or verified_sponsored_without_text(cached.get("metadata", {})))
            and cached.get("url") == url
            and (not urlparse(url).path.startswith("/videos/")
                 or cached.get("metadata", {}).get("video_identity_verified") is True)
            and (not cached.get("relevant") or complete_article_body(cached.get("metadata", {}))
                 or verified_video_without_text(cached.get("metadata", {}))
                 or verified_sponsored_without_text(cached.get("metadata", {})))):
        metadata = cached["metadata"]
        if verified_publication_date_conflict(metadata):
            return dict(cached, cache_hit=True)
        evidence = metadata.get("publication_evidence", [])
        dates = [(row.get("source"), row.get("timestamp"), publication_day(row.get("timestamp")))
                 for row in evidence]
        try:
            if not dates or any(not day for _, _, day in dates):
                raise ValueError("missing_or_invalid_publication_date")
            published, convention, dated_evidence = _reconcile_publication_dates(
                dates, metadata.get("visible_publication_date"))
            if published != metadata.get("publication_date"):
                raise ValueError("cached_publication_date_mismatch")
        except (ValueError, TypeError):
            pass  # A cache with uncorroborated dates requires original HTML.
        else:
            result = dict(cached, metadata=dict(metadata, publisher_date_convention=convention,
                                                publication_evidence=dated_evidence), cache_hit=True)
            if metadata.get("article_verified") is True:
                if (metadata.get("primary_identity_verified") is False
                        or metadata.get("publication_date_verified") is False):
                    return _verified_detail(entry, loader, None, audit)
                # Earlier verified caches lacked these explicit flags. Their
                # canonical identity, original HTML hash, unchanged lastmod and
                # entire publication evidence were checked above. Capture time
                # and original hash remain unchanged; this is not a fresh fetch.
                result["metadata"].update(primary_identity_verified=True, publication_date_verified=True)
                result["metadata"] = _project_missing_body_completeness(result["metadata"])
            return result
    try:
        html = _request_with_retries(loader, url, audit)
        title, body, metadata = extract_article(html, url)
        digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
        combined = title + " " + body + " " + str(metadata.get("keywords", ""))
        relevant = health_anchor(combined)
        metadata.update(article_body_evidence(body), discovered_from=entry["listing"], page_text=body if relevant else "",
                        market_role="media", source_quality_gate="passed", captured_at=now,
                        html_sha256=digest,
                        publisher_lastmod=entry.get("lastmod", ""),
                        topics=health_topics(combined) if relevant else [])
        return dict(url=url, title=title, body=body[:1800] if relevant else "", metadata=metadata,
                    relevant=relevant, lastmod=entry.get("lastmod", ""), cache_hit=False)
    except SponsoredArticle as exc:
        metadata = dict(exc.metadata)
        combined = exc.title + " " + exc.body + " " + str(metadata.get("keywords", ""))
        metadata.update(article_body_evidence(exc.body), discovered_from=entry["listing"],
                        market_role="media", source_quality_gate="deferred_sponsored_content_review", captured_at=now,
                        html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                        publisher_lastmod=entry.get("lastmod", ""), topics=health_topics(combined))
        return dict(url=url, title=exc.title, body=exc.body[:1800], metadata=metadata,
                    relevant=health_anchor(combined), deferred_reason=str(exc),
                    lastmod=entry.get("lastmod", ""), cache_hit=False)
    except ConflictingPublicationArticle as exc:
        metadata = dict(exc.metadata)
        metadata.update(article_body_evidence(exc.body), discovered_from=entry["listing"],
                        market_role="media", source_quality_gate="deferred_publication_date", captured_at=now,
                        html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                        publisher_lastmod=entry.get("lastmod", ""),
                        health_anchor_observed=health_anchor(exc.title + " " + exc.body))
        metadata["topics"] = health_topics(exc.title + " " + exc.body)
        return dict(url=url, title=exc.title, body=exc.body[:1800], metadata=metadata, relevant=True,
                    deferred_reason="publisher_conflicting_publication_dates",
                    lastmod=entry.get("lastmod", ""), cache_hit=False)
    except TextUnavailableArticle as exc:
        metadata = dict(exc.metadata)
        quality = ("deferred_sponsored_text" if str(exc) == "publisher_sponsored_text_unavailable" else "deferred_video_text")
        metadata.update(article_body_evidence(exc.body), discovered_from=entry["listing"],
                        market_role="media", source_quality_gate=quality, captured_at=now,
                        html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                        publisher_lastmod=entry.get("lastmod", ""),
                        health_anchor_observed=health_anchor(exc.title + " " + str(metadata.get("keywords", ""))
                                                             + " " + metadata.get("description", "")))
        metadata["topics"] = health_topics(exc.title + " " + str(metadata.get("keywords", ""))
                                           + " " + metadata.get("description", ""))
        return dict(url=url, title=exc.title, body=exc.body, metadata=metadata, relevant=True,
                    deferred_reason=str(exc), lastmod=entry.get("lastmod", ""), cache_hit=False)
    except ExcludedArticle as exc:
        metadata = dict(exc.metadata)
        metadata.update(article_body_evidence(exc.body), discovered_from=entry["listing"], captured_at=now,
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
    publisher_exceptions = 0
    terminal, boundary, termination = False, False, "unproven"
    advertised = []
    try:
        kind, advertised = parse_sitemap(_request_with_retries(detail_loader, SITEMAP_INDEX, audit, scope="archive_index"))
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
        nonlocal errors, excluded, older_pages, terminal, boundary, termination, attempted_pages, consecutive_page_errors, rss_exclusions, publisher_exceptions
        attempted_pages += 1
        try:
            xml = _request_with_retries(detail_loader, url, audit, scope="archive_page")
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
                rss_items = parse_fulltext_rss(_request_with_retries(detail_loader, rss_url, audit, scope="rss"))
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
            # Fulltext RSS is corroboration, never sufficient to exclude a
            # cold URL: a publisher may emit an unmarked truncated excerpt.
            # Verified primary details/exclusions can be reused by change token.
            candidates.append(entry)
        dates = []
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            results = list(pool.map(lambda entry: _verified_detail(entry, detail_loader, articles.get(entry["url"]), audit), candidates))
        page_errors = False
        for entry, result in zip(candidates, results):
            if result.get("status") == "detail_error":
                errors += 1
                page_errors = True
                audit.append(result)
                continue
            articles[result["url"]] = {key: value for key, value in result.items() if key != "cache_hit"}
            metadata = result["metadata"]
            day, status, reason = _inventory_disposition(result, cutoff, today)
            if day:
                dates.append(day)
                verified_days.append(day)
            else:
                page_errors = True  # an ambiguous date never corroborates an old page
                publisher_exceptions += 1
            trace = dict(_primary_trace(metadata), url=result["url"], listing=url, status=status, reason=reason,
                         title=result["title"], publisher_lastmod=entry.get("lastmod", ""),
                         cache_hit=result["cache_hit"], in_complete_30_days=bool(day and today - timedelta(days=30) <= day < today),
                         in_complete_90_days=bool(day and cutoff <= day < today), current_day_slice=day == today)
            audit.append(trace)
            if status in ("discovered", "discovered_metadata_only"):
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


PUBLIC_FEEDS = tuple(("section", name) for name in (
    "pulso", "nacional", "politica", "tendencias", "que-pasa", "paula", "sustentabilidad",
    "lt-board", "sociales", "servicios", "tecnologia", "la-tercera-pm", "horizontes",
)) + tuple(("tag", name) for name in (
    "salud", "isapres", "fonasa", "clinicas", "hospitales", "listas-de-espera", "banmedica",
))


def _public_feed_url(kind, name, offset, deployment=None):
    """Same unauthenticated request made by the publisher's visible Ver más."""
    source = "story-feed-sections-fetch" if kind == "section" else "story-feed-tag-fetch"
    query = dict(feedOffset=offset, feedSize=24, fromComponent="result-list")
    query["includeSections" if kind == "section" else "tagSlug"] = "/" + name if kind == "section" else name
    params = dict(query=json.dumps(query, separators=(",", ":")), _website="la-tercera")
    if deployment:
        params["d"] = deployment
    return "https://www.latercera.com/pf/api/v3/content/fetch/" + source + "?" + urlencode(params)


def parse_public_feed(value):
    """Parse the publicly rendered ANS inventory without a title/topic gate."""
    value = json.loads(value) if isinstance(value, str) else value
    if isinstance(value, dict) and isinstance(value.get("data"), dict):
        value = value["data"]
    if not isinstance(value, dict) or not isinstance(value.get("content_elements"), list):
        raise ValueError("unexpected_public_feed_document")
    entries = []
    for node in value["content_elements"]:
        if not isinstance(node, dict):
            raise ValueError("invalid_public_feed_article")
        site = node.get("websites", {}).get("la-tercera", {})
        candidate = site.get("website_url") or node.get("website_url") or node.get("canonical_url")
        url = article_url(candidate) if candidate else None
        entries.append(dict(url=url, publisher_url=urljoin(LISTINGS[0], candidate or ""),
                            lastmod=node.get("last_updated_date", ""),
                            first_publish_date=node.get("first_publish_date"),
                            publish_date=node.get("publish_date"),
                            title=node.get("headlines", {}).get("basic", ""),
                            section=node.get("taxonomy", {}).get("primary_section", {}),
                            publisher_id=node.get("_id")))
    return entries, value.get("count"), value.get("next")


def _checkpoint_feed_cache(path, cache, last_saved, *, force=False):
    """Persist the first verified page, periodic progress and each feed end.

    A warm cache can exceed 50 MB. Rewriting it on every inventory page adds
    minutes without preserving additional original evidence. Checkpoints remain
    atomic and periodic; completed and failed feeds always persist their final
    verified details before the next surface starts.
    """
    from .pending_queue import atomic_json
    now = monotonic()
    if force or last_saved is None or now - last_saved >= 30:
        cache["updated_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
        atomic_json(path, cache)
        return monotonic()
    return last_saved


def discover_public_feeds(loader, audit, cache_path, *, visited=None, today=None,
                          workers=4, feeds=None, max_feed_pages=250):
    """Recover the 90-day horizon through ordinary public frontend pagination.

    All new factual URLs are opened in detail. API first_publish_date is only
    chronology corroboration; final publication remains the primary byline.
    """
    today = today or datetime.now(ZoneInfo("America/Santiago")).date()
    cutoff = today - timedelta(days=90)
    cache = _load_cache(cache_path)
    articles = cache["articles"]
    last_saved = None
    visited = visited if visited is not None else set()
    out, summaries = [], []
    feeds = PUBLIC_FEEDS if feeds is None else feeds
    worker_count = max(1, min(int(workers), 4))
    deployment = None
    try:
        page_html = _request_with_retries(loader, LISTINGS[0], audit, scope="publisher_listing")
        match = re.search(r'Fusion\.deployment="([a-zA-Z0-9_-]+)"', page_html)
        deployment = match[1] if match else None
    except Exception as exc:
        audit.append(dict(listing=LISTINGS[0], status="surface_error", reason=str(exc), fallback="public_feed_without_deployment_cache_key"))
    for kind, name in feeds:
        offset, old_pages, page_count, errors, publisher_exceptions = 0, 0, 0, 0, 0
        growth, identities, observed_dates, publisher_ids = set(), set(), [], set()
        no_growth_pages = 0
        complete, termination = False, "unproven"
        total = None
        while page_count < max_feed_pages:
            url = _public_feed_url(kind, name, offset, deployment)
            page_count += 1
            try:
                payload = _request_with_retries(loader, url, audit, scope="public_feed", feed=kind + ":" + name)
                entries, total, next_cursor = parse_public_feed(payload)
            except Exception as exc:
                errors += 1
                termination = "public_feed_error"
                audit.append(dict(listing=url, status="listing_error", reason=str(exc), error_type=type(exc).__name__, feed=kind + ":" + name))
                break
            identity = tuple(entry.get("publisher_id") or entry["publisher_url"] for entry in entries)
            if entries and identity in identities:
                errors += 1
                termination = "public_feed_repeated_page"
                audit.append(dict(listing=url, status="listing_error", reason=termination, feed=kind + ":" + name))
                break
            identities.add(identity)
            new_ids = set(identity) - publisher_ids
            publisher_ids.update(identity)
            no_growth_pages = no_growth_pages + 1 if entries and not new_ids else 0
            if no_growth_pages >= 2:
                errors += 1
                termination = "public_feed_nonadvancing_inventory"
                audit.append(dict(listing=url, status="listing_error", reason=termination, feed=kind + ":" + name))
                break
            primary_dates, page_results, candidates = [], [], []
            for entry in entries:
                if entry.get("first_publish_date"):
                    try:
                        day = _publisher_day(entry["first_publish_date"])
                        if day:
                            primary_dates.append(date.fromisoformat(day))
                    except (ValueError, TypeError):
                        pass
                canonical = entry["url"]
                if not canonical:
                    audit.append(dict(url=entry["publisher_url"], listing=url, status="excluded_path", reason="nonfactual_or_unsupported_article_path"))
                    continue
                growth.add(canonical)
                entry["listing"] = url
                cached = articles.get(canonical)
                # The archive already verified/prescreened this URL. Details
                # are still required for old-page boundary corroboration.
                is_boundary_page = bool(primary_dates and max(primary_dates) < cutoff - timedelta(days=2))
                if canonical in visited and not is_boundary_page:
                    if (cached and _cached_capture_dates_valid(cached.get("metadata", {}))
                            and (cached.get("metadata", {}).get("article_verified")
                                   or verified_video_without_text(cached.get("metadata", {}))
                                   or verified_publication_date_conflict(cached.get("metadata", {}))
                                   or verified_sponsored_without_text(cached.get("metadata", {})))):
                        page_results.append((entry, dict(cached, cache_hit=True)))
                        continue
                candidates.append(entry)
            with ThreadPoolExecutor(max_workers=worker_count) as pool:
                verified = list(pool.map(lambda entry: _verified_detail(entry, loader, articles.get(entry["url"]), audit), candidates))
            page_results.extend(zip(candidates, verified))
            detail_dates = []
            page_errors = 0
            for entry, result in page_results:
                if result.get("status") == "detail_error":
                    errors += 1
                    page_errors += 1
                    audit.append(dict(result, feed=kind + ":" + name))
                    continue
                metadata = result["metadata"]
                day, status, reason = _inventory_disposition(result, cutoff, today)
                if day:
                    detail_dates.append(day)
                    observed_dates.append(day)
                else:
                    publisher_exceptions += 1
                    page_errors += 1  # date unknown, independently breaks boundary
                articles[result["url"]] = {key: val for key, val in result.items() if key != "cache_hit"}
                was_seen = result["url"] in visited
                visited.add(result["url"])
                audit.append(dict(_primary_trace(metadata), url=result["url"], listing=url,
                                  feed=kind + ":" + name, status=status, reason=reason,
                                  title=result["title"], cache_hit=result["cache_hit"],
                                  first_publish_date=entry.get("first_publish_date"), duplicate_inventory_url=was_seen,
                                  in_complete_30_days=bool(day and today - timedelta(days=30) <= day < today),
                                  in_complete_90_days=bool(day and cutoff <= day < today), current_day_slice=day == today))
                if status in ("discovered", "discovered_metadata_only") and not was_seen:
                    out.append(RawItem("pulso_latercera", result["title"], result["url"], "Pulso / La Tercera", "press_high_trust",
                                       event_date=metadata["publication_date"], raw_text=result["body"], metadata=metadata))
            # Stop only on a sustained publisher first-publication boundary,
            # corroborated against final dates of all factual URLs on each
            # boundary page. Excluded opinion paths remain inventoried.
            factual_count = sum(bool(entry["url"]) for entry in entries)
            old = (len(entries) == 24 and len(primary_dates) == len(entries)
                   and max(primary_dates) < cutoff - timedelta(days=2)
                   and len(detail_dates) == factual_count and not page_errors
                   and (not detail_dates or max(detail_dates) < cutoff - timedelta(days=2)))
            old_pages = old_pages + 1 if old else 0
            audit.append(dict(listing=url, status="public_feed_page", feed=kind + ":" + name, offset=offset,
                              count=total, next=next_cursor, primary_entries=len(entries), unique_urls=len(growth),
                              json_sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                              inventory_day_min=min(primary_dates).isoformat() if primary_dates else None,
                              inventory_day_max=max(primary_dates).isoformat() if primary_dates else None,
                              verified_details=len(detail_dates), boundary_pages=old_pages))
            last_saved = _checkpoint_feed_cache(cache_path, cache, last_saved)
            if old_pages >= 3:
                complete, termination = not errors, "three_publication_ordered_detail_verified_old_pages"
                break
            # A complete, count-delimited feed can be shorter than the window;
            # unlike a publisher's capped global sitemap, its explicit total
            # identifies the scope whose entire history has been traversed.
            at_count = isinstance(total, int) and offset + len(entries) >= total and total < 10000
            if at_count:
                complete, termination = not errors, "all_feed_count_delimited_articles"
                break
            if not entries:
                termination = "feed_exhausted_without_verified_window"
                break
            if not isinstance(next_cursor, int) or next_cursor <= offset or next_cursor > offset + 24:
                errors += 1
                termination = "nonadvancing_public_feed_cursor"
                audit.append(dict(listing=url, status="listing_error", reason=termination, feed=kind + ":" + name))
                break
            offset = next_cursor
        if page_count >= max_feed_pages and not complete:
            termination = "explicit_public_feed_page_limit"
        summary = dict(status="public_feed_coverage", feed=kind + ":" + name, coverage_complete=complete,
                       pages_attempted=page_count, unique_urls=len(growth), publisher_count=total, errors=errors,
                       publisher_exceptions=publisher_exceptions,
                       enumerated_with_editorial_exceptions=bool(publisher_exceptions),
                       publication_date_coverage_complete=complete and not publisher_exceptions,
                       article_content_coverage_complete=complete and not publisher_exceptions and not any(
                           row.get("feed") == kind + ":" + name and row.get("source_content_unavailable_reason")
                           and row.get("status") == "discovered_metadata_only" for row in audit),
                       termination=termination, verified_publication_day_min=min(observed_dates).isoformat() if observed_dates else None)
        last_saved = _checkpoint_feed_cache(cache_path, cache, last_saved, force=True)
        summaries.append(summary)
        audit.append(summary)
        if not complete:
            audit.append(dict(listing=_public_feed_url(kind, name, offset, deployment), status="listing_error",
                              reason="public_feed_coverage_incomplete", feed=kind + ":" + name, termination=termination))
    complete = bool(summaries and all(item["coverage_complete"] for item in summaries))
    summary = dict(status="runtime_coverage", mechanism="normal_public_frontend_pagination_and_official_rss",
                   coverage_complete=complete, required_feeds=[kind + ":" + name for kind, name in feeds],
                   publisher_exceptions=sum(item["publisher_exceptions"] for item in summaries),
                   enumerated_with_editorial_exceptions=any(item["enumerated_with_editorial_exceptions"] for item in summaries),
                   publication_date_coverage_complete=complete and all(item["publication_date_coverage_complete"] for item in summaries),
                   article_content_coverage_complete=complete and all(item["article_content_coverage_complete"] for item in summaries),
                   complete_30_days=dict(start=(today - timedelta(days=30)).isoformat(), end=(today - timedelta(days=1)).isoformat()),
                   complete_90_days=dict(start=cutoff.isoformat(), end=(today - timedelta(days=1)).isoformat()),
                   current_day_slice=today.isoformat(), new_inventory_urls=len(out),
                   new_health_urls=sum(not item.metadata.get("publisher_exception_reason")
                                       and not item.metadata.get("source_content_unavailable_reason") for item in out),
                   metadata_only_video_candidates=sum(item.metadata.get("publisher_document_type") == "video" and not item.metadata.get("article_body_complete", True) for item in out),
                   metadata_only_date_conflict_candidates=sum(item.metadata.get("publisher_exception_reason") == "publisher_conflicting_publication_dates" for item in out),
                   metadata_only_sponsored_candidates=sum(item.metadata.get("publisher_exception_reason") == "publisher_sponsored_content_review_required" for item in out),
                   metadata_only_sponsored_text_unavailable_candidates=sum(item.metadata.get("publisher_exception_reason") == "publisher_sponsored_text_unavailable" for item in out),
                   publication_date_coverage_only_for_text_unavailable_candidates=True)
    audit.append(summary)
    return out, summary


def discover_pulso(detail_loader=None, audit=None, *, cache_path=None, today=None, workers=4,
                   max_pages=3, include_listings=True, include_public_feeds=True, feeds=None, max_feed_pages=250):
    """Normal daily source hook: historical inventory first, live surfaces second."""
    from pathlib import Path
    from .paths import project_root
    detail_loader = detail_loader or fetch_html
    audit = audit if audit is not None else []
    cache_path = Path(cache_path) if cache_path is not None else project_root() / "data/state/pulso_discovery_cache.json"
    visited, out = set(), []
    public_coverage = dict(coverage_complete=False)
    if include_public_feeds:
        out, public_coverage = discover_public_feeds(detail_loader, audit, cache_path, visited=visited,
                                                     today=today, workers=workers, feeds=feeds, max_feed_pages=max_feed_pages)
    # The historical section/taxonomy traversal is primary. A bounded global
    # RSS/sitemap slice supplies current cross-section discoveries without
    # delaying the 90-day recovery behind unrelated historical sports/culture.
    extra, archive_visited, coverage = discover_archive(detail_loader, audit, cache_path, today=today,
                                                        workers=workers, max_pages=max_pages)
    out.extend(extra)
    visited.update(archive_visited)
    if include_public_feeds:
        # The global index's hard cap is a documented surface limitation. A
        # complete normal frontend inventory can independently satisfy 90 days.
        if public_coverage["coverage_complete"]:
            max_advertised_offset = max(0, (coverage.get("advertised_pages", 0) - 1) * 100)
            for entry in audit:
                if entry.get("status") != "listing_error":
                    continue
                listing = entry.get("listing", "")
                offset = int(parse_qs(urlparse(listing).query).get("from", [0])[0])
                if entry.get("reason") == "archive_coverage_incomplete" or (
                        "/arc/outboundfeeds/sitemap/" in listing and offset > max_advertised_offset):
                    entry["status"] = "surface_limit"
                    entry["covered_by"] = "normal_public_frontend_pagination"
    if include_listings:
        for listing in LISTINGS:
            try:
                html = _request_with_retries(detail_loader, listing, audit, scope="publisher_listing")
            except Exception as exc:
                audit.append(dict(listing=listing, status="surface_error", reason=str(exc), error_type=type(exc).__name__))
                continue
            out.extend(discover_listing(html, listing, detail_loader, audit, visited))
    if not out:
        raise RuntimeError("Pulso / La Tercera has no verified, dated health articles")
    unique = {}
    for item in out:
        unique.setdefault(item.url, item)
    diagnosed, inventory_discoveries = set(), 0
    metadata_diagnosed, metadata_occurrences = set(), 0
    for entry in audit:
        if entry.get("status") == "discovered_metadata_only" and entry.get("url"):
            metadata_occurrences += 1
            entry["duplicate_inventory_url"] = entry["url"] in metadata_diagnosed
            metadata_diagnosed.add(entry["url"])
        if entry.get("status") != "discovered" or not entry.get("url"):
            continue
        inventory_discoveries += 1
        entry["duplicate_inventory_url"] = entry["url"] in diagnosed
        diagnosed.add(entry["url"])
    audit.append(dict(status="discovery_inventory", unique_inventory_urls=len(unique),
                      unique_health_urls=sum(not item.metadata.get("publisher_exception_reason")
                                             and not item.metadata.get("source_content_unavailable_reason")
                                             for item in unique.values()),
                      unique_metadata_only_urls=len(metadata_diagnosed),
                      inventory_metadata_only_occurrences=metadata_occurrences,
                      inventory_health_occurrences=inventory_discoveries,
                      duplicate_inventory_occurrences=inventory_discoveries - len(diagnosed)))
    # Unknown publisher dates remain pending; they cannot be compared to ISO
    # dates or acquire a synthetic ingestion/publication day during sorting.
    return sorted(unique.values(), key=lambda item: item.event_date or "", reverse=True)
