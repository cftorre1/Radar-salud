from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Dict, List
from urllib.parse import urljoin

from .models import RawItem, Signal
from .pipeline import build_signal


HEALTH_HINTS = (
    'salud','isapre','clínica','clinica','hospital','fonasa','médic','medic','prestador',
    'farmac','laboratorio','biotech','healthtech','oncolog','seguro','asegurador','ges','caec',
)


class _ListingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: List[tuple[str, str]] = []
        self._href = None
        self._text: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            self._href = dict(attrs).get('href')
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            s = ' '.join(data.split())
            if s:
                self._text.append(s)

    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self._href is not None:
            label = ' '.join(self._text).strip()
            if label:
                self.links.append((self._href, label))
            self._href = None
            self._text = []


def _is_health(text: str) -> bool:
    low = text.casefold()
    return any(term in low for term in HEALTH_HINTS)


def parse_df_listing(html: str, base_url: str = 'https://www.df.cl') -> List[RawItem]:
    """Parse candidate health/business stories from a DF listing page.

    V0 intentionally uses visible link labels only. Article body extraction can be
    added later; this keeps the scout resilient and avoids depending on paywalled body text.
    """
    p = _ListingParser(); p.feed(html)
    out: List[RawItem] = []
    seen = set()
    for href, label in p.links:
        if not href or not _is_health(label):
            continue
        url = urljoin(base_url, href)
        key = (url, label)
        if key in seen:
            continue
        seen.add(key)
        out.append(RawItem(
            source_slug='diario_financiero',
            title=label,
            url=url,
            source_name='Diario Financiero',
            source_type='press_high_trust',
            raw_text=label,
            metadata={
                'what_happened': label,
                'why_it_matters': 'Movimiento empresarial o sectorial relevante para el mercado de salud chileno.',
                'who_cares': ['estrategia', 'desarrollo de negocios', 'inteligencia competitiva'],
                'watch_tags': ['diario financiero', 'mercado salud'],
                'scores': {'economic': 70, 'regulatory': 35, 'scope': 65, 'novelty': 75, 'actionability': 65},
                'subcategory': 'Prensa sectorial',
                'corroboration_status': 'not_required',
            },
        ))
    return out


def process_df_item(raw: RawItem, source_cfg: Dict[str, Any]) -> Signal:
    signal = build_signal(raw, source_cfg)
    # High-trust press does not require a second source to remain high-confidence.
    signal.confidence_score = max(signal.confidence_score, int(source_cfg.get('base_confidence', 93)))
    signal.validation_status = 'high_trust_press'
    signal.corroboration_status = raw.metadata.get('corroboration_status', 'not_required')
    return signal


def raw_reuters_item(title: str, url: str, summary: str = '', event_date: str | None = None) -> RawItem:
    return RawItem(
        source_slug='reuters',
        title=title,
        url=url,
        source_name='Reuters',
        source_type='press_high_trust',
        event_date=event_date,
        raw_text=summary or title,
        metadata={
            'what_happened': summary or title,
            'why_it_matters': 'Señal internacional que puede anticipar tendencias relevantes para salud, tecnología, regulación o modelos de atención.',
            'who_cares': ['estrategia', 'innovación', 'inteligencia competitiva'],
            'watch_tags': ['radar mundo', 'reuters'],
            'scores': {'economic': 60, 'regulatory': 45, 'scope': 65, 'novelty': 80, 'actionability': 50},
            'subcategory': 'Radar Mundo',
            'corroboration_status': 'not_required',
            'language': 'en',
            'translation_status': 'pending',
        },
    )


def process_reuters_item(raw: RawItem, source_cfg: Dict[str, Any]) -> Signal:
    signal = build_signal(raw, source_cfg)
    signal.category = 'Radar Mundo'
    signal.system_domain = 'GLOBAL_HEALTH'
    signal.confidence_score = max(signal.confidence_score, int(source_cfg.get('base_confidence', 96)))
    signal.validation_status = 'high_trust_press'
    signal.corroboration_status = raw.metadata.get('corroboration_status', 'not_required')
    signal.original_language = raw.metadata.get('language', 'en')
    signal.original_title = signal.title
    signal.original_what_happened = signal.what_happened
    signal.original_why_it_matters = signal.why_it_matters
    if signal.original_language != 'es':
        signal.display_language = 'es'
        signal.translation_status = raw.metadata.get('translation_status', 'pending')
    return signal
