import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location("recovery_command", Path(__file__).parents[1] / "scripts/pulso_recovery_command.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
recovery_command = module.recovery_command
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
