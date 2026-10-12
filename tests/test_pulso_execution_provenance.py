import hashlib
import importlib.util
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("pulso_runtime_provenance", ROOT / "scripts/audit_pulso_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def test_frozen_actual_checkout_and_implementation_cover_real_core_before_execution():
    provenance = runtime.execution_code_provenance(ROOT)
    assert provenance["code_sha"] == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    fingerprint = provenance["runtime_fingerprint"]
    assert fingerprint["git_or_marker_sha_used"] is False
    assert "src/radar_salud/engine_cli.py" in fingerprint["files"]
    assert "src/radar_salud/pulso_editorial_proof.py" in fingerprint["files"]
    assert ".github/run-pulso-runtime-now" not in fingerprint["files"]
    assert "config/orchestrator_queue.json" not in fingerprint["files"]
    for path, sha in fingerprint["files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha


def test_report_only_uses_prior_paid_execution_provenance_instead_of_new_head():
    discovery = {"at": "2026-10-11T13:00:00+00:00", "sources": {"pulso_latercera": {}}, "source_details": {"pulso_latercera": []}}
    paid = {"engine_called": True, "started_at": "2026-10-11T12:55:00+00:00", "code_sha": "a" * 40,
            "runtime_fingerprint": {"sha256": "b" * 64}}
    report = {"execution": {"mode": "report_only_rejoin", "code_sha": "c" * 40}, "last_core_execution": paid}
    result, current = runtime.report_only_discovery(discovery, report)
    assert current is True and result == discovery
    assert report["last_core_execution"] == paid
