"""Dirección 4-nov-2026: fichas held only by their first-review gate get an unlisted staging preview; nothing else."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from radar_salud import review_preview as rp  # noqa: E402

FICHA = {"family": "F4", "slug": "f4_ges", "period": "2026-06", "headline": "Titular", "status": "AWAITING_FIRST_REVIEW",
         "evidence": {"values": {"x": 1}}, "kpis": [], "tabs": []}


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
