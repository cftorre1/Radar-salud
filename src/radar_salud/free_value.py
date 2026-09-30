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


def score_global_teaser(theme: dict[str, Any], verified_sources: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Rank eligible Global themes by executive/commercial value.

    Freshness is a gate, not a scoring advantage: at least one verified source
    must have been published in the last 14 days. Once eligible, newer does not
    score higher merely for being newer.
    """
    profile = theme.get("home_teaser_profile") or {}
    published_days=[_day(x.get("published_at")) for x in verified_sources]
    latest=max((x for x in published_days if x), default=None)
    eligible=bool(latest and 0 <= (today-latest).days <= 14)
    evidence = min(100.0, 55.0 + 15.0 * len({x.get("publisher") for x in verified_sources if x.get("publisher")}))
    dims = {
        "commercial_hook": _score01(profile.get("commercial_hook"), 70.0),
        "strategic_relevance": _score01(profile.get("executive_relevance"), 70.0),
        "decision_usefulness": _score01(profile.get("decision_usefulness"), 70.0),
        "conversation_potential": _score01(profile.get("conversation_potential"), 70.0),
        "evidence_strength": evidence,
    }
    weights = {
        "commercial_hook": .30,
        "strategic_relevance": .30,
        "decision_usefulness": .20,
        "conversation_potential": .15,
        "evidence_strength": .05,
    }
    score=round(sum(dims[k] * weights[k] for k in weights), 2) if eligible else -1.0
    return {
        "score": score,
        "eligible": eligible,
        "freshness_gate_days": 14,
        "latest_source_date": latest.isoformat() if latest else None,
        "dimensions": dims,
    }


def strategic_weekly_score(signal: dict[str, Any], recent: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Rank weekly Insight candidates with an explicit product hierarchy.

    1) Strategic relevance is the primary criterion.
    2) Commercial hook breaks ties among strategically strong candidates.
    3) Decision usefulness and evidence protect quality.
    Freshness is an eligibility gate, not a substitute for relevance.
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
    magnitude = _score01(mat.get("magnitude"), _score01(signal.get("radar_score")))
    event = str(signal.get("event_type") or "").upper()
    category = str(ev.get("value_category") or "")
    shift = max(
        _score01(signal.get("regulatory_impact_score")),
        _score01(signal.get("economic_impact_score")),
        92.0 if event in {"REGULATION", "M&A"} else 88.0 if event == "INVESTMENT" else 80.0 if event == "SANCTION" else 0.0,
        92.0 if category in {"regulatory_obligation","portfolio_competition","investment_ma","financial_impact"} else 0.0,
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

    strategic_relevance = (
        .18*financial + .18*operational + .22*shift + .15*scope
        + .12*urgency + .15*actionability
    )
    commercial_hook = .35*magnitude + .30*shift + .20*novelty + .15*scope
    decision_usefulness = .60*actionability + .40*urgency
    selection_score = .55*strategic_relevance + .25*commercial_hook + .15*decision_usefulness + .05*evidence

    dims = {
        "strategic_relevance": strategic_relevance,
        "commercial_hook": commercial_hook,
        "decision_usefulness": decision_usefulness,
        "financial_impact": financial,
        "operational_impact": operational,
        "regulatory_or_competitive_shift": shift,
        "affected_scope": scope,
        "urgency_time_horizon": urgency,
        "actionability": actionability,
        "evidence_strength": evidence,
        "magnitude": magnitude,
        "novelty_non_repetition": novelty,
    }
    return {"score": round(selection_score,2), "dimensions": {k: round(v,2) for k,v in dims.items()}}

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
    return sorted(ranked, key=lambda x: (
        x["strategic_dimensions"].get("strategic_relevance", 0),
        x["strategic_dimensions"].get("commercial_hook", 0),
        x["strategic_dimensions"].get("decision_usefulness", 0),
        x["selection_score"],
        x["signal"].get("event_date", "")
    ), reverse=True)


def build_free_value(snapshot: dict[str, Any], themes: dict[str, Any], history: list[dict[str, Any]] | None = None,
                     today: date | None = None) -> dict[str, Any]:
    history = history or []
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    week_start = monday.isoformat()
    current = next((x for x in reversed(history) if x.get("week_start") == week_start), None)
    prior_history = [x for x in history if x.get("week_start") != week_start]
    theme_rows = [row for x in themes.get("themes", []) if (row := _verified_theme(x, today))]
    scored_themes = [
        (score_global_teaser(theme, verified_sources, today), theme, verified_sources)
        for theme, verified_sources in theme_rows
    ]
    scored_themes = [row for row in scored_themes if row[0].get("eligible")]
    scored_themes.sort(key=lambda row: row[0]["score"], reverse=True)
    teaser_score, theme, verified_sources = scored_themes[0] if scored_themes else (None, None, [])
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
            "teaser_score": teaser_score,
            "model_trace": {"mode": "deterministic_existing_evidence", "api_call": False,
                            "model": None, "output_id": theme["id"]},
        }
    weekly = None
    signals = snapshot.get("signals") or []
    ranked = rank_weekly_candidates(signals, prior_history, today)
    picked = ranked[0] if ranked else None
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
            "current_week_locked": False,
            "selection_method": "strategic_relevance_first_then_commercial_hook_v3",
            "strategic_dimensions": ["financial_impact","operational_impact","regulatory_or_competitive_shift","affected_scope","urgency_time_horizon","actionability","evidence_strength","novelty_non_repetition"],
            "penalizes": ["repetition_in_novelty_dimension"],
            "fallback": "hide_without_reproducible_evidence_tied_insight",
            "weekly_insight_status": "published_single_source_deep_dive" if weekly else "hidden_fail_closed",
            "minimum_insight_evidence": "two independent sources, or one high-quality source with reproducible deep analysis and explicit decision use",
            "no_forced_frequency": True,
        },
    }
