"""Validate the branch-owned recovery marker before invoking the real core."""
from pathlib import Path


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
        path = Path(selection)
        audits = (root / "data/audits").resolve()
        if path.is_absolute() or path.suffix != ".json":
            raise ValueError("Queue selection must be a repository-owned JSON audit")
        resolved = (root / path).resolve(strict=True)
        if not resolved.is_relative_to(audits) or not resolved.is_file():
            raise ValueError("Queue selection must remain inside repository data/audits")
        from radar_salud.queue_selection import load_queue_selection
        load_queue_selection(resolved, ["pulso_latercera"])
        command.extend(["--queue-selection", str(resolved.relative_to(root.resolve()))])
    return command
