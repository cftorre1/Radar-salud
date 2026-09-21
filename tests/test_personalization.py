from src.radar_salud.models import Signal
from src.radar_salud.personalization import DEFAULT_PROFILES, personal_relevance


def sig(**kw):
    base = dict(
        title="Circular SUSESO",
        source_name="SUSESO", source_type="official", source_url="https://example.com/1",
        category="Regulación & Legal", subcategory="Regulación", system_domain="OCCUPATIONAL_HEALTH",
        what_happened="Nueva circular", radar_score=78, confidence_score=100,
        regulatory_impact_score=95, watch_tags=["suseso", "circular", "mutualidades"],
    )
    base.update(kw)
    return Signal(**base)


def test_mutualidad_boosts_suseso_regulation():
    s = sig()
    assert personal_relevance(s, DEFAULT_PROFILES["mutualidad"]) >= 95
    assert personal_relevance(s, DEFAULT_PROFILES["mutualidad"]) > personal_relevance(s, DEFAULT_PROFILES["isapre"])


def test_isapre_boosts_health_insurance_signal():
    s = sig(
        title="Circular Superintendencia de Salud",
        source_name="Superintendencia de Salud",
        system_domain="HEALTH_INSURANCE",
        watch_tags=["isapres", "circular"],
        radar_score=80,
    )
    assert personal_relevance(s, DEFAULT_PROFILES["isapre"]) >= 95
