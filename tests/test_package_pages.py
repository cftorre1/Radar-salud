import importlib.util
import json
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("package_pages", Path("scripts/package_pages.py"))
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)
SHA = "a" * 40


def site(path, title, *, checked=False):
    (path / "admin").mkdir(parents=True)
    (path / "data").mkdir()
    (path / "index.html").write_text(title)
    (path / "app.js").write_text(title)
    if checked:
        (path / "admin/product.html").write_text(title)
        (path / "data/product.json").write_text('{"published": 1}')


def test_preview_preserves_production_and_replaces_old_preview(tmp_path):
    accepted, checked, output = (tmp_path / x for x in ("accepted", "checked", "output"))
    site(accepted, "previous")
    (accepted / "staging").mkdir()
    (accepted / "staging/old.html").write_text("obsolete")
    site(checked, "candidate", checked=True)
    pages.assemble("staging", accepted, checked, output, SHA)
    assert (output / "index.html").read_bytes() == (accepted / "index.html").read_bytes()
    assert (output / "staging/index.html").read_bytes() == (checked / "index.html").read_bytes()
    assert not (output / "staging/old.html").exists()
    assert json.loads((output / "staging/release.json").read_text())["sha"] == SHA


def test_release_contains_exact_checked_files_and_two_stamps(tmp_path):
    accepted, checked, output = (tmp_path / x for x in ("accepted", "checked", "output"))
    site(accepted, "previous")
    site(checked, "candidate", checked=True)
    pages.assemble("production", accepted, checked, output, SHA)
    for name in ("index.html", "app.js", "admin/product.html", "data/product.json"):
        assert (output / name).read_bytes() == (checked / name).read_bytes()
        assert (output / "staging" / name).read_bytes() == (checked / name).read_bytes()
    assert json.loads((output / "release.json").read_text())["sha"] == SHA
    assert json.loads((output / "staging/release.json").read_text())["sha"] == SHA


def test_incomplete_candidate_never_removes_existing_output(tmp_path):
    accepted, checked, output = (tmp_path / x for x in ("accepted", "checked", "output"))
    site(accepted, "previous")
    site(checked, "incomplete")
    site(output, "existing")
    with pytest.raises(ValueError, match="Incomplete"):
        pages.assemble("production", accepted, checked, output, SHA)
    assert (output / "index.html").read_text() == "existing"
