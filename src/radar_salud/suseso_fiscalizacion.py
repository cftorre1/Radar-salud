"""SUSESO actor taxonomy is a discovery surface, not an enforcement finding."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit
from .models import RawItem
from .regulatory import _TableParser
from .scouts import fetch_html
from .superintendencia_fiscalizacion import canonical_url, _valid_date

PAGES = [
    ('Isapres', 'https://www.suseso.gob.cl/612/w3-propertyvalue-30981.html'),
    ('COMPIN', 'https://www.suseso.gob.cl/612/w3-propertyvalue-30982.html'),
]


def parse_actor_listing(html, actor, page):
    parser = _TableParser()
    parser.feed(html)
    items = {}
    for row in parser.rows:
        if len(row) < 2:
            continue
        publication_date = _valid_date(row[0].get('text', ''))
        for href, title in row[1].get('links', []):
            url = canonical_url(urljoin(page, href))
            parsed = urlsplit(url)
            if parsed.netloc not in ('www.suseso.gob.cl', 'suseso.gob.cl'):
                continue
            if not re.fullmatch(r'/612/w3-article-\d+\.html', parsed.path):
                continue
            if not re.match(r'(Circular|Dictamen|Informe|Resoluci[oó]n)\b', title, re.I):
                continue
            doc_kind = 'related_normative' if re.match(r'(Circular|Dictamen)\b', title, re.I) else 'enforcement_candidate'
            items.setdefault(url, RawItem('suseso_fiscalizacion', title, url,
                'Superintendencia de Seguridad Social (SUSESO)', 'official',
                event_date=publication_date,
                raw_text=' '.join(cell.get('text', '') for cell in row[2:4]),
                metadata={
                    'discovered_from': page, 'listing_urls': [page],
                    'fiscalized_actors': [actor], 'fiscalized_actor': actor,
                    'actor_evidence': 'related_actor_taxonomy', 'document_class': doc_kind,
                    'publication_date': publication_date, 'event_date_basis': 'publication' if publication_date else None,
                    'suggested_source': 'suseso' if doc_kind == 'related_normative' else None,
                }))
    return list(items.values())


class SusesoFiscalizacionScout:
    SOURCE_SLUG = 'suseso_fiscalizacion'
    SOURCE_NAME = 'Superintendencia de Seguridad Social (SUSESO)'
    SOURCE_TYPE = 'official'
    PAGES = PAGES

    def discover(self):
        items = {}
        self.surface_results = []
        for actor, page in self.PAGES:
            try:
                found = parse_actor_listing(fetch_html(page), actor, page)
                if not found:
                    raise ValueError('Actor surface has no identifiable document rows')
                self.surface_results.append({'url': page, 'status': 'parsed', 'documents': len(found),
                    'undated': sum(raw.event_date is None for raw in found)})
                for raw in found:
                    if raw.url not in items:
                        items[raw.url] = raw
                    else:
                        meta = items[raw.url].metadata
                        meta['fiscalized_actors'] = sorted(set(meta['fiscalized_actors'] + [actor]))
                        meta['fiscalized_actor'] = ' / '.join(meta['fiscalized_actors'])
                        meta['listing_urls'] = sorted(set(meta['listing_urls'] + [page]))
                        if raw.event_date != items[raw.url].event_date:
                            meta['date_conflicts'] = ['listing_dates_disagree']
            except Exception as exc:
                self.surface_results.append({'url': page, 'status': 'error', 'error': type(exc).__name__})
        if not items:
            raise RuntimeError('No SUSESO actor surface parsed successfully')
        # No arbitrary top-40 cap: all dated rows remain auditable, before queue horizon filtering.
        return sorted(items.values(), key=lambda raw: raw.event_date or '', reverse=True)


def reviewed_normative_candidate(raw):
    """Route a document only when an explicit source/date review exists."""
    import json
    from dataclasses import replace
    from .paths import project_root
    path = project_root() / 'config/fiscalization_editorial_reviews.json'
    reviews = json.loads(path.read_text()) if path.exists() else {}
    review = reviews.get('source_records', {}).get(raw.url)
    if not review or review.get('decision') != 'publish_normative':
        return None
    if raw.event_date != review.get('event_date') or review['legal_identity'] != raw.title:
        return None
    return replace(raw, source_slug='suseso', metadata={**raw.metadata,
        'reviewed_normative': review, 'routed_from': 'suseso_fiscalizacion'})


def process_reviewed_normative(raw, cfg):
    from .pipeline import build_signal
    from .processing import RejectedProcessing
    review = raw.metadata['reviewed_normative']
    if raw.url != review['source_url'] or raw.event_date != review['event_date']:
        raise RejectedProcessing('reviewed_normative_identity_or_date_mismatch')
    raw.metadata.update(what_happened=review['what_happened'], why_it_matters=review['why_it_matters'],
        event_type='REGULATION', key_points=review['key_points'], validity_text=review['validity_text'],
        watch_tags=['suseso','licencias médicas','isapres','compin'],
        scores={'economic':65,'regulatory':90,'scope':85,'novelty':80,'actionability':90})
    row = build_signal(raw, cfg).to_dict()
    row.update(signal_types=['Normativa'], scopes=['Isapres','COMPIN','Salud laboral'],
        fiscalized_actors=raw.metadata.get('fiscalized_actors', ['Isapres','COMPIN']),
        normative_document_label=review['legal_identity'], legal_identity=review['legal_identity'],
        normative_document_number=review['legal_identity'], normative_context=review['normative_context'],
        display_title=review['plain_language_title'], editorial_review=review['review_basis'],
        publication_date=review['event_date'], source_documents=[{'url':raw.url,'label':'Ficha oficial SUSESO'}])
    return row
