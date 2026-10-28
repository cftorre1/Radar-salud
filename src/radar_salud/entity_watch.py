"""WATCH: deterministic entity tagging for feed signals (Dirección 27-oct-2026).

Rules live in config/entities.json. Matching is explicit names only: no model,
no inference from ownership (Bupa does not imply Isapre Cruz Blanca) and no bare
commune or adjective ("Las Condes", "esencial", "Santa María").
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from .paths import project_root

CONFIG = 'config/entities.json'
TEXT_FIELDS = ('title', 'display_title', 'what_happened', 'card_what', 'official_subject', 'regulated_entity')


def fold(text):
    """Strip accents and collapse spaces, keeping case (MEDS, ISP, CLC are case-sensitive)."""
    text = ''.join(c for c in unicodedata.normalize('NFKD', str(text or '')) if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', text).strip()


class Entity:
    def __init__(self, raw):
        self.id = raw['id']
        self.name = raw['display_name']
        self.short = raw.get('short_name') or raw['display_name']
        self.aliases = list(raw.get('aliases', []))
        self.kind = raw['kind']
        self.source_names = {fold(x).casefold() for x in raw.get('source_names', [])}
        self.exclude = [re.compile(x, re.I) for x in raw.get('exclude', [])]
        self.patterns = [(re.compile(p['re'], re.I if p.get('ci', True) else 0),
                          re.compile(p['context'], re.I) if p.get('context') else None)
                         for p in raw['patterns']]

    def matches(self, folded):
        for rx in self.exclude:
            folded = rx.sub(' ', folded)
        return any(rx.search(folded) and (ctx is None or ctx.search(folded)) for rx, ctx in self.patterns)


def load_catalog(path=None):
    return _load(str(Path(path) if path else project_root() / CONFIG))


@lru_cache(maxsize=4)
def _load(path):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    ids = [e['id'] for e in raw['entities']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate entity id in entities.json')
    return tuple(Entity(e) for e in raw['entities'])


def match_text(text, catalog=None):
    """Entity ids explicitly named in text, in catalog order."""
    folded = fold(text)
    return [e.id for e in (catalog or load_catalog()) if folded and e.matches(folded)]


# Diario Oficial listing captures prepend the previous act of the listing: "<previous act>
# Ver PDF (CVE-n) [<issuer header>] <this act>". This record is the last segment; when that
# segment has no issuer header of its own it inherits the header that opens the capture.
_MARKER = re.compile(r'\s*Ver PDF \(CVE-\d+\)\s*')
_ACT = re.compile(r'(Extracto de |Resoluci[oó]n|Decreto|Ley |Circular|Oficio|Norma )', re.I)


def _own(value):
    text = re.sub(r'<a\b.*$', '', str(value or ''), flags=re.S)
    parts = _MARKER.split(text)
    if len(parts) == 1:
        return text
    last = parts[-1]
    if _ACT.match(last):
        head = _ACT.search(parts[0])
        if head and 0 < head.start() <= 120:
            last = parts[0][:head.start()] + last
    return last


def signal_text(signal, fields=TEXT_FIELDS):
    return ' | '.join(_own(signal.get(k)) for k in fields)


def _source_ids(signal, catalog):
    name = fold(signal.get('source_name')).casefold()
    return [e.id for e in catalog if name and name in e.source_names]


def direct_ids(signal, catalog=None):
    catalog = catalog or load_catalog()
    found = match_text(signal_text(signal), catalog)
    return found, [x for x in _source_ids(signal, catalog) if x not in found]


def _ref(entity, basis):
    return {'canonical_id': entity.id, 'name': entity.name, 'kind': entity.kind, 'basis': basis}


def entity_refs(signal, *, members_by_url=None, catalog=None):
    """Refs for one card: its own text and source first, then acts aggregated in it.

    'member' refs come from source_alternatives (pulses, story syntheses, corroborating
    pieces): their titles/materials and, by URL, the tagged history record of each act.
    """
    catalog = catalog or load_catalog()
    by_id = {e.id: e for e in catalog}
    text, source = direct_ids(signal, catalog)
    member = []
    for alt in signal.get('source_alternatives') or []:
        if not isinstance(alt, dict):
            continue
        ids = match_text(' | '.join(str(alt.get(k) or '') for k in ('title', 'material')), catalog)
        ids += (members_by_url or {}).get(alt.get('url') or '', [])
        member += [x for x in ids if x not in member]
    out, seen = [], set()
    for basis, ids in (('text', text), ('source', source), ('member', member)):
        for x in ids:
            if x not in seen:
                seen.add(x); out.append(_ref(by_id[x], basis))
    # Keep pipeline refs (e.g. official Isapre codes) that this catalog did not reach.
    for old in signal.get('entity_refs') or []:
        cid = old.get('canonical_id') if isinstance(old, dict) else None
        if cid and cid not in seen:
            seen.add(cid)
            entity = by_id.get(cid)
            out.append(_ref(entity, 'pipeline') if entity else dict(old, basis='pipeline'))
    return out


def members_index(signals, catalog=None):
    """URL -> entity ids for history records, so an aggregate inherits the acts it lists."""
    catalog = catalog or load_catalog(); index = {}
    for s in signals:
        url = s.get('source_url')
        if not url:
            continue
        text, source = direct_ids(s, catalog)
        ids = index.setdefault(url, [])
        ids += [x for x in text + source if x not in ids]
    return index


def apply(cards, history=(), catalog=None):
    catalog = catalog or load_catalog()
    index = members_index(history, catalog)
    for card in cards:
        card['entity_refs'] = entity_refs(card, members_by_url=index, catalog=catalog)
    return cards


def public_catalog(catalog=None):
    """Compact list for the web 'Entidades' picker (names and aliases for search)."""
    return [{'id': e.id, 'name': e.name, 'short': e.short, 'kind': e.kind,
             'aliases': [a for a in e.aliases if a != e.name]} for e in (catalog or load_catalog())]
