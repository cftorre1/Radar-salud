import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("recovery_command", Path(__file__).parents[1] / "scripts/pulso_recovery_command.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
recovery_command = module.recovery_command
idempotence_command = module.idempotence_command
directed_qa_command = module.directed_qa_command
URL = "https://www.latercera.com/pulso/noticia/inversion-en-red-clinica/"


def marker(tmp_path):
    path = tmp_path / "data/audits/cohort.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"source": "pulso_latercera", "urls": [URL]}))
    return {"phase": "process", "queue_selection": "data/audits/cohort.json"}


def test_valid_marker_passes_repository_path_as_single_argument(tmp_path):
    value = marker(tmp_path)
    command = recovery_command(value, tmp_path)
    assert command[-2:] == ["--queue-selection", "data/audits/cohort.json"]
    assert command[:5] == ["timeout", "--signal=TERM", "--kill-after=45s", "75m", "python"]
    assert command[command.index("--limit") + 1] == "250"


@pytest.mark.parametrize("selection", ["../cohort.json", "/tmp/cohort.json", "data/audits/cohort.txt", "data/state/cohort.json", "data/audits/absent.json", "", [], "data/audits/../../outside.json"])
def test_path_escape_wrong_type_or_missing_original_is_rejected(tmp_path, selection):
    value = marker(tmp_path)
    value["queue_selection"] = selection
    with pytest.raises((ValueError, FileNotFoundError)):
        recovery_command(value, tmp_path)


def test_symlink_cannot_escape_repository_audits(tmp_path):
    value = marker(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"source": "pulso_latercera", "urls": [URL]}))
    path = tmp_path / value["queue_selection"]
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ValueError):
        recovery_command(value, tmp_path)


@pytest.mark.parametrize("phase", ["discovery_only", "report_only", "bad"])
def test_selection_cannot_change_read_only_or_unknown_phase(tmp_path, phase):
    value = marker(tmp_path)
    value["phase"] = phase
    with pytest.raises(ValueError):
        recovery_command(value, tmp_path)


def test_invalid_source_is_rejected_before_subprocess(tmp_path):
    value = marker(tmp_path)
    path = tmp_path / value["queue_selection"]
    path.write_text(json.dumps({"source": "bupa", "urls": [URL]}))
    with pytest.raises(ValueError):
        recovery_command(value, tmp_path)


@pytest.mark.parametrize("phase, flag", [("process", None), ("discovery_only", "--discovery-only"), ("report_only", "--report-only")])
def test_existing_phases_preserve_command_and_limit(tmp_path, phase, flag):
    command = recovery_command({"phase": phase}, tmp_path)
    assert "--queue-selection" not in command
    assert command[-1] == (flag or "250")


def test_first_paid_processing_captures_only_after_successful_qa(tmp_path):
    value = marker(tmp_path)
    assert idempotence_command(value, tmp_path, "preflight") == []
    assert idempotence_command(value, tmp_path, "after_core") == []
    assert idempotence_command(value, tmp_path, "after_qa") == [
        "python", "scripts/pulso_idempotence.py", "capture", "--baseline", module.BASELINE]
    assert "--idempotence-baseline" not in directed_qa_command(value, tmp_path)


def test_replay_keeps_paid_baseline_and_requires_actual_second_run_proof(tmp_path):
    value = marker(tmp_path)
    (tmp_path / module.BASELINE).write_text("{}")
    value["idempotence_baseline"] = module.BASELINE
    assert idempotence_command(value, tmp_path, "preflight")[-3:] == ["preflight", "--baseline", module.BASELINE]
    assert idempotence_command(value, tmp_path, "after_core")[-5:] == [
        "compare", "--baseline", module.BASELINE, "--output", module.PROOF]
    assert idempotence_command(value, tmp_path, "after_qa") == []
    with pytest.raises(FileNotFoundError):
        directed_qa_command(value, tmp_path)
    (tmp_path / module.PROOF).write_text("{}")
    assert directed_qa_command(value, tmp_path)[-4:] == [
        "--idempotence-baseline", module.BASELINE, "--idempotence-proof", module.PROOF]
    assert "idempotence" not in " ".join(recovery_command(value, tmp_path))


@pytest.mark.parametrize("baseline", ["../outside.json", "/tmp/proof.json", "data/state/baseline.json", "data/audits/absent.json", "", []])
def test_invalid_baseline_stops_before_paid_core(tmp_path, baseline):
    value = marker(tmp_path)
    value["idempotence_baseline"] = baseline
    with pytest.raises((ValueError, FileNotFoundError)):
        recovery_command(value, tmp_path)


@pytest.mark.parametrize("phase", ["discovery_only", "report_only", "process"])
def test_replay_requires_explicit_selected_processing(tmp_path, phase):
    (tmp_path / "data/audits").mkdir(parents=True)
    (tmp_path / module.BASELINE).write_text("{}")
    with pytest.raises(ValueError):
        recovery_command({"phase": phase, "idempotence_baseline": module.BASELINE}, tmp_path)


@pytest.mark.parametrize("phase", ["discovery_only", "report_only"])
def test_read_only_phases_do_not_capture_or_overwrite_paid_proof(tmp_path, phase):
    for stage in ("preflight", "after_core", "after_qa"):
        assert idempotence_command({"phase": phase}, tmp_path, stage) == []


def test_capture_output_cannot_escape_through_symlink(tmp_path):
    value = marker(tmp_path)
    (tmp_path / module.BASELINE).symlink_to(tmp_path / "outside.json")
    with pytest.raises(ValueError):
        idempotence_command(value, tmp_path, "after_qa")


def test_paid_lineage_capture_is_explicit_and_runs_only_after_successful_qa(tmp_path):
    value = marker(tmp_path)
    value["baseline_capture_mode"] = "revalidated_paid_lineage"
    assert idempotence_command(value, tmp_path, "preflight") == []
    assert idempotence_command(value, tmp_path, "after_core") == []
    assert idempotence_command(value, tmp_path, "after_qa") == [
        "python", "scripts/pulso_idempotence.py", "capture-revalidated", "--baseline", module.BASELINE]
    ordinary = {key: item for key, item in value.items() if key != "baseline_capture_mode"}
    assert recovery_command(value, tmp_path) == recovery_command(ordinary, tmp_path)


@pytest.mark.parametrize("mode", ["capture", "allow-zero", "", [], True])
def test_unknown_paid_lineage_capture_modes_stop_before_runtime(tmp_path, mode):
    value = marker(tmp_path)
    value["baseline_capture_mode"] = mode
    with pytest.raises(ValueError, match="Unsupported baseline capture mode"):
        idempotence_command(value, tmp_path, "after_qa")


@pytest.mark.parametrize("phase", ["discovery_only", "report_only", "process"])
def test_paid_lineage_capture_requires_selected_processing(tmp_path, phase):
    with pytest.raises(ValueError):
        recovery_command({"phase": phase, "baseline_capture_mode": "revalidated_paid_lineage"}, tmp_path)


def test_paid_lineage_capture_cannot_replace_replay_baseline(tmp_path):
    value = marker(tmp_path)
    (tmp_path / module.BASELINE).write_text("{}")
    value.update(baseline_capture_mode="revalidated_paid_lineage", idempotence_baseline=module.BASELINE)
    with pytest.raises(ValueError, match="before its replay"):
        idempotence_command(value, tmp_path, "after_qa")


def test_terminal_followthrough_capture_is_explicit_and_only_after_qa(tmp_path):
    value = marker(tmp_path)
    value["baseline_capture_mode"] = "terminal_followthrough"
    assert idempotence_command(value, tmp_path, "preflight") == []
    assert idempotence_command(value, tmp_path, "after_core") == []
    assert idempotence_command(value, tmp_path, "after_qa") == [
        "python", "scripts/pulso_idempotence.py", "capture-terminal-followthrough", "--baseline", module.BASELINE]
    ordinary = {key: item for key, item in value.items() if key != "baseline_capture_mode"}
    assert recovery_command(value, tmp_path) == recovery_command(ordinary, tmp_path)


@pytest.mark.parametrize("phase", ["discovery_only", "report_only", "process"])
def test_terminal_followthrough_capture_requires_selected_processing(tmp_path, phase):
    with pytest.raises(ValueError):
        recovery_command({"phase": phase, "baseline_capture_mode": "terminal_followthrough"}, tmp_path)


def test_terminal_followthrough_capture_never_replaces_sealed_baseline(tmp_path):
    value = marker(tmp_path)
    (tmp_path / module.BASELINE).write_text("{}")
    value.update(baseline_capture_mode="terminal_followthrough", idempotence_baseline=module.BASELINE)
    with pytest.raises(ValueError, match="before its replay"):
        idempotence_command(value, tmp_path, "after_qa")
