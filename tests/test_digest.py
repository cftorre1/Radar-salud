from src.radar_salud.digest import build_daily_digest
from src.radar_salud.models import Signal


def mk(title, source, score, confidence, why):
    return Signal(
        title=title,
        source_name=source,
        source_type="official",
        source_url="https://example.org",
        category="Mercado",
        subcategory="General",
        system_domain="HEALTH",
        what_happened=title,
        why_it_matters=why,
        radar_score=score,
        confidence_score=confidence,
    )


def test_digest_combines_sources_and_orders_by_relevance():
    signals = [
        mk("Señal SUSESO", "SUSESO", 88, 98, "Cambio regulatorio."),
        mk("Señal Isapre", "Superintendencia de Salud", 76, 99, "Actualiza cartera."),
        mk("Ruido", "Fuente X", 40, 99, "No relevante."),
    ]
    out = build_daily_digest(signals, "2026-09-21")
    assert out.index("Señal SUSESO") < out.index("Señal Isapre")
    assert "Ruido" not in out
    assert "2026-09-21" in out
