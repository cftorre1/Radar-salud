from src.radar_salud.models import Signal
from src.radar_salud.multisource import merge_signals, rank_for_profile
from src.radar_salud.personalization import DEFAULT_PROFILES


def mk(title, url, domain, category, score, tags=None):
    return Signal(
        title=title, source_name="X", source_type="official", source_url=url,
        category=category, subcategory="General", system_domain=domain,
        what_happened=title, radar_score=score, confidence_score=95,
        watch_tags=tags or [], regulatory_impact_score=90 if category == "Regulación & Legal" else 20,
    )


def test_merge_and_rank_are_profile_specific():
    a = mk("Circular SUSESO", "https://x/a", "OCCUPATIONAL_HEALTH", "Regulación & Legal", 78, ["suseso", "circular"])
    b = mk("Dato Isapre", "https://x/b", "HEALTH_INSURANCE", "Aseguramiento", 82, ["isapres"])
    merged = merge_signals([[a, b], [a]])
    assert len(merged) == 2
    mutual = rank_for_profile(merged, DEFAULT_PROFILES["mutualidad"])
    isapre = rank_for_profile(merged, DEFAULT_PROFILES["isapre"])
    assert mutual[0].signal.title == "Circular SUSESO"
    assert isapre[0].signal.title == "Dato Isapre"
