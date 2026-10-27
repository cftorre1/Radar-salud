import json
from pathlib import Path

from src.radar_salud.source_health import load_retired_sources, mark_retired_sources


def test_directorate_retirements_are_explicit_and_reasoned():
    retired = load_retired_sources(Path("."))
    assert set(retired) == {"pfizer_chile", "indisa", "red_davila", "clinicas_achs_salud"}
    assert all(isinstance(r, str) and len(r) > 20 for r in retired.values())
    # IST is critical for Dirección (26-oct-2026) and must never be retired here.
    assert "ist" not in retired


def test_mark_retired_keeps_history_and_leaves_freshness_checks(tmp_path):
    (tmp_path / "data").mkdir()
    health = {"sources": {
        "indisa": {"status": "error", "checked_at": "2026-10-25T21:25:00+00:00", "latest_original_at": "2026-09-11"},
        "suseso": {"status": "ok", "checked_at": "2026-10-25T21:25:00+00:00"},
    }}
    (tmp_path / "data/source_health.json").write_text(json.dumps(health), encoding="utf-8")
    mark_retired_sources(tmp_path, {"indisa": "Sitio en mantención"})
    out = json.loads((tmp_path / "data/source_health.json").read_text())["sources"]
    assert out["indisa"]["status"] == "retired" and out["indisa"]["latest_original_at"] == "2026-09-11"
    assert out["suseso"]["status"] == "ok"
    # The reviewer only enforces freshness on ok/warning rows.
    assert out["indisa"]["status"] not in ("ok", "warning")


def test_engine_never_polls_retired_sources():
    src = Path("src/radar_salud/engine_cli.py").read_text()
    assert "specs=[spec for spec in specs if spec[0] not in retired]" in src
