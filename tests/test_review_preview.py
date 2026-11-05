"""Dirección 4-nov-2026: fichas held only by their first-review gate get an unlisted staging preview; nothing else."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from radar_salud import review_preview as rp  # noqa: E402

FICHA = {"family": "F4", "slug": "f4_ges", "period": "2026-06", "headline": "Titular", "status": "AWAITING_FIRST_REVIEW",
         "verification": {"verdict": "PASS"}, "evidence": {"values": {"x": 1}}, "kpis": [], "tabs": []}


def hold(root, name, holds, cand=FICHA):
    d = root / "data/stats_fichas/hold"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps({"decision": {"holds": holds}, "candidate": cand, "generated_at": "2026-11-05T00:00:00Z"}))


def live(root, family, period):
    d = root / "data/stats_fichas/live"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{family}.json").write_text(json.dumps({"family": family, "period": period}))


def test_only_a_first_review_hold_is_previewed_without_its_evidence(tmp_path):
    hold(tmp_path, "f4.json", [rp.FIRST_REVIEW_HOLD])
    hold(tmp_path, "f6.json", ["HOLD_RECONCILIATION:x"], {**FICHA, "family": "F6", "slug": "f6_prestadores"})
    hold(tmp_path, "f2.json", [rp.FIRST_REVIEW_HOLD, "HOLD_VERIFICATION:y"], {**FICHA, "family": "F2", "slug": "f2_x"})
    web = tmp_path / "web/data"
    assert rp.write(tmp_path, web) == ["f4_ges"]
    d = json.loads((web / "preview/f4_ges.json").read_text())
    assert d["ficha"]["headline"] == "Titular" and "evidence" not in d["ficha"]
    assert json.loads((web / "preview/index.json").read_text())["previews"][0]["slug"] == "f4_ges"


def test_a_hold_already_covered_by_the_live_ficha_is_not_previewed_and_stale_previews_go(tmp_path):
    hold(tmp_path, "f7.json", [rp.FIRST_REVIEW_HOLD], {**FICHA, "family": "F7", "slug": "f7_fin", "period": "2026-07"})
    live(tmp_path, "F7", "2026-09")
    web = tmp_path / "web/data"
    (web / "preview").mkdir(parents=True)
    (web / "preview/old.json").write_text("{}")
    assert rp.write(tmp_path, web) == []
    assert sorted(p.name for p in (web / "preview").iterdir()) == ["index.json"]


def test_preview_page_is_unlisted_and_never_linked_from_the_site():
    web = Path(__file__).resolve().parents[1] / "web"
    page = (web / "preview.html").read_text(encoding="utf-8")
    assert '<meta name="robots" content="noindex,nofollow"/>' in page and "no publicada" in page
    for f in web.glob("*.html"):
        if f.name != "preview.html":
            assert "preview.html" not in f.read_text(encoding="utf-8"), f.name


def test_malformed_files_unsafe_slugs_and_unverified_candidates_are_skipped(tmp_path):
    d = tmp_path / "data/stats_fichas/hold"
    d.mkdir(parents=True)
    (d / "list.json").write_text("[1, 2]")
    (d / "bad.json").write_text("{not json")
    (d / "str.json").write_text(json.dumps({"decision": "x", "candidate": []}))
    hold(tmp_path, "slug.json", [rp.FIRST_REVIEW_HOLD], {**FICHA, "slug": "../x"})
    hold(tmp_path, "unverified.json", [rp.FIRST_REVIEW_HOLD], {**FICHA, "slug": "f9_x", "verification": {"verdict": "FAIL"}})
    hold(tmp_path, "status.json", [rp.FIRST_REVIEW_HOLD], {**FICHA, "slug": "f8_x", "status": "HOLD"})
    lv = tmp_path / "data/stats_fichas/live"
    lv.mkdir(parents=True)
    (lv / "weird.json").write_text("[]")
    assert rp.write(tmp_path, tmp_path / "web/data") == []
    assert not (tmp_path / "web/x.json").exists()


def test_production_root_never_carries_previews(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import package_pages as pp
    checked = tmp_path / "checked"
    (checked / "admin").mkdir(parents=True)
    (checked / "data/preview").mkdir(parents=True)
    (checked / "index.html").write_text("<html></html>")
    (checked / "admin/product.html").write_text("<html></html>")
    (checked / "data/product.json").write_text(json.dumps({"version": "1"}))
    (checked / "preview.html").write_text("x")
    (checked / "data/preview/f4_ges.json").write_text("{}")
    sha = "a" * 40
    out = tmp_path / "out"
    pp.assemble("production", checked, checked, out, sha)
    assert not (out / "preview.html").exists() and not (out / "data/preview").exists()
    assert (out / "staging/preview.html").exists() and (out / "staging/data/preview/f4_ges.json").exists()
    out2 = tmp_path / "out2"
    pp.assemble("staging", checked, checked, out2, sha)
    assert not (out2 / "preview.html").exists() and (out2 / "staging/preview.html").exists()


def test_previews_never_reach_the_feed_or_datos():
    root = Path(__file__).resolve().parents[1]
    for f in ("web/data/radar_today.json", "web/data/datos.json"):
        assert "data/preview" not in (root / f).read_text(encoding="utf-8")
    for js in (root / "web").glob("*.js"):
        assert "preview/" not in js.read_text(encoding="utf-8"), js.name
