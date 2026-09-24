from datetime import date

from radar_salud.free_value import build_free_value, rank_weekly_candidates


def signal(title, event, score=90, scope="Isapres", source="Fuente oficial"):
    return {
        "title": title, "event_type": event, "event_date": "2026-09-23",
        "source_name": source, "source_url": f"https://example.org/{title}",
        "scopes": [scope], "radar_score": score, "source_quality_score": 100,
        "publication_ready_score": 100, "publication_gate_reason": "ok",
        "what_happened": f"Ocurrió {title}", "why_it_matters": f"Importa {title}",
    }


def test_repetition_penalties_change_weekly_ranking():
    regulation = signal("regulación", "REGULATION", 96)
    investment = signal("inversión", "INVESTMENT", 82, "Prestadores", "Fuente económica")
    first = rank_weekly_candidates([regulation, investment], [])
    assert first[0]["signal"]["title"] == "regulación"
    history = [{"archetype": "cambio_regulatorio", "scope": "Isapres", "source_name": "Fuente oficial"}]
    diverse = rank_weekly_candidates([regulation, investment], history)
    assert diverse[0]["signal"]["title"] == "inversión"
    assert all(x["signal"]["title"] != "regulación" for x in diverse)


def test_free_value_is_evidence_backed_and_teaser_is_fractional():
    snapshot = {"generated_at": "2026-09-24T18:00:00Z", "signals": [signal("regulación", "REGULATION")]}
    themes = {"themes": [{"id": "theme-1", "kind": "global_theme", "title": "Tema global", "global_finding": "Análisis extenso",
                           "why_it_matters": "Una fracción útil y autosuficiente.",
                           "chile_watch": {"kind": "hypothesis", "trend_chile_status": "not_established"},
                           "sources": [{"publisher": "WHO", "title": "Informe", "url": "https://who.int/report",
                                        "published_at": "2026-06-01", "captured_at": "2026-09-24", "evidence": "Hallazgo explícito"},
                                       {"publisher": "Reuters", "title": "Nota", "url": "https://reuters.com/note",
                                        "published_at": "2026-09-18", "captured_at": "2026-09-24", "evidence": "Hallazgo contrastado"}]}]}
    result = build_free_value(snapshot, themes, today=date(2026, 9, 24))
    assert result["weekly_insight"]["evidence_status"] == "verified_source"
    assert result["weekly_insight"]["week_start"] == "2026-09-21"
    assert result["global_teaser"]["premium_href"] == "global.html#theme-theme-1"
    assert "global_finding" not in result["global_teaser"]
    assert result["selection_policy"]["no_forced_frequency"] is True
    assert result["weekly_insight"]["model_trace"]["api_call"] is False


def test_no_verified_signal_does_not_force_weekly_content():
    result = build_free_value({"signals": [{"title": "sin fuente"}]}, {"themes": []})
    assert result["weekly_insight"] is None
    assert result["status"] == "partial"


def test_current_week_is_locked_and_next_week_penalizes_repetition():
    regulation = signal("regulación", "REGULATION", 96)
    investment = signal("inversión", "INVESTMENT", 82, "Prestadores", "Fuente económica")
    history = [{"week_start": "2026-09-21", "source_url": regulation["source_url"],
                "archetype": "cambio_regulatorio", "scope": "Isapres", "source_name": "Fuente oficial"}]
    current = build_free_value({"signals": [regulation, investment]}, {"themes": []}, history, date(2026, 9, 24))
    assert current["weekly_insight"]["title"] == "regulación"
    assert current["selection_policy"]["current_week_locked"] is True
    following = build_free_value({"signals": [regulation, investment]}, {"themes": []}, history, date(2026, 9, 28))
    assert following["weekly_insight"]["title"] == "inversión"


def test_old_unsafe_or_repeated_signal_fails_closed():
    unsafe = signal("riesgo", "OTHER", 99)
    unsafe["source_url"] = "javascript:alert(1)"
    unsafe["event_date"] = "2025-01-01"
    assert rank_weekly_candidates([unsafe], [], date(2026, 9, 24)) == []
    used = signal("regulación", "REGULATION", 99)
    history = [{"source_url": used["source_url"], "archetype": "cambio_regulatorio",
                "scope": "Isapres", "source_name": "Fuente oficial"}]
    assert rank_weekly_candidates([used], history, date(2026, 9, 24)) == []


def test_spoofed_global_source_never_becomes_verified_teaser():
    fake = {"kind": "global_theme", "id": "fake", "title": "Tema", "why_it_matters": "Importa",
            "chile_watch": {"kind": "hypothesis", "trend_chile_status": "not_established"},
            "sources": [{"publisher": "Unknown", "url": "javascript:alert(1)"}]}
    result = build_free_value({"signals": []}, {"themes": [fake]}, today=date(2026, 9, 24))
    assert result["global_teaser"] is None and result["status"] == "partial"
