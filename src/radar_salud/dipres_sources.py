"""Official budget stocks, with fiscal hierarchy, state and price basis intact."""
from __future__ import annotations
import io
import re
import hashlib
from datetime import date
from calendar import monthrange
from urllib.parse import urlsplit, urlunsplit
from pypdf import PdfReader
from .official_tables import fold

MONTHS=('enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre')


def canonical_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname not in ('www.dipres.gob.cl','dipres.gob.cl'): raise ValueError('Budget requires official public DIPRES URL')
    return urlunsplit((p.scheme,p.netloc,p.path,'',''))


def pdf_text(content):
    if not content.startswith(b'%PDF'): raise ValueError('DIPRES document is not PDF content')
    reader=PdfReader(io.BytesIO(content))
    return '\n'.join(p.extract_text(extraction_mode='layout') or '' for p in reader.pages)


def _hierarchy(text):
    result={}
    for key,label in [('partida','PARTIDA'),('chapter','CAP[IÍ]TULO'),('program','PROGRAMA')]:
        matches=re.findall(label+r'\s*:\s*(\d{2})(?!\d)',text,re.I)
        if len(set(matches))>1: raise ValueError('Multiple budget hierarchies in one document')
        result[key]=matches[0] if matches else None
    sub=re.search(r'SUBPARTIDA\s*:\s*(\d{4})',text)
    result['subpartida']=sub[1] if sub else None
    return result


def _amount(value):
    if not re.fullmatch(r'-?\d[\d.]*',value): raise ValueError('Unrecognized budget amount')
    return int(value.replace('.',''))


def _base(text,url,sha):
    if not re.search(r'Miles de (?:\$|Pesos)',text,re.I): raise ValueError('Unverified budget currency/unit')
    return dict(source_url=canonical_url(url),source_sha256=sha,currency='CLP',unit='thousand_CLP',
                published_at=None,event_date=None,effective_date=None,
                date_reason='Official PDF provides fiscal period, not a verified publication day')


def parse_project(text, *, source_url, sha256):
    m=re.search(r'PROYECTO DE LEY DE PRESUPUESTOS (?:PARA EL )?AÑO\s+(20\d{2})',text,re.I)
    if not m: raise ValueError('Not a project budget document')
    if 'CUADRO COMPARATIVO' in text: raise ValueError('Comparative budget requires column-specific parser')
    dims=_hierarchy(text)
    if dims['partida']!='16': raise ValueError('Outside Salud budget perimeter')
    records=[]
    for metric in ('INGRESOS','GASTOS'):
        values=re.findall(r'^\s*'+metric+r'\s+(\d[\d.]*)\s*$',text,re.M)
        if len(set(values))!=1: raise ValueError(f'Missing/ambiguous official {metric} total')
        records.append({**_base(text,source_url,sha256),**dims,'metric':metric.lower(),
            'fiscal_year':int(m[1]),'period':m[1],'budget_state':'project',
            'measurement_basis':'nominal','price_base_year':int(m[1]),'value':_amount(values[0]),
            'reporting_level':'program' if dims['program'] else 'chapter' if dims['chapter'] else 'partida',
            'materiality_disposition':'data_snapshot','materiality_reason':'Budget stocks are not individual news rows'})
    return records


def parse_comparative(text, *, source_url, sha256):
    m=re.search(r'CUADRO COMPARATIVO ANAL[IÍ]TICO AÑOS\s+(20\d{2})\s*-\s*(20\d{2})',text)
    if not m: raise ValueError('Comparative fiscal years unverified')
    previous,current=map(int,m.groups());dims=_hierarchy(text)
    if dims['partida']!='16': raise ValueError('Outside Salud budget perimeter')
    if not all(f'(En $ de {y})' in text for y in (previous,current)):
        raise ValueError('Comparative nominal/real price bases unverified')
    header=fold(text[:text.find('INGRESOS')])
    header_months=[i+1 for i,name in enumerate(MONTHS) if re.search(r'\b'+name+r'\b',header)]
    # Layout PDF columns wrap: validate the single explicit cutoff month in the
    # execution/header area; conflicting monthly cutoffs fail closed.
    report_month=header_months[0] if len(header_months)==1 else None
    end=date(previous,report_month,monthrange(previous,report_month)[1]).isoformat() if report_month else None
    states=[('approved_adjusted',previous,previous,'nominal'),('modified',previous,previous,'nominal'),
            ('executed',previous,previous,'nominal'),('approved_adjusted',previous,current,'constant_prices'),
            ('project',current,current,'nominal')]
    records=[]
    for metric in ('INGRESOS','GASTOS'):
        line=next((l for l in text.splitlines() if re.match(r'^\s*'+metric+r'\s+\d',l)),None)
        if not line: raise ValueError('Comparative total missing')
        values=re.findall(r'-?\d[\d.]*',line)
        if len(values)<5: raise ValueError('Comparative fiscal columns incomplete')
        for column,(state,year,base,basis) in enumerate(states,1):
            if state=='executed' and not end: raise ValueError('Execution cutoff unknown')
            records.append({**_base(text,source_url,sha256),**dims,'metric':metric.lower(),
                'fiscal_year':year,'period':end[:7] if state=='executed' else str(year),
                'period_start':f'{previous}-01-01' if state=='executed' else None,'period_end':end if state=='executed' else None,
                'budget_state':state,'measurement_basis':basis,'price_base_year':base,'value':_amount(values[column-1]),
                'source_column':column,'reporting_level':'program' if dims['program'] else 'chapter' if dims['chapter'] else 'partida',
                'materiality_disposition':'data_snapshot','materiality_reason':'Preserve analytical columns; no news quota'})
    return records


def parse_execution(text, *, source_url, sha256):
    if 'INFORME DE IDENTIFICACION Y EJECUCION DE INVERSION PUBLICA' in text:
        return parse_investment_execution(text, source_url=source_url, sha256=sha256)
    m=re.search(r'INFORME EJECUCION (?:MENSUAL|TRIMESTRAL) PERIODO\s+(20\d{2})',text)
    if not m or 'Montos Devengados' not in text: raise ValueError('Execution/accrual schema missing')
    year=int(m[1]);area=re.search(r'\b(16\d{0,4})\s*:\s*([^\n]+)',text)
    if not area or len(area[1]) not in (2,4,6): raise ValueError('Execution hierarchy unknown')
    code=area[1];dims={'partida':code[:2],'chapter':code[2:4] or None,'program':code[4:6] or None}
    cutoff=fold(text[:2000]);month=next((i+1 for i,name in enumerate(MONTHS) if re.search(r'\b'+name+r'\b',cutoff)),None)
    if month is None:
        month=3 if 'primer trimestre' in cutoff else 6 if 'segundo trimestre' in cutoff else 9 if 'tercer trimestre' in cutoff else None
    if month is None: raise ValueError('Execution accumulated period unverified')
    end=date(year,month,monthrange(year,month)[1]).isoformat();records=[]
    for metric in ('INGRESOS','GASTOS'):
        line=next((l for l in text.splitlines() if re.match(r'^\s*'+metric+r'\s+\d',l)),None)
        if line is None: raise ValueError('Execution total missing')
        values=re.findall(r'\d[\d.]*',line)
        if len(values)!=3: raise ValueError('Execution budget columns unknown')
        for value,state in zip(values,['approved_initial','modified','executed']):
            records.append({**_base(text,source_url,sha256),**dims,'metric':metric.lower(),'fiscal_year':year,
                'period':f'{year}-{month:02d}','period_start':f'{year}-01-01','period_end':end,
                'budget_state':state,'measurement_basis':'nominal','price_base_year':year,'accounting_basis':'accrued',
                'value':_amount(value),'reporting_level':'program' if dims['program'] else 'chapter' if dims['chapter'] else 'partida',
                'materiality_disposition':'data_snapshot','materiality_reason':'Accumulated executed spending is not a monthly flow'})
    return records


def parse_investment_execution(text, *, source_url, sha256):
    period=re.search(r'A\s+('+ '|'.join(m.upper() for m in MONTHS) +r')\s+DE\s+(20\d{2})\s*-\s*LEY DE PRESUPUESTOS',text)
    program=re.search(r'PROGRAMA:\s*(16\d{4})(?!\d)',text)
    total=re.search(r'TOTAL NIVEL NACIONAL\s+(\d[\d.]*)\s+(\d[\d.]*)\s+(\d+[,.]\d+)\s*%',text)
    if not period or not program or not total: raise ValueError('Investment program/cutoff/national total unverified')
    year=int(period[2]);month=MONTHS.index(fold(period[1]))+1;end=date(year,month,monthrange(year,month)[1]).isoformat()
    generated=re.search(r'Fecha\s*:\s*(\d{2}/\d{2}/20\d{2})',text)
    return [{**_base(text,source_url,sha256),'partida':'16','chapter':program[1][2:4],'program':program[1][4:6],
        'metric':'public_investment_subtitle_31','reporting_level':'program','fiscal_year':year,
        'period':end[:7],'period_start':f'{year}-01-01','period_end':end,'budget_state':state,
        'measurement_basis':'nominal','price_base_year':year,'value':_amount(total[col]),
        'report_generated_date':generated[1] if generated else None,
        'decree_scope':'Totalmente Tramitado' if 'Totalmente Tramitado' in text else None,
        'materiality_disposition':'data_snapshot','materiality_reason':'National program investment aggregate; not a news item for each project/region'}
        for col,state in [(1,'identified'),(2,'executed')]]


def budget_key(row):
    return '|'.join(str(row.get(k)) for k in ['partida','subpartida','chapter','program','metric','fiscal_year','period','budget_state','price_base_year','accounting_basis'])


def material_variations(records):
    """Compare the project's exact program to the previous law in the SAME price base."""
    groups={}
    for row in records:
        if row['metric']!='gastos' or 'source_column' not in row:continue
        groups.setdefault(row['source_url'],{})[row['source_column']]=row
    candidates=[]
    for columns in groups.values():
        previous,current=columns.get(4),columns.get(5)
        if not previous or not current or previous['price_base_year']!=current['price_base_year'] or previous['value']<=0:continue
        delta=current['value']-previous['value'];pct=delta/previous['value']*100
        if abs(pct)<2 or abs(delta)<10000000:continue
        candidates.append(dict(partida=current['partida'],chapter=current['chapter'],program=current['program'],
            source_url=current['source_url'],source_sha256=current['source_sha256'],
            previous_state=previous['budget_state'],current_state='project',currency='CLP',unit='thousand_CLP',
            price_base_year=current['price_base_year'],delta=delta,pct_change=round(pct,4),
            publication_date=current['published_at'],disposition='deferred',
            reason='Material project allocation change (>=2% and >=CLP10bn); no verified publication day, core editorial gate remains open',
            use=['Trend fiscal allocation','Benchmark same program; do not sum transfer-financed program totals']))
    return candidates
