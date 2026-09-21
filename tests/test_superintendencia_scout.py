from src.radar_salud.scouts import SuperintendenciaStatsScout, SeenStore, _fingerprint


HTML = """
<html><body>
<a href="/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2026/">
Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE - año 2026
</a>
<a href="/biblioteca-digital/estadistica-mensual-de-movilidad-de-cartera-de-cotizantes-del-sistema-isapre-a-nivel-regional-ano-2026/">
Estadística Mensual de Movilidad de Cartera de Cotizantes del Sistema ISAPRE a Nivel Regional - Año 2026
</a>
<a href="/tax-biblioteca-digital/estadisticas-3724/">Estadísticas</a>
</body></html>
"""


def test_discovers_detail_pages_only():
    scout = SuperintendenciaStatsScout()
    items = scout.discover_from_html(HTML)
    assert len(items) == 2
    assert all(x.source_slug == "superintendencia_salud" for x in items)
    assert "cartera" in items[0].title.lower()


def test_seen_store_deduplicates(tmp_path):
    scout = SuperintendenciaStatsScout()
    items = scout.discover_from_html(HTML)
    store = SeenStore(tmp_path / "seen.json")
    fp = _fingerprint(items[0].source_slug, items[0].url, items[0].title)
    store.add_many([fp])
    assert store.is_seen(fp)
