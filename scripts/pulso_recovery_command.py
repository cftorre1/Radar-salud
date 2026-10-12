"""Validate the branch-owned recovery marker before invoking the real core."""
from pathlib import Path
import hashlib

BASELINE = "data/audits/pulso_idempotence_baseline_2026_10_11.json"
PROOF = "data/audits/pulso_idempotence_2026_10_11.json"
TERMINAL_COHORT = "data/audits/pulso_material_recovery_cohort_2026_10_11.json"
TERMINAL_COHORT_SHA256 = "8ed358f0cd37ecc4b554ab96cd4366048b8e6180ad1c0ee0044fc5d5f6976514"


def audit_path(value, root: Path, label: str, *, exists=True) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(label + " requires a repository audit path")
    path = Path(value)
    if path.is_absolute() or path.suffix != ".json":
        raise ValueError(label + " must be a repository-owned JSON audit")
    resolved = (root / path).resolve(strict=exists)
    if not resolved.is_relative_to((root / "data/audits").resolve()) or (exists and not resolved.is_file()):
        raise ValueError(label + " must remain inside repository data/audits")
    return str(resolved.relative_to(root.resolve()))


def recovery_command(marker: dict, root: Path) -> list[str]:
    phase = marker.get("phase")
    if phase not in {"discovery_only", "process", "report_only"}:
        raise ValueError("Unsupported recovery phase")
    command = ["timeout", "--signal=TERM", "--kill-after=45s", "75m", "python",
               "scripts/audit_pulso_runtime.py", "--limit", "250"]
    if phase == "discovery_only":
        command.append("--discovery-only")
    if phase == "report_only":
        command.append("--report-only")
    selection = marker.get("queue_selection")
    if selection is not None:
        if phase != "process" or not isinstance(selection, str) or not selection:
            raise ValueError("Queue selection requires a processing marker and a repository audit path")
        relative = audit_path(selection, root, "Queue selection")
        from radar_salud.queue_selection import load_queue_selection
        load_queue_selection(root / relative, ["pulso_latercera"])
        command.extend(["--queue-selection", relative])
    baseline = marker.get("idempotence_baseline")
    if baseline is not None:
        if phase != "process" or selection is None:
            raise ValueError("Idempotence replay requires a selected processing marker")
        audit_path(baseline, root, "Idempotence baseline")
    capture_mode = marker.get("baseline_capture_mode")
    if capture_mode is not None:
        if not isinstance(capture_mode, str) or capture_mode not in {"revalidated_paid_lineage", "terminal_followthrough"}:
            raise ValueError("Unsupported baseline capture mode")
        if phase != "process" or selection is None or baseline is not None:
            raise ValueError("Paid-lineage capture requires selected processing before its replay")
        if capture_mode == "terminal_followthrough":
            if selection != TERMINAL_COHORT or hashlib.sha256((root / selection).read_bytes()).hexdigest() != TERMINAL_COHORT_SHA256:
                raise ValueError("Terminal followthrough requires the unchanged frozen 113 cohort before core")
    return command


def idempotence_command(marker: dict, root: Path, stage: str) -> list[str]:
    """Keep paid processing and its zero-call replay as distinct proofs."""
    recovery_command(marker, root)  # Validate before any subprocess activity.
    if stage not in {"preflight", "after_core", "after_qa"}:
        raise ValueError("Unsupported idempotence stage")
    if marker["phase"] != "process" or not marker.get("queue_selection"):
        return []
    baseline = marker.get("idempotence_baseline")
    helper = ["python", "scripts/pulso_idempotence.py"]
    if baseline:
        relative = audit_path(baseline, root, "Idempotence baseline")
        if stage == "preflight":
            return helper + ["preflight", "--baseline", relative]
        if stage == "after_core":
            return helper + ["compare", "--baseline", relative, "--output", PROOF]
        return []  # Never replace the paid baseline with its zero-call replay.
    if stage == "after_qa":
        capture = {"revalidated_paid_lineage": "capture-revalidated",
                   "terminal_followthrough": "capture-terminal-followthrough"}.get(marker.get("baseline_capture_mode"), "capture")
        return helper + [capture, "--baseline", audit_path(BASELINE, root, "Baseline output", exists=False)]
    return []


def directed_qa_command(marker: dict, root: Path) -> list[str]:
    recovery_command(marker, root)
    scope = "processing" if marker["phase"] == "process" else "discovery"
    command = ["python", "scripts/qa_pulso_recovery.py", "--" + scope,
               "--capture-artifact", ".scratch/pulso-prior-capture", "--output",
               "data/audits/pulso_directed_" + scope + "_qa_2026_10_11.json"]
    if marker.get("idempotence_baseline"):
        command.extend(["--idempotence-baseline", audit_path(marker["idempotence_baseline"], root, "Idempotence baseline"),
                        "--idempotence-proof", audit_path(PROOF, root, "Idempotence proof")])
    return command
