import json
from pathlib import Path

from radar_salud.pmo import project


def test_validated_requires_full_evidence_for_exact_candidate(tmp_path):
    baseline = json.loads(Path("config/pmo_baseline.json").read_text())
    block = baseline["blocks"][0]
    block["status"] = "Validado"
    block["evidence"] = ["staging_qa"]
    block["missing"] = []
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline))
    old = project(path, "a" * 40)
    assert old["blocks"][0]["status"] == "Implementado"
    assert not old["readiness"]["ready"]
    current = project(path, baseline["reference_staging_sha"])
    assert current["blocks"][0]["status"] == "Implementado"
    baseline["evidence_catalog"]["staging_qa"]["validated_blocks"] = ["pmo"]
    path.write_text(json.dumps(baseline))
    current = project(path, baseline["reference_staging_sha"])
    assert current["blocks"][0]["status"] == "Validado"
    baseline["evidence_catalog"]["staging_qa"]["checks"].remove("reviewer")
    path.write_text(json.dumps(baseline))
    assert project(path, baseline["reference_staging_sha"])["blocks"][0]["status"] == "Implementado"


def test_source_baseline_has_no_unproven_validation():
    report = project(Path("config/pmo_baseline.json"), "b" * 40)
    assert report["readiness"]["validated"] == 0
    assert report["open_failures"]
    assert report["human_blockers"]
    assert any("Excel" in x for x in report["missing_for_beta"])
