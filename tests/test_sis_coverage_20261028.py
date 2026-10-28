"""SIS coverage fixes (Director's report 28-oct-2026: Circular IF/N°534 suspension, sparse SIS stats/sanctions)."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_salud import regulatory
from radar_salud.daily_window import item_date, lagged_publication_date
from radar_salud.extraction import extract_superintendencia_detail
from radar_salud.history import merge_history
from radar_salud.isapre_pulse import _official_releases, RELEASE_URLS
from radar_salud.models import RawItem
from radar_salud.normative_minimal import act_scope, minimal_card
from radar_salud.normative_relations import apply_backlinks, extract_relations, is_general_relation
from radar_salud.pending_queue import PendingQueue, fingerprint, legacy_fingerprint
from radar_salud.regulatory_pipeline import apply_official_relations
from radar_salud.scouts import SuperintendenciaStatsScout, rolling_statistic

FIX = Path(__file__).parent / "fixtures" / "sis"


def _listing(name):
    return (FIX / name).read_text(encoding="utf-8")


# --- Normative relations (resolutions acting on circulars) ---------------------------------

@pytest.mark.parametrize("subject,relation,target", [
    ("Suspende los efectos de la Circular IF/N°529, de 10 de julio de 2026, hasta resolver los recursos de reposición.",
     "suspende", "Circular IF/N°529"),
    ("Rechaza la solicitud de Isapre Esencial S.A. de suspender los efectos de la Circular IF/N°532, de 31 de julio de 2026.",
     "rechaza_suspension", "Circular IF/N°532"),
    ("Acoge parcialmente los recursos de reposición interpuestos por las ISAPRES Banmédica S.A., en contra de la Circular IF/Nº528, de 26 de mayo de 2026.",
     "modifica_por_recurso", "Circular IF/N°528"),
    ("Rechaza recursos de reposición contra la Circular IF/N°531", "confirma", "Circular IF/N°531"),
    ("Acoge la suspensión de la Circular IF/N°521 para tres Isapres mientras se resuelven los recursos", "suspende", "Circular IF/N°521"),
    ("Rechaza solicitudes de suspensión de la Circular IF/N°513 y resuelve recursos de reposición de tres Isapres",
     "rechaza_suspension", "Circular IF/N°513"),
    ("Rechaza recursos contra el Oficio Circular IF/N°20 y lo confirma íntegramente", "confirma", "Oficio Circular IF/N°20"),
])
def test_relation_read_from_official_subject(subject, relation, target):
    rels = extract_relations(subject, "Resolución Exenta IF/N°1")
    assert [(r["relation"], r["target_id"]) for r in rels] == [(relation, target)]
    assert rels[0]["evidence"] and rels[0]["basis"] == "official_listing_subject"


def test_no_relation_without_a_named_instruction_or_for_particular_acts():
    assert extract_relations("Modifica instrucciones sobre hospitalización domiciliaria CAEC.", "Circular IF/N°536") == []
    assert extract_relations("Acoge parcialmente un recurso de reposición de Nueva Masvida contra el Oficio Ord. IF/N°27.377") == []
    # A circular never relates to itself.
    assert extract_relations("Modifica la Circular IF/N°534", "Circular IF/N°534") == []


def test_listing_resolution_suspending_534_is_discovered_and_general(monkeypatch):
    html = _listing("aseguradoras_resoluciones_20261028.html")
    monkeypatch.setattr(regulatory, "fetch_html", lambda url: html)
    scout = regulatory.SuperintendenciaNormativaScout()
    monkeypatch.setattr(scout, "PAGES", [("Para ISAPREs y FONASA", "https://www.superdesalud.gob.cl/x/", "Isapres / Fonasa")])
    items = scout.discover()
    suspension = next(i for i in items if i.title == "Resolución Exenta IF/N°99999")
    assert suspension.event_date == "2026-10-27"
    row = {"title": suspension.title, "official_subject": suspension.raw_text,
           "related_reference_ids": ["Circular IF/N° 534, de 14 de septiembre de 2026", "Ley N°19.880"],
           "related_reference_contexts": [{"id": "Circular IF/N° 534, de 14 de septiembre de 2026",
                                           "relationship": "Antecedente normativo citado por el documento actual."}]}
    apply_official_relations(row, suspension.raw_text, suspension.title)
    assert row["normative_act_relation"] == "suspende"
    ctx = row["related_reference_contexts"][0]
    assert "suspende transitoriamente" in ctx["relationship"] and "Circular IF/N°534" in ctx["relationship"]
    assert len(row["related_reference_ids"]) == 2  # target matched, not duplicated
    label = "Resolución Exenta IF/N°99999"
    assert is_general_relation(suspension.raw_text, label)
    sis = {"source_name": "Superintendencia de Salud", "source_url": suspension.url, "event_date": suspension.event_date,
           "official_subject": suspension.raw_text, "title": label, "official_listing_scope": "Isapres / Fonasa"}
    assert act_scope(sis, label) == "general"  # previously "unknown" -> held, never shown
    card = minimal_card(sis, label)
    assert card and card["normative_relations"][0]["target_id"] == "Circular IF/N°534"


def test_target_circular_shows_its_suspension_and_older_history_counts():
    circular = {"title": "Circular IF/N°534", "source_url": "https://www.superdesalud.gob.cl/normativa/circular-if-n534/",
                "event_date": "2026-09-14"}
    suspension = {"title": "Resolución Exenta IF/N°99999", "event_date": "2026-10-27",
                  "source_url": "https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n99999/",
                  "official_subject": "Suspende transitoriamente los efectos de la Circular IF/N°534, de 14 de septiembre de 2026."}
    legacy = {"title": "Resolución Exenta IF/N°9994", "event_date": "2026-08-26",
              "source_url": "https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n9994/",
              "official_subject": "Rechaza la solicitud de Esencial de suspender la Circular IF/N°532"}
    c532 = {"title": "Circular IF/N°532", "source_url": "https://www.superdesalud.gob.cl/normativa/circular-if-n532/"}
    out = {r["title"]: r for r in apply_backlinks([circular, suspension, legacy, c532])}
    assert out["Circular IF/N°534"]["normative_status"] == "Suspendida transitoriamente"
    assert out["Circular IF/N°534"]["normative_status_events"][0]["by"] == "Resolución Exenta IF/N°99999"
    assert out["Circular IF/N°532"]["normative_status"] == "Vigente: suspensión rechazada"
    assert "normative_status" not in out["Resolución Exenta IF/N°9994"]
    assert circular.get("normative_status") is None  # inputs untouched


# --- Fiscalization: sanctions listed weeks after emission ---------------------------------

def _qualis(publication="2026-10-13", emission="2026-09-23", conflicts=()):
    return {"source": "superintendencia_fiscalizacion", "status": "pending", "lane": "BACKFILL",
            "detected_at": "2026-10-25T19:38:46+00:00", "attempts": 0, "reason": None,
            "raw": {"source_slug": "superintendencia_fiscalizacion", "title": "Resolución Exenta IP/N°7464",
                    "url": "https://www.superdesalud.gob.cl/fiscalizacion/resolucion-exenta-ip-n7464",
                    "source_name": "Superintendencia de Salud", "source_type": "official", "event_date": emission,
                    "raw_text": "Sancionase a la Entidad Qualis SpA con una multa de 20 Unidades de Fomento",
                    "metadata": {"publication_date": publication, "emission_date": emission,
                                 "date_conflicts": list(conflicts), "regulated_entity": "Qualis SpA"}}}


def test_lagged_listing_uses_publication_day_for_the_window():
    assert item_date(_qualis()).isoformat() == "2026-10-13"
    # Bulk re-dating of 2024 reports on 20-oct-2026 is not news.
    assert lagged_publication_date(_qualis(publication="2026-10-20", emission="2024-12-09")["raw"]) is None
    assert lagged_publication_date(_qualis(conflicts=["publication_precedes_emission"])["raw"]) is None
    assert lagged_publication_date(dict(_qualis()["raw"], source_slug="minsal")) is None


def test_lagged_sanction_not_archived_and_reopened_on_rediscovery(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_DAILY_WINDOW_DAYS", "30")
    now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
    q = PendingQueue(tmp_path / "q.json")
    item = _qualis()
    raw = RawItem(**item["raw"])
    key = fingerprint(raw)
    q.items[key] = item
    assert q.archive_outside_daily_window(30, now=now) == 0
    # The stock archived before this fix is reopened when the listing is rediscovered.
    item.update(status="archived", reason="outside_daily_window_30d")
    q.discover("superintendencia_fiscalizacion", [raw], now=now)
    assert q.items[key]["status"] == "pending"
    assert q.items[key]["rediscovery_repairs"][-1]["reason"] == "listing_publication_inside_daily_window"


# --- Statistics: listing date and rolling releases ----------------------------------------

def test_stats_listing_dates_and_rolling_releases():
    items = SuperintendenciaStatsScout().discover_from_html(_listing("estadisticas_listing_20261028.html"))
    by = {i.url.rsplit("/", 2)[-2]: i for i in items}
    assert len(items) == 6
    ges = by["estadistica-trimestral-de-casos-ges-auge-de-fonasa-y-sistema-isapre-a-junio-2026"]
    assert ges.event_date == "2026-10-14" and "release_key" not in ges.metadata
    cartera = by["estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026"]
    assert cartera.event_date == "2026-10-02" and cartera.metadata["release_key"] == "2026-10-02"
    assert "release_key" not in by["estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-a-nivel-regional-agosto-2026"].metadata
    assert by["estadistica-anual-de-egresos-hospitalarios-del-sistema-isapre-ano-2025"].event_date == "2026-06-08"


def test_stats_stacked_listing_keeps_dates_per_row():
    items = SuperintendenciaStatsScout().discover_from_html(_listing("estadisticas_listing_stacked_20261028.html"))
    assert [i.event_date for i in items] == ["2026-10-02", None]


def test_rolling_release_gets_new_identity_but_other_items_keep_theirs():
    assert rolling_statistic("Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE – año 2026")
    assert rolling_statistic("Estadística Mensual de Movilidad de Cartera de Cotizantes del Sistema ISAPRE a Nivel Regional, Año 2026")
    assert not rolling_statistic("Estadística Anual de Egresos Hospitalarios del Sistema ISAPRE año 2025")
    assert not rolling_statistic("Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE a Nivel Regional – Agosto 2026")
    items = SuperintendenciaStatsScout().discover_from_html(_listing("estadisticas_listing_20261028.html"))
    for raw in items:
        if raw.metadata.get("release_key"):
            assert fingerprint(raw) != legacy_fingerprint(raw)
        else:
            assert fingerprint(raw) == legacy_fingerprint(raw)  # no mass re-enqueue of old stock


def test_detail_page_date_does_not_hide_a_newer_listing_release():
    raw = RawItem("superintendencia_salud", "Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE – año 2026",
                  "https://www.superdesalud.gob.cl/biblioteca-digital/x/", "Superintendencia de Salud", "official",
                  event_date="2026-10-02", metadata={"listing_publication_date": "2026-10-02", "release_key": "2026-10-02"})
    html = "<html><h1>Cartera</h1><p>Fecha de publicación: 7 de septiembre de 2026</p></html>"
    out = extract_superintendencia_detail(raw, html)
    assert out.event_date == "2026-10-02"
    assert out.metadata["detail_publication_date"] in ("2026-09-07", None)
    assert out.metadata["event_date_basis"] == "listing_publication"


def test_history_keeps_every_release_of_a_rolling_series():
    url = RELEASE_URLS["cartera"]
    old = {"source_url": url, "signal_types": ["Datos"], "event_date": "2026-09-07"}
    new = {"source_url": url, "signal_types": ["Datos"], "event_date": "2026-10-02", "release_key": "2026-10-02"}
    assert len(merge_history([old], [new])) == 2
    assert len(merge_history([old], [dict(old)])) == 1


def test_isapre_pulse_binds_to_the_release_it_validated():
    def rel(family, day):
        return {"title": {"cartera": "Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE – año 2026",
                          "suscripciones": "Estadística Mensual de Suscripciones y Desahucios del Sistema ISAPRE – año 2026",
                          "movilidad": "Estadística Mensual de Movilidad de Cartera de Cotizantes del Sistema ISAPRE a Nivel Regional – año 2026"}[family],
                "source_name": "Superintendencia de Salud", "source_type": "official",
                "source_url": RELEASE_URLS[family], "event_date": day}
    releases = [rel(f, "2026-09-07") for f in RELEASE_URLS] + [rel(f, "2026-10-02") for f in RELEASE_URLS]
    from datetime import date
    assert {x["event_date"] for x in _official_releases(releases, not_after=date(2026, 9, 20)).values()} == {"2026-09-07"}
    assert {x["event_date"] for x in _official_releases(releases).values()} == {"2026-10-02"}
