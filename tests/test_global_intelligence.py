import copy
import json
from pathlib import Path

import pytest

from radar_salud.global_intelligence import export, load, validate


SOURCE = Path("data/global/themes.json")


def test_public_global_sample_matches_canonical_checked_research():
    canonical = load(SOURCE)
    public = json.loads(Path("web/data/global_themes.json").read_text(encoding="utf-8"))
    assert public == canonical


def test_pwc_research_is_publicly_traceable_without_chile_trend_transfer():
    themes = load(SOURCE)['themes']
    ai = next(t for t in themes if t['id'] == 'global-health-ai-operating-model-2026')
    report = next(s for s in ai['sources'] if s['publisher'] == 'PwC')
    assert report['published_at'] == '2026-05-04'
    assert report['url'].startswith('https://www.pwc.com/')
    assert ai['chile_watch']['trend_chile_status'] == 'not_established'


def test_direct_who_report_preserves_reuters_attribution():
    workforce=next(t for t in load(SOURCE)['themes'] if t['id']=='global-workforce-pressure-2026')
    who=next(s for s in workforce['sources'] if s['publisher']=='WHO')
    assert who['published_at']=='2026-06-22'
    assert who['url']=='https://www.who.int/publications/i/item/9789240122925'
    assert '11,1 millones' not in who['evidence']
    assert workforce['chile_watch']['trend_chile_status']=='not_established'


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
        assert set(theme["cross_analysis"]) == {"recurring_pattern", "tensions", "decision_use"}
        for source in theme["sources"]:
            if source["material_type"] != "high_trust_press":
                assert 3 <= len(source["analysis"]["key_findings"]) <= 5
                assert source["analysis"]["figures"]
                assert source["analysis"]["implications"]
                assert source["analysis"]["methodology"]
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


def test_long_form_sources_fail_closed_without_structured_depth():
    payload = load(SOURCE)
    missing = copy.deepcopy(payload)
    next(s for t in missing["themes"] for s in t["sources"] if s["material_type"] != "high_trust_press").pop("analysis")
    with pytest.raises(ValueError, match="structured analysis"):
        validate(missing)
    for findings in ([], ["uno"], ["uno", "dos"]):
        shallow = copy.deepcopy(payload)
        next(s for t in shallow["themes"] for s in t["sources"] if s["material_type"] != "high_trust_press")["analysis"]["key_findings"] = findings
        with pytest.raises(ValueError, match="invalid key_findings"):
            validate(shallow)
