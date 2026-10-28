"""Read genuine core observations to prove a selected processing replay is inert.

No engine, model, discovery, queue or editorial mutation is invoked here. The
original baseline requires passing paid processing. The explicit revalidated
mode keeps a failed paid producer separate from later passing, actual zero-AI
processing. Either baseline needs a later real core with zero attempts/events.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

SOURCE = "pulso_latercera"
SCHEMA = "pulso_idempotence_v1"
ROOT = Path(__file__).resolve().parents[1]
# Historical evidence: audits redacted under the rights policy (Dirección 28-oct-2026)
# are re-verified from their exact pinned git blobs, never from the redacted tree.
import sys as _sys
_sys.path.insert(0, str(ROOT / "src"))
from radar_salud.pinned_evidence import install_original_audit_reader  # noqa: E402
install_original_audit_reader(ROOT)
DEFAULT_SELECTION = "data/audits/pulso_material_recovery_cohort_2026_10_11.json"
DEFAULT_REPORT = "data/audits/pulso_runtime_2026_10_11.json"
DEFAULT_QA = "data/audits/pulso_directed_processing_qa_2026_10_11.json"
DEFAULT_BASELINE = "data/audits/pulso_idempotence_baseline_2026_10_11.json"
DEFAULT_RESULT = "data/audits/pulso_idempotence_2026_10_11.json"
EDITORIAL_REVIEW_REGISTRY = "data/audits/pulso_editorial_review_registry_2026_10_11.json"
RUNTIME_HELPERS = (
    "scripts/audit_pulso_runtime.py", "scripts/qa_pulso_recovery.py",
    "scripts/retain_pulso_runtime_fixtures.py", "scripts/export_web_snapshot.py",
    "scripts/product_report.py", "scripts/apply_pulso_editorial_review.py",
    "scripts/pulso_idempotence.py", "scripts/pulso_recovery_command.py", "pyproject.toml",
    ".github/workflows/daily-radar.yml", ".github/workflows/pulso-runtime-recovery.yml",
)
RUNTIME_CONFIGS = (
    "sources.json", "beta_source_configs.json", "source_quality_gate.json",
    "media_early_signal_gate.json", "model_routing_v1.json", "taxonomy_v2.json",
    "editorial_rules_v2.json", "editorial_copy_overrides_v1.json",
    "editorial_intelligence_committee_v1.json", "normative_editorial_v2.json",
    "pulso_editorial_repair_admission_2026_10_11.json",
)
TERMINAL = {"published", "rejected", "archived"}
IMMUTABLE_COHORT_INPUTS = ("frozen_control", "independent_primary_review", "expanded_negative_review")
TECHNICAL_HOLDS = {"analysis_unavailable", "article_verification_failed", "budget_or_analysis_deferred",
                   "analysis_complete_primary_body_not_proven", "fast_analysis_capacity_exhausted",
                   "publisher_liveblog_entry_dates_unverified"}
INCREMENTAL_REVIEW = "data/audits/pulso_incremental_review_2026_10_11.json"
INCREMENTAL_REVIEW_SHA256 = "e5cee8d34839a905e391e85d6187db8bcdae09c0dde7f688cc71a9f04f093ddd"
INCREMENTAL_ADDENDUM = "data/audits/pulso_oct5_incremental_addendum_2026_10_11.json"
INCREMENTAL_ADDENDUM_SHA256 = "589ba50032521924803ef8ce94f40e3854930edcadddf7fc1223d9df81714160"
REVALIDATED_MODE = "genuine_revalidated_processing_baseline"
FINAL_PAID_PRODUCER = "323b73ef5fb0ec39410024c21d70e6fd99b065e2"
FINAL_PAID_CODE = "c2db17141fd55cbacbcda5b53805341aa4dfa86f"
FINAL_PAID_FINGERPRINT = "c960999eea01aed6e578d0ca1354cb5f45b8720ae8832993d609d0db540b0406"
TERMINAL_FOLLOWTHROUGH_MODE = "genuine_terminal_followthrough_processing_baseline"
ARCHIVED_FINAL_PRODUCER = "123bf2550536030a077c03ad4d56572df24ab418"
ARCHIVED_FINAL_CODE = "46a3683c6760f0e61031a7dc7d5961c105cacb36"
ARCHIVED_FINAL_FINGERPRINT = "8f50110e88b79f0832e86957a0f14d3a461a52faf6f65fd2b1fab8299df831fa"
ARCHIVED_FINAL_FILES = {
    DEFAULT_REPORT: "6f0f26ac044cf50e2df2fc30be21e42b56276c6e77ca6678b6c8621b35a7d8d9",
    DEFAULT_QA: "719d0afbb61718808c4ccee7252cb98af337e0d6fec3c56aab2ad2a553dd4582",
    "data/state/pending_queue.json": "509da9e5c5a2da99da8b537c7a003870e5f6a1b777adff6aff5f3db106308105",
    "data/history/superintendencia_signals.json": "1400cb4a7bfd9d50283bf7927515dffa328ec07cbb1a780148f9227f3db98b26",
    "web/data/radar_today.json": "6c7bd5a3b7dda1fbb6fe032d43c4927adc1393111716852835dfd495ce1e53dc",
    "data/ai_usage/responses.jsonl": "19bb3e6b2ae1e15c623a97eb08ae6b3f323b1c11cec6fa74aad359f3ca04cfad",
    "data/ai_usage/2026-10.json": "aec8ca63b045c2d44c28ebfddcfd4474651ae5bfc27efbc1247f4171a18e9ca9",
    "data/state/discovery_run.json": "301529a60f3209f6b1d5294d6bf1123f90e8c283974528602d461f1c09120f26",
}
ALLOWED_TERMINAL_CONSUMER_CHANGES = frozenset({
    "scripts/qa_pulso_recovery.py", "scripts/pulso_idempotence.py",
    "scripts/pulso_recovery_command.py", ".github/workflows/pulso-runtime-recovery.yml",
})
SETTLEMENT_PRODUCER = "d48a495a5fcefb9adaca26ca30b1f12ddad7e59f"
SETTLEMENT_CODE = "1b4817164dbd9cd091197e1c7ebd03de6fa93526"
SETTLEMENT_FINGERPRINT = "be91910c2f322831f8279afd200963155b7bb076e31034c2592cb31290e56814"
SETTLEMENT_FILES = {
    DEFAULT_REPORT: "8ce66b878a4165bb079292eb4c2853eb029309a9341954c77007bc578cf5accb",
    DEFAULT_QA: "cf5ee33b0833b6ee6704c19b7a8e308a4e65c6d089e4dda4a4b4d2e662bc063a",
    "data/state/pending_queue.json": "d44cfa10569f34cf1e1f8a7746d26bd71728d069679c89b756387381123eddf8",
    "data/history/superintendencia_signals.json": "1400cb4a7bfd9d50283bf7927515dffa328ec07cbb1a780148f9227f3db98b26",
    "web/data/radar_today.json": "4801f42db2518366dd9c2555bd62a1b55d257e46cfb25f67bf089352fc5eccf0",
    "data/ai_usage/responses.jsonl": "85baafcd92e24f98d912105fc8dced023b5dd78f18d63a571e7626908d917d31",
    "data/ai_usage/2026-10.json": "4411394f3ac5fa75136f023b125ed00eac7538b0d4670e545fc34a05d921204a",
    "data/state/discovery_run.json": "6ed0352474bb398f02d13bf6550e2865f71c7e0c65c4c25062c4d1e3ee48a9c0",
}
SETTLEMENT_REVIEW_FILES = {
    "data/audits/pulso_additional_live9_recovery_cohort_2026_10_11.json": "641eee7d713cd1c9fba2171d9e45dbaeab0688434ac371a87f56089b2f141373",
    "data/audits/pulso_additional_live9_primary_semantic_triage_2026_10_11.json": "fba017ed27f0449be06e20c9c2c4943984d7b835c47fa0a0e8b74bf7de67dfe8",
    "tests/fixtures/pulso_live9_primary_real/manifest.json": "908875faca85694905ca6abeae9945b1366903a3cc54f67c588cee96b133d46f",
}


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(value).hexdigest()


def stamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except (AttributeError, TypeError, ValueError):
        return None


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def runtime_fingerprint(root):
    # Include newly added runtime modules automatically. Governance queues and
    # marker/git SHAs are not implementation fingerprints.
    files = sorted({str(path.relative_to(root)) for path in (root / "src/radar_salud").glob("*.py")}
                   | set(RUNTIME_HELPERS) | {"config/" + name for name in RUNTIME_CONFIGS})
    required = {"src/radar_salud/engine_cli.py", "src/radar_salud/pulso_source.py", "src/radar_salud/ai_budget.py"}
    require(required <= set(files), "runtime_implementation_missing")
    hashes = {path: digest((root / path).read_bytes()) for path in files}
    return {"files": hashes, "sha256": digest(hashes), "git_or_marker_sha_used": False}


def core_checkout_files(root, code_ref, paths):
    """Bind implementation bytes to the real run's recorded checkout revision.

    The revision locates original blobs; only file hashes establish equality.
    Different marker/data commits can therefore use identical implementation.
    """
    if not isinstance(code_ref, str) or not re.fullmatch(r"[0-9a-f]{40}", code_ref):
        return {"error": "recorded_core_checkout_revision_missing"}
    hashes = {}
    for path in paths:
        result = subprocess.run(["git", "show", code_ref + ":" + path], cwd=root, capture_output=True)
        if result.returncode:
            return {"error": "recorded_core_implementation_blob_unavailable", "path": path}
        hashes[path] = digest(result.stdout)
    return {"files": hashes, "sha256": digest(hashes), "git_or_marker_sha_used": False}


def compact(value):
    """Hash large primary text while retaining its length, never dropping proof."""
    if isinstance(value, dict):
        return {key: (({"value_type": "str", "utf8_sha256": digest(item.encode()), "characters": len(item)}
                       if isinstance(item, str) else {"value_type": type(item).__name__, "value": compact(item)})
                      if key in {"page_text", "raw_text"} else compact(item))
                for key, item in value.items() if key not in {"last_checked_at", "cache_hit"}}
    if isinstance(value, list):
        return [compact(item) for item in value]
    return value


def signal_index(signals):
    if isinstance(signals, dict):
        signals = signals["signals"]
    require(isinstance(signals, list), "invalid_signal_snapshot")
    indexed = {}
    for signal in signals:
        fields = [signal.get("source_url"), signal.get("event_date")]
        # Distinct official offices share their publisher's stock listing.
        # Preserve their native record identity instead of treating the listing
        # as a news-article identity. La Tercera articles retain URL/date dedupe.
        record_id = signal.get("source_record_id")
        host = urlparse(str(signal.get("source_url") or "")).hostname
        if (host not in {"latercera.com", "www.latercera.com"}
                and signal.get("source_type") == "official"
                and isinstance(record_id, str) and record_id.strip()):
            fields.append(record_id.strip())
        identity = json.dumps(fields, ensure_ascii=False)
        require(identity not in indexed, "duplicate_effective_signal_identity")
        indexed[identity] = digest(signal)
    return indexed


def budget_delta(execution):
    delta = {}
    for tier in ("fast", "deep"):
        delta[tier] = {}
        for metric in ("attempted", "successful", "failed"):
            changes = []
            for scope in ("run", "month"):
                before = execution["budget_before"][scope][tier][metric]
                after = execution["budget_after"][scope][tier][metric]
                require(type(before) is int and type(after) is int and 0 <= before <= after,
                        "invalid_or_decreased_analysis_counter")
                changes.append(after - before)
            require(changes[0] == changes[1], "run_month_analysis_delta_disagree")
            delta[tier][metric] = changes[0]
        require(delta[tier]["attempted"] == delta[tier]["successful"] + delta[tier]["failed"],
                "analysis_attempt_without_result")
    return delta


def source_queue(queue):
    rows = {}
    for fingerprint, item in queue.items():
        if item.get("source") != SOURCE:
            continue
        url = item.get("raw", {}).get("url")
        metadata = item.get("raw", {}).get("metadata", {})
        require(isinstance(url, str) and url not in rows, "duplicate_or_invalid_source_queue_identity")
        rows[url] = dict(fingerprint=fingerprint, status=item.get("status"), attempts=item.get("attempts", 0),
                         semantic_sha256=digest(compact(item)), retry_at=item.get("retry_at"),
                         publication_date=item.get("raw", {}).get("event_date"),
                         lane=item.get("lane"), reason=item.get("reason"),
                         assessment=metadata.get("editorial_assessment"), editorial_hold=metadata.get("editorial_hold"),
                         body_sha256=metadata.get("article_body_sha256"), body_characters=metadata.get("article_body_characters"),
                         source_quality_gate=metadata.get("source_quality_gate"),
                         editorial_proof_validation=metadata.get("pulso_editorial_proof_validation"),
                         primary_item_binding=metadata.get("primary_item_binding"),
                         analysis_input_complete=metadata.get("analysis_input_complete"),
                         article_body_complete=metadata.get("article_body_complete"),
                         editorial_review_sha256=digest(metadata["editorial_review"]) if metadata.get("editorial_review") else None)
    return rows


def processing_evidence_failures(row):
    failures = []
    validation, binding = row.get("editorial_proof_validation"), row.get("primary_item_binding")
    if isinstance(validation, dict) and validation.get("decision") == "deferred":
        failures.append("editorial_proof_validation_deferred")
    if isinstance(binding, dict) and binding.get("verified") is False:
        failures.append("primary_item_binding_unverified")
    for field in ("analysis_input_complete", "article_body_complete"):
        if row.get(field) is False:
            failures.append(field + "_unverified")
    if row["status"] not in TERMINAL:
        assessment = row.get("assessment") or {}
        for reason in (assessment.get("reason"), row.get("editorial_hold"), row.get("reason")):
            if isinstance(reason, str) and (reason in TECHNICAL_HOLDS or reason.startswith(
                    ("pulso_editorial_", "pulso_primary_", "processing_not_attempted:"))):
                failures.append(reason)
    return sorted(set(failures))


def reviewed_hold_bindings(context):
    """A static duplicate triage is insufficient without its live canonical item.

    Check persisted primary/copy proof only. This never releases a hold, supplies
    a date, or interprets an unresolved model decision as editorial approval.
    """
    document = context.get("incremental_review_files", {}).get(INCREMENTAL_REVIEW)
    if not isinstance(document, dict):
        return {}
    policy = document.get("editorial_policy", {})
    if (context.get("referenced_proof_files", {}).get(INCREMENTAL_REVIEW) != INCREMENTAL_REVIEW_SHA256
            or document.get("source_id") != SOURCE or document.get("schema_version") != 1
            or document.get("verdict") != "PASS_INCREMENTAL_TRIAGE_NOT_PUBLICATION_APPROVAL"
            or policy.get("media_materiality_threshold") != 72
            or policy.get("threshold_changed") is not False or policy.get("publication_approved") is not False):
        return {}
    history = context["history"]
    history = history.get("signals", []) if isinstance(history, dict) else history
    bindings = {}
    for item in context["queue"].values():
        if item.get("source") != SOURCE or item.get("status") in TERMINAL:
            continue
        raw = item.get("raw", {})
        metadata = raw.get("metadata", {})
        review = metadata.get("incremental_review") or {}
        url, day = raw.get("url"), raw.get("event_date")
        entries = [entry for entry in document.get("reviews", []) if entry.get("source_url") == url]
        if len(entries) != 1 or not isinstance(review, dict):
            continue
        entry = entries[0]
        reason = metadata.get("editorial_assessment", {}).get("reason")
        body = metadata.get("page_text")
        if (review.get("review_ref") != INCREMENTAL_REVIEW
                or review.get("review_sha256") != INCREMENTAL_REVIEW_SHA256
                or review.get("decision") != entry.get("decision") or entry.get("decision") != "keep_hold"
                or review.get("publication_approved") is not False or entry.get("publication_approved") is not False
                or reason != entry.get("reason") or metadata.get("editorial_hold") != reason
                or metadata.get("article_verified") is not True or metadata.get("primary_identity_verified") is not True
                or metadata.get("publication_date_verified") is not True or metadata.get("source_quality_gate") != "passed"
                or metadata.get("canonical_url") != url or day != entry.get("publication_date")
                or metadata.get("publication_date") != day or review.get("verified_publication_date") != day
                or not isinstance(body, str) or len(body.strip()) < 160
                or digest(body.encode()) != metadata.get("article_body_sha256")
                or review.get("verified_body_sha256") != metadata.get("article_body_sha256")
                or not re.fullmatch(r"[0-9a-f]{64}", str(metadata.get("html_sha256", "")))
                or review.get("verified_html_sha256") != metadata.get("html_sha256")
                or not stamp(metadata.get("captured_at"))
                or review.get("verified_captured_at") != metadata.get("captured_at")):
            continue
        compared = entry.get("compared_signal", {})
        target_url, target_day = compared.get("source_url"), compared.get("publication_date")
        target_queue = [(key, value) for key, value in context["queue"].items()
                        if value.get("raw", {}).get("url") == target_url]
        target_history = [value for value in history if value.get("source_url") == target_url
                          and value.get("event_date") == target_day]
        if len(target_queue) != 1 or len(target_history) != 1:
            continue
        target_key, target = target_queue[0]
        target_raw, signal = target.get("raw", {}), target_history[0]
        target_meta = target_raw.get("metadata", {})
        target_body = target_meta.get("page_text")
        target_copy = target_meta.get("analysis_model_output") or target_meta
        score = signal.get("editorial_relevance")
        if (target.get("status") != "published" or target_raw.get("event_date") != target_day
                or target_meta.get("canonical_url") != target_url or target_meta.get("publication_date") != target_day
                or target_meta.get("publication_date_verified") is not True
                or target_meta.get("article_verified") is not True or target_meta.get("primary_identity_verified") is not True
                or target_meta.get("article_body_complete") is not True or target_meta.get("source_quality_gate") != "passed"
                or not re.fullmatch(r"[0-9a-f]{64}", str(target_meta.get("html_sha256", "")))
                or not stamp(target_meta.get("captured_at"))
                or not isinstance(target_body, str) or len(target_body.strip()) < 160
                or digest(target_body.encode()) != target_meta.get("article_body_sha256")
                or signal.get("editorial_decision") == "reject" or signal.get("feed_visibility") is False
                or signal.get("source_type") != "official" and signal.get("evidence_maturity") != "media_reported"
                or type(score) is not int or score < 72 or not isinstance(target_copy, dict)
                or any(not isinstance(signal.get(field), str) or len(signal[field].strip()) < 20
                       or signal[field] != target_copy.get(field) for field in ("what_happened", "why_it_matters"))):
            continue
        bindings[url] = dict(review_ref=INCREMENTAL_REVIEW, review_sha256=INCREMENTAL_REVIEW_SHA256,
                             reason=reason, primary_publication_date=day,
                             primary_body_sha256=metadata["article_body_sha256"], primary_html_sha256=metadata["html_sha256"],
                             target_url=target_url, target_publication_date=target_day,
                             target_queue_fingerprint=target_key, target_body_sha256=target_meta["article_body_sha256"],
                             target_html_sha256=target_meta["html_sha256"], target_captured_at=target_meta["captured_at"],
                             target_signal_sha256=digest(signal))
    return bindings


def selected_partition(rows, urls, now, *, reviewed_holds=None):
    terminal, held = [], []
    for url in urls:
        require(url in rows, "selected_queue_identity_missing:" + url)
        row = rows[url]
        require(type(row["attempts"]) is int and row["attempts"] >= 0, "invalid_queue_attempts")
        require(not processing_evidence_failures(row), "selected_non_editorial_or_unresolved_hold:" + url)
        if row["status"] in TERMINAL:
            terminal.append(url)
            continue
        assessment = row.get("assessment") or {}
        reason = assessment.get("reason") or row.get("editorial_hold") or row.get("reason")
        require(row["status"] in {"pending", "retry"} and isinstance(reason, str) and reason
                and reason not in TECHNICAL_HOLDS
                and url in (reviewed_holds or {}) and reviewed_holds[url].get("reason") == reason,
                "selected_non_editorial_or_unresolved_hold:" + url)
        retry = stamp(row.get("retry_at"))
        require(retry is not None and retry > now, "selected_editorial_hold_is_due:" + url)
        held.append(url)
    return {"terminal_urls": sorted(terminal), "held_not_due_urls": sorted(held)}


def incremental_proof_files(root, queue):
    """Preserve both immutable reviews; a release never erases earlier evidence."""
    documents = {}
    for item in queue.values():
        if item.get("source") != SOURCE:
            continue
        metadata = item.get("raw", {}).get("metadata", {})
        for field, relative, expected in (
            ("incremental_review", INCREMENTAL_REVIEW, INCREMENTAL_REVIEW_SHA256),
            ("incremental_review_addendum", INCREMENTAL_ADDENDUM, INCREMENTAL_ADDENDUM_SHA256),
        ):
            review = metadata.get(field)
            if review is None:
                continue
            require(isinstance(review, dict) and review.get("review_ref") == relative
                    and review.get("review_sha256") == expected, field + "_reference_unverified")
            if field == "incremental_review_addendum":
                prior = metadata.get("incremental_review")
                require(isinstance(prior, dict) and prior.get("review_ref") == INCREMENTAL_REVIEW
                        and prior.get("review_sha256") == INCREMENTAL_REVIEW_SHA256
                        and review.get("prior_review_ref") == INCREMENTAL_REVIEW
                        and review.get("prior_review_sha256") == INCREMENTAL_REVIEW_SHA256
                        and review.get("decision") == "release_hold_for_editorial_analysis"
                        and review.get("publication_approved") is False,
                        "incremental_addendum_prior_review_unverified")
            raw = (root / relative).read_bytes()
            require(digest(raw) == expected, field + "_file_changed")
            documents[relative] = json.loads(raw)
    return documents


def paid_revalidation_proof_files(root):
    """Bind the paid-reuse authority before any admission stamp exists."""
    from radar_salud.pulso_paid_revalidation import MANIFEST_REF, MANIFEST_SHA256
    from radar_salud.pulso_current_paid_revalidation import (
        MANIFEST_REF as CURRENT_REF, MANIFEST_SHA256 as CURRENT_SHA)
    from radar_salud.pulso_followup_paid_revalidation import (
        MANIFEST_REF as FOLLOWUP_REF, MANIFEST_SHA256 as FOLLOWUP_SHA)
    from radar_salud.pulso_final_paid_revalidation import (
        MANIFEST_REF as FINAL_REF, MANIFEST_SHA256 as FINAL_SHA)
    authorities = (
        (MANIFEST_REF, MANIFEST_SHA256, "pulso_v5_paid_guard_revalidation_manifest_v1"),
        (CURRENT_REF, CURRENT_SHA, "pulso_current_paid_guard_revalidation_manifest_v1"),
        (FOLLOWUP_REF, FOLLOWUP_SHA, "pulso_followup_paid_guard_revalidation_manifest_v1"),
        (FINAL_REF, FINAL_SHA, "pulso_final_paid_guard_revalidation_manifest_v1"),
    )
    references = set()
    for manifest_ref, expected_sha, schema in authorities:
        path = root / manifest_ref
        if not path.is_file():
            continue
        payload = path.read_bytes()
        require(digest(payload) == expected_sha, "paid_revalidation_manifest_changed")
        manifest = json.loads(payload)
        require(manifest.get("schema_version") == schema
                and manifest.get("source_id") == SOURCE
                and isinstance(manifest.get("semantic_references"), list)
                and len(manifest["semantic_references"]) == 2,
                "paid_revalidation_manifest_invalid")
        bound = {manifest_ref}
        for proof in manifest["semantic_references"]:
            relative = proof.get("path") if isinstance(proof, dict) else None
            require(isinstance(relative, str), "paid_revalidation_semantic_path_invalid")
            source = (root / relative).resolve()
            require(source.is_relative_to((root / "data/audits").resolve()) and source.is_file()
                    and digest(source.read_bytes()) == proof.get("sha256"),
                    "paid_revalidation_semantic_reference_changed")
            bound.add(relative)
        require(len(bound) == 3, "paid_revalidation_semantic_reference_repeated")
        references.update(bound)
    return references


def read_context(root, *, selection=DEFAULT_SELECTION, report=DEFAULT_REPORT, qa=DEFAULT_QA):
    paths = dict(selection=selection, report=report, processing_qa=qa,
                 discovery="data/state/discovery_run.json", queue="data/state/pending_queue.json",
                 history="data/history/superintendencia_signals.json", feed="web/data/radar_today.json")
    values, hashes = {}, {}
    for key, relative in paths.items():
        raw = (root / relative).read_bytes()
        hashes[relative] = digest(raw)
        values[key] = json.loads(raw)
    telemetry = root / "data/ai_usage/responses.jsonl"
    raw = telemetry.read_bytes()
    hashes[str(telemetry.relative_to(root))] = digest(raw)
    events = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    ledgers = {}
    for path in sorted((root / "data/ai_usage").glob("????-??.json")):
        raw = path.read_bytes()
        ledgers[path.name] = json.loads(raw)
        hashes[str(path.relative_to(root))] = digest(raw)
    references = paid_revalidation_proof_files(root)
    inputs = values["selection"].get("inputs", {})
    for key in IMMUTABLE_COHORT_INPUTS:
        value = inputs.get(key)
        require(isinstance(value, dict) and isinstance(value.get("path"), str), "immutable_cohort_reference_missing:" + key)
        path = (root / value["path"]).resolve()
        require(path.is_relative_to(root.resolve()) and digest(path.read_bytes()) == value.get("sha256"),
                "immutable_cohort_reference_changed:" + key)
        references.add(value["path"])
    history = values["history"].get("signals", []) if isinstance(values["history"], dict) else values["history"]
    reviewed = [row.get("editorial_review", {}) for row in history]
    reviewed.extend(item.get("raw", {}).get("metadata", {}).get("editorial_review", {}) for item in values["queue"].values())
    references.update(review["review_file"] for review in reviewed if isinstance(review, dict) and isinstance(review.get("review_file"), str))
    if (root / EDITORIAL_REVIEW_REGISTRY).is_file():
        # Authorizing a future independent audit is a data mutation. Preserve
        # the whole approval registry, including an initially empty registry,
        # so it cannot change silently between the paid run and its replay.
        references.add(EDITORIAL_REVIEW_REGISTRY)
        registry = json.loads((root / EDITORIAL_REVIEW_REGISTRY).read_bytes())
        require(registry.get("schema_version") == "pulso_paid_editorial_review_registry_v1"
                and registry.get("source_id") == SOURCE and isinstance(registry.get("reviews"), list),
                "editorial_review_registry_invalid")
        for pair in registry["reviews"]:
            require(isinstance(pair, dict), "editorial_review_registry_pair_invalid")
            for field, sha_field in (("review_file", "review_sha256"),
                                     ("independent_review_file", "independent_review_sha256")):
                relative = pair.get(field)
                require(isinstance(relative, str), "editorial_review_registry_path_invalid")
                path = (root / relative).resolve()
                require(path.is_relative_to((root / "data/audits").resolve()) and path.is_file()
                        and digest(path.read_bytes()) == pair.get(sha_field),
                        "editorial_review_registry_pair_hash_changed")
                references.add(relative)
    incremental_review_files = incremental_proof_files(root, values["queue"])
    references.update(incremental_review_files)
    proof_files = {}
    for relative in sorted(references):
        path = (root / relative).resolve()
        require(path.is_relative_to(root.resolve()), "unsafe_referenced_proof_file")
        proof_files[relative] = digest(path.read_bytes())
        hashes[relative] = proof_files[relative]
    fingerprint = runtime_fingerprint(root)
    core_execution = values["report"].get("last_core_execution") or values["report"].get("execution", {})
    values.update(events=events, ledgers=ledgers, observed_files=hashes, runtime_fingerprint=fingerprint,
                  referenced_proof_files=proof_files,
                  incremental_review_files=incremental_review_files,
                  cohort_declared_reference_provenance=inputs,
                  recorded_core_runtime_fingerprint=core_checkout_files(root, core_execution.get("code_sha"), fingerprint["files"]))
    return values


def core_proof(context):
    report, discovery, cohort = context["report"], context["discovery"], context["selection"]
    execution = report.get("last_core_execution") or report.get("execution", {})
    start, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    require(execution.get("mode") == "real_core_processing" and execution.get("engine_called") is True
            and execution.get("engine_completed") is True and start and end and start <= end,
            "genuine_completed_core_processing_required")
    require(execution.get("ai_guardrails_modified") is False, "analysis_guardrails_changed")
    require(isinstance(execution.get("code_sha"), str) and re.fullmatch(r"[0-9a-f]{40}", execution["code_sha"])
            and execution.get("runtime_fingerprint") == context["runtime_fingerprint"]
            and context.get("recorded_core_runtime_fingerprint") == execution["runtime_fingerprint"],
            "actual_core_runtime_fingerprint_unverified")
    require(report.get("discovery_persisted_by_current_execution") is True
            and stamp(discovery.get("at")) and start <= stamp(discovery["at"]) <= end,
            "current_original_discovery_missing")
    source = discovery.get("sources", {}).get(SOURCE, {})
    require(report.get("source") == SOURCE and report.get("runtime") == "daily_core" and report.get("core_source_present") is True
            and discovery.get("runtime") == "daily_core" and discovery.get("selected_sources") == [SOURCE],
            "genuine_source_scoped_daily_core_required")
    require(source.get("technical_status") == "ok" and not source.get("error_type"), "source_discovery_not_complete")
    urls = cohort.get("urls", [])
    require(cohort.get("source") == SOURCE and len(urls) == len(set(urls)) == 113
            and {row["url"] for row in cohort.get("items", [])} == set(urls), "full_immutable_113_cohort_required")
    recorded = discovery.get("processing_selection")
    require(isinstance(recorded, dict) and recorded == execution.get("processing_selection"), "selection_not_bound_to_actual_core")
    sha = context["observed_files"][DEFAULT_SELECTION]
    require(recorded.get("sha256") == recorded.get("file_sha256") == sha
            and recorded.get("reason") == "explicit_queue_selection"
            and recorded.get("selected_urls") == urls
            and recorded.get("selected_url_count") == recorded.get("matched_existing_url_count") == 113
            and not recorded.get("validation_error"), "actual_113_selection_mismatch")
    current = source_queue(context["queue"])
    for item in cohort["items"]:
        url = item["url"]
        require(url in current and current[url]["fingerprint"] == item.get("queue_fingerprint"),
                "immutable_selected_queue_fingerprint_changed:" + url)
        raw = context["queue"][current[url]["fingerprint"]]["raw"]
        metadata = raw.get("metadata", {})
        require(not processing_evidence_failures(current[url]), "selected_non_editorial_or_unresolved_hold:" + url)
        body = metadata.get("page_text")
        require(isinstance(body, str) and digest(body.encode()) == metadata.get("article_body_sha256") == item.get("body_sha256")
                and len(body) == item.get("body_characters") and raw.get("event_date") == item.get("publication_date"),
                "immutable_selected_primary_body_or_date_changed:" + url)
    delta = budget_delta(execution)
    require(context["ledgers"].get(end.strftime("%Y-%m") + ".json") == execution["budget_after"]["month"],
            "actual_persisted_month_ledger_mismatch")
    run_events = [event for event in context["events"] if stamp(event.get("at")) and start <= stamp(event["at"]) <= end]
    for tier in ("fast", "deep"):
        events = [event for event in run_events if event.get("kind") == tier]
        require(len(events) == delta[tier]["attempted"]
                and sum(event.get("success") is True for event in events) == delta[tier]["successful"],
                "actual_response_events_ledger_mismatch")
        require(all(event.get("response_id") for event in events if event.get("success") is True),
                "actual_successful_response_id_missing")
    ids = [event["response_id"] for event in run_events if event.get("success") is True]
    require(len(ids) == len(set(ids)), "duplicate_actual_response_id")
    return execution, urls, delta, run_events


def semantic_snapshot(context):
    rows = source_queue(context["queue"])
    source_primary = {}
    for row in context["report"].get("matrix", []):
        if not row.get("current_core_detected"):
            continue
        facts = dict(publication_date=row.get("publication_date"), publication_date_verified=row.get("publication_date_verified"),
                     current_core_verified_health=row.get("current_core_verified_health"),
                     metadata_only_candidate=row.get("metadata_only_candidate"),
                     publisher_exception_reason=row.get("publisher_exception_reason"))
        traces = row.get("current_discovery_trace", [])
        facts["body_sha256s"] = sorted({trace["article_body_sha256"] for trace in traces if trace.get("article_body_sha256")})
        source_primary[row["url"]] = facts
    require(source_primary, "current_source_primary_inventory_missing")
    return dict(source_queue=rows, source_primary=source_primary,
                reviewed_hold_bindings=reviewed_hold_bindings(context),
                history=signal_index(context["history"]), feed=signal_index(context["feed"]),
                referenced_proof_files=context.get("referenced_proof_files", {}),
                ledgers=context["ledgers"], response_event_sha256s=[digest(event) for event in context["events"]],
                actual_response_ids=[event.get("response_id") for event in context["events"] if event.get("success") is True])


def native_queue(queue):
    # Retain whole records. The compact source snapshot's cache exclusions are
    # deliberately unavailable for proving that other connectors were inert.
    return {key: digest(item) for key, item in queue.items() if item.get("source") != SOURCE}


def revalidated_snapshot(context):
    result = semantic_snapshot(context)
    result["native_queue"] = native_queue(context["queue"])
    return result


def terminal_snapshot(context, *, root):
    result = revalidated_snapshot(context)
    reader = final_paid_reader(root)
    for item in context["queue"].values():
        if item.get("source") == SOURCE:
            url = item.get("raw", {}).get("url")
            result["source_queue"][url]["semantic_sha256"] = digest(reader.terminal_source_inventory_semantic(item))
    return result


def final_paid_reader(root):
    path = root / "scripts/qa_pulso_recovery.py"
    spec = importlib.util.spec_from_file_location("pulso_revalidated_idempotence_reader", path)
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    require(callable(getattr(reader, "final_paid_origin", None))
            and callable(getattr(reader, "verify_final_paid_revalidation", None)),
            "independent_final_paid_reader_unavailable")
    return reader


def revalidated_paid_lineage(context, execution, *, root):
    """Recompute the independent composite proof without relabelling paid323."""
    reader = final_paid_reader(root)
    require(callable(getattr(reader, "verify_final_revalidated_execution", None)),
            "independent_final_revalidated_execution_reader_unavailable")
    history = context["history"]
    history = history["signals"] if isinstance(history, dict) else history
    result = reader.verify_final_revalidated_execution(root, report=context["report"],
        queue=context["queue"], history=history, telemetry=context["events"], execution=execution)
    require(isinstance(result, dict) and result.get("evaluation_execution") == execution
            and result.get("actual_budget_delta") == budget_delta(execution)
            and result.get("publication_approved") is False,
            "independent_final_revalidated_execution_binding_missing")
    return result["paid_model_lineage"], result["launch_stock"], result["current_revalidation_receipts"]


def capture_revalidated_baseline(context, *, root=ROOT, now=None):
    now = now or datetime.now(timezone.utc)
    qa = context["processing_qa"]
    require(qa.get("phase") == "real_core_processing" and qa.get("requested_phase") == "processing"
            and qa.get("verdict") == "PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW"
            and qa.get("discovery_qa") == qa.get("processing_qa") == "PASS"
            and qa.get("acceptance") == "PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW"
            and not qa.get("findings"), "revalidated_processing_qa_pass_required")
    execution, urls, delta, events = core_proof(context)
    require(all(value == 0 for tier in delta.values() for value in tier.values()) and not events,
            "revalidated_baseline_must_use_zero_new_ai")
    require(execution.get("processing_attempts_increased") == context["discovery"].get("processing_attempts") == 2,
            "genuine_two_revalidation_processing_attempts_required")
    require(qa.get("checks", {}).get("actual_ai_budget_delta") == delta
            and qa["checks"].get("actual_fast_response_events") == 0
            and qa["checks"].get("processing_selection", {}).get("sha256") == context["observed_files"][DEFAULT_SELECTION]
            and qa["checks"]["processing_selection"].get("selected_urls") == 113,
            "passing_revalidation_qa_not_bound_to_actual_observations")
    snapshot = revalidated_snapshot(context)
    partition = selected_partition(snapshot["source_queue"], urls, now)
    require(len(partition["terminal_urls"]) == 113 and not partition["held_not_due_urls"]
            and all(snapshot["source_queue"][url]["status"] in {"published", "rejected"} for url in urls),
            "revalidated_baseline_requires_all113_terminal")
    lineage, stock, receipts = revalidated_paid_lineage(context, execution, root=root)
    recorded = execution["processing_selection"]
    require(set(recorded.get("ready_selected_urls", [])) == set(lineage["models"])
            and sorted(recorded.get("skipped_terminal_urls", [])) == sorted(stock["preserved_terminal_urls"])
            and not recorded.get("skipped_not_due_urls") and not recorded.get("skipped_in_progress_urls"),
            "actual_two_reuse_and111_terminal_skip_unverified")
    bundle = dict(schema_version=SCHEMA, mode=REVALIDATED_MODE, at=now.isoformat(), read_only=True,
        baseline_execution=execution, revalidated_budget_delta=delta, revalidated_successful_response_ids=[],
        paid_model_lineage=lineage, launch_stock=stock, current_revalidation_receipts=receipts,
        selection=dict(path=DEFAULT_SELECTION, sha256=context["observed_files"][DEFAULT_SELECTION], urls=urls,
                       count=113, current_partition=partition), observed_files=context["observed_files"],
        runtime_fingerprint=context["runtime_fingerprint"],
        cohort_declared_reference_provenance=context.get("cohort_declared_reference_provenance", {}),
        processing_qa=dict(verdict=qa["verdict"], discovery_qa="PASS", processing_qa="PASS",
            requested_phase=qa["requested_phase"], acceptance=qa["acceptance"], phase=qa["phase"],
            sha256=context["observed_files"][DEFAULT_QA], checks=qa.get("checks", {})), semantic=snapshot,
        acceptance_note="Original paid323 QA remains FAIL. Actual repaired zero-AI processing passes; independent editorial/final staging acceptance remains separate.")
    bundle["payload_sha256"] = digest(bundle)
    validate_revalidated_baseline(bundle)
    return bundle


def validate_revalidated_baseline(bundle):
    require(bundle.get("schema_version") == SCHEMA and bundle.get("mode") == REVALIDATED_MODE
            and bundle.get("read_only") is True, "invalid_revalidated_idempotence_baseline")
    require(bundle.get("payload_sha256") == digest({key: value for key, value in bundle.items() if key != "payload_sha256"}),
            "baseline_payload_sha256_mismatch")
    quality = bundle["processing_qa"]
    require(quality.get("phase") == "real_core_processing" and quality.get("requested_phase") == "processing"
            and quality.get("verdict") == "PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW"
            and quality.get("discovery_qa") == quality.get("processing_qa") == "PASS"
            and quality.get("acceptance") == "PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW",
            "baseline_revalidated_processing_qa_missing")
    execution, lineage, stock = bundle["baseline_execution"], bundle["paid_model_lineage"], bundle["launch_stock"]
    delta = budget_delta(execution)
    require(delta == bundle["revalidated_budget_delta"]
            and all(value == 0 for tier in delta.values() for value in tier.values())
            and bundle["revalidated_successful_response_ids"] == [] and execution.get("processing_attempts_increased") == 2
            and quality["checks"].get("actual_ai_budget_delta") == delta
            and quality["checks"].get("actual_fast_response_events") == 0,
            "baseline_zero_ai_two_revalidation_proof_missing")
    require(execution.get("mode") == "real_core_processing" and execution.get("engine_called") is True
            and execution.get("engine_completed") is True and execution.get("ai_guardrails_modified") is False
            and stamp(execution.get("started_at")) and stamp(execution.get("finished_at"))
            and stamp(execution["started_at"]) <= stamp(execution["finished_at"]),
            "baseline_revalidated_execution_not_genuine")
    require("paid_budget_delta" not in bundle and "paid_successful_response_ids" not in bundle
            and lineage.get("schema_version") == "pulso_genuine_paid_model_lineage_v1"
            and lineage.get("producer_state_commit") == FINAL_PAID_PRODUCER
            and lineage.get("producer_core_checkout") == FINAL_PAID_CODE
            and lineage.get("original_paid_qa_promoted") is False
            and lineage.get("same_runtime_fingerprint_as_baseline") is False
            and lineage["original_processing_qa"].get("verdict") == lineage["original_processing_qa"].get("processing_qa") == "FAIL"
            and lineage["original_processing_qa"].get("findings"), "baseline_original_paid_failure_erased_or_promoted")
    original, fingerprint = lineage["original_execution"], lineage["original_runtime_fingerprint"]
    original_delta = budget_delta(original)
    ids = lineage["original_successful_response_ids"]
    require(original_delta == lineage["original_budget_delta"] == {
                "fast": dict(attempted=2, successful=2, failed=0), "deep": dict(attempted=0, successful=0, failed=0)}
            and original.get("code_sha") == FINAL_PAID_CODE and original.get("runtime_fingerprint") == fingerprint
            and fingerprint.get("sha256") == FINAL_PAID_FINGERPRINT
            and digest(fingerprint.get("files")) == FINAL_PAID_FINGERPRINT
            and fingerprint != bundle["runtime_fingerprint"] and len(ids) == len(set(ids)) == 2
            and set(ids) <= set(bundle["semantic"]["actual_response_ids"])
            and len(lineage["models"]) == 2
            and {row["original_response_id"] for row in lineage["models"].values()} == set(ids)
            and all(row["receipt"].get("original_model_output_sha256") == row["original_model_output_sha256"]
                    and row["receipt"].get("original_response_id") == row["original_response_id"]
                    and row["receipt"].get("original_model_output_unchanged") is True
                    and row["receipt"].get("new_model_request") is False
                    and row["receipt"].get("publication_approved") is False
                    and type(row["admission"].get("original_attempts")) is int
                    and row["admission"].get("original_attempts") + 1 == bundle["semantic"]["source_queue"][url]["attempts"]
                    for url, row in lineage["models"].items()), "baseline_original_paid_model_lineage_invalid")
    require(original.get("mode") == "real_core_processing" and original.get("engine_called") is True
            and original.get("engine_completed") is True and original.get("ai_guardrails_modified") is False
            and lineage["original_processing_qa"].get("acceptance") == "NOT_ACCEPTED"
            and lineage["original_processing_qa"].get("checks", {}).get("actual_ai_budget_delta") == original_delta,
            "baseline_original_paid_failure_not_genuine")
    require(execution.get("runtime_fingerprint") == bundle["runtime_fingerprint"]
            and re.fullmatch(r"[0-9a-f]{40}", str(execution.get("code_sha", "")))
            and stock.get("commit") == execution["code_sha"]
            and stamp(original.get("finished_at")) < stamp(execution.get("started_at")),
            "baseline_original_and_revalidated_execution_binding_invalid")
    selection, partition = bundle["selection"], bundle["selection"]["current_partition"]
    require(selection.get("count") == len(set(selection["urls"])) == 113
            and partition == dict(terminal_urls=sorted(selection["urls"]), held_not_due_urls=[])
            and all(bundle["semantic"]["source_queue"][url]["status"] in {"published", "rejected"}
                    for url in selection["urls"])
            and len(stock["preserved_terminal_urls"]) == 111
            and set(stock["preserved_terminal_urls"]) == set(selection["urls"]) - set(lineage["models"])
            and stock.get("native_queue_count") == len(bundle["semantic"]["native_queue"]) == 5293
            and stock.get("native_history_count") == 897
            and re.fullmatch(r"[0-9a-f]{64}", str(stock.get("native_queue_sha256", "")))
            and re.fullmatch(r"[0-9a-f]{64}", str(stock.get("native_history_sha256", ""))),
            "baseline_full113_terminal_and_native_stock_proof_missing")
    require(execution.get("processing_selection", {}).get("selected_urls") == selection["urls"]
            and execution["processing_selection"].get("sha256") == selection["sha256"]
            and quality["checks"].get("processing_selection", {}).get("sha256") == selection["sha256"]
            and quality["checks"]["processing_selection"].get("selected_urls") == 113
            and set(bundle["current_revalidation_receipts"]) == set(lineage["models"])
            and all(receipt.get("original_response_id") == lineage["models"][url]["original_response_id"]
                    == receipt.get("current_response_id") and receipt.get("old_paid_output_reused") is True
                    and receipt.get("publication_approved") is False
                    and receipt.get("current_evaluation_code") == execution["code_sha"]
                    and receipt.get("current_receipt_sha256") == digest(lineage["models"][url]["receipt"])
                    for url, receipt in bundle["current_revalidation_receipts"].items()),
            "baseline_full_selection_or_two_current_receipts_missing")


def terminal_followthrough_provenance(context, execution, *, root):
    reader = final_paid_reader(root)
    require(callable(getattr(reader, "verify_terminal_followthrough_execution", None)),
            "independent_terminal_followthrough_reader_unavailable")
    history = context["history"]
    history = history["signals"] if isinstance(history, dict) else history
    result = reader.verify_terminal_followthrough_execution(root, report=context["report"],
        queue=context["queue"], history=history, snapshot=context["feed"], telemetry=context["events"], execution=execution)
    require(isinstance(result, dict) and result.get("current_followthrough_execution") == execution
            and result.get("actual_budget_delta") == budget_delta(execution)
            and result.get("publication_approved") is False,
            "independent_terminal_followthrough_execution_binding_missing")
    return result


def terminal_context(context, *, root):
    # This mode alone binds the later ordinary-processing namespace. Older
    # baseline contracts retain their original proof inventory unchanged.
    result = dict(context)
    result["referenced_proof_files"] = dict(context.get("referenced_proof_files", {}))
    result["observed_files"] = dict(context["observed_files"])
    for path, expected in SETTLEMENT_REVIEW_FILES.items():
        require(digest((root / path).read_bytes()) == expected, "terminal_settlement_review_file_changed")
        result["referenced_proof_files"][path] = expected
        result["observed_files"][path] = expected
    return result


def capture_terminal_followthrough_baseline(context, *, root=ROOT, now=None):
    context = terminal_context(context, root=root)
    now = now or datetime.now(timezone.utc)
    qa = context["processing_qa"]
    require(qa.get("phase") == "real_core_processing" and qa.get("requested_phase") == "processing"
            and qa.get("verdict") == "PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW"
            and qa.get("discovery_qa") == qa.get("processing_qa") == "PASS"
            and qa.get("acceptance") == "PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW"
            and not qa.get("findings"), "terminal_followthrough_processing_qa_pass_required")
    execution, urls, delta, events = core_proof(context)
    require(all(value == 0 for tier in delta.values() for value in tier.values()) and not events
            and execution.get("processing_attempts_increased") == context["discovery"].get("processing_attempts") == 0,
            "terminal_followthrough_requires_zero_actual_ai_and_attempts")
    require(qa.get("checks", {}).get("actual_ai_budget_delta") == delta
            and qa["checks"].get("actual_fast_response_events") == 0
            and qa["checks"].get("processing_selection", {}).get("sha256") == context["observed_files"][DEFAULT_SELECTION]
            and qa["checks"]["processing_selection"].get("selected_urls") == 113,
            "passing_terminal_followthrough_qa_not_bound_to_actual_observations")
    snapshot = terminal_snapshot(context, root=root)
    partition = selected_partition(snapshot["source_queue"], urls, now)
    recorded = execution["processing_selection"]
    require(partition == dict(terminal_urls=sorted(urls), held_not_due_urls=[])
            and all(snapshot["source_queue"][url]["status"] in {"published", "rejected"} for url in urls)
            and sorted(recorded.get("skipped_terminal_urls", [])) == sorted(urls)
            and not any(recorded.get(field) for field in (
                "ready_selected_urls", "skipped_not_due_urls", "skipped_in_progress_urls")),
            "terminal_followthrough_requires_actual_all113_terminal_skip")
    proof = terminal_followthrough_provenance(context, execution, root=root)
    bundle = dict(schema_version=SCHEMA, mode=TERMINAL_FOLLOWTHROUGH_MODE, at=now.isoformat(), read_only=True,
        baseline_execution=execution, terminal_budget_delta=delta, terminal_successful_response_ids=[],
        terminal_followthrough_provenance=proof,
        archived_producer=dict(state_commit=ARCHIVED_FINAL_PRODUCER, core_checkout=ARCHIVED_FINAL_CODE,
            runtime_fingerprint_sha256=ARCHIVED_FINAL_FINGERPRINT, files=dict(ARCHIVED_FINAL_FILES)),
        settlement_producer=dict(state_commit=SETTLEMENT_PRODUCER, core_checkout=SETTLEMENT_CODE,
            runtime_fingerprint_sha256=SETTLEMENT_FINGERPRINT, files=dict(SETTLEMENT_FILES)),
        allowed_consumer_changes=sorted(ALLOWED_TERMINAL_CONSUMER_CHANGES),
        selection=dict(path=DEFAULT_SELECTION, sha256=context["observed_files"][DEFAULT_SELECTION], urls=urls,
                       count=113, current_partition=partition), observed_files=context["observed_files"],
        runtime_fingerprint=context["runtime_fingerprint"],
        cohort_declared_reference_provenance=context.get("cohort_declared_reference_provenance", {}),
        processing_qa=dict(verdict=qa["verdict"], discovery_qa="PASS", processing_qa="PASS",
            requested_phase=qa["requested_phase"], acceptance=qa["acceptance"], phase=qa["phase"],
            sha256=context["observed_files"][DEFAULT_QA], checks=qa.get("checks", {})), semantic=snapshot,
        acceptance_note="Original paid323, final123 and LIVE9 settlement QA remain FAIL. Bound ordinary LIVE9 processing may add real usage; fresh terminal followthrough uses zero new AI with unchanged runtime outside four consumers. Final acceptance remains separate.")
    bundle["payload_sha256"] = digest(bundle)
    validate_terminal_followthrough_baseline(bundle)
    return bundle


def validate_terminal_followthrough_baseline(bundle):
    require(bundle.get("schema_version") == SCHEMA and bundle.get("mode") == TERMINAL_FOLLOWTHROUGH_MODE
            and bundle.get("read_only") is True, "invalid_terminal_followthrough_baseline")
    require(bundle.get("payload_sha256") == digest({key: value for key, value in bundle.items() if key != "payload_sha256"}),
            "baseline_payload_sha256_mismatch")
    require(bundle.get("archived_producer") == dict(state_commit=ARCHIVED_FINAL_PRODUCER,
                core_checkout=ARCHIVED_FINAL_CODE, runtime_fingerprint_sha256=ARCHIVED_FINAL_FINGERPRINT,
                files=ARCHIVED_FINAL_FILES)
            and bundle.get("settlement_producer") == dict(state_commit=SETTLEMENT_PRODUCER,
                core_checkout=SETTLEMENT_CODE, runtime_fingerprint_sha256=SETTLEMENT_FINGERPRINT, files=SETTLEMENT_FILES)
            and bundle.get("allowed_consumer_changes") == sorted(ALLOWED_TERMINAL_CONSUMER_CHANGES),
            "terminal_followthrough_archive_or_consumer_scope_changed")
    execution, quality = bundle["baseline_execution"], bundle["processing_qa"]
    proof = bundle["terminal_followthrough_provenance"]
    require(proof.get("schema_version") == "pulso_terminal_followthrough_provenance_v1"
            and proof.get("archived_producer") == dict(commit=ARCHIVED_FINAL_PRODUCER, code_sha=ARCHIVED_FINAL_CODE,
                runtime_fingerprint_sha256=ARCHIVED_FINAL_FINGERPRINT, files=ARCHIVED_FINAL_FILES, original_qa_promoted=False)
            and proof.get("settlement_producer") == dict(commit=SETTLEMENT_PRODUCER, code_sha=SETTLEMENT_CODE,
                runtime_fingerprint_sha256=SETTLEMENT_FINGERPRINT, files=SETTLEMENT_FILES, original_qa_promoted=False),
            "terminal_followthrough_provenance_descriptor_changed")
    archived = proof["archived_final_evaluation"]["evaluation_execution"]
    archived_qa = proof["archived_processing_qa"]
    delta = budget_delta(execution)
    require(proof.get("current_followthrough_execution") == execution and proof.get("actual_budget_delta") == delta
            and proof.get("publication_approved") is False and delta == bundle["terminal_budget_delta"]
            and not any(value for tier in delta.values() for value in tier.values())
            and bundle.get("terminal_successful_response_ids") == [] and execution.get("processing_attempts_increased") == 0
            and execution.get("mode") == "real_core_processing" and execution.get("engine_called") is True
            and execution.get("engine_completed") is True and execution.get("ai_guardrails_modified") is False,
            "terminal_followthrough_current_execution_not_genuine_zero")
    require(quality.get("phase") == "real_core_processing" and quality.get("requested_phase") == "processing"
            and quality.get("verdict") == "PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW"
            and quality.get("discovery_qa") == quality.get("processing_qa") == "PASS"
            and quality.get("acceptance") == "PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW"
            and quality.get("checks", {}).get("actual_ai_budget_delta") == delta
            and quality["checks"].get("actual_fast_response_events") == 0,
            "terminal_followthrough_current_processing_qa_missing")
    original = archived["runtime_fingerprint"]
    current = bundle["runtime_fingerprint"]
    require(archived.get("code_sha") == ARCHIVED_FINAL_CODE
            and original.get("sha256") == digest(original.get("files")) == ARCHIVED_FINAL_FINGERPRINT
            and archived.get("processing_attempts_increased") == 2
            and not any(value for tier in budget_delta(archived).values() for value in tier.values())
            and archived_qa.get("verdict") == archived_qa.get("processing_qa") == "FAIL"
            and archived_qa.get("acceptance") == "NOT_ACCEPTED" and len(archived_qa.get("findings", [])) == 24,
            "terminal_followthrough_archived_real_evaluation_or_failure_changed")
    require(set(original["files"]) == set(current["files"])
            and current.get("sha256") == digest(current["files"])
            and original.get("git_or_marker_sha_used") is current.get("git_or_marker_sha_used") is False
            and all(current["files"][path] == value for path, value in original["files"].items()
                    if path not in ALLOWED_TERMINAL_CONSUMER_CHANGES)
            and execution.get("runtime_fingerprint") == current
            and re.fullmatch(r"[0-9a-f]{40}", str(execution.get("code_sha", "")))
            and stamp(archived.get("finished_at")) < stamp(execution.get("started_at")) <= stamp(execution.get("finished_at")),
            "terminal_followthrough_runtime_changed_outside_bound_consumers")
    lineage = proof["paid_model_lineage"]
    require(lineage == proof["archived_final_evaluation"]["paid_model_lineage"]
            and lineage.get("producer_state_commit") == FINAL_PAID_PRODUCER
            and lineage.get("original_paid_qa_promoted") is False
            and lineage.get("same_runtime_fingerprint_as_baseline") is False
            and lineage["original_processing_qa"].get("processing_qa") == "FAIL"
            and lineage["original_budget_delta"]["fast"] == dict(attempted=2, successful=2, failed=0)
            and len(set(lineage["original_successful_response_ids"])) == 2
            and set(lineage["original_successful_response_ids"]) <= set(bundle["semantic"]["actual_response_ids"])
            and len(proof["preserved_final_receipts"]) == 2,
            "terminal_followthrough_original_paid_or_final_receipts_erased")
    settlement = proof["settlement_execution"]
    settled_fp = settlement["runtime_fingerprint"]
    settled_delta = budget_delta(settlement)
    require(settlement.get("code_sha") == SETTLEMENT_CODE
            and settled_fp.get("sha256") == digest(settled_fp.get("files")) == SETTLEMENT_FINGERPRINT
            and settlement.get("mode") == "real_core_processing" and settlement.get("engine_called") is True
            and settlement.get("engine_completed") is True and settlement.get("ai_guardrails_modified") is False
            and settlement.get("processing_attempts_increased") == 9
            and settled_delta == proof["settlement_budget_delta"] == {
                "fast": dict(attempted=4, successful=4, failed=0), "deep": dict(attempted=0, successful=0, failed=0)}
            and proof["settlement_processing_qa"].get("verdict") == proof["settlement_processing_qa"].get("processing_qa") == "FAIL"
            and len(proof["settlement_processing_qa"].get("findings", [])) == 1477
            and len(proof["settlement_live9"]) == 9
            and not set(proof["settlement_live9"]) & set(bundle["selection"]["urls"])
            and all(row.get("status") == "rejected" and row.get("attempts") == 1
                    and bundle["semantic"]["source_queue"][url]["status"] == "rejected"
                    and bundle["semantic"]["source_queue"][url]["attempts"] == 1
                    for url, row in proof["settlement_live9"].items())
            and set(settled_fp["files"]) == set(original["files"])
            and all(settled_fp["files"][path] == value for path, value in original["files"].items()
                    if path not in ALLOWED_TERMINAL_CONSUMER_CHANGES)
            and stamp(archived.get("finished_at")) < stamp(settlement.get("started_at"))
                <= stamp(settlement.get("finished_at")) < stamp(execution.get("started_at"))
            and execution["budget_before"]["month"] == execution["budget_after"]["month"] == settlement["budget_after"]["month"],
            "terminal_followthrough_settlement_execution_or_usage_changed")
    events = proof["settlement_response_events"]
    require(len(events) == len({event.get("response_id") for event in events}) == 4
            and all(event.get("kind") == "fast" and event.get("success") is True
                and isinstance(event.get("response_id"), str) and event["response_id"]
                and stamp(settlement["started_at"]) <= stamp(event.get("at")) <= stamp(settlement["finished_at"])
                for event in events)
            and {event["response_id"] for event in events} <= set(bundle["semantic"]["actual_response_ids"])
            and all(bundle["semantic"]["referenced_proof_files"].get(path) == sha
                    for path, sha in SETTLEMENT_REVIEW_FILES.items()),
            "terminal_followthrough_settlement_responses_or_reviews_missing")
    selection, stock = bundle["selection"], proof["launch_stock"]
    require(selection.get("count") == len(set(selection["urls"])) == 113
            and selection["current_partition"] == dict(terminal_urls=sorted(selection["urls"]), held_not_due_urls=[])
            and all(bundle["semantic"]["source_queue"][url]["status"] in {"published", "rejected"}
                    for url in selection["urls"])
            and execution["processing_selection"].get("selected_urls") == selection["urls"]
            and execution["processing_selection"].get("sha256") == selection["sha256"]
            and sorted(execution["processing_selection"].get("skipped_terminal_urls", [])) == sorted(selection["urls"])
            and not any(execution["processing_selection"].get(field) for field in (
                "ready_selected_urls", "skipped_not_due_urls", "skipped_in_progress_urls"))
            and quality["checks"].get("processing_selection", {}).get("sha256") == selection["sha256"]
            and quality["checks"]["processing_selection"].get("selected_urls") == 113
            and len(bundle["semantic"]["native_queue"]) == stock.get("native_queue_count") == 5293
            and stock.get("native_history_count") == 897
            and stock.get("commit") == SETTLEMENT_PRODUCER
            and stock.get("file_sha256") == SETTLEMENT_FILES,
            "terminal_followthrough_full113_or_native_stock_missing")
    source_rows = bundle["semantic"]["source_queue"]
    source_stocks = stock["source_queue_semantic_sha256s"]
    require(all(url in source_rows and source_rows[url]["semantic_sha256"] == sha for url, sha in source_stocks.items())
            and set(selection["urls"]) | set(proof["settlement_live9"]) <= set(source_stocks)
            and all(source_rows[url]["attempts"] == 0 and source_rows[url]["status"] in {"pending", "archived"}
                    for url in set(source_rows) - set(source_stocks)),
            "terminal_followthrough_existing_source_semantics_changed")
    require(not any(field in bundle for field in ("paid_budget_delta", "paid_successful_response_ids",
                "revalidated_budget_delta", "revalidated_successful_response_ids")),
            "terminal_followthrough_retagged_as_paid_or_revalidation")


def capture_baseline(context, *, now=None):
    now = now or datetime.now(timezone.utc)
    qa = context["processing_qa"]
    require(qa.get("phase") == "real_core_processing" and qa.get("requested_phase") == "processing"
            and qa.get("verdict") == "PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW"
            and qa.get("discovery_qa") == "PASS" and qa.get("processing_qa") == "PASS"
            and qa.get("acceptance") == "PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW"
            and not qa.get("findings"), "paid_processing_qa_pass_required")
    execution, urls, delta, events = core_proof(context)
    require(context.get("recorded_core_runtime_fingerprint") == context["runtime_fingerprint"],
            "current_implementation_differs_from_genuine_paid_core")
    require(delta["fast"]["attempted"] > 0 and delta["fast"]["successful"] > 0,
            "positive_genuine_paid_processing_required")
    require(qa.get("checks", {}).get("actual_ai_budget_delta") == delta
            and qa.get("checks", {}).get("actual_fast_response_events") == delta["fast"]["attempted"],
            "passing_qa_not_bound_to_actual_paid_observations")
    selection_check = qa.get("checks", {}).get("processing_selection", {})
    require(selection_check.get("sha256") == context["observed_files"][DEFAULT_SELECTION]
            and selection_check.get("selected_urls") == 113,
            "passing_qa_not_bound_to_full_processing_cohort")
    snapshot = semantic_snapshot(context)
    partition = selected_partition(snapshot["source_queue"], urls, now, reviewed_holds=snapshot["reviewed_hold_bindings"])
    bundle = dict(schema_version=SCHEMA, mode="genuine_processing_baseline", at=now.isoformat(), read_only=True,
                  baseline_execution=execution, paid_budget_delta=delta,
                  paid_successful_response_ids=[event["response_id"] for event in events if event.get("success") is True],
                  selection=dict(path=DEFAULT_SELECTION, sha256=context["observed_files"][DEFAULT_SELECTION], urls=urls,
                                 count=113, current_partition=partition),
                  observed_files=context["observed_files"], runtime_fingerprint=context["runtime_fingerprint"],
                  cohort_declared_reference_provenance=context.get("cohort_declared_reference_provenance", {}),
                  moving_reference_policy="Cohort-declared runtime/queue hashes cite historical observations; current mutable paths are not immutable review files.",
                  processing_qa=dict(verdict=qa["verdict"], discovery_qa="PASS", processing_qa="PASS",
                                     requested_phase=qa["requested_phase"],
                                     acceptance=qa["acceptance"], phase=qa["phase"],
                                     sha256=context["observed_files"][DEFAULT_QA], checks=qa.get("checks", {})),
                  semantic=snapshot,
                  acceptance_note="Paid processing QA passes; independent editorial/final staging acceptance remains separate.")
    bundle["payload_sha256"] = digest(bundle)
    return bundle


def validate_baseline(bundle):
    if bundle.get("mode") == TERMINAL_FOLLOWTHROUGH_MODE:
        validate_terminal_followthrough_baseline(bundle)
        return
    if bundle.get("mode") == REVALIDATED_MODE:
        validate_revalidated_baseline(bundle)
        return
    require(bundle.get("schema_version") == SCHEMA and bundle.get("mode") == "genuine_processing_baseline"
            and bundle.get("read_only") is True, "invalid_idempotence_baseline")
    require(bundle.get("payload_sha256") == digest({key: value for key, value in bundle.items() if key != "payload_sha256"}),
            "baseline_payload_sha256_mismatch")
    require(bundle.get("processing_qa", {}).get("verdict") == "PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW"
            and bundle["processing_qa"].get("discovery_qa") == bundle["processing_qa"].get("processing_qa") == "PASS"
            and bundle.get("paid_budget_delta", {}).get("fast", {}).get("successful", 0) > 0
            and bundle.get("paid_successful_response_ids"), "baseline_genuine_paid_proof_missing")
    require(bundle.get("selection", {}).get("count") == 113
            and len(set(bundle["selection"]["urls"])) == 113, "baseline_full_113_selection_missing")
    require(budget_delta(bundle["baseline_execution"]) == bundle["paid_budget_delta"]
            and len(bundle["paid_successful_response_ids"]) == sum(tier["successful"] for tier in bundle["paid_budget_delta"].values())
            and len(set(bundle["paid_successful_response_ids"])) == len(bundle["paid_successful_response_ids"])
            and set(bundle["paid_successful_response_ids"]) <= set(bundle["semantic"]["actual_response_ids"]),
            "baseline_paid_response_ids_or_ledger_invalid")
    require(bundle["baseline_execution"].get("runtime_fingerprint") == bundle["runtime_fingerprint"]
            and re.fullmatch(r"[0-9a-f]{40}", str(bundle["baseline_execution"].get("code_sha", ""))),
            "baseline_original_core_implementation_proof_missing")


def verify_revalidated_baseline_lineage(bundle, context, *, root):
    lineage, stock, receipts = revalidated_paid_lineage(context, bundle["baseline_execution"], root=root)
    require(lineage == bundle["paid_model_lineage"] and stock == bundle["launch_stock"]
            and receipts == bundle["current_revalidation_receipts"],
            "immutable_original_paid_or_revalidated_execution_lineage_changed")


def verify_terminal_followthrough_baseline_lineage(bundle, context, *, root):
    proof = terminal_followthrough_provenance(context, bundle["baseline_execution"], root=root)
    require(proof == bundle["terminal_followthrough_provenance"],
            "immutable_archived_final_or_terminal_followthrough_provenance_changed")


def preflight(bundle, context, *, now=None, root=ROOT):
    """Fail before engine/model activity if the genuine baseline cannot replay."""
    validate_baseline(bundle)
    if bundle["mode"] == TERMINAL_FOLLOWTHROUGH_MODE:
        context = terminal_context(context, root=root)
    now = now or datetime.now(timezone.utc)
    require(bundle["runtime_fingerprint"] == context["runtime_fingerprint"], "runtime_implementation_or_policy_changed")
    require(bundle["selection"]["sha256"] == context["observed_files"][DEFAULT_SELECTION]
            and bundle["selection"]["urls"] == context["selection"]["urls"], "immutable_113_selection_changed")
    revalidated = bundle["mode"] == REVALIDATED_MODE
    terminal = bundle["mode"] == TERMINAL_FOLLOWTHROUGH_MODE
    if revalidated:
        verify_revalidated_baseline_lineage(bundle, context, root=root)
    if terminal:
        verify_terminal_followthrough_baseline_lineage(bundle, context, root=root)
    snapshot = terminal_snapshot(context, root=root) if terminal else revalidated_snapshot(context) if revalidated else semantic_snapshot(context)
    require(snapshot == bundle["semantic"], "runtime_state_changed_since_passing_baseline")
    partition = selected_partition(snapshot["source_queue"], bundle["selection"]["urls"], now,
                                   reviewed_holds=snapshot["reviewed_hold_bindings"])
    require(partition == bundle["selection"]["current_partition"], "selected_terminal_or_not_due_partition_changed")
    return dict(schema_version=SCHEMA, mode="before_genuine_core", verdict="PASS", read_only=True,
                baseline_sha256=bundle["payload_sha256"], selected=113, partition=partition,
                ai_calls=0, fingerprint_uses_git_sha=False)


def compare(bundle, context, *, now=None, root=ROOT):
    validate_baseline(bundle)
    if bundle["mode"] == TERMINAL_FOLLOWTHROUGH_MODE:
        context = terminal_context(context, root=root)
    now = now or datetime.now(timezone.utc)
    findings = []
    def check(condition, code, **evidence):
        if not condition:
            findings.append(dict(code=code, **evidence))
    check(bundle["runtime_fingerprint"] == context["runtime_fingerprint"], "runtime_implementation_or_policy_changed")
    check(context.get("recorded_core_runtime_fingerprint") == context["runtime_fingerprint"],
          "actual_second_core_implementation_not_bound")
    revalidated = bundle["mode"] == REVALIDATED_MODE
    terminal = bundle["mode"] == TERMINAL_FOLLOWTHROUGH_MODE
    if revalidated:
        try:
            verify_revalidated_baseline_lineage(bundle, context, root=root)
        except (OSError, KeyError, TypeError, ValueError) as error:
            findings.append(dict(code="original_paid_or_revalidated_execution_lineage_invalid", reason=str(error)))
    if terminal:
        try:
            verify_terminal_followthrough_baseline_lineage(bundle, context, root=root)
        except (OSError, KeyError, TypeError, ValueError) as error:
            findings.append(dict(code="archived_final_or_terminal_followthrough_provenance_invalid", reason=str(error)))
    try:
        execution, urls, delta, events = core_proof(context)
        check(stamp(execution["started_at"]) > stamp(bundle["baseline_execution"]["finished_at"]), "second_actual_core_not_fresh")
        check(context["observed_files"][DEFAULT_SELECTION] == bundle["selection"]["sha256"]
              and urls == bundle["selection"]["urls"], "immutable_113_selection_changed")
        check(all(value == 0 for tier in delta.values() for value in tier.values()), "new_analysis_budget_consumed", delta=delta)
        check(not events, "new_actual_model_response_events", count=len(events))
        check(execution.get("processing_attempts_increased") == 0
              and context["discovery"].get("processing_attempts") == 0, "second_core_processing_attempts_nonzero")
        recorded = execution["processing_selection"]
        partition = selected_partition(source_queue(context["queue"]), urls, now,
                                       reviewed_holds=reviewed_hold_bindings(context))
        check(not recorded.get("ready_selected_urls") and not recorded.get("skipped_in_progress_urls")
              and sorted(recorded.get("skipped_terminal_urls", [])) == partition["terminal_urls"]
              and sorted(recorded.get("skipped_not_due_urls", [])) == partition["held_not_due_urls"],
              "actual_terminal_skip_or_held_not_due_not_proven")
    except (KeyError, TypeError, ValueError) as error:
        findings.append(dict(code="genuine_second_core_proof_invalid", reason=str(error)))
        delta, partition = {}, {}
    after = terminal_snapshot(context, root=root) if terminal else revalidated_snapshot(context) if revalidated else semantic_snapshot(context)
    before = bundle["semantic"]
    for key in ("history", "feed", "referenced_proof_files", "reviewed_hold_bindings", "ledgers",
                "response_event_sha256s", "actual_response_ids"):
        check(after[key] == before[key], "changed_" + key)
    if revalidated or terminal:
        check(after["native_queue"] == before["native_queue"], "changed_native_queue")
    added = {}
    for key in ("source_queue", "source_primary"):
        missing = sorted(set(before[key]) - set(after[key]))
        changed = sorted(url for url in set(before[key]) & set(after[key]) if before[key][url] != after[key][url])
        new = sorted(set(after[key]) - set(before[key]))
        check(not missing and not changed, "changed_existing_" + key, missing=missing, changed=changed)
        check(not set(new) & set(bundle["selection"]["urls"]), "new_selected_identity_appeared")
        if key == "source_queue":
            check(all(after[key][url]["attempts"] == 0 and after[key][url]["status"] in {"pending", "archived"} for url in new),
                  "new_unselected_discovery_was_processed")
        added[key] = new
    return dict(schema_version=SCHEMA, mode="after_genuine_core", verdict="FAIL" if findings else "PASS",
                acceptance="IDEMPOTENCE_NOT_PROVEN" if findings else "GENUINE_SELECTED_CORE_IDEMPOTENCE_PROVEN",
                read_only=True, baseline_sha256=bundle["payload_sha256"], observed_files=context["observed_files"],
                runtime_fingerprint=context["runtime_fingerprint"], actual_budget_delta=delta,
                selected_partition=partition, new_unselected_discovery=added,
                history_signal_count=len(after["history"]), feed_signal_count=len(after["feed"]),
                findings=findings, method=("Actual same-runtime terminal replay after bound immutable paid and final evaluation lineage; archived QA failures preserved."
                    if terminal else "Actual selected core execution after separately bound original paid lineage and genuine repaired processing; no original paid QA relabelling."
                    if revalidated else "Actual selected core execution, paid baseline and immutable semantic identities; no mocked model or injected discovery."))


def write_result(root, path, result):
    target = path if path.is_absolute() else root / path
    relative = target.resolve().relative_to(root.resolve()) if target.resolve().is_relative_to(root.resolve()) else None
    require(relative is None or not str(relative).startswith(("data/state/", "data/history/", "data/ai_usage/", "web/data/")),
            "refusing_to_overwrite_runtime_state")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "capture-revalidated", "capture-terminal-followthrough", "preflight", "compare"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=Path(DEFAULT_BASELINE))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        context = read_context(args.root)
        baseline_path = args.baseline if args.baseline.is_absolute() else args.root / args.baseline
        if args.mode in {"capture", "capture-revalidated", "capture-terminal-followthrough"}:
            output = args.output or args.baseline
            destination = output if output.is_absolute() else args.root / output
            if destination.exists():
                result = json.loads(destination.read_bytes())
                expected_mode = (TERMINAL_FOLLOWTHROUGH_MODE if args.mode == "capture-terminal-followthrough"
                                 else REVALIDATED_MODE if args.mode == "capture-revalidated" else "genuine_processing_baseline")
                require(result.get("mode") == expected_mode, "refusing_to_replace_different_processing_baseline_mode")
                preflight(result, context, root=args.root)
                require(result["baseline_execution"] == (context["report"].get("last_core_execution") or context["report"].get("execution")),
                        "refusing_to_replace_genuine_processing_baseline")
            else:
                result = (capture_terminal_followthrough_baseline(context, root=args.root) if args.mode == "capture-terminal-followthrough"
                          else capture_revalidated_baseline(context, root=args.root) if args.mode == "capture-revalidated"
                          else capture_baseline(context))
        else:
            baseline = json.loads(baseline_path.read_bytes())
            result = (preflight(baseline, context, root=args.root) if args.mode == "preflight"
                      else compare(baseline, context, root=args.root))
            output = args.output or (Path(DEFAULT_RESULT) if args.mode == "compare" else None)
        if output is not None:
            write_result(args.root, output, result)
        print(json.dumps({key: result.get(key) for key in ("schema_version", "mode", "verdict", "acceptance", "baseline_sha256", "findings")}))
        return 0 if result.get("verdict", "PASS") == "PASS" else 1
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(json.dumps(dict(verdict="FAIL", mode=args.mode, reason=str(error), read_only=True, ai_calls=0)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
