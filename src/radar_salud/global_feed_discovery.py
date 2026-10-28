"""Licensed RSS/Atom metadata discovery for Global (no bodies, no AI, no publication).

Each feed in ``config/global_discovery.json`` ``feeds`` declares a ``rights`` basis.
Only the publisher's own title, link, date, byline and categories are kept. The
publisher's own short summary (RSS ``description`` / Atom ``summary``) is kept only
when the feed's rights allow it (``store_description``: public domain, OGL, CC BY or
an equivalent reuse notice), verbatim and capped at ``DESCRIPTION_MAX`` characters.
``content:encoded`` / Atom ``content`` (the body) is never read, stored or rewritten,
and a description that is really a body (longer than ``DESCRIPTION_BODY_LIMIT``) is
dropped: the card then shows the title only. Nothing is ever invented.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit, urlunsplit

from .global_discovery_common import canonical_url
from .global_relevance import global_interest, source_rules, validate_rules

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "rss1": "http://purl.org/rss/1.0/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}
REQUIRED_RIGHTS = {"basis", "license", "evidence_urls", "permitted_use", "automated_access", "attribution", "verified_on"}
PERMITTED_USE = "metadata_title_link_byline_only"
DESCRIPTION_MAX = 300
DESCRIPTION_BODY_LIMIT = 1200
SEGMENTS = ("payers", "providers", "pharma", "regulation", "healthtech", "ai_in_health")


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (text or "").casefold()) if not unicodedata.combining(c))


class _TextOnly(HTMLParser):
    """Text outside real tags. Tags are tokenized first; character references in text are then
    decoded exactly once by the parser (convert_charrefs), so decoded "<" can never become a tag."""

    SKIP = {"script", "style"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skipping = [], 0

    def handle_starttag(self, tag, attrs):
        self.skipping += tag in self.SKIP
        self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skipping:
            self.skipping -= 1
        self.parts.append(" ")

    def handle_startendtag(self, tag, attrs):
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


# Entity references left in the TEXT after the markup layer was decoded: the feed escaped twice
# ("&amp;lt;5" -> "&lt;5"). Only these well-formed references count; a bare "&" is left alone.
_RESIDUAL_ENTITY = re.compile(r"&(?:lt|gt|amp|quot|apos|nbsp|#\d{1,7}|#[xX][0-9A-Fa-f]{1,6});")


def _clean(text) -> str:
    """Plain, readable text from a feed field; never reworded, nothing between "<" and ">" lost.

    1. The markup layer is parsed first (HTML parser): real tags are dropped and character
       references are decoded exactly once, so a decoded "<" can never become a tag.
    2. If the resulting TEXT still holds entity references, the publisher escaped twice
       ("Children &amp;lt;5" -> "Children &lt;5"): that text layer is decoded once with
       html.unescape and is NOT parsed as markup again, so "<5 ... >65" stays as words.
    The result is plain text (it may contain "<", ">" or "&"); the web UI escapes it exactly
    once when rendering (esc() in web/global.js)."""
    parser = _TextOnly()
    parser.feed(str(text or ""))
    parser.close()
    value = "".join(parser.parts)
    if _RESIDUAL_ENTITY.search(value):
        value = unescape(value)
    return " ".join(value.split())


def publisher_summary(raw) -> tuple[str | None, bool]:
    """Publisher's own short summary, verbatim (markup/entities removed), at most DESCRIPTION_MAX chars.

    Longer summaries are cut at the last sentence end that fits, else at a word boundary; a cut
    summary ALWAYS ends with "…" (also after a sentence end) and is flagged as truncated. Text
    longer than DESCRIPTION_BODY_LIMIT is a body, not a summary: it is dropped (title only)."""
    text = _clean(raw)
    if not text or len(text) > DESCRIPTION_BODY_LIMIT:
        return None, False
    if len(text) <= DESCRIPTION_MAX:
        return text, False
    head = text[:DESCRIPTION_MAX - 2]  # room for " …"
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s)", head + " ")]
    if ends and ends[-1] >= 80:
        return head[:ends[-1]].rstrip() + " …", True
    return head.rsplit(" ", 1)[0].rstrip(" ,;:-") + "…", True


# Redirect/click-tracking links (e.g. GovDelivery e-mail links) are NEVER fetched. A redirect link is
# accepted only when the official target URL is written inside the link itself (query parameter,
# GovDelivery /CL0/<encoded URL>/ path, or lnks.gd JWT payload) and that target is on the feed's own
# allowed hosts; anything else (content.govdelivery.com bulletins, opaque short links) is rejected.
REDIRECT_QUERY_KEYS = {"url", "u", "target", "redirect", "redirect_url", "dest", "destination"}


def _embedded_target(link: str) -> str | None:
    parts = urlsplit(link)
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in REDIRECT_QUERY_KEYS and re.match(r"https?://", value, re.I):
            return value
    path = parts.path
    match = re.match(r"^/CL0/(https?:[^/]+)", path, re.I)  # GovDelivery: the target is ONE percent-encoded segment
    if match:
        return unquote(match.group(1))
    match = re.match(r"^/l/([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)\.", path)  # lnks.gd JWT; the payload is read, never verified or fetched
    if match:
        try:
            payload = json.loads(base64.urlsafe_b64decode(match.group(2) + "=" * (-len(match.group(2)) % 4)))
        except (ValueError, TypeError):
            return None
        target = payload.get("url") if isinstance(payload, dict) else None
        return target if isinstance(target, str) and re.match(r"https?://", target, re.I) else None
    return None


def _official_link(link: str, base: str, feed: dict, hosts: set) -> str:
    """Absolute https URL on an allowed host. http is upgraded and configured host aliases
    (e.g. fda.gov -> www.fda.gov) are mapped ONLY for the publisher's own hosts."""
    parts = urlsplit(urljoin(base, link))
    host = (parts.hostname or "").lower()
    host = (feed.get("link_host_aliases") or {}).get(host, host)
    if parts.scheme not in {"http", "https"} or host not in hosts:
        raise ValueError("unapproved public URL")
    netloc = host if parts.port in (None, 80, 443) and not (parts.username or parts.password) else parts.netloc
    return canonical_url(urlunsplit(("https", netloc, parts.path, parts.query, "")), "", hosts)


def resolve_feed_link(link: str, base: str, feed: dict, hosts: set) -> tuple[str, str | None]:
    """(canonical official URL, redirect host it was decoded from or None). Raises ValueError otherwise."""
    try:
        return _official_link(link, base, feed, hosts), None
    except ValueError:
        pass
    parts = urlsplit(urljoin(base, link))
    redirect_hosts = set(feed.get("redirect_link_hosts") or [])
    host = (parts.hostname or "").lower()
    if parts.scheme == "https" and host in redirect_hosts:
        target = _embedded_target(urljoin(base, link))
        if target:
            # One level only: the decoded target must itself be an official link, not another redirect.
            return _official_link(target, "", feed, hosts), host
    raise ValueError("unapproved public URL")


def validate_feed_config(feed: dict) -> None:
    rights = feed.get("rights") or {}
    missing = REQUIRED_RIGHTS - set(rights)
    if missing:
        raise ValueError("feed rights basis incomplete: " + ",".join(sorted(missing)))
    if rights["permitted_use"] != PERMITTED_USE or rights["automated_access"] not in {"rss_offered_by_publisher", "public_domain_government_feed", "reuse_permitted_with_acknowledgement"}:
        raise ValueError("feed rights do not permit automated metadata+link use")
    if not feed.get("attribution") or not feed.get("allowed_link_hosts") or not feed.get("routes"):
        raise ValueError("feed attribution/hosts/routes missing")
    if feed.get("store_description") and not rights.get("description_basis"):
        # Keeping the publisher's summary needs its own recorded rights basis (fail closed).
        raise ValueError("store_description without rights.description_basis")
    if "include_title_patterns" in feed:
        # Dirección 28-oct 09:58: no "always include" rule (safety alerts are excluded like any one-off).
        raise ValueError("include_title_patterns is not allowed (Dirección 28-oct 09:58)")
    for pattern in feed.get("exclude_title_patterns", []):
        re.compile(pattern)
    hosts = set(feed["allowed_link_hosts"])
    if not set((feed.get("link_host_aliases") or {}).values()) <= hosts:
        raise ValueError("link_host_aliases must map onto allowed_link_hosts")
    if set(feed.get("redirect_link_hosts") or []) & hosts:
        raise ValueError("a redirect host cannot also be an allowed link host")


def enabled_routes(feed: dict) -> list[dict]:
    """Routes that run: a route can be held off on its own (``"enabled": false``) while the feed runs."""
    return [route for route in feed.get("routes", []) if route.get("enabled", True) is not False]


def feed_day(raw: str | None, as_of: date) -> tuple[str | None, str | None]:
    """Publisher-declared day in the publisher's own offset; future/invalid -> None."""
    text = (raw or "").strip()
    if not text:
        return None, "missing_feed_publication_date"
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}", text):
            value = datetime.fromisoformat(text.replace("Z", "+00:00")) if "T" in text else datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
        else:
            value = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None, "invalid_feed_publication_date"
    if value is None:
        return None, "invalid_feed_publication_date"
    day = value.date()
    if day > as_of:
        return None, "future_feed_publication_date"
    return day.isoformat(), None


def _text(node, path):
    found = node.find(path, NS)
    return found.text if found is not None and found.text else ""


PROLOG_SKIP = re.compile(r"\s+|<\?.*?\?>|<!--.*?-->", re.S)


def xml_prolog(raw: bytes) -> str:
    """Everything before the root element (XML declaration, PIs, comments, DOCTYPE), however long.

    A fixed-size head window could be bypassed by padding the prolog (e.g. a long comment) before
    a DOCTYPE/ENTITY; this walks the whole prolog instead."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace").lstrip("\ufeff")
    pos = 0
    while pos < len(text):
        match = PROLOG_SKIP.match(text, pos)
        if match and match.end() > pos:
            pos = match.end()
            continue
        break
    return text[:pos] + text[pos:pos + 2] if text.startswith("<!", pos) else text[:pos]


def parse_feed(raw: bytes, route: dict, feed: dict, as_of: date) -> list[dict]:
    """Parse RSS 2.0, RSS 1.0 (RDF) or Atom. Raises on non-feed bodies (e.g. HTML challenge)."""
    prolog = xml_prolog(raw)
    if re.search(r"<!DOCTYPE|<!ENTITY", prolog, re.I) or prolog.endswith("<!"):
        raise ValueError("feed_doctype_or_entity_rejected")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("feed_xml_parse_error: " + str(exc)[:120]) from exc
    tag = root.tag.split("}")[-1].lower()
    hosts = set(feed["allowed_link_hosts"])
    entries = []
    if tag == "rss":
        channel = root.find("channel")
        if channel is None:
            raise ValueError("rss_channel_missing")
        for item in channel.findall("item"):
            entries.append({
                "title": _text(item, "title"), "link": _text(item, "link") or (_text(item, "guid") if (item.find("guid") is not None and (item.find("guid").get("isPermaLink", "true").lower() == "true")) else ""),
                "guid": _text(item, "guid"), "date": _text(item, "pubDate") or _text(item, "dc:date"), "summary": _text(item, "description"),
                "bylines": [_clean(n.text) for n in item.findall("dc:creator", NS) if n.text] + [_clean(n.text) for n in item.findall("author") if n.text],
                "categories": [_clean(n.text) for n in item.findall("category") if n.text] + [_clean(n.text) for n in item.findall("dc:subject", NS) if n.text]})
    elif tag == "feed":
        for item in root.findall("atom:entry", NS):
            links = [l for l in item.findall("atom:link", NS) if l.get("href") and l.get("rel", "alternate") == "alternate"]
            entries.append({
                "title": _text(item, "atom:title"), "link": links[0].get("href") if links else "", "guid": _text(item, "atom:id"),
                "date": _text(item, "atom:published") or _text(item, "atom:updated"), "summary": _text(item, "atom:summary"),
                "bylines": [_clean(_text(a, "atom:name")) for a in item.findall("atom:author", NS) if _text(a, "atom:name")],
                "categories": [_clean(c.get("term") or c.get("label")) for c in item.findall("atom:category", NS) if c.get("term") or c.get("label")]})
    elif tag == "rdf":
        for item in root.findall("rss1:item", NS):
            entries.append({"title": _text(item, "rss1:title"), "link": _text(item, "rss1:link"), "guid": item.get(f"{{{NS['rdf']}}}about", ""),
                            "date": _text(item, "dc:date"), "summary": _text(item, "rss1:description"), "bylines": [_clean(n.text) for n in item.findall("dc:creator", NS) if n.text],
                            "categories": [_clean(n.text) for n in item.findall("dc:subject", NS) if n.text]})
    else:
        raise ValueError("not_a_feed_document: " + tag[:40])
    rows = []
    for entry in entries:
        title = _clean(entry["title"])
        row = {"source": feed["id"], "section": route["section"], "feed_url": route["url"], "title": title,
               "attribution": feed["attribution"], "bylines": list(dict.fromkeys(b for b in entry["bylines"] if b)),
               "categories": sorted({c for c in entry["categories"] if c}), "guid": _clean(entry["guid"]) or None,
               "raw_publication_dates": [entry["date"]] if entry["date"] else [], "publication_date_basis": "publisher_feed_declared_date",
               "content_use": "metadata_and_link_only", "body_stored": False}
        raw_link = _clean(entry["link"])
        try:
            row["url"], via = resolve_feed_link(raw_link, route["url"], feed, hosts)
        except ValueError:
            raw_parts = urlsplit(urljoin(route["url"], raw_link))
            row.update(url=None, status="rejected", reason="link_outside_licensed_publisher_hosts", raw_link=raw_link[:300],
                       raw_link_scheme=raw_parts.scheme or None, raw_link_host=(raw_parts.hostname or None))
            rows.append(row)
            continue
        if via:
            row["link_resolution"] = {"method": "official_target_decoded_from_redirect_link_without_fetch", "redirect_host": via}
        if not title:
            row.update(status="rejected", reason="missing_publisher_title")
            rows.append(row)
            continue
        row["published_at"], row["publication_date_error"] = feed_day(entry["date"], as_of)
        # A route may withhold summaries (FDA MedWatch links to company recall notices: not public domain).
        if feed.get("store_description") and route.get("store_description", True) is not False:
            row["description"], row["description_truncated"] = publisher_summary(entry.get("summary"))
            row["description_basis"] = "publisher_feed_summary_verbatim" if row["description"] else None
        rows.append(row)
    return rows


# Deterministic relevance for Chilean healthcare executives. Keyword hits on the
# publisher's title/categories only; no summary, no paid model (paid_ai_calls=0).
SEGMENT_RULES = {
    "payers": r"\binsur|\bpayer|medicare|medicaid|health plans?\b|premium|coverage|reimburs|affordable care act|\baca\b|obamacare|prior authori|\bpbm|pharmacy benefit|copay|deductible|out-of-pocket|uninsured|medical debt|isapre|fonasa|seguro|aseguradora|cobertura",
    "providers": r"hospital|\bclinics?\b|\bclinicas?\b|health system|physician|doctor|nurs|nursing home|workforce|emergency room|private equity|merger|acquisition|rural health|staffing|billing|price transparency|long-term care|primary care|prestador|medicos?\b|enfermer",
    "pharma": r"\bdrug|pharma|medicine|vaccin|biosimilar|generic|glp-1|ozempic|wegovy|semaglutide|tirzepatide|prescription|\b340b\b|clinical trial|marketing authori[sz]ation|\bchmp\b|orphan|biologic|therap|insulin|antibiotic|antimicrobial|medicament|farmac|vacuna",
    "regulation": r"\bfda\b|\bema\b|\bcms\b|regulat|\brule\b|\blaw\b|legislat|policy|guidance|guideline|approv|recall|warning letter|\bban\b|court|lawsuit|antitrust|ruling|executive order|tariff|authori[sz]ation|safety communication|referral|consultation|normativ|regulac|\bley\b|authori[sz]e[sd]?\b|authori[sz]ing",
    "healthtech": r"telehealth|telemedicine|digital health|health data|data space|\behds\b|health tech|\bapps?\b|wearable|electronic health record|\behr\b|cybersecur|ransomware|data breach|medical device|\bdevices?\b|software|interoperab|digital|telesalud",
    "ai_in_health": r"artificial intelligence|\bai\b|machine learning|algorithm|chatbot|large language model|\bllm|generative|inteligencia artificial|\bia\b",
}
EXCLUSION_RULES = (
    ("podcast_or_multimedia", r"podcast|what the health\?|an arm and a leg|^watch:|^listen:|\bvideo:|^kff health news'"),
    ("newsletter_digest", r"morning briefing|^first edition|readers and tweeters|letters? to the editor|^in case you missed"),
    ("institutional_routine", r"\b(appointed|appointment|anniversary|webinar|training|celebrates|congratulates|obituar|honou?rs?|award(?:s|ed)?|career|vacanc|procurement|tender)\b"),
    ("preclinical_animal_study", r"\bin (mice|mouse|rats?)\b|\bmice\b|\bmouse\b|fruit fl(y|ies)|zebrafish"),
    ("advisory_panel_meeting", r"advisory (committee|panel|board|council)s?\b.*\bmeeting|\bmeeting\b.*\badvisory (committee|panel|board|council)|notice of (a )?(public )?meeting|\bpanel meeting\b"),
    ("out_of_scope_consumer_product", r"\b(food|foods|infant formula|tobacco|cigarette|vape|vaping|e-cigarette|cosmetic|tattoo|pet food|veterinar|animal)\b"),
)
# Immunization coverage is epidemiology, not insurance coverage (payers).
VACCINE_COVERAGE = r"(vaccin\w*|immuni[sz]ation|vacunacion|inmunizacion)\s+(rate\s+)?coverage|coverage\s+(of|for|with)\s+(\w+\s+){0,2}(vaccin\w*|immuni[sz]ation|doses?)|cobertura\s+(de\s+)?(vacunacion|inmunizacion|vacunas?)"
ROUTINE_REGULATOR_EVENTS = r"^(event|agenda|minutes)\b|^meeting (agenda|minutes)\b|\bevents?\b.*\b(registration|stakeholder)\b"


def classify_relevance(title: str, categories=(), *, default_segments=()) -> dict:
    text = _fold(" ".join([title or "", *categories]))
    title_text = _fold(title or "")
    for reason, pattern in EXCLUSION_RULES:
        if re.search(pattern, title_text):
            # A drug/device product recall is pharma/healthtech, not a consumer exclusion.
            if reason == "out_of_scope_consumer_product" and re.search(SEGMENT_RULES["pharma"] + "|medical device", title_text):
                continue
            return {"materiality": "excluded", "relevant": False, "segments": [], "priority": 0, "category": reason,
                    "reason": "irrelevant_for_chilean_health_executives:" + reason, "method": "deterministic_rules_v1",
                    "ai_gate": {"invoked": False, "reason": "paid_ai_calls_contract_0"}}
    if re.search(ROUTINE_REGULATOR_EVENTS, title_text):
        return {"materiality": "excluded", "relevant": False, "segments": [], "priority": 0, "category": "institutional_routine",
                "reason": "irrelevant_for_chilean_health_executives:institutional_routine", "method": "deterministic_rules_v1",
                "ai_gate": {"invoked": False, "reason": "paid_ai_calls_contract_0"}}
    matched = [segment for segment in SEGMENTS
               if re.search(SEGMENT_RULES[segment], re.sub(VACCINE_COVERAGE, " ", text) if segment == "payers" else text)]
    segments = matched or [s for s in default_segments if s in SEGMENTS]
    if not segments:
        return {"materiality": "excluded", "relevant": False, "segments": [], "priority": 0, "category": "no_segment_match",
                "reason": "irrelevant_for_chilean_health_executives:no_segment_match", "method": "deterministic_rules_v1",
                "ai_gate": {"invoked": False, "reason": "paid_ai_calls_contract_0"}}
    priority = min(95, 60 + 8 * len(matched) + (10 if "ai_in_health" in matched else 0) + (5 if "regulation" in matched else 0))
    return {"materiality": "candidate", "relevant": True, "segments": segments, "priority": priority,
            "category": segments[0], "reason": "segment_keyword_match" if matched else "publisher_default_segment",
            "method": "deterministic_rules_v1", "ai_gate": {"invoked": False, "reason": "paid_ai_calls_contract_0"},
            "chile_transfer": "hypothesis_only"}


def collect_feeds(config: dict, client, as_of: date) -> tuple[list[dict], list[dict], dict]:
    window = int(config.get("inventory_window_days", 90))
    items, failures, routes = {}, [], {}
    validate_rules(config)
    for feed in config.get("feeds", []):
        validate_feed_config(feed)
        if not feed.get("enabled", False):
            continue
        for route in enabled_routes(feed):
            key = feed["id"] + "/" + route["section"]
            stage = "robots"
            try:
                # robots.txt is checked first and separately so a failure says WHICH request failed
                # (28-oct: CDC http_406 / NIH http_403 did not say whether robots.txt or the feed).
                if hasattr(client, "check_robots"):
                    client.check_robots(canonical_url(route["url"], "", getattr(client, "hosts", None)))
                stage = "feed"
                raw, capture = client.fetch(route["url"])
                stage = "parse"
                rows = parse_feed(raw, route, feed, as_of)
            except Exception as exc:
                failures.append({"source": feed["id"], "section": route["section"], "url": route["url"], "stage": stage,
                                 "error": type(exc).__name__ + ": " + str(exc)[:200]})
                routes[key] = {"source": feed["id"], "section": route["section"], "url": route["url"], "status": "error", "entries": 0}
                continue
            evidence = {"feed_url": route["url"], "body_sha256": capture["body_sha256"], "fetched_at": capture["fetched_at"],
                        "http_status": capture["http_status"], "tls_verified": capture["tls_verified"]}
            routes[key] = {"source": feed["id"], "section": route["section"], "url": route["url"], "status": "ok", "entries": len(rows),
                           "oldest_entry": min((r["published_at"] for r in rows if r.get("published_at")), default=None),
                           "newest_entry": max((r["published_at"] for r in rows if r.get("published_at")), default=None),
                           "capture": evidence}
            for row in rows:
                if row.get("status") == "rejected":
                    # The rejected link's scheme/host are recorded so the run data shows WHY (28-oct: FDA had none).
                    failures.append({"source": feed["id"], "section": route["section"], "url": route["url"], "error": row["reason"], "rejected_entry": True,
                                     "raw_link_scheme": row.get("raw_link_scheme"), "raw_link_host": row.get("raw_link_host")})
                    continue
                if row["published_at"] and (as_of - date.fromisoformat(row["published_at"])).days >= window:
                    continue
                identity = row["url"]
                if identity in items:
                    previous = items[identity]
                    previous["sections"] = sorted(set(previous["sections"] + [route["section"]]))
                    previous["index_evidence"].append(evidence)
                    previous["categories"] = sorted(set(previous["categories"] + row["categories"]))
                    # Same publisher, another route: may fill a missing summary. Never across publishers.
                    if previous["source"] == row["source"] and not previous.get("description") and row.get("description"):
                        previous.update(description=row["description"], description_truncated=row["description_truncated"],
                                        description_basis=row["description_basis"])
                    if previous["published_at"] != row["published_at"]:
                        previous.update(published_at=None, publication_date_error="conflicting_feed_dates")
                    continue
                row["sections"] = [route["section"]]
                row["index_evidence"] = [evidence]
                items[identity] = row
    result = []
    defaults = {feed["id"]: feed.get("default_segments", []) for feed in config.get("feeds", [])}
    title_exclusions = {feed["id"]: feed.get("exclude_title_patterns", []) for feed in config.get("feeds", [])}
    rights_by_feed = {feed["id"]: feed.get("rights") or {} for feed in config.get("feeds", [])}
    for row in items.values():
        row["classification"] = classify_relevance(row["title"], row["categories"], default_segments=defaults.get(row["source"], ()))
        # Publisher-specific routine document types (e.g. GOV.UK "Transparency data:", "FOI release:").
        if any(re.search(p, _fold(row["title"])) for p in title_exclusions.get(row["source"], [])):
            row["classification"] = {"materiality": "excluded", "relevant": False, "segments": [], "priority": 0,
                                     "category": "publisher_routine_document_type",
                                     "reason": "irrelevant_for_chilean_health_executives:publisher_routine_document_type",
                                     "method": "deterministic_rules_v1", "ai_gate": {"invoked": False, "reason": "paid_ai_calls_contract_0"}}
        # Dirección 28-oct 09:58: Global = trends and global interest (no recalls/alerts, beds, acquisitions,
        # openings or single-product approvals). Recorded on every row; a relevant row must also pass it.
        interest = global_interest(row["title"], row["categories"], source=row["source"], rules=source_rules(config, row["source"]))
        row["global_interest"] = interest
        if row["classification"]["relevant"] and not interest["relevant"]:
            row["classification"] = {"materiality": "excluded", "relevant": False, "segments": [], "priority": 0,
                                     "category": interest["category"], "reason": interest["reason"], "method": interest["method"],
                                     "ai_gate": {"invoked": False, "reason": "paid_ai_calls_contract_0"}}
        row["publication_ready"] = False
        rights = rights_by_feed.get(row["source"], {})
        # Paid tiers need the publisher's written confirmation when the licence is NonCommercial (KFF).
        row["paid_tier_eligible"] = not rights.get("paid_tier_requires_publisher_confirmation") or bool(rights.get("paid_tier_confirmation"))
        if not row["paid_tier_eligible"]:
            row["paid_tier_hold"] = "publisher_confirmation_required_before_paid_or_commercial_use"
        if row.get("publication_date_error"):
            row.update(status="pending", reason=row["publication_date_error"])
        elif row["classification"]["relevant"]:
            row.update(status="pending", reason="awaiting_editorial_corroboration_and_rights_review")
        else:
            row.update(status="rejected", reason=row["classification"]["reason"])
        row["item_id"] = hashlib.sha256(row["url"].encode()).hexdigest()[:20]
        result.append(row)
    result.sort(key=lambda r: (r["source"], r.get("published_at") or "", r["url"]), reverse=True)
    return result, failures, routes


def feed_health(feed: dict, items: list[dict], failures: list[dict], routes: dict, as_of: date, checked_at: str | None) -> dict:
    own = [r for r in items if r["source"] == feed["id"]]
    own_routes = [r for r in routes.values() if r["source"] == feed["id"]]
    technical = [f for f in failures if f["source"] == feed["id"] and not f.get("rejected_entry")]
    def window(days):
        return sum(bool(r.get("published_at")) and 0 <= (as_of - date.fromisoformat(r["published_at"])).days < days for r in own)
    ok = bool(own_routes) and all(r["status"] == "ok" for r in own_routes) and not technical
    relevant = [r for r in own if r["classification"]["relevant"] and r.get("published_at")]
    return {"name": feed["name"], "discovery_scope": "global_intelligence", "checked_at": checked_at,
            "status": "warning" if ok else "error", "technical_status": "ok" if ok else "error",
            "operation_mode": "licensed_feed_metadata_only", "coverage_status": "feed_window_only",
            "coverage_completeness": "feed_window_only_not_archive", "coverage_window_days": 90,
            "outcome": "FEED_METADATA_CAPTURED" if ok else "FEED_TECHNICAL_HOLD",
            "recurrent_operation_proven": False, "cadence_validation_pending": True,
            "counts": {"30": window(30), "90": window(90)}, "recent_items": window(30), "unique_items": window(90),
            "material_items": len(relevant), "relevant_items": len(relevant),
            "excluded_items": sum(r["status"] == "rejected" for r in own), "rejected": sum(r["status"] == "rejected" for r in own),
            "deferred": sum(r["status"] == "pending" for r in own), "discovered": len(own), "new": 0, "published": 0,
            "pages_checked": len(own_routes), "parser_routes": [r["section"] for r in own_routes],
            "technical_failures": technical, "rights": feed["rights"], "attribution": feed["attribution"],
            "content_use": "metadata_and_link_only", "publication_activation": False,
            "publication_activation_basis": "not_authorized_by_direccion_feed_sources_are_discovery_only",
            "editorial_outcome": "discovery_only_pending_editorial_and_rights_review"}
