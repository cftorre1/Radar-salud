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


def test_history_canonical_url_alias_is_one_act_but_offices_remain_distinct():
    a={'signal_types':['Fiscalización'],'source_url':'https://www.superdesalud.gob.cl/normativa/acto/','title':'Acto antiguo'}
    b={**a,'source_url':'https://www.superdesalud.gob.cl/normativa/acto','title':'Acto corregido'}
    assert len(merge_history([a],[b]))==1
    assert len(merge_history([{**a,'source_record_id':'Oficio 1'}],[{**b,'source_record_id':'Oficio 2'}]))==2


def test_unique_listing_image_alias_recovers_original_detection_without_merging_shared_images(tmp_path):
    from radar_salud.models import RawItem
    old=RawItem('superintendencia_fiscalizacion','Informe','https://www.superdesalud.gob.cl/old.jpg','SIS','official','2022-12-31',metadata={'event_date_basis':'publication'})
    q=PendingQueue(tmp_path/'queue.json');detected=datetime(2026,9,1,tzinfo=timezone.utc);q.discover(old.source_slug,[old],now=detected)
    current=RawItem(old.source_slug,'Informe corregido','https://www.superdesalud.gob.cl/observatorio/informe','SIS','official','2022-12-31',metadata={'event_date_basis':'publication','listing_asset_aliases':[old.url]})
    q.discover(old.source_slug,[current],now=datetime(2026,10,11,tzinfo=timezone.utc))
    assert len(q.items)==1
    item=q.items[fingerprint(current)];assert item['detected_at']==detected.isoformat()
    assert item['raw']['url']==current.url and item['rediscovery_repairs'][0]['previous_raw']['url']==old.url
    q=PendingQueue(tmp_path/'shared.json');q.discover(old.source_slug,[old],now=detected)
    other=RawItem(**{**current.__dict__,'url':current.url+'-different'})
    q.discover(old.source_slug,[current,other],now=datetime(2026,10,11,tzinfo=timezone.utc))
    assert len(q.items)==3


def test_medical_report_execution_month_never_becomes_daily_publication():
    import pytest
    from radar_salud.models import RawItem
    from radar_salud.processing import DeferredProcessing
    from radar_salud.public_source_pipeline import process_suseso_fiscalizacion
    raw=RawItem('suseso_fiscalizacion','Informe 2026/IFIS10','https://www.suseso.gob.cl/609/w3-article-786875.html','SUSESO','official',None,metadata={'document_class':'enforcement_report_candidate','execution_period':'2026 / Junio','publication_date':None,'emission_date':None})
    with pytest.raises(DeferredProcessing,match='execution_period_is_not_publication'):
        process_suseso_fiscalizacion(raw,{'base_confidence':100})


def test_archived_office_with_current_suspension_is_recovered_without_new_dates(tmp_path):
    raw,=parse_enforcement_listing(professional_table(1).replace('02/10/2026','17/06/2026'),*ENFORCEMENT_PAGES[0])
    queue=PendingQueue(tmp_path/'queue.json');at=datetime(2026,10,11,tzinfo=timezone.utc)
    queue.discover(raw.source_slug,[raw],now=at)
    key=fingerprint(raw);item=queue.items[key]
    item.update(status='archived',reason='outside_90_day_backfill')
    original_detection=item['detected_at'];queue.save()
    queue.discover(raw.source_slug,[raw],now=at)
    assert queue.items[key]['status']=='pending'
    assert queue.items[key]['lane']=='BACKFILL'
    assert queue.items[key]['detected_at']==original_detection
    assert queue.items[key]['raw']['event_date']=='2026-06-17'
    assert queue.items[key]['raw']['metadata']['publication_date'] is None
    assert queue.enforce_backfill_horizon(now=at)==0
    row=process_professional_sanction(raw,{'base_confidence':100})
    from radar_salud.editorial_gate import publication_ready
    assert publication_ready(row)[0]
    queue.finish(key,'published',now=at)
    queue.discover(raw.source_slug,[raw],now=at)
    assert queue.items[key]['status']=='published'


def test_expired_or_unverified_suspension_does_not_bypass_historical_horizon(tmp_path):
    from radar_salud.pending_queue import beyond_backfill_horizon
    from radar_salud.suseso_fiscalizacion import current_professional_suspension
    raw,=parse_enforcement_listing(professional_table(1).replace('02/10/2026','17/06/2026').replace('07/10/2026','18/06/2026').replace('04/01/2027','18/09/2026'),*ENFORCEMENT_PAGES[0])
    at=datetime(2026,10,11,tzinfo=timezone.utc)
    assert beyond_backfill_horizon(raw,at)
    raw.metadata['suspension_end']='2027-01-04'
    raw.metadata['date_conflicts']=['incomplete_or_inconsistent_register_row']
    assert beyond_backfill_horizon(raw,at)
    raw.metadata['date_conflicts']=[]
    assert not current_professional_suspension('https://example.org/register',raw.metadata,at.date())


def test_active_old_office_is_context_in_recent_register_without_inflating_counts():
    from datetime import date
    spec=importlib.util.spec_from_file_location('register_stock_export',Path('scripts/export_web_snapshot.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    new,=parse_enforcement_listing(professional_table(1),*ENFORCEMENT_PAGES[0])
    old,=parse_enforcement_listing(professional_table(1).replace('03209','00040').replace('02/10/2026','09/01/2026'),*ENFORCEMENT_PAGES[0])
    rows=[process_professional_sanction(raw,{'base_confidence':100}) for raw in (new,old)]
    pulse,=module.curate(rows,resolve_external=False,as_of=date(2026,10,11))
    assert pulse['counts']=={'30':1,'90':1}
    assert len(pulse['source_alternatives'])==1
    context,=pulse['historical_sanction_context']
    assert context['source_record_id']=='O-02-S-00040-2026'
    assert context['event_date']=='2026-01-09' and context['publication_date'] is None
    assert 'no se suman a las novedades' in pulse['what_happened']
