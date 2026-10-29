"""Dirección 28-oct-2026 17:08: "Avanza con FNE y Congreso".

FNE (health mergers and competition) and Congreso (health bills, tramitación
milestones) as deterministic daily sources that feed the Chile radar through
the editorial gate and the paywall corroboration matcher.

Offline: fixtures under tests/fixtures/fne and tests/fixtures/congreso (see
their provenance comments; the 'synthetic' XML is labelled as such).
"""
import json
import socket
from datetime import date
from pathlib import Path

import pytest

from radar_salud import congreso_sources as cg
from radar_salud import fne_sources as fne
from radar_salud import paywall_corroboration as pc

FIX = Path(__file__).parent / "fixtures"
FNE_CFG = {"slug": fne.SLUG, "name": fne.SOURCE_NAME, "base_confidence": 100, "default_category": "Mercado",
           "force_category": True}
CG_CFG = {"slug": cg.SLUG, "name": cg.SOURCE_NAME, "base_confidence": 100, "default_category": "Regulación & Legal",
          "force_category": True}
REG = pc.Registry(pc.load_registry(Path(".")))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network access in an FNE/Congreso test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def html(name):
    return (FIX / "fne" / name).read_text(encoding="utf-8")


# --- FNE ---------------------------------------------------------------------------

def test_fne_listing_parses_real_rows_and_skips_navigation():
    rows = fne.parse_listing(html("noticias_2_page1_20261028.html"))
    assert len(rows) == 6
    assert rows[0] == {"title": "FNE participó en feria laboral de Derecho de la Universidad Diego Portales",
                       "url": "https://www.fne.gob.cl/fne-participo-en-feria-laboral-de-derecho-de-la-universidad-diego-portales-2/",
                       "date": "2026-10-28"}
    assert [r["date"] for r in fne.parse_listing(html("noticias_2_page2_20261028.html"))][-1] == "2026-10-06"
    assert all(fne.post_url(r["url"]) for r in rows)
    assert not fne.post_url("https://www.fne.gob.cl/fusiones/buscador/")
    assert not fne.post_url("https://evil.example/fne-aprueba/")


def test_fne_real_week_has_no_health_case_and_drops_agenda_noise():
    audit = []
    for name in ("noticias_2_page1_20261028.html", "noticias_2_page2_20261028.html"):
        items = fne.items_from_rows(fne.parse_listing(html(name)), listing=fne.LISTING, today=date(2026, 10, 28),
                                    window_days=30, report=audit)
        assert items == []
    reasons = {a["url"].split("/")[3]: a["reason"] for a in audit}
    assert reasons["fne-participo-en-taller-de-apec-sobre-libre-competencia"] == "institutional_agenda"
    assert reasons["fne-dicto-charla-para-estudiantes-de-la-universidad-catolica"] == "institutional_agenda"
    # real merger approvals outside health (energy, convenience stores, hotels) never enter
    assert reasons["fne-aprueba-adquisicion-de-seis-tiendas-de-conveniencia-ahorra-food-depot-por-parte-de-smu"] == "not_health_sector"
    assert sum(r == "not_health_sector" for r in reasons.values()) == 5


def test_fne_health_cases_carry_stage_and_parties():
    rows = fne.parse_listing(html("health_rows_20261028.html"))
    audit = []
    items = fne.items_from_rows(rows, listing=fne.LISTING, today=date(2026, 9, 28), window_days=10, report=audit)
    assert [a["reason"] for a in audit] == ["accepted", "outside_window"]
    (item,) = items
    assert item.metadata["case_stage"] == "aprobada" and item.event_date == "2026-09-23"
    assert item.metadata["parties"] == [{"role": "target", "name": "Rotter & Krauss"},
                                        {"role": "acquirer", "name": "Salcobrand"}]
    saval = fne.parties(rows[1]["title"])
    assert fne.classify(rows[1]["title"]) == ("merger", "en_analisis_fase_2")
    assert {p["name"] for p in saval} == {"Instituto Sanitas y Chemopharma", "Laboratorios Saval"}


@pytest.mark.parametrize("title,expected", [
    ("FNE prohíbe la adquisición de Clínica X por parte de Red Y", ("merger", "prohibida")),
    ("FNE aprueba con condiciones fusión entre Laboratorio A y Laboratorio B", ("merger", "aprobada_con_condiciones")),
    ("FNE inicia investigación por adquisición de control en Hospital Clínico Viña del Mar por parte de Red Interclínica",
     ("merger", "en_analisis_fase_1")),
    ("FNE recomienda al TDLC revisar el valor del seguro laboral obligatorio que cobran las mutualidades para proteger la libre competencia",
     ("advocacy", "recomendacion")),
    ("FNE pide al TDLC sancionar por colusión a laboratorios", ("conduct", "requerimiento")),
    ("FNE se reunió con directiva de la CPC", ("noise", "institutional_agenda")),
])
def test_fne_title_classification(title, expected):
    assert fne.classify(title) == expected


def test_fne_scout_honours_robots_and_lane(monkeypatch):
    pages = {fne.listing_url(1): html("noticias_2_page1_20261028.html").encode(),
             fne.listing_url(2): html("noticias_2_page2_20261028.html").encode()}
    calls = []

    def fetch(url):
        calls.append(url)
        return pages[url], {"sha256": "x", "charset": "utf-8"}

    scout = fne.FneScout(fetch_fn=fetch, today=date(2026, 10, 28), window_days=10, enabled=True,
                         robots=lambda url: True)
    assert scout.discover() == []
    assert calls == [fne.listing_url(1), fne.listing_url(2)]  # page 2 reaches past the window
    assert scout.diagnostics["window_complete"] is True and len(scout.discovery_audit) == 12
    blocked = fne.FneScout(fetch_fn=fetch, today=date(2026, 10, 28), enabled=True, robots=lambda url: False)
    with pytest.raises(RuntimeError, match="robots_disallowed"):
        blocked.discover()
    monkeypatch.delenv("RADAR_FNE", raising=False)
    assert fne.FneScout().discover() == []  # pytest never runs the network lane
    assert fne.live_lane_enabled({"RADAR_FNE": "0", "RADAR_CAPTURE_EVIDENCE": "1"}) is False


def _salcobrand():
    rows = fne.parse_listing(html("health_rows_20261028.html"))
    return fne.items_from_rows(rows, listing=fne.LISTING, today=date(2026, 9, 28), window_days=10)[0]


def test_fne_card_is_deterministic_and_passes_gate():
    row = fne.process_fne(_salcobrand(), FNE_CFG)
    assert row["what_happened"].startswith("La FNE aprobó una operación de concentración: «FNE aprueba adquisición")
    assert "Partes: Rotter & Krauss; Salcobrand." in row["what_happened"]
    assert row["signal_types"] == ["Mercado"] and row["deterministic_processing"] is True
    assert row["terms_policy"] == "title_date_link_only" and row["publication_ready_score"] >= 62


def test_fne_card_rejects_noise_and_unverified_evidence():
    from radar_salud.processing import DeferredProcessing, RejectedProcessing
    raw = _salcobrand()
    raw.metadata["publication_date_evidence"] = {**raw.metadata["publication_date_evidence"], "date": "2026-09-24"}
    with pytest.raises(DeferredProcessing):
        fne.process_fne(raw, FNE_CFG)
    raw = _salcobrand()
    raw.title = "FNE participó en seminario sobre farmacias"
    with pytest.raises(RejectedProcessing, match="institutional_agenda"):
        fne.process_fne(raw, FNE_CFG)


# --- Congreso ----------------------------------------------------------------------

def xml(name):
    return (FIX / "congreso" / name).read_bytes()


def test_senado_service_xml_real_structure():
    (bill,) = cg.parse_tramitacion(xml("tramitacion_boletin_18623_20261028.xml"))
    assert bill["boletin"] == "18623-07" and bill["camara_origen"] == "Senado"
    assert len(bill["tramites"]) == 9
    kinds = [cg.milestone(t["descripcion"]) for t in bill["tramites"]]
    # real 18623 history: one ingreso, two committee reports, seven 'cuenta'/urgencia rows dropped
    assert kinds == ["ingreso", None, None, None, None, None, None, "informe_comision", "informe_comision"]
    assert cg.committee(bill["tramites"][7]["descripcion"]) == "Constitución, Legislación, Justicia y Reglamento"
    assert not cg.health_scope(bill)  # data-protection bill: out of scope


def test_senado_rejects_unexpected_structures():
    with pytest.raises(ValueError):
        cg.parse_tramitacion(b"<html><body>error</body></html>")
    with pytest.raises(ValueError):
        cg.parse_tramitacion(b'<!DOCTYPE x [<!ENTITY a "b">]><proyectos/>')


def test_health_milestones_only_status_changes():
    bills = cg.parse_tramitacion(xml("tramitacion_fecha_synthetic.xml"))
    audit = []
    items = cg.items_from_bills(bills, api_url=cg.query_url(date(2026, 9, 21)), since=date(2026, 9, 21),
                                today=date(2026, 10, 28), report=audit)
    by = {a["boletin"]: a for a in audit}
    assert by["18623-07"]["reason"] == by["99902-06"]["reason"] == "not_health"  # datos personales; licencias de conducir
    assert by["18255-31"]["procedural_dropped"] == 3  # cuenta, urgencia, citación
    got = [(i.metadata["bill"]["boletin"], i.metadata["milestone"], i.event_date) for i in items]
    assert got == [("18255-31", "informe_comision", "2026-09-22"),
                   ("18255-31", "aprobacion_general_particular", "2026-09-29"),
                   ("18255-31", "despacho", "2026-09-29"),
                   ("99901-11", "ingreso", "2026-10-20"),
                   ("99901-11", "informe_comision", "2026-10-27"),
                   ("99901-11", "aprobacion_general", "2026-10-28")]
    assert len({i.url for i in items}) == len(items)
    assert items[4].metadata["committee"] == "Salud"


def _bill_items():
    bills = cg.parse_tramitacion(xml("tramitacion_fecha_synthetic.xml"))
    return cg.items_from_bills(bills, api_url=cg.query_url(date(2026, 9, 21)), since=date(2026, 9, 21),
                               today=date(2026, 10, 28))


def test_bill_card_is_deterministic_and_passes_gate():
    row = cg.process_congreso(_bill_items()[4], CG_CFG)
    assert row["what_happened"].startswith("La comisión de Salud emitió informe sobre el proyecto «Modifica el DFL N° 1")
    assert "(Boletín N° 99901-11) el 27-10-2026, en el Senado." in row["what_happened"]
    assert row["signal_types"] == ["Legal"] and row["bill_milestone"] == "informe_comision"
    assert "aún no es ley vigente" in row["why_it_matters"]
    assert row["primary_source_url"].endswith("boletin_ini=99901-11")


def test_bill_card_rejects_tampered_milestone():
    from radar_salud.processing import DeferredProcessing, RejectedProcessing
    raw = _bill_items()[0]
    raw.metadata["tramite"] = {**raw.metadata["tramite"], "descripcion": "Cuenta del Mensaje 1-374 que hace presente la urgencia Suma"}
    with pytest.raises(RejectedProcessing, match="procedural_noise"):
        cg.process_congreso(raw, CG_CFG)
    raw = _bill_items()[0]
    raw.event_date = "2026-09-23"
    with pytest.raises(DeferredProcessing):
        cg.process_congreso(raw, CG_CFG)


def test_congreso_scout_window_robots_and_lane(monkeypatch):
    seen = []

    def fetch(url):
        seen.append(url)
        return xml("tramitacion_fecha_synthetic.xml"), {"sha256": "y"}

    scout = cg.CongresoScout(fetch_fn=fetch, today=date(2026, 10, 28), window_days=60, enabled=True,
                             robots=lambda url: True)
    items = scout.discover()
    assert seen == ["https://tramitacion.senado.cl/wspublico/tramitacion.php?fecha=28%2F09%2F2026"]  # capped at 30 days
    assert {i.metadata["bill"]["boletin"] for i in items} == {"18255-31", "99901-11"}
    with pytest.raises(PermissionError):
        cg.CongresoScout(fetch_fn=fetch, today=date(2026, 10, 28), enabled=True, robots=lambda url: False).discover()
    monkeypatch.delenv("RADAR_CONGRESO", raising=False)
    assert cg.CongresoScout().discover() == []


# --- corroboration -------------------------------------------------------------------

def _index(rows):
    docs = pc.build_corpus(Path("."), REG, signal_sets=[rows], queue={})
    docs = [d for d in docs if d.origin != "data/market/cmf_events.json"]
    return pc.CorpusIndex(docs, REG, fingerprints=set())


def _df(title, day, url="https://www.df.cl/empresas/salud/x"):
    return {"title": title, "teaser": "", "date": date.fromisoformat(day), "url": url, "paywall_name": "Diario Financiero"}


def test_fne_case_corroborates_on_merging_parties():
    row = fne.process_fne(_salcobrand(), FNE_CFG)
    block = pc.corroborate(_df("FNE da luz verde para la compra de las ópticas Rotter & Krauss por parte de Salcobrand",
                               "2026-09-23"), _index([row]))
    assert block["status"] == "corroborated"
    rel = block["related_sources"][0]
    assert rel["url"] == row["source_url"]
    assert {"party:rotter & krauss", "party:salcobrand", "src:fne"} <= set(rel["matched_on"]["entities"])
    assert block["what"][0]["attribution"] == "la Fiscalía Nacional Económica (FNE)"


def test_fne_case_does_not_match_another_deal_of_the_same_buyer():
    raw = fne.items_from_rows([{"title": "Resolución de aprobación de adquisición de control en Hospital Clínico Viña del Mar S.A. por parte de Red Interclínica S.A.",
                                "url": "https://www.fne.gob.cl/resolucion-de-aprobacion-de-adquisicion-de-control-en-hospital-clinico-vina-del-mar-s-a-por-parte-de-red-interclinica-s-a/",
                                "date": "2026-05-06"}], listing=fne.LISTING, today=date(2026, 5, 7), window_days=5)[0]
    row = fne.process_fne(raw, FNE_CFG)
    block = pc.corroborate(_df("Excontroladores del Banco Internacional venden Clínica Puerto Varas a Red Interclínica",
                               "2026-04-30"), _index([row]))
    assert block["status"] == "none"


def test_bill_milestone_corroborates_on_title_terms_and_boletin():
    rows = [cg.process_congreso(i, CG_CFG) for i in _bill_items()]
    index = _index(rows)
    block = pc.corroborate(_df("Cámara Baja despacha al Senado proyecto del PDG que compensa la compra de medicamentos y pañales",
                               "2026-09-29"), index)
    assert block["status"] == "corroborated"
    assert block["related_sources"][0]["url"].endswith("18255-31#hito-despacho-2026-09-29")
    by_number = pc.corroborate(_df("Senado recibe proyecto de pañales y medicamentos, boletín 18.255-31", "2026-09-30"), index)
    assert by_number["related_sources"] and by_number["related_sources"][0]["matched_on"]["acts"] == ["boletin:18255"]
    other = pc.corroborate(_df("Senado aprueba proyecto de licencias de conducir", "2026-10-28"), index)
    assert other["status"] == "none"


def test_act_ids_conflict_only_within_the_same_kind():
    assert pc.act_ids("Boletín N° 18.255-31") == {"boletin:18255"} == pc.act_ids("boletín 18255")
    p = pc.features("La Ley 21.674 y el boletín 18255", REG)
    assert pc.conflicts(p, pc.features("Boletín N° 18255-31", REG)) == []
    assert "act_id" in pc.conflicts(pc.features("boletín 18300", REG), pc.features("Boletín N° 18255-31", REG))


# --- registry and inventory ------------------------------------------------------------

OPEN_PRESS = {"biobiochile", "cooperativa", "cnn_chile", "24horas_tvn", "t13", "el_mostrador", "ciper",
              "el_desconcierto", "regional_press"}


def test_registry_enables_fne_and_congreso_and_keeps_open_press_disabled():
    by = {s["id"]: s for s in REG.sources}
    for sid, slug in (("fne", fne.SLUG), ("congreso_tramitacion", cg.SLUG)):
        s = by[sid]
        assert s["status"] == "enabled" and s["mode"] == "corpus_only" and slug in s["source_slugs"]
        assert s["live_search"] is False and s["excerpt_allowed"] is False and s["evidence_urls"]
    assert REG.enabled_source("https://www.fne.gob.cl/fne-aprueba-x/")["id"] == "fne"
    assert REG.enabled_source(cg.bill_page("18255-31"))["id"] == "congreso_tramitacion"
    assert by["camara"]["status"] == "disabled_pending_verification"
    assert OPEN_PRESS <= set(by)
    for sid in OPEN_PRESS:
        s = by[sid]
        assert s["kind"] == "open_press" and s["status"] != "enabled"
        assert all(s.get(k) for k in ("status", "reason", "next_step", "reevaluate_after")), sid


def test_sources_catalog_and_freshness_policy_register_both():
    sources = {s["slug"]: s for s in json.loads(Path("config/sources.json").read_text(encoding="utf-8"))}
    assert sources[fne.SLUG]["cadence"] == sources[cg.SLUG]["cadence"] == "daily"
    policy = json.loads(Path("config/source_freshness_policy.json").read_text(encoding="utf-8"))
    assert {fne.SLUG, cg.SLUG} <= set(policy["activated_daily_2026_10_28"])
    from radar_salud import engine_cli
    assert {fne.SLUG, cg.SLUG} <= set(engine_cli.DETERMINISTIC_SOURCES) & set(engine_cli.PUBLIC_DATA_SOURCES)
    assert engine_cli.FneScout is fne.FneScout and engine_cli.CongresoScout is cg.CongresoScout


# --- review 28-oct-2026: loose health words and per-run cap -----------------------------

@pytest.mark.parametrize("title,health", [
    ("FNE aprueba adquisición de laboratorio clínico Bionet por parte de Achs", True),
    ("FNE investiga adquisición de Laboratorios Farmacéuticos Andinos", True),
    ("FNE publica estudio de mercado sobre medicamentos genéricos", True),
    ("FNE aprueba compra de centros de diagnóstico por imágenes", True),
    ("FNE aprueba adquisición de laboratorio de ensayos de materiales de construcción", False),
    ("FNE presenta diagnóstico del mercado del transporte interurbano", False),
    ("FNE investiga colusión en productos genéricos de limpieza", False),
])
def test_fne_loose_health_words_need_health_context(title, health):
    from radar_salud.official_open import HEALTH_TERMS, fold, health_basis
    assert bool(HEALTH_TERMS.search(fold(title).casefold())) is health
    assert bool(health_basis(title)) is health  # the editorial-gate nexus fallback does not reopen them


def test_fne_and_congreso_per_run_cap_is_configured_and_keeps_newest():
    from radar_salud.models import RawItem
    from radar_salud.official_open import cap_new_items
    cfg = {s["slug"]: s for s in json.loads(Path("config/sources.json").read_text(encoding="utf-8"))}
    for slug in (fne.SLUG, cg.SLUG):
        assert 1 <= cfg[slug]["max_new_items_per_run"] <= 10
    items = [RawItem(fne.SLUG, f"t{i}", f"https://www.fne.gob.cl/p{i}/", fne.SOURCE_NAME, "official",
                     event_date=f"2026-10-{i + 1:02d}", raw_text="") for i in range(14)]
    known = {items[0].url}
    kept, deferred = cap_new_items(items, known, 10, lambda r: r.url)
    assert items[0] in kept and len(kept) == 11 and len(deferred) == 3
    assert {r.event_date for r in deferred} == {"2026-10-02", "2026-10-03", "2026-10-04"}  # oldest wait


def test_engine_applies_the_cap_to_fne_and_congreso():
    from radar_salud import engine_cli
    assert set(engine_cli.NEW_ITEM_CAPPED_SOURCES) == {fne.SLUG, cg.SLUG}
    src = Path(engine_cli.__file__).read_text(encoding="utf-8")
    assert "cap_new_items(items,seen|set(queue.items),cap,fingerprint)" in src


def test_senado_registry_note_records_missing_licence():
    senado = next(s for s in REG.sources if s["id"] == "senado")
    assert "licencia" in senado["licence"].lower() and senado["status"] != "enabled"
