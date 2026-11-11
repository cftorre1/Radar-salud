"""Global «noticia de la semana» on Home (Dirección 11-nov-2026): one Global item per week, rule global_weekly_pick_v1."""
from datetime import date

from radar_salud.global_daily_feed import weekly_pick


def card(i, day, priority, *, es=True, summary="Texto de la noticia.", title=None):
    c = {"id": i, "title": title or f"Title {i}", "url": f"https://example.org/{i}", "published_at": day, "priority": priority,
         "source_label": "FDA"}
    if es:
        c.update(title_es=f"Título {i}", description_es=summary, translation={"status": "translated", "verified": True})
    else:
        c.update(summary_es="Resumen de Alicanto.", translation={"status": "summarized", "kind": "summary", "verified": True})
    return c


def test_window_is_the_week_before_through_this_monday_and_spanish_first():
    cards = [card("a", "2026-11-09", 90, es=False), card("b", "2026-11-06", 76), card("c", "2026-11-02", 81),
             card("d", "2026-11-01", 99), card("e", "2026-11-10", 99)]
    p = weekly_pick(cards, date(2026, 11, 11))
    assert p["week_anchor"] == "2026-11-09" and p["window"] == ["2026-11-02", "2026-11-09"]
    # d is before the window and e after this week's Monday; a (English title) loses to Spanish titles.
    assert p["id"] == "c" and p["title"] == "Título c" and p["summary"] == "Texto de la noticia." and p["title_in_spanish"]
    assert p["href"] == "global.html#semana" and p["rule"] == "global_weekly_pick_v1"
    # Stable through the week: Sunday gives the same pick.
    assert weekly_pick(cards, date(2026, 11, 15))["id"] == "c"


def test_title_and_text_come_from_the_same_card_and_a_repeated_title_is_dropped():
    p = weekly_pick([card("x", "2026-11-09", 50, summary="Título x.")], date(2026, 11, 9))
    assert p["title"] == "Título x" and p["summary"] is None


def test_summary_only_items_are_a_fallback_and_an_empty_week_hides_the_card():
    p = weekly_pick([card("a", "2026-11-09", 90, es=False)], date(2026, 11, 12))
    # Decision 3 (11-nov): the row title is the first sentence of the verified Alicanto summary (licence forbids translating).
    assert p["id"] == "a" and p["title"] == "Resumen de Alicanto" and p["summary"] is None and p["title_in_spanish"] is True
    assert weekly_pick([card("old", "2026-10-01", 99)], date(2026, 11, 12)) is None


def test_published_feed_carries_the_pick():
    import json
    from pathlib import Path
    d = json.loads((Path(__file__).resolve().parents[1] / "web/data/global_feed.json").read_text(encoding="utf-8"))
    assert d["weekly_pick"] is None or d["weekly_pick"]["rule"] == "global_weekly_pick_v1"


def test_pick_summary_names_the_day_instead_of_hoy():
    from radar_salud.global_daily_feed import _no_relative_day
    assert _no_relative_day("La FDA emitió hoy una guía; ayer hubo otra.", date(2026, 11, 2)) == \
        "La FDA emitió el 2 nov 2026 una guía; el 1 nov 2026 hubo otra."
