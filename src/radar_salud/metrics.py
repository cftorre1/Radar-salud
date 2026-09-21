from __future__ import annotations
from collections import defaultdict
from typing import Iterable, Dict, List, Optional
from .models import MetricDefinition, MetricObservation


def validate_observation(obs: MetricObservation, definition: MetricDefinition) -> List[str]:
    errors: List[str] = []
    if obs.metric_id != definition.metric_id:
        errors.append("metric_id mismatch")
    if obs.unit != definition.unit:
        errors.append(f"unit mismatch: expected {definition.unit}, got {obs.unit}")
    if not (0 <= obs.confidence_score <= 100):
        errors.append("confidence_score must be 0..100")
    if definition.institution_types and obs.institution_type and obs.institution_type not in definition.institution_types:
        errors.append("institution_type not supported by metric definition")
    return errors


def latest_by_entity(observations: Iterable[MetricObservation], metric_id: str) -> Dict[str, MetricObservation]:
    latest: Dict[str, MetricObservation] = {}
    for obs in observations:
        if obs.metric_id != metric_id:
            continue
        previous = latest.get(obs.entity_id)
        if previous is None or obs.period_end > previous.period_end:
            latest[obs.entity_id] = obs
    return latest


def benchmark_metric(observations: Iterable[MetricObservation], definition: MetricDefinition) -> List[dict]:
    """Return a transparent comparable table. No best/worst judgment is emitted."""
    if not definition.comparable_across_entities:
        raise ValueError(f"Metric {definition.metric_id} is not comparable across entities")
    latest = latest_by_entity(observations, definition.metric_id)
    rows = []
    for entity_id, obs in latest.items():
        rows.append({
            "entity_id": entity_id,
            "metric_id": obs.metric_id,
            "value": obs.value,
            "unit": obs.unit,
            "period_end": obs.period_end,
            "source_name": obs.source_name,
            "source_url": obs.source_url,
            "confidence_score": obs.confidence_score,
            "segment": obs.segment,
        })
    return sorted(rows, key=lambda r: r["value"], reverse=True)


def group_metric_summary(observations: Iterable[MetricObservation], metric_id: str, group_key: str) -> Dict[str, dict]:
    """Simple cohort summary over explicit segment fields (e.g. sex, region, age_band)."""
    grouped = defaultdict(list)
    for obs in observations:
        if obs.metric_id != metric_id:
            continue
        group = obs.segment.get(group_key)
        if group is not None:
            grouped[str(group)].append(obs.value)
    return {
        group: {"count": len(values), "mean": sum(values) / len(values), "min": min(values), "max": max(values)}
        for group, values in grouped.items()
    }
