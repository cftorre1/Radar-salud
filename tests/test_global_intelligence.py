import copy
import json
from pathlib import Path

import pytest

from radar_salud.global_intelligence import export, load, validate


SOURCE = Path("data/global/themes.json")


def test_real_global_themes_are_premium_traceable_and_not_chile_trends(tmp_path):
    payload = load(SOURCE)
    assert payload["access_tier"] == "PREMIUM"
    assert len(payload["themes"]) >= 3
    for theme in payload["themes"]:
        assert theme["kind"] == "global_theme"
        assert theme["chile_watch"]["kind"] == "hypothesis"
        assert theme["chile_watch"]["trend_chile_status"] == "not_established"
        assert theme["chile_watch"]["compatible_local_signals"] == []
        assert all(s["url"].startswith("https://") and s["evidence"] for s in theme["sources"])
    target = tmp_path / "global.json"
    export(SOURCE, target)
    assert json.loads(target.read_text()) == payload


def test_global_theme_rejects_publisher_domain_spoof():
    payload = load(SOURCE)
    bad = copy.deepcopy(payload)
    bad["themes"][0]["sources"][0]["url"] = "https://example.com/reuters-copy"
    with pytest.raises(ValueError, match="publisher/domain mismatch"):
        validate(bad)


def test_global_theme_cannot_become_chile_trend_without_local_evidence():
    payload = load(SOURCE)
    bad = copy.deepcopy(payload)
    bad["themes"][0]["chile_watch"]["trend_chile_status"] = "established"
    with pytest.raises(ValueError, match="canonical Chile evidence pipeline"):
        validate(bad)


def test_foreign_urls_cannot_promote_candidate_or_established_trend_chile():
    payload = load(SOURCE)
    global_urls = [theme["sources"][0]["url"] for theme in payload["themes"]]
    candidate = copy.deepcopy(payload)
    candidate["themes"][0]["chile_watch"].update(
        trend_chile_status="candidate",
        compatible_local_signals=[{"verified": True, "url": global_urls[0]}],
    )
    with pytest.raises(ValueError, match="canonical Chile evidence pipeline"):
        validate(candidate)
    established = copy.deepcopy(payload)
    established["themes"][0]["chile_watch"].update(
        trend_chile_status="established",
        review_status="approved",
        compatible_local_signals=[
            {"verified": True, "url": global_urls[0]},
            {"verified": True, "url": global_urls[1]},
        ],
    )
    with pytest.raises(ValueError, match="canonical Chile evidence pipeline"):
        validate(established)


def test_global_source_dates_are_ordered_and_never_future_dated():
    payload = load(SOURCE)
    bad_order = copy.deepcopy(payload)
    bad_order["themes"][0]["sources"][0].update(
        published_at="2026-09-25", captured_at="2026-09-24"
    )
    with pytest.raises(ValueError, match="published_at <= captured_at <= generated_at"):
        validate(bad_order)
    future = copy.deepcopy(payload)
    future["generated_at"] = "2099-01-02T00:00:00Z"
    future["themes"][0]["sources"][0].update(
        published_at="2099-01-01", captured_at="2099-01-01"
    )
    with pytest.raises(ValueError, match="cannot be in the future"):
        validate(future)


def test_global_theme_rejects_unapproved_material():
    payload = load(SOURCE)
    bad = copy.deepcopy(payload)
    bad["themes"][0]["sources"][0]["material_type"] = "marketing"
    with pytest.raises(ValueError, match="research/outlook/report"):
        validate(bad)
