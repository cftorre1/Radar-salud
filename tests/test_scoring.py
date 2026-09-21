from src.radar_salud.scoring import ScoreInputs, calculate_radar_score, relevance_band, confidence_gate
from src.radar_salud.distribution import choose_distribution, UserPlan


def test_score_is_bounded_and_weighted():
    s = ScoreInputs(100, 100, 100, 100, 100, 100)
    assert calculate_radar_score(s) == 100
    assert relevance_band(100) == "critical"


def test_confidence_gate():
    assert confidence_gate(95) == "publishable"
    assert confidence_gate(80) == "cross_check"
    assert confidence_gate(70) == "hold"


def test_daily_not_immediate_without_watch():
    out = choose_distribution(92, 96, UserPlan("pro"), ["isapres"], [])
    assert out == "daily_digest"


def test_watch_can_break_daily_rule():
    out = choose_distribution(92, 96, UserPlan("pro"), ["isapres"], ["isapres"])
    assert out == "watch_immediate"


def test_free_is_weekly():
    out = choose_distribution(80, 95, UserPlan("free"), [], [])
    assert out == "weekly_digest"
