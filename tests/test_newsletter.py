import importlib.util
import json

from src.radar_salud.newsletter import render_free_weekly, render_premium_weekly, weekly_material


def signal(title="Cambio", **values):
    row = {
        "title": title,
        "event_date": "2026-09-24",
        "ingestion_mode": "LIVE",
        "radar_score": 85,
        "confidence_score": 90,
        "validation_status": "validated",
        "source_url": "https://example.org/source",
        "source_name": "Fuente oficial",
        "what_happened": "Se publicó un cambio material y verificable.",
        "why_it_matters": "Requiere revisar procesos durante esta semana.",
        "signal_types": ["Normativa"],
        "scopes": ["Isapres"],
    }
    row.update(values)
    return row


def test_weekly_material_fails_closed_for_backfill_old_low_confidence_and_missing_source():
    rows = [
        signal("Elegible"),
        signal("Histórico", ingestion_mode="BACKFILL"),
        signal("Antiguo", event_date="2026-09-10"),
        signal("Incierto", confidence_score=70),
        signal("Sin fuente", source_url=""),
    ]
    assert [x["title"] for x in weekly_material(rows, "2026-09-24")] == ["Elegible"]


def test_free_is_summarized_and_premium_is_complete_and_personalized():
    material = weekly_material([
        signal("Norma Isapres"),
        signal("Prestadores", scopes=["Prestadores"], radar_score=80),
    ], "2026-09-24")
    free = render_free_weekly(material, "2026-09-24")
    premium = render_premium_weekly(material, "2026-09-24", ["Isapres"])
    assert free and "Qué ocurrió:" not in free[1] and "Fuente original" in free[1]
    assert premium and "Norma Isapres" in premium[1] and "Por qué importa:" in premium[1]
    assert "Prestadores" not in premium[1]


def test_no_relevant_material_means_no_email():
    assert render_free_weekly([], "2026-09-24") is None
    assert render_premium_weekly([], "2026-09-24") is None


def test_present_api_key_cannot_bypass_disabled_delivery(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("weekly_sender", "scripts/send_weekly_digest.py")
    sender = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sender)
    config = tmp_path / "subscription.json"
    config.write_text(json.dumps({
        "provider": "buttondown", "capture_enabled": False, "send_enabled": False,
        "privacy_approved": False, "double_opt_in": True,
    }))
    data = tmp_path / "radar.json"
    data.write_text(json.dumps({"signals": [signal()]}))
    calls = []
    monkeypatch.setenv("BUTTONDOWN_API_KEY", "present-but-must-not-be-used")
    monkeypatch.setattr(sender, "urlopen", lambda *args, **kwargs: calls.append(args))
    assert sender.main(config, data) == 0
    assert calls == []
