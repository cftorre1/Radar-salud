from src.radar_salud.demo_multisource_cli import demo_signals
from src.radar_salud.personal_digest import build_personal_daily_digest
from src.radar_salud.personalization import DEFAULT_PROFILES


def test_digest_changes_by_profile():
    isapre = build_personal_daily_digest(demo_signals(), DEFAULT_PROFILES["isapre"])
    mutual = build_personal_daily_digest(demo_signals(), DEFAULT_PROFILES["mutualidad"])
    assert isapre.index("Superintendencia actualiza") < isapre.index("SUSESO publica")
    assert mutual.index("SUSESO publica") < mutual.index("Superintendencia actualiza")
