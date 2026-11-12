"""Dirección 12-nov-2026: past weekly insights stay in the feed with their date, can be filtered and shared."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("export_insights", ROOT / "scripts/export_insights.py")
ei = importlib.util.module_from_spec(spec); spec.loader.exec_module(ei)


def _w(day, slug, title, dek, expires=None):
    w = {"id": f"weekly-insight:{day}:{slug}", "freshness_anchor_date": day, "insight_title": title, "dek": dek}
    if expires:
        w["expires_on"] = expires
    return {"status": "pass", "weekly_insight": w}


def _root(tmp_path, approved, archive):
    folder = tmp_path / "data/weekly_insight"
    (folder / "archive").mkdir(parents=True)
    (folder / "editorial_approved.json").write_text(json.dumps(approved), encoding="utf-8")
    for name, doc in archive.items():
        (folder / "archive" / name).write_text(json.dumps(doc), encoding="utf-8")
    (tmp_path / "web/data").mkdir(parents=True)
    return tmp_path


def test_archive_newest_first_current_excluded_and_share_pages(tmp_path):
    root = _root(tmp_path, _w("2026-11-09", "residencias", "Título actual", "Bajada actual", "2026-11-16"), {
        "2026-10-23.json": _w("2026-10-23", "licencias", "Licencias", "Bajada <b>licencias</b>"),
        "2026-11-02.json": _w("2026-11-02", "sarampion", "Sarampión", "Bajada sarampión"),
        "2026-09-01.json": {"status": "fail", "weekly_insight": {"insight_title": "No pasó"}}})
    d = ei.write(root, today="2026-11-12")
    assert [x["slug"] for x in d["items"]] == ["2026-11-02-sarampion", "2026-10-23-licencias"]
    assert d["current"]["slug"] == "2026-11-09-residencias"
    page = (root / "web/i/2026-10-23-licencias.html").read_text(encoding="utf-8")
    assert 'property="og:title" content="Licencias"' in page and "&lt;b&gt;licencias&lt;/b&gt;" in page
    assert 'url=../index.html?insight=2026-10-23-licencias' in page
    assert (root / "web/i/2026-11-09-residencias.html").exists()  # the current one can be shared too


def test_expired_current_joins_the_feed(tmp_path):
    root = _root(tmp_path, _w("2026-11-09", "residencias", "Título actual", "Bajada", "2026-11-16"), {})
    d = ei.build(root, today="2026-11-17")
    assert "current" not in d and [x["slug"] for x in d["items"]] == ["2026-11-09-residencias"]


def test_published_files_match_the_repository_archive():
    d = json.loads((ROOT / "web/data/insights.json").read_text(encoding="utf-8"))
    assert d["schema"] == "alicanto_insights_v1" and len(d["items"]) >= 4
    for x in d["items"]:
        assert (ROOT / "web" / x["share_path"]).exists() and x["weekly"] and x["dek"] and x["date"]
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert "{k:'insights',label:'Insights',group:'Temas'" in app and "openSharedInsight()" in app
