"""SIS Biblioteca digital > Publicaciones (Dirección 12-nov-2026): documentos metodológicos (ICSA, IRCI, ...)
and the other collections in the hub's menu are discovered with their listing dates, across pages."""
from pathlib import Path
from unittest import mock

from radar_salud import scouts
from radar_salud.scouts import SuperintendenciaStatsScout

FIX = Path(__file__).parent / "fixtures" / "sis"
S = SuperintendenciaStatsScout
METODO = S.PUBLICATION_LISTINGS[0]
TRABAJO = "https://www.superdesalud.gob.cl/tax-biblioteca-digital/publicaciones-6509/documentos-de-trabajo-7454/"


def _f(name):
    return (FIX / name).read_text(encoding="utf-8")


def _pages(extra=None):
    pages = {S.PUBLICATIONS_URL: _f("publicaciones_hub_20261112.html"),
             METODO: _f("documentos_metodologicos_p1_20261112.html"),
             METODO + "page/2/": _f("documentos_metodologicos_p2_20261112.html")}
    pages.update(extra or {})

    def fetch(url):
        if url not in pages:
            raise OSError("404 " + url)
        return pages[url]
    return fetch


def test_hub_menu_gives_only_publication_collections():
    out = S().publication_listings(_f("publicaciones_hub_20261112.html"))
    assert out == [TRABAJO, METODO]  # never Estadísticas, Datos abiertos or the Observatorio


def test_methodological_documents_with_dates_collection_and_all_pages():
    scout = S()
    items = scout.discover_publications(fetch=_pages())
    by = {i.title: i for i in items}
    icsa = by["Indicador de Costos de la Salud (ICSA) 2025"]
    assert icsa.event_date == "2026-03-09" and icsa.metadata["listing_publication_date"] == "2026-03-09"
    assert icsa.metadata["collection"] == "documentos-metodologicos"
    assert icsa.url == "https://www.superdesalud.gob.cl/biblioteca-digital/indicador-de-costos-de-la-salud-icsa-2025/"
    assert by["Índices referenciales del Costo de las Isapres (IRCI) 2025"].event_date == "2026-03-10"
    assert by["Documentación y metadatos Boletín de Planes 2025."].event_date == "2026-01-30"  # page 2
    assert len(items) == 6 and not any("/tax-" in i.url or "/app/uploads/" in i.url for i in items)
    # documentos de trabajo is in the menu but unreachable here: reported, never fatal.
    assert scout.publication_errors == [(TRABAJO, "OSError")]


def test_pagination_is_bounded_and_does_not_loop():
    looping = "<a href='" + METODO + "page/2/'>2</a>"
    pages = {S.PUBLICATIONS_URL: "<html></html>", METODO: looping, METODO + "page/2/": "<a href='" + METODO + "page/3/'>3</a>"}
    for n in range(3, 20):
        pages[METODO + f"page/{n}/"] = f"<a href='{METODO}page/{n + 1}/'>{n + 1}</a>"
    seen = []

    def fetch(url):
        seen.append(url)
        return pages[url]
    S().discover_publications(fetch=fetch)
    assert len([u for u in seen if u.startswith(METODO)]) == S.MAX_PAGES
    assert S.next_page(_f("documentos_metodologicos_p2_20261112.html"), METODO + "page/2/") is None


def test_discover_adds_publications_after_statistics_and_survives_hub_failure():
    stats = _f("estadisticas_listing_20261028.html")

    def fetch(url, timeout=20):
        if url == S.DEFAULT_URL:
            return stats
        return _pages()(url)
    with mock.patch.object(scouts, "fetch_html", fetch):
        items = S().discover()
    assert len(items) == 6 + 6
    assert {i.metadata.get("collection") for i in items[6:]} == {"documentos-metodologicos"}

    def broken(url, timeout=20):
        if url == S.DEFAULT_URL:
            return stats
        raise OSError("down")
    with mock.patch.object(scouts, "fetch_html", broken):
        scout = S()
        assert len(scout.discover()) == 6  # statistics unaffected
        assert scout.publication_errors


def test_malformed_markup_never_breaks_statistics():
    stats = _f("estadisticas_listing_20261028.html")

    def fetch(url, timeout=20):
        if url == S.DEFAULT_URL:
            return stats
        if url == S.PUBLICATIONS_URL:
            return "<a href='http://[bad'>x</a>"
        return "<a href='http://[bad'>x</a><a href='/biblioteca-digital/y/'>y</a>"
    with mock.patch.object(scouts, "fetch_html", fetch):
        scout = S()
        assert len(scout.discover()) == 6
    assert scout.discovery_errors and all(e.startswith("publicaciones:") for e in scout.discovery_errors)


def test_page_cap_is_reported():
    pages = {S.PUBLICATIONS_URL: "<html></html>"}
    for n in range(1, 20):
        url = METODO if n == 1 else METODO + f"page/{n}/"
        pages[url] = f"<a href='{METODO}page/{n + 1}/'>{n + 1}</a>"
    scout = S()
    scout.discover_publications(fetch=lambda u: pages[u])
    assert (METODO + f"page/{S.MAX_PAGES + 1}/", "page_cap") in scout.publication_errors


def test_publication_is_not_classified_as_a_statistics_family():
    from radar_salud.analysis import analyze_superintendencia
    from radar_salud.models import RawItem
    raw = RawItem("superintendencia_salud", "Documento de trabajo: Gestión de reclamos y casos GES 2025",
                  "https://www.superdesalud.gob.cl/biblioteca-digital/x/", "Superintendencia de Salud", "official",
                  event_date="2026-11-10", metadata={"collection": "documentos-de-trabajo"})
    a = analyze_superintendencia(raw)
    assert "tasas de uso GES" not in a.what_happened and a.what_happened.startswith("La Superintendencia publicó en su biblioteca digital") and "ges" not in a.watch_tags and "publicaciones" in a.watch_tags
    src = (Path(__file__).parents[1] / "src/radar_salud/superintendencia_pipeline.py").read_text(encoding="utf-8")
    assert 'fam=None if (raw.metadata or {}).get("collection")' in src
