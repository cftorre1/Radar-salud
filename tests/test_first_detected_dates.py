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


def item(url="https://www.clinicasdechile.cl/documento", detected="2026-10-25T21:17:56+00:00", slug="clinicas_chile", **meta):
    return RawItem(slug, "Titular de prueba suficientemente largo", url, "Fuente", "corporate",
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
        apply_first_detected(RawItem("clinicas_chile", "t", "https://www.clinicasdechile.cl/x", "C", "corporate"), today=TODAY)


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


def test_undated_bupa_article_publishes_with_detection_label(monkeypatch, tmp_path):
    from radar_salud.date_basis import ensure_first_detection_baseline
    monkeypatch.setattr("radar_salud.paths.project_root", lambda: tmp_path)
    assert ensure_first_detection_baseline(tmp_path, "bupa_chile", ["https://www.bupa.cl/sala-de-prensa/antigua"])
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


def test_prestadores_baseline_covers_whole_listing_then_only_new_bulletins(tmp_path, monkeypatch):
    from radar_salud.beta_sources import PrestadoresDailyScout, process_prestadores_bulletin
    page = "https://www.superdesalud.gob.cl/tax-observatorio-de-calidad-en-salud/boletines-estadisticos-7994/"

    def listing(*names):
        return "".join(f'<a href="/app/uploads/{n}.pdf">{t}</a>' for n, t in names)
    old = [("2019-acred", "Boletín Estadístico de Acreditación 2019")] + [
        (f"2026-{i}", f"Boletín Estadístico de Acreditación N°{i}-2026") for i in range(1, 15)]
    first = PrestadoresDailyScout(root=tmp_path, enabled=True, fetch=lambda url: listing(*old))
    assert first.discover() == [] and first.surface_results[0]["baseline_items"] == 15
    import json
    baseline = json.loads((tmp_path / "data/state/prestadores_data_baseline.json").read_text())["urls"]
    assert any("2019-acred" in u for u in baseline) and any("2026-14" in u for u in baseline)  # beyond out[:12]
    fresh_name = ("2026-15", "Boletín Estadístico de Mediación N°15-2026")
    later = PrestadoresDailyScout(root=tmp_path, enabled=True, fetch=lambda url: listing(fresh_name, *old))
    fresh = later.discover()
    assert [raw.url for raw in fresh] == ["https://www.superdesalud.gob.cl/app/uploads/2026-15.pdf"]
    monkeypatch.setenv("RADAR_DAILY_WINDOW_DAYS", "30")
    monkeypatch.setattr("radar_salud.beta_sources.download_prestadores_pdf", lambda url: b"%PDF-1.4 fixture")
    # Header line carries the issuer: the unfiltered extractor keeps it.
    monkeypatch.setattr("radar_salud.beta_sources.prestadores_pdf_text",
                        lambda data: "Intendencia de Prestadores · Superintendencia de Salud\n" + "Boletín estadístico. " * 20)
    raw = fresh[0]
    raw.metadata["first_detected_at"] = recent(0)
    cfg = source_index(load_sources(Path("config/sources.json")))["prestadores_data"]
    row = process_prestadores_bulletin(raw, cfg)
    assert row["date_basis"] == "first_detected" and row["publication_date"] is None
    assert row["signal_types"] == ["Datos"] and "no informa fecha de publicación" in row["why_it_matters"]
    from radar_salud.editorial_gate import publication_ready
    assert publication_ready(row)[0]


def test_prestadores_download_is_bounded_and_host_restricted():
    from radar_salud.beta_sources import download_prestadores_pdf
    with pytest.raises(ValueError, match="official"):
        download_prestadores_pdf("https://evil.example/boletin.pdf")
    with pytest.raises(ValueError, match="official"):
        download_prestadores_pdf("http://www.superdesalud.gob.cl/boletin.pdf")


def test_first_detection_is_capped_at_30_days_when_window_env_is_unset(monkeypatch):
    from radar_salud.date_basis import FIRST_DETECTED_MAX_DAYS
    monkeypatch.delenv("RADAR_DAILY_WINDOW_DAYS", raising=False)  # default window is 90
    assert FIRST_DETECTED_MAX_DAYS == 30
    with pytest.raises(RejectedProcessing, match="outside_daily_window"):
        apply_first_detected(item(detected="2026-09-20T12:00:00+00:00"), today=TODAY)
    with pytest.raises(RejectedProcessing):
        apply_first_detected(item(detected="2026-09-20T12:00:00+00:00"), today=TODAY, window_days=90)
    assert apply_first_detected(item(detected="2026-10-20T12:00:00+00:00"), today=TODAY) == "2026-10-20"


def test_story_groups_carry_date_basis_and_never_borrow_publication_date():
    from radar_salud.story_groups import apply_story_groups, _alt
    detected = {"title": "Memoria", "source_name": "Clínicas de Chile A.G.", "source_url": "https://a.cl/1",
                "event_date": "2026-10-20", "date_basis": "first_detected", "first_detected_at": "2026-10-20T12:00:00+00:00"}
    dated = {"title": "Nota", "source_name": "DF", "source_url": "https://a.cl/2", "event_date": "2026-10-19"}
    assert _alt(detected)["date_basis"] == "first_detected" and "date_basis" not in _alt(dated)
    groups = [{"id": "g", "mode": "summary", "member_urls": ["https://a.cl/1", "https://a.cl/2"],
               "card": {"title": "Síntesis", "what_happened": "x", "why_it_matters": "y"}}]
    _, summaries = apply_story_groups([detected, dated], groups)
    card = summaries[0]
    assert card["publication_date"] is None and card["date_basis"] == "first_detected"
    assert card["source_alternatives"][0]["first_detected_at"] == "2026-10-20T12:00:00+00:00"


def test_bupa_requires_baseline_and_never_publishes_baseline_items_by_detection(monkeypatch, tmp_path):
    from radar_salud.date_basis import ensure_first_detection_baseline
    monkeypatch.setattr("radar_salud.paths.project_root", lambda: tmp_path)
    raw = item(url="https://www.bupa.cl/sala-de-prensa/nota", slug="bupa_chile")
    with pytest.raises(DeferredProcessing, match="baseline_not_established"):
        apply_first_detected(raw, today=TODAY, window_days=30)
    assert ensure_first_detection_baseline(tmp_path, "bupa_chile", [raw.url, raw.url])
    assert not ensure_first_detection_baseline(tmp_path, "bupa_chile", ["https://www.bupa.cl/otra"])  # created once
    with pytest.raises(RejectedProcessing, match="baseline_existing_item"):
        apply_first_detected(raw, today=TODAY, window_days=30)
    new = item(url="https://www.bupa.cl/sala-de-prensa/nueva", detected="2026-10-26T12:00:00+00:00", slug="bupa_chile")
    assert apply_first_detected(new, today=TODAY, window_days=30) == "2026-10-26"


def test_prestadores_off_host_or_non_pdf_defers_not_rejects(monkeypatch):
    from radar_salud.beta_sources import process_prestadores_bulletin
    def bad(url):
        raise ValueError("Prestadores redirect left the official HTTPS host")
    monkeypatch.setattr("radar_salud.beta_sources.download_prestadores_pdf", bad)
    raw = RawItem("prestadores_data", "Boletín N°3-2026", "https://www.superdesalud.gob.cl/app/uploads/b.pdf",
                  "Superintendencia de Salud · Intendencia de Prestadores", "official", metadata={"first_detected_at": recent(0)})
    with pytest.raises(DeferredProcessing, match="unavailable"):
        process_prestadores_bulletin(raw, {"slug": "prestadores_data"})


def test_date_basis_keys_include_release_scope():
    from radar_salud.story_groups import _alt
    alt = _alt({"source_url": "https://datos.gob.cl/dataset/x#liberacion-2026-10", "date_basis": "data_release",
                "data_release_date": "2026-10-07", "data_release_scope": "catalog"})
    assert alt["data_release_scope"] == "catalog"
