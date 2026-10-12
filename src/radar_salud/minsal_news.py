"""MINSAL news: primary Elementor body and article-bound publication stamps."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from .models import RawItem
from .processing import DeferredProcessing


def official(url):
    p = urlsplit(url)
    return p.scheme == 'https' and p.netloc == 'www.minsal.cl' and not p.username and not p.password


class Article(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.title, self.body, self.dates = [], [], []
        self.canonical = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'link' and a.get('rel') == 'canonical':
            self.canonical = a.get('href')
        if tag == 'meta' and (a.get('property') or a.get('name')) == 'article:published_time':
            self.dates.append(a.get('content', ''))
        if tag not in ('meta', 'link', 'img', 'br', 'hr', 'input', 'source', 'wbr'):
            primary = bool(re.search(r'\b(elementor-widget-theme-post-content|entry-content)\b', a.get('class', '')))
            self.stack.append((tag, primary))

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        tags = {t for t, _ in self.stack}
        if tags & {'script', 'style', 'nav', 'footer', 'aside', 'noscript'}:
            return
        text = ' '.join(data.split())
        if 'h1' in tags and text:
            self.title.append(text)
        if any(primary for _, primary in self.stack) and text:
            self.body.append(text)


def bind_minsal(raw, html, *, now=None):
    if not official(raw.url):
        raise DeferredProcessing('minsal_nonofficial_detail')
    p = Article(); p.feed(html)
    if not p.canonical or p.canonical.rstrip('/') != raw.url.rstrip('/'):
        raise DeferredProcessing('minsal_primary_identity_missing_or_conflicting')
    title, body = ' '.join(p.title), ' '.join(p.body)
    if not title or len(body) < 180:
        raise DeferredProcessing('minsal_primary_body_missing')
    stamps = []
    for value in p.dates:
        try:
            stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                raise ValueError('Unzoned stamp')
            stamps.append((value, stamp))
        except ValueError:
            raise DeferredProcessing('minsal_publication_stamp_invalid')
    now = now or datetime.now(timezone.utc)
    if not stamps or len({s[1] for s in stamps}) != 1 or stamps[0][1] > now:
        raise DeferredProcessing('minsal_publication_stamp_missing_conflicting_or_future')
    value, stamp = stamps[0]
    if raw.metadata.get('rss_published_at') and datetime.fromisoformat(raw.metadata['rss_published_at']) != stamp:
        raise DeferredProcessing('minsal_rss_detail_publication_conflict')
    raw.title = title
    raw.event_date = stamp.astimezone(ZoneInfo('America/Santiago')).date().isoformat()
    raw.raw_text = body[:3000]
    raw.metadata.update(page_text=body, primary_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
                        primary_html_sha256=hashlib.sha256(html.encode()).hexdigest(),
                        publication_date_source='article:published_time',
                        publication_date_evidence=dict(kind='article:published_time', value=value,
                                                       date=raw.event_date, url=raw.url),
                        publication_timestamp=stamp.isoformat(), minsal_primary_verified=True)
    return raw


def rss_candidates(xml, *, now=None, days=30):
    if not 1 <= days <= 30:
        raise ValueError('Daily First window must be 1..30 days')
    now = now or datetime.now(timezone.utc)
    root = ET.fromstring(xml)
    if root.tag != 'rss' or root.findtext('./channel/link', '').rstrip('/') not in (
            'https://www.minsal.cl', 'https://www.minsal.cl/category/noticias'):
        raise ValueError('Not the official MINSAL RSS channel')
    rows = []
    for node in root.findall('./channel/item')[:30]:
        url, title = node.findtext('link', ''), node.findtext('title', '')
        if not official(url) or not title:
            continue
        try:
            stamp = parsedate_to_datetime(node.findtext('pubDate', ''))
            if stamp.tzinfo is None or not now-timedelta(days=days) <= stamp <= now:
                continue
        except (ValueError, TypeError):
            continue
        rows.append(RawItem('minsal', title, url, 'Ministerio de Salud', 'official',
                    event_date=stamp.astimezone(ZoneInfo('America/Santiago')).date().isoformat(),
                    metadata={'discovered_from': 'https://www.minsal.cl/category/noticias/feed/',
                              'rss_published_at': stamp.isoformat()}))
    return sorted({r.url: r for r in rows}.values(), key=lambda r: r.metadata['rss_published_at'], reverse=True)
