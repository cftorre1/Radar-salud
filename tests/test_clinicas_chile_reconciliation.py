import pytest
from radar_salud.models import RawItem
from radar_salud.source_scouts import ClinicasChileScout
from radar_salud.public_source_pipeline import process_clinicas_chile
from radar_salud.processing import DeferredProcessing


def test_clinicas_library_excludes_menu_dates_and_dataset_years():
    scout=ClinicasChileScout()
    html='''<a href="/quienes-somos/">Quiénes Somos y nuestras instituciones</a>
      <a href="/knowledgebase_category/estudios-y-analisis/">Estudios y análisis</a>
      <a href="/wp-content/uploads/2025/12/dimensionamiento-2024.pdf">Descargar DIMENSIONAMIENTO 2024</a>
      <a href="https://evil.example/a.pdf">Descargar Documento 2026</a>'''
    rows=scout.discover_from_html(html,"Estudios y análisis",scout.PAGES[2][1])
    assert len(rows)==1 and rows[0].event_date is None
    assert rows[0].metadata["publication_date_source"]=="unverified"
    assert scout.PAGES[2][1].endswith("/estudios-y-analisis/")


def test_clinicas_news_binds_listing_stamp_without_borrowing_body_dates(monkeypatch):
    scout=ClinicasChileScout()
    html='''<div>6:42 pm el 2 de Octubre del 2026</div><h2><a href="/jornada-salud-digital/">Clínicas de Chile y CENS revisan nuevo marco digital</a></h2>'''
    raw=scout.discover_from_html(html,"Noticias",scout.PAGES[0][1])[0]
    assert raw.event_date=="2026-10-02"
    assert raw.metadata["publication_date_source"]=="dated_news_listing"
    pdf=RawItem("clinicas_chile","Descargar Memoria 2025","https://www.clinicasdechile.cl/wp-content/uploads/2026/03/memoria-2025.pdf",
                "Clínicas de Chile A.G.","sector_association",metadata={"clinicas_channel":"Memorias"},
                raw_text="Cita legal del 31 de agosto de 2004. "*20)
    monkeypatch.setattr("radar_salud.public_source_pipeline.extract_pdf_text",lambda *a,**k:pytest.fail("An undated PDF must not be evaluated"))
    with pytest.raises(DeferredProcessing,match="without verified date"):
        process_clinicas_chile(pdf,{})
    assert pdf.event_date is None


def test_clinicas_undated_card_cannot_inherit_previous_stamp():
    scout=ClinicasChileScout()
    html='''<div>6:42 pm el 2 de Octubre del 2026</div>
      <h2><a href="/jornada-salud-digital/">Clínicas de Chile y CENS revisan nuevo marco digital</a></h2>
      <h2><a href="/otra-noticia-sin-fecha/">Otra noticia de Clínicas de Chile sin sello de publicación</a></h2>'''
    rows=scout.discover_from_html(html,"Noticias",scout.PAGES[0][1])
    assert rows[0].event_date=="2026-10-02"
    assert rows[1].event_date is None


def test_clinicas_partial_library_failure_preserves_news_and_exact_error(monkeypatch):
    scout=ClinicasChileScout()
    def fetch(url):
        if url==scout.PAGES[0][1]:
            return '<div>6:42 pm el 2 de Octubre del 2026</div><h2><a href="/jornada-salud-digital/">Clínicas de Chile y CENS revisan nuevo marco digital</a></h2>'
        if url.endswith('/jornada-salud-digital/'):return '<h1>Clínicas de Chile y CENS</h1>'
        raise OSError('blocked')
    monkeypatch.setattr('radar_salud.source_scouts.fetch_html',fetch)
    rows=scout.discover()
    assert len(rows)==1 and rows[0].event_date=='2026-10-02'
    assert len(scout.discovery_errors)==10
    assert any('Memorias:' in error and 'OSError' in error for error in scout.discovery_errors)
    scout.discover()
    assert len(scout.discovery_errors)==10


def test_verified_rediscovery_updates_retry_without_bypassing_gate(tmp_path):
    from radar_salud.pending_queue import PendingQueue
    raw=RawItem('clinicas_chile','Noticia de gremio con fecha inicialmente ausente',
                'https://www.clinicasdechile.cl/noticia-auditada/','Clínicas de Chile A.G.','sector_association',
                metadata={'publication_date_source':'unverified','source_quality_gate':'pending_90_day_audit'})
    queue=PendingQueue(tmp_path/'queue.json');queue.discover('clinicas_chile',[raw])
    key=next(iter(queue.items));queue.finish(key,'retry','without_verified_date')
    detected=queue.items[key]['detected_at']
    raw.event_date='2026-10-02';raw.metadata.update(publication_date_source='dated_news_listing',source_quality_gate='passed')
    assert queue.discover('clinicas_chile',[raw])==0
    stored=queue.items[key]
    assert stored['raw']['event_date']=='2026-10-02' and stored['lane']=='BACKFILL'
    assert stored['detected_at']==detected and stored['raw']['metadata']['source_quality_gate']=='pending_90_day_audit'
