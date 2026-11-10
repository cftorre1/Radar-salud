"""Datos v2 mockup: staging-only (never in the production root), unlisted, and built only from data already in web/data."""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _pp():
    spec = importlib.util.spec_from_file_location("pp", ROOT / "scripts/package_pages.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _site(d: Path) -> None:
    (d / "admin").mkdir(parents=True)
    (d / "data").mkdir()
    (d / "index.html").write_text("x")
    (d / "admin/product.html").write_text("x")
    (d / "data/product.json").write_text('{"version":"1"}')
    (d / "datos-v2.html").write_text("x")


def test_mockup_is_staging_only_in_both_assembly_modes(tmp_path):
    pp, sha = _pp(), "a" * 40
    for mode in ("production", "staging"):
        checked, out = tmp_path / f"c-{mode}", tmp_path / f"o-{mode}"
        _site(checked)
        pp.assemble(mode, checked, checked, out, sha)
        assert not (out / "datos-v2.html").exists(), mode
        assert (out / "staging/datos-v2.html").exists(), mode


def test_mockup_is_unlisted_and_noindex():
    page = (WEB / "datos-v2.html").read_text(encoding="utf-8")
    assert '<meta name="robots" content="noindex,nofollow"/>' in page
    for f in list(WEB.glob("*.html")) + list(WEB.glob("*.js")):
        if f.name != "datos-v2.html":
            assert "datos-v2" not in f.read_text(encoding="utf-8"), f.name


def test_mockup_reads_only_existing_static_data():
    page = (WEB / "datos-v2.html").read_text(encoding="utf-8")
    urls = set(re.findall(r"load\('([^']+)'\)", page))
    assert urls == {"data/datos.json", "data/radar_today.json",
                    "data/preview/f13_licencias.json", "data/series_isapre.json"}
    for u in urls:
        assert (WEB / u).is_file(), u
    assert "http://" not in page and not re.search(r"""(src|href)=["']https?://""", page)
