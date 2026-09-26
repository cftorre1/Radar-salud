from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "editorial_rules_v2.json"


@dataclass(frozen=True)
class EditorialDecision:
    decision: str
    materiality_score: int
    reasons: tuple[str, ...]
    value_category: str


def load_rules(path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _bounded(value: Any) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def _valid_evidence_refs(raw: Any) -> tuple[list[Mapping[str, Any]], set[str]]:
    valid: list[Mapping[str, Any]] = []
    independent_sources: set[str] = set()
    if not isinstance(raw, list):
        return valid, independent_sources
    for ref in raw:
        if not isinstance(ref, Mapping):
            continue
        url = str(ref.get("url") or "").strip()
        source = str(ref.get("source") or "").strip().casefold()
        try:
            parsed = urlparse(url)
        except ValueError:
            continue
        if parsed.scheme != "https" or not parsed.netloc or not source:
            continue
        valid.append(ref)
        independent_sources.add(source)
    return valid, independent_sources


def evaluate_editorial_v2(
    candidate: Mapping[str, Any], rules: Mapping[str, Any] | None = None
) -> EditorialDecision:
    """Evaluate structured editorial evidence without inventing missing impact.

    The collector or editor supplies ``editorial_v2``. Missing structure fails
    closed instead of being inferred from persuasive prose.
    """

    cfg = dict(rules or load_rules())
    evidence = candidate.get("editorial_v2")
    if not isinstance(evidence, Mapping):
        return EditorialDecision(
            "reject", 0, ("invalid_editorial_v2_structure",), "context_without_action"
        )
    reasons: list[str] = []
    required = cfg["required_fields"]
    missing = [field for field in required if not str(evidence.get(field, "")).strip()]
    category = str(evidence.get("value_category") or "context_without_action")
    if category not in cfg["taxonomy"]:
        missing.append("valid_value_category")
    if missing:
        return EditorialDecision(
            "reject", 0, ("missing:" + ",".join(missing),), category
        )

    dimensions = evidence.get("materiality")
    if not isinstance(dimensions, Mapping):
        dimensions = {}
    weights = cfg["materiality"]["dimensions"]
    score = round(sum(_bounded(dimensions.get(name)) * weight for name, weight in weights.items()))
    evidence_refs, independent_sources = _valid_evidence_refs(evidence.get("evidence_refs"))
    if not evidence_refs:
        reasons.append("missing_impact_evidence")

    special = evidence.get("special_piece")
    if special:
        special_cfg = cfg["special_pieces"].get(special)
        if special_cfg is None:
            return EditorialDecision("reject", score, ("unknown_special_piece",), category)
        if special == "weekly_insight":
            mode = str(evidence.get("weekly_mode") or "multi_evidence")
            if mode not in special_cfg["modes"]:
                reasons.append("invalid_weekly_mode")
            elif mode == "multi_evidence":
                if len(independent_sources) < special_cfg["multi_evidence_min_independent_evidence"]:
                    reasons.append("insufficient_independent_evidence")
            else:
                if len(evidence_refs) < special_cfg["single_source_min_evidence"]:
                    reasons.append("missing_impact_evidence")
                if not evidence.get("reproducible_analysis"):
                    reasons.append("missing_reproducible_analysis")
                if not str(evidence.get("decision_use") or "").strip():
                    reasons.append("missing_decision_use")
            if not evidence.get("non_obvious_business_interpretation"):
                reasons.append("missing_non_obvious_business_interpretation")
        elif len(independent_sources) < special_cfg["min_independent_evidence"]:
            reasons.append("insufficient_independent_evidence")
        if special == "global_intelligence":
            if not evidence.get("global_facts_separate_from_chile_hypothesis"):
                reasons.append("global_chile_boundary_missing")
            if not evidence.get("actionable_strategic_reading"):
                reasons.append("missing_actionable_strategic_reading")

    accept_at = cfg["materiality"]["thresholds"]["accept"]
    degrade_at = cfg["materiality"]["thresholds"]["degrade"]
    if score < degrade_at:
        return EditorialDecision("reject", score, tuple(reasons or ["insufficient_materiality"]), category)
    if reasons:
        return EditorialDecision("degrade", score, tuple(reasons), category)
    if evidence.get("routine_repeated") and score < accept_at:
        return EditorialDecision("group", score, ("routine_repeated",), category)
    if score < accept_at:
        return EditorialDecision("degrade", score, tuple(reasons or ["context_only"]), category)
    return EditorialDecision("accept", score, ("material_and_evidenced",), category)
