import io
import json
from pathlib import Path
from zipfile import ZipFile
import pytest
from openpyxl import load_workbook
from radar_salud.isapre_universe import parse_registry, release_metadata, parse_portfolio, load_universe, resolve_isapres, portfolio_benchmark
from radar_salud.models import RawItem
from radar_salud.pipeline import build_signal

ROOT = Path(__file__).resolve().parents[1]


def native():
    return ZipFile(ROOT/'data/audits/source_expansion/native_initial.zip')


def test_native_official_registry_and_current_portfolio():
    with native() as archive:
        receipts=json.loads(archive.read('receipts.json'))['receipts']
        reg=next(r for r in receipts if r['kind']=='registry')
        entities=parse_registry(archive.read(reg['body_file']).decode(),fetched_at=reg['completed_at'],sha256=reg['sha256'])
        assert len(entities)==10
        assert sum(e['isapre_type']=='open' for e in entities)==7
        assert all(e['validity']['effective_from'] is None for e in entities)
        release=next(r for r in receipts if r['kind']=='cartera_release')
        meta=release_metadata(archive.read(release['body_file']).decode())
        assert meta=={'published_at':'2026-10-02','reporting_period':'2026-08'}
        book=next(r for r in receipts if '.xlsx' in r['url'])
        data=parse_portfolio(archive.read(book['body_file']),source_url=book['url'],sha256=book['sha256'],published_at=meta['published_at'],fetched_at=book['completed_at'],universe=entities)
        assert len(data['coverage'])==8 and len(data['observations'])==320
        assert data['coverage'][-1]['total_beneficiaries']==2486683
        for cohort, count in [('open',7),('closed',3)]:
            rows=portfolio_benchmark(data['observations'],period='2026-08',cohort=cohort)
            assert len(rows)==count and sum(r['value'] for r in rows)==pytest.approx(100)


def test_missing_code_or_changed_schema_does_not_succeed():
    with native() as archive:
        receipts=json.loads(archive.read('receipts.json'))['receipts']; r=next(r for r in receipts if '.xlsx' in r['url'])
        b=load_workbook(io.BytesIO(archive.read(r['body_file'])), data_only=True)
    b['Agosto']['A8']=999
    out=io.BytesIO();b.save(out)
    with pytest.raises(ValueError,match='codes'):
        parse_portfolio(out.getvalue(),source_url=r['url'],sha256='a'*64,published_at='2026-10-02',fetched_at='2026-10-11')


@pytest.mark.parametrize('text,codes',[('SIS multa a Isapre Banmédica y CruzBlanca',[78,99]),('SUSESO: Isalud Isapre de Codelco SpA y VidaTres',[63,80]),('Convenio Isapre Fundación / Nueva Masvida',[76,81]),('Colmena, Consalud e Isapre Esencial',[67,107,108]),('Cruz del Norte',[94])])
def test_names_resolve_across_sources(text,codes):
    assert sorted(e['official_code'] for e in resolve_isapres(text))==codes


@pytest.mark.parametrize('text',['ILC emite bonos','Bupa compra un hospital','Banmédica S.A. matriz anuncia adquisición','La fundación presta un servicio esencial'])
def test_parent_or_generic_word_never_implies_subsidiary(text):
    assert resolve_isapres(text)==[]


def test_pipeline_reuses_canonical_identity():
    signal=build_signal(RawItem('test','Isapre Consalud firma convenio','https://example.org','Test','press'),{})
    assert signal.entity_refs[0].canonical_id=='cl:isapre:107'
    raw=RawItem('cmf','ILC financia sus filiales Consalud','https://example.org','CMF','official',metadata={'entity_scope':'issuer','entities':['ILC']})
    assert build_signal(raw,{}).entity_refs==[]
