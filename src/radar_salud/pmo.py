"""Conservative PMO projection. Source status never becomes Validado by file presence."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_CHECKS = {"tests", "desktop", "mobile", "reviewer", "preview"}
RUN_URL = re.compile(r"https://github\.com/cftorre1/Radar-salud/actions/runs/[0-9]+/?\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def full_qa(proof: dict) -> bool:
    return (proof.get("kind") == "github_actions"
            and proof.get("result") == "success"
            and REQUIRED_CHECKS <= set(proof.get("checks", []))
            and isinstance(proof.get("sha"), str) and SHA.fullmatch(proof["sha"]) is not None
            and isinstance(proof.get("url"), str) and RUN_URL.fullmatch(proof["url"]) is not None)


def project(path: Path, candidate_sha: str | None = None, now: datetime | None = None) -> dict:
    baseline = json.loads(path.read_text(encoding="utf-8"))
    now = now or datetime.now(timezone.utc)
    evidence = baseline["evidence_catalog"]
    blocks = []
    completed_requirements=0
    total_requirements=0
    for source in baseline["blocks"]:
        block = dict(source)
        links = [evidence[key] for key in block["evidence"] if key in evidence]
        # Every validated block must carry a successful full QA record. The
        # previous release's QA is not proof of a newer candidate's changes.
        if block["status"] == "Validado" and (block.get("missing") or not any(
            full_qa(e) and e.get("sha") == candidate_sha
            and block["id"] in e.get("validated_blocks", []) for e in links
        )):
            block["status"] = "Implementado"
            block["validation_note"] = "Falta evidencia completa del commit candidato."
        block["evidence_links"] = [{"url": e.get("url"), "sha": e.get("sha"), "result": e.get("result")} for e in links]
        requirements=[]
        for entry in source.get("requirements", []):
            requirement=dict(entry)
            proof=evidence.get(requirement.get("evidence"), {})
            supported=(full_qa(proof) and requirement["label"] in proof.get("validated_requirements", []))
            if requirement.get("status")=="Validado" and not supported:
                requirement["status"]="Implementado"
                requirement["validation_note"]="Falta evidencia completa de QA/Reviewer."
            if supported and requirement["status"]=="Validado":
                requirement["evidence_url"]=proof["url"]
                completed_requirements+=1
            requirements.append(requirement)
            total_requirements+=1
        block["requirements"]=requirements
        blocks.append(block)
    critical = [b for b in blocks if b["critical"]]
    validated = [b for b in critical if b["status"] == "Validado"]
    failures = baseline.get("open_failures", [])
    blockers = baseline.get("human_blockers", [])
    ready = len(validated) == len(critical) and not failures and not blockers
    yesterday = now.date().toordinal() - 1
    changes = [c for c in baseline["changelog"] if datetime.fromisoformat(c["date"]).date().toordinal() >= yesterday]
    missing = [f"{b['title']}: {item}" for b in critical if b["status"] != "Validado" for item in b["missing"]]
    external_observations=baseline.get("external_observations",[])
    return {
        "version": baseline["version"], "target_date": baseline["target_date"],
        "candidate_sha": candidate_sha, "reference_staging_sha": baseline["reference_staging_sha"],
        "production_reference_sha": baseline["production_reference_sha"],
        "reference_deploy": evidence["staging_qa"],
        "release_rule": baseline["release_rule"],
        "readiness": {"ready": ready, "label": "Lista para decisión de release" if ready else "No lista para Beta",
                      "validated": len(validated), "total": len(critical),
                      "validated_requirements":completed_requirements,"total_requirements":total_requirements,
                      "requirement_percent":round(100*completed_requirements/total_requirements) if total_requirements else None},
        "blocks": blocks, "open_failures": failures, "human_blockers": blockers,
        "external_observations":external_observations,
        "scope_deviations": baseline["scope_deviations"], "changes_since_yesterday": changes,
        "missing_for_beta": missing, "next_action": missing[0] if missing else "Solicitar decisión explícita de release."
    }
