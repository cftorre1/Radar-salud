import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("bootstrap", Path("scripts/bootstrap_autopilot.py"))
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
SHA = "a" * 40


def test_initialization_requires_success_on_current_main():
    runs = {"workflow_runs": [
        {"head_sha": "b" * 40, "head_branch": "main", "conclusion": "success"},
        {"head_sha": SHA, "head_branch": "staging", "conclusion": "success"},
        {"head_sha": SHA, "head_branch": "main", "conclusion": "failure"},
    ]}
    assert not bootstrap.is_accepted_main(SHA, runs)
    runs["workflow_runs"].append({"head_sha": SHA, "head_branch": "main", "conclusion": "success"})
    assert bootstrap.is_accepted_main(SHA, runs)


def test_no_arbitrary_ref_is_accepted():
    assert not bootstrap.is_accepted_main("main", {"workflow_runs": []})


def test_existing_auxiliary_branches_do_not_require_new_main_release():
    with patch.object(bootstrap.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as probe, \
         patch.object(bootstrap, "command") as command:
        bootstrap.ensure_branches()
    assert probe.call_count == 2
    command.assert_not_called()


def test_missing_branch_still_requires_verified_main(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/repo")
    with patch.object(bootstrap.subprocess, "run", side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=2)]), \
         patch.object(bootstrap, "command", side_effect=[SHA, '{"workflow_runs": []}']):
        try:
            bootstrap.ensure_branches()
        except RuntimeError as error:
            assert "not a successfully deployed" in str(error)
        else:
            assert False, "Missing branch must not be seeded from unaccepted main"
