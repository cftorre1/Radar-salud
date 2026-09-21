from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class RawItem:
    source_slug: str
    title: str
    url: str
    source_name: str
    source_type: str
    event_date: Optional[str] = None
    raw_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityRef:
    """An entity mentioned by a Signal, with enough structure for CONNECT/TREND."""
    name: str
    entity_type: str = "organization"          # organization/person/place/product/etc.
    institution_type: Optional[str] = None      # PRIVATE_PROVIDER / ISAPRE / MUTUAL / etc.
    subsector: Optional[str] = None
    country: str = "CL"
    region: Optional[str] = None
    ownership_type: Optional[str] = None        # private/public/mixed
    canonical_id: Optional[str] = None


@dataclass
class Signal:
    """Atomic unit of Radar Salud V2.

    DISCOVER creates Signals. WATCH filters them. CONNECT links them. TREND
    aggregates them. BENCHMARK compares entities using them. ASK queries all
    of the above.
    """
    title: str
    source_name: str
    source_type: str
    source_url: str
    category: str
    subcategory: str
    system_domain: str
    what_happened: str

    event_date: Optional[str] = None
    detected_at: Optional[str] = None
    primary_source_url: Optional[str] = None

    # V2 classification dimensions. Category is the DISCOVER family; these
    # fields are orthogonal tags so the same Signal can be queried many ways.
    event_type: str = "OTHER"
    strategic_theme: List[str] = field(default_factory=list)
    institution_types: List[str] = field(default_factory=list)
    entity_refs: List[EntityRef] = field(default_factory=list)
    country: str = "CL"

    topics: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)  # legacy/simple display list
    people: List[str] = field(default_factory=list)
    geography: List[str] = field(default_factory=list)
    key_facts: List[str] = field(default_factory=list)
    key_numbers: List[Dict[str, Any]] = field(default_factory=list)
    why_it_matters: str = ""
    who_cares: List[str] = field(default_factory=list)
    possible_implications: List[str] = field(default_factory=list)
    watch_tags: List[str] = field(default_factory=list)

    # CONNECT / TREND hints populated by pipeline or later enrichment jobs.
    connection_keys: List[str] = field(default_factory=list)
    trend_keys: List[str] = field(default_factory=list)
    prospective_evidence: bool = False

    economic_impact_score: int = 0
    regulatory_impact_score: int = 0
    scope_score: int = 0
    novelty_score: int = 0
    actionability_score: int = 0
    source_quality_score: int = 0
    radar_score: int = 0
    confidence_score: int = 0
    distribution: str = "archive"
    validation_status: str = "automatic"
    corroboration_status: str = "unknown"
    additional_sources: List[str] = field(default_factory=list)

    # Language / translation traceability. User-facing Radar is Spanish-only.
    original_language: str = "es"
    display_language: str = "es"
    translation_status: str = "not_required"
    original_title: Optional[str] = None
    original_what_happened: Optional[str] = None
    original_why_it_matters: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SignalConnection:
    """Explicit relationship inferred between two Signals."""
    signal_a_id: str
    signal_b_id: str
    relationship_type: str      # SAME_ENTITY / SAME_THEME / SEQUENCE / SUPPORTS / CONTRADICTS
    strength_score: int         # 0..100
    rationale: str
    shared_entities: List[str] = field(default_factory=list)
    shared_themes: List[str] = field(default_factory=list)


@dataclass
class Trend:
    """A multi-signal pattern detected across time and/or entities."""
    trend_key: str
    title: str
    strategic_theme: str
    status: str                 # emerging / accelerating / established / cooling
    window_days: int
    signal_count: int
    entity_count: int
    current_intensity: float
    previous_intensity: float
    growth_pct: Optional[float]
    confidence_score: int
    why_it_matters: str = ""
    institution_types: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    evidence_signal_ids: List[str] = field(default_factory=list)
    prospective_note: Optional[str] = None


@dataclass
class MetricDefinition:
    """Canonical definition of a comparable public metric used by BENCHMARK."""
    metric_id: str
    name: str
    family: str
    institution_types: List[str]
    unit: str
    description: str
    directionality: str = "neutral"  # higher_better / lower_better / neutral / context_dependent
    aggregation: str = "latest"      # latest / sum / avg / weighted_avg / ratio
    denominator_definition: Optional[str] = None
    numerator_definition: Optional[str] = None
    time_granularity: str = "periodic"
    comparable_across_entities: bool = True
    segment_dimensions: List[str] = field(default_factory=list)
    geography_levels: List[str] = field(default_factory=list)
    source_preferences: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MetricObservation:
    """One sourced observation of a metric for an entity/segment/period."""
    entity_id: str
    metric_id: str
    value: float
    unit: str
    period_start: str
    period_end: str
    source_name: str
    source_url: str
    country: str = "CL"
    institution_type: Optional[str] = None
    geography: Optional[str] = None
    population: Optional[str] = None
    segment: Dict[str, Any] = field(default_factory=dict)
    confidence_score: int = 100
    is_estimated: bool = False
    methodology_note: Optional[str] = None
    retrieved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
