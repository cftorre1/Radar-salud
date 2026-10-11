from radar_salud.superintendencia_fiscalizacion import parse_listing, PAGES, _amount


def listing(rows):
    return '<table><tr><th>Fecha de publicación</th><th>Prestador</th><th>Título</th><th>Resumen</th><th>Materia</th></tr>' + ''.join(
        '<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>' for row in rows) + '</table>'


def test_sis_2026_emission_is_independent_of_contradictory_source_publication():
    # Source columns verified 11 Oct: 7462 labels publication 2025 and emission 2026.
    html = listing([['23/09/2025', '', '<a href="/normativa/resolucion-exenta-ip-n-7462-emision-23-09-2026/">Resolución Exenta IP/N° 7462 - Emisión: 23/09/2026</a>',
        'Sancionase al pago de una multa por 400 Unidades Tributarias Mensuales a Clínica Sanatorio Alemán, por una infracción del artículo 141 bis. Fecha emisión: 23 de septiembre de 2026.', 'Cheque en garantía']])
    raw, = parse_listing(html, *PAGES[2])
    assert raw.event_date == '2026-09-23'
    assert raw.metadata['publication_date'] == '2025-09-23'
    assert raw.metadata['date_conflicts'] == ['publication_precedes_emission']
    assert raw.metadata['regulated_entity'] == 'Clínica Sanatorio Alemán'
    assert (raw.metadata['sanction_amount'], raw.metadata['sanction_unit']) == (400, 'UTM')


def test_sis_reposition_uses_current_act_and_entity_column_not_prior_act_date():
    html = listing([['20/08/2026', 'Centro Médico y Dental Red Salud Alameda',
        '<a href="/fiscalizacion/9774">Resolución Exenta IF/N°9774 - Emisión: 20/08/2026</a>',
        'ACOGER PARCIALMENTE el recurso de reposición interpuesto por el prestador CENTRO MÉDICO Y DENTAL RED SALUD ALAMEDA, en contra de la Resolución Exenta IF/N° 7409, de 22 de julio de 2025, rebajando la multa impuesta a 120 UF.', 'GES']])
    raw, = parse_listing(html, *PAGES[2])
    assert raw.event_date == '2026-08-20'
    assert raw.metadata['regulated_entity'] == 'Centro Médico y Dental Red Salud Alameda'
    assert raw.metadata['sanction_effect'] == 'amendment'
    assert raw.metadata['sanction_amount'] == 120


def test_sis_deduplicates_aliases_but_preserves_two_acts_for_same_actor():
    rows = [['15/09/2026', '', f'<a href="/normativa/{number}/">Resolución Exenta IP/N°{number} - Emisión: 08/09/2026</a>',
        'Sancionase al pago de una multa por 50 Unidades de Fomento a Clínica Los Carrera, por una infracción.', 'Cheque'] for number in ['6835', '6836']]
    rows.append([*rows[0][:2], rows[0][2].replace('/6835/', '/6835/?utm_source=x#top'), *rows[0][3:]])
    items = parse_listing(listing(rows), *PAGES[2])
    assert len(items) == 2
    assert all(raw.event_date == '2026-09-08' for raw in items)
    assert all(raw.metadata['publication_date'] == '2026-09-15' for raw in items)


def test_sis_invalid_table_date_and_navigation_cannot_prove_discovery():
    rows = [['31/02/2026', '', '<a href="/normativa/1">Resolución Exenta IP/N°1</a>', 'Multa', 'GES'],
            ['15/09/2026', '', '<a href="/">Inicio de fiscalización</a>', 'Menú', 'GES']]
    assert parse_listing(listing(rows), *PAGES[2]) == []


def suseso_table(extra=''):
    return '<script>var fake="2020-01-01";</script><table><tr><th>Fecha</th><th>Título</th><th>Temas</th><th>Descriptores</th></tr><tr><td>29/09/2026</td><td><a href="/612/w3-article-791293.html">Dictamen O-02-S-03153-2026</a></td><td>Licencias médicas</td><td>Procedimiento</td></tr>' + extra + '</table>'


def test_suseso_uses_row_date_and_unions_compin_isapre_memberships(monkeypatch):
    from radar_salud.suseso_fiscalizacion import SusesoFiscalizacionScout
    monkeypatch.setattr('radar_salud.suseso_fiscalizacion.fetch_html', lambda url: suseso_table())
    raw, = SusesoFiscalizacionScout().discover()
    assert raw.event_date == '2026-09-29'
    assert raw.metadata['fiscalized_actors'] == ['COMPIN', 'Isapres']
    assert len(raw.metadata['listing_urls']) == 2
    assert raw.metadata['document_class'] == 'related_normative'


def test_suseso_related_normative_rejected_before_ai_or_detail_fetch():
    import pytest
    from radar_salud.processing import RejectedProcessing
    from radar_salud.suseso_fiscalizacion import parse_actor_listing, PAGES
    from radar_salud.public_source_pipeline import process_suseso_fiscalizacion
    raw, = parse_actor_listing(suseso_table(), *PAGES[0])
    with pytest.raises(RejectedProcessing, match='related_normative_not_enforcement'):
        process_suseso_fiscalizacion(raw, {})


def test_suseso_partial_surface_keeps_other_actor_and_exposes_failure(monkeypatch):
    from radar_salud.suseso_fiscalizacion import SusesoFiscalizacionScout
    def fetch(url):
        if '30981' in url: raise TimeoutError()
        return suseso_table()
    monkeypatch.setattr('radar_salud.suseso_fiscalizacion.fetch_html', fetch)
    scout = SusesoFiscalizacionScout()
    raw, = scout.discover()
    assert raw.metadata['fiscalized_actors'] == ['COMPIN']
    assert [row['status'] for row in scout.surface_results] == ['error', 'parsed']


def test_suseso_retains_undated_documents_and_does_not_limit_recent_coverage(monkeypatch):
    from radar_salud.suseso_fiscalizacion import SusesoFiscalizacionScout
    html = suseso_table(''.join(f'<tr><td>29/09/2026</td><td><a href="/612/w3-article-{800000+i}.html">Dictamen {i}-2026</a></td><td>Licencias</td></tr>' for i in range(45)) + '<tr><td></td><td><a href="/612/w3-article-999999.html">Informe sin fecha</a></td></tr>')
    monkeypatch.setattr('radar_salud.suseso_fiscalizacion.fetch_html', lambda url: html)
    scout = SusesoFiscalizacionScout()
    items = scout.discover()
    assert len(items) == 47
    assert sum(raw.event_date is None for raw in items) == 1
    assert scout.surface_results[0]['undated'] == 1


def test_fiscalization_rediscovery_recovers_archived_date_without_losing_checkpoint(tmp_path):
    from dataclasses import asdict
    from datetime import datetime, timezone
    from radar_salud.models import RawItem
    from radar_salud.pending_queue import PendingQueue, atomic_json, fingerprint, legacy_fingerprint
    raw = RawItem('superintendencia_fiscalizacion', 'Resolución 7462 antigua', 'https://example.org/7462/', 'SIS', 'official', '2025-09-23')
    key = legacy_fingerprint(raw)
    atomic_json(tmp_path/'queue.json', {key:dict(raw=asdict(raw),source=raw.source_slug,lane='BACKFILL',status='archived',detected_at='2026-10-01T00:00:00+00:00',attempts=2,reason='outside_90_day_backfill')})
    queue = PendingQueue(tmp_path/'queue.json')
    raw.title = 'Resolución 7462 - Emisión: 23/09/2026'
    raw.event_date = '2026-09-23';raw.metadata = {'event_date_basis':'emission'}
    assert queue.discover(raw.source_slug,[raw],now=datetime(2026,10,11,tzinfo=timezone.utc),last_discovered_at='2026-10-10T00:00:00+00:00') == 0
    item = queue.items[fingerprint(raw)]
    assert len(queue.items) == 1 and item['status'] == 'pending' and item['lane'] == 'BACKFILL'
    assert item['attempts'] == 2 and item['detected_at'].startswith('2026-10-01')
    assert item['legacy_keys'] == [key]
    assert item['rediscovery_repairs'][0]['previous_raw']['event_date'] == '2025-09-23'
    assert queue.discover(raw.source_slug,[raw]) == 0
    assert len(item['rediscovery_repairs']) == 1


def test_fiscalization_duplicate_legacy_titles_preserve_published_decision(tmp_path):
    from dataclasses import asdict
    from radar_salud.models import RawItem
    from radar_salud.pending_queue import PendingQueue, atomic_json, fingerprint, legacy_fingerprint
    raw = RawItem('suseso_fiscalizacion','Dictamen anterior','https://example.org/1/','SUSESO','official','2026-09-29')
    old = legacy_fingerprint(raw)
    published = dict(raw=asdict(raw),source=raw.source_slug,lane='BACKFILL',status='published',detected_at='2026-10-01',attempts=1,reason=None)
    raw.title = 'Dictamen renombrado';new = legacy_fingerprint(raw)
    atomic_json(tmp_path/'q.json', {old:published, new:dict(published,raw=asdict(raw),status='pending',attempts=0)})
    queue = PendingQueue(tmp_path/'q.json');queue.discover(raw.source_slug,[raw])
    assert len(queue.items) == 1
    assert queue.items[fingerprint(raw)]['status'] == 'published'
    assert len(queue.items[fingerprint(raw)]['superseded_records']) == 1


def test_fiscalization_legacy_seen_is_respected_and_other_source_identity_unchanged(tmp_path):
    from radar_salud.models import RawItem
    from radar_salud.pending_queue import PendingQueue, fingerprint, legacy_fingerprint
    raw=RawItem('suseso_fiscalizacion','Circular 3926','https://example.org/3926','SUSESO','official','2026-09-23')
    queue=PendingQueue(tmp_path/'q.json')
    assert queue.discover(raw.source_slug,[raw],seen={legacy_fingerprint(raw)}) == 0
    raw.source_slug='minsal'
    assert fingerprint(raw) == legacy_fingerprint(raw)


def test_sis_date_conflict_gets_durable_review_reason_and_appeal_is_not_new_sanction():
    import pytest
    from radar_salud.processing import RejectedProcessing
    from radar_salud.models import RawItem
    from radar_salud.superintendencia_fiscalizacion import process_fiscalizacion
    raw=RawItem('superintendencia_fiscalizacion','Resolución Exenta IP/N°7462','https://example.org/7462','SIS','official','2026-09-23',metadata={'date_conflicts':['publication_precedes_emission']})
    with pytest.raises(RejectedProcessing, match='source_date_conflict_requires_review'):
        process_fiscalizacion(raw,{})
    raw.metadata={'scope':'Prestadores','fiscalization_kind':'sanction','regulated_entity':'Red Salud Alameda','sanction_effect':'amendment','sanction_amount':120,'sanction_unit':'UF','publication_date':'2026-08-20','emission_date':'2026-08-20','event_date_basis':'emission'}
    raw.event_date='2026-08-20'
    row=process_fiscalizacion(raw,{'base_confidence':100})
    assert row['event_type']=='SANCTION_AMENDMENT'
    assert row['publication_date']==row['emission_date']=='2026-08-20'
    assert 'modifica una sanción anterior' in row['why_it_matters']


def test_sanction_pulse_counts_publications_without_changing_act_dates():
    import importlib.util
    from pathlib import Path
    from datetime import date
    spec=importlib.util.spec_from_file_location('fiscal_export',Path('scripts/export_web_snapshot.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    row={'title':'Resolución 6836','source_url':'https://example.org/6836','event_type':'SANCTION','scopes':['Prestadores'],'event_date':'2026-09-08','publication_date':'2026-09-15','regulated_entity':'Clínica Los Carrera','sanction_amount':70,'sanction_unit':'UF'}
    pulse,=module._sanction_pulses([row],date(2026,10,11))
    assert pulse['event_date']=='2026-09-15' and pulse['window_basis']=='publication_date'
    assert pulse['source_alternatives'][0]['event_date']=='2026-09-08'
    assert pulse['source_alternatives'][0]['publication_date']=='2026-09-15'
