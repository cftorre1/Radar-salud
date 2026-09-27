"""Build the two approved FREE value features from already verified evidence."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

from .editorial_committee import weekly_candidate_eligibility


ARCHETYPES = {
    "REGULATION": "cambio_regulatorio",
    "DATA_PULSE": "dato_contraintuitivo",
    "SANCTION": "señal_temprana",
    "INVESTMENT": "movimiento_competitivo",
    "M&A": "movimiento_competitivo",
}


def _archetype(signal: dict[str, Any]) -> str:
    event = str(signal.get("event_type") or "").upper()
    if event in ARCHETYPES:
        return ARCHETYPES[event]
    if signal.get("data_insights"):
        return "dato_contraintuitivo"
    if signal.get("related_context") or signal.get("historical_connections"):
        return "conexion_entre_señales"
    return "single_signal_deep_dive"


def _https(value: Any) -> bool:
    try:
        parsed = urlparse(str(value))
        return parsed.scheme == "https" and bool(parsed.netloc)
    except ValueError:
        return False


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _verified_theme(theme: dict[str, Any], today: date) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    watch = theme.get("chile_watch") or {}
    if (theme.get("kind") != "global_theme" or not theme.get("id") or not theme.get("title")
            or not theme.get("global_finding") or not theme.get("why_it_matters")
            or watch.get("kind") != "hypothesis"
            or watch.get("trend_chile_status") not in {"not_established", "candidate", "established"}):
        return None
    valid = []
    for source in theme.get("sources") or []:
        published = _day(source.get("published_at"))
        captured = _day(source.get("captured_at"))
        if (source.get("publisher") and source.get("title") and source.get("evidence")
                and _https(source.get("url")) and published and captured
                and published <= captured <= today):
            valid.append(source)
    return (theme, valid) if valid else None


def _score01(value: Any, fallback: float = 0.0) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return fallback


def strategic_weekly_score(signal: dict[str, Any], recent: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Quantitative business-first score for weekly insight selection.

    Uses structured editorial materiality when present and falls back to existing
    product scores without inventing missing dimensions.
    """
    recent = recent or []
    ev = signal.get("editorial_v2") or {}
    mat = ev.get("materiality") if isinstance(ev, dict) else {}
    if not isinstance(mat, dict):
        mat = {}
    financial = _score01(mat.get("financial_impact"), _score01(signal.get("economic_impact_score")))
    operational = _score01(mat.get("operational_impact"), _score01(signal.get("operational_impact_score"), _score01(signal.get("radar_score"))))
    scope = _score01(mat.get("affected_scope"), _score01(signal.get("scope_score"), _score01(signal.get("radar_score"))))
    urgency = _score01(mat.get("time_horizon"), _score01(signal.get("actionability_score"), _score01(signal.get("radar_score"))))
    actionability = _score01(mat.get("actionability"), _score01(signal.get("actionability_score"), _score01(signal.get("radar_score"))))
    evidence = _score01(mat.get("evidence_strength"), _score01(signal.get("source_quality_score")))
    event = str(signal.get("event_type") or "").upper()
    category = str(ev.get("value_category") or "")
    shift = max(
        _score01(signal.get("regulatory_impact_score")),
        _score01(signal.get("economic_impact_score")),
        92.0 if event in {"REGULATION", "M&A"} else 85.0 if event == "INVESTMENT" else 75.0 if event == "SANCTION" else 0.0,
        90.0 if category in {"regulatory_obligation","portfolio_competition","investment_ma","financial_impact"} else 0.0,
    )
    url = signal.get("source_url")
    archetype = _archetype(signal)
    scope_name = (signal.get("scopes") or [None])[0]
    source = signal.get("source_name")
    repetition_hits = sum(1 for x in recent if x.get("source_url")==url)
    repetition_hits += sum(0.35 for x in recent if x.get("archetype")==archetype)
    repetition_hits += sum(0.20 for x in recent if scope_name and x.get("scope")==scope_name)
    repetition_hits += sum(0.15 for x in recent if source and x.get("source_name")==source)
    novelty = max(0.0, 100.0 - min(100.0, repetition_hits * 35.0))
    dims = {
        "financial_impact": financial,
        "operational_impact": operational,
        "regulatory_or_competitive_shift": shift,
        "affected_scope": scope,
        "urgency_time_horizon": urgency,
        "actionability": actionability,
        "evidence_strength": evidence,
        "novelty_non_repetition": novelty,
    }
    weights = {
        "financial_impact": .16,
        "operational_impact": .14,
        "regulatory_or_competitive_shift": .14,
        "affected_scope": .10,
        "urgency_time_horizon": .10,
        "actionability": .14,
        "evidence_strength": .12,
        "novelty_non_repetition": .10,
    }
    return {"score": round(sum(dims[k]*weights[k] for k in weights),2), "dimensions": {k: round(v,2) for k,v in dims.items()}}


def rank_weekly_candidates(signals: list[dict[str, Any]], history: list[dict[str, Any]],
                           as_of: date | None = None) -> list[dict[str, Any]]:
    """Rank publishable signals while making recent repetition explicit and testable."""
    recent = history[-6:]
    recent_archetypes = [x.get("archetype") for x in recent]
    recent_scopes = [x.get("scope") for x in recent]
    recent_sources = [x.get("source_name") for x in recent]
    recent_urls = {x.get("source_url") for x in recent if x.get("source_url")}
    as_of = as_of or date.today()
    ranked = []
    for signal in signals:
        event_day = _day(signal.get("event_date"))
        if (not _https(signal.get("source_url")) or not event_day or event_day > as_of
                or (as_of - event_day).days > 21 or signal.get("source_url") in recent_urls):
            continue
        if signal.get("publication_gate_reason") != "ok":
            continue
        eligibility = weekly_candidate_eligibility(signal)
        if not eligibility["eligible"]:
            continue
        ready = signal.get("publication_ready_score")
        if ready is None or float(ready) < 85:
            continue
        summary = signal.get("card_what") or signal.get("what_happened")
        importance = signal.get("card_why") or signal.get("why_it_matters")
        if not signal.get("title") or not signal.get("source_name") or not summary or not importance:
            continue
        archetype = _archetype(signal)
        scope = (signal.get("scopes") or [None])[0]
        quality = min(100.0, float(signal.get("source_quality_score") or 0))
        if quality < 80:
            continue
        strategic = strategic_weekly_score(signal, recent)
        selection_score = strategic["score"]
        if selection_score < 70:
            continue
        ranked.append({
            "signal": signal,
            "archetype": archetype,
            "scope": scope,
            "base_score": selection_score,
            "strategic_dimensions": strategic["dimensions"],
            "penalties": {
                "same_archetype": 0,
                "same_scope": 0,
                "same_source": 0,
            },
            "selection_score": selection_score,
            "editorial_gate": eligibility,
        })
    return sorted(ranked, key=lambda x: (x["selection_score"], x["signal"].get("event_date", "")), reverse=True)


def build_free_value(snapshot: dict[str, Any], themes: dict[str, Any], history: list[dict[str, Any]] | None = None,
                     today: date | None = None) -> dict[str, Any]:
    history = history or []
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    week_start = monday.isoformat()
    current = next((x for x in reversed(history) if x.get("week_start") == week_start), None)
    prior_history = [x for x in history if x.get("week_start") != week_start]
    theme_rows = [row for x in themes.get("themes", []) if (row := _verified_theme(x, today))]
    theme, verified_sources = theme_rows[0] if theme_rows else (None, [])
    teaser = None
    if theme:
        latest_source = max(verified_sources, key=lambda x: str(x.get("published_at") or ""))
        teaser_finding = str(theme.get("global_finding") or "").split(". ", 1)[0].rstrip(".") + "."
        cross_analysis = theme.get("cross_analysis") or {}
        chile_watch = theme.get("chile_watch") or {}
        teaser = {
            "theme_id": theme["id"],
            "title": theme["title"],
            "excerpt": teaser_finding,
            "what_changed": teaser_finding,
            "why_it_matters": theme["why_it_matters"],
            "what_to_watch": cross_analysis.get("decision_use"),
            "chile_hypothesis": chile_watch.get("text"),
            "chile_hypothesis_status": chile_watch.get("trend_chile_status"),
            "source_count": len(verified_sources),
            "publishers": sorted({x["publisher"] for x in verified_sources}),
            "source_label": " · ".join(sorted({x["publisher"] for x in verified_sources})),
            "published_at": latest_source["published_at"],
            "premium_href": f"global.html#theme-{theme['id']}",
            "evidence_status": "verified_sources",
            "model_trace": {"mode": "deterministic_existing_evidence", "api_call": False,
                            "model": None, "output_id": theme["id"]},
        }
    weekly = None
    signals = snapshot.get("signals") or []
    locked_signal = next((s for s in signals if current and s.get("source_url") == current.get("source_url")), None)
    ranked = rank_weekly_candidates(signals, prior_history, today)
    picked = None
    if locked_signal:
        picked = {
            "signal": locked_signal,
            "archetype": current.get("archetype") or _archetype(locked_signal),
            "scope": current.get("scope") or ((locked_signal.get("scopes") or [None])[0]),
        }
    elif ranked:
        picked = ranked[0]
    if picked:
        signal = picked["signal"]
        support = [
            *(signal.get("key_points") or []),
            *(signal.get("data_insights") or []),
            *(signal.get("affected_processes") or []),
        ]
        reproducible = bool(support) and bool(signal.get("source_url")) and signal.get("publication_gate_reason") == "ok"
        if reproducible:
            weekly = {
                "id": f"{week_start}:{signal.get('event_type','OTHER')}:{picked['archetype']}",
                "title": signal["title"],
                "insight_title": f"Qué cambia esta semana: {signal['title']}",
                "summary": signal.get("card_what") or signal.get("what_happened"),
                "insight_teaser": signal.get("card_why") or signal.get("why_it_matters"),
                "insight_reading": signal.get("why_it_matters") or signal.get("card_why"),
                "decision_use": "Revisar impacto, implementación y próximos hitos con la evidencia original.",
                "source_name": signal["source_name"],
                "source_url": signal["source_url"],
                "event_date": signal["event_date"],
                "scope": picked["scope"],
                "archetype": picked["archetype"],
                "weekly_mode": "single_source_deep_dive",
                "reproducible_analysis": True,
                "supporting_elements": support[:6],
                "model_trace": {"mode": "deterministic_existing_evidence", "api_call": False,
                                "model": None, "output_id": f"weekly:{week_start}:{signal['source_url']}"},
            }
    return {
        "generated_at": snapshot.get("generated_at"),
        "status": "available" if teaser and weekly else "partial",
        "global_teaser": teaser,
        "weekly_insight": weekly,
        "selection_policy": {
            "window_weeks": 6,
            "recent_history_count": len(prior_history[-6:]),
            "current_week_locked": bool(current),
            "selection_method": "quantitative_strategic_score_v2",
            "strategic_dimensions": ["financial_impact","operational_impact","regulatory_or_competitive_shift","affected_scope","urgency_time_horizon","actionability","evidence_strength","novelty_non_repetition"],
            "penalizes": ["repetition_in_novelty_dimension"],
            "fallback": "hide_without_reproducible_evidence_tied_insight",
            "weekly_insight_status": "published_single_source_deep_dive" if weekly else "hidden_fail_closed",
            "minimum_insight_evidence": "two independent sources, or one high-quality source with reproducible deep analysis and explicit decision use",
            "no_forced_frequency": True,
        },
    }
