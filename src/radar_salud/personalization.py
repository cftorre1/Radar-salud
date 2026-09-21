from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List

from .models import Signal


@dataclass(frozen=True)
class UserProfile:
    profile_id: str
    label: str
    domains: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    watch_tags: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    institution_types: List[str] = field(default_factory=list)
    strategic_themes: List[str] = field(default_factory=list)


def _overlap(left: Iterable[str], right: Iterable[str]) -> int:
    a = {x.casefold() for x in left if x}
    b = {x.casefold() for x in right if x}
    return len(a & b)


def personal_relevance(signal: Signal, profile: UserProfile) -> int:
    """Return a personalized 0..100 relevance score.

    The global Radar Score remains untouched. Personal relevance is a second
    layer used for ranking/distribution to a specific user.
    """
    # Start below the global score so explicit user affinity can meaningfully
    # reorder signals instead of every broadly relevant item saturating at 100.
    score = signal.radar_score * 0.75
    domain_match = signal.system_domain in profile.domains

    if domain_match:
        score += 15
    if signal.category in profile.categories:
        score += 8

    tag_hits = _overlap(signal.watch_tags + signal.topics, profile.watch_tags)
    score += min(18, tag_hits * 6)

    entity_hits = _overlap(signal.entities, profile.entities)
    score += min(12, entity_hits * 6)

    institution_hits = _overlap(signal.institution_types, profile.institution_types)
    score += min(12, institution_hits * 6)

    theme_hits = _overlap(signal.strategic_theme, profile.strategic_themes)
    score += min(12, theme_hits * 6)

    # Strong regulatory signals are especially important for profiles that
    # explicitly follow regulation/legal content.
    if (
        signal.category == "Regulación & Legal"
        and "Regulación & Legal" in profile.categories
        and signal.regulatory_impact_score >= 80
        and domain_match
    ):
        score += 6

    return max(0, min(100, round(score)))


DEFAULT_PROFILES = {
    "isapre": UserProfile(
        profile_id="isapre",
        label="Ejecutivo Isapre",
        domains=["HEALTH_INSURANCE"],
        categories=["Aseguramiento", "Regulación & Legal", "Prestadores"],
        watch_tags=["isapres", "ges", "caec", "circular", "resolución", "oficio", "prestadores"],
        institution_types=["ISAPRE", "PRIVATE_PROVIDER"],
        strategic_themes=["DIGITAL_TRANSFORMATION", "AI", "COST_MANAGEMENT", "REGULATORY_CHANGE"],
    ),
    "mutualidad": UserProfile(
        profile_id="mutualidad",
        label="Ejecutivo Mutualidad",
        domains=["OCCUPATIONAL_HEALTH", "SOCIAL_SECURITY"],
        categories=["Salud Laboral & Seguridad Social", "Regulación & Legal"],
        watch_tags=["suseso", "mutualidades", "circular", "resolución", "ley 16.744", "accidentabilidad"],
        institution_types=["MUTUAL", "REGULATOR"],
        strategic_themes=["PREVENTION", "AI", "DIGITAL_TRANSFORMATION", "REGULATORY_CHANGE"],
    ),
    "prestador": UserProfile(
        profile_id="prestador",
        label="Ejecutivo Prestador",
        domains=["HEALTH_PROVIDERS", "HEALTH"],
        categories=["Prestadores", "Oportunidades & Licitaciones", "Mercado"],
        watch_tags=["licitaciones", "inversiones", "prestadores", "hospital", "clínica"],
        institution_types=["PRIVATE_PROVIDER", "PUBLIC_PROVIDER"],
        strategic_themes=["CAPACITY_EXPANSION", "AI", "DIGITAL_TRANSFORMATION", "AMBULATORY_SHIFT"],
    ),
}
