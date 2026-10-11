"""Semantic fixtures reconstructed from original pages; not raw HTML captures."""
import pytest
from datetime import date

from radar_salud.beta_sources import CuratedBetaSourceScout, process_curated_beta_source
from radar_salud.occupational_sources import Article, SourceDiscoveryError, materiality

ACHS = "/centro-de-noticias/noticia/2026/"


@pytest.fixture(autouse=True)
def audit_calendar(monkeypatch, tmp_path):
    monkeypatch.setattr("radar_salud.occupational_sources.chile_today", lambda: date(2026, 10, 11))
    monkeypatch.setattr("radar_salud.occupational_evidence.project_root", lambda: tmp_path)
    original = CuratedBetaSourceScout.discover_from_html
    def captured(self, html, detail_loader=None):
        cache = {}
        def load(url):
            if url not in cache:
                cache[url] = detail_loader(url)
            return cache[url]
        rows = original(self, html, load)
        import hashlib
        import json
        for raw in rows:
            body = cache[raw.url].encode()
            identity = hashlib.sha256((raw.url + "\nidentified").encode()).hexdigest()[:20]
            path = tmp_path / "data/audits/source_e_recovery/fixture" / (identity + "-0.body")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            digest, stamp = hashlib.sha256(body).hexdigest(), "2026-10-11T06:00:00+00:00"
            hop = dict(url=raw.url, http_status=200, curl_exit=0, tls={"verified": True}, waf=None,
                       body_file=path.name, sha256=digest, bytes=len(body))
            path.with_name(identity + ".json").write_text(json.dumps(dict(url=raw.url, final_url=raw.url,
                user_agent="identified", captured_at=stamp, stop_reason="response_captured", waf=None, http_status=200, hops=[hop])))
            raw.metadata["capture_evidence"] = {"url": raw.url, "final_url": raw.url, "http_status": 200,
                "tls_verified": True, "sha256": digest, "artifact": str(path), "captured_at": stamp}
        return rows
    monkeypatch.setattr(CuratedBetaSourceScout, "discover_from_html", captured)


def detail(title, published="24/09/2026", body=None, meta=""):
    body = body or ("La nueva guía de tratamiento de patologías de salud mental laboral incorpora "
                    "recomendaciones para evaluación, atención clínica y reintegro laboral, "
                    "elaboradas a partir de una revisión sistemática y entrevistas a equipos tratantes.")
    return (f'<meta property="article:published_time" content="{meta}">' if meta else "") + (
        '<nav>10/08/2016 Clínicas Achs Salud Fonasa prevención</nav>'
        '<script>"datePublished": "2016-11-02"</script>'
        f'<h1>{title}</h1><div class="publication-date">{published}</div><p>{body}</p>'
        '<h2>Últimas publicaciones</h2><p>05/10/2026 Clínica Atacama Achs Salud inaugura pabellón</p>'
        '<footer>Fonasa, convenios, mutualidades</footer>')


def test_achs_reads_visible_title_and_own_date_without_og_metadata():
    scout = CuratedBetaSourceScout("achs_seguro_laboral")
    rows = scout.discover_from_html(f'<a href="{ACHS}guia">Ver detalle</a>',
                                   lambda url: detail("Nueva guía de tratamiento en salud mental laboral"))
    assert len(rows) == 1
    assert rows[0].event_date == "2026-09-24"
    assert rows[0].metadata["materiality_accepted"]
    assert "05/10/2026" not in rows[0].metadata["page_text"]
    assert "Clínica Atacama" not in rows[0].metadata["page_text"]


@pytest.mark.parametrize("published,meta", [
    ("31/02/2026", ""), ("24/09/2099", ""), ("", ""),
    ("24/09/2026", "2026-09-23T12:00:00Z"),
])
def test_invalid_missing_future_or_conflicting_dates_never_use_related_news(published, meta):
    article = Article()
    article.feed(detail("Una publicación con contenido suficiente", published, meta=meta))
    assert article.result()[1] is None


def test_prose_event_date_is_not_publication_evidence():
    article = Article()
    article.feed(detail("Una publicación con contenido suficiente", "", body="Actividad realizada el 24/09/2026. " * 8))
    assert article.result()[1] is None


def test_missing_detail_is_technical_failure_with_exact_url():
    def failing(url):
        raise TimeoutError()
    with pytest.raises(SourceDiscoveryError) as exc:
        CuratedBetaSourceScout("achs_seguro_laboral").discover_from_html(
            f'<a href="{ACHS}guia">Ver detalle</a>', failing)
    assert exc.value.code == "detail_fetch_failed"
    assert exc.value.url.endswith("/guia")


def test_provider_and_mutuality_are_exclusive_even_with_common_footer():
    listing = f'<a href="{ACHS}safed">Ver detalle</a><a href="{ACHS}guia">Ver detalle</a>'
    pages = {
        "safed": detail("Clínicas Achs Salud activa atención SAFED", "28/08/2026",
                        "Clínicas Achs Salud incorpora la Clínica Atacama a SAFED de Fonasa. "
                        "La activación habilita consultas, laboratorio e imagenología sin costo para "
                        "damnificados inscritos en FIBE. La red pública conserva las hospitalizaciones."),
        "guia": detail("Nueva guía de tratamiento en salud mental laboral"),
    }
    load = lambda url: pages[url.rsplit("/", 1)[1]]
    provider = CuratedBetaSourceScout("clinicas_achs_salud").discover_from_html(listing, load)
    mutual = CuratedBetaSourceScout("achs_seguro_laboral").discover_from_html(listing, load)
    assert [r.url.rsplit("/", 1)[1] for r in provider] == ["safed"]
    assert [r.url.rsplit("/", 1)[1] for r in mutual] == ["guia"]


def test_provider_absence_in_listing_is_valid_zero_not_runtime_error():
    scout = CuratedBetaSourceScout("clinicas_achs_salud")
    assert scout.discover_from_html(f'<a href="{ACHS}guia">Ver detalle</a>',
                                    lambda url: detail("Nueva guía de tratamiento en salud mental laboral")) == []
    assert scout.decisions[0]["reason"] == "different_market_role"


def test_center_changes_and_incidental_clinic_routing_are_not_clinic_news():
    from radar_salud.occupational_sources import market_role
    assert market_role("Master Plan Achs Salud: modernizamos centros y ampliamos servicios",
                       "Nuevo Centro San Javier. Fuera de horario acudir a Clínica Lircay Achs Salud.") == "provider_achs_centers"


def test_clinic_story_after_five_mutual_stories_remains_discoverable(monkeypatch):
    from radar_salud.beta_sources_fast import FastCuratedBetaSourceScout
    listing = "".join(f'<a href="{ACHS}guia-{n}">Ver detalle</a>' for n in range(5))
    listing += f'<a href="{ACHS}safed">Ver detalle</a>'
    def load(url):
        if url.endswith("centro-de-noticias"):
            return listing
        if url.endswith("safed"):
            return detail("Clínicas Achs Salud activa atención SAFED", "28/08/2026",
                          "Clínicas Achs Salud activa SAFED de Fonasa en Clínica Atacama. " * 4)
        return detail("Nueva guía de tratamiento en salud mental laboral")
    # Pass the loader explicitly because the base discover_from_html default is bound.
    monkeypatch.setattr("radar_salud.beta_sources.fetch_html", load)
    monkeypatch.setattr(CuratedBetaSourceScout, "discover", lambda self: self.discover_from_html(load(self.cfg["page"]), load))
    assert len(FastCuratedBetaSourceScout("clinicas_achs_salud").discover()) == 1


@pytest.mark.parametrize("title", [
    "Campaña por salud mental laboral", "Testimonio de rehabilitación",
    "Feria de bienestar con adherentes", "Semana de la seguridad con prevención",
    "Premio por cinco años sin accidentes", "Caminata preventiva de Achs Seguro Laboral",
])
def test_noise_cannot_be_promoted_by_generic_body_or_footer(title):
    assert not materiality("mutuality", title, "Fonasa inversión accidentes salud mental prevención")[0]


def test_quantified_work_accidents_are_material_but_advice_is_not():
    assert materiality("mutuality", "Accidentes de trayecto aumentan un 37%", "Datos del primer semestre de 2026")[0]
    assert not materiality("mutuality", "Consejos para prevenir accidentes", "Use casco y cuide su salud mental")[0]


def test_processing_reuses_scoped_detail_and_rejects_before_llm(monkeypatch):
    scout = CuratedBetaSourceScout("achs_seguro_laboral")
    rows = scout.discover_from_html(f'<a href="{ACHS}campana">Ver detalle</a>',
                                   lambda url: detail("Campaña por salud mental laboral", body="Jornada de difusión de consejos generales de bienestar. " * 5))
    def forbidden(*args, **kwargs):
        raise AssertionError("must not fetch or call paid analysis for rejected material")
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html", forbidden)
    monkeypatch.setattr("radar_salud.llm_analysis.analyze_news", forbidden)
    assert process_curated_beta_source(rows[0], {}) is None


def test_ist_heading_selectors_skip_history_navigation_and_archive_page_date():
    html = ('<meta property="article:published_time" content="2016-11-02">'
            '<nav><a href="/historia/">Historia del IST desde 1957</a></nav>'
            '<a href="/contacto/">Contáctanos y agenda tu atención</a>'
            '<article><h2 class="entry-title"><a href="/nueva-cobertura/">Nuevo adherente IST</a></h2></article>')
    visited = []
    def load(url):
        visited.append(url)
        return detail("IST incorpora a MK Recursos Humanos como adherente", "29/07/2026",
                      "Se incorpora un nuevo adherente, incorporando a más de 700 trabajadores "
                      "y trabajadoras. Esta nueva cobertura nacional permite acompañamiento técnico "
                      "a la empresa y sus trabajadores en el sistema de salud laboral.")
    rows = CuratedBetaSourceScout("ist").discover_from_html(html, load)
    assert visited == ["https://ist.cl/nueva-cobertura/"]
    assert rows[0].event_date == "2026-07-29"
    assert rows[0].metadata["materiality_reason"] == "quantified_coverage_change"


def test_old_ist_article_keeps_historical_date_and_does_not_enter_recent_discovery():
    scout = CuratedBetaSourceScout("ist")
    listing = '<h2><a href="/nota-historica/">Una noticia histórica del IST</a></h2>'
    assert scout.discover_from_html(listing, lambda url: detail("Una noticia histórica del IST", "02/11/2016")) == []
    assert scout.decisions[0]["event_date"] == "2016-11-02"
    assert scout.decisions[0]["reason"] == "outside_90_day_horizon"


def test_mutual_waf_challenge_is_exact_external_blocker_not_selector_failure():
    scout = CuratedBetaSourceScout("mutual_seguridad")
    with pytest.raises(SourceDiscoveryError) as exc:
        scout.discover_from_html('<iframe src="/_Incapsula_Resource?incident_id=example"></iframe>')
    assert exc.value.code == "external_waf_challenge"
    assert exc.value.url == scout.cfg["page"]


def test_proxy_denial_records_executor_blocker_not_origin_http_status(monkeypatch):
    from urllib.error import URLError
    def denied(url):
        raise URLError("Tunnel connection failed: 403 Forbidden")
    class DeniedLoader:
        def __init__(self, *args, **kwargs):
            pass
        def __call__(self, url):
            return denied(url)
    monkeypatch.setattr("radar_salud.occupational_capture.CaptureLoader", DeniedLoader)
    with pytest.raises(SourceDiscoveryError) as exc:
        CuratedBetaSourceScout("mutual_seguridad").discover()
    assert exc.value.code == "executor_proxy_denied"


def test_blocked_mutual_does_not_prevent_independent_source_discovery():
    results = {}
    for slug in ("mutual_seguridad", "achs_seguro_laboral"):
        scout = CuratedBetaSourceScout(slug)
        try:
            html = '<iframe src="/_Incapsula_Resource"></iframe>' if slug == "mutual_seguridad" else f'<a href="{ACHS}guia">Ver detalle</a>'
            results[slug] = scout.discover_from_html(html, lambda url: detail("Nueva guía de tratamiento en salud mental laboral"))
        except SourceDiscoveryError as exc:
            results[slug] = exc.code
    assert results["mutual_seguridad"] == "external_waf_challenge"
    assert len(results["achs_seguro_laboral"]) == 1


def test_unreconciled_occupational_source_never_becomes_live_from_new_watermark():
    from datetime import datetime, timezone
    from radar_salud.pending_queue import lane
    now = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
    scout = CuratedBetaSourceScout("achs_seguro_laboral")
    raw = scout.discover_from_html(f'<a href="{ACHS}guia">Ver detalle</a>',
                                   lambda url: detail("Nueva guía de tratamiento en salud mental laboral", now.strftime("%d/%m/%Y")))[0]
    assert lane(raw, now, now.isoformat()) == "BACKFILL"


def test_core_collector_continues_after_mutual_blocker_and_records_noise_rejection(tmp_path, monkeypatch):
    import json
    import shutil
    import sys
    from pathlib import Path
    from radar_salud import engine_cli, paths
    from radar_salud.pending_queue import fingerprint
    (tmp_path / "config").mkdir()
    shutil.copy(Path(__file__).resolve().parents[1] / "config/sources.json", tmp_path / "config/sources.json")
    class Null:
        def __init__(self, *args, **kwargs):
            pass
        def discover(self, *args, **kwargs):
            return []
    class Curated(CuratedBetaSourceScout):
        def discover(self):
            if self.slug == "mutual_seguridad":
                raise SourceDiscoveryError("external_waf_challenge", self.cfg["page"])
            if self.slug == "achs_seguro_laboral":
                return self.discover_from_html(f'<a href="{ACHS}campana">Ver detalle</a>',
                                               lambda url: detail("Campaña por salud mental laboral", body="Jornada de difusión de consejos generales de bienestar. " * 5))
            return []
    for name in ("SuperintendenciaStatsScout", "SuperintendenciaNormativaScout", "SuperintendenciaFiscalizacionScout",
                 "MinsalNewsScout", "SusesoNormativeScout", "SusesoNewsScout", "SusesoFiscalizacionScout", "DfHealthScout",
                 "FonasaDataHubScout", "FonasaNewsScout", "IspSurveillanceScout", "IspAnamedAlertScout", "ClinicasChileScout",
                 "DeisResourceScout", "DiarioOficialHealthScout", "CorporateNewsroomScout"):
        monkeypatch.setattr(engine_cli, name, Null)
    monkeypatch.setattr(engine_cli, "CuratedBetaSourceScout", Curated)
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    monkeypatch.setattr(engine_cli, "seed_from_history", lambda root: None)
    monkeypatch.setattr(engine_cli, "has_capacity", lambda kind: True)
    monkeypatch.setattr(engine_cli, "ai_budget_status", lambda: {})
    monkeypatch.setattr(sys, "argv", ["engine_cli", "--limit", "1"])
    engine_cli.main()
    audit = json.loads((tmp_path / "data/state/occupational_source_discovery.json").read_text())
    assert audit["mutual_seguridad"]["error"]["code"] == "external_waf_challenge"
    assert audit["achs_seguro_laboral"]["technical_status"] == "ok"
    queue = json.loads((tmp_path / "data/state/pending_queue.json").read_text())
    assert len(queue) == 1
    item = next(iter(queue.values()))
    assert item["status"] == "rejected"
    assert item["reason"] == "campaign_event_testimonial_or_recognition"
    health = json.loads((tmp_path / "data/source_health.json").read_text())
    assert health["sources"]["mutual_seguridad"]["error_detail"]["code"] == "external_waf_challenge"


def test_beta_analysis_deferral_remains_pending_not_editorial_rejection(tmp_path, monkeypatch):
    import json
    import shutil
    from pathlib import Path
    from radar_salud import beta_source_engine, paths
    (tmp_path / "config").mkdir()
    shutil.copy(Path(__file__).resolve().parents[1] / "config/beta_source_configs.json", tmp_path / "config/beta_source_configs.json")
    class Curated(CuratedBetaSourceScout):
        def discover(self):
            if self.slug != "achs_seguro_laboral":
                return []
            return self.discover_from_html(f'<a href="{ACHS}guia">Ver detalle</a>',
                                           lambda url: detail("Nueva guía de tratamiento en salud mental laboral"))
    class Null:
        def discover(self):
            return []
    monkeypatch.setattr(beta_source_engine, "CuratedBetaSourceScout", Curated)
    monkeypatch.setattr(beta_source_engine, "PrestadoresDataScout", Null)
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    monkeypatch.setattr(beta_source_engine, "project_root", lambda: tmp_path)
    monkeypatch.setattr("radar_salud.llm_analysis.analyze_news", lambda **kwargs: None)
    beta_source_engine.main()
    row = json.loads((tmp_path / "data/state/beta_source_validation.json").read_text())["sources"]["achs_seguro_laboral"]
    assert row["published"] == 0
    assert row["rejected_sample"] == 0
    assert row["deferred_sample"] == 1
    assert row["processing_decisions"][0]["status"] == "pending"
