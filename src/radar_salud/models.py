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
    name: str
    entity_type: str = "organization"
    institution_type: Optional[str] = None
    subsector: Optional[str] = None
    country: str = "CL"
    region: Optional[str] = None
    ownership_type: Optional[str] = None
    canonical_id: Optional[str] = None

@dataclass
class Signal:
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
    event_type: str = "OTHER"
    strategic_theme: List[str] = field(default_factory=list)
    institution_types: List[str] = field(default_factory=list)
    entity_refs: List[EntityRef] = field(default_factory=list)
    country: str = "CL"
    topics: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    people: List[str] = field(default_factory=list)
    geography: List[str] = field(default_factory=list)
    key_facts: List[str] = field(default_factory=list)
    key_numbers: List[Dict[str, Any]] = field(default_factory=list)
    why_it_matters: str = ""
    who_cares: List[str] = field(default_factory=list)
    possible_implications: List[str] = field(default_factory=list)
    watch_tags: List[str] = field(default_factory=list)
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
    source_documents: List[Dict[str, Any]] = field(default_factory=list)
    key_points: List[str] = field(default_factory=list)
    risk_notes: List[str] = field(default_factory=list)
    data_insights: List[str] = field(default_factory=list)
    validity_text: Optional[str] = None
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
    signal_a_id: str
    signal_b_id: str
    relationship_type: str
    strength_score: int
    rationale: str
    shared_entities: List[str] = field(default_factory=list)
    shared_themes: List[str] = field(default_factory=list)

@dataclass
class Trend:
    trend_key: str
    title: str
    strategic_theme: str
    status: str
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
    metric_id: str
    name: str
    family: str
    institution_types: List[str]
    unit: str
    description: str
    directionality: str = "neutral"
    aggregation: str = "latest"
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
