"""Adversarial publisher fields, actor attribution and partial captures."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from radar_salud.occupational_sources import (
    Article, SourceDiscoveryError, discover_items, fetch_listing, market_role,
    materiality, valid_date, classify_content_kind,
)

TODAY = date(2026, 10, 11)
BASE = "https://www.achs.cl/centro-de-noticias/noticia/2026/"
GUIDE = "Nueva guía de tratamiento en salud mental laboral"
BODY = ("La nueva guía de tratamiento de patologías de salud mental laboral incorpora "
        "recomendaciones para evaluación, atención clínica y reintegro laboral. "
        "Se publica una revisión de evidencia para los equipos tratantes y empresas adherentes.")


def article_html(title=GUIDE, body=BODY, published="2026-09-24", *, field="meta"):
    publication = (f'<meta property="article:published_time" content="{published}">'
                   if field == "meta" else f'<div class="fecha">{published}</div>')
    return (publication if field == "meta" else "") + (
        f"<article><h1>{title}</h1>" + (publication if field != "meta" else "") + f"<p>{body}</p></article>")


def parse(html, url=BASE + "guia"):
    parser = Article(url=url)
    parser.feed(html)
    return parser


def scout(role="mutuality", *, accepted_roles=None):
    cfg = {"page": "https://www.achs.cl/centro-de-noticias", "hosts": ["www.achs.cl"],
           "path": r"/centro-de-noticias/noticia/2026/[^/]+", "role": role,
           "name": "Achs", "type": "institution_verified"}
    if accepted_roles:
        cfg["accepted_roles"] = accepted_roles
    return SimpleNamespace(slug="achs_seguro_laboral" if role == "mutuality" else "clinicas_achs_salud", cfg=cfg)


@pytest.mark.parametrize("value", [
    "publicado 2026-09-24", "2026-09-24 unrelated text", "update=2026-09-24",
    "31/02/2026", "2026-09-24T99:00:00Z", "2026-09-24T12:00:00Z trailing",
    "2026-10-12", "12/10/2026", "29/02/2025", "24/09-2026", "2026-09-24junk",
])
def test_publication_field_must_be_entire_valid_nonfuture_date(value):
    assert valid_date(value, today=TODAY) is None


@pytest.mark.parametrize("value,expected", [
    ("24/09/2026", "2026-09-24"), ("24-09-2026", "2026-09-24"),
    ("24 de septiembre de 2026", "2026-09-24"),
    ("2026-09-24T12:13:14.005-03:00", "2026-09-24"),
    ("2026-10-11", "2026-10-11"), ("29/02/2024", "2024-02-29"),
])
def test_calendar_and_explicit_audit_day(value, expected):
    assert valid_date(value, today=TODAY) == expected


def test_timezone_publication_instant_uses_chile_day_including_future_boundary():
    assert valid_date("2026-10-06T00:22:30Z", today=TODAY) == "2026-10-05"
    assert valid_date("2026-10-05T21:22:30-03:00", today=TODAY) == "2026-10-05"
    assert valid_date("2026-10-12T00:22:30Z", today=TODAY) == "2026-10-11"
    assert valid_date("2026-10-12T04:22:30Z", today=TODAY) is None


def test_local_and_utc_publication_fields_agree_on_chile_day():
    html = ('<meta property="article:published_time" content="2026-10-06T00:22:30Z">'
            f'<h1>{GUIDE}</h1><time class="published" datetime="2026-10-05T21:22:30-03:00"></time><p>{BODY}</p>')
    parser = parse(html)
    assert parser.result(today=TODAY)[1] == "2026-10-05"
    assert parser.publication_evidence(today=TODAY)["value"] == "2026-10-06T00:22:30Z"


@pytest.mark.parametrize("value,expected", [
    ("Oct 7, 2026", "2026-10-07"), ("October 7, 2026", "2026-10-07"),
    ("Ago 31, 2026", "2026-08-31"), ("Aug 31, 2026", "2026-08-31"),
    ("Jan 1, 2026", "2026-01-01"), ("Ene 1, 2026", "2026-01-01"),
    ("Apr 30, 2026", "2026-04-30"), ("Dec 31, 2025", "2025-12-31"),
    ("February 29, 2024", "2024-02-29"),
])
def test_captured_cms_month_first_publication_fields(value, expected):
    assert valid_date(value, today=TODAY) == expected


@pytest.mark.parametrize("value", [
    "Published Oct 7, 2026", "Oct 7, 2026 event", "Oct 7 2026", "Oct 7, 26",
    "Feb 29, 2025", "Ago 32, 2026", "Apr 31, 2026", "Oct 12, 2026",
    "Oct 7, 2026, 10:00", "October 7th, 2026", "Somemonth 7, 2026",
])
def test_month_first_field_stays_whole_calendar_valid_and_nonfuture(value):
    assert valid_date(value, today=TODAY) is None


def test_cms_publisher_date_agrees_with_iso_and_preserves_conflicting_days():
    meta = '<meta property="article:published_time" content="2026-10-06T00:22:30Z">'
    html = meta + f'<h1>{GUIDE}</h1><span class="published">Oct 5, 2026</span><p>{BODY}</p>'
    parser = parse(html, "https://ist.cl/noticia/")
    assert parser.result(today=TODAY)[1] == "2026-10-05"
    assert parser.publication_evidence(today=TODAY)["value"] == "2026-10-06T00:22:30Z"
    conflicting = parse(html.replace("Oct 5, 2026", "Oct 6, 2026"), "https://ist.cl/noticia/")
    assert conflicting.result(today=TODAY)[3] == "conflicting_publication_dates"
    assert conflicting.publication_evidence(today=TODAY) is None


def test_bare_month_first_event_is_not_publication_evidence():
    parser = parse(f'<h1>{GUIDE}</h1><p>Oct 7, 2026</p><p>{BODY}</p>', "https://ist.cl/noticia/")
    assert parser.result(today=TODAY)[3] == "missing_publication_date"


def test_live_ist_cms_semantic_date_matches_published_metadata():
    import hashlib
    import json
    root = Path(__file__).resolve().parents[1]
    audit = root / "data/audits/source_e_recovery/actions/38116209530/inventory"
    url = "https://ist.cl/mes-de-la-salud-mental-junto-a-uai-realizamos-significativo-encuentro-sobre-su-cuidado/"
    capture = json.loads((audit / "capture_index.json").read_text())[url]
    hop = capture["hops"][-1]
    content = (audit / "capture" / hop["body_file"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == "14165a3564ca3adc851a5d747cb4173312ccd4bc57efc48906a68bded48ca035"
    parser = parse(content.decode("utf-8"), url)
    assert parser.date_candidates == [
        {"kind": "article:published_time", "value": "2026-10-07T14:34:47+00:00"},
        {"kind": "publisher:publication_container", "value": "Oct 7, 2026"},
    ]
    assert parser.result(today=TODAY)[1] == "2026-10-07"
    assert parser.publication_evidence(today=TODAY)["value"] == "2026-10-07T14:34:47+00:00"


@pytest.mark.parametrize("field", [
    '<div>24/09/2026</div>', '<time datetime="2026-09-24">24/09/2026</time>',
    '<time class="unpublished" datetime="2026-09-24">24/09/2026</time>',
    '<div class="unpublished">24/09/2026</div>',
    '<p>Actividad realizada el 24/09/2026.</p>',
])
def test_event_dates_and_unpublished_class_are_not_publisher_evidence(field):
    parser = parse(f"<h1>{GUIDE}</h1>{field}<p>{BODY}</p>")
    assert parser.result(today=TODAY)[1:] == (None, parser.result(today=TODAY)[2], "missing_publication_date")
    assert parser.publication_evidence(today=TODAY) is None


def test_accumulate_all_publication_fields_and_fail_closed_on_conflict():
    parser = parse('<meta property="article:published_time" content="2026-09-23">' + article_html())
    assert len(parser.date_candidates) == 2
    assert parser.result(today=TODAY)[1] is None
    assert parser.result(today=TODAY)[3] == "conflicting_publication_dates"
    assert parser.publication_evidence(today=TODAY) is None


def test_invalid_first_meta_is_not_overwritten_by_later_valid_meta():
    parser = parse('<meta itemprop="datePublished" content="bogus 2026-09-24">' + article_html())
    assert parser.result(today=TODAY)[3] == "invalid_publication_date"


def test_duplicate_consistent_publication_fields_preserve_original_evidence():
    html = article_html().replace("<p>", '<time class="published" datetime="2026-09-24T12:00:00Z"></time><p>', 1)
    parser = parse(html)
    assert parser.result(today=TODAY)[1] == "2026-09-24"
    assert parser.publication_evidence(today=TODAY) == {
        "url": BASE + "guia", "value": "2026-09-24", "date": "2026-09-24", "kind": "article:published_time"}


def test_native_achs_fecha_is_header_scoped_and_host_verified():
    html = article_html(published="24/09/2026", field="native")
    parser = parse(html)
    assert parser.result(today=TODAY)[1::2] == ("2026-09-24", "publisher:achs_div_fecha")
    assert parse(html, "https://ist.cl/noticia/").result(today=TODAY)[1] is None
    assert parse(html, "https://www.achs.cl/centro-de-noticias/noticia/1").result(today=TODAY)[1] is None
    after_body = f'<h1>{GUIDE}</h1><p>Evento previsto para el próximo mes.</p><div class="fecha">24/09/2026</div>'
    assert parse(after_body).result(today=TODAY)[1] is None


def test_recognized_published_container_and_semantic_time_have_explicit_evidence():
    html = f'<h1>{GUIDE}</h1><div class="publication-date">Publicado el 24 de septiembre de 2026</div><p>{BODY}</p>'
    parser = parse(html, "https://ist.cl/noticia/")
    assert parser.result(today=TODAY)[1] == "2026-09-24"
    assert parser.publication_evidence(today=TODAY)["value"] == "24 de septiembre de 2026"
    timed = parse(f'<h1>{GUIDE}</h1><time class="entry-date published" datetime="2026-09-24T12:00:00Z"></time><p>{BODY}</p>')
    assert timed.publication_evidence(today=TODAY)["kind"] == "time.published@datetime"


def test_related_publication_fields_do_not_supply_article_date():
    parser = parse(f'<h1>{GUIDE}</h1><p>{BODY}</p><h2>Últimas publicaciones</h2><time class="published" datetime="2026-09-24"></time>')
    assert parser.result(today=TODAY)[1] is None


@pytest.mark.parametrize("body", [
    "La doctora de Clínica Atacama Achs Salud explica tratamientos y amplía información sobre prevención.",
    "Según el médico de Clínicas Achs Salud, se habilita información de prevención para los trabajadores.",
    'Un especialista afirma: "Clínicas Achs Salud incorpora nuevas prestaciones". El artículo analiza salud laboral.',
    "Fuera de horario, acudir a Clínica Lircay Achs Salud para atención.",
])
def test_incidental_provider_affiliation_quote_or_referral_does_not_change_actor(body):
    assert market_role("Guía sobre accidentes de trabajo y prevención", body) == "mutuality"


def test_actual_provider_action_and_headline_are_attributed():
    body = "La Achs, junto con su filial Clínicas Achs Salud, se suma a la activación de SAFED de Fonasa."
    assert market_role("Achs se une a iniciativa público privada por las lluvias", body) == "provider_achs"
    assert market_role("Clínica Atacama Achs Salud amplía servicios", "Nuevas prestaciones.") == "provider_achs"


def test_free_coverage_is_not_an_action_negation():
    assert materiality("provider_achs", "Atención a damnificados", "Clínicas Achs Salud activa SAFED de Fonasa sin costo.") == (True, "public_private_coverage_change")


def test_centers_are_distinct_from_clinics_despite_referral():
    assert market_role("Master Plan Achs Salud: modernizamos centros y ampliamos servicios",
                       "Nuevo Centro San Javier. Fuera de horario acudir a Clínica Lircay Achs Salud.") == "provider_achs_centers"


@pytest.mark.parametrize("title,body", [
    ("No inaugura ni amplía", "La organización no inaugura ni amplía centros o servicios."),
    ("Campaña de prevención", "Se amplía la información sobre prevención y autocuidado."),
    ("Consejos para prevenir accidentes", "Use casco y amplíe su información sobre riesgos."),
    ("No se adhiere nueva empresa", "No se adhiere una empresa con 700 trabajadores."),
    ("No implementa nuevo protocolo", "La organización no implementa un nuevo protocolo de tratamiento."),
])
def test_negated_or_generic_prevention_does_not_pass_materiality(title, body):
    assert not materiality("mutuality", title, body)[0]


@pytest.mark.parametrize("title,body,reason", [
    ("Campaña con nueva capacidad clínica", "Se inaugura un nuevo centro con 20 boxes de atención.", "capacity_or_investment_change"),
    ("Campaña de salud mental", "Se implementa un nuevo protocolo de tratamiento y reintegro laboral.", "new_operational_tool_or_protocol"),
    ("Empresa se adhiere al IST", "Se adhiere una empresa con 700 trabajadores y trabajadoras.", "quantified_coverage_change"),
    ("Accidentes de trayecto aumentan un 37%", "Datos del primer semestre de 2026.", "quantified_occupational_data"),
])
def test_concrete_change_can_accompany_campaign_and_adherence_coverage(title, body, reason):
    assert materiality("mutuality", title, body) == (True, reason)


def test_partial_timeout_preserves_other_articles_and_exact_error():
    source = scout()
    visited = []
    def loader(url):
        visited.append(url)
        if url.endswith("failed"):
            raise TimeoutError("connect timed out after 12s")
        return article_html()
    listing = '<a href="' + BASE + 'failed">failed</a><a href="' + BASE + 'good">good</a>'
    with pytest.raises(SourceDiscoveryError) as captured:
        discover_items(source, listing, loader, as_of=TODAY)
    error = captured.value
    assert visited == [BASE + "failed", BASE + "good"]
    assert error.code == "detail_fetch_failed" and error.url == BASE + "failed"
    assert "connect timed out after 12s" in error.diagnostics[0]["detail"]
    assert [raw.url for raw in error.partial_items] == [BASE + "good"]
    assert source.discovery_incomplete and source.coverage_status == "incomplete"
    assert source.decisions[0]["status"] == "pending"
    evidence = error.partial_items[0].metadata["publication_evidence"]
    assert evidence["url"] == BASE + "good" and evidence["date"] == "2026-09-24"
    assert error.partial_items[0].metadata["publication_date_source"] == evidence["kind"]


def test_undated_detail_with_valid_other_article_remains_incomplete():
    source = scout()
    listing = f'<a href="{BASE}event">event</a><a href="{BASE}good">good</a>'
    def loader(url):
        return f"<h1>{GUIDE}</h1><div>24/09/2026</div><p>{BODY}</p>" if url.endswith("event") else article_html()
    with pytest.raises(SourceDiscoveryError) as captured:
        discover_items(source, listing, loader, as_of=TODAY)
    assert captured.value.code == "detail_publication_evidence_missing"
    assert captured.value.diagnostics[0]["detail"] == "missing_publication_date"
    assert len(captured.value.partial_items) == 1


def test_multiple_failures_preserve_http_and_waf_evidence_and_continue():
    source = scout()
    listing = "".join(f'<a href="{BASE}{name}">{name}</a>' for name in ("http", "waf", "good"))
    def loader(url):
        if url.endswith("http"):
            raise HTTPError(url, 403, "Forbidden", {}, None)
        if url.endswith("waf"):
            return '<iframe src="/_Incapsula_Resource?incident_id=123"></iframe>'
        return article_html()
    with pytest.raises(SourceDiscoveryError) as captured:
        discover_items(source, listing, loader, as_of=TODAY)
    assert captured.value.code == "partial_detail_capture"
    assert captured.value.diagnostics[0]["http_status"] == 403
    assert captured.value.diagnostics[1]["code"] == "external_waf_challenge"
    assert captured.value.partial_items[0].url == BASE + "good"


def test_listing_proxy_denial_does_not_claim_origin_http_403():
    source = scout()
    def denied(url):
        raise URLError("Tunnel connection failed: 403 Forbidden")
    with pytest.raises(SourceDiscoveryError) as captured:
        fetch_listing(source, denied)
    assert captured.value.code == "executor_proxy_denied"
    assert "http_status" not in captured.value.diagnostics[0]
    assert source.discovery_incomplete


def test_no_silent_sixty_detail_cap_and_explicit_configured_limit():
    listing = "".join(f'<a href="{BASE}guide-{n}">guide</a>' for n in range(61))
    source = scout()
    rows = discover_items(source, listing, lambda url: article_html(), as_of=TODAY)
    assert len(rows) == 61 and len(source.decisions) == 61
    assert source.coverage_status == "observed_page_complete"
    with pytest.raises(SourceDiscoveryError) as captured:
        discover_items(source, listing, lambda url: article_html(), as_of=TODAY, max_items=60)
    assert captured.value.code == "detail_limit_reached"
    assert len(captured.value.partial_items) == 60
    assert "1 distinct candidate" in captured.value.diagnostics[0]["detail"]


def test_centers_accepted_only_by_configured_provider_role_and_keep_subtype():
    title = "Master Plan Achs Salud: modernizamos centros y ampliamos servicios"
    body = "Se inaugura un nuevo centro de atención en San Javier y se amplía el equipamiento. " * 3
    source = scout("provider_achs", accepted_roles=("provider_achs", "provider_achs_centers"))
    listing = f'<a href="{BASE}master-plan">Master Plan</a>'
    rows = discover_items(source, listing, lambda url: article_html(title, body), as_of=TODAY)
    assert len(rows) == 1
    assert rows[0].metadata["market_role"] == "provider_achs_centers"
    assert rows[0].metadata["provider_subtype"] == "centros"
    mutual = scout()
    assert discover_items(mutual, listing, lambda url: article_html(title, body), as_of=TODAY) == []
    assert mutual.decisions[0]["market_role"] == "provider_achs_centers"
    assert mutual.decisions[0]["reason"] == "different_market_role"


def test_explicit_as_of_horizon_is_independent_of_machine_clock():
    source = scout()
    listing = f'<a href="{BASE}boundary">boundary</a>'
    rows = discover_items(source, listing, lambda url: article_html(published="2026-07-13"), as_of=TODAY)
    assert len(rows) == 1
    assert discover_items(source, listing, lambda url: article_html(published="2026-07-12"), as_of=TODAY) == []
    assert source.decisions[0]["reason"] == "outside_90_day_horizon"


def live_material_fixture(fragment, *, mutual=False):
    """Return an article whose full scoped body agrees with the live bytes."""
    import hashlib
    import json
    root = Path(__file__).resolve().parents[1]
    if mutual:
        audit = json.loads((root / "data/audits/source_e_recovery/mutual_run4_replay.json").read_text())
        raws = audit["inventory"]["raw_items"]
    else:
        audit = json.loads((root / "data/audits/source_e_recovery/actions/38116209530/inventory/inventory.json").read_text())
        raws = audit["sources"]["achs_seguro_laboral"]["raw_items"]
    raw = next(raw for raw in raws if fragment in raw["url"])
    evidence = audit["evidence"][raw["url"]] if mutual else raw["metadata"]["capture_evidence"]
    content = (root / evidence["artifact"]).read_bytes()
    assert hashlib.sha256(content).hexdigest() == evidence["sha256"]
    if mutual:
        from radar_salud.mutual_sources import parse_detail
        current = parse_detail(content.decode("utf-8"), raw["url"], as_of=TODAY)
        title, body = current["title"], current["body"]
    else:
        title, _, body, _ = parse(content.decode("utf-8"), raw["url"]).result(today=TODAY)
    assert title == raw["title"] and body == raw["metadata"]["page_text"]
    return raw


@pytest.mark.parametrize("fragment,expected", [
    ("a-dos-anos-de-la-ley-karin", "quantified_occupational_data"),
    ("innovar-para-llegar-a-tiempo", "quantified_occupational_data"),
    ("renovado-centro-de-entrenamiento", "capacity_or_investment_change"),
    ("achs-pone-a-disposicion-guia", "new_operational_tool_or_protocol"),
    ("conoce-las-actualizaciones", "quantified_operational_process_change"),
])
def test_real_published_business_changes_are_not_lost_before_editorial_review(fragment, expected):
    raw = live_material_fixture(fragment)
    assert materiality("mutuality", raw["title"], raw["metadata"]["page_text"]) == (True, expected)


@pytest.mark.parametrize("fragment,expected", [
    ("licitacion-publica-convenio-marco", "capacity_procurement_call"),
    ("gran-americas-se-incorpora", "quantified_coverage_change"),
])
def test_real_mutual_procurement_and_quantified_network_adherence_are_candidates(fragment, expected):
    raw = live_material_fixture(fragment, mutual=True)
    assert materiality("mutuality", raw["title"], raw["metadata"]["page_text"]) == (True, expected)
    if expected == "capacity_procurement_call":
        assert "carácter facultativo" in raw["metadata"]["page_text"]
        assert "eventual adjudicación" in raw["metadata"]["page_text"]


def test_real_available_reporting_tool_and_generic_grc_manual_remain_rejected():
    for fragment, mutual in (("descubre-el-modulo-de-reporteria", False), ("manual-grc", True)):
        raw = live_material_fixture(fragment, mutual=mutual)
        assert materiality("mutuality", raw["title"], raw["metadata"]["page_text"]) == (
            False, "no_verifiable_material_change")


@pytest.mark.parametrize("title,body", [
    ("Centro de entrenamiento", "No reabre el centro ni remodela su infraestructura."),
    ("Licitación pública", "La convocatoria es para adquirir material de oficina y mobiliario."),
    ("Nueva adhesión", "Una empresa se incorpora a la mutualidad sin informar escala o trabajadores."),
    ("Cobertura de transporte", "La mutualidad asesora a ocho de las nueve empresas desde hace años."),
    ("Informe de salud mental laboral", "No se publicó un informe. Se recibieron 32.522 requerimientos."),
    ("Consejos de inscripción", "Inscribir cursos e-learning en simples pasos ayuda al usuario."),
    ("Guía de buen trato", "Una guía recomienda respeto y autocuidado en las instituciones."),
])
def test_generic_negated_or_unquantified_updates_stay_closed(title, body):
    assert not materiality("mutuality", title, body)[0]


@pytest.mark.parametrize("fragment,mutual,expected", [
    ("a-dos-anos-de-la-ley-karin", False, "study"),
    ("renovado-centro-de-entrenamiento", False, "news"),
    ("achs-pone-a-disposicion-guia", False, "prevention"),
    ("conoce-las-actualizaciones", False, "news"),
    ("licitacion-publica-convenio-marco", True, "commercial"),
    ("gran-americas-se-incorpora", True, "commercial"),
    ("manual-grc", True, "prevention"),
])
def test_live_content_kind_describes_article_without_changing_its_gate(fragment, mutual, expected):
    raw = live_material_fixture(fragment, mutual=mutual)
    body = raw["metadata"]["page_text"]
    before = materiality("mutuality", raw["title"], body)
    assert classify_content_kind(before[1], raw["title"], body) == expected
    assert materiality("mutuality", raw["title"], body) == before
    assert raw["event_date"] == raw["metadata"]["publication_date"]


def test_study_landing_classification_does_not_promote_an_unassessed_report():
    title = "Reporte de Sostenibilidad IST 2025"
    body = "El reporte correspondiente al año2025 incluye60 indicadores GRI y SASB que documentan desempeño."
    accepted, reason = materiality("mutuality", title, body)
    assert not accepted
    assert classify_content_kind(reason, title, body) == "study"


def test_content_kind_labels_cannot_override_missing_date_or_generic_promotion():
    assert classify_content_kind("missing_publication_date", "Nueva clínica amplía servicios") == "news"
    assert classify_content_kind("no_verifiable_material_change", "Descuentos en atenciones") == "commercial"
    assert classify_content_kind("campaign_event_testimonial_or_recognition", "Campaña rutinaria de prevención") == "prevention"
    assert not materiality("mutuality", "Descuentos en atenciones", "Una promoción comercial ofrece precios especiales.")[0]

