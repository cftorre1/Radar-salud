"""Undated sources publish with a labelled first-detection date (Dirección 27-oct-2026, decision d)."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from radar_salud.date_basis import apply_first_detected, upload_path_month, chile_day
from radar_salud.models import RawItem
from radar_salud.processing import DeferredProcessing, RejectedProcessing
from radar_salud.public_source_pipeline import process_clinicas_chile, process_corporate_news
from radar_salud.sources import load_sources, source_index

TODAY = date(2026, 10, 27)


def item(url="https://www.bupa.cl/sala-de-prensa/nota", detected="2026-10-25T21:17:56+00:00", **meta):
    return RawItem("bupa_chile", "Titular de prueba suficientemente largo", url, "Bupa Chile", "corporate",
                   metadata={"first_detected_at": detected, **meta})


def test_first_detection_sets_labelled_basis_never_publication_date():
    raw = item()
    assert apply_first_detected(raw, today=TODAY, window_days=30) == "2026-10-25"
    assert raw.event_date == "2026-10-25" and raw.metadata["date_basis"] == "first_detected"
    assert raw.metadata["publication_date"] is None and raw.metadata["date_label"].startswith("Detectado el")


def test_detection_outside_window_or_missing_is_never_published():
    with pytest.raises(RejectedProcessing, match="outside_daily_window"):
        apply_first_detected(item(detected="2026-09-20T12:00:00+00:00"), today=TODAY, window_days=30)
    with pytest.raises(DeferredProcessing):
        apply_first_detected(RawItem("bupa_chile", "t", "https://www.bupa.cl/x", "Bupa Chile", "corporate"), today=TODAY)


def test_late_detection_of_an_old_wordpress_upload_is_refused():
    # Real queue example: library memoria uploaded 2026/03, first detected 11-oct.
    url = "https://www.clinicasdechile.cl/wp-content/uploads/2026/03/Memoria-clinicas-2025-final.pdf"
    assert upload_path_month(url) == (2026, 3)
    with pytest.raises(RejectedProcessing, match="uploaded_before_window"):
        apply_first_detected(item(url=url, detected="2026-10-11T06:00:00+00:00"), today=TODAY, window_days=30)
    fresh = "https://www.clinicasdechile.cl/wp-content/uploads/2026/10/Informe-camas.pdf"
    assert apply_first_detected(item(url=fresh, detected="2026-10-11T06:00:00+00:00"), today=TODAY, window_days=30)


def test_chile_calendar_day_for_utc_detection():
    assert chile_day("2026-10-27T02:30:00+00:00").isoformat() == "2026-10-26"


def recent(days=2):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_undated_bupa_article_publishes_with_detection_label(monkeypatch):
    monkeypatch.setenv("RADAR_DAILY_WINDOW_DAYS", "30")
    cfg = source_index(load_sources(Path("config/sources.json")))["bupa_chile"]
    raw = RawItem("bupa_chile", "Clínica Bupa Santiago incorpora cirugía robótica y amplía el acceso a intervenciones de alta precisión en Chile",
                  "https://www.bupa.cl/sala-de-prensa/clinica-bupa-santiago-incorpora-cirugia-robotica", "Bupa Chile", "corporate",
                  metadata={"first_detected_at": recent()})
    html = Path("tests/fixtures/bupa_real_article_excerpt.html").read_text().replace(
        '<p class="tools__date">Martes 5 de mayo de 2026</p>', "")
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html", lambda _: html)
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_news", lambda **kw: {
        "relevance_score": 82, "what_happened": "Bupa incorporó cirugía robótica en Clínica Bupa Santiago con el sistema Toumai.",
        "why_it_matters": "Amplía la capacidad quirúrgica de alta precisión de la red privada."})
    row = process_corporate_news(raw, cfg)
    assert row["date_basis"] == "first_detected" and row["publication_date"] is None
    assert row["event_date"] == chile_day(raw.metadata["first_detected_at"]).isoformat()
    assert row["date_label"].startswith("Detectado el")
    # An unreadable (present) date field is never replaced by detection.
    raw2 = RawItem(raw.source_slug, raw.title, raw.url, raw.source_name, raw.source_type,
                   metadata={"first_detected_at": recent()})
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html",
                        lambda _: html.replace("<div class=\"CUERPO\">", '<p class="tools__date">fecha ilegible</p><div class="CUERPO">'))
    with pytest.raises(DeferredProcessing, match="publication date unavailable"):
        process_corporate_news(raw2, cfg)


def test_clinicas_library_document_uses_detection_but_news_still_requires_date(monkeypatch):
    monkeypatch.setenv("RADAR_DAILY_WINDOW_DAYS", "30")
    now = datetime.now(timezone.utc)
    url = f"https://www.clinicasdechile.cl/wp-content/uploads/{now:%Y}/{now:%m}/informe-camas.pdf"
    doc = RawItem("clinicas_chile", "Informe de camas hospitalarias", url, "Clínicas de Chile A.G.", "sector_association",
                  metadata={"clinicas_channel": "Documentos", "publication_date_source": "unverified",
                            "first_detected_at": recent(1)})
    monkeypatch.setattr("radar_salud.public_source_pipeline.extract_pdf_text", lambda *a, **k: "Camas hospitalarias privadas. " * 20)
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_news", lambda **kw: {
        "relevance_score": 80, "what_happened": "Clínicas de Chile publicó un informe con la dotación de camas hospitalarias privadas.",
        "why_it_matters": "Entrega una base para comparar capacidad hospitalaria privada por región."})
    row = process_clinicas_chile(doc, {"slug": "clinicas_chile", "name": "Clínicas de Chile A.G."})
    assert row["date_basis"] == "first_detected" and row["signal_types"] == ["Datos"]
    news = RawItem("clinicas_chile", "Nota sin fecha", "https://www.clinicasdechile.cl/nota/", "Clínicas de Chile A.G.",
                   "sector_association", metadata={"clinicas_channel": "Noticias", "first_detected_at": recent(1)})
    with pytest.raises(DeferredProcessing, match="without verified date"):
        process_clinicas_chile(news, {})


def test_prestadores_baseline_then_only_new_bulletins(tmp_path, monkeypatch):
    from radar_salud.beta_sources import PrestadoresDailyScout, process_prestadores_bulletin

    class Listing:
        def __init__(self, urls):
            self.urls = urls

        def discover(self):
            return [RawItem("prestadores_data", f"Boletín Estadístico de Acreditación N°{i}-2026", url,
                            "Superintendencia de Salud · Intendencia de Prestadores", "official",
                            metadata={"data_family": "acreditación", "data_period": "2026"})
                    for i, url in enumerate(self.urls, 1)]
    base = "https://www.superdesalud.gob.cl/app/uploads/2026/"
    first = PrestadoresDailyScout(root=tmp_path, scout=Listing([base + "a.pdf", base + "b.pdf"]), enabled=True)
    assert first.discover() == [] and first.surface_results[0]["status"] == "baseline_established"
    later = PrestadoresDailyScout(root=tmp_path, scout=Listing([base + "a.pdf", base + "b.pdf", base + "c.pdf"]), enabled=True)
    fresh = later.discover()
    assert [raw.url for raw in fresh] == [base + "c.pdf"]
    monkeypatch.setenv("RADAR_DAILY_WINDOW_DAYS", "30")
    monkeypatch.setattr("radar_salud.document_intelligence.extract_pdf_text",
                        lambda *a, **k: "Intendencia de Prestadores de Salud. Boletín estadístico. " * 10)
    raw = fresh[0]
    raw.metadata["first_detected_at"] = recent(0)
    cfg = source_index(load_sources(Path("config/sources.json")))["prestadores_data"]
    row = process_prestadores_bulletin(raw, cfg)
    assert row["date_basis"] == "first_detected" and row["publication_date"] is None
    assert row["signal_types"] == ["Datos"] and "no informa fecha de publicación" in row["why_it_matters"]
    from radar_salud.editorial_gate import publication_ready
    assert publication_ready(row)[0]
