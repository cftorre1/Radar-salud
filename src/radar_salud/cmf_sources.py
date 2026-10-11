"""Public CMF issuer documents. Parent and subsidiary are separate reporting actors."""
from __future__ import annotations
import hashlib
import re
from datetime import date
from urllib.parse import urljoin, urlsplit, parse_qs, urlencode
from .official_tables import read, fold

CMF = 'https://www.cmfchile.cl/institucional/mercados/entidad.php'


def issuer_url(rut, tab=1):
    return CMF + '?' + urlencode(dict(control='svs', mercado='V', pestania=tab,
                                     rut=rut, tipoentidad='RVEMI', vig='VI'))


def validate_rut(value):
    match=re.fullmatch(r'(\d{7,8})\s*-\s*([0-9Kk])', value.replace('.', ''))
    if not match: raise ValueError('Invalid reporting RUT')
    total=sum(int(n)*[2,3,4,5,6,7][i%6] for i,n in enumerate(reversed(match[1])))
    check=11-total%11; digit='0' if check==11 else 'K' if check==10 else str(check)
    if digit != match[2].upper(): raise ValueError('CMF RUT check digit mismatch')
    return match[1]+'-'+digit


def parse_actor(html, *, source_url, sha256, fetched_at):
    rows={fold(r[0]):r[1] for r in read(html).rows if len(r)==2}
    rut=validate_rut(rows.get('rut','')); expected=parse_qs(urlsplit(source_url).query).get('rut',[''])[0]
    if rut.split('-')[0] != expected: raise ValueError('CMF actor is not the requested reporting entity')
    if not rows.get('razon social'): raise ValueError('CMF identification is empty')
    return dict(entity_id='cl:rut:'+rut, rut=rut, legal_name=rows['razon social'],
                commercial_name=rows.get('nombre de fantasia') or None,
                issuer_registration_status=rows.get('vigencia'),
                ticker=None, ticker_reason='CMF identification does not prove a current listed ticker',
                reporting_role='reporting_entity', parent_entity_id=None, subsidiary_entity_ids=[],
                reporting_perimeter='Document-specific: consolidated or individual; no subsidiary fact propagation',
                source_url=source_url, source_sha256=sha256, fetched_at=fetched_at)


def essential_query(rut, name, start, end):
    return issuer_url(rut,25), urlencode(dict(dd=f'{start.day:02d}', mm=f'{start.month:02d}', aa=start.year,
        dd2=f'{end.day:02d}', mm2=f'{end.month:02d}', aa2=end.year, entidad=name, rut=rut, formulario=1))


def _day(text):
    m=re.search(r'(?<!\d)(\d{2})[/.](\d{2})[/.](20\d{2})(?!\d)', text)
    return date(int(m[3]), int(m[2]), int(m[1])).isoformat() if m else None


def parse_essential_index(html, *, actor, source_url, query_start, query_end):
    """Only dated result rows with an actual document link; menus/forms are not results."""
    # Preserve links within each row, including documents linked through JS window.open.
    documents=[]
    for row_html in re.findall(r'<tr\b[^>]*>(.*?)</tr>', html, re.I|re.S):
        row=read('<table><tr>'+row_html+'</tr></table>')
        text=' '.join(row.text); published=_day(text)
        if not published: continue
        links=list(row.links)
        links += [(u,'Documento') for u in re.findall(r"(?:ventana|window\.open)\(['\"]([^'\"]+)",row_html)]
        for href,label in links:
            url=urljoin(source_url,href)
            if urlsplit(url).hostname not in ('www.cmfchile.cl','cmfchile.cl'): continue
            if not re.search(r'(?:ver_sgd\.php|hes_|hechos.*(?:archivo|descarg)|ver_doc|\.pdf)',url,re.I): continue
            if not query_start <= published <= query_end: raise ValueError('CMF returned a disclosure outside requested dates')
            # A date in the search index is communication/publication, not the event date.
            number=re.search(r'\b20\d{11}\b', label)
            if not number: raise ValueError('Essential disclosure lacks its official document number')
            identity=actor['rut']+':'+number[0]
            documents.append(dict(record_id=identity, official_document_number=number[0], issuer_entity_id=actor['entity_id'], issuer_rut=actor['rut'],
                issuer_name=actor['legal_name'], title=text.strip(), source_url=url, discovered_from=source_url,
                published_at=published, event_date=None, effective_date=None, reporting_period=None,
                entity_scope='issuer', subsidiary_attribution=False,
                disposition='deferred', reason='Primary document and materiality must be verified'))
    documents=list({d['record_id']:d for d in documents}.values())
    text=fold(' '.join(read(html).text))
    explicit_absence=any(term in text for term in ['no se encontraron', 'no existen hechos', 'no hay hechos', 'sin resultados', 'sin informacion'])
    return {'documents':documents, 'coverage_complete':bool(documents or explicit_absence),
            'coverage_reason':'dated_results' if documents else 'official_explicit_absence' if explicit_absence else 'search_form_or_unrecognized_results',
            'query_start':query_start, 'query_end':query_end}


def financial_documents(html, *, actor, source_url, reporting_period, sha256):
    if parse_qs(urlsplit(source_url).query).get('pestania') != ['3']:
        raise ValueError('Financial calendar is not a financial statement')
    if not re.fullmatch(r'20\d{2}-(03|06|09|12)', reporting_period): raise ValueError('Invalid financial reporting period')
    result=[]
    for href,label in read(html).links:
        if not re.search(r'estados financieros.*PDF|an.lisis razonado|hechos relevantes',label,re.I): continue
        url=urljoin(source_url,href)
        if urlsplit(url).hostname not in ('www.cmfchile.cl','cmfchile.cl'): continue
        result.append(dict(issuer_entity_id=actor['entity_id'], issuer_rut=actor['rut'], document_kind=label,
            source_url=url, discovered_from=source_url, reporting_period=reporting_period,
            published_at=None, event_date=None, date_reason='Quarter selected is an accounting period, not a publication day',
            reporting_perimeter='consolidated', index_sha256=sha256,
            disposition='data_document', reason='EEFF feeds Benchmark; primary body/hash and unit required for numerical results'))
    return result


def classify_primary(text):
    """Deterministic triage, never final publication or attribution of a parent fact."""
    value=fold(text)
    material=[label for label,pattern in [
        ('capital',r'aumento de capital|colocacion de acciones|suscripcion de acciones'),
        ('debt',r'emision de bonos|credito|refinanciamiento|incumplimiento|covenant'),
        ('ownership',r'adquisicion|enajenacion|toma de control|oferta publica|fusion'),
        ('capacity',r'cierre de clinica|apertura de clinica|inversion hospitalaria')]
        if re.search(pattern,value)]
    if material: return {'material':True,'disposition':'deferred','themes':material,
                         'reason':'Primary financial/corporate event; independent editorial validation required'}
    if re.search(r'reparto de dividendos|dividendo|renuncia|designacion|junta ordinaria|citacion',value):
        return {'material':False,'disposition':'rejected','themes':[],
                'reason':'Routine issuer governance/dividend notice without demonstrated health-market effect'}
    return {'material':None,'disposition':'deferred','themes':[], 'reason':'Materiality cannot be determined from the available primary document'}


def financial_results(html, *, actor, source_url, sha256, reporting_period):
    """Read actual IFRS income cells with their column interval, unit and perimeter."""
    result=[]
    for table in re.findall(r'<table\b[^>]*>(.*?)</table>',html,re.I|re.S):
        if '[310000]' not in table: continue
        rows=read('<table>'+table+'</table>').rows
        header=next((r for r in rows if r and '[310000]' in r[0]),None)
        if not header or 'CLP - Peso chileno (Miles)' not in header[0]:
            raise ValueError('Income statement unit or column schema not supported')
        intervals=[]
        for col in header[1:]:
            dates=re.findall(r'20\d{2}-\d{2}-\d{2}',col)
            if len(dates)!=2: raise ValueError('Financial interval missing')
            intervals.append(dates)
        if not any(end.startswith(reporting_period) for _,end in intervals):
            raise ValueError('Requested period differs from actual financial columns')
        for row in rows:
            if not row or fold(row[0]) not in ['ingresos de actividades ordinarias','ganancia (perdida)']: continue
            if len(row)!=len(intervals)+1: raise ValueError('Financial result column count mismatch')
            for value,(start,end) in zip(row[1:],intervals):
                if value=='-': continue
                if not re.fullmatch(r'-?\d[\d.]*',value): raise ValueError('Financial result not numeric')
                result.append(dict(entity_id=actor['entity_id'], metric_id='revenue' if 'ingresos' in fold(row[0]) else 'profit_loss',
                    value=int(value.replace('.','')), period_start=start, period_end=end,
                    reporting_period=reporting_period, currency='CLP', unit='thousand_CLP',
                    reporting_perimeter='consolidated', measurement_basis='nominal', published_at=None,
                    source_url=source_url, source_sha256=sha256,
                    comparability='Same reporting entity, interval, perimeter and accounting basis only'))
    return result
