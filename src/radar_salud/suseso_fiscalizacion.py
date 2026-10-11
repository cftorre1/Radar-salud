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
ENFORCEMENT_PAGES = [
    ('Sanciones a emisores de licencias médicas', 'https://www.suseso.gob.cl/609/w3-propertyvalue-799701.html', 'professionals'),
    ('Sanciones a entidades', 'https://www.suseso.gob.cl/609/w3-propertyvalue-806511.html', 'entities'),
    ('Informes Seguridad y Salud en el Trabajo', 'https://www.suseso.gob.cl/609/w3-propertyvalue-559471.html', 'reports'),
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
            if not re.match(r'(Circular|Dictamen|Ley|Informe|Resoluci[oó]n)\b', title, re.I):
                continue
            doc_kind = 'related_normative' if re.match(r'(Circular|Dictamen|Ley)\b', title, re.I) else 'enforcement_candidate'
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


def parse_enforcement_listing(html, name, page, kind):
    """Parse the original /609 registers, without guessing missing daily dates."""
    parser = _TableParser(); parser.feed(html)
    out = []
    for row in parser.rows:
        cells = [cell.get('text', '').strip() for cell in row]
        if kind == 'professionals':
            if len(cells) != 10 or not re.fullmatch(r'O-\d{2}-[A-Z]+-\d+-20\d{2}', cells[4]):
                continue
            identity = cells[4]
            entity = ' '.join(cells[2:4])
            emitted, start, end = (_valid_date(cells[index]) for index in (5, 8, 9))
            try:
                amount, days = float(cells[6]), int(cells[7])
            except ValueError:
                amount = days = None
            conflicts = [] if emitted and start and end and start <= end and amount is not None and days is not None else ['incomplete_or_inconsistent_register_row']
            metadata = dict(source_record_id=identity, legal_identity='Oficio ' + identity,
                document_class='enforcement_sanction', fiscalization_kind='sanction',
                fiscalized_actors=['Profesionales emisores de licencias médicas'],
                regulated_entity=entity, actor_evidence='official_sanction_register',
                sanction_amount=amount, sanction_unit='UTM', suspension_days=days,
                suspension_start=start, suspension_end=end, emission_date=emitted,
                publication_date=None, fact_date=None, modification_date=None,
                event_date_basis='emission', date_conflicts=conflicts,
                listing_url=page, listing_name=name, scopes=['Prestadores','COMPIN','Isapres'],
                affected_actors=['COMPIN','Isapres'],
                validity_text=f'Suspensión de emisión de licencias: {start} a {end}, ambas fechas inclusive. El registro no acredita fecha de publicación ni notificación.')
            text = f'SUSESO registra para {entity} una multa de {amount:g} UTM y suspensión de emisión de licencias por {days} días, del {start} al {end}.' if amount is not None and days is not None else 'Registro de sanción con campos incompletos.'
            out.append(RawItem('suseso_fiscalizacion','Oficio ' + identity + ' · sanción a emisor de licencias',page,
                'Superintendencia de Seguridad Social (SUSESO)','official',emitted,text,metadata))
        elif kind == 'entities':
            if len(cells) < 12 or not _valid_date(cells[1]):
                continue
            detail = next((urljoin(page, href) for href, _ in row[11].get('links', []) if 'w3-article-' in href), None)
            if not detail:
                continue
            attachments = [{'url':urljoin(page,href),'label':label} for cell in (row[3],row[9]) for href,label in cell.get('links',[]) if '.pdf' in href]
            out.append(RawItem('suseso_fiscalizacion',cells[3] + ' · ' + cells[2],canonical_url(detail),
                'Superintendencia de Seguridad Social (SUSESO)','official',_valid_date(cells[1]),cells[5],
                dict(document_class='enforcement_entity',regulated_entity=cells[2],sanction_text=cells[4],
                    notification_date=_valid_date(cells[1]),publication_date=None,emission_date=None,
                    modification_date=_valid_date(cells[10]),event_date_basis='notification',
                    validity_text=cells[6],listing_url=page,listing_name=name,attachments=attachments)))
        elif kind == 'reports':
            if len(cells) < 5 or not re.search(r'20\d{2}', cells[0]):
                continue
            detail = next((urljoin(page, href) for href, _ in row[1].get('links', []) if 'w3-article-' in href), None)
            if not detail:
                continue
            out.append(RawItem('suseso_fiscalizacion',cells[1],canonical_url(detail),
                'Superintendencia de Seguridad Social (SUSESO)','official',None,cells[2],
                dict(document_class='historical_enforcement_report',execution_period=cells[3],
                    legal_identity=cells[0],publication_date=None,emission_date=None,event_date_basis=None,
                    listing_url=page,listing_name=name,
                    attachments=[{'url':urljoin(page,href),'label':label} for href,label in row[4].get('links',[]) if '.pdf' in href])))
    return out


class SusesoFiscalizacionScout:
    SOURCE_SLUG = 'suseso_fiscalizacion'
    SOURCE_NAME = 'Superintendencia de Seguridad Social (SUSESO)'
    SOURCE_TYPE = 'official'
    PAGES = PAGES

    ENFORCEMENT_PAGES = ENFORCEMENT_PAGES

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
        for name, page, kind in self.ENFORCEMENT_PAGES:
            try:
                found = parse_enforcement_listing(fetch_html(page), name, page, kind)
                if not found:
                    raise ValueError('Enforcement register has no identifiable rows')
                self.surface_results.append({'url':page,'status':'parsed','documents':len(found),
                    'undated':sum(raw.event_date is None for raw in found),'surface_kind':kind})
                for raw in found:
                    items[(raw.url, raw.metadata.get('source_record_id'))] = raw
            except Exception as exc:
                self.surface_results.append({'url':page,'status':'error','error':type(exc).__name__})
        if not items:
            raise RuntimeError('No SUSESO actor surface parsed successfully')
        # No arbitrary top-40 cap: all dated rows remain auditable, before queue horizon filtering.
        return sorted(items.values(), key=lambda raw: raw.event_date or '', reverse=True)


def process_professional_sanction(raw, cfg):
    from .pipeline import build_signal
    from .processing import DeferredProcessing
    meta = raw.metadata
    if meta.get('date_conflicts') or not raw.event_date or not meta.get('regulated_entity'):
        raise DeferredProcessing('invalid_official_sanction_register_row')
    meta.update(what_happened=raw.raw_text,
        why_it_matters='La suspensión restringe la emisión de licencias médicas por el profesional identificado. Prestadores, Isapres y COMPIN pueden contrastar sus licencias y circuitos de validación con el periodo exacto del registro oficial; la sanción recae sobre el emisor.',
        event_type='SANCTION',scores={'economic':65,'regulatory':90,'scope':85,'novelty':75,'actionability':90},
        watch_tags=['suseso','licencias médicas','suspensión de emisores'])
    row = build_signal(raw, cfg).to_dict()
    row.update(signal_types=['Fiscalización'],scopes=meta['scopes'],
        **{key:meta.get(key) for key in ('source_record_id','legal_identity','document_class','regulated_entity',
            'fiscalized_actors','affected_actors','actor_evidence','sanction_amount','sanction_unit',
            'suspension_days','suspension_start','suspension_end','emission_date','publication_date','fact_date',
            'modification_date','event_date_basis','date_conflicts')})
    return row


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
