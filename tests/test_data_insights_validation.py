from radar_salud.data_insights import _month_key, _safe_numeric, family_from_title

def test_invalid_month_is_not_a_comparable_period():
    assert _month_key("2026-13") is None
    assert _month_key("2026-00") is None
    assert _month_key("2026-09")== (2026,9)

def test_boolean_does_not_become_a_financial_observation():
    assert _safe_numeric(True) is None
    assert _safe_numeric("1.000") is None
    assert _safe_numeric(0)==0

def test_unknown_family_is_not_guessed():
    assert family_from_title("Resumen de información") is None
