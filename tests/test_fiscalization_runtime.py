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
