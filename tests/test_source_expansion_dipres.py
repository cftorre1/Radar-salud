import json
from pathlib import Path
from zipfile import ZipFile
import pytest
from radar_salud.dipres_sources import pdf_text, parse_project, parse_comparative, parse_execution, material_variations, budget_key

ROOT=Path(__file__).resolve().parents[1]


def primary(number):
    with ZipFile(ROOT/'data/audits/source_expansion/native_validated.zip') as z:
        receipt=next(r for r in json.loads(z.read('receipts.json'))['receipts'] if number in r['url'] and '.pdf' in r['url'])
        return pdf_text(z.read(receipt['body_file'])), {'source_url':receipt['url'],'sha256':receipt['sha256']}


def test_fonasa_project_remains_project_with_hierarchy_and_actual_unit():
    text,meta=primary('430523');rows=parse_project(text,**meta)
    expense=next(r for r in rows if r['metric']=='gastos')
    assert (expense['partida'],expense['chapter'],expense['program'])==('16','02','01')
    assert expense['budget_state']=='project' and expense['fiscal_year']==2027
    assert expense['value']==16223541378 and expense['unit']=='thousand_CLP'
    assert expense['published_at'] is None and expense['effective_date'] is None
    assert expense['source_url'].endswith('articles-430523_doc_pdf.pdf')


def test_comparative_never_compares_different_price_bases():
    text,meta=primary('431114');rows=parse_comparative(text,**meta)
    assert len(rows)==10
    expense=[r for r in rows if r['metric']=='gastos']
    execution=next(r for r in expense if r['budget_state']=='executed')
    assert execution['period_end']=='2026-08-31' and execution['value']==11715714950
    prior=next(r for r in expense if r['source_column']==4)
    assert prior['measurement_basis']=='constant_prices' and prior['price_base_year']==2027
    change=material_variations(rows)[0]
    assert change['delta']==736575636 and change['pct_change']==pytest.approx(4.7561)
    assert change['disposition']=='deferred' and change['current_state']=='project'
    changed=[{**r,'price_base_year':2026} if r.get('source_column')==4 else r for r in rows]
    assert material_variations(changed)==[]


def test_execution_preserves_approved_modified_and_accumulated_accrued():
    text,meta=primary('424381');rows=parse_execution(text,**meta)
    assert {r['budget_state'] for r in rows}=={'approved_initial','modified','executed'}
    expense=next(r for r in rows if r['budget_state']=='executed' and r['metric']=='gastos')
    assert expense['value']==10414445721 and expense['period_end']=='2026-07-31'
    assert expense['accounting_basis']=='accrued' and expense['program'] is None
    assert budget_key(expense)!=budget_key({**expense,'program':'01'})


def test_aggregate_and_program_or_future_year_never_get_conflated():
    text,meta=primary('431115');rows=parse_comparative(text,**meta)
    assert rows[0]['subpartida']=='1603' and rows[0]['chapter'] is None
    with pytest.raises(ValueError,match='unit'):
        parse_project(primary('430523')[0].replace('Miles de $',''),**primary('430523')[1])
    with pytest.raises(ValueError,match='column'):
        parse_project(primary('431114')[0],**primary('431114')[1])


def test_investment_execution_is_a_program_aggregate_with_report_generation_separate():
    text,meta=primary('426169');rows=parse_execution(text,**meta)
    assert len(rows)==2 and rows[1]['value']==776488
    assert (rows[1]['partida'],rows[1]['chapter'],rows[1]['program'])==('16','09','01')
    assert rows[1]['period_end']=='2026-07-31' and rows[1]['report_generated_date']=='24/08/2026'
    assert rows[1]['published_at'] is None and rows[1]['metric']=='public_investment_subtitle_31'
