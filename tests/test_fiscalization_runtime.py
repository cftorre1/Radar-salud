from datetime import datetime, timezone
import importlib.util
from pathlib import Path

from radar_salud.history import merge_history
from radar_salud.pending_queue import PendingQueue, fingerprint
from radar_salud.suseso_fiscalizacion import ENFORCEMENT_PAGES, parse_enforcement_listing, process_professional_sanction


def professional_table(count=2):
    return '<table><tr>' + ''.join('<th>'+x+'</th>' for x in ['RUN PROFESIONAL EMISOR','RUT PROVISORIO PROFESIONAL EMISOR','NOMBRES PROFESIONAL EMISOR','APELLIDOS PROFESIONAL EMISOR','NÚMERO OFICIO','FECHA OFICIO','MONTO MULTA (UTM)','SUSPENSIÓN (días)','INICIO DE LA SUSPENSIÓN DE EMISIÓN DE LM (inclusive)','FIN DE LA SUSPENSIÓN DE EMISIÓN DE LM (inclusive)']) + '</tr>' + ''.join('<tr>'+''.join('<td>'+x+'</td>' for x in ['0-0','-','Emisor',str(i),f'O-02-S-{3209+i:05d}-2026','02/10/2026','50','90','07/10/2026','04/01/2027'])+'</tr>' for i in range(count))+'</table>'


def test_official_register_has_no_per_act_url_but_preserves_every_office_and_replay(tmp_path):
    raws=parse_enforcement_listing(professional_table(75),*ENFORCEMENT_PAGES[0])
    assert len(raws)==75 and len({raw.url for raw in raws})==1
    assert len({fingerprint(raw) for raw in raws})==75
    queue=PendingQueue(tmp_path/'queue.json')
    at=datetime(2026,10,11,tzinfo=timezone.utc)
    assert queue.discover('suseso_fiscalizacion',raws,now=at)==75
    assert queue.discover('suseso_fiscalizacion',raws,now=at)==0
    assert len(queue.items)==75
    assert all(item['lane']=='BACKFILL' for item in queue.items.values())
    rows=[process_professional_sanction(raw,{'base_confidence':100}) for raw in raws]
    assert len(merge_history(merge_history([],rows),rows))==75
    assert all(row['publication_date'] is None and row['event_date_basis']=='emission' for row in rows)
    assert all(row['fiscalized_actors']==['Profesionales emisores de licencias médicas'] for row in rows)
    assert all(row['affected_actors']==['COMPIN','Isapres'] for row in rows)
    assert all('RUN' not in str(row) for row in rows)
    spec=importlib.util.spec_from_file_location('fiscal_register_export',Path('scripts/export_web_snapshot.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert len(module._merge_duplicates(rows))==75


def test_register_suspension_dates_cannot_be_used_as_publication_or_emission():
    raw,=parse_enforcement_listing(professional_table(1),*ENFORCEMENT_PAGES[0])
    assert raw.event_date=='2026-10-02'
    assert raw.metadata['suspension_start']=='2026-10-07'
    assert raw.metadata['suspension_end']=='2027-01-04'
    assert raw.metadata['publication_date'] is None
    assert raw.metadata['modification_date'] is None


def test_inconsistent_register_row_is_retained_and_deferred():
    import pytest
    from radar_salud.processing import DeferredProcessing
    raw,=parse_enforcement_listing(professional_table(1).replace('04/01/2027','01/01/2026'),*ENFORCEMENT_PAGES[0])
    with pytest.raises(DeferredProcessing,match='invalid_official_sanction_register_row'):
        process_professional_sanction(raw,{})


def test_official_news_needs_specific_primary_review_even_with_fiscalization_in_title():
    import pytest
    from radar_salud.suseso_fiscalizacion import parse_official_news_listing, process_enforcement_news
    from radar_salud.processing import DeferredProcessing
    html='<p class="fecha iso8601-20260821T1200000300">21 de agosto</p><h3><a href="w3-article-999999.html">Nueva fiscalización</a></h3>'
    raw,=parse_official_news_listing(html)
    with pytest.raises(DeferredProcessing,match='official_news_requires_primary_enforcement_review'):
        process_enforcement_news(raw,{})
    raw.url='https://www.suseso.gob.cl/605/w3-article-788234.html'
    row=process_enforcement_news(raw,{'base_confidence':100})
    assert row['event_type']=='ENFORCEMENT_BALANCE'
    assert 'no se suman' in row['why_it_matters']


def test_primary_agent_review_corrects_misassigned_actor_and_preserves_substitution():
    import json
    from radar_salud.models import RawItem
    from radar_salud.superintendencia_fiscalizacion import process_fiscalizacion
    reviews=json.loads(Path('config/fiscalization_editorial_reviews.json').read_text())['primary_document_reviews']
    for number in ('11027','11076'):
        url=next(url for url in reviews if f'if-n{number}-' in url)
        review=reviews[url]
        raw=RawItem('superintendencia_fiscalizacion','Resolución '+number,url,'SIS','official',review['emission_date'],
            raw_text='Resumen del listado',metadata={'fiscalization_kind':'sanction','scope':'Agentes de ventas',
                'emission_date':review['emission_date'],'publication_date':review['observed_listing_publication_date'],
                'regulated_entity':'Actor incorrecto del listado','attachments':[{'url':review['primary_document_url']}],
                'sanction_effect':'revocation'})
        row=process_fiscalizacion(raw,{'base_confidence':100})
        assert row['observed_listing_regulated_entity']=='Actor incorrecto del listado'
        assert row['publication_date']==review['observed_listing_publication_date']
        if number=='11027':
            assert row['regulated_entity']=='Doris del Pilar Alcántara Poblete'
        else:
            assert row['event_type']=='SANCTION_SUBSTITUTION'
            assert row['sanction_amount'] is None and row['replaced_fine_amount']==5
            assert 'cancelación del registro' in row['what_happened']


def test_register_feed_aggregates_without_losing_legal_ids_or_inventing_publication():
    from datetime import date
    spec=importlib.util.spec_from_file_location('register_export',Path('scripts/export_web_snapshot.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=[process_professional_sanction(raw,{'base_confidence':100}) for raw in parse_enforcement_listing(professional_table(75),*ENFORCEMENT_PAGES[0])]
    pulse,=module._enforcement_register_pulses(rows,date(2026,10,11))
    assert pulse['counts']=={'30':75,'90':75}
    assert len(pulse['source_alternatives'])==75
    assert len({r['source_record_id'] for r in pulse['source_alternatives']})==75
    assert pulse['publication_date'] is None and pulse['event_date_basis']=='emission'
    assert all('2027-01-04' in r['material'] for r in pulse['source_alternatives'])


def test_primary_proof_reopens_date_rejection_preserving_original_detection(tmp_path):
    from radar_salud.models import RawItem
    raw=RawItem('superintendencia_fiscalizacion','Acto','https://www.superdesalud.gob.cl/normativa/acto','SIS','official','2025-09-23',metadata={'event_date_basis':'publication'})
    queue=PendingQueue(tmp_path/'queue.json');old=datetime(2026,9,25,tzinfo=timezone.utc)
    queue.discover(raw.source_slug,[raw],now=old)
    key=fingerprint(raw);queue.finish(key,'rejected','source_date_conflict_requires_review',now=old)
    raw.event_date='2026-09-23';raw.metadata.update(event_date_basis='verified_primary_emission',publication_date=None,date_conflicts=[],primary_document_review={'decision':'publish_fiscalization'})
    assert queue.discover(raw.source_slug,[raw],now=datetime(2026,10,11,tzinfo=timezone.utc))==0
    item=queue.items[key]
    assert item['status']=='pending' and item['lane']=='BACKFILL'
    assert item['detected_at']==old.isoformat()
    assert item['rediscovery_repairs'][0]['previous_reason']=='source_date_conflict_requires_review'
