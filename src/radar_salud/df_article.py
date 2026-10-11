"""Publisher-specific DF evidence; publication dates never come from navigation.

Keep the original timestamps and discrepancies. dateModified and crawl dates
are not publication dates. The date is expressed in the publisher's Chile zone.
"""
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from pathlib import Path


def _day(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo:
            stamp = stamp.astimezone(ZoneInfo("America/Santiago"))
        return stamp.date().isoformat()
    except (ValueError, TypeError):
        return None


def article_url(value):
    parsed = urlsplit(value)
    return parsed.path.rstrip("/")


class _Article(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.stack = []
        self.paragraphs = []
        self.article = []
        self.json_blocks = []
        self.script = None
        self.times = []
        self.header = []
        self.visible = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            self.meta.setdefault(key, attrs.get("content") or "")
        if tag == "time" and attrs.get("datetime"):
            self.times.append(attrs["datetime"])
        if tag == "script":
            self.script = [] if attrs.get("type", "").lower() == "application/ld+json" else None
        if tag not in ("meta", "link", "br", "img", "input", "hr", "source", "wbr"):
            classes = attrs.get("class", "") + " " + attrs.get("id", "")
            body = tag == "article" or bool(re.search(r"\b(cuerpo|article-body|story-body|news-body)\b", classes, re.I))
            self.stack.append((tag, body))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "script" and self.script is not None:
            self.json_blocks.append("".join(self.script))
            self.script = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        tags = {t for t, _ in self.stack}
        if "script" in tags:
            if self.script is not None:
                self.script.append(data)
            return
        if tags & {"style", "nav", "footer", "aside", "noscript"}:
            return
        value = " ".join(data.split())
        if not value:
            return
        self.visible.append(value)
        if any(body for _, body in self.stack):
            self.article.append(value)
        if "p" in tags and "header" not in tags:
            self.paragraphs.append(value)
        if "time" in tags:
            self.header.append(value)


def _news_nodes(value):
    if isinstance(value, list):
        for node in value:
            yield from _news_nodes(node)
    elif isinstance(value, dict):
        kind = value.get("@type", [])
        kind = [kind] if isinstance(kind, str) else kind
        if any(x in kind for x in ("NewsArticle", "Article", "ReportageNewsArticle")):
            yield value
        yield from _news_nodes(value.get("@graph", []))


def parse_df_article(html, url):
    p = _Article()
    p.feed(html)
    nodes = []
    for block in p.json_blocks:
        try:
            nodes.extend(_news_nodes(json.loads(block)))
        except (ValueError, TypeError):
            continue
    selected = []
    for node in nodes:
        identity = node.get("url") or node.get("mainEntityOfPage")
        if isinstance(identity, dict):
            identity = identity.get("@id")
        if not identity or article_url(str(identity)) == article_url(url):
            selected.append(node)
    candidates = []
    for key in ("article:published_time", "cxenseparse:recs:publishtime", "datepublished", "publishdate"):
        if p.meta.get(key):
            candidates.append({"source": key, "value": p.meta[key], "day": _day(p.meta[key])})
    for node in selected:
        if node.get("datePublished"):
            candidates.append({"source": "jsonld:datePublished", "value": node["datePublished"], "day": _day(node["datePublished"])})
    # Only explicitly labelled publication text can contradict publisher metadata.
    labelled = re.search(r"\bPublicad[oa]\s*(?::|el)\s*(.{1,100})", " ".join(p.visible), re.I)
    if labelled:
        from .public_source_pipeline import _date
        # Select the first date next to the label, not an ISO incident/modification
        # date later in the paragraph (the generic _date prefers any ISO token).
        token=re.search(r"20\d{2}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]20\d{2}|\d{1,2}\s+de\s+\w+\s+de\s+20\d{2}",labelled[1],re.I)
        visible_day = _date(token[0]) if token else None
        if visible_day and _day(visible_day):
            candidates.append({"source": "visible:published_label", "value": labelled[1], "day": visible_day})
    # A time element is only a fallback: many pages have clocks in their header.
    if not candidates and len(p.times) == 1:
        candidates.append({"source": "time:datetime", "value": p.times[0], "day": _day(p.times[0])})
    valid = [c for c in candidates if c["day"]]
    conflict = len({c["day"] for c in valid}) > 1
    chosen = valid[0] if valid and not conflict else None
    resolution=None
    if conflict:
        decisions=json.loads((Path(__file__).resolve().parents[2]/"config/df_date_provenance.json").read_text())["decisions"]
        rule=decisions.get(article_url(url))
        if rule and all(any(c["source"]==source and c["value"]==rule[field] for c in valid)
                        for source,field in (("cxenseparse:recs:publishtime","expected_cx_timestamp"),
                                             ("jsonld:datePublished","expected_jsonld_timestamp"))):
            chosen=next((c for c in valid if c["source"]=="visible:published_label" and c["day"]==rule["selected_visible_day"]),None)
            if chosen:resolution=rule
    node = selected[0] if selected else {}
    body = node.get("articleBody") or " ".join(p.article) or " ".join(p.paragraphs)
    description = p.meta.get("og:description") or p.meta.get("description") or node.get("description") or ""
    return {
        "event_date": chosen["day"] if chosen else None,
        "raw_text": description or body[:1800],
        "metadata": {
            "page_text": body or description,
            "article_title": node.get("headline") or p.meta.get("og:title") or "",
            "article_section": node.get("articleSection") or p.meta.get("article:section") or "",
            "publication_date_source": chosen["source"] if chosen else None,
            "publication_timestamp": chosen["value"] if chosen else None,
            "publication_date_candidates": candidates,
            "publication_date_conflict": conflict,
            "publication_date_conflict_resolution": resolution,
            "article_content_source": "jsonld:articleBody" if node.get("articleBody") else "visible_article" if body else "description",
            "date_semantics": "publisher_publication_day_America/Santiago; incident date is separate",
        },
    }


def bind_df_article(raw, html):
    evidence = parse_df_article(html, raw.url)
    # Correct a previous unverifiable fallback only when publisher evidence exists.
    raw.event_date = evidence["event_date"]
    raw.raw_text = evidence["raw_text"]
    raw.metadata.update(evidence["metadata"])
    raw.metadata.pop("fetch_error", None)
    return raw
