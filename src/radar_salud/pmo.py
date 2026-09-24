"""Conservative PMO projection. Source status never becomes Validado by file presence."""
import json
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_CHECKS = {"tests", "desktop", "mobile", "reviewer", "preview"}


def project(path: Path, candidate_sha: str | None = None, now: datetime | None = None) -> dict:
    baseline = json.loads(path.read_text(encoding="utf-8"))
    now = now or datetime.now(timezone.utc)
    evidence = baseline["evidence_catalog"]
    blocks = []
    for source in baseline["blocks"]:
        block = dict(source)
        links = [evidence[key] for key in block["evidence"] if key in evidence]
        # Every validated block must carry a successful full QA record. The
        # previous release's QA is not proof of a newer candidate's changes.
        if block["status"] == "Validado" and (block.get("missing") or not any(
            e.get("result") == "success" and REQUIRED_CHECKS <= set(e.get("checks", []))
            and e.get("sha") == candidate_sha and block["id"] in e.get("validated_blocks", [])
            and e.get("url", "").startswith("https://") for e in links
        )):
            block["status"] = "Implementado"
            block["validation_note"] = "Falta evidencia completa del commit candidato."
        block["evidence_links"] = [{"url": e["url"], "sha": e["sha"], "result": e["result"]} for e in links]
        blocks.append(block)
    critical = [b for b in blocks if b["critical"]]
    validated = [b for b in critical if b["status"] == "Validado"]
    failures = baseline.get("open_failures", [])
    blockers = baseline.get("human_blockers", [])
    ready = len(validated) == len(critical) and not failures and not blockers
    yesterday = now.date().toordinal() - 1
    changes = [c for c in baseline["changelog"] if datetime.fromisoformat(c["date"]).date().toordinal() >= yesterday]
    missing = [f"{b['title']}: {item}" for b in critical if b["status"] != "Validado" for item in b["missing"]]
    return {
        "version": baseline["version"], "target_date": baseline["target_date"],
        "candidate_sha": candidate_sha, "reference_staging_sha": baseline["reference_staging_sha"],
        "production_reference_sha": baseline["production_reference_sha"],
        "reference_deploy": evidence["staging_qa"],
        "release_rule": baseline["release_rule"],
        "readiness": {"ready": ready, "label": "Lista para decisión de release" if ready else "No lista para Beta",
                      "validated": len(validated), "total": len(critical)},
        "blocks": blocks, "open_failures": failures, "human_blockers": blockers,
        "scope_deviations": baseline["scope_deviations"], "changes_since_yesterday": changes,
        "missing_for_beta": missing, "next_action": missing[0] if missing else "Solicitar decisión explícita de release."
    }
