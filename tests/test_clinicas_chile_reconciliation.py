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
