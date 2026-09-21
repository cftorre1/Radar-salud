from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import urljoin

from .models import RawItem
from .quality import clean_technical_text


DATE_RE = re.compile(r"Fecha de publicación:\s*(\d{1,2}\s+de\s+[A-Za-zÁÉÍÓÚáéíóúñÑ]+\s+de\s+\d{4})", re.I)
UPDATED_RE = re.compile(r"Información actualizada a\s+([^\.]+)\.", re.I)
NUMBER_RE = re.compile(r"(?<!\w)(?:\$\s*)?\d[\d\.\,]*(?:\s*(?:%|MM|mil|millones?|UF|UTM|MB|GB))?", re.I)

MONTHS = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
}


class _DetailParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts: List[str] = []
        self.text_parts: List[str] = []
        self.links: List[tuple[str, str]] = []
        self._tag_stack: List[str] = []
        self._href: Optional[str] = None
        self._anchor_text: List[str] = []
        self._capture_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        self._tag_stack.append(tag)
        if tag == "h1":
            self._capture_title = True
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._anchor_text = []

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text:
            return
        self.text_parts.append(text)
        if self._capture_title:
            self.title_parts.append(text)
        if self._href is not None:
            self._anchor_text.append(text)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "h1":
            self._capture_title = False
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._anchor_text)))
            self._href = None
            self._anchor_text = []
        if self._tag_stack:
            self._tag_stack.pop()


def _parse_spanish_date(text: str) -> Optional[str]:
    m = re.search(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(\d{4})", text, re.I)
    if not m:
        return None
    day, month_name, year = m.groups()
    month = MONTHS.get(month_name.lower())
    if not month:
        return None
    return f"{year}-{month}-{int(day):02d}"


def extract_superintendencia_detail(raw: RawItem, html: str) -> RawItem:
    """Enrich a discovered publication using its detail page.

    This deliberately extracts only facts visible on the official page. It does
    not infer implications; that belongs to the Analyst stage.
    """
    parser = _DetailParser()
    parser.feed(html)
    all_text = " ".join(parser.text_parts)

    title = " ".join(parser.title_parts).strip() or raw.title
    date_match = DATE_RE.search(all_text)
    event_date = _parse_spanish_date(date_match.group(1)) if date_match else raw.event_date
    updated = UPDATED_RE.search(all_text)

    # Keep likely downloadable evidence links.
    attachments: List[Dict[str, str]] = []
    for href, text in parser.links:
        label = " ".join(text.split())
        lower = f"{href} {label}".lower()
        if any(ext in lower for ext in (".xlsx", ".xls", ".csv", ".pdf", "descargar")):
            attachments.append({"url": urljoin(raw.url, href), "label": label})

    # Superintendencia detail pages place the useful description close to the
    # title. Strip obvious chrome phrases and preserve a bounded evidence text.
    chrome = {
        "inicio", "trámites y servicios", "orientación en salud", "publicaciones y estadísticas",
        "regulación y fiscalización", "contáctanos", "acerca de la superintendencia",
    }
    meaningful = [p for p in parser.text_parts if p.lower() not in chrome]
    evidence_text = " ".join(meaningful)

    # Description: sentence beginning with 'Contiene' when present; otherwise
    # use a bounded text excerpt.
    desc_match = re.search(r"(Contiene\s+.+?)(?=Información actualizada|Fecha de publicación|Descargar|$)", evidence_text, re.I)
    description = " ".join(desc_match.group(1).split()) if desc_match else evidence_text[:1500]
    description = clean_technical_text(description)

    numbers = []
    for match in NUMBER_RE.findall(description):
        value = " ".join(match.split())
        if value not in numbers:
            numbers.append(value)

    metadata = dict(raw.metadata)
    metadata.update({
        "description": description,
        "updated_through": updated.group(1).strip() if updated else None,
        "attachments": attachments,
        "extracted_numbers": numbers[:20],
        "evidence_text": evidence_text[:8000],
    })

    return RawItem(
        source_slug=raw.source_slug,
        title=title,
        url=raw.url,
        source_name=raw.source_name,
        source_type=raw.source_type,
        event_date=event_date,
        raw_text=description,
        metadata=metadata,
    )
