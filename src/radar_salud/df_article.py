"""Publisher-specific DF evidence; publication dates never come from navigation.

Keep the original timestamps and discrepancies. dateModified and crawl dates
are not publication dates. The date is expressed in the publisher's Chile zone.
"""
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin
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
        self.primary = []
        self.json_blocks = []
        self.script = None
        self.times = []
        self.header = []
        self.visible = []
        self.publication_label = []
        self.primary_found = False
        self.images = []
        self.media = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag=='img' and attrs.get('src') and any(e[1] for e in self.stack):self.images.append(attrs['src'])
        if tag=='iframe' and attrs.get('src') and any(e[4] for e in self.stack):self.media.append(attrs['src'])
        if tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            self.meta.setdefault(key, attrs.get("content") or "")
        if (tag == "time" and attrs.get("datetime") and attrs.get("itemprop", "").lower()=="datepublished"
                and not any(entry[0] in ('nav','aside','footer') or entry[3] for entry in self.stack)):
            self.times.append(attrs["datetime"])
        if tag == "script":
            self.script = [] if attrs.get("type", "").lower() == "application/ld+json" else None
        if tag not in ("meta", "link", "br", "img", "input", "hr", "source", "wbr"):
            classes = attrs.get("class", "") + " " + attrs.get("id", "")
            primary = bool(re.search(r"\b(cuerpo|article-body|story-body|news-body)\b", classes, re.I))
            self.primary_found |= primary
            excluded = bool(re.search(r"\b(card|related|recommendations|newsletter|te-puede-interesar)\b", classes, re.I))
            publication_header=tag=='header' and bool(re.search(r'\benc-main\b',classes))
            publication_label=bool(re.search(r'\bauthor__date\b',classes))
            self.stack.append((tag, primary, tag == "article" and not excluded, excluded, publication_header, publication_label))

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
        tags = {entry[0] for entry in self.stack}
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
        if any(entry[4] for entry in self.stack) and any(entry[5] for entry in self.stack):
            self.publication_label.append(value)
        if any(entry[3] for entry in self.stack):
            return
        if any(entry[1] for entry in self.stack):
            self.primary.append(value)
        if any(entry[2] for entry in self.stack):
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


def _node_identity(node):
    identity=node.get('url') or node.get('mainEntityOfPage')
    return identity.get('@id') if isinstance(identity,dict) else identity


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
        identity = _node_identity(node)
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
    labelled = re.search(r"\bPublicad[oa]\s*(?::|el)\s*(.{1,100})", " ".join(p.publication_label or p.visible), re.I)
    if labelled:
        from .public_source_pipeline import _date
        # Select the first date next to the label, not an ISO incident/modification
        # date later in the paragraph (the generic _date prefers any ISO token).
        token=re.search(r"20\d{2}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]20\d{2}|\d{1,2}\s+de\s+\w+\s+de\s+20\d{2}",labelled[1],re.I)
        visible_day = _date(token[0]) if token else None
        if visible_day and _day(visible_day):
            candidates.append({"source": "visible:published_label", "value": labelled[1], "day": visible_day})
    # An explicitly marked publication time is a fallback; bare clocks and
    # incident dates are not publication evidence even if there is only one.
    if not candidates and len(p.times) == 1:
        candidates.append({"source": "time:datePublished", "value": p.times[0], "day": _day(p.times[0])})
    valid = [c for c in candidates if c["day"]]
    conflict = len({c["day"] for c in valid}) > 1
    chosen = valid[0] if valid and not conflict else None
    resolution=None
    identity_verified=any(article_url(str(_node_identity(node) or ''))==article_url(url) for node in selected)
    if conflict and p.publication_label and (p.primary_found or p.media) and identity_verified:
        chosen=next((c for c in valid if c['source']=='visible:published_label'),None)
        if chosen:
            resolution={'rule':'primary_header_explicit_publication_label','selected_visible_day':chosen['day'],
                        'basis':'DF enc-main header / author__date explicitly labels publication; matching NewsArticle URL and primary body or embedded media container verified. Metadata timestamps retained; discrepancy cause unknown.'}
    if conflict:
        decisions=json.loads((Path(__file__).resolve().parents[2]/"config/df_date_provenance.json").read_text())["decisions"]
        rule=decisions.get(article_url(url))
        if not resolution and rule and all(any(c["source"]==source and c["value"]==rule[field] for c in valid)
                        for source,field in (("cxenseparse:recs:publishtime","expected_cx_timestamp"),
                                             ("jsonld:datePublished","expected_jsonld_timestamp"))):
            chosen=next((c for c in valid if c["source"]=="visible:published_label" and c["day"]==rule["selected_visible_day"]),None)
            if chosen:resolution=rule
    node = selected[0] if selected else {}
    # DF's primary content is #articleLock/#articleFree.CUERPO. Recommendation
    # cards also use <article>; never combine them with the story or fall back
    # to every paragraph on the page (newsletter/paywall pages have those too).
    body = node.get("articleBody") or " ".join(p.primary) or " ".join(p.article)
    description = p.meta.get("og:description") or p.meta.get("description") or node.get("description") or ""
    return {
        "event_date": chosen["day"] if chosen else None,
        "raw_text": description or body[:1800],
        "metadata": {
            "page_text": body,
            "article_title": node.get("headline") or p.meta.get("og:title") or "",
            "article_section": node.get("articleSection") or p.meta.get("article:section") or "",
            "primary_image_urls":[urljoin(url,src) for src in p.images],
            "primary_media_urls":[urljoin(url,src) for src in p.media],
            "publication_date_source": chosen["source"] if chosen else None,
            "publication_timestamp": chosen["value"] if chosen and chosen["source"] != "visible:published_label" else None,
            "publication_label": chosen["value"] if chosen and chosen["source"] == "visible:published_label" else None,
            "publication_date_candidates": candidates,
            "publication_date_conflict": conflict,
            "publication_date_conflict_resolution": resolution,
            "article_content_source": "jsonld:articleBody" if node.get("articleBody") else "df_primary_body" if p.primary else "semantic_article" if p.article else "df_primary_images" if p.images else "df_embedded_media_without_transcript" if p.media else "missing_primary_article",
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
