"""Semantic fixtures reconstructed from original pages; not raw HTML captures."""
import pytest

from radar_salud.beta_sources import CuratedBetaSourceScout, process_curated_beta_source
from radar_salud.occupational_sources import Article, SourceDiscoveryError, materiality

ACHS = "/centro-de-noticias/noticia/2026/"


def detail(title, published="24/09/2026", body=None, meta=""):
    body = body or ("La nueva guía de tratamiento de patologías de salud mental laboral incorpora "
                    "recomendaciones para evaluación, atención clínica y reintegro laboral, "
                    "elaboradas a partir de una revisión sistemática y entrevistas a equipos tratantes.")
    return (f'<meta property="article:published_time" content="{meta}">' if meta else "") + (
        '<nav>10/08/2016 Clínicas Achs Salud Fonasa prevención</nav>'
        '<script>"datePublished": "2016-11-02"</script>'
        f'<h1>{title}</h1><div>{published}</div><p>{body}</p>'
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
                                   lambda url: detail("Campaña por salud mental laboral"))
    def forbidden(*args, **kwargs):
        raise AssertionError("must not fetch or call paid analysis for rejected material")
    monkeypatch.setattr("radar_salud.public_source_pipeline.fetch_html", forbidden)
    monkeypatch.setattr("radar_salud.llm_analysis.analyze_news", forbidden)
    assert process_curated_beta_source(rows[0], {}) is None
