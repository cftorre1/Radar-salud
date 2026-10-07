import json
from pathlib import Path

from radar_salud.beta_sources import CuratedBetaSourceScout, PrestadoresDataScout, media_gate_accepts

ROOT=Path(__file__).resolve().parents[1]

def _json(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))

def test_all_required_beta_sources_have_gate_disposition():
    reviews=_json("config/source_quality_reviews_beta_2026_10_01.json")
    providers=reviews["provider_networks"]
    for key in ("red_davila","clinica_las_condes","clinicas_achs_salud","redsalud","andes_salud","interclinicas"):
        assert providers[key]["status"].startswith("pass_")
    for key in ("achs_seguro_laboral","mutual_seguridad","ist"):
        assert reviews["mutualities"][key]["status"]=="pass_active"
    for key in ("diario_financiero","pulso_latercera","el_mercurio_economia_negocios"):
        assert reviews["media"][key]["status"].startswith("pass_")
    assert reviews["fonasa_grd"]["status"]=="compensated_official_alternative"
    assert reviews["prestadores_data"]["status"]=="pass_data"
    assert reviews["epidemiology"]["status"]=="pass_existing"

def test_every_new_active_gate_source_is_in_beta_catalog():
    reviews=_json("config/source_quality_reviews_beta_2026_10_01.json")
    registered={x["slug"] for x in _json("config/beta_source_configs.json")}
    expected={"prestadores_data"}
    for section in ("provider_networks","mutualities","media"):
        for row in reviews[section].values():
            if row["status"]=="pass_active" and row.get("slug"):
                expected.add(row["slug"])
    assert expected<=registered

def test_media_early_signal_gate_has_lifecycle_and_noise_controls():
    gate=_json("config/media_early_signal_gate.json")
    assert gate["lifecycle"]==["media_reported","company_confirmed","official_confirmed"]
    assert "opinion/columns" in gate["excluded"]
    assert {"diario_financiero","pulso_latercera"}<=set(gate["trusted_sources"])
    assert media_gate_accepts("Clínica aumenta capital e invertirá en nueva capacidad")
    assert not media_gate_accepts("Columna de opinión sobre salud", "seminario y premio sin cambio de negocio")

def test_curated_scout_catalog_covers_required_integrations():
    expected={"red_davila","andes_salud","clinicas_achs_salud","achs_seguro_laboral","mutual_seguridad","ist","pulso_latercera"}
    assert expected<=set(CuratedBetaSourceScout.SOURCES)

def test_prestadores_data_discovers_current_2026_bulletins_without_fake_publication_date():
    html="""
    <a href="/app/uploads/2026/08/boletin-n2-2026-rnpi-enero-junio-2026.pdf">Boletin N°2-2026 RNPI enero- junio 2026</a>
    <a href="/app/uploads/2026/08/boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf">Boletín N°2-2026 Acreditación enero-junio 2026</a>
    <a href="/app/uploads/2026/08/boletin-n2-2026-mediacion-enero-junio-2026.pdf">Boletín N°2-2026 Mediación enero-junio 2026</a>
    <a href="/app/uploads/2026/08/boletin-n2-2026-reclamos-enero-junio-2026.pdf">Boletín N°2-2026 Reclamos enero-junio 2026</a>
    """
    rows=PrestadoresDataScout().discover_from_html(html)
    assert len(rows)==4
    assert {x.metadata["data_family"] for x in rows}=={"rnpi","acreditación","mediación","reclamos"}
    assert all(x.event_date is None for x in rows)

def test_fonasa_grd_compensation_is_official_and_explicit():
    row=_json("config/source_quality_reviews_beta_2026_10_01.json")["fonasa_grd"]
    assert row["blocker_is_external"] is True
    assert row["beta_decision"]=="covered"
    hosts=" ".join(x["url"] for x in row["compensation"])
    assert "minsal.cl" in hosts and "dipres.gob.cl" in hosts and "datosabiertos.fonasa.cl" in hosts


def test_compact_spanish_date_parser_used_by_provider_newsrooms():
    from radar_salud.public_source_pipeline import _date
    assert _date("11sept.2026")=="2026-09-11"
    assert _date("24ago.2026")=="2026-08-24"


def test_beta_source_surfaces_use_current_newsroom_routes():
    sources=CuratedBetaSourceScout.SOURCES
    assert sources["clinicas_achs_salud"]["page"]=="https://www.achs.cl/centro-de-noticias"
    assert sources["achs_seguro_laboral"]["page"]=="https://www.achs.cl/centro-de-noticias"
    assert sources["pulso_latercera"]["page"]=="https://www.latercera.com/canal/pulso/"
