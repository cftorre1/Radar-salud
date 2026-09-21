from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from .analysis import AnalysisResult
from .models import RawItem, Signal
from .pipeline import build_signal
from .validation import validate_official_item


DATE_PATTERNS = [
    re.compile(r"(?:Fecha de publicación|Publicado|Publicación)[:\s]+(\d{1,2}\s+de\s+[A-Za-zÁÉÍÓÚáéíóúñÑ]+\s+de\s+\d{4})", re.I),
    re.compile(r"\[(\d{4})\s*/\s*([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\]", re.I),
]
MONTHS = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04", "mayo": "05", "junio": "06",
    "julio": "07", "agosto": "08", "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
}
NUMBER_RE = re.compile(r"(?<!\w)(?:\$\s*)?\d[\d\.\,]*(?:\s*(?:%|MM|mil|millones?|UF|UTM|trabajadores?|empresas?|días?))?", re.I)


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text: List[str] = []
        self.title: List[str] = []
        self.links: List[tuple[str, str]] = []
        self._in_h1 = False
        self._href: Optional[str] = None
        self._anchor: List[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "h1":
            self._in_h1 = True
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._anchor = []

    def handle_data(self, data):
        s = " ".join(data.split())
        if not s:
            return
        self.text.append(s)
        if self._in_h1:
            self.title.append(s)
        if self._href is not None:
            self._anchor.append(s)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "h1":
            self._in_h1 = False
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._anchor)))
            self._href = None
            self._anchor = []


def _date_from_text(text: str) -> Optional[str]:
    m = DATE_PATTERNS[0].search(text)
    if m:
        d = re.search(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(\d{4})", m.group(1), re.I)
        if d and d.group(2).lower() in MONTHS:
            return f"{d.group(3)}-{MONTHS[d.group(2).lower()]}-{int(d.group(1)):02d}"
    m = DATE_PATTERNS[1].search(text)
    if m and m.group(2).lower() in MONTHS:
        return f"{m.group(1)}-{MONTHS[m.group(2).lower()]}-01"
    return None


def extract_suseso_detail(raw: RawItem, html: str) -> RawItem:
    parser = _PageParser()
    parser.feed(html)
    all_text = " ".join(parser.text)
    title = " ".join(parser.title).strip() or raw.title
    event_date = _date_from_text(all_text) or raw.event_date

    attachments: List[Dict[str, str]] = []
    for href, label in parser.links:
        low = f"{href} {label}".lower()
        if any(ext in low for ext in (".pdf", ".xlsx", ".xls", ".csv", "archivo_", "descargar")):
            attachments.append({"url": urljoin(raw.url, href), "label": " ".join(label.split())})

    # Keep a bounded evidence block while removing obvious nav noise.
    noise = {"inicio", "fiscalización", "estadísticas", "publicaciones", "contacto", "transparencia"}
    meaningful = [x for x in parser.text if x.lower() not in noise]
    evidence = " ".join(meaningful)
    description = evidence[:2500]

    numbers: List[str] = []
    for match in NUMBER_RE.findall(description):
        value = " ".join(match.split())
        if value and value not in numbers:
            numbers.append(value)

    metadata = dict(raw.metadata)
    metadata.update({
        "description": description,
        "attachments": attachments,
        "extracted_numbers": numbers[:25],
        "evidence_text": evidence[:10000],
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


def analyze_suseso(raw: RawItem) -> AnalysisResult:
    text = f"{raw.title} {raw.raw_text}".lower()
    tags = ["suseso"]
    who = ["estrategia", "estudios", "mutualidades"]
    economic, regulatory, scope, novelty, actionability = 45, 55, 65, 70, 60
    subcategory = "Estadísticas"
    why = "Aporta información oficial para monitorear seguridad social, salud laboral y desempeño del sistema de la Ley 16.744."

    if "circular" in text or "instru" in text or "norma" in text:
        tags += ["regulación", "circular"]
        regulatory, scope, actionability = 90, 80, 85
        subcategory = "Regulación"
        why = "Puede cambiar obligaciones, procesos o criterios aplicables a mutualidades, empleadores u otros organismos del sistema."
    if "accident" in text:
        tags += ["accidentabilidad", "ley 16.744"]
        who += ["prevención", "empleadores"]
        scope, actionability = max(scope, 75), max(actionability, 70)
        subcategory = "Accidentabilidad"
    if "enfermedad profesional" in text or "enfermedades profesionales" in text:
        tags += ["enfermedades profesionales", "ley 16.744"]
        who += ["salud ocupacional", "empleadores"]
        scope, actionability = max(scope, 75), max(actionability, 70)
        subcategory = "Enfermedades profesionales"
    if "mutual" in text:
        tags += ["mutualidades"]
        who += ["achs", "mutual de seguridad", "ist", "isl"]
    if "licencia" in text or "subsidio" in text:
        tags += ["licencias médicas", "subsidios"]
        who += ["rrhh", "compin"]
        regulatory = max(regulatory, 70)
        subcategory = "Licencias y subsidios"

    description = raw.metadata.get("description") or raw.raw_text
    key_facts = [description[:500]] if description else []
    key_numbers = [{"raw": x} for x in raw.metadata.get("extracted_numbers", [])[:12]]
    return AnalysisResult(
        what_happened=(description[:600] if description else raw.title),
        key_facts=key_facts,
        key_numbers=key_numbers,
        why_it_matters=why,
        who_cares=list(dict.fromkeys(who)),
        watch_tags=list(dict.fromkeys(tags)),
        scores={
            "economic": economic,
            "regulatory": regulatory,
            "scope": scope,
            "novelty": novelty,
            "actionability": actionability,
        },
        subcategory=subcategory,
    )


def process_suseso_detail(raw: RawItem, html: str, source_cfg: Dict[str, Any]) -> Signal:
    enriched = extract_suseso_detail(raw, html)
    validation = validate_official_item(enriched, source_cfg.get("base_confidence", 100))
    analysis = analyze_suseso(enriched)
    enriched.metadata.update({
        "what_happened": analysis.what_happened,
        "key_facts": analysis.key_facts,
        "key_numbers": analysis.key_numbers,
        "why_it_matters": analysis.why_it_matters,
        "who_cares": analysis.who_cares,
        "watch_tags": analysis.watch_tags,
        "scores": analysis.scores,
        "subcategory": analysis.subcategory,
        "confidence_adjustment": validation.confidence_score - source_cfg.get("base_confidence", 100),
    })
    signal = build_signal(enriched, source_cfg)
    signal.confidence_score = validation.confidence_score
    signal.validation_status = validation.status
    return signal
