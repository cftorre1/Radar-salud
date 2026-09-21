from datetime import date, timedelta
from radar_salud.models import Signal
from radar_salud.connect import connection_strength, connect_signals
from radar_salud.trends import detect_trends
from radar_salud.benchmark import benchmark_signal_activity


def sig(title, entity, theme, day, institution_type="PRIVATE_PROVIDER", event_type="INVESTMENT_ANNOUNCEMENT"):
    return Signal(
        title=title,
        source_name="Test",
        source_type="official",
        source_url="https://example.com",
        category="Mercado",
        subcategory="Inversión",
        system_domain="HEALTH_PROVIDERS",
        what_happened=title,
        event_date=day.isoformat(),
        entities=[entity],
        institution_types=[institution_type],
        strategic_theme=[theme],
        event_type=event_type,
        confidence_score=95,
        radar_score=80,
    )


def test_connect_same_entity_and_theme():
    d = date(2026, 9, 20)
    a = sig("A", "Clínica X", "AI", d)
    b = sig("B", "Clínica X", "AI", d)
    assert connection_strength(a, b) >= 70
    c = connect_signals("a", a, "b", b)
    assert c is not None
    assert c.relationship_type == "SAME_ENTITY"


def test_trend_requires_multiple_entities_and_signals():
    as_of = date(2026, 9, 20)
    entities = ["Clínica A", "Clínica B", "Clínica C"]
    signals = []
    for i in range(6):
        signals.append(sig(str(i), entities[i % 3], "AI", as_of - timedelta(days=i * 5)))
    trends = detect_trends(signals, as_of=as_of)
    assert len(trends) == 1
    assert trends[0].strategic_theme == "ai"
    assert trends[0].entity_count == 3


def test_benchmark_counts_visible_activity():
    d = date(2026, 9, 20)
    signals = [
        sig("1", "A", "AI", d),
        sig("2", "A", "AI", d),
        sig("3", "B", "AI", d),
    ]
    result = benchmark_signal_activity(signals, strategic_theme="AI")
    assert result["A"]["signals"] == 2
    assert result["B"]["signals"] == 1
