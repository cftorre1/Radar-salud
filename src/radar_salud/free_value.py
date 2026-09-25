"""Build the two approved FREE value features from already verified evidence."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse


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
            or not theme.get("why_it_matters") or watch.get("kind") != "hypothesis"
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


def _curated_weekly(signal: dict[str, Any], processes: list[str]) -> dict[str, str] | None:
    """Return an evidence-tied analytical reading, or fail closed."""
    expected_url = "https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n11156"
    evidence = " ".join(str(signal.get(key) or "") for key in
                        ("card_what", "card_why", "what_happened", "why_it_matters")).lower()
    evidence += " " + " ".join(str(x) for key in ("key_points", "risk_notes")
                                 for x in (signal.get(key) or [])).lower()
    required = ("acredit", "registro", "bono", "1 de noviembre")
    required_processes = {"Beneficios / Cobertura", "Tecnología / Canales", "Operaciones"}
    if (signal.get("title") != "Resolución Exenta IF/N°11156"
            or str(signal.get("source_url") or "").rstrip("/") != expected_url
            or not all(token in evidence for token in required)
            or not required_processes.issubset(set(processes))):
        return None
    return {
        "title": "TEA: la cobertura sin tope depende de un flujo operativo completo",
        "teaser": ("Cobertura, registro y compra de bonos no son cambios separados: "
                   "convergen en un único hito operativo el 1 de noviembre."),
        "reading": (
            "La conexión ejecutiva une la regla de cobertura con su implementación: "
            "acreditación y registro alimentan la validación, y esa validación debe habilitar "
            "la compra directa de bonos sin tope. La fecha común —1 de noviembre— convierte "
            "beneficios, canales y operaciones en un solo hito de cumplimiento."
        ),
        "connection_type": "cross_process_implementation",
    }


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
        ready = signal.get("publication_ready_score")
        if ready is None or float(ready) < 85:
            continue
        summary = signal.get("card_what") or signal.get("what_happened")
        importance = signal.get("card_why") or signal.get("why_it_matters")
        if not signal.get("title") or not signal.get("source_name") or not summary or not importance:
            continue
        archetype = _archetype(signal)
        scope = (signal.get("scopes") or [None])[0]
        base = float(signal.get("radar_score") or signal.get("editorial_relevance") or 0)
        quality = min(100.0, float(signal.get("source_quality_score") or 0))
        if base < 65 or quality < 80:
            continue
        penalties = {
            "same_archetype": 24 if archetype in recent_archetypes else 0,
            "same_scope": 14 if scope and scope in recent_scopes else 0,
            "same_source": 10 if signal.get("source_name") in recent_sources else 0,
        }
        selection_score = round(base * .7 + quality * .3 - sum(penalties.values()), 2)
        if selection_score < 65:
            continue
        ranked.append({
            "signal": signal,
            "archetype": archetype,
            "scope": scope,
            "base_score": round(base * .7 + quality * .3, 2),
            "penalties": penalties,
            "selection_score": selection_score,
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
        teaser_finding = str(theme["why_it_matters"]).split(". ", 1)[0].rstrip(".") + "."
        teaser = {
            "theme_id": theme["id"],
            "title": theme["title"],
            "excerpt": teaser_finding,
            "source_count": len(verified_sources),
            "publishers": sorted({x["publisher"] for x in verified_sources}),
            "source_label": " · ".join(sorted({x["publisher"] for x in verified_sources})),
            "published_at": latest_source["published_at"],
            "premium_href": f"global.html#theme-{theme['id']}",
            "evidence_status": "verified_sources",
            "model_trace": {"mode": "deterministic_existing_evidence", "api_call": False,
                            "model": None, "output_id": theme["id"]},
        }
    candidates = rank_weekly_candidates(snapshot.get("signals", []), prior_history, today)
    if current:
        recorded = next((x for x in candidates if x["signal"].get("source_url") == current.get("source_url")), None)
        candidates = ([recorded] + [x for x in candidates if x is not recorded]) if recorded else []
    weekly = None
    if candidates:
        selected = candidates[0]
        signal = selected["signal"]
        processes = [str(x).strip() for x in signal.get("affected_processes") or [] if str(x).strip()]
        curated = _curated_weekly(signal, processes)
        importance = signal.get("card_why") or signal.get("why_it_matters")
        if curated:
            weekly = {
                "id": f"{monday.isoformat()}-{signal.get('event_type', 'signal').lower()}",
                "week_start": week_start,
                "archetype": selected["archetype"],
                "title": signal["title"],
                "insight_title": curated["title"],
                "insight_teaser": curated["teaser"],
                "summary": signal.get("card_what") or signal.get("what_happened"),
                "why_it_matters": importance,
                "insight_reading": curated["reading"],
                "insight_basis": {
                    "kind": selected["archetype"],
                    "connection_type": curated["connection_type"],
                    "affected_processes": processes,
                    "is_single_signal": True,
                },
                "source_name": signal.get("source_name"),
                "source_url": signal["source_url"],
                "event_date": signal["event_date"],
                "scope": selected["scope"],
                "evidence_status": "verified_source",
                "model_trace": {"mode": "deterministic_existing_evidence", "api_call": False,
                                "model": None, "output_id": f"{week_start}-{signal.get('event_type', 'signal').lower()}"},
                "selection": {
                    "base_score": selected["base_score"],
                    "diversity_penalties": selected["penalties"],
                    "selection_score": selected["selection_score"],
                    "eligible_candidates": len(candidates),
                },
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
            "penalizes": ["archetype", "scope", "source"],
            "fallback": "hide_without_curated_evidence_tied_insight",
            "no_forced_frequency": True,
        },
    }
