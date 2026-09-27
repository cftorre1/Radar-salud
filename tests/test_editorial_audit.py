import json
from pathlib import Path


def test_expert_editorial_audit_preserves_the_frozen_default_home_scope():
    audit = json.loads(Path("data/editorial_audit_2026_09_26.json").read_text())
    audited = {row["id"] for row in audit["items"] if row["id"].startswith("https://")}
    assert audit["scope"]["visible_base_signals"] == 14
    assert audit["scope"]["special_pieces_audited"] == 2
    assert audit["scope"]["historical_items_audited"] == len(audit["items"]) == 16
    assert len(audited) == 14
    # The live/curated feed can now be smaller because persistent rules may
    # degrade, group or hide routine pieces after the frozen audit.
    assert all(url.startswith("https://") for url in audited)


def test_expert_editorial_audit_is_traceable_and_fail_closed():
    audit = json.loads(Path("data/editorial_audit_2026_09_26.json").read_text())
    allowed = {
        "conservar",
        "ajustar_titulo",
        "ajustar_resumen",
        "ajustar_por_que_importa",
        "requiere_evidencia_adicional",
        "descartar",
    }
    for row in audit["items"]:
        assert set(row["verdict"]) <= allowed
        assert row["current"]["title"]
        assert set(row["proposed"]) == {"title", "summary", "why"}
        assert row["rationale"]
    insufficient = [
        row for row in audit["items"] if "requiere_evidencia_adicional" in row["verdict"]
    ]
    assert len(insufficient) == 3
    assert all(row["evidence_flag"] for row in insufficient)
    for verdict, expected in audit["summary"].items():
        assert sum(verdict in row["verdict"] for row in audit["items"]) == expected
