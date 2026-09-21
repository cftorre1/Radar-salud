from __future__ import annotations

import re
from typing import Iterable

TECHNICAL_GARBAGE_PATTERNS = (
    r'@context', r'@graph', r'schema\.org', r'"@type"', r'"isPartOf"',
    r'<script', r'application/ld\+json', r'__next_data__',
)


def has_technical_garbage(text: str | None) -> bool:
    if not text:
        return False
    sample = text.lower()
    hits = sum(bool(re.search(p, sample, re.I)) for p in TECHNICAL_GARBAGE_PATTERNS)
    brace_density = (sample.count('{') + sample.count('}')) / max(len(sample), 1)
    return hits >= 1 or brace_density > 0.01


def clean_technical_text(text: str | None) -> str:
    """Strip common JSON-LD / page-chrome contamination from extracted prose."""
    if not text:
        return ''
    value = ' '.join(str(text).split())
    # Anything after an obvious JSON-LD payload is page chrome, not editorial content.
    markers = ['{"@context"', "{'@context'", '@context', 'schema.org']
    positions = [value.lower().find(m.lower()) for m in markers if value.lower().find(m.lower()) >= 0]
    if positions:
        value = value[:min(positions)].strip(' -–—:{[,')
    # Remove isolated script-ish fragments if any survived.
    value = re.sub(r'\s*application/ld\+json.*$', '', value, flags=re.I)
    return value.strip()


def publication_ready(texts: Iterable[str | None]) -> bool:
    return not any(has_technical_garbage(t) for t in texts if t)
