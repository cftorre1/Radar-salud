"""Read-only directed QA of original Pulso runtime evidence.

A discovery PASS is not end-to-end acceptance. Even automated processing PASS
requires independent review of the actual published facts on the final SHA.
The frozen controls are a recall benchmark, never an inventory or publication
quota. This reader cannot change the queue, history, budget or source code.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import types
import unicodedata
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

SOURCE = "pulso_latercera"
ROOT = Path(__file__).resolve().parents[1]
FROZEN_CONTROL_SHA256 = "b9c3ce2aea38107797fc19572581f27884d15611214fd2328d458bd35e906374"
PROCESSING_COHORT_PATH = "data/audits/pulso_material_recovery_cohort_2026_10_11.json"
PROCESSING_COHORT_SHA256 = "8ed358f0cd37ecc4b554ab96cd4366048b8e6180ad1c0ee0044fc5d5f6976514"
EDITORIAL_REVIEW_PATH = "data/audits/pulso_first_paid_editorial_corrections_2026_10_11.json"
EDITORIAL_REVIEW_SHA256 = "35e1d8a806f99881b56c5358d904880ca6bf2aa7ddd21e7bdada8a4b740a78d2"
INDEPENDENT_EDITORIAL_PATH = "data/audits/pulso_first_real_all32_semantic_review_2026_10_11.json"
INDEPENDENT_EDITORIAL_SHA256 = "a6ddc143c4cedb1bdc77bb1eb07ce80f25630a36bdde9ac68d49e2e2fe44d48f"
INCREMENTAL_REVIEW_PATH = "data/audits/pulso_incremental_review_2026_10_11.json"
INCREMENTAL_REVIEW_SHA256 = "e5cee8d34839a905e391e85d6187db8bcdae09c0dde7f688cc71a9f04f093ddd"
INCREMENTAL_ADDENDUM_PATH = "data/audits/pulso_oct5_incremental_addendum_2026_10_11.json"
INCREMENTAL_ADDENDUM_SHA256 = "589ba50032521924803ef8ce94f40e3854930edcadddf7fc1223d9df81714160"
CODE_REPAIR_PINS_PATH = "config/pulso_editorial_repair_admission_2026_10_11.json"
CODE_REPAIR_PINS_SHA256 = "7f915bf1f8b4ee14d6426a41541cf3b6c319ad2e2acd384b8cc9fefa53224731"
CODE_REPAIR_VERSION = "pulso_editorial_proof_v5"
PAID_REVALIDATION_PATH = "data/audits/pulso_v5_paid_guard_revalidation_manifest_2026_10_11.json"
PAID_REVALIDATION_SHA256 = "3645971793d5803c53b3a9f0f5bcb1b8e8f91ef5638b186aeaab4073645a48ff"
PAID_REVALIDATION_PRODUCER = "981b0ff25c226d47785b77944aa53c459053aa21"
PAID_REVALIDATION_CODE = "03bf998a4bb5840c84da6473666e932fbc5cedd9"
PAID_REVALIDATION_FINGERPRINT = "4feb04bc17ac24d37bd5cbb07f12893f5e8202de61aa7133b8fb1a8aeb6a4118"
CURRENT_PAID_PATH = "data/audits/pulso_current12_paid_guard_revalidation_manifest_2026_10_11.json"
CURRENT_PAID_SHA256 = "3f27a3a4450e0fbf074fadc8da380f674c18d35ab20e896971a2b19d7c55cc1b"
CURRENT_PAID_PRODUCER = "9083056a7127656e90ff40d4fcd7aef0ac407dbc"
CURRENT_PAID_CODE = "29731f04d998659e5892c109871f54ef0c7f8eef"
CURRENT_PAID_FINGERPRINT = "73b012deb1cd6729e55527f87569825136d5f5523617029ff862640eadea366d"
CURRENT_PAID_FILES = {
    "data/state/pending_queue.json": "10b1f2e3ea5ea434be8347b06874fcec7bb3c1f3a6ab67eec803976849101202",
    "data/audits/pulso_runtime_2026_10_11.json": "eb420d6e3b74b9a2274598adc5b2ae7f2f5f7e9635e1fc34f60968c896a95bd3",
    "data/ai_usage/responses.jsonl": "d421299b6f6fbe440c166bb13ad686ba0896ccfc0cbfeda400f49932c9781037",
    "data/history/superintendencia_signals.json": "bd7e32dd341348f44cfacdb0140247c5f957c417f6bed625fdcf9762a4d0f4ca",
}
CURRENT_PAID_STAMP = "current_paid_guard_revalidation_admission"
CURRENT_PAID_RECEIPT = "current_paid_guard_revalidation_receipt"
CURRENT_PAID_ATTEMPTS = "current_paid_new_fast_attempt_receipts"
CURRENT_PAID_REVISION = "verified_current_paid_guard_revalidation_admission"
FOLLOWUP_PAID_PATH = "data/audits/pulso_followup5_paid_guard_revalidation_manifest_2026_10_11.json"
FOLLOWUP_PAID_SHA256 = "1c7389906e3855d2e622e4bc4aab91addcf1e8615e8251f03def15b447f922fa"
FOLLOWUP_PAID_PRODUCER = "66f37ca044b4cf233bc9f649b7140ff8a69855d3"
FOLLOWUP_PAID_CODE = "de51496ca0bfbe656c96551743e52024b9b6608e"
FOLLOWUP_PAID_FINGERPRINT = "7f5da999f7df70bb15ef775bba83ab2ff2697f1065b99d0e48b73ec8e987efed"
FOLLOWUP_PAID_FILES = {
    "data/state/pending_queue.json": "03f998df22ec3410078c0f53dec6332e139799bd8febc92c547eba617f886fe0",
    "data/audits/pulso_runtime_2026_10_11.json": "7448f3ef7e867ff49ca395f853e61b986f6b4c8c2c5207d18c08207cc6f91dec",
    "data/ai_usage/responses.jsonl": "f5d5f4ba51d3c510997e2750d97e43d3e1d4c05196b3f2cdcb8eb5b18aec6a1b",
    "data/history/superintendencia_signals.json": "45ec0b8571447a68465ddcedb92a843663616e6014d423554bb3e4408c4548f0",
}
FOLLOWUP_PAID_STAMP = "followup_paid_guard_revalidation_admission"
FOLLOWUP_PAID_RECEIPT = "followup_paid_guard_revalidation_receipt"
FOLLOWUP_PAID_ATTEMPTS = "followup_paid_new_fast_attempt_receipts"
FOLLOWUP_PAID_REVISION = "verified_followup_paid_guard_revalidation_admission"
FINAL_PAID_PATH = "data/audits/pulso_final2_paid_guard_revalidation_manifest_2026_10_11.json"
FINAL_PAID_SHA256 = "78020e40fa2ff47c59086faf58bd8413122866e25221d0a99131150cb25e0534"
FINAL_PAID_PRODUCER = "323b73ef5fb0ec39410024c21d70e6fd99b065e2"
FINAL_PAID_CODE = "c2db17141fd55cbacbcda5b53805341aa4dfa86f"
FINAL_PAID_FINGERPRINT = "c960999eea01aed6e578d0ca1354cb5f45b8720ae8832993d609d0db540b0406"
FINAL_PAID_FILES = {
    "data/state/pending_queue.json": "b5fb262284e5ce28e6b9664703f2a94996ad7abef128a7f1c679fc0a83b26481",
    "data/audits/pulso_runtime_2026_10_11.json": "c746b44864dceb465c2d72889ed48e15510fcb7286f8d0840545f584afe6793e",
    "data/ai_usage/responses.jsonl": "19bb3e6b2ae1e15c623a97eb08ae6b3f323b1c11cec6fa74aad359f3ca04cfad",
    "data/history/superintendencia_signals.json": "39e63cc84af25227fc7cf916ab42867ab8a84a085cb6fffb3b920aa2ba0ed11a",
}
FINAL_PAID_QA_PATH = "data/audits/pulso_directed_processing_qa_2026_10_11.json"
FINAL_PAID_QA_SHA256 = "3bb88f9be0976f4d62ddb965276e2d45cbbd659b4867fffba5002c373ceb0346"
FINAL_PAID_STAMP = "final_paid_guard_revalidation_admission"
FINAL_PAID_RECEIPT = "final_paid_guard_revalidation_receipt"
FINAL_PAID_REVISION = "verified_final_paid_guard_revalidation_admission"
FOLLOWUP_REVIEW_PINS = {
    "data/audits/pulso_focus_new5_editorial_corrections_2026_10_11.json": (
        "c49022c8f81c4d45d654bac2f675ffb341bd2f6e288316f544b82a99dab3c530",
        "data/audits/pulso_focus_new5_semantic_review_2026_10_11.json",
        "773fcc79b87e2a8bfc215f344a87145526f47e947e26a740c8505b7bc8188518"),
    "data/audits/pulso_plan_enlace_temporal_correction_2026_10_11.json": (
        "c9310df3284fdfffc90710a72645a9eb582db81be4f3f350b9bf099141d2c60f",
        "data/audits/pulso_plan_enlace_temporal_addendum_2026_10_11.json",
        "f65b95dbc9d768a97342f58accd5f0e1f3261d38a21d620640ddc51660209eb2"),
}
FOCUS_PRODUCER = "0713ca9a327b4c09932345aff1353c5d87662332"
EDITORIAL_REGISTRY_PATH = "data/audits/pulso_editorial_review_registry_2026_10_11.json"
WINDOWS = {"30": ("2026-09-11", "2026-10-10", 29), "90": ("2026-07-13", "2026-10-10", 79)}
REQUIRED_FEEDS = {"section:" + name for name in (
    "pulso", "nacional", "politica", "tendencias", "que-pasa", "paula", "sustentabilidad",
    "lt-board", "sociales", "servicios", "tecnologia", "la-tercera-pm", "horizontes",
)} | {"tag:" + name for name in ("salud", "isapres", "fonasa", "clinicas", "hospitales", "listas-de-espera", "banmedica")}
PRIMARY_DATE_SOURCES = {"visible_article_byline", "json_ld_datePublished", "article_published_time", "article_time"}
VIDEO_HOLD = "publisher_video_text_unavailable"
DATE_HOLD = "publisher_conflicting_publication_dates"
SPONSORED_HOLD = "publisher_sponsored_content_review_required"
SPONSORED_TEXT_HOLD = "publisher_sponsored_text_unavailable"
SHA = re.compile(r"[0-9a-f]{64}")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def object_digest(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def idempotence_signal_hashes(signals):
    """Keep native official records sharing a listing distinct and intact.

    La Tercera article identity remains URL plus date regardless of an injected
    record identifier or source-type label. Whole signal hashes preserve every
    original field; this reader neither normalizes nor removes history rows.
    """
    rows = {}
    for signal in signals:
        url = signal.get("source_url")
        identity = [url, signal.get("event_date")]
        record = signal.get("source_record_id")
        press_host = urlsplit(url or "").hostname in {"latercera.com", "www.latercera.com"}
        if (not press_host and signal.get("source_type") == "official"
                and isinstance(record, str) and record.strip()):
            identity.append(record.strip())
        key = json.dumps(identity, ensure_ascii=False)
        if key in rows:
            raise ValueError("duplicate_effective_signal_identity")
        rows[key] = object_digest(signal)
    return rows


def verify_incremental_addendum_reference(raw, root):
    """An analysis release keeps both immutable reviews and its exact original.

    This reads the applied provenance after processing, so a terminal editorial
    decision is allowed here. It never authorizes admission or exempts a pending
    important control from a decision.
    """
    metadata = raw.get("metadata", {})
    applied = metadata.get("incremental_review_addendum")
    if applied is None:
        return None
    for relative, sha in ((INCREMENTAL_REVIEW_PATH, INCREMENTAL_REVIEW_SHA256),
                          (INCREMENTAL_ADDENDUM_PATH, INCREMENTAL_ADDENDUM_SHA256)):
        if digest(local_capture_path(root, relative).read_bytes()) != sha:
            raise ValueError("incremental_addendum_immutable_review_changed")
    document = json.loads(local_capture_path(root, INCREMENTAL_ADDENDUM_PATH).read_bytes())
    article = document["article"]
    prior = metadata.get("incremental_review") or {}
    body = metadata.get("page_text")
    expected = dict(review_ref=INCREMENTAL_ADDENDUM_PATH, review_sha256=INCREMENTAL_ADDENDUM_SHA256,
        schema_version=document["schema_version"], review_id=document["review_id"], review_date=document["review_date"],
        decision=document["decision"], reason=document["reason"], previous_hold=document["prior_review"]["reason"],
        prior_review_ref=INCREMENTAL_REVIEW_PATH, prior_review_sha256=INCREMENTAL_REVIEW_SHA256,
        publication_approved=False, verified_publication_date=article["publication_date"],
        verified_html_sha256=article["html_sha256"], verified_body_sha256=article["body_sha256"],
        verified_captured_at=metadata.get("captured_at"))
    if (not isinstance(applied, dict) or applied != expected
            or document["decision"] != "release_hold_for_editorial_analysis"
            or document["editorial_policy"]["publication_approved"] is not False
            or document["editorial_policy"]["media_materiality_threshold"] != 72
            or document["editorial_policy"]["threshold_changed"] is not False
            or raw.get("url") != article["source_url"] or raw.get("event_date") != article["publication_date"]
            or metadata.get("canonical_url") != article["source_url"]
            or metadata.get("publication_date") != article["publication_date"]
            or metadata.get("publication_timestamp") != article["publication_timestamp"]
            or any(metadata.get(field) is not True for field in
                   ("article_verified", "primary_identity_verified", "publication_date_verified", "article_body_complete"))
            or metadata.get("html_sha256") != article["html_sha256"]
            or not isinstance(body, str) or len(body) != article["body_characters"]
            or digest(body.encode()) != article["body_sha256"]
            or metadata.get("article_body_sha256") != article["body_sha256"]
            or not stamp(metadata.get("captured_at"))
            or prior.get("review_ref") != INCREMENTAL_REVIEW_PATH or prior.get("review_sha256") != INCREMENTAL_REVIEW_SHA256
            or prior.get("decision") != "keep_hold" or prior.get("reason") != document["prior_review"]["reason"]
            or prior.get("publication_approved") is not False
            or prior.get("verified_publication_date") != article["publication_date"]
            or prior.get("verified_body_sha256") != article["body_sha256"]
            or prior.get("verified_html_sha256") != article["html_sha256"]
            or not all(quote in body for quote in document["new_incremental_observations"])):
        raise ValueError("incremental_addendum_applied_original_or_provenance_mismatch")
    return dict(review_ref=INCREMENTAL_ADDENDUM_PATH, review_sha256=INCREMENTAL_ADDENDUM_SHA256,
                analysis_release_only=True, publication_approved=False)


def verify_code_repair_reference(raw, root, *, successful_response_ids=None, require_new_assessment=False):
    """Read one bound analysis admission and its immutable old paid response.

    The historical v4 answer remains v4. A completed repair needs a distinct,
    telemetry-backed v5 answer for the same full primary request; the permission
    itself supplies neither an editorial decision nor publication approval.
    """
    metadata = raw.get("metadata", {})
    applied = metadata.get("editorial_code_repair_admission")
    revisions = [row for row in metadata.get("evidence_revisions", [])
                 if row.get("reason") == "verified_editorial_code_repair_analysis_admission"]
    if applied is None and not revisions:
        return None
    encoded = local_capture_path(root, CODE_REPAIR_PINS_PATH).read_bytes()
    if digest(encoded) != CODE_REPAIR_PINS_SHA256:
        raise ValueError("code_repair_immutable_pins_changed")
    document = json.loads(encoded)
    pins = {row["url"]: row for row in document["pins"]}
    if (document.get("repair_version") != CODE_REPAIR_VERSION
            or document.get("cohort_sha256") != PROCESSING_COHORT_SHA256
            or document.get("producer_run_id") != 38149773071 or len(pins) != 69
            or len(document["pins"]) != 69):
        raise ValueError("code_repair_immutable_cohort_invalid")
    pin = pins.get(raw.get("url"))
    if pin is None:
        raise ValueError("code_repair_original_not_pinned")
    previous_id = pin["model_response"]["response_id"]
    admission_id = digest((CODE_REPAIR_VERSION + "\n" + CODE_REPAIR_PINS_SHA256 + "\n"
                           + pin["url"] + "\n" + pin["previous_reason"] + "\n" + previous_id).encode())
    request_sha = pin["model_response"]["request_input_sha256"]
    expected = dict(repair_version=CODE_REPAIR_VERSION, admission_id=admission_id,
        pins_sha256=CODE_REPAIR_PINS_SHA256, cohort_sha256=PROCESSING_COHORT_SHA256,
        producer_run_id=38149773071, previous_response_id=previous_id,
        previous_model_output_sha256=pin["previous_model_output_sha256"], previous_reason=pin["previous_reason"],
        url=pin["url"], publication_date=pin["publication_date"], article_body_sha256=pin["article_body_sha256"],
        html_sha256=pin["html_sha256"], request_input_sha256=request_sha,
        new_assessment_required=True, old_response_reuse=False, publication_approved=False,
        other_editorial_and_budget_gates_still_apply=True)
    if not isinstance(applied, dict) or applied != expected or len(revisions) != 1:
        raise ValueError("code_repair_admission_or_unique_revision_mismatch")
    revision = revisions[0]
    old_raw = revision.get("previous_processing_raw") or {}
    old = old_raw.get("metadata", {})
    old_ai = old.get("analysis_model_output")
    old_validation = old.get("pulso_editorial_proof_validation") or {}
    old_assessment = old.get("editorial_assessment") or {}
    old_binding = old.get("primary_item_binding") or {}
    for original in (old_raw, raw):
        primary = original.get("metadata", {})
        body = primary.get("page_text")
        if (original.get("url") != pin["url"] or original.get("title") != pin["title"]
                or original.get("event_date") != pin["publication_date"]
                or original.get("source_slug") != SOURCE or original.get("source_name") != "Pulso / La Tercera"
                or original.get("source_type") != "press_high_trust"
                or any(primary.get(field) is not True for field in (
                    "article_verified", "article_body_complete", "primary_identity_verified", "publication_date_verified"))
                or primary.get("source_quality_gate") != "passed" or primary.get("canonical_url") != pin["url"]
                or primary.get("publication_date") != pin["publication_date"]
                or primary.get("html_sha256") != pin["html_sha256"]
                or not isinstance(body, str) or len(body.strip()) < 160
                or digest(body.encode()) != pin["article_body_sha256"]
                or primary.get("article_body_sha256") != pin["article_body_sha256"]):
            raise ValueError("code_repair_current_or_archived_primary_mismatch")
        request = "Fuente: Pulso / La Tercera\nTítulo: " + original["title"] + "\nContenido:\n" + body
        if digest(request.encode()) != request_sha:
            raise ValueError("code_repair_full_request_changed")
    if (revision.get("code_repair_admission") != expected
            or revision.get("status_preserved") not in {"pending", "retry"}
            or type(revision.get("attempts_preserved")) is not int or revision["attempts_preserved"] < 1
            or revision.get("fingerprint_preserved") != metadata.get("queue_identity_fingerprint")
            or "previous_retry_at" not in revision
            or revision["previous_retry_at"] is not None and not stamp(revision["previous_retry_at"])
            or not isinstance(old_ai, dict) or object_digest(old_ai) != pin["previous_model_output_sha256"]
            or old_ai.get("_pulso_analysis_meta") != pin["model_response"]
            or pin["model_response"].get("schema_version") != "pulso_editorial_proof_v4"
            or old_validation.get("version") != "pulso_editorial_proof_v4"
            or old_validation.get("decision") != "deferred" or old_validation.get("reason") != pin["previous_reason"]
            or old_validation.get("model_output_sha256") != pin["previous_model_output_sha256"]
            or old_validation.get("model_response") != pin["model_response"]
            or old_validation.get("request_input_sha256") != request_sha
            or old_validation.get("analysis_text_sha256") != pin["article_body_sha256"]
            or old_assessment.get("decision") != "pending" or old_assessment.get("reason") != pin["previous_reason"]
            or old_assessment.get("threshold") != 72 or old_assessment.get("proof_version") != "pulso_editorial_proof_v4"
            or old.get("analysis_input_complete") is not True
            or old.get("analysis_input_format") != "full_primary_article_body"
            or old.get("analysis_request_input_sha256") != request_sha
            or old.get("analysis_input_body_sha256") != pin["article_body_sha256"]
            or old_binding.get("verified") is not True
            or old_binding.get("raw_url") != pin["url"] or old_binding.get("primary_canonical_url") != pin["url"]
            or old_binding.get("raw_event_date") != pin["publication_date"]
            or old_binding.get("primary_publication_date") != pin["publication_date"]):
        raise ValueError("code_repair_archived_paid_response_or_bookkeeping_changed")
    current_id = None
    if require_new_assessment:
        current = metadata.get("analysis_model_output") or {}
        model = current.get("_pulso_analysis_meta") or {}
        validation = metadata.get("pulso_editorial_proof_validation") or {}
        binding = metadata.get("primary_item_binding") or {}
        current_id = model.get("response_id")
        if (model.get("schema_version") != CODE_REPAIR_VERSION or current_id == previous_id
                or not isinstance(current_id, str) or not current_id.strip()
                or successful_response_ids is None or current_id not in successful_response_ids
                or model.get("analysis_text_sha256") != pin["article_body_sha256"]
                or model.get("request_input_sha256") != request_sha
                or model.get("source_name") != "Pulso / La Tercera"
                or not isinstance(model.get("model"), str) or not model["model"].strip()
                or not SHA.fullmatch(str(model.get("raw_model_output_sha256", "")))
                or validation.get("version") != CODE_REPAIR_VERSION
                or validation.get("model_response") != model
                or validation.get("model_output_sha256") != object_digest(current)
                or validation.get("analysis_text_sha256") != pin["article_body_sha256"]
                or validation.get("request_input_sha256") != request_sha
                or metadata.get("analysis_input_complete") is not True
                or metadata.get("analysis_input_format") != "full_primary_article_body"
                or metadata.get("analysis_input_body_sha256") != pin["article_body_sha256"]
                or metadata.get("analysis_request_input_sha256") != request_sha
                or binding.get("verified") is not True
                or binding.get("raw_url") != pin["url"] or binding.get("primary_canonical_url") != pin["url"]
                or binding.get("raw_event_date") != pin["publication_date"]
                or binding.get("primary_publication_date") != pin["publication_date"]):
            raise ValueError("code_repair_new_genuine_v5_assessment_missing_or_unbound")
        # A paid answer can be fully bound yet remain editorially deferred.
        # Keep that blocker explicit without misreporting its retained response
        # as missing. Primary/request/telemetry failures always take precedence.
        if validation.get("decision") == "deferred":
            raise ValueError("code_repair_new_genuine_v5_validation_deferred")
        if validation.get("decision") not in {"ready", "rejected"}:
            raise ValueError("code_repair_new_genuine_v5_validation_invalid")
    return dict(pins_ref=CODE_REPAIR_PINS_PATH, pins_sha256=CODE_REPAIR_PINS_SHA256,
                admission_id=admission_id, previous_response_id=previous_id,
                current_response_id=current_id, analysis_release_only=True, publication_approved=False)


def paid_revalidation_proof_files(root):
    """Pin both semantic readers before the first genuine recovery attempt."""
    target = local_capture_path(root, PAID_REVALIDATION_PATH)
    if not target.exists():
        return {}
    payload = target.read_bytes()
    if digest(payload) != PAID_REVALIDATION_SHA256:
        raise ValueError("paid_revalidation_manifest_changed")
    document = json.loads(payload)
    references = document.get("semantic_references") or []
    if len(references) != 2:
        raise ValueError("paid_revalidation_two_semantic_readers_required")
    values = {PAID_REVALIDATION_PATH: PAID_REVALIDATION_SHA256}
    for reference in references:
        path = reference.get("path")
        if (not isinstance(path, str) or not re.fullmatch(r"data/audits/pulso_[A-Za-z0-9_]+\.json", path)
                or digest(local_capture_path(root, path).read_bytes()) != reference.get("sha256")):
            raise ValueError("paid_revalidation_separate_semantic_reader_changed")
        values[path] = reference["sha256"]
    if len(values) != 3:
        raise ValueError("paid_revalidation_separate_semantic_reader_required")
    return values


def paid_revalidation_origin(root):
    """Read both independent full-source reviews and the immutable paid producer.

    The recovery routes authorize analysis only. They cannot change a model
    answer, invent a Response event, or turn the original failed run into PASS.
    """
    root = Path(root)
    payload = local_capture_path(root, PAID_REVALIDATION_PATH).read_bytes()
    if digest(payload) != PAID_REVALIDATION_SHA256:
        raise ValueError("paid_revalidation_manifest_changed")
    document = json.loads(payload)
    if (document.get("schema_version") != "pulso_v5_paid_guard_revalidation_manifest_v1"
            or document.get("producer_state_commit") != PAID_REVALIDATION_PRODUCER
            or document.get("producer_core_checkout") != PAID_REVALIDATION_CODE
            or document.get("producer_runtime_fingerprint_sha256") != PAID_REVALIDATION_FINGERPRINT
            or document.get("publication_approved") is not False or document.get("editorial_gate") != 72):
        raise ValueError("paid_revalidation_original_producer_invalid")
    paths = dict(history="data/history/superintendencia_signals.json", queue="data/state/pending_queue.json",
        runtime_report="data/audits/pulso_runtime_2026_10_11.json", telemetry="data/ai_usage/responses.jsonl")
    references = document.get("inputs") or {}
    if set(references) != set(paths) or any(ref.get("commit") != PAID_REVALIDATION_PRODUCER for ref in references.values()):
        raise ValueError("paid_revalidation_four_original_inputs_required")
    original = {key: archived_editorial_input(root, references[key], path) for key, path in paths.items()}
    execution = original["runtime_report"].get("last_core_execution") or original["runtime_report"]["execution"]
    fingerprint = execution.get("runtime_fingerprint") or {}
    start, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    delta, error = budget_delta(execution)
    events = [event for event in original["telemetry"] if start and end and stamp(event.get("at"))
              and start <= stamp(event["at"]) <= end]
    ids = [event.get("response_id") for event in events]
    if (execution.get("mode") != "real_core_processing" or execution.get("engine_called") is not True
            or execution.get("engine_completed") is not True or execution.get("ai_guardrails_modified") is not False
            or execution.get("code_sha") != PAID_REVALIDATION_CODE
            or fingerprint.get("sha256") != PAID_REVALIDATION_FINGERPRINT
            or object_digest(fingerprint.get("files")) != PAID_REVALIDATION_FINGERPRINT
            or not start or not end or start > end or error
            or delta.get("fast") != dict(attempted=69, successful=69, failed=0)
            or delta.get("deep") != dict(attempted=0, successful=0, failed=0)
            or len(events) != 69 or len(set(ids)) != 69 or any(not value for value in ids)
            or any(event.get("kind") != "fast" or event.get("success") is not True for event in events)):
        raise ValueError("paid_revalidation_69_genuine_original_responses_unverified")
    rows = document.get("rows") or []
    originals = {key: item for key, item in original["queue"].items() if item.get("source") == SOURCE
        and item.get("status") == "retry" and item.get("raw", {}).get("metadata", {}).get("analysis_model_output", {}).get(
            "_pulso_analysis_meta", {}).get("response_id") in ids}
    if (len(rows) != 49 or len(originals) != 49 or len({row.get("url") for row in rows}) != 49
            or {row.get("queue_fingerprint") for row in rows} != set(originals)):
        raise ValueError("paid_revalidation_all49_originals_required")
    semantic = document.get("semantic_references") or []
    if len(semantic) != 2:
        raise ValueError("paid_revalidation_two_semantic_readers_required")
    covered, proof_files = set(), {PAID_REVALIDATION_PATH: PAID_REVALIDATION_SHA256}
    for reference in semantic:
        path = reference.get("path")
        if (not isinstance(path, str) or not re.fullmatch(r"data/audits/pulso_[A-Za-z0-9_]+\.json", path)
                or digest(local_capture_path(root, path).read_bytes()) != reference.get("sha256")):
            raise ValueError("paid_revalidation_separate_semantic_reader_changed")
        reader = json.loads(local_capture_path(root, path).read_bytes())
        read_rows = reader.get("rows") or []
        urls = {row.get("url") for row in read_rows}
        if (reader.get("producer_commit") != PAID_REVALIDATION_PRODUCER
                or len(read_rows) != reference.get("scope_count") or len(urls) != len(read_rows)
                or urls & covered or reader.get("publication_approved", reader.get("summary", {}).get("publication_approved")) is not False):
            raise ValueError("paid_revalidation_semantic_partition_invalid")
        covered |= urls
        proof_files[path] = reference["sha256"]
    if covered != {row["url"] for row in rows}:
        raise ValueError("paid_revalidation_full_source_reading_incomplete")
    counts = {route: sum(row.get("runtime_route") == route for row in rows) for route in (
        "reuse_code_fn", "reuse_below_gate_reject", "assess_contract_or_semantic_defect")}
    if counts != dict(reuse_code_fn=18, reuse_below_gate_reject=6, assess_contract_or_semantic_defect=25):
        raise ValueError("paid_revalidation_approved_routes_changed")
    for row in rows:
        context = row.get("reassessment_context")
        if context is None:
            continue
        target = original["queue"].get(context.get("target_queue_fingerprint")) or {}
        raw = target.get("raw") or {}; metadata = raw.get("metadata") or {}
        signals = [signal for signal in original["history"]["signals"]
                   if signal.get("source_url") == context.get("target_url")]
        if (row["runtime_route"] != "assess_contract_or_semantic_defect"
                or context.get("producer_state_commit") != PAID_REVALIDATION_PRODUCER
                or target.get("status") != "published" or len(signals) != 1
                or object_digest(target) != context.get("target_queue_entry_sha256")
                or object_digest(raw) != context.get("target_raw_sha256")
                or raw.get("url") != context.get("target_url")
                or raw.get("event_date") != context.get("target_publication_date")
                or metadata.get("page_text") != context.get("target_full_primary_body")
                or metadata.get("article_body_sha256") != context.get("target_body_sha256")
                or metadata.get("html_sha256") != context.get("target_html_sha256")
                or signals[0] != context.get("target_full_original_signal")
                or object_digest(signals[0]) != context.get("target_full_original_signal_sha256")
                or context.get("publication_approved") is not False or context.get("rejection_approved") is not False
                or not all(quote in row["original_full_primary_body"] for quote in context.get("source_repetition_quotes", []))
                or not all(quote in metadata["page_text"] for quote in context.get("target_repetition_quotes", []))):
            raise ValueError("paid_revalidation_incremental_context_not_actual_published_original")
    return dict(document=document, originals=originals, rows={row["url"]: row for row in rows},
                execution=execution, telemetry=original["telemetry"], successful_response_ids=set(ids), proof_files=proof_files)


def has_paid_revalidation_claim(metadata):
    """A missing stamp cannot hide a surviving receipt or producer archive."""
    return ("paid_guard_revalidation_admission" in metadata or "paid_guard_revalidation_receipt" in metadata
            or "paid_guard_new_fast_attempt_receipts" in metadata
            or any(isinstance(revision, dict) and revision.get("reason") == "verified_paid_guard_revalidation_admission"
                   for revision in metadata.get("evidence_revisions", [])))


def execution_bound_paid_guard_bytes(root, execution, *, archived=False):
    path = "src/radar_salud/pulso_editorial_proof.py"
    if archived:
        code = execution.get("code_sha")
        if not isinstance(code, str) or not re.fullmatch(r"[0-9a-f]{40}", code):
            raise ValueError("paid_revalidation_archived_execution_code_missing")
        result = subprocess.run(["git", "show", code + ":" + path], cwd=root, capture_output=True, check=False)
        if result.returncode:
            raise ValueError("paid_revalidation_archived_guard_bytes_unavailable")
        payload = result.stdout
    else:
        payload = local_capture_path(root, path).read_bytes()
    if execution.get("runtime_fingerprint", {}).get("files", {}).get(path) != digest(payload):
        raise ValueError("paid_revalidation_guard_not_bound_to_actual_execution")
    return payload


def replay_paid_guard_validation(current, body, root, execution, admission, *, archived=False):
    """Replay the pure validator from the exact execution-bound file bytes.

    Admission/application/queue helpers are never invoked. This establishes the
    recorded validator result, while the separate full-body readers establish
    its semantic limits. Executing fresh bytes also avoids an older module left
    cached by a test or process after a validated source checkpoint changed.
    """
    path = local_capture_path(root, "src/radar_salud/pulso_editorial_proof.py")
    payload = execution_bound_paid_guard_bytes(root, execution, archived=archived)
    guard = types.ModuleType("radar_salud._qa_replayed_paid_guard")
    guard.__package__ = "radar_salud"
    guard.__file__ = str(path)
    exec(compile(payload, str(path), "exec"), guard.__dict__)
    expected = guard.validate_pulso_editorial_proof(current, body)
    expected.update(primary_article_body_sha256=admission["body_sha256"],
                    request_input_sha256=admission["request_input_sha256"],
                    model_response=current.get("_pulso_analysis_meta"))
    if not guard.model_binding_matches(current, source_name="Pulso / La Tercera",
            input_text_sha256=admission["analysis_input_sha256"], request_input_sha256=admission["request_input_sha256"]):
        expected.update(decision="deferred", reason="pulso_editorial_model_binding_mismatch")
    return expected


def verify_paid_guard_revalidation(item, root, *, execution, telemetry, origin=None, archived_execution=False):
    """Independently bind an old paid answer to its new genuine core verdict.

    The repaired guard receipt and old API response have separate provenance.
    A targeted reassessment must have a new current-window Response ID. This
    reader never imports the recovery module or its application helper.
    """
    raw = item.get("raw", {}); metadata = raw.get("metadata", {})
    applied = metadata.get("paid_guard_revalidation_admission")
    revisions = [revision for revision in metadata.get("evidence_revisions", [])
                 if revision.get("reason") == "verified_paid_guard_revalidation_admission"]
    receipt = metadata.get("paid_guard_revalidation_receipt")
    if not has_paid_revalidation_claim(metadata):
        return None
    origin = origin or paid_revalidation_origin(root)
    row = origin["rows"].get(raw.get("url"))
    if row is None:
        raise ValueError("paid_revalidation_original_not_in_all49")
    original = origin["originals"][row["queue_fingerprint"]]
    old_raw = json.loads(json.dumps(original["raw"]))
    old_raw["metadata"].pop("evidence_revisions", None)
    old = original["raw"]["metadata"]; model = old["analysis_model_output"]; response = model["_pulso_analysis_meta"]
    expected = dict(schema_version="pulso_paid_guard_revalidation_admission_v1", manifest_ref=PAID_REVALIDATION_PATH,
        manifest_sha256=PAID_REVALIDATION_SHA256, producer_state_commit=PAID_REVALIDATION_PRODUCER,
        producer_core_checkout=PAID_REVALIDATION_CODE, producer_runtime_fingerprint_sha256=PAID_REVALIDATION_FINGERPRINT,
        disposition=row["runtime_route"], publication_approved=False,
        new_model_request=row["runtime_route"] == "assess_contract_or_semantic_defect", url=row["url"],
        queue_fingerprint=row["queue_fingerprint"], publication_date=row["publication_date"], source_type=original["raw"]["source_type"],
        original_html_sha256=row["original_html_sha256"], body_sha256=row["original_body_sha256"],
        body_characters=len(old["page_text"]), request_input_sha256=response["request_input_sha256"],
        analysis_input_sha256=response["analysis_text_sha256"], original_response_id=response["response_id"],
        model_output_sha256=object_digest(model), raw_model_output_sha256=response["raw_model_output_sha256"],
        previous_validation_sha256=object_digest(old["pulso_editorial_proof_validation"]),
        previous_reason=original["reason"], original_paid_raw_sha256=object_digest(old_raw), original_attempts=original["attempts"])
    if row.get("reassessment_context") is not None:
        expected["reassessment_context_sha256"] = object_digest(row["reassessment_context"])
    expected["admission_id"] = object_digest(expected)
    if applied != expected or len(revisions) != 1:
        raise ValueError("paid_revalidation_admission_or_unique_revision_changed")
    revision = revisions[0]
    if (revision.get("paid_guard_revalidation_admission") != expected or revision.get("previous_processing_raw") != old_raw
            or revision.get("status_preserved") != original["status"]
            or revision.get("attempts_preserved") != original["attempts"]
            or revision.get("lane_preserved") != original["lane"]
            or revision.get("detected_at_preserved") != original["detected_at"]
            or revision.get("fingerprint_preserved") != row["queue_fingerprint"]
            or revision.get("previous_retry_at") != original.get("retry_at")
            or item.get("lane") != original["lane"] or item.get("detected_at") != original["detected_at"]
            or type(item.get("attempts")) is not int or item["attempts"] < original["attempts"] + 1):
        raise ValueError("paid_revalidation_archive_or_bookkeeping_changed")
    body = metadata.get("page_text")
    request = "Fuente: Pulso / La Tercera\nTítulo: " + str(raw.get("title")) + "\nContenido:\n" + str(body)
    if (raw.get("url") != row["url"] or raw.get("title") != original["raw"]["title"]
            or raw.get("event_date") != row["publication_date"] or raw.get("source_slug") != SOURCE
            or raw.get("source_name") != "Pulso / La Tercera" or raw.get("source_type") != "press_high_trust"
            or metadata.get("canonical_url") != row["url"] or metadata.get("publication_date") != row["publication_date"]
            or metadata.get("html_sha256") != row["original_html_sha256"]
            or not isinstance(body, str) or body != old["page_text"] or digest(body.encode()) != row["original_body_sha256"]
            or metadata.get("article_body_sha256") != row["original_body_sha256"]
            or digest(request.encode()) != expected["request_input_sha256"]
            or any(metadata.get(field) is not True for field in (
                "article_verified", "article_body_complete", "primary_identity_verified", "publication_date_verified", "analysis_input_complete"))
            or metadata.get("source_quality_gate") != "passed" or metadata.get("market_role") != "media"
            or metadata.get("analysis_input_format") != "full_primary_article_body"
            or metadata.get("analysis_request_input_sha256") != expected["request_input_sha256"]
            or metadata.get("analysis_input_body_sha256") != expected["analysis_input_sha256"]):
        raise ValueError("paid_revalidation_current_primary_or_complete_request_changed")
    begin, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    current = metadata.get("analysis_model_output") or {}; current_response = current.get("_pulso_analysis_meta") or {}
    validation = metadata.get("pulso_editorial_proof_validation") or {}
    if expected["new_model_request"]:
        current_events = {event.get("response_id") for event in telemetry if event.get("kind") == "fast"
            and event.get("success") is True and begin and end and stamp(event.get("at"))
            and begin <= stamp(event["at"]) <= end}
        if (receipt is not None or current_response.get("response_id") == expected["original_response_id"]
                or current_response.get("response_id") not in current_events):
            raise ValueError("paid_revalidation_contract_defect_requires_new_genuine_fast")
        attempts = metadata.get("paid_guard_new_fast_attempt_receipts") or []
        latest = attempts[-1] if attempts else {}
        guard_path = "src/radar_salud/pulso_editorial_proof.py"
        guard_sha = digest(execution_bound_paid_guard_bytes(root, execution, archived=archived_execution))
        when = stamp(latest.get("assessed_at"))
        ids = [attempt.get("new_response_id") for attempt in attempts]
        all_actual_ids = {event.get("response_id") for event in telemetry
                          if event.get("kind") == "fast" and event.get("success") is True}
        if (not attempts or len(set(ids)) != len(ids) or expected["original_response_id"] in ids
                or any(value not in all_actual_ids for value in ids)
                or any(attempt.get("admission_id") != expected["admission_id"]
                       or attempt.get("model_output_sha256") != object_digest(attempt.get("full_model_output"))
                       or attempt.get("new_validation_sha256") != object_digest(attempt.get("new_validation"))
                       or attempt.get("original_response_id") != expected["original_response_id"]
                       or attempt.get("new_model_request") is not True or attempt.get("publication_approved") is not False
                       for attempt in attempts)
                or latest.get("full_model_output") != current or latest.get("new_validation") != validation
                or latest.get("new_response_id") != current_response.get("response_id")
                or latest.get("schema_version") != "pulso_paid_guard_new_fast_attempt_receipt_v1"
                or latest.get("validator_guard_sha256") != guard_sha
                or execution.get("runtime_fingerprint", {}).get("files", {}).get(guard_path) != guard_sha
                or not when or not begin or not end or not begin <= when <= end):
            raise ValueError("paid_revalidation_new_fast_attempt_or_guard_receipt_unverified")
    else:
        if current != model or current_response.get("response_id") not in origin["successful_response_ids"]:
            raise ValueError("paid_revalidation_original_model_or_response_changed")
        when = stamp(receipt.get("revalidated_at")) if isinstance(receipt, dict) else None
        guard_path = "src/radar_salud/pulso_editorial_proof.py"
        guard_sha = digest(execution_bound_paid_guard_bytes(root, execution, archived=archived_execution))
        if (execution.get("runtime_fingerprint", {}).get("files", {}).get(guard_path) != guard_sha
                or not when or not begin or not end or not begin <= when <= end):
            raise ValueError("paid_revalidation_guard_not_bound_to_actual_execution")
        expected_receipt = dict(schema_version="pulso_paid_guard_revalidation_receipt_v1", admission=expected,
            producer_core_checkout=PAID_REVALIDATION_CODE, producer_state_commit=PAID_REVALIDATION_PRODUCER,
            producer_runtime_fingerprint_sha256=PAID_REVALIDATION_FINGERPRINT,
            original_response_id=expected["original_response_id"], original_model_output_sha256=expected["model_output_sha256"],
            original_raw_model_output_sha256=expected["raw_model_output_sha256"],
            previous_validation=old["pulso_editorial_proof_validation"], previous_validation_sha256=expected["previous_validation_sha256"],
            validator_guard_sha256=guard_sha, validator_version=CODE_REPAIR_VERSION, revalidated_at=receipt["revalidated_at"],
            new_validation=validation, new_validation_sha256=object_digest(validation), new_model_request=False,
            original_model_output_unchanged=True, publication_approved=False, quote_validation_is_semantic_approval=False)
        if receipt != expected_receipt:
            raise ValueError("paid_revalidation_guard_receipt_or_old_provenance_changed")
        if row["runtime_route"] == "reuse_below_gate_reject" and (
                type(current.get("relevance_score")) is not int or current["relevance_score"] >= 72
                or validation.get("decision") != "rejected" or validation.get("reason") != "editorial_relevance_below_threshold"):
            raise ValueError("paid_revalidation_below_gate_rejection_not_actual")
    binding = metadata.get("primary_item_binding") or {}
    if (current_response.get("schema_version") != CODE_REPAIR_VERSION
            or current_response.get("source_name") != "Pulso / La Tercera"
            or current_response.get("analysis_text_sha256") != expected["analysis_input_sha256"]
            or current_response.get("request_input_sha256") != expected["request_input_sha256"]
            or validation.get("version") != CODE_REPAIR_VERSION or validation.get("model_response") != current_response
            or validation.get("model_output_sha256") != object_digest(current)
            or validation.get("analysis_text_sha256") != expected["analysis_input_sha256"]
            or validation.get("request_input_sha256") != expected["request_input_sha256"]
            or validation.get("proof") != current.get("pulso_editorial_proof")
            or validation.get("publication_approved") is not False or validation.get("quote_validation_is_semantic_approval") is not False
            or binding.get("verified") is not True or binding.get("raw_url") != row["url"]
            or binding.get("primary_canonical_url") != row["url"]
            or binding.get("raw_event_date") != row["publication_date"]
            or binding.get("primary_publication_date") != row["publication_date"]):
        raise ValueError("paid_revalidation_final_answer_or_primary_binding_missing")
    if validation != replay_paid_guard_validation(current, body, root, execution, expected, archived=archived_execution):
        raise ValueError("paid_revalidation_recorded_verdict_not_actual_guard_result")
    if validation.get("decision") == "deferred":
        raise ValueError("paid_revalidation_actual_validation_still_deferred")
    if validation.get("decision") not in {"ready", "rejected"}:
        raise ValueError("paid_revalidation_actual_validation_invalid")
    return dict(manifest_ref=PAID_REVALIDATION_PATH, manifest_sha256=PAID_REVALIDATION_SHA256,
        disposition=row["runtime_route"], original_response_id=expected["original_response_id"],
        current_response_id=current_response["response_id"], original_producer_preserved=True,
        old_paid_output_reused=not expected["new_model_request"], publication_approved=False)


def current_paid_proof_files(root):
    """Bind two current-answer readings; a historical 69 review is insufficient."""
    path = local_capture_path(root, CURRENT_PAID_PATH)
    if not path.exists():
        return {}
    if digest(path.read_bytes()) != CURRENT_PAID_SHA256:
        raise ValueError("current_paid_manifest_changed")
    document = json.loads(path.read_bytes())
    references = document.get("semantic_references") or []
    if len(references) != 2 or len({ref.get("path") for ref in references}) != 2:
        raise ValueError("current_paid_two_independent_current_readers_required")
    files = {CURRENT_PAID_PATH: CURRENT_PAID_SHA256}
    for reference in references:
        target = reference.get("path")
        if (not isinstance(target, str) or not re.fullmatch(r"data/audits/pulso_[A-Za-z0-9_]+\.json", target)
                or digest(local_capture_path(root, target).read_bytes()) != reference.get("sha256")):
            raise ValueError("current_paid_current_semantic_reader_changed")
        files[target] = reference["sha256"]
    return files


def has_current_paid_claim(metadata):
    return (any(key in metadata for key in (CURRENT_PAID_STAMP, CURRENT_PAID_RECEIPT, CURRENT_PAID_ATTEMPTS))
            or any(isinstance(row, dict) and row.get("reason") == CURRENT_PAID_REVISION
                   for row in metadata.get("evidence_revisions", [])))


def requires_current_paid_authority(item, origin):
    """A processed member of the frozen12 cannot erase its newer authority."""
    metadata = item.get("raw", {}).get("metadata", {})
    if has_current_paid_claim(metadata):
        return True
    row = (origin or {}).get("rows", {}).get(item.get("raw", {}).get("url"))
    if row is None:
        return False
    original = origin["originals"][row["queue_fingerprint"]]
    old = original["raw"]["metadata"]
    return (item.get("attempts") != original.get("attempts")
            or item.get("status") not in {"pending", "retry"}
            or any(metadata.get(field) != old.get(field) for field in (
                "analysis_model_output", "pulso_editorial_proof_validation", "paid_guard_new_fast_attempt_receipts")))


def current_paid_pin(key, entry):
    raw, meta = entry["raw"], entry["raw"]["metadata"]
    model = meta["analysis_model_output"]; response = model["_pulso_analysis_meta"]
    archived = json.loads(json.dumps(raw)); archived["metadata"].pop("evidence_revisions", None)
    return dict(url=raw["url"], queue_fingerprint=key, publication_date=raw["event_date"],
        title=raw["title"], source_name=raw["source_name"], source_type=raw["source_type"],
        original_attempts=entry["attempts"], original_html_sha256=meta["html_sha256"],
        body_sha256=meta["article_body_sha256"], body_characters=len(meta["page_text"]),
        request_input_sha256=response["request_input_sha256"], analysis_input_sha256=response["analysis_text_sha256"],
        original_response_id=response["response_id"], model_output_sha256=object_digest(model),
        raw_model_output_sha256=response["raw_model_output_sha256"],
        previous_validation_sha256=object_digest(meta["pulso_editorial_proof_validation"]),
        previous_reason=entry["reason"], original_paid_raw_sha256=object_digest(archived))


def current_paid_origin(root, *, previous_origin=None):
    """Read 908 bytes and its failed verdict without turning that run into PASS."""
    files = current_paid_proof_files(root)
    if not files:
        raise ValueError("current_paid_frozen_manifest_unavailable")
    document = json.loads(local_capture_path(root, CURRENT_PAID_PATH).read_bytes())
    if (document.get("schema_version") != "pulso_current_paid_guard_revalidation_manifest_v1"
            or document.get("source_id") != SOURCE or document.get("producer_state_commit") != CURRENT_PAID_PRODUCER
            or document.get("producer_core_checkout") != CURRENT_PAID_CODE
            or document.get("producer_runtime_fingerprint_sha256") != CURRENT_PAID_FINGERPRINT
            or document.get("producer_files") != CURRENT_PAID_FILES
            or document.get("gate_threshold") != 72 or document.get("publication_approved") is not False):
        raise ValueError("current_paid_frozen_original_producer_changed")
    original = {path: archived_editorial_input(root, dict(commit=CURRENT_PAID_PRODUCER, path=path,
                    file_sha256=sha), path) for path, sha in CURRENT_PAID_FILES.items()}
    execution = original["data/audits/pulso_runtime_2026_10_11.json"]["last_core_execution"]
    telemetry = original["data/ai_usage/responses.jsonl"]
    start, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    delta, error = budget_delta(execution)
    events = [event for event in telemetry if start and end and stamp(event.get("at"))
              and start <= stamp(event["at"]) <= end]
    ids = {event.get("response_id") for event in events}
    fingerprint = execution.get("runtime_fingerprint") or {}
    if (execution.get("code_sha") != CURRENT_PAID_CODE or fingerprint.get("sha256") != CURRENT_PAID_FINGERPRINT
            or object_digest(fingerprint.get("files")) != CURRENT_PAID_FINGERPRINT
            or execution.get("mode") != "real_core_processing" or execution.get("engine_called") is not True
            or execution.get("engine_completed") is not True or execution.get("ai_guardrails_modified") is not False
            or execution.get("processing_selection", {}).get("sha256") != PROCESSING_COHORT_SHA256
            or not start or not end or start > end or error
            or delta.get("fast") != dict(attempted=25, successful=25, failed=0)
            or delta.get("deep") != dict(attempted=0, successful=0, failed=0)
            or len(events) != 25 or len(ids) != 25 or None in ids
            or any(event.get("kind") != "fast" or event.get("success") is not True for event in events)):
        raise ValueError("current_paid_original25_actual_responses_or_ledger_unverified")
    queue = original["data/state/pending_queue.json"]
    held = {key: item for key, item in queue.items() if item.get("source") == SOURCE and item.get("status") == "retry"
            and item.get("raw", {}).get("metadata", {}).get("analysis_model_output", {}).get(
                "_pulso_analysis_meta", {}).get("response_id") in ids}
    rows = document.get("rows") or []
    if (len(rows) != 12 or len(held) != 12 or len({row.get("url") for row in rows}) != 12
            or {row.get("queue_fingerprint") for row in rows} != set(held)
            or {route: sum(row.get("runtime_route") == route for row in rows) for route in (
                "reuse_code_fn", "assess_contract_or_semantic_defect")} != dict(reuse_code_fn=2, assess_contract_or_semantic_defect=10)):
        raise ValueError("current_paid_exact_original12_partition_changed")
    for reference in document["semantic_references"]:
        reader = json.loads(local_capture_path(root, reference["path"]).read_bytes())
        read_rows = reader.get("rows") or []
        if (reader.get("producer_commit") != CURRENT_PAID_PRODUCER or reader.get("publication_approved") is not False
                or len(read_rows) != 12 or {row.get("url") for row in read_rows} != {row["url"] for row in rows}
                or any(row.get("full_original_body_read") is not True for row in read_rows)):
            raise ValueError("current_paid_complete_current_body_model_reading_required")
        for reading in read_rows:
            item = next(entry for entry in held.values() if entry["raw"]["url"] == reading["url"])
            metadata = item["raw"]["metadata"]
            model = reading.get("original_full_model_output", reading.get("actual_full_model_output"))
            if (reading.get("original_full_primary_body") != metadata["page_text"]
                    or model != metadata["analysis_model_output"]
                    or reading.get("publication_date") != item["raw"]["event_date"]
                    or reading.get("original_html_sha256") != metadata["html_sha256"]
                    or reading.get("original_body_sha256") != metadata["article_body_sha256"]):
                raise ValueError("current_paid_semantic_reader_not_exact_current_primary_model")
    previous_origin = previous_origin or paid_revalidation_origin(root)
    previous_ids = {event.get("response_id") for event in telemetry if event.get("success") is True and event.get("kind") == "fast"}
    for row in rows:
        entry = held[row["queue_fingerprint"]]; raw, meta = entry["raw"], entry["raw"]["metadata"]
        pin = current_paid_pin(row["queue_fingerprint"], entry)
        if (any(row.get(key) != value for key, value in pin.items())
                or row.get("original_full_primary_body") != meta["page_text"]
                or row.get("original_full_model_output") != meta["analysis_model_output"]
                or row.get("actual_pulso_validation") != meta["pulso_editorial_proof_validation"]
                or row.get("actual_queue_entry_sha256") != object_digest(entry)
                or row.get("original_raw_sha256") != object_digest(raw) or row.get("original_metadata_sha256") != object_digest(meta)
                or type(entry.get("attempts")) is not int or entry["attempts"] != 3
                or row.get("semantic_references") != document["semantic_references"]
                or row.get("publication_approved") is not False or row.get("runtime_route_is_publication_approval") is not False
                or row.get("editorial_gate") != 72 or meta["pulso_editorial_proof_validation"].get("decision") != "deferred"
                or entry.get("reason") != meta["pulso_editorial_proof_validation"].get("reason")
                or meta.get("editorial_assessment", {}).get("decision") != "pending"
                or meta["editorial_assessment"].get("reason") != entry["reason"]):
            raise ValueError("current_paid_full_original_primary_model_verdict_pin_changed")
        # Both pre-existing admissions remain historical facts. Their original
        # deferred result is accepted only as the premise for this exact repair.
        try:
            verify_code_repair_reference(raw, root, successful_response_ids=previous_ids, require_new_assessment=True)
        except ValueError as error:
            if str(error) != "code_repair_new_genuine_v5_validation_deferred":
                raise
        try:
            verify_paid_guard_revalidation(entry, root, execution=execution, telemetry=telemetry,
                origin=previous_origin, archived_execution=True)
        except ValueError as error:
            if str(error) != "paid_revalidation_actual_validation_still_deferred":
                raise
    return dict(document=document, originals=held, queue=queue, rows={row["url"]: row for row in rows}, execution=execution,
                telemetry=telemetry, history=original["data/history/superintendencia_signals.json"]["signals"],
                successful_response_ids=ids, proof_files=files)


def verify_current_paid_revalidation(item, root, *, execution, telemetry, origin=None, archived_execution=False):
    """Bind the new verdict to its actual paid908 answer or a new FAST call."""
    raw, meta = item.get("raw", {}), item.get("raw", {}).get("metadata", {})
    if origin is None and local_capture_path(root, CURRENT_PAID_PATH).exists():
        origin = current_paid_origin(root)
    if not has_current_paid_claim(meta):
        if requires_current_paid_authority(item, origin):
            raise ValueError("current_paid_required_authority_missing")
        return None
    origin = origin or current_paid_origin(root)
    row = origin["rows"].get(raw.get("url"))
    if row is None:
        raise ValueError("current_paid_original_not_in_exact12")
    original = origin["originals"][row["queue_fingerprint"]]; old = original["raw"]["metadata"]
    pin = current_paid_pin(row["queue_fingerprint"], original)
    expected = dict(schema_version="pulso_current_paid_guard_revalidation_admission_v1", manifest_ref=CURRENT_PAID_PATH,
        manifest_sha256=CURRENT_PAID_SHA256, producer_state_commit=CURRENT_PAID_PRODUCER,
        producer_core_checkout=CURRENT_PAID_CODE, producer_runtime_fingerprint_sha256=CURRENT_PAID_FINGERPRINT,
        disposition=row["runtime_route"], new_model_request=row["runtime_route"] == "assess_contract_or_semantic_defect",
        publication_approved=False, **{field: value for field, value in pin.items() if field not in {"title", "source_name"}})
    if row.get("reassessment_context") is not None:
        expected["reassessment_context_sha256"] = object_digest(row["reassessment_context"])
    expected["admission_id"] = object_digest(expected)
    revisions = [revision for revision in meta.get("evidence_revisions", []) if revision.get("reason") == CURRENT_PAID_REVISION]
    archive = json.loads(json.dumps(original["raw"])); archive["metadata"].pop("evidence_revisions", None)
    if (meta.get(CURRENT_PAID_STAMP) != expected or len(revisions) != 1
            or revisions[0].get(CURRENT_PAID_STAMP) != expected or revisions[0].get("previous_processing_raw") != archive
            or any(revisions[0].get(field) != value for field, value in dict(
                previous_retry_at=original.get("retry_at"), status_preserved=original["status"],
                attempts_preserved=original["attempts"], lane_preserved=original["lane"],
                detected_at_preserved=original["detected_at"], fingerprint_preserved=row["queue_fingerprint"]).items())
            or item.get("lane") != original["lane"] or item.get("detected_at") != original["detected_at"]
            or type(item.get("attempts")) is not int or item["attempts"] < original["attempts"] + 1
            or meta.get("paid_guard_revalidation_admission") != old.get("paid_guard_revalidation_admission")
            or meta.get("editorial_code_repair_admission") != old.get("editorial_code_repair_admission")
            or any(revision not in meta.get("evidence_revisions", []) for revision in old.get("evidence_revisions", []))
            or meta.get("paid_guard_new_fast_attempt_receipts", [])[:len(old["paid_guard_new_fast_attempt_receipts"])] != old["paid_guard_new_fast_attempt_receipts"]):
        raise ValueError("current_paid_admission_archive_or_historical_chain_changed")
    body = meta.get("page_text")
    request = "Fuente: Pulso / La Tercera\nTítulo: " + str(raw.get("title")) + "\nContenido:\n" + str(body)
    if (raw.get("url") != pin["url"] or raw.get("title") != pin["title"] or raw.get("event_date") != pin["publication_date"]
            or raw.get("source_slug") != SOURCE or raw.get("source_name") != pin["source_name"] or raw.get("source_type") != "press_high_trust"
            or meta.get("canonical_url") != pin["url"] or meta.get("publication_date") != pin["publication_date"]
            or meta.get("html_sha256") != pin["original_html_sha256"] or body != old["page_text"]
            or digest(str(body).encode()) != pin["body_sha256"] or meta.get("article_body_sha256") != pin["body_sha256"]
            or meta.get("analysis_base_article_body_sha256") != pin["body_sha256"]
            or digest(request.encode()) != pin["request_input_sha256"] or meta.get("analysis_input_body_sha256") != pin["analysis_input_sha256"]
            or meta.get("analysis_request_input_sha256") != pin["request_input_sha256"]
            or meta.get("source_quality_gate") != "passed" or meta.get("market_role") != "media"
            or meta.get("analysis_input_format") != "full_primary_article_body"
            or any(meta.get(field) is not True for field in (
                "article_verified", "article_body_complete", "primary_identity_verified", "publication_date_verified", "analysis_input_complete"))):
        raise ValueError("current_paid_current_primary_or_full_request_changed")
    model = meta.get("analysis_model_output") or {}; response = model.get("_pulso_analysis_meta") or {}
    validation = meta.get("pulso_editorial_proof_validation") or {}
    begin, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    guard_sha = digest(execution_bound_paid_guard_bytes(root, execution, archived=archived_execution))
    if expected["new_model_request"]:
        receipts = meta.get(CURRENT_PAID_ATTEMPTS) or []; latest = receipts[-1] if receipts else {}
        ids = [attempt.get("new_response_id") for attempt in receipts]
        all_ids = {event.get("response_id") for event in telemetry if event.get("kind") == "fast" and event.get("success") is True}
        current_ids = {event.get("response_id") for event in telemetry if event.get("kind") == "fast" and event.get("success") is True
                       and begin and end and stamp(event.get("at")) and begin <= stamp(event["at"]) <= end}
        when = stamp(latest.get("assessed_at"))
        legacy = meta.get("paid_guard_new_fast_attempt_receipts") or []
        if (CURRENT_PAID_RECEIPT in meta or not receipts or len(set(ids)) != len(ids)
                or pin["original_response_id"] in ids or any(value not in all_ids for value in ids)
                or response.get("response_id") not in current_ids
                or any(attempt.get("admission_id") != expected["admission_id"]
                    or attempt.get("original_response_id") != pin["original_response_id"]
                    or attempt.get("model_output_sha256") != object_digest(attempt.get("full_model_output"))
                    or attempt.get("new_validation_sha256") != object_digest(attempt.get("new_validation"))
                    or attempt.get("schema_version") != "pulso_current_paid_new_fast_attempt_receipt_v1"
                    or attempt.get("full_model_output", {}).get("_pulso_analysis_meta", {}).get("response_id") != attempt.get("new_response_id")
                    or attempt.get("new_validation", {}).get("model_response") != attempt.get("full_model_output", {}).get("_pulso_analysis_meta")
                    or attempt.get("publication_approved") is not False or attempt.get("new_model_request") is not True
                    for attempt in receipts)
                or latest.get("full_model_output") != model or latest.get("new_validation") != validation
                or latest.get("validator_guard_sha256") != guard_sha or latest.get("validator_version") != CODE_REPAIR_VERSION
                or latest.get("new_response_id") != response.get("response_id")
                or not when or not begin or not end or not begin <= when <= end
                or len(legacy) < len(old["paid_guard_new_fast_attempt_receipts"]) + len(receipts)
                or any(not any(previous.get("full_model_output") == attempt["full_model_output"]
                    and previous.get("new_validation") == attempt["new_validation"]
                    and previous.get("new_response_id") == attempt["new_response_id"] for previous in legacy) for attempt in receipts)):
            raise ValueError("current_paid_contract_defect_requires_new_actual_bound_fast")
    else:
        receipt = meta.get(CURRENT_PAID_RECEIPT)
        when = stamp(receipt.get("revalidated_at")) if isinstance(receipt, dict) else None
        expected_receipt = dict(schema_version="pulso_current_paid_guard_revalidation_receipt_v1", admission=expected,
            producer_state_commit=CURRENT_PAID_PRODUCER, producer_core_checkout=CURRENT_PAID_CODE,
            producer_runtime_fingerprint_sha256=CURRENT_PAID_FINGERPRINT, original_response_id=pin["original_response_id"],
            original_model_output_sha256=pin["model_output_sha256"], original_raw_model_output_sha256=pin["raw_model_output_sha256"],
            previous_validation=old["pulso_editorial_proof_validation"], previous_validation_sha256=pin["previous_validation_sha256"],
            new_validation=validation, new_validation_sha256=object_digest(validation), validator_guard_sha256=guard_sha,
            validator_version=CODE_REPAIR_VERSION, revalidated_at=(receipt or {}).get("revalidated_at"), new_model_request=False,
            original_model_output_unchanged=True, publication_approved=False, quote_validation_is_semantic_approval=False)
        if (model != old["analysis_model_output"] or response.get("response_id") not in origin["successful_response_ids"]
                or CURRENT_PAID_ATTEMPTS in meta or receipt != expected_receipt
                or not when or not begin or not end or not begin <= when <= end):
            raise ValueError("current_paid_unchanged908_answer_or_current_guard_receipt_changed")
    binding = meta.get("primary_item_binding") or {}
    if (response.get("schema_version") != CODE_REPAIR_VERSION or response.get("source_name") != "Pulso / La Tercera"
            or response.get("analysis_text_sha256") != pin["analysis_input_sha256"]
            or response.get("request_input_sha256") != pin["request_input_sha256"]
            or not SHA.fullmatch(str(response.get("raw_model_output_sha256", "")))
            or binding.get("verified") is not True or binding.get("raw_url") != pin["url"]
            or binding.get("primary_canonical_url") != pin["url"] or binding.get("raw_event_date") != pin["publication_date"]
            or binding.get("primary_publication_date") != pin["publication_date"]):
        raise ValueError("current_paid_final_primary_or_actual_model_binding_missing")
    if validation != replay_paid_guard_validation(model, body, root, execution, pin, archived=archived_execution):
        raise ValueError("current_paid_recorded_verdict_not_execution_bound_guard_result")
    if validation.get("decision") == "deferred":
        raise ValueError("current_paid_actual_bound_validation_still_deferred")
    if validation.get("decision") not in {"ready", "rejected"}:
        raise ValueError("current_paid_actual_validation_invalid")
    return dict(manifest_ref=CURRENT_PAID_PATH, manifest_sha256=CURRENT_PAID_SHA256, disposition=row["runtime_route"],
        original_producer=CURRENT_PAID_PRODUCER, original_response_id=pin["original_response_id"],
        current_response_id=response["response_id"], old_paid_output_reused=not expected["new_model_request"],
        prior981_and908_paid_provenances_preserved=True, publication_approved=False)


def verify_followup_reassessment_context(context, entry, original):
    raw, metadata = entry["raw"], entry["raw"]["metadata"]
    if context is None:
        return
    if (context.get("source_url") != raw["url"] or context.get("source_publication_date") != raw["event_date"]
            or context.get("source_body_sha256") != metadata["article_body_sha256"]
            or context.get("publication_approved") is not False or context.get("rejection_approved") is not False
            or not isinstance(context.get("context_text"), str) or not context["context_text"].strip()
            or not context.get("source_verbatim_quotes")
            or any(not isinstance(quote, str) or " ".join(quote.split()).casefold() not in
                " ".join(metadata["page_text"].split()).casefold() for quote in context["source_verbatim_quotes"])):
        raise ValueError("followup_paid_exact_primary_context_changed")
    for target in context.get("published_comparison_targets", []):
        old = original["data/state/pending_queue.json"][target["target_queue_fingerprint"]]
        url, day = old["raw"]["url"], old["raw"]["event_date"]
        signals = [signal for signal in original["data/history/superintendencia_signals.json"]["signals"]
                   if signal.get("source_url") == url and signal.get("event_date") == day]
        if (len(signals) != 1 or old.get("status") != "published"
                or old["raw"]["metadata"].get("editorial_assessment", {}).get("decision") != "published"
                or old["raw"]["metadata"]["editorial_assessment"].get("threshold") != 72
                or target.get("target_queue_entry_sha256") != object_digest(old)
                or target.get("target_full_primary_raw") != old["raw"]
                or target.get("target_full_signal") != signals[0]
                or target.get("target_signal_sha256") != object_digest(signals[0])
                or signals[0].get("evidence_maturity") != "media_reported"
                or signals[0].get("source_type") != "press_high_trust"
                or signals[0].get("feed_visibility") is False
                or type(signals[0].get("editorial_relevance")) is not int or signals[0]["editorial_relevance"] < 72):
            raise ValueError("followup_paid_original_published_comparison_changed")


def followup_paid_proof_files(root):
    """Bind two current-answer readings; a historical 69 review is insufficient."""
    path = local_capture_path(root, FOLLOWUP_PAID_PATH)
    if not path.exists():
        return {}
    if digest(path.read_bytes()) != FOLLOWUP_PAID_SHA256:
        raise ValueError("followup_paid_manifest_changed")
    document = json.loads(path.read_bytes())
    references = document.get("semantic_references") or []
    if len(references) != 2 or len({ref.get("path") for ref in references}) != 2:
        raise ValueError("followup_paid_two_independent_current_readers_required")
    files = {FOLLOWUP_PAID_PATH: FOLLOWUP_PAID_SHA256}
    for reference in references:
        target = reference.get("path")
        if (not isinstance(target, str) or not re.fullmatch(r"data/audits/pulso_[A-Za-z0-9_]+\.json", target)
                or digest(local_capture_path(root, target).read_bytes()) != reference.get("sha256")):
            raise ValueError("followup_paid_current_semantic_reader_changed")
        files[target] = reference["sha256"]
    return files


def has_followup_paid_claim(metadata):
    return (any(key in metadata for key in (FOLLOWUP_PAID_STAMP, FOLLOWUP_PAID_RECEIPT, FOLLOWUP_PAID_ATTEMPTS))
            or any(isinstance(row, dict) and row.get("reason") == FOLLOWUP_PAID_REVISION
                   for row in metadata.get("evidence_revisions", [])))


def requires_followup_paid_authority(item, origin):
    """A processed member of the frozen5 cannot erase its newer authority."""
    metadata = item.get("raw", {}).get("metadata", {})
    if has_followup_paid_claim(metadata):
        return True
    row = (origin or {}).get("rows", {}).get(item.get("raw", {}).get("url"))
    if row is None:
        return False
    original = origin["originals"][row["queue_fingerprint"]]
    old = original["raw"]["metadata"]
    return (item.get("attempts") != original.get("attempts")
            or item.get("status") not in {"pending", "retry"}
            or any(metadata.get(field) != old.get(field) for field in (
                "analysis_model_output", "pulso_editorial_proof_validation", "paid_guard_new_fast_attempt_receipts")))


def followup_paid_pin(key, entry):
    raw, meta = entry["raw"], entry["raw"]["metadata"]
    model = meta["analysis_model_output"]; response = model["_pulso_analysis_meta"]
    archived = json.loads(json.dumps(raw)); archived["metadata"].pop("evidence_revisions", None)
    return dict(url=raw["url"], queue_fingerprint=key, publication_date=raw["event_date"],
        title=raw["title"], source_name=raw["source_name"], source_type=raw["source_type"],
        original_attempts=entry["attempts"], original_html_sha256=meta["html_sha256"],
        body_sha256=meta["article_body_sha256"], body_characters=len(meta["page_text"]),
        request_input_sha256=response["request_input_sha256"], analysis_input_sha256=response["analysis_text_sha256"],
        original_response_id=response["response_id"], model_output_sha256=object_digest(model),
        raw_model_output_sha256=response["raw_model_output_sha256"],
        previous_validation_sha256=object_digest(meta["pulso_editorial_proof_validation"]),
        previous_reason=entry["reason"], original_paid_raw_sha256=object_digest(archived))


def followup_paid_origin(root, *, current_origin=None):
    """Read 66f bytes and its failed verdict without turning that run into PASS."""
    files = followup_paid_proof_files(root)
    if not files:
        raise ValueError("followup_paid_frozen_manifest_unavailable")
    document = json.loads(local_capture_path(root, FOLLOWUP_PAID_PATH).read_bytes())
    if (document.get("schema_version") != "pulso_followup_paid_guard_revalidation_manifest_v1"
            or document.get("source_id") != SOURCE or document.get("producer_state_commit") != FOLLOWUP_PAID_PRODUCER
            or document.get("producer_core_checkout") != FOLLOWUP_PAID_CODE
            or document.get("producer_runtime_fingerprint_sha256") != FOLLOWUP_PAID_FINGERPRINT
            or document.get("producer_files") != FOLLOWUP_PAID_FILES
            or document.get("gate_threshold") != 72 or document.get("publication_approved") is not False):
        raise ValueError("followup_paid_frozen_original_producer_changed")
    original = {path: archived_editorial_input(root, dict(commit=FOLLOWUP_PAID_PRODUCER, path=path,
                    file_sha256=sha), path) for path, sha in FOLLOWUP_PAID_FILES.items()}
    execution = original["data/audits/pulso_runtime_2026_10_11.json"]["last_core_execution"]
    telemetry = original["data/ai_usage/responses.jsonl"]
    start, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    delta, error = budget_delta(execution)
    events = [event for event in telemetry if start and end and stamp(event.get("at"))
              and start <= stamp(event["at"]) <= end]
    ids = {event.get("response_id") for event in events}
    fingerprint = execution.get("runtime_fingerprint") or {}
    if (execution.get("code_sha") != FOLLOWUP_PAID_CODE or fingerprint.get("sha256") != FOLLOWUP_PAID_FINGERPRINT
            or object_digest(fingerprint.get("files")) != FOLLOWUP_PAID_FINGERPRINT
            or execution.get("mode") != "real_core_processing" or execution.get("engine_called") is not True
            or execution.get("engine_completed") is not True or execution.get("ai_guardrails_modified") is not False
            or execution.get("processing_selection", {}).get("sha256") != PROCESSING_COHORT_SHA256
            or not start or not end or start > end or error
            or delta.get("fast") != dict(attempted=10, successful=10, failed=0)
            or delta.get("deep") != dict(attempted=0, successful=0, failed=0)
            or len(events) != 10 or len(ids) != 10 or None in ids
            or any(event.get("kind") != "fast" or event.get("success") is not True for event in events)):
        raise ValueError("followup_paid_original10_actual_responses_or_ledger_unverified")
    queue = original["data/state/pending_queue.json"]
    held = {key: item for key, item in queue.items() if item.get("source") == SOURCE and item.get("status") == "retry"
            and item.get("raw", {}).get("metadata", {}).get("analysis_model_output", {}).get(
                "_pulso_analysis_meta", {}).get("response_id") in ids}
    rows = document.get("rows") or []
    if (len(rows) != 5 or len(held) != 5 or len({row.get("url") for row in rows}) != 5
            or {row.get("queue_fingerprint") for row in rows} != set(held)
            or {route: sum(row.get("runtime_route") == route for row in rows) for route in (
                "reuse_code_fn", "assess_contract_or_semantic_defect")} != dict(reuse_code_fn=3, assess_contract_or_semantic_defect=2)):
        raise ValueError("followup_paid_exact_original5_partition_changed")
    for reference in document["semantic_references"]:
        reader = json.loads(local_capture_path(root, reference["path"]).read_bytes())
        read_rows = reader.get("rows") or []
        if (reader.get("producer_commit") != FOLLOWUP_PAID_PRODUCER
                or len(read_rows) != 5 or {entry.get("url") for entry in read_rows} != {entry["url"] for entry in rows}):
            raise ValueError("followup_paid_complete_current_body_model_reading_required")
        # The second full reader also retains its exact paid fixture. Its
        # declared byte hash links those bodies/outputs to the frozen review.
        fixture = reader.get("actual_fixture")
        if fixture:
            payload = local_capture_path(root, fixture.get("path")).read_bytes()
            if digest(payload) != fixture.get("sha256"):
                raise ValueError("followup_paid_semantic_full_fixture_changed")
            full = json.loads(gzip.decompress(payload))
            if full.get("producer_commit") != FOLLOWUP_PAID_PRODUCER:
                raise ValueError("followup_paid_semantic_fixture_wrong_producer")
            full_rows = {entry["url"]: entry for entry in full.get("rows", [])}
            if set(full_rows) != {entry["url"] for entry in rows}:
                raise ValueError("followup_paid_semantic_fixture_missing_body")
        else:
            full_rows = {}
        for reading in read_rows:
            entry = next(value for value in held.values() if value["raw"]["url"] == reading["url"])
            metadata = entry["raw"]["metadata"]
            exact = full_rows.get(reading["url"], reading)
            model = exact.get("original_full_model_output", exact.get("actual_full_model_output"))
            reviewed_row = next(value for value in rows if value["url"] == reading["url"])
            if (reading.get("publication_approved") is not False
                    or reading.get("full_original_body_read", reading.get("full_primary_body_read")) is not True
                    or reading.get("full_original_model_read", reading.get("full_actual_model_read")) is not True
                    or reading.get("runtime_route") != reviewed_row["runtime_route"]
                    or exact.get("original_full_primary_body") != metadata["page_text"]
                    or model != metadata["analysis_model_output"]
                    or reading.get("publication_date") != entry["raw"]["event_date"]
                    or reading.get("original_html_sha256", reading.get("html_sha256")) != metadata["html_sha256"]
                    or reading.get("original_body_sha256", reading.get("body_sha256")) != metadata["article_body_sha256"]
                    or reading.get("original_response_id", reading.get("response_id")) != model["_pulso_analysis_meta"]["response_id"]):
                raise ValueError("followup_paid_semantic_reader_not_exact_current_primary_model")
    current_origin = current_origin or current_paid_origin(root)
    previous_ids = {event.get("response_id") for event in telemetry if event.get("success") is True and event.get("kind") == "fast"}
    for row in rows:
        entry = held[row["queue_fingerprint"]]; raw, meta = entry["raw"], entry["raw"]["metadata"]
        pin = followup_paid_pin(row["queue_fingerprint"], entry)
        if (any(row.get(key) != value for key, value in pin.items())
                or row.get("original_full_primary_body") != meta["page_text"]
                or row.get("original_full_model_output") != meta["analysis_model_output"]
                or row.get("actual_pulso_validation") != meta["pulso_editorial_proof_validation"]
                or row.get("actual_queue_entry_sha256") != object_digest(entry)
                or row.get("original_raw_sha256") != object_digest(raw) or row.get("original_metadata_sha256") != object_digest(meta)
                or type(entry.get("attempts")) is not int or entry["attempts"] != 4
                or row.get("semantic_references") != document["semantic_references"]
                or row.get("publication_approved") is not False or row.get("runtime_route_is_publication_approval") is not False
                or row.get("editorial_gate") != 72 or meta["pulso_editorial_proof_validation"].get("decision") != "deferred"
                or entry.get("reason") != meta["pulso_editorial_proof_validation"].get("reason")
                or meta.get("editorial_assessment", {}).get("decision") != "pending"
                or meta["editorial_assessment"].get("reason") != entry["reason"]):
            raise ValueError("followup_paid_full_original_primary_model_verdict_pin_changed")
        # Both pre-existing admissions remain historical facts. Their original
        # deferred result is accepted only as the premise for this exact repair.
        try:
            verify_code_repair_reference(raw, root, successful_response_ids=previous_ids, require_new_assessment=True)
        except ValueError as error:
            if str(error) != "code_repair_new_genuine_v5_validation_deferred":
                raise
        try:
            verify_current_paid_revalidation(entry, root, execution=execution, telemetry=telemetry,
                origin=current_origin, archived_execution=True)
        except ValueError as error:
            if str(error) != "current_paid_actual_bound_validation_still_deferred":
                raise
        if meta["pulso_editorial_proof_validation"] != replay_paid_guard_validation(
                meta["analysis_model_output"], meta["page_text"], root, execution, pin, archived=True):
            raise ValueError("followup_paid_original_verdict_not_actual_archived_guard")
        verify_followup_reassessment_context(row.get("reassessment_context"), entry, original)
    return dict(document=document, originals=held, queue=queue, rows={row["url"]: row for row in rows}, execution=execution,
                telemetry=telemetry, history=original["data/history/superintendencia_signals.json"]["signals"],
                successful_response_ids=ids, proof_files=files)


def verify_followup_paid_revalidation(item, root, *, execution, telemetry, origin=None, archived_execution=False):
    """Bind the new verdict to its actual paid66f answer or a new FAST call."""
    raw, meta = item.get("raw", {}), item.get("raw", {}).get("metadata", {})
    if origin is None and local_capture_path(root, FOLLOWUP_PAID_PATH).exists():
        origin = followup_paid_origin(root)
    if not has_followup_paid_claim(meta):
        if requires_followup_paid_authority(item, origin):
            raise ValueError("followup_paid_required_authority_missing")
        return None
    origin = origin or followup_paid_origin(root)
    row = origin["rows"].get(raw.get("url"))
    if row is None:
        raise ValueError("followup_paid_original_not_in_exact5")
    original = origin["originals"][row["queue_fingerprint"]]; old = original["raw"]["metadata"]
    pin = followup_paid_pin(row["queue_fingerprint"], original)
    expected = dict(schema_version="pulso_followup_paid_guard_revalidation_admission_v1", manifest_ref=FOLLOWUP_PAID_PATH,
        manifest_sha256=FOLLOWUP_PAID_SHA256, producer_state_commit=FOLLOWUP_PAID_PRODUCER,
        producer_core_checkout=FOLLOWUP_PAID_CODE, producer_runtime_fingerprint_sha256=FOLLOWUP_PAID_FINGERPRINT,
        disposition=row["runtime_route"], new_model_request=row["runtime_route"] == "assess_contract_or_semantic_defect",
        publication_approved=False, **{field: value for field, value in pin.items() if field not in {"title", "source_name"}})
    if row.get("reassessment_context") is not None:
        expected["reassessment_context_sha256"] = object_digest(row["reassessment_context"])
    expected["admission_id"] = object_digest(expected)
    revisions = [revision for revision in meta.get("evidence_revisions", []) if revision.get("reason") == FOLLOWUP_PAID_REVISION]
    archive = json.loads(json.dumps(original["raw"])); archive["metadata"].pop("evidence_revisions", None)
    if (meta.get(FOLLOWUP_PAID_STAMP) != expected or len(revisions) != 1
            or revisions[0].get(FOLLOWUP_PAID_STAMP) != expected or revisions[0].get("previous_processing_raw") != archive
            or any(revisions[0].get(field) != value for field, value in dict(
                previous_retry_at=original.get("retry_at"), status_preserved=original["status"],
                attempts_preserved=original["attempts"], lane_preserved=original["lane"],
                detected_at_preserved=original["detected_at"], fingerprint_preserved=row["queue_fingerprint"]).items())
            or item.get("lane") != original["lane"] or item.get("detected_at") != original["detected_at"]
            or type(item.get("attempts")) is not int or item["attempts"] < original["attempts"] + 1
            or meta.get("current_paid_guard_revalidation_admission") != old.get("current_paid_guard_revalidation_admission")
            or meta.get("paid_guard_revalidation_admission") != old.get("paid_guard_revalidation_admission")
            or meta.get("editorial_code_repair_admission") != old.get("editorial_code_repair_admission")
            or any(revision not in meta.get("evidence_revisions", []) for revision in old.get("evidence_revisions", []))
            or meta.get("paid_guard_new_fast_attempt_receipts", [])[:len(old["paid_guard_new_fast_attempt_receipts"])] != old["paid_guard_new_fast_attempt_receipts"]
            or meta.get(CURRENT_PAID_ATTEMPTS, [])[:len(old[CURRENT_PAID_ATTEMPTS])] != old[CURRENT_PAID_ATTEMPTS]):
        raise ValueError("followup_paid_admission_archive_or_historical_chain_changed")
    body = meta.get("page_text")
    request = "Fuente: Pulso / La Tercera\nTítulo: " + str(raw.get("title")) + "\nContenido:\n" + str(body)
    if (raw.get("url") != pin["url"] or raw.get("title") != pin["title"] or raw.get("event_date") != pin["publication_date"]
            or raw.get("source_slug") != SOURCE or raw.get("source_name") != pin["source_name"] or raw.get("source_type") != "press_high_trust"
            or meta.get("canonical_url") != pin["url"] or meta.get("publication_date") != pin["publication_date"]
            or meta.get("html_sha256") != pin["original_html_sha256"] or body != old["page_text"]
            or digest(str(body).encode()) != pin["body_sha256"] or meta.get("article_body_sha256") != pin["body_sha256"]
            or meta.get("analysis_base_article_body_sha256") != pin["body_sha256"]
            or digest(request.encode()) != pin["request_input_sha256"] or meta.get("analysis_input_body_sha256") != pin["analysis_input_sha256"]
            or meta.get("analysis_request_input_sha256") != pin["request_input_sha256"]
            or meta.get("source_quality_gate") != "passed" or meta.get("market_role") != "media"
            or meta.get("analysis_input_format") != "full_primary_article_body"
            or any(meta.get(field) is not True for field in (
                "article_verified", "article_body_complete", "primary_identity_verified", "publication_date_verified", "analysis_input_complete"))):
        raise ValueError("followup_paid_current_primary_or_full_request_changed")
    model = meta.get("analysis_model_output") or {}; response = model.get("_pulso_analysis_meta") or {}
    validation = meta.get("pulso_editorial_proof_validation") or {}
    begin, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    guard_sha = digest(execution_bound_paid_guard_bytes(root, execution, archived=archived_execution))
    if expected["new_model_request"]:
        receipts = meta.get(FOLLOWUP_PAID_ATTEMPTS) or []; latest = receipts[-1] if receipts else {}
        ids = [attempt.get("new_response_id") for attempt in receipts]
        all_ids = {event.get("response_id") for event in telemetry if event.get("kind") == "fast" and event.get("success") is True}
        current_ids = {event.get("response_id") for event in telemetry if event.get("kind") == "fast" and event.get("success") is True
                       and begin and end and stamp(event.get("at")) and begin <= stamp(event["at"]) <= end}
        when = stamp(latest.get("assessed_at"))
        legacy = meta.get("paid_guard_new_fast_attempt_receipts") or []
        previous_current = meta.get(CURRENT_PAID_ATTEMPTS) or []
        if (FOLLOWUP_PAID_RECEIPT in meta or not receipts or len(set(ids)) != len(ids)
                or pin["original_response_id"] in ids or any(value not in all_ids for value in ids)
                or response.get("response_id") not in current_ids
                or any(attempt.get("admission_id") != expected["admission_id"]
                    or attempt.get("original_response_id") != pin["original_response_id"]
                    or attempt.get("model_output_sha256") != object_digest(attempt.get("full_model_output"))
                    or attempt.get("new_validation_sha256") != object_digest(attempt.get("new_validation"))
                    or attempt.get("schema_version") != "pulso_followup_paid_new_fast_attempt_receipt_v1"
                    or attempt.get("full_model_output", {}).get("_pulso_analysis_meta", {}).get("response_id") != attempt.get("new_response_id")
                    or attempt.get("new_validation", {}).get("model_response") != attempt.get("full_model_output", {}).get("_pulso_analysis_meta")
                    or attempt.get("publication_approved") is not False or attempt.get("new_model_request") is not True
                    for attempt in receipts)
                or latest.get("full_model_output") != model or latest.get("new_validation") != validation
                or latest.get("validator_guard_sha256") != guard_sha or latest.get("validator_version") != CODE_REPAIR_VERSION
                or latest.get("new_response_id") != response.get("response_id")
                or not when or not begin or not end or not begin <= when <= end
                or len(legacy) < len(old["paid_guard_new_fast_attempt_receipts"]) + len(receipts)
                or len(previous_current) < len(old[CURRENT_PAID_ATTEMPTS]) + len(receipts)
                or any(not any(previous.get("full_model_output") == attempt["full_model_output"]
                    and previous.get("new_validation") == attempt["new_validation"]
                    and previous.get("new_response_id") == attempt["new_response_id"] for previous in previous_current) for attempt in receipts)
                or any(not any(previous.get("full_model_output") == attempt["full_model_output"]
                    and previous.get("new_validation") == attempt["new_validation"]
                    and previous.get("new_response_id") == attempt["new_response_id"] for previous in legacy) for attempt in receipts)):
            raise ValueError("followup_paid_contract_defect_requires_new_actual_bound_fast")
    else:
        receipt = meta.get(FOLLOWUP_PAID_RECEIPT)
        when = stamp(receipt.get("revalidated_at")) if isinstance(receipt, dict) else None
        expected_receipt = dict(schema_version="pulso_followup_paid_guard_revalidation_receipt_v1", admission=expected,
            producer_state_commit=FOLLOWUP_PAID_PRODUCER, producer_core_checkout=FOLLOWUP_PAID_CODE,
            producer_runtime_fingerprint_sha256=FOLLOWUP_PAID_FINGERPRINT, original_response_id=pin["original_response_id"],
            original_model_output_sha256=pin["model_output_sha256"], original_raw_model_output_sha256=pin["raw_model_output_sha256"],
            previous_validation=old["pulso_editorial_proof_validation"], previous_validation_sha256=pin["previous_validation_sha256"],
            new_validation=validation, new_validation_sha256=object_digest(validation), validator_guard_sha256=guard_sha,
            validator_version=CODE_REPAIR_VERSION, revalidated_at=(receipt or {}).get("revalidated_at"), new_model_request=False,
            original_model_output_unchanged=True, publication_approved=False, quote_validation_is_semantic_approval=False)
        if (model != old["analysis_model_output"] or response.get("response_id") not in origin["successful_response_ids"]
                or FOLLOWUP_PAID_ATTEMPTS in meta or receipt != expected_receipt
                or meta.get(CURRENT_PAID_ATTEMPTS) != old[CURRENT_PAID_ATTEMPTS]
                or meta.get("paid_guard_new_fast_attempt_receipts") != old["paid_guard_new_fast_attempt_receipts"]
                or not when or not begin or not end or not begin <= when <= end):
            raise ValueError("followup_paid_unchanged66f_answer_or_current_guard_receipt_changed")
    binding = meta.get("primary_item_binding") or {}
    if (response.get("schema_version") != CODE_REPAIR_VERSION or response.get("source_name") != "Pulso / La Tercera"
            or response.get("analysis_text_sha256") != pin["analysis_input_sha256"]
            or response.get("request_input_sha256") != pin["request_input_sha256"]
            or not SHA.fullmatch(str(response.get("raw_model_output_sha256", "")))
            or binding.get("verified") is not True or binding.get("raw_url") != pin["url"]
            or binding.get("primary_canonical_url") != pin["url"] or binding.get("raw_event_date") != pin["publication_date"]
            or binding.get("primary_publication_date") != pin["publication_date"]):
        raise ValueError("followup_paid_final_primary_or_actual_model_binding_missing")
    if validation != replay_paid_guard_validation(model, body, root, execution, pin, archived=archived_execution):
        raise ValueError("followup_paid_recorded_verdict_not_execution_bound_guard_result")
    if validation.get("decision") == "deferred":
        raise ValueError("followup_paid_actual_bound_validation_still_deferred")
    if validation.get("decision") not in {"ready", "rejected"}:
        raise ValueError("followup_paid_actual_validation_invalid")
    return dict(manifest_ref=FOLLOWUP_PAID_PATH, manifest_sha256=FOLLOWUP_PAID_SHA256, disposition=row["runtime_route"],
        original_producer=FOLLOWUP_PAID_PRODUCER, original_response_id=pin["original_response_id"],
        current_response_id=response["response_id"], old_paid_output_reused=not expected["new_model_request"],
        prior981_and908_and66_paid_provenances_preserved=True, publication_approved=False)


def final_paid_proof_files(root):
    """Bind two current-answer readings; a historical 69 review is insufficient."""
    path = local_capture_path(root, FINAL_PAID_PATH)
    if not path.exists():
        return {}
    if digest(path.read_bytes()) != FINAL_PAID_SHA256:
        raise ValueError("final_paid_manifest_changed")
    document = json.loads(path.read_bytes())
    references = document.get("semantic_references") or []
    if len(references) != 2 or len({ref.get("path") for ref in references}) != 2:
        raise ValueError("final_paid_two_independent_current_readers_required")
    files = {FINAL_PAID_PATH: FINAL_PAID_SHA256}
    for reference in references:
        target = reference.get("path")
        if (not isinstance(target, str) or not re.fullmatch(r"data/audits/pulso_[A-Za-z0-9_]+\.json", target)
                or digest(local_capture_path(root, target).read_bytes()) != reference.get("sha256")):
            raise ValueError("final_paid_current_semantic_reader_changed")
        files[target] = reference["sha256"]
    return files


def required_runtime_fingerprint_paths(root):
    """Policies and entry points must accompany the parser/validator bytes."""
    paths = {str(path.relative_to(root)) for path in (root / "src/radar_salud").glob("*.py")}
    paths.update({"scripts/qa_pulso_recovery.py", "scripts/audit_pulso_runtime.py", "scripts/pulso_idempotence.py",
        "scripts/export_web_snapshot.py", "scripts/retain_pulso_runtime_fixtures.py",
        "scripts/apply_pulso_editorial_review.py", "scripts/pulso_recovery_command.py", "scripts/product_report.py", "pyproject.toml",
        ".github/workflows/daily-radar.yml", ".github/workflows/pulso-runtime-recovery.yml"})
    paths.update("config/" + name for name in ("sources.json", "beta_source_configs.json",
        "source_quality_gate.json", "media_early_signal_gate.json", "model_routing_v1.json", "taxonomy_v2.json",
        "editorial_rules_v2.json", "editorial_copy_overrides_v1.json", "editorial_intelligence_committee_v1.json",
        "normative_editorial_v2.json", "pulso_editorial_repair_admission_2026_10_11.json"))
    return paths


def has_final_paid_claim(metadata):
    return (any(key in metadata for key in (FINAL_PAID_STAMP, FINAL_PAID_RECEIPT))
            or any(isinstance(row, dict) and row.get("reason") == FINAL_PAID_REVISION
                   for row in metadata.get("evidence_revisions", [])))


def requires_final_paid_authority(item, origin):
    """A processed member of the frozen5 cannot erase its newer authority."""
    metadata = item.get("raw", {}).get("metadata", {})
    if has_final_paid_claim(metadata):
        return True
    row = (origin or {}).get("rows", {}).get(item.get("raw", {}).get("url"))
    if row is None:
        return False
    original = origin["originals"][row["queue_fingerprint"]]
    old = original["raw"]["metadata"]
    return (item.get("attempts") != original.get("attempts")
            or item.get("status") not in {"pending", "retry"}
            or any(metadata.get(field) != old.get(field) for field in (
                "analysis_model_output", "pulso_editorial_proof_validation", "paid_guard_new_fast_attempt_receipts")))


def final_paid_pin(key, entry):
    raw, meta = entry["raw"], entry["raw"]["metadata"]
    model = meta["analysis_model_output"]; response = model["_pulso_analysis_meta"]
    archived = json.loads(json.dumps(raw)); archived["metadata"].pop("evidence_revisions", None)
    return dict(url=raw["url"], queue_fingerprint=key, publication_date=raw["event_date"],
        title=raw["title"], source_name=raw["source_name"], source_type=raw["source_type"],
        original_attempts=entry["attempts"], original_html_sha256=meta["html_sha256"],
        body_sha256=meta["article_body_sha256"], body_characters=len(meta["page_text"]),
        request_input_sha256=response["request_input_sha256"], analysis_input_sha256=response["analysis_text_sha256"],
        original_response_id=response["response_id"], model_output_sha256=object_digest(model),
        raw_model_output_sha256=response["raw_model_output_sha256"],
        previous_validation_sha256=object_digest(meta["pulso_editorial_proof_validation"]),
        previous_reason=entry["reason"], original_paid_raw_sha256=object_digest(archived))


def final_paid_origin(root, *, followup_origin=None):
    """Read 323 bytes and its failed verdict without turning that run into PASS."""
    files = final_paid_proof_files(root)
    if not files:
        raise ValueError("final_paid_frozen_manifest_unavailable")
    document = json.loads(local_capture_path(root, FINAL_PAID_PATH).read_bytes())
    if (document.get("schema_version") != "pulso_final_paid_guard_revalidation_manifest_v1"
            or document.get("source_id") != SOURCE or document.get("producer_state_commit") != FINAL_PAID_PRODUCER
            or document.get("producer_core_checkout") != FINAL_PAID_CODE
            or document.get("producer_runtime_fingerprint_sha256") != FINAL_PAID_FINGERPRINT
            or document.get("producer_files") != FINAL_PAID_FILES):
        raise ValueError("final_paid_frozen_original_producer_changed")
    original = {path: archived_editorial_input(root, dict(commit=FINAL_PAID_PRODUCER, path=path,
                    file_sha256=sha), path) for path, sha in FINAL_PAID_FILES.items()}
    execution = original["data/audits/pulso_runtime_2026_10_11.json"]["last_core_execution"]
    telemetry = original["data/ai_usage/responses.jsonl"]
    start, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    delta, error = budget_delta(execution)
    events = [event for event in telemetry if start and end and stamp(event.get("at"))
              and start <= stamp(event["at"]) <= end]
    ids = {event.get("response_id") for event in events}
    fingerprint = execution.get("runtime_fingerprint") or {}
    if (execution.get("code_sha") != FINAL_PAID_CODE or fingerprint.get("sha256") != FINAL_PAID_FINGERPRINT
            or object_digest(fingerprint.get("files")) != FINAL_PAID_FINGERPRINT
            or execution.get("mode") != "real_core_processing" or execution.get("engine_called") is not True
            or execution.get("engine_completed") is not True or execution.get("ai_guardrails_modified") is not False
            or execution.get("processing_selection", {}).get("sha256") != PROCESSING_COHORT_SHA256
            or not start or not end or start > end or error
            or delta.get("fast") != dict(attempted=2, successful=2, failed=0)
            or delta.get("deep") != dict(attempted=0, successful=0, failed=0)
            or len(events) != 2 or len(ids) != 2 or None in ids
            or any(event.get("kind") != "fast" or event.get("success") is not True for event in events)):
        raise ValueError("final_paid_original2_actual_responses_or_ledger_unverified")
    queue = original["data/state/pending_queue.json"]
    held = {key: item for key, item in queue.items() if item.get("source") == SOURCE and item.get("status") == "retry"
            and item.get("raw", {}).get("metadata", {}).get("analysis_model_output", {}).get(
                "_pulso_analysis_meta", {}).get("response_id") in ids}
    rows = document.get("rows") or []
    if (len(rows) != 2 or len(held) != 2 or len({row.get("url") for row in rows}) != 2
            or {row.get("queue_fingerprint") for row in rows} != set(held)
            or {route: sum(row.get("runtime_route") == route for row in rows) for route in (
                "reuse_code_fn", "assess_contract_or_semantic_defect")} != dict(reuse_code_fn=2, assess_contract_or_semantic_defect=0)):
        raise ValueError("final_paid_exact_original2_partition_changed")
    for reference in document["semantic_references"]:
        reader = json.loads(local_capture_path(root, reference["path"]).read_bytes())
        read_rows = reader.get("rows") or []
        if (reader.get("producer_commit") != FINAL_PAID_PRODUCER
                or len(read_rows) != 2 or {entry.get("url") for entry in read_rows} != {entry["url"] for entry in rows}):
            raise ValueError("final_paid_complete_current_body_model_reading_required")
        # The second full reader also retains its exact paid fixture. Its
        # declared byte hash links those bodies/outputs to the frozen review.
        fixture = reader.get("actual_fixture")
        if fixture:
            payload = local_capture_path(root, fixture.get("path")).read_bytes()
            if digest(payload) != fixture.get("sha256"):
                raise ValueError("final_paid_semantic_full_fixture_changed")
            full = json.loads(gzip.decompress(payload))
            if full.get("producer_commit") != FINAL_PAID_PRODUCER:
                raise ValueError("final_paid_semantic_fixture_wrong_producer")
            full_rows = {entry["url"]: entry for entry in full.get("rows", [])}
            if set(full_rows) != {entry["url"] for entry in rows}:
                raise ValueError("final_paid_semantic_fixture_missing_body")
        else:
            full_rows = {}
        for reading in read_rows:
            entry = next(value for value in held.values() if value["raw"]["url"] == reading["url"])
            metadata = entry["raw"]["metadata"]
            exact = full_rows.get(reading["url"], reading)
            model = exact.get("original_full_model_output", exact.get("actual_full_model_output"))
            reviewed_row = next(value for value in rows if value["url"] == reading["url"])
            if (reading.get("publication_approved") is not False
                    or not (reading.get("full_original_body_read", reading.get("full_primary_body_read")) is True or isinstance(exact.get("original_full_primary_body"), str))
                    or not (reading.get("full_original_model_read", reading.get("full_actual_model_read")) is True or isinstance(model, dict))
                    or (reading.get("runtime_route", reading.get("proposed_runtime_route")) != reviewed_row["runtime_route"]
                        and not (reading.get("semantic_disposition") == "code_only_false_negative_subject_to_exact_revalidation_not_human_publication"
                                 and reviewed_row["runtime_route"] == "reuse_code_fn"))
                    or exact.get("original_full_primary_body") != metadata["page_text"]
                    or model != metadata["analysis_model_output"]
                    or reading.get("publication_date") != entry["raw"]["event_date"]
                    or reading.get("original_html_sha256", reading.get("html_sha256")) != metadata["html_sha256"]
                    or reading.get("original_body_sha256", reading.get("body_sha256")) != metadata["article_body_sha256"]
                    or reading.get("original_response_id", reading.get("response_id")) != model["_pulso_analysis_meta"]["response_id"]):
                raise ValueError("final_paid_semantic_reader_not_exact_current_primary_model")
    followup_origin = followup_origin or followup_paid_origin(root)
    previous_ids = {event.get("response_id") for event in telemetry if event.get("success") is True and event.get("kind") == "fast"}
    for row in rows:
        entry = held[row["queue_fingerprint"]]; raw, meta = entry["raw"], entry["raw"]["metadata"]
        pin = final_paid_pin(row["queue_fingerprint"], entry)
        if (any(row.get(key) != value for key, value in pin.items())
                or row.get("original_full_primary_body") != meta["page_text"]
                or row.get("original_full_model_output") != meta["analysis_model_output"]
                or row.get("actual_pulso_validation") != meta["pulso_editorial_proof_validation"]
                or row.get("actual_queue_entry_sha256") != object_digest(entry)
                or row.get("original_raw_sha256") != object_digest(raw) or row.get("original_metadata_sha256") != object_digest(meta)
                or type(entry.get("attempts")) is not int or entry["attempts"] != 5
                or row.get("publication_approved") is not False or row.get("new_model_request") is not False
                or meta.get("editorial_assessment", {}).get("threshold") != 72
                or meta["pulso_editorial_proof_validation"].get("decision") != "deferred"
                or entry.get("reason") != meta["pulso_editorial_proof_validation"].get("reason")
                or meta.get("editorial_assessment", {}).get("decision") != "pending"
                or meta["editorial_assessment"].get("reason") != entry["reason"]):
            raise ValueError("final_paid_full_original_primary_model_verdict_pin_changed")
        # Both pre-existing admissions remain historical facts. Their original
        # deferred result is accepted only as the premise for this exact repair.
        try:
            verify_code_repair_reference(raw, root, successful_response_ids=previous_ids, require_new_assessment=True)
        except ValueError as error:
            if str(error) != "code_repair_new_genuine_v5_validation_deferred":
                raise
        try:
            verify_followup_paid_revalidation(entry, root, execution=execution, telemetry=telemetry,
                origin=followup_origin, archived_execution=True)
        except ValueError as error:
            if str(error) != "followup_paid_actual_bound_validation_still_deferred":
                raise
        if meta["pulso_editorial_proof_validation"] != replay_paid_guard_validation(
                meta["analysis_model_output"], meta["page_text"], root, execution, pin, archived=True):
            raise ValueError("final_paid_original_verdict_not_actual_archived_guard")
    paid_qa = archived_editorial_input(root, dict(commit=FINAL_PAID_PRODUCER, path=FINAL_PAID_QA_PATH, file_sha256=FINAL_PAID_QA_SHA256), FINAL_PAID_QA_PATH)
    if paid_qa.get("processing_qa") != "FAIL" or paid_qa.get("discovery_qa") != "PASS":
        raise ValueError("final_paid_original_failed_qa_changed")
    return dict(document=document, originals=held, queue=queue, rows={row["url"]: row for row in rows}, execution=execution,
                telemetry=telemetry, history=original["data/history/superintendencia_signals.json"]["signals"],
                successful_response_ids=ids, proof_files=files, files=FINAL_PAID_FILES, processing_qa=paid_qa, budget_delta=delta)


def verify_final_paid_revalidation(item, root, *, execution, telemetry, origin=None, archived_execution=False):
    """Bind only a real zero-API evaluation of the unchanged paid323 answer."""
    raw, meta = item.get("raw", {}), item.get("raw", {}).get("metadata", {})
    if origin is None and local_capture_path(root, FINAL_PAID_PATH).exists():
        origin = final_paid_origin(root)
    if not has_final_paid_claim(meta):
        if requires_final_paid_authority(item, origin):
            raise ValueError("final_paid_required_authority_missing")
        return None
    origin = origin or final_paid_origin(root)
    row = origin["rows"].get(raw.get("url"))
    if row is None:
        raise ValueError("final_paid_original_not_in_exact2")
    original = origin["originals"][row["queue_fingerprint"]]; old = original["raw"]["metadata"]
    pin = final_paid_pin(row["queue_fingerprint"], original)
    expected = dict(schema_version="pulso_final_paid_guard_revalidation_admission_v1", manifest_ref=FINAL_PAID_PATH,
        manifest_sha256=FINAL_PAID_SHA256, producer_state_commit=FINAL_PAID_PRODUCER,
        producer_core_checkout=FINAL_PAID_CODE, producer_runtime_fingerprint_sha256=FINAL_PAID_FINGERPRINT,
        disposition=row["runtime_route"], new_model_request=False, validator_guard_sha256=origin["document"]["validator_guard_sha256"],
        publication_approved=False, **{field: value for field, value in pin.items() if field not in {"title", "source_name"}})
    expected["admission_id"] = object_digest(expected)
    revisions = [revision for revision in meta.get("evidence_revisions", []) if revision.get("reason") == FINAL_PAID_REVISION]
    archive = json.loads(json.dumps(original["raw"])); archive["metadata"].pop("evidence_revisions", None)
    if (meta.get(FINAL_PAID_STAMP) != expected or len(revisions) != 1
            or revisions[0].get(FINAL_PAID_STAMP) != expected or revisions[0].get("previous_processing_raw") != archive
            or any(revisions[0].get(field) != value for field, value in dict(
                previous_retry_at=original.get("retry_at"), status_preserved=original["status"],
                attempts_preserved=original["attempts"], lane_preserved=original["lane"],
                detected_at_preserved=original["detected_at"], fingerprint_preserved=row["queue_fingerprint"]).items())
            or item.get("lane") != original["lane"] or item.get("detected_at") != original["detected_at"]
            or type(item.get("attempts")) is not int or item["attempts"] < original["attempts"] + 1
            or meta.get("current_paid_guard_revalidation_admission") != old.get("current_paid_guard_revalidation_admission")
            or meta.get("paid_guard_revalidation_admission") != old.get("paid_guard_revalidation_admission")
            or meta.get("editorial_code_repair_admission") != old.get("editorial_code_repair_admission")
            or any(revision not in meta.get("evidence_revisions", []) for revision in old.get("evidence_revisions", []))
            or meta.get("paid_guard_new_fast_attempt_receipts", [])[:len(old["paid_guard_new_fast_attempt_receipts"])] != old["paid_guard_new_fast_attempt_receipts"]
            or meta.get(CURRENT_PAID_ATTEMPTS, [])[:len(old[CURRENT_PAID_ATTEMPTS])] != old[CURRENT_PAID_ATTEMPTS]):
        raise ValueError("final_paid_admission_archive_or_historical_chain_changed")
    body = meta.get("page_text")
    request = "Fuente: Pulso / La Tercera\nTítulo: " + str(raw.get("title")) + "\nContenido:\n" + str(body)
    if (raw.get("url") != pin["url"] or raw.get("title") != pin["title"] or raw.get("event_date") != pin["publication_date"]
            or raw.get("source_slug") != SOURCE or raw.get("source_name") != pin["source_name"] or raw.get("source_type") != "press_high_trust"
            or meta.get("canonical_url") != pin["url"] or meta.get("publication_date") != pin["publication_date"]
            or meta.get("html_sha256") != pin["original_html_sha256"] or body != old["page_text"]
            or digest(str(body).encode()) != pin["body_sha256"] or meta.get("article_body_sha256") != pin["body_sha256"]
            or meta.get("analysis_base_article_body_sha256") != pin["body_sha256"]
            or digest(request.encode()) != pin["request_input_sha256"] or meta.get("analysis_input_body_sha256") != pin["analysis_input_sha256"]
            or meta.get("analysis_request_input_sha256") != pin["request_input_sha256"]
            or meta.get("source_quality_gate") != "passed" or meta.get("market_role") != "media"
            or meta.get("analysis_input_format") != "full_primary_article_body"
            or any(meta.get(field) is not True for field in (
                "article_verified", "article_body_complete", "primary_identity_verified", "publication_date_verified", "analysis_input_complete"))):
        raise ValueError("final_paid_current_primary_or_full_request_changed")
    model = meta.get("analysis_model_output") or {}; response = model.get("_pulso_analysis_meta") or {}
    validation = meta.get("pulso_editorial_proof_validation") or {}
    begin, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    guard_sha = digest(execution_bound_paid_guard_bytes(root, execution, archived=archived_execution))
    if guard_sha != origin["document"]["validator_guard_sha256"]:
        raise ValueError("final_paid_guard_not_exact_authorized_execution")
    receipt = meta.get(FINAL_PAID_RECEIPT)
    when = stamp(receipt.get("revalidated_at")) if isinstance(receipt, dict) else None
    expected_receipt = dict(schema_version="pulso_final_paid_guard_revalidation_receipt_v1", admission=expected,
        producer_state_commit=FINAL_PAID_PRODUCER, producer_core_checkout=FINAL_PAID_CODE,
        producer_runtime_fingerprint_sha256=FINAL_PAID_FINGERPRINT, original_response_id=pin["original_response_id"],
        original_model_output_sha256=pin["model_output_sha256"], original_raw_model_output_sha256=pin["raw_model_output_sha256"],
        previous_validation=old["pulso_editorial_proof_validation"], previous_validation_sha256=pin["previous_validation_sha256"],
        new_validation=validation, new_validation_sha256=object_digest(validation), validator_guard_sha256=guard_sha,
        validator_version=CODE_REPAIR_VERSION, revalidated_at=(receipt or {}).get("revalidated_at"), new_model_request=False,
        original_model_output_unchanged=True, publication_approved=False, quote_validation_is_semantic_approval=False)
    if (model != old["analysis_model_output"] or response.get("response_id") not in origin["successful_response_ids"]
            or receipt != expected_receipt
            or any(meta.get(field) != old.get(field) for field in (FOLLOWUP_PAID_STAMP, FOLLOWUP_PAID_RECEIPT, FOLLOWUP_PAID_ATTEMPTS, CURRENT_PAID_STAMP, CURRENT_PAID_RECEIPT, CURRENT_PAID_ATTEMPTS, "paid_guard_revalidation_admission", "paid_guard_revalidation_receipt", "paid_guard_new_fast_attempt_receipts", "editorial_code_repair_admission"))
            or not when or not begin or not end or not begin <= when <= end):
        raise ValueError("final_paid_unchanged323_answer_or_current_guard_receipt_changed")
    binding = meta.get("primary_item_binding") or {}
    if (response.get("schema_version") != CODE_REPAIR_VERSION or response.get("source_name") != "Pulso / La Tercera"
            or response.get("analysis_text_sha256") != pin["analysis_input_sha256"]
            or response.get("request_input_sha256") != pin["request_input_sha256"]
            or not SHA.fullmatch(str(response.get("raw_model_output_sha256", "")))
            or binding.get("verified") is not True or binding.get("raw_url") != pin["url"]
            or binding.get("primary_canonical_url") != pin["url"] or binding.get("raw_event_date") != pin["publication_date"]
            or binding.get("primary_publication_date") != pin["publication_date"]):
        raise ValueError("final_paid_final_primary_or_actual_model_binding_missing")
    if validation != replay_paid_guard_validation(model, body, root, execution, pin, archived=archived_execution):
        raise ValueError("final_paid_recorded_verdict_not_execution_bound_guard_result")
    if validation.get("decision") == "deferred":
        raise ValueError("final_paid_actual_bound_validation_still_deferred")
    if validation.get("decision") not in {"ready", "rejected"}:
        raise ValueError("final_paid_actual_validation_invalid")
    return dict(manifest_ref=FINAL_PAID_PATH, manifest_sha256=FINAL_PAID_SHA256, disposition=row["runtime_route"],
        original_producer=FINAL_PAID_PRODUCER, original_response_id=pin["original_response_id"],
        current_response_id=response["response_id"], old_paid_output_reused=not expected["new_model_request"],
        prior981_and908_and66_and323_paid_provenances_preserved=True, current_guard_sha256=guard_sha, current_evaluation_code=execution.get("code_sha"), current_receipt_sha256=object_digest(receipt), publication_approved=False)


def verify_final_revalidated_execution(root, *, report, queue, history, telemetry, execution=None, origin=None,
                                      _terminal_archive=False):
    """Observe real final evaluation separately from the immutable paid window."""
    origin = origin or final_paid_origin(root)
    execution = execution or report.get("last_core_execution") or report.get("execution") or {}
    begin, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    delta, error = budget_delta(execution)
    selection = execution.get("processing_selection") or {}
    cohort = json.loads(local_capture_path(root, PROCESSING_COHORT_PATH).read_bytes())
    selected = set(selection.get("selected_urls") or [])
    ids = set(origin["successful_response_ids"])
    events = [event for event in telemetry if begin and end and stamp(event.get("at")) and begin <= stamp(event["at"]) <= end]
    fingerprint = execution.get("runtime_fingerprint") or {}
    if (execution.get("mode") != "real_core_processing" or execution.get("engine_called") is not True
            or execution.get("engine_completed") is not True or execution.get("ai_guardrails_modified") is not False
            or not begin or not end or begin > end or begin <= stamp(origin["execution"]["finished_at"])
            or error or any(value for tier in delta.values() for value in tier.values()) or events
            or execution.get("processing_attempts_increased") != 2
            or selection.get("sha256") != PROCESSING_COHORT_SHA256 or len(selected) != 113
            or selected != set(cohort["urls"]) or set(selection.get("ready_selected_urls") or []) != set(origin["rows"])
            or len(selection.get("skipped_terminal_urls") or []) != 111
            or set(selection["skipped_terminal_urls"]) != selected - set(origin["rows"])
            or selection.get("skipped_not_due_urls") or selection.get("skipped_in_progress_urls")
            or not required_runtime_fingerprint_paths(root) <= set(fingerprint.get("files") or {})
            or object_digest(fingerprint.get("files")) != fingerprint.get("sha256")
            or fingerprint.get("git_or_marker_sha_used") is not False):
        raise ValueError("final_revalidated_execution_not_real_zero_api_exact2")
    code = execution.get("code_sha")
    if not re.fullmatch(r"[0-9a-f]{40}", str(code or "")):
        raise ValueError("final_revalidated_checkout_unavailable")
    if _terminal_archive:
        path = "data/audits/pulso_runtime_2026_10_11.json"
        original = archived_editorial_input(root, dict(commit=TERMINAL_FOLLOWTHROUGH_PRODUCER,
            path=path, file_sha256=TERMINAL_FOLLOWTHROUGH_FILES[path]), path)
        if (execution != original.get("last_core_execution") or code != TERMINAL_FOLLOWTHROUGH_CODE
                or fingerprint.get("sha256") != TERMINAL_FOLLOWTHROUGH_FINGERPRINT):
            raise ValueError("final_terminal_archive_not_exact_known_execution")
    for path, expected in fingerprint["files"].items():
        archived = subprocess.run(["git", "show", code + ":" + path], cwd=root, capture_output=True)
        if (archived.returncode or digest(archived.stdout) != expected
                or not (_terminal_archive and path in TERMINAL_CONSUMER_PATHS)
                and digest(local_capture_path(root, path).read_bytes()) != expected):
            raise ValueError("final_revalidated_implementation_not_exact_recorded_bytes")
    source_entries = [(key,item) for key,item in queue.items() if item.get("source") == SOURCE]
    current = {item["raw"]["url"]: (key, item) for key,item in source_entries}
    if len(current) != len(source_entries):
        raise ValueError("final_revalidated_duplicate_source_queue_identity")
    if any(url not in current or current[url][1].get("status") not in {"published", "rejected"}
           or technical_processing_deferral(current[url][1], {}) for url in selected):
        raise ValueError("final_revalidated_selected113_not_terminal_or_grounded")
    launch = {}; launch_hashes = {}
    for name,path in (("queue", "data/state/pending_queue.json"), ("history", "data/history/superintendencia_signals.json")):
        result = subprocess.run(["git", "show", code + ":" + path], cwd=root, capture_output=True)
        if result.returncode:
            raise ValueError("final_revalidated_launch_stock_not_retained")
        launch[name] = json.loads(result.stdout); launch_hashes[path] = digest(result.stdout)
    prior = {item["raw"]["url"]: (key,item) for key,item in launch["queue"].items() if item.get("source") == SOURCE}
    preserved = {}
    for url in sorted(selected - set(origin["rows"])):
        old = prior.get(url); now = current.get(url)
        if not old or old[1].get("status") not in {"published", "rejected"} or old != now:
            raise ValueError("final_revalidated_previous111_terminal_stock_changed")
        preserved[url] = dict(queue_fingerprint=old[0], queue_entry_sha256=object_digest(old[1]))
    native_queue = {key:item for key,item in queue.items() if item.get("source") != SOURCE}
    launch_native_queue = {key:item for key,item in launch["queue"].items() if item.get("source") != SOURCE}
    original_native_queue = {key:item for key,item in origin["queue"].items() if item.get("source") != SOURCE}
    native_history = [row for row in history if not normalized_url(row.get("source_url"))]
    launch_history = launch["history"]["signals"] if isinstance(launch["history"],dict) else launch["history"]
    launch_native_history = [row for row in launch_history if not normalized_url(row.get("source_url"))]
    original_native_history = [row for row in origin["history"] if not normalized_url(row.get("source_url"))]
    if idempotence_signal_hashes([row for row in history if normalized_url(row.get("source_url")) not in origin["rows"]]) != idempotence_signal_hashes(
            [row for row in launch_history if normalized_url(row.get("source_url")) not in origin["rows"]]):
        raise ValueError("final_revalidated_previous_history_stock_changed")
    if (native_queue != launch_native_queue or native_queue != original_native_queue
            or native_history != launch_native_history or native_history != original_native_history
            or len(native_queue) != 5293 or len(native_history) != 897
            or telemetry != origin["telemetry"]):
        raise ValueError("final_revalidated_native_stock_or_original_response_ledger_changed")
    receipts = {}
    models = {}
    for url,row in sorted(origin["rows"].items()):
        key,item = current[url]
        original = origin["originals"][row["queue_fingerprint"]]
        if key != row["queue_fingerprint"] or item.get("attempts") != original["attempts"] + 1:
            raise ValueError("final_revalidated_exact2_attempt_bookkeeping_changed")
        proof = verify_final_paid_revalidation(item, root, execution=execution, telemetry=telemetry, origin=origin,
            archived_execution=_terminal_archive)
        receipts[url] = proof
        metadata = item["raw"]["metadata"]
        models[url] = dict(queue_fingerprint=key, original_response_id=row["original_response_id"],
            original_model_output_sha256=row["model_output_sha256"], original_raw_model_output_sha256=row["raw_model_output_sha256"],
            original_body_sha256=row["body_sha256"], original_html_sha256=row["original_html_sha256"],
            original_request_input_sha256=row["request_input_sha256"], publication_date=row["publication_date"],
            admission=metadata[FINAL_PAID_STAMP], receipt=metadata[FINAL_PAID_RECEIPT])
    old_events = [event for event in origin["telemetry"] if event.get("response_id") in ids]
    paid_lineage = dict(schema_version="pulso_genuine_paid_model_lineage_v1", producer_state_commit=FINAL_PAID_PRODUCER,
        producer_core_checkout=FINAL_PAID_CODE, original_execution=origin["execution"],
        original_runtime_fingerprint=origin["execution"]["runtime_fingerprint"], original_budget_delta=origin["budget_delta"],
        original_successful_response_ids=[event["response_id"] for event in old_events], original_response_events=old_events,
        original_processing_qa=origin["processing_qa"], original_observed_files=dict(FINAL_PAID_FILES, **{FINAL_PAID_QA_PATH:FINAL_PAID_QA_SHA256}),
        original_paid_qa_promoted=False, same_runtime_fingerprint_as_baseline=False, authority=origin["proof_files"], models=models)
    stock = dict(commit=code, file_sha256=launch_hashes, preserved_terminal_urls=preserved,
        native_queue_count=len(native_queue), native_queue_sha256=object_digest(native_queue),
        native_history_count=len(native_history), native_history_sha256=object_digest(native_history))
    return dict(paid_model_lineage=paid_lineage, launch_stock=stock, current_revalidation_receipts=receipts,
        evaluation_execution=execution, actual_budget_delta=delta, publication_approved=False)


TERMINAL_FOLLOWTHROUGH_PRODUCER = "123bf2550536030a077c03ad4d56572df24ab418"
TERMINAL_FOLLOWTHROUGH_CODE = "46a3683c6760f0e61031a7dc7d5961c105cacb36"
TERMINAL_FOLLOWTHROUGH_FINGERPRINT = "8f50110e88b79f0832e86957a0f14d3a461a52faf6f65fd2b1fab8299df831fa"
TERMINAL_FOLLOWTHROUGH_FILES = {
    "data/audits/pulso_runtime_2026_10_11.json": "6f0f26ac044cf50e2df2fc30be21e42b56276c6e77ca6678b6c8621b35a7d8d9",
    "data/audits/pulso_directed_processing_qa_2026_10_11.json": "719d0afbb61718808c4ccee7252cb98af337e0d6fec3c56aab2ad2a553dd4582",
    "data/state/pending_queue.json": "509da9e5c5a2da99da8b537c7a003870e5f6a1b777adff6aff5f3db106308105",
    "data/history/superintendencia_signals.json": "1400cb4a7bfd9d50283bf7927515dffa328ec07cbb1a780148f9227f3db98b26",
    "web/data/radar_today.json": "6c7bd5a3b7dda1fbb6fe032d43c4927adc1393111716852835dfd495ce1e53dc",
    "data/ai_usage/responses.jsonl": "19bb3e6b2ae1e15c623a97eb08ae6b3f323b1c11cec6fa74aad359f3ca04cfad",
    "data/ai_usage/2026-10.json": "aec8ca63b045c2d44c28ebfddcfd4474651ae5bfc27efbc1247f4171a18e9ca9",
    "data/state/discovery_run.json": "301529a60f3209f6b1d5294d6bf1123f90e8c283974528602d461f1c09120f26",
}
TERMINAL_CONSUMER_PATHS = frozenset({"scripts/qa_pulso_recovery.py", "scripts/pulso_idempotence.py",
    "scripts/pulso_recovery_command.py", ".github/workflows/pulso-runtime-recovery.yml"})
LIVE9_PRODUCER = "d48a495a5fcefb9adaca26ca30b1f12ddad7e59f"
LIVE9_CODE = "1b4817164dbd9cd091197e1c7ebd03de6fa93526"
LIVE9_FINGERPRINT = "be91910c2f322831f8279afd200963155b7bb076e31034c2592cb31290e56814"
LIVE9_PATH = "data/audits/pulso_additional_live9_recovery_cohort_2026_10_11.json"
LIVE9_SHA256 = "641eee7d713cd1c9fba2171d9e45dbaeab0688434ac371a87f56089b2f141373"
LIVE9_TRIAGE_PATH = "data/audits/pulso_additional_live9_primary_semantic_triage_2026_10_11.json"
LIVE9_TRIAGE_SHA256 = "fba017ed27f0449be06e20c9c2c4943984d7b835c47fa0a0e8b74bf7de67dfe8"
LIVE9_ORIGINALS_PATH = "tests/fixtures/pulso_live9_primary_real/manifest.json"
LIVE9_ORIGINALS_SHA256 = "908875faca85694905ca6abeae9945b1366903a3cc54f67c588cee96b133d46f"
LIVE9_FILES = {
    "data/audits/pulso_runtime_2026_10_11.json": "8ce66b878a4165bb079292eb4c2853eb029309a9341954c77007bc578cf5accb",
    "data/audits/pulso_directed_processing_qa_2026_10_11.json": "cf5ee33b0833b6ee6704c19b7a8e308a4e65c6d089e4dda4a4b4d2e662bc063a",
    "data/state/pending_queue.json": "d44cfa10569f34cf1e1f8a7746d26bd71728d069679c89b756387381123eddf8",
    "data/history/superintendencia_signals.json": "1400cb4a7bfd9d50283bf7927515dffa328ec07cbb1a780148f9227f3db98b26",
    "web/data/radar_today.json": "4801f42db2518366dd9c2555bd62a1b55d257e46cfb25f67bf089352fc5eccf0",
    "data/ai_usage/responses.jsonl": "85baafcd92e24f98d912105fc8dced023b5dd78f18d63a571e7626908d917d31",
    "data/ai_usage/2026-10.json": "4411394f3ac5fa75136f023b125ed00eac7538b0d4670e545fc34a05d921204a",
    "data/state/discovery_run.json": "6ed0352474bb398f02d13bf6550e2865f71c7e0c65c4c25062c4d1e3ee48a9c0",
}


def terminal_live9_proof_files(root):
    files = {LIVE9_PATH: LIVE9_SHA256, LIVE9_TRIAGE_PATH: LIVE9_TRIAGE_SHA256,
             LIVE9_ORIGINALS_PATH:LIVE9_ORIGINALS_SHA256}
    for path, expected in files.items():
        if digest(local_capture_path(root, path).read_bytes()) != expected:
            raise ValueError("terminal_live9_independent_selection_or_triage_changed")
    return files


def terminal_live9_original_bytes(root, raw, metadata, records):
    """Open publisher bytes, independently binding current body and byline."""
    url = raw["url"]; expected = metadata["html_sha256"]
    for record in records:
        if (record.get("status") != 200 or normalized_url(record.get("url")) != url
                or record.get("returned_text_utf8_sha256") != expected):
            continue
        payload = local_capture_path(root, record["gzip_file"]).read_bytes()
        original = gzip.decompress(payload)
        html = original.decode(record.get("charset") or "utf-8",errors="replace")
        dates = PrimaryDates(); dates.feed(html)
        _, body = dates.primary_text(url)
        if (digest(payload) != record.get("gzip_sha256") or digest(original) != record.get("sha256")
                or len(original) != record.get("bytes") or digest(html.encode()) != expected
                or dates.canonical != url or dates.days_for(url) != {raw["event_date"]}
                or body != metadata["page_text"] or digest(body.encode()) != metadata["article_body_sha256"]
                or record.get("primary_body_sha256") != metadata["article_body_sha256"]
                or record.get("capture_provenance") != "preserved_original_http_response"
                or not SHA.fullmatch(str(record.get("original_capture_manifest_sha256","")))
                or not stamp(record.get("captured_at")) or type(record.get("artifact_run_id")) is not int
                or type(record.get("artifact_id")) is not int):
            raise ValueError("terminal_live9_original_html_date_body_or_transport_proof_changed")
        return dict(original_html_sha256=expected,original_raw_sha256=record["sha256"],
            gzip_sha256=record["gzip_sha256"],capture_manifest_sha256=record["original_capture_manifest_sha256"],
            captured_at=record["captured_at"],artifact_run_id=record["artifact_run_id"],artifact_id=record["artifact_id"],
            body_sha256=metadata["article_body_sha256"],publication_date=raw["event_date"],canonical_url=url)
    raise ValueError("terminal_live9_original_html_missing_for_actual_body")


def terminal_live9_settlement(root, archived):
    """Read the actual additional paid scope without changing its failed QA.

    This scope used the ordinary Source processor. Its four real answers and
    five prefilter rejections settle the nine already discovered articles;
    neither the frozen113 cohort nor a publication quota is redefined.
    """
    proof_files = terminal_live9_proof_files(root)
    original_manifest = json.loads(local_capture_path(root,LIVE9_ORIGINALS_PATH).read_bytes())
    if (original_manifest.get("schema_version") != "pulso_live9_original_primary_recovery_v1"
            or original_manifest.get("verdict") != "PASS_ALL9_AND_UPDATED_PAID_PRIMARY_EXACT_ORIGINALS"
            or original_manifest.get("targets") != 9 or original_manifest.get("retained_originals") != 9
            or original_manifest.get("refreshed_primary_targets") != 1 or original_manifest.get("retained_refreshed_originals") != 1
            or len(original_manifest.get("requests",[])) != 10 or original_manifest.get("missing")
            or original_manifest.get("refreshed_missing")
            or original_manifest.get("current_target_proof",{}).get("target_commit") != LIVE9_PRODUCER
            or original_manifest.get("current_target_proof",{}).get("queue_sha256") != LIVE9_FILES["data/state/pending_queue.json"]):
        raise ValueError("terminal_live9_original_manifest_not_complete_exact_producer")
    data = {path: archived_editorial_input(root, dict(commit=LIVE9_PRODUCER,
                path=path, file_sha256=sha), path) for path, sha in LIVE9_FILES.items()}
    report = data["data/audits/pulso_runtime_2026_10_11.json"]
    queue = data["data/state/pending_queue.json"]
    history = data["data/history/superintendencia_signals.json"]["signals"]
    snapshot = data["web/data/radar_today.json"]
    telemetry = data["data/ai_usage/responses.jsonl"]
    month = data["data/ai_usage/2026-10.json"]
    quality = data["data/audits/pulso_directed_processing_qa_2026_10_11.json"]
    execution = report.get("last_core_execution") or report.get("execution") or {}
    cohort = json.loads(local_capture_path(root, LIVE9_PATH).read_bytes())
    frozen = json.loads(local_capture_path(root, PROCESSING_COHORT_PATH).read_bytes())
    selected = execution.get("processing_selection") or {}
    delta, error = budget_delta(execution)
    begin, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    fingerprint = execution.get("runtime_fingerprint") or {}
    if (execution.get("mode") != "real_core_processing" or execution.get("engine_called") is not True
            or execution.get("engine_completed") is not True or execution.get("ai_guardrails_modified") is not False
            or execution.get("code_sha") != LIVE9_CODE or fingerprint.get("sha256") != LIVE9_FINGERPRINT
            or object_digest(fingerprint.get("files")) != LIVE9_FINGERPRINT
            or not begin or not end or not stamp(archived["execution"]["finished_at"]) < begin <= end
            or selected.get("sha256") != LIVE9_SHA256 or selected.get("selected_urls") != cohort["urls"]
            or selected.get("ready_selected_urls") != cohort["urls"] or len(set(cohort["urls"])) != 9
            or set(cohort["urls"]) & set(frozen["urls"]) or execution.get("processing_attempts_increased") != 9
            or selected.get("skipped_terminal_urls") or selected.get("skipped_not_due_urls") or selected.get("skipped_in_progress_urls")
            or error or delta != {"fast":dict(attempted=4,successful=4,failed=0),"deep":dict(attempted=0,successful=0,failed=0)}
            or execution.get("budget_before", {}).get("month") != archived["month"]
            or execution.get("budget_after", {}).get("month") != month
            or quality.get("verdict") != "FAIL" or quality.get("processing_qa") != "FAIL"
            or len(quality.get("findings", [])) != 1477):
        raise ValueError("terminal_live9_genuine_scope_execution_or_failed_qa_changed")
    old_files = archived["execution"]["runtime_fingerprint"]["files"]
    if set(fingerprint["files"]) != set(old_files) or any(fingerprint["files"][p] != old_files[p]
            for p in old_files if p not in TERMINAL_CONSUMER_PATHS):
        raise ValueError("terminal_live9_source_or_policy_changed")
    for path, expected in fingerprint["files"].items():
        raw = subprocess.run(["git", "show", LIVE9_CODE + ":" + path], cwd=root, capture_output=True)
        if raw.returncode or digest(raw.stdout) != expected:
            raise ValueError("terminal_live9_recorded_checkout_bytes_changed")
    prefix = archived["telemetry"]
    events = [event for event in telemetry if stamp(event.get("at")) and begin <= stamp(event["at"]) <= end]
    if (telemetry[:len(prefix)] != prefix or telemetry[len(prefix):] != events
            or len(events) != 4 or any(event.get("kind") != "fast" or event.get("success") is not True for event in events)
            or any(not event.get("response_id") for event in events)
            or len({event["response_id"] for event in events}) != 4
            or {event["response_id"] for event in events} & {event.get("response_id") for event in prefix}):
        raise ValueError("terminal_live9_real_response_events_not_exact_append")
    if (history != archived["history"] or snapshot.get("signals") != archived["snapshot"].get("signals")
            or {k:v for k,v in queue.items() if v.get("source") != SOURCE}
                != {k:v for k,v in archived["queue"].items() if v.get("source") != SOURCE}):
        raise ValueError("terminal_live9_previous_history_feed_or_native_stock_changed")
    preserved = {url: (key,item) for key,item in archived["queue"].items() if item.get("source") == SOURCE
                 for url in [item["raw"]["url"]] if url in frozen["urls"]}
    if len(preserved) != 113 or any(queue.get(key) != item or item.get("status") not in {"published","rejected"}
            for key,item in preserved.values()):
        raise ValueError("terminal_live9_changed_original113_terminal_decisions")
    rows = {}; response_ids = set()
    for declared in cohort["items"]:
        url, key = declared["url"], declared["queue_fingerprint"]
        item = queue.get(key); original = archived["queue"].get(key)
        if not item or not original:
            raise ValueError("terminal_live9_original_queue_identity_missing")
        raw = item.get("raw", {}); metadata = raw.get("metadata", {}); assessment = metadata.get("editorial_assessment") or {}
        body = metadata.get("page_text"); day = raw.get("event_date"); body_sha = digest(body.encode()) if isinstance(body,str) else None
        if (raw.get("url") != url or original.get("attempts") != 0 or item.get("attempts") != 1
                or original.get("status") != "pending" or item.get("status") != "rejected"
                or assessment.get("decision") != "rejected" or not assessment.get("reason")
                or day != declared["publication_date"] or metadata.get("publication_date") != day
                or metadata.get("canonical_url") != url or len(str(body or "")) < 160
                or body_sha != metadata.get("article_body_sha256")
                or any(metadata.get(flag) is not True for flag in
                    ("article_verified","primary_identity_verified","publication_date_verified"))
                or metadata.get("article_body_complete") is False
                or not queue_timestamp_corroborates(metadata, day)
                or metadata.get("rejection_reason") != assessment["reason"]):
            raise ValueError("terminal_live9_original_primary_or_exact_rejection_unverified")
        model = metadata.get("analysis_model_output"); validation = metadata.get("pulso_editorial_proof_validation")
        response = model.get("_pulso_analysis_meta") if isinstance(model,dict) else None
        if model is not None:
            request = "Fuente: " + str(raw["source_name"]) + "\nTítulo: " + str(raw["title"]) + "\nContenido:\n" + body
            pin = dict(body_sha256=body_sha, analysis_input_sha256=body_sha, request_input_sha256=digest(request.encode()))
            if (metadata.get("analysis_input_complete") is not True or metadata.get("analysis_base_article_body_sha256") != body_sha
                    or metadata.get("analysis_input_format") != "full_primary_article_body"
                    or metadata.get("analysis_request_input_sha256") != pin["request_input_sha256"]
                    or not isinstance(response,dict) or response.get("response_id") not in {e["response_id"] for e in events}
                    or validation != replay_paid_guard_validation(model, body, root, execution, pin, archived=True)
                    or validation.get("decision") != "rejected" or assessment.get("threshold") != 72
                    or type(model.get("relevance_score")) is not int or model["relevance_score"] >= 72
                    or model["relevance_score"] != assessment.get("relevance_score")):
                raise ValueError("terminal_live9_new_paid_model_input_guard_or_gate_unverified")
            response_ids.add(response["response_id"])
        elif assessment != {"decision":"rejected", "reason":"media_materiality_prefilter"}:
            raise ValueError("terminal_live9_prefilter_not_exact_non_ai_rejection")
        html_proof = terminal_live9_original_bytes(root,raw,metadata,original_manifest["requests"])
        rows[url] = dict(queue_fingerprint=key,queue_entry_sha256=object_digest(item),
            publication_date=day,body_sha256=body_sha,html_sha256=metadata.get("html_sha256"),body_characters=len(body),
            original_body_sha256=declared["body_sha256"],original_html_sha256=declared["html_sha256"],
            primary_updated=body_sha != declared["body_sha256"] or metadata.get("html_sha256") != declared["html_sha256"],
            model_output_sha256=object_digest(model) if model is not None else None,
            model_response_id=response.get("response_id") if response else None,
            validation_sha256=object_digest(validation) if validation is not None else None,
            request_input_sha256=metadata.get("analysis_request_input_sha256"),status=item["status"],attempts=item["attempts"],
            assessment=assessment,original_html_byte_proof=html_proof,
            actual_primary_and_model_records_read=True,publication_approved=False)
    if response_ids != {event["response_id"] for event in events}:
        raise ValueError("terminal_live9_paid_response_set_not_exact_models")
    updated_prior_html = {}
    for url,row in rows.items():
        if row["primary_updated"]:
            prior_raw = archived["queue"][row["queue_fingerprint"]]["raw"]
            updated_prior_html[url] = terminal_live9_original_bytes(root,prior_raw,prior_raw["metadata"],original_manifest["requests"])
    return dict(report=report,queue=queue,history=history,snapshot=snapshot,telemetry=telemetry,month=month,
        execution=execution,processing_qa=quality,files=dict(LIVE9_FILES),rows=rows,events=events,budget_delta=delta,
        proof_files=proof_files,updated_prior_html=updated_prior_html,telemetry_prefix=dict(commit=TERMINAL_FOLLOWTHROUGH_PRODUCER,
            events=len(prefix),sha256=object_digest(prefix),settled_events=len(telemetry),settled_sha256=object_digest(telemetry)))


def terminal_followthrough_origin(root, *, final_origin=None):
    """Retain the genuine final evaluation, including its original failed QA."""
    data = {path: archived_editorial_input(root, dict(commit=TERMINAL_FOLLOWTHROUGH_PRODUCER,
                path=path, file_sha256=sha), path) for path, sha in TERMINAL_FOLLOWTHROUGH_FILES.items()}
    report = data["data/audits/pulso_runtime_2026_10_11.json"]
    queue = data["data/state/pending_queue.json"]
    history = data["data/history/superintendencia_signals.json"]["signals"]
    snapshot = data["web/data/radar_today.json"]
    telemetry = data["data/ai_usage/responses.jsonl"]
    quality = data["data/audits/pulso_directed_processing_qa_2026_10_11.json"]
    execution = report.get("last_core_execution") or report.get("execution") or {}
    if (execution.get("code_sha") != TERMINAL_FOLLOWTHROUGH_CODE
            or execution.get("runtime_fingerprint", {}).get("sha256") != TERMINAL_FOLLOWTHROUGH_FINGERPRINT
            or quality.get("verdict") != "FAIL" or quality.get("processing_qa") != "FAIL"
            or quality.get("discovery_qa") != "PASS" or len(quality.get("findings", [])) != 24):
        raise ValueError("terminal_original_evaluation_or_failed_qa_changed")
    final_origin = final_origin or final_paid_origin(root)
    evaluation = verify_final_revalidated_execution(root, report=report, queue=queue, history=history,
        telemetry=telemetry, execution=execution, origin=final_origin, _terminal_archive=True)
    reviewed, failures = verify_bound_editorial_review(queue, history, snapshot, root)
    if failures or len(reviewed) != 93:
        raise ValueError("terminal_archived_human_reviews_not_exactly_bound")
    result = dict(report=report, queue=queue, history=history, snapshot=snapshot, telemetry=telemetry,
        month=data["data/ai_usage/2026-10.json"], processing_qa=quality, execution=execution,
        final_origin=final_origin, evaluation=evaluation, files=dict(TERMINAL_FOLLOWTHROUGH_FILES))
    result["settlement"] = terminal_live9_settlement(root, result)
    return result


def unchanged_final_paid_execution(item, terminal_origin):
    """Published final receipts keep their real46a guard/window, never a new one."""
    if terminal_origin is None:
        return None
    key = item.get("raw", {}).get("metadata", {}).get("queue_identity_fingerprint")
    old = terminal_origin["queue"].get(key)
    return terminal_origin["execution"] if old is not None and item == old else None


def terminal_source_semantic(value):
    """Preserve every primary/model/editorial field except two cache counters."""
    if isinstance(value,dict):
        return {key: (({"value_type":"str","utf8_sha256":digest(item.encode()),"characters":len(item)}
                if isinstance(item,str) else {"value_type":type(item).__name__,"value":terminal_source_semantic(item)})
                if key in {"page_text","raw_text"} else terminal_source_semantic(item))
                for key,item in value.items() if key not in {"last_checked_at","cache_hit"}}
    return [terminal_source_semantic(item) for item in value] if isinstance(value,list) else value


TERMINAL_REDISCOVERY_URLS = frozenset({
    "https://www.latercera.com/branded/noticia/revive-el-primer-capitulo-de-empresas-en-accion-los-desafios-para-conectar-la-educacion-tecnico-profesional-con-el-empleo/",
    "https://www.latercera.com/branded/noticia/cardenal-chomali-presidenta-de-sofofa-y-rector-de-inacap-dialogan-sobre-el-rol-de-las-empresas-en-la-sociedad/",
    "https://www.latercera.com/videos/noticia/jose-miguel-correa-esta-entrando-mucha-inversion-al-mercado-chileno/",
    "https://www.latercera.com/videos/noticia/el-crudo-documental-de-la-ultima-expedicion-de-jp-mohr/",
    "https://www.latercera.com/videos/noticia/bernardo-larrain-matte-no-basta-con-la-gestion-se-requieren-reformas-claves/",
    "https://www.latercera.com/videos/noticia/claves-de-la-nueva-estrategia-electrica-de-porsche/",
    "https://www.latercera.com/videos/noticia/marisol-pena-expresidenta-del-tc-esta-reforma-constitucional-aborda-temas-que-perfectamente-podrian-ser-acometidos-por-reformas-legales/",
})
TERMINAL_LATE_PERSONAL_URL = "https://www.latercera.com/mundo/noticia/leon-xiv-sera-operado-de-un-nodulo-pulmonar-a-semanas-de-su-gira-por-uruguay-argentina-y-peru/"


def terminal_source_inventory_semantic(item):
    """Seven unprocessed URLs may renew HTML transport; body and dates stay exact."""
    raw = item.get("raw") or {}
    metadata = raw.get("metadata") or {}
    if (raw.get("url") in TERMINAL_REDISCOVERY_URLS and item.get("status") in {"pending", "retry"}
            and metadata.get("publication_date_verified") is True and metadata.get("primary_identity_verified") is True
            and not metadata.get("analysis_model_output")):
        item = dict(item, raw=dict(raw, metadata={key:value for key,value in metadata.items()
            if key not in {"html_sha256", "captured_at", "evidence_revisions"}}))
    return terminal_source_semantic(item)


def terminal_unselected_observation(old, item, key, observer):
    """Explain operational rediscovery separately from editorial processing."""
    original, current = old["raw"], item["raw"]
    before, after = original.get("metadata") or {}, current.get("metadata") or {}
    semantic = lambda value: object_digest(terminal_source_inventory_semantic(value))
    if semantic(old) == semantic(item):
        if terminal_source_semantic(old) == terminal_source_semantic(item):
            return "unchanged"
        kind, revision_reason = "unchanged_unselected_primary_HTML_transport_refresh", "verified_publisher_exception_rediscovery"
        if original.get("url") == "https://www.latercera.com/videos/noticia/marisol-pena-expresidenta-del-tc-esta-reforma-constitucional-aborda-temas-que-perfectamente-podrian-ser-acometidos-por-reformas-legales/":
            revision_reason = "verified_article_rediscovery"
        end = stamp(observer.get("finished_at"))
        captured = stamp(after.get("captured_at"))
        if not captured or not end or captured > end or not SHA.fullmatch(str(after.get("html_sha256", ""))):
            raise ValueError("terminal_followthrough_rediscovery_capture_unverified")
    elif (old.get("status") == "pending" and old.get("attempts") == 0
            and item.get("status") == "archived" and item.get("reason") == "outside_90_day_backfill"
            and original.get("event_date") == before.get("publication_date") == "2026-07-13"
            and before.get("publication_date_verified") is True
            and stamp(observer.get("started_at")).date().isoformat() == "2026-10-12"
            and terminal_source_semantic(dict(old, status="archived", reason="outside_90_day_backfill")) == terminal_source_semantic(item)):
        return "verified_unselected_publication_aged_beyond_90_days"
    elif (original.get("url") == TERMINAL_LATE_PERSONAL_URL and old.get("status") == item.get("status") == "pending"
            and old.get("attempts") == item.get("attempts") == 0 and before.get("article_body_complete") is None
            and after.get("article_body_complete") is True and after.get("queue_identity_fingerprint") == key
            and before.get("article_verified") is before.get("primary_identity_verified") is before.get("publication_date_verified") is True
            and isinstance(before.get("page_text"), str) and len(before["page_text"]) == 5351
            and digest(before["page_text"].encode()) == "57f6222d5fd48097f997c5d975823a20966cd516bc4154cb6c08adec17cd6fbc"):
        restored = dict(after)
        for field in ("article_body_complete", "queue_identity_fingerprint", "evidence_revisions"):
            if field in before: restored[field] = before[field]
            else: restored.pop(field, None)
        if terminal_source_semantic(dict(item, raw=dict(current, metadata=restored))) != terminal_source_semantic(old):
            raise ValueError("terminal_followthrough_late_personal_primary_or_decision_changed")
        kind, revision_reason = "verified_late_personal_primary_identity_enrichment", "verified_article_rediscovery"
    else:
        raise ValueError("terminal_followthrough_unselected_processing_changed")
    previous = before.get("evidence_revisions", [])
    revisions = after.get("evidence_revisions", [])
    if revisions[:len(previous)] != previous or len(revisions) <= len(previous):
        raise ValueError("terminal_followthrough_rediscovery_revision_erased")
    for revision in revisions[len(previous):]:
        if (revision.get("reason") != revision_reason or not stamp(revision.get("at"))
                or stamp(revision["at"]) > stamp(observer.get("finished_at"))
                or revision.get("previous_publication_date") != original.get("event_date")
                or revision.get("verified_publication_date") != current.get("event_date")
                or revision.get("previous_title") != original.get("title") or revision.get("verified_title") != current.get("title")
                or revision.get("lane_preserved") != old.get("lane")
                or revision.get("previous_publisher_exception_reason") != before.get("publisher_exception_reason")
                or revision.get("verified_publisher_exception_reason") != after.get("publisher_exception_reason")):
            raise ValueError("terminal_followthrough_rediscovery_original_identity_changed")
    return kind


def terminal_feed_clock_rollover(root, snapshot, settlement, execution):
    """Recognize only the retained staging UTC rollover; Source feed stays exact."""
    previous = settlement["snapshot"]
    if snapshot.get("signals") == previous.get("signals"):
        return None
    path = "data/audits/pulso_inherited_native_feed_clock_rollover_2026_10_12.json"
    expected = "3a4bdf5e3ed55357b3e1cd6f5492360c9c77bc6b60eb75a543fd66846e9f5e48"
    raw = local_capture_path(root, path).read_bytes()
    if digest(raw) != expected:
        raise ValueError("terminal_followthrough_native_clock_evidence_changed")
    audit = json.loads(raw)
    begin, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    source = lambda rows: [row for row in rows if normalized_url(row.get("source_url"))]
    if (previous.get("date") != audit["prior_date"] or snapshot.get("date") != audit["current_date"]
            or not begin or not end or begin.date().isoformat() != audit["current_date"]
            or end.date() != begin.date()
            or object_digest(previous["signals"]) != audit["old_feed_signals_sha256"]
            or object_digest(snapshot["signals"]) != audit["current_feed_signals_sha256"]
            or source(snapshot["signals"]) != source(previous["signals"])
            or len(source(snapshot["signals"])) != 70
            or digest(local_capture_path(root, "scripts/export_web_snapshot.py").read_bytes()) != audit["exporter_file_sha256"]):
        raise ValueError("terminal_followthrough_effective_history_feed_or_native_stock_changed")
    return dict(path=path, sha256=expected, prior_date=audit["prior_date"], current_date=audit["current_date"],
        classification=audit["classification"], exact_native_changes=len(audit["changes"]),
        old_feed_signals_sha256=audit["old_feed_signals_sha256"], current_feed_signals_sha256=audit["current_feed_signals_sha256"],
        pulso_70_signals_unchanged=True, global_feed_unchanged=False, AI_calls=0)


def verify_terminal_followthrough_execution(root, *, report, queue, history, snapshot, telemetry,
                                            execution=None, origin=None):
    """Observe a new inert core without relabelling the earlier evaluator or AI."""
    origin = origin or terminal_followthrough_origin(root)
    settlement = origin["settlement"]
    execution = execution or report.get("last_core_execution") or report.get("execution") or {}
    begin, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    delta, error = budget_delta(execution)
    selection = execution.get("processing_selection") or {}
    cohort_raw = local_capture_path(root, PROCESSING_COHORT_PATH).read_bytes()
    cohort = json.loads(cohort_raw)
    selected = selection.get("selected_urls") or []
    if (execution.get("mode") != "real_core_processing" or execution.get("engine_called") is not True
            or execution.get("engine_completed") is not True or execution.get("ai_guardrails_modified") is not False
            or not begin or not end or begin > end or begin <= stamp(settlement["execution"]["finished_at"])
            or error or any(value for tier in delta.values() for value in tier.values())
            or execution.get("processing_attempts_increased") != 0
            or digest(cohort_raw) != PROCESSING_COHORT_SHA256 or selection.get("sha256") != PROCESSING_COHORT_SHA256
            or selected != cohort["urls"] or len(set(selected)) != 113
            or selection.get("ready_selected_urls") or selection.get("skipped_not_due_urls")
            or selection.get("skipped_in_progress_urls")
            or set(selection.get("skipped_terminal_urls") or []) != set(selected)
            or len(selection.get("skipped_terminal_urls") or []) != 113
            or telemetry != settlement["telemetry"]
            or any(stamp(row.get("at")) and begin <= stamp(row["at"]) <= end for row in telemetry)
            or execution.get("budget_before", {}).get("month") != settlement["month"]
            or execution.get("budget_after", {}).get("month") != settlement["month"]
            or json.loads(local_capture_path(root, "data/ai_usage/2026-10.json").read_bytes()) != settlement["month"]):
        raise ValueError("terminal_followthrough_not_fresh_genuine_zero_api_zero_attempts")
    fingerprint = execution.get("runtime_fingerprint") or {}
    files = fingerprint.get("files") or {}
    old_files = origin["execution"]["runtime_fingerprint"]["files"]
    changed = {path for path in files if files[path] != old_files.get(path)}
    code = execution.get("code_sha")
    if (set(files) != set(old_files) or not required_runtime_fingerprint_paths(root) <= set(files)
            or fingerprint.get("git_or_marker_sha_used") is not False
            or object_digest(files) != fingerprint.get("sha256")
            or fingerprint.get("sha256") == TERMINAL_FOLLOWTHROUGH_FINGERPRINT
            or "scripts/qa_pulso_recovery.py" not in changed or not changed <= TERMINAL_CONSUMER_PATHS
            or not re.fullmatch(r"[0-9a-f]{40}", str(code or ""))):
        raise ValueError("terminal_followthrough_source_or_policy_changed")
    for path, expected in files.items():
        original = subprocess.run(["git", "show", code + ":" + path], cwd=root, capture_output=True)
        if original.returncode or digest(original.stdout) != expected or digest(local_capture_path(root, path).read_bytes()) != expected:
            raise ValueError("terminal_followthrough_actual_implementation_not_bound")
    previous = {item["raw"]["url"]: (key,item) for key,item in settlement["queue"].items() if item.get("source") == SOURCE}
    rows = [(key,item) for key,item in queue.items() if item.get("source") == SOURCE]
    current = {item["raw"]["url"]: (key,item) for key,item in rows}
    if (len(rows) != len(current) or not set(previous) <= set(current)
            or any(current[url][0] != key for url,(key,item) in previous.items()) or any(url not in current or previous.get(url) != current[url]
            or current[url][1].get("status") not in {"published", "rejected"}
            or technical_processing_deferral(current[url][1], {}) for url in selected)):
        raise ValueError("terminal_followthrough_selected113_proof_or_status_changed")
    native_queue = {key:item for key,item in queue.items() if item.get("source") != SOURCE}
    native_original = {key:item for key,item in settlement["queue"].items() if item.get("source") != SOURCE}
    native_clock_rollover = terminal_feed_clock_rollover(root, snapshot, settlement, execution)
    if (native_queue != native_original or len(native_queue) != 5293 or history != settlement["history"]
            or len([row for row in history if not normalized_url(row.get("source_url"))]) != 897):
        raise ValueError("terminal_followthrough_effective_history_feed_or_native_stock_changed")
    observations = {}
    observer = report.get("last_core_execution") or execution
    for url, (key,item) in current.items():
        if url not in selected and url in previous:
            old = previous[url][1]
            kind = terminal_unselected_observation(old, item, key, observer)
            if kind != "unchanged": observations[url] = kind
        elif url not in previous and (item.get("attempts") != 0 or item.get("status") not in {"pending", "archived"}):
            raise ValueError("terminal_followthrough_new_unselected_candidate_processed")
    stock = dict(commit=LIVE9_PRODUCER, file_sha256=settlement["files"],
        preserved_terminal_urls={url:dict(queue_fingerprint=previous[url][0],
            queue_entry_sha256=object_digest(previous[url][1])) for url in selected},
        native_queue_count=len(native_queue), native_queue_sha256=object_digest(native_queue),
        native_history_count=897,
        native_history_sha256=object_digest([row for row in history if not normalized_url(row.get("source_url"))]),
        history_signal_count=len(history), history_sha256=object_digest(history),
        feed_signal_count=len(snapshot["signals"]), feed_sha256=object_digest(snapshot["signals"]),
        source_queue_semantic_sha256s={url:object_digest(terminal_source_inventory_semantic(current[url][1])) for url in previous},
        original_source_queue_semantic_sha256s={url:object_digest(terminal_source_inventory_semantic(item)) for url,(key,item) in previous.items()},
        unselected_operational_observations=observations)
    return dict(schema_version="pulso_terminal_followthrough_provenance_v1",
        archived_producer=dict(commit=TERMINAL_FOLLOWTHROUGH_PRODUCER,
            code_sha=TERMINAL_FOLLOWTHROUGH_CODE, runtime_fingerprint_sha256=TERMINAL_FOLLOWTHROUGH_FINGERPRINT,
            files=origin["files"], original_qa_promoted=False),
        archived_final_evaluation=origin["evaluation"], current_followthrough_execution=execution,
        archived_processing_qa=origin["processing_qa"], paid_model_lineage=origin["evaluation"]["paid_model_lineage"],
        settlement_producer=dict(commit=LIVE9_PRODUCER,code_sha=LIVE9_CODE,
            runtime_fingerprint_sha256=LIVE9_FINGERPRINT,files=settlement["files"],original_qa_promoted=False),
        settlement_execution=settlement["execution"],settlement_processing_qa=settlement["processing_qa"],
        settlement_live9=settlement["rows"],settlement_response_events=settlement["events"],
        settlement_budget_delta=settlement["budget_delta"],settlement_telemetry_prefix=settlement["telemetry_prefix"],
        launch_stock=stock, inherited_native_feed_clock_rollover=native_clock_rollover,
        preserved_final_receipts=origin["evaluation"]["current_revalidation_receipts"],
        actual_budget_delta=delta, publication_approved=False)


def unchanged_followup_paid_execution(item, final_origin):
    """The three genuine terminal5 keep their323 guard/window after followup."""
    if final_origin is None or has_final_paid_claim(item.get("raw", {}).get("metadata", {})):
        return None
    key = item.get("raw", {}).get("metadata", {}).get("queue_identity_fingerprint")
    old = final_origin["queue"].get(key)
    if not old or old.get("status") not in {"published", "rejected"} or item.get("status") not in {"published", "rejected"}:
        return None
    metadata, prior = item["raw"]["metadata"], old["raw"]["metadata"]
    if (any(item.get(field) != old.get(field) for field in ("attempts", "lane", "detected_at"))
            or any(metadata.get(field) != prior.get(field) for field in (
                "analysis_model_output", "pulso_editorial_proof_validation", "followup_paid_guard_revalidation_admission",
                "followup_paid_guard_revalidation_receipt", "followup_paid_new_fast_attempt_receipts"))):
        return None
    return final_origin["execution"]


def unchanged_current_paid_execution(item, followup_origin):
    """The seven genuine terminal12 keep their66 guard/window after followup."""
    if followup_origin is None or has_followup_paid_claim(item.get("raw", {}).get("metadata", {})):
        return None
    key = item.get("raw", {}).get("metadata", {}).get("queue_identity_fingerprint")
    old = followup_origin["queue"].get(key)
    if not old or old.get("status") not in {"published", "rejected"} or item.get("status") not in {"published", "rejected"}:
        return None
    metadata, prior = item["raw"]["metadata"], old["raw"]["metadata"]
    if (any(item.get(field) != old.get(field) for field in ("attempts", "lane", "detected_at"))
            or any(metadata.get(field) != prior.get(field) for field in (
                "analysis_model_output", "pulso_editorial_proof_validation", "current_paid_guard_revalidation_admission",
                "current_paid_guard_revalidation_receipt", "current_paid_new_fast_attempt_receipts"))):
        return None
    return followup_origin["execution"]


def unchanged_previous_paid_execution(item, current_origin):
    """Terminal reuse remains bound to its real908 execution, not a later run."""
    if current_origin is None or has_current_paid_claim(item.get("raw", {}).get("metadata", {})):
        return None
    old = current_origin["queue"].get(item.get("raw", {}).get("metadata", {}).get("queue_identity_fingerprint"))
    if not old or old.get("status") not in {"published", "rejected"} or item.get("status") not in {"published", "rejected"}:
        return None
    if any(item.get(field) != old.get(field) for field in ("attempts", "lane", "detected_at")):
        return None
    metadata, previous = item["raw"]["metadata"], old["raw"]["metadata"]
    if any(metadata.get(field) != previous.get(field) for field in (
            "analysis_model_output", "pulso_editorial_proof_validation", "paid_guard_revalidation_admission",
            "paid_guard_revalidation_receipt", "paid_guard_new_fast_attempt_receipts")):
        return None
    return current_origin["execution"]


def archived_editorial_input(root, specification, required_path):
    """Read immutable producer bytes, never the currently claimed queue flags."""
    commit = specification.get("commit")
    if (not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit)
            or specification.get("path") != required_path
            or not SHA.fullmatch(str(specification.get("file_sha256", "")))):
        raise ValueError("editorial_producer_reference_invalid")
    result = subprocess.run(["git", "show", commit + ":" + required_path], cwd=root,
                            capture_output=True, check=False)
    if result.returncode or digest(result.stdout) != specification["file_sha256"]:
        raise ValueError("editorial_producer_original_bytes_unavailable_or_changed")
    if required_path.endswith(".jsonl"):
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    return json.loads(result.stdout)


def frozen323_followup_review_binding(root, path, audit_sha, reader, paid, reconstructed):
    """Read the separately frozen receipt omitted by two older reader rows.

    These exact reviews retained complete publisher/model bytes and a second
    independent reader retained the complete dual receipt. Other review files
    still have to declare their full dual binding themselves.
    """
    reader_path = "data/audits/pulso_actual323_three_primary_semantic_review_2026_10_11.json"
    peer_path = "data/audits/pulso_actual323_ilc_mask_independent_second_peer_2026_10_11.json"
    if (path != "data/audits/pulso_actual323_ilc_mask_editorial_review_2026_10_11.json"
            or audit_sha != "8ff73f3d5abba75148238f609d39f96957bf9e51e9b3f16add04c60806c8760c"
            or "revalidated_followup_paid_response" in (reader.get("original_output_binding") or {})):
        return False
    raw = local_capture_path(root, reader_path).read_bytes()
    peer_raw = local_capture_path(root, peer_path).read_bytes()
    if (digest(raw) != "7646fca3839727228c5b603175056320454e4ad3f74e8eb0708d0c6b66e33d66"
            or digest(peer_raw) != "cd826b140ad60154f34bb278a08248265883313c5d0eab39eb2077dd2ce95ecd"):
        raise ValueError("editorial_frozen323_separate_dual_receipt_bytes_changed")
    parent, peer = json.loads(raw), json.loads(peer_raw)
    key = (reader.get("url"), reader.get("publication_date"))
    parents = [row for row in parent["all_signals"] if (row["url"], row["publication_date"]) == key]
    rows = [row for row in peer["all_signals"] if (row["url"], row["publication_date"]) == key]
    metadata = paid["raw"]["metadata"]
    if (len(parent["all_signals"]) != 2 or len(peer["all_signals"]) != 2
            or len(parents) != 1 or parents[0] != reader or len(rows) != 1
            or peer.get("producer_commit") != FINAL_PAID_PRODUCER
            or peer.get("first_reader") != dict(path=reader_path, sha256=digest(raw))
            or peer.get("template") != dict(path=path, sha256=audit_sha)
            or reconstructed.get("publication_execution_code") != FINAL_PAID_CODE
            or reconstructed.get("original_producer") != FOLLOWUP_PAID_PRODUCER):
        raise ValueError("editorial_frozen323_separate_dual_receipt_identity_changed")
    row = rows[0]
    if (row["first_reader_record_sha256"] != object_digest(reader)
            or row["original_queue_entry_sha256"] != object_digest(paid)
            or row["original_full_primary_body"] != metadata["page_text"]
            or row["original_full_model_output"] != metadata["analysis_model_output"]
            or row["original_model_response_binding"] != metadata["analysis_model_output"]["_pulso_analysis_meta"]
            or row["original_full_signal"] != reader["original_full_signal"]
            or row["revalidation_receipt"] != metadata[FOLLOWUP_PAID_RECEIPT]
            or object_digest(row["revalidation_receipt"]) != reconstructed["actual_receipt_sha256"]
            or any(row.get(field) is not True for field in (
                "full_original_body_read", "full_actual_model_output_read", "full_signal_read"))):
        raise ValueError("editorial_frozen323_separate_dual_receipt_primary_or_model_changed")
    return True


def verify_additional_editorial_reviews(queue, history, snapshot, root):
    """Read separate full-body reviews of genuinely paid publications.

    Future audits use the same v1 application format plus immutable producer
    history, queue, runtime report and Response-event references in the separate
    reader's inputs. They can correct or withdraw existing paid publications;
    a retry, fabricated terminal flag or self-reported approval cannot qualify.
    This reader does not import or invoke the correction application.
    """
    source_claims = [item for item in queue.values() if item.get("source") == SOURCE
                     and item.get("raw", {}).get("metadata", {}).get("editorial_review")]
    all_history_claims = [row for row in history if normalized_url(row.get("source_url")) and row.get("editorial_review")]
    if (any(not isinstance(item["raw"]["metadata"]["editorial_review"], dict) for item in source_claims)
            or any(not isinstance(row["editorial_review"], dict) for row in all_history_claims)):
        return {}, [dict(domain="processing", code="additional_editorial_review_unverified",
                         error="editorial_review_provenance_not_an_object")]
    claimed = [item for item in source_claims if item["raw"]["metadata"]["editorial_review"].get("review_file") != EDITORIAL_REVIEW_PATH]
    history_claims = [row for row in all_history_claims if row["editorial_review"].get("review_file") != EDITORIAL_REVIEW_PATH]
    if not claimed and not history_claims:
        return {}, []
    cache, active, producers, required_records, revalidation_origins = {}, set(), {}, set(), {}

    def audit_path(value):
        if (not isinstance(value, str) or not re.fullmatch(r"data/audits/pulso_[A-Za-z0-9_]+\.json", value)
                or local_capture_path(root, value).resolve().parent != (root / "data/audits").resolve()):
            raise ValueError("editorial_review_path_outside_authorized_audits")
        return value

    def load(proof):
        path = audit_path(proof.get("review_file"))
        raw = local_capture_path(root, path).read_bytes()
        if digest(raw) != proof.get("review_sha256"):
            raise ValueError("editorial_review_file_hash_changed")
        audit = json.loads(raw)
        reference = audit.get("independent_review") or {}
        parent_path = audit_path(reference.get("path"))
        parent_raw = local_capture_path(root, parent_path).read_bytes()
        if parent_path == path or digest(parent_raw) != reference.get("sha256"):
            raise ValueError("editorial_separate_reader_hash_changed")
        pinned = FOLLOWUP_REVIEW_PINS.get(path)
        if pinned and (digest(raw), parent_path, digest(parent_raw)) != pinned:
            raise ValueError("editorial_known_followup_immutable_files_changed")
        if not pinned:
            registry = json.loads(local_capture_path(root, EDITORIAL_REGISTRY_PATH).read_bytes())
            registrations = registry.get("reviews") or []
            identities = [entry.get("review_file") for entry in registrations]
            registered = [entry for entry in registrations if entry.get("review_file") == path]
            if (registry.get("schema_version") != "pulso_paid_editorial_review_registry_v1"
                    or registry.get("source_id") != SOURCE or len(set(identities)) != len(identities)
                    or len(registered) != 1 or registered[0] != dict(review_file=path, review_sha256=digest(raw),
                        independent_review_file=parent_path, independent_review_sha256=digest(parent_raw))):
                raise ValueError("editorial_review_not_registered_as_independently_authorized")
        parent = json.loads(parent_raw)
        records, readers = audit.get("records") or [], parent.get("all_signals") or []
        keys = [(r.get("url"), r.get("publication_date")) for r in records]
        reader_keys = [(r.get("url"), r.get("publication_date")) for r in readers]
        if (audit.get("schema_version") != "pulso_editorial_review_v1" or not audit.get("review_id")
                or audit.get("source_id") != SOURCE or parent.get("source_id") != SOURCE
                or not keys or len(set(keys)) != len(keys) or len(set(reader_keys)) != len(reader_keys)
                or set(keys) != set(reader_keys)):
            raise ValueError("editorial_separate_reader_complete_identity_mismatch")
        required_records.update((path, key) for key in keys)
        return path, digest(raw), audit, {key: row for key, row in zip(reader_keys, readers)}

    def producer(parent_document, pinned):
        inputs = parent_document.get("inputs") or {}
        if pinned:
            # The known new5 review predates the generic declaration contract.
            # Its entire dual-reader files and producer commit are frozen above.
            commit = FOCUS_PRODUCER
        else:
            if set(inputs) != {"history", "queue", "runtime_report", "telemetry"}:
                raise ValueError("editorial_genuine_paid_producer_inputs_missing")
            commits = {value.get("commit") for value in inputs.values() if isinstance(value, dict)}
            if len(commits) != 1:
                raise ValueError("editorial_producer_mixed_snapshots")
            commit = next(iter(commits))
        if commit not in producers:
            required = {"history": "data/history/superintendencia_signals.json",
                        "queue": "data/state/pending_queue.json",
                        "runtime_report": "data/audits/pulso_runtime_2026_10_11.json",
                        "telemetry": "data/ai_usage/responses.jsonl"}
            specs = {}
            for key, path in required.items():
                if pinned:
                    result = subprocess.run(["git", "show", str(commit) + ":" + path], cwd=root,
                                            capture_output=True, check=False)
                    if result.returncode:
                        raise ValueError("editorial_known_producer_unavailable")
                    specs[key] = dict(commit=commit, path=path, file_sha256=digest(result.stdout))
                    if key in {"history", "queue"} and inputs.get(key) != specs[key]:
                        raise ValueError("editorial_known_producer_reference_changed")
                else:
                    specs[key] = inputs[key]
            producers[commit] = {key: archived_editorial_input(root, specs[key], path)
                                 for key, path in required.items()}
            producers[commit]["_references"] = specs
            run = producers[commit]["runtime_report"].get("last_core_execution") or producers[commit]["runtime_report"].get("execution") or {}
            first, last = stamp(run.get("started_at")), stamp(run.get("finished_at"))
            events = [row for row in producers[commit]["telemetry"] if first and last and stamp(row.get("at"))
                      and first <= stamp(row["at"]) <= last and row.get("kind") == "fast"]
            before = run.get("budget_before", {}).get("run", {}).get("fast", {})
            after = run.get("budget_after", {}).get("run", {}).get("fast", {})
            delta = {key: after.get(key, -1) - before.get(key, 0) for key in ("attempted", "successful", "failed")}
            if (not first or not last or last < first or delta["successful"] <= 0
                    or delta != dict(attempted=len(events), successful=sum(row.get("success") is True for row in events),
                                     failed=sum(row.get("success") is False for row in events))
                    or len({row.get("response_id") for row in events if row.get("success") is True}) != delta["successful"]):
                raise ValueError("editorial_original_paid_runtime_ledger_or_response_events_mismatch")
        else:
            # Validate each reader's declared hashes even when a commit is reused.
            for key, specification in inputs.items():
                if isinstance(specification, dict) and key in producers[commit]:
                    if specification != producers[commit]["_references"][key]:
                        raise ValueError("editorial_producer_reference_changed_within_review")
        return producers[commit]

    def derive_legacy_first32(proof, key):
        """A frozen first-paid publication has no invented provider JSON/ID."""
        raw = local_capture_path(root, EDITORIAL_REVIEW_PATH).read_bytes()
        primary = local_capture_path(root, INDEPENDENT_EDITORIAL_PATH).read_bytes()
        if digest(raw) != EDITORIAL_REVIEW_SHA256 or digest(primary) != INDEPENDENT_EDITORIAL_SHA256:
            raise ValueError("editorial_legacy_first32_immutable_pair_changed")
        audit, independent = json.loads(raw), json.loads(primary)
        record = next((row for row in audit["records"] if (row["url"], row["publication_date"]) == key), None)
        reading = next((row for row in independent["all_signals"] if (row["url"], row["publication_date"]) == key), None)
        if (len(audit["records"]) != 32 or len(independent["all_signals"]) != 32 or record is None or reading is None
                or audit["independent_review"] != dict(path=INDEPENDENT_EDITORIAL_PATH, sha256=INDEPENDENT_EDITORIAL_SHA256)
                or record["independent_review_record_sha256"] != object_digest(reading)
                or record["decision"] not in {"accept", "correct"}):
            raise ValueError("editorial_legacy_predecessor_not_exact_visible_first32")
        commit = "90e99ad30e6eeaf470480e7847a7a814334a2b7b"
        original_queue = archived_editorial_input(root, dict(commit=commit, path="data/state/pending_queue.json",
            file_sha256="44d1e17ffc5d3f158570e458f59907a9cf7d5fea57575e4c5e0f8bedc20e886b"), "data/state/pending_queue.json")
        original_history = archived_editorial_input(root, dict(commit=commit, path="data/history/superintendencia_signals.json",
            file_sha256="04fcb275bda8f48b2ecefd4923ce99a20b94e850dfbb8415b6321b80bb2fe09e"), "data/history/superintendencia_signals.json")
        items = [row for row in original_queue.values() if row.get("source") == SOURCE
                 and (row.get("raw", {}).get("url"), row.get("raw", {}).get("event_date")) == key]
        signals = [row for row in original_history["signals"] if (row.get("source_url"), row.get("event_date")) == key]
        if len(items) != 1 or len(signals) != 1 or signals[0] != record["original_signal"]:
            raise ValueError("editorial_legacy_original_paid_snapshot_not_exact")
        paid, original = items[0], record["original_signal"]
        metadata = paid["raw"]["metadata"]; body = metadata.get("page_text")
        score = original.get("editorial_relevance"); assessment = record["original_model_assessment"]
        approved = {quote["text"] for quote in reading["supporting_verbatim_quotes"] if quote.get("origin") == "original"}
        if (paid.get("status") != "published" or type(paid.get("attempts")) is not int or paid["attempts"] < 1
                or assessment != metadata.get("editorial_assessment")
                or assessment != dict(decision="published", relevance_score=score, threshold=72,
                                      analysis_reason=assessment.get("analysis_reason"))
                or not assessment.get("analysis_reason") or type(score) is not int or score < 72
                or original.get("evidence_maturity") != "media_reported"
                or original.get("publication_date") != key[1]
                or record["original_signal_sha256"] != object_digest(original)
                or not isinstance(body, str) or body != reading.get("original_full_primary_body")
                or digest(body.encode()) != record["original_body_sha256"]
                or metadata.get("article_body_sha256") != record["original_body_sha256"]
                or metadata.get("analysis_base_article_body_sha256") != record["original_body_sha256"]
                or metadata.get("canonical_url") != key[0] or metadata.get("publication_date") != key[1]
                or any(metadata.get(field) is not True for field in (
                    "article_verified", "article_body_complete", "primary_identity_verified", "publication_date_verified"))
                or not set(record["evidence_quotes"]) <= approved
                or any(" ".join(quote.split()) not in " ".join(body.split()) for quote in record["evidence_quotes"])):
            raise ValueError("editorial_legacy_original_gate_primary_or_quote_changed")
        provenance = dict(schema_version="pulso_editorial_review_v1", review_id=audit["review_id"],
            review_file=EDITORIAL_REVIEW_PATH, review_sha256=EDITORIAL_REVIEW_SHA256, record_sha256=object_digest(record),
            original_signal_sha256=record["original_signal_sha256"], original_body_sha256=record["original_body_sha256"],
            publication_date=key[1], decision=record["decision"], reason=record["reason"], evidence_quotes=record["evidence_quotes"],
            original_terminal_status="published", original_model_assessment=assessment,
            original_model_what_happened=original["what_happened"], original_model_why_it_matters=original["why_it_matters"])
        effective = dict(original, editorial_review=provenance, editorial_decision="accept",
                         editorial_review_reason=record["reason"], feed_visibility=True)
        if record["decision"] == "correct":
            effective.update(record["proposed"], event_status=record["event_status"],
                             prospective_evidence=record["event_status"] in {"proposed", "planned"})
            assessment = dict(decision="published", reason="independent_editorial_copy_corrected", relevance_score=score,
                threshold=72, original_model_assessment=assessment, review_sha256=EDITORIAL_REVIEW_SHA256)
        if proof != provenance:
            raise ValueError("editorial_legacy_predecessor_provenance_changed")
        return effective, provenance, paid, assessment

    def derive(proof, key):
        identity = (proof.get("review_file"), key)
        if identity in active:
            raise ValueError("editorial_review_predecessor_cycle")
        if identity in cache:
            result = cache[identity]
            if result[1] != proof:
                raise ValueError("editorial_review_provenance_changed")
            return result
        active.add(identity)
        if proof.get("review_file") == EDITORIAL_REVIEW_PATH:
            result = derive_legacy_first32(proof, key)
            cache[identity] = result
            active.remove(identity)
            return result
        path, audit_sha, audit, readers = load(proof)
        record = next((row for row in audit["records"] if (row["url"], row["publication_date"]) == key), None)
        if record is None:
            raise ValueError("editorial_review_record_not_bound")
        reader = readers[key]
        original, decision = record.get("original_signal") or {}, record.get("decision")
        url, day = key
        score = original.get("editorial_relevance")
        body = reader.get("original_full_primary_body")
        quotes = record.get("evidence_quotes")
        allowed = {q["text"] for q in reader.get("supporting_verbatim_quotes", []) if q.get("origin") == "original"}
        if (normalized_url(url) != url or original.get("source_url") != url
                or original.get("event_date") != day or original.get("publication_date") != day
                or original.get("evidence_maturity") != "media_reported" or type(score) is not int or score < 72
                or record.get("original_signal_sha256") != object_digest(original)
                or reader.get("original_signal_sha256") != object_digest(original)
                or reader.get("original_full_signal") != original
                or record.get("independent_review_record_sha256") != object_digest(reader)
                or record.get("original_body_sha256") != reader.get("original_body_sha256")
                or not isinstance(body, str) or digest(body.encode()) != record.get("original_body_sha256")
                or reader.get("full_original_body_read") is not True or reader.get("full_signal_read") is not True
                or reader.get("decision") != decision or reader.get("exact_reason") != record.get("reason")
                or not isinstance(record.get("reason"), str) or not record["reason"].strip()
                or decision not in {"accept", "reject", "group", "correct"}
                or not isinstance(quotes, list) or not quotes or not set(quotes) <= allowed
                or any(not isinstance(q, str) or len(" ".join(q.split())) < 20
                       or " ".join(q.split()) not in " ".join(body.split()) for q in quotes)
                or reader.get("original_published_what_happened") != original.get("what_happened")
                or reader.get("original_published_why_it_matters") != original.get("why_it_matters")):
            raise ValueError("editorial_independent_full_original_or_decision_changed")
        assessment = record.get("original_model_assessment")
        predecessor = record.get("previous_editorial_review")
        if predecessor:
            previous, previous_proof, paid, previous_assessment = derive(predecessor, key)
            target = record.get("duplicate_of") or {}
            reviewed_group = (decision == "group" and not record.get("proposed")
                and set(target) == {"url", "event_date", "queue_fingerprint", "source_id", "survivor_signal_sha256"}
                and reader.get("duplicate_survivor_binding") == target)
            historical_correction = (decision == "correct" and record.get("event_status") == "historical"
                and set(record.get("proposed") or {}) == {"what_happened", "why_it_matters"}
                and record["proposed"]["what_happened"] == original.get("what_happened"))
            if (previous != original or predecessor != original.get("editorial_review")
                    or previous_proof["decision"] not in ({"accept", "correct"} if reviewed_group else {"accept"})
                    or previous.get("feed_visibility") is not True or original.get("editorial_decision") != "accept"
                    or not (reviewed_group or historical_correction)
                    or reader.get("previous_editorial_review") != predecessor or assessment != previous_assessment):
                raise ValueError("editorial_followup_predecessor_not_exact_accepted_publication")
            prior_model = paid["raw"]["metadata"].get("analysis_model_output")
            if prior_model is None:
                # Only the already-pinned first-paid snapshot can have this
                # declared legacy limitation. No fake provider JSON or ID.
                if (not reviewed_group or previous_proof.get("review_file") != EDITORIAL_REVIEW_PATH
                        or reader.get("original_model_output_missing") is not True
                        or reader.get("original_full_model_output") is not None
                        or reader.get("original_model_output_semantic_sha256") is not None
                        or reader.get("original_model_response_binding") is not None
                        or reader.get("original_output_binding") != next(row["original_output_binding"] for row in
                            json.loads(local_capture_path(root, INDEPENDENT_EDITORIAL_PATH).read_bytes())["all_signals"]
                            if (row["url"], row["publication_date"]) == key)):
                    raise ValueError("editorial_legacy_model_limitation_not_explicitly_bound")
            elif (reviewed_group and reader.get("original_full_model_output") != prior_model
                    or reader.get("original_model_output_semantic_sha256") != object_digest(prior_model)
                    or reader.get("original_model_response_binding") != prior_model.get("_pulso_analysis_meta")):
                raise ValueError("editorial_followup_original_paid_model_or_primary_changed")
            if (reader.get("original_html_sha256") != paid["raw"]["metadata"].get("html_sha256")
                    or body != paid["raw"]["metadata"].get("page_text")):
                raise ValueError("editorial_followup_original_paid_model_or_primary_changed")
        else:
            parent_document = json.loads(local_capture_path(root, audit["independent_review"]["path"]).read_bytes())
            archived = producer(parent_document, path in FOLLOWUP_REVIEW_PINS)
            signals = [row for row in archived["history"]["signals"] if (row.get("source_url"), row.get("event_date")) == key]
            items = [row for row in archived["queue"].values() if row.get("source") == SOURCE
                     and (row.get("raw", {}).get("url"), row.get("raw", {}).get("event_date")) == key]
            if len(signals) != 1 or len(items) != 1 or signals[0] != original:
                raise ValueError("editorial_original_not_in_immutable_paid_history")
            paid = items[0]
            paid_metadata = paid["raw"].get("metadata", {})
            model = paid_metadata.get("analysis_model_output") or {}
            model_response = model.get("_pulso_analysis_meta") or {}
            execution = archived["runtime_report"].get("last_core_execution") or archived["runtime_report"].get("execution") or {}
            begin, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
            events = [event for event in archived["telemetry"] if event.get("response_id") == model_response.get("response_id")
                      and event.get("success") is True and event.get("kind") == "fast"
                      and begin and end and stamp(event.get("at")) and begin <= stamp(event["at"]) <= end]
            binding = reader.get("original_output_binding") or {}
            revalidated_paid_response = None
            revalidated_current_paid_response = None
            revalidated_followup_paid_response = None
            revalidated_final_paid_response = None
            if not events and has_final_paid_claim(paid_metadata):
                if FINAL_PAID_PRODUCER not in revalidation_origins:
                    revalidation_origins[FINAL_PAID_PRODUCER] = final_paid_origin(root)
                else:
                    final_paid_proof_files(root)
                origin = revalidation_origins[FINAL_PAID_PRODUCER]
                receipt = verify_final_paid_revalidation(paid, root, execution=execution,
                    telemetry=archived["telemetry"], origin=origin, archived_execution=True)
                if receipt.get("old_paid_output_reused") is not True or receipt.get("disposition") != "reuse_code_fn":
                    raise ValueError("editorial_final_revalidation_not_exact_frozen2_publication")
                old_execution = origin["execution"]
                old_begin, old_end = stamp(old_execution["started_at"]), stamp(old_execution["finished_at"])
                events = [event for event in origin["telemetry"]
                    if event.get("response_id") == model_response.get("response_id")
                    and event.get("success") is True and event.get("kind") == "fast"
                    and stamp(event.get("at")) and old_begin <= stamp(event["at"]) <= old_end]
                revalidated_final_paid_response = dict(original_producer=FINAL_PAID_PRODUCER,
                    original_core_code=FINAL_PAID_CODE, publication_execution_code=execution["code_sha"],
                    manifest_ref=FINAL_PAID_PATH, manifest_sha256=FINAL_PAID_SHA256,
                    actual_receipt_sha256=object_digest(paid_metadata[FINAL_PAID_RECEIPT]), proof=receipt)
            elif not events and has_followup_paid_claim(paid_metadata):
                if FOLLOWUP_PAID_PRODUCER not in revalidation_origins:
                    revalidation_origins[FOLLOWUP_PAID_PRODUCER] = followup_paid_origin(root)
                else:
                    followup_paid_proof_files(root)
                origin = revalidation_origins[FOLLOWUP_PAID_PRODUCER]
                receipt = verify_followup_paid_revalidation(paid, root, execution=execution,
                    telemetry=archived["telemetry"], origin=origin, archived_execution=True)
                if receipt.get("old_paid_output_reused") is not True or receipt.get("disposition") != "reuse_code_fn":
                    raise ValueError("editorial_followup_revalidation_not_exact_frozen3_publication")
                old_execution = origin["execution"]
                old_begin, old_end = stamp(old_execution["started_at"]), stamp(old_execution["finished_at"])
                events = [event for event in origin["telemetry"]
                    if event.get("response_id") == model_response.get("response_id")
                    and event.get("success") is True and event.get("kind") == "fast"
                    and stamp(event.get("at")) and old_begin <= stamp(event["at"]) <= old_end]
                revalidated_followup_paid_response = dict(original_producer=FOLLOWUP_PAID_PRODUCER,
                    original_core_code=FOLLOWUP_PAID_CODE, publication_execution_code=execution["code_sha"],
                    manifest_ref=FOLLOWUP_PAID_PATH, manifest_sha256=FOLLOWUP_PAID_SHA256,
                    actual_receipt_sha256=object_digest(paid_metadata[FOLLOWUP_PAID_RECEIPT]), proof=receipt)
            elif not events and has_current_paid_claim(paid_metadata):
                if CURRENT_PAID_PRODUCER not in revalidation_origins:
                    revalidation_origins[CURRENT_PAID_PRODUCER] = current_paid_origin(root)
                else:
                    current_paid_proof_files(root)
                origin = revalidation_origins[CURRENT_PAID_PRODUCER]
                receipt = verify_current_paid_revalidation(paid, root, execution=execution,
                    telemetry=archived["telemetry"], origin=origin, archived_execution=True)
                if receipt.get("old_paid_output_reused") is not True or receipt.get("disposition") != "reuse_code_fn":
                    raise ValueError("editorial_current_revalidation_not_exact_frozen2_publication")
                old_execution = origin["execution"]
                old_begin, old_end = stamp(old_execution["started_at"]), stamp(old_execution["finished_at"])
                events = [event for event in origin["telemetry"]
                    if event.get("response_id") == model_response.get("response_id")
                    and event.get("success") is True and event.get("kind") == "fast"
                    and stamp(event.get("at")) and old_begin <= stamp(event["at"]) <= old_end]
                revalidated_current_paid_response = dict(original_producer=CURRENT_PAID_PRODUCER,
                    original_core_code=CURRENT_PAID_CODE, publication_execution_code=execution["code_sha"],
                    manifest_ref=CURRENT_PAID_PATH, manifest_sha256=CURRENT_PAID_SHA256,
                    actual_receipt_sha256=object_digest(paid_metadata[CURRENT_PAID_RECEIPT]), proof=receipt)
            elif not events and has_paid_revalidation_claim(paid_metadata):
                # A published revalidation has two immutable provenances: its
                # actual publication/guard run and the earlier genuinely paid
                # answer. Never invent a Response event in the later window.
                if PAID_REVALIDATION_PRODUCER not in revalidation_origins:
                    revalidation_origins[PAID_REVALIDATION_PRODUCER] = paid_revalidation_origin(root)
                else:
                    paid_revalidation_proof_files(root)
                origin = revalidation_origins[PAID_REVALIDATION_PRODUCER]
                receipt = verify_paid_guard_revalidation(paid, root, execution=execution,
                    telemetry=archived["telemetry"], origin=origin, archived_execution=True)
                if receipt.get("old_paid_output_reused") is not True or receipt.get("disposition") != "reuse_code_fn":
                    raise ValueError("editorial_revalidation_not_exact_frozen_paid_publication")
                old_execution = origin["execution"]
                old_begin, old_end = stamp(old_execution["started_at"]), stamp(old_execution["finished_at"])
                events = [event for event in origin["telemetry"]
                          if event.get("response_id") == model_response.get("response_id")
                          and event.get("success") is True and event.get("kind") == "fast"
                          and stamp(event.get("at")) and old_begin <= stamp(event["at"]) <= old_end]
                revalidated_paid_response = dict(original_producer=PAID_REVALIDATION_PRODUCER,
                    original_core_code=PAID_REVALIDATION_CODE,
                    publication_execution_code=execution["code_sha"],
                    manifest_ref=PAID_REVALIDATION_PATH, manifest_sha256=PAID_REVALIDATION_SHA256,
                    actual_receipt_sha256=object_digest(paid_metadata["paid_guard_revalidation_receipt"]),
                    proof=receipt)
            if binding.get("revalidated_paid_response") != revalidated_paid_response:
                raise ValueError("editorial_revalidated_response_dual_provenance_changed")
            if binding.get("revalidated_current_paid_response") != revalidated_current_paid_response:
                raise ValueError("editorial_current_revalidated_response_dual_provenance_changed")
            if binding.get("revalidated_final_paid_response") != revalidated_final_paid_response:
                raise ValueError("editorial_final_revalidated_response_dual_provenance_changed")
            if binding.get("revalidated_followup_paid_response") != revalidated_followup_paid_response:
                if (revalidated_followup_paid_response is None or not frozen323_followup_review_binding(
                        root, path, audit_sha, reader, paid, revalidated_followup_paid_response)):
                    raise ValueError("editorial_followup_revalidated_response_dual_provenance_changed")
            request = "Fuente: Pulso / La Tercera\nTítulo: " + paid["raw"]["title"] + "\nContenido:\n" + body
            if (paid.get("status") != "published" or type(paid.get("attempts")) is not int or paid["attempts"] < 1
                    or paid["raw"].get("source_slug") != SOURCE or paid["raw"].get("source_type") != "press_high_trust"
                    or paid_metadata.get("canonical_url") != url or paid_metadata.get("publication_date") != day
                    or any(paid_metadata.get(field) is not True for field in (
                        "article_verified", "article_body_complete", "primary_identity_verified", "publication_date_verified"))
                    or assessment != paid_metadata.get("editorial_assessment")
                    or assessment != dict(decision="published", relevance_score=score, threshold=72,
                                          analysis_reason=assessment.get("analysis_reason"))
                    or not assessment.get("analysis_reason") or paid_metadata.get("page_text") != body
                    or paid_metadata.get("analysis_base_article_body_sha256") != record["original_body_sha256"]
                    or binding.get("retained_model_output_semantic_sha256") != object_digest(model)
                    or binding.get("model_response") != model_response or binding.get("signal_sha256") != object_digest(original)
                    or model.get("relevance_score") != score or not isinstance(model_response.get("response_id"), str)
                    or not model_response["response_id"].strip()
                    or not SHA.fullmatch(str(model_response.get("raw_model_output_sha256", "")))
                    or paid_metadata.get("html_sha256") != reader.get("original_html_sha256")
                    or paid_metadata.get("analysis_input_format") != "full_primary_article_body"
                    or paid_metadata.get("analysis_input_complete") is not True
                    or model_response.get("analysis_text_sha256") != digest(body.encode())
                    or model_response.get("request_input_sha256") != digest(request.encode())
                    or execution.get("mode") != "real_core_processing" or execution.get("engine_completed") is not True
                    or execution.get("engine_called") is not True or execution.get("ai_guardrails_modified") is not False
                    or len(events) != 1):
                raise ValueError("editorial_original_genuine_paid_response_or_gate_not_bound")
        provenance = dict(schema_version="pulso_editorial_review_v1", review_id=audit["review_id"],
            review_file=path, review_sha256=audit_sha, record_sha256=object_digest(record),
            original_signal_sha256=record["original_signal_sha256"], original_body_sha256=record["original_body_sha256"],
            publication_date=day, decision=decision, reason=record["reason"], evidence_quotes=quotes,
            original_terminal_status="published", original_model_assessment=assessment,
            original_model_what_happened=original["what_happened"], original_model_why_it_matters=original["why_it_matters"])
        if predecessor:
            provenance["previous_editorial_review"] = predecessor
        if record.get("duplicate_of"):
            provenance["duplicate_of"] = record["duplicate_of"]
        effective = dict(original, editorial_review=provenance, editorial_decision=decision if decision in {"reject", "group"} else "accept",
                         editorial_review_reason=record["reason"], feed_visibility=decision not in {"reject", "group"})
        effective_assessment = assessment
        if decision == "correct":
            proposed = record.get("proposed") or {}
            approved = dict(what_happened=reader.get("proposed_what_happened"), why_it_matters=reader.get("proposed_why_it_matters"))
            if reader.get("proposed_category"):
                approved["category"] = reader["proposed_category"]
            if (proposed != approved or not set(proposed) <= {"what_happened", "why_it_matters", "category"}
                    or proposed.get("category", "Prestadores") not in {"Prestadores", "Regulación & Legal"}
                    or record.get("event_status") != reader.get("event_status")
                    or record.get("event_status") not in {"reported", "proposed", "planned", "historical"}
                    or not explicit_media_attribution(proposed.get("what_happened"))):
                raise ValueError("editorial_corrected_copy_not_independently_bound")
            effective.update(proposed, event_status=record["event_status"], prospective_evidence=record["event_status"] in {"proposed", "planned"})
            effective_assessment = dict(decision="published", reason="independent_editorial_copy_corrected", relevance_score=score,
                threshold=72, original_model_assessment=assessment, review_sha256=audit_sha)
        elif decision in {"reject", "group"}:
            effective_assessment = dict(decision="rejected", reason="independent_editorial_review:" + record["reason"],
                relevance_score=score, threshold=72, original_model_assessment=assessment, review_sha256=audit_sha)
        if proof != provenance:
            raise ValueError("editorial_review_provenance_changed")
        if decision not in {"reject", "group"}:
            from copy import deepcopy
            from radar_salud.editorial_gate import publication_ready
            ok, reason, _ = publication_ready(deepcopy(effective))
            # Later Dirección relevance rules (27-oct-2026) withdraw a card from the feed;
            # they do not invalidate the provenance of the reviewed copy being verified here.
            if not ok and reason not in {"health_not_main_subject", "institutional_agenda"}:
                raise ValueError("editorial_effective_copy_fails_existing_publication_gate")
        result = effective, provenance, paid, effective_assessment
        cache[identity] = result
        active.remove(identity)
        return result

    verified, failures = {}, []
    for claim in claimed + history_claims:
        raw = claim.get("raw")
        key = (raw.get("url"), raw.get("event_date")) if raw else (claim.get("source_url"), claim.get("event_date"))
        proof = raw["metadata"]["editorial_review"] if raw else claim["editorial_review"]
        try:
            effective, provenance, paid, assessment = derive(proof, key)
            matches = [row for row in queue.values() if row.get("source") == SOURCE
                       and (row.get("raw", {}).get("url"), row.get("raw", {}).get("event_date")) == key]
            signals = [row for row in history if (row.get("source_url"), row.get("event_date")) == key]
            if len(matches) != 1 or len(signals) != 1:
                raise ValueError("editorial_effective_identity_missing_or_ambiguous")
            item, signal = matches[0], signals[0]
            metadata, primary = item["raw"].get("metadata", {}), paid["raw"].get("metadata", {})
            rejected = provenance["decision"] in {"reject", "group"}
            if (signal != effective or metadata.get("editorial_review") != provenance
                    or metadata.get("editorial_assessment") != assessment
                    or item.get("status") != ("rejected" if rejected else "published")
                    or any(item.get(field) != paid.get(field) for field in ("attempts", "lane", "detected_at"))
                    or metadata.get("what_happened") != effective["what_happened"]
                    or metadata.get("why_it_matters") != effective["why_it_matters"]
                    or metadata.get("analysis_model_output") != primary.get("analysis_model_output")
                    or metadata.get("page_text") != primary.get("page_text")
                    or any(metadata.get(field) != primary.get(field) for field in (
                        "canonical_url", "publication_date", "html_sha256", "article_body_sha256", "analysis_base_article_body_sha256"))
                    or any(metadata.get(field) is not True for field in (
                        "article_verified", "article_body_complete", "primary_identity_verified", "publication_date_verified"))
                    or rejected and (metadata.get("rejection_reason") != assessment["reason"] or item.get("last_error") != assessment["reason"])):
                raise ValueError("editorial_effective_state_model_primary_or_bookkeeping_changed")
            present = [row for row in snapshot.get("signals", []) if (row.get("source_url"), row.get("event_date")) == key]
            if rejected and present or not rejected and len(present) != 1:
                raise ValueError("editorial_effective_serialized_feed_presence_changed")
            if present and any(row.get(field) != effective.get(field) for row in present for field in (
                    "what_happened", "why_it_matters", "event_date", "publication_date", "editorial_relevance",
                    "evidence_maturity", "category", "editorial_review", "editorial_decision", "feed_visibility", "event_status", "prospective_evidence")):
                raise ValueError("editorial_effective_serialized_feed_copy_changed")
            if provenance["decision"] == "group":
                target = provenance.get("duplicate_of") or {}
                target_key = (target.get("url"), target.get("event_date"))
                survivors = [row for row in history if (row.get("source_url"), row.get("event_date")) == target_key]
                survivor_items = [row for row in queue.values() if (row.get("raw", {}).get("url"), row.get("raw", {}).get("event_date")) == target_key]
                feeds = [row for row in snapshot.get("signals", []) if (row.get("source_url"), row.get("event_date")) == target_key]
                explicit_target = target.get("queue_fingerprint") is not None
                if explicit_target:
                    if (set(target) != {"url", "event_date", "queue_fingerprint", "source_id", "survivor_signal_sha256"}
                            or not isinstance(target.get("source_id"), str) or not target["source_id"].strip()
                            or not SHA.fullmatch(str(target.get("survivor_signal_sha256", "")))):
                        raise ValueError("editorial_group_explicit_survivor_descriptor_invalid")
                    survivor_items = [candidate for fingerprint, candidate in queue.items()
                        if fingerprint == target["queue_fingerprint"] and candidate.get("source") == target["source_id"]
                        and (candidate.get("raw", {}).get("url"), candidate.get("raw", {}).get("event_date")) == target_key]
                    survivors = [signal for signal in survivors if object_digest(signal) == target["survivor_signal_sha256"]]
                    if len(survivors) == 1:
                        record_id = survivors[0].get("source_record_id")
                        feeds = [signal for signal in feeds if signal.get("source_record_id") == record_id]
                review_path, _, audit, readers = load(provenance)
                reader = readers[key]
                target_record = next((row for row in audit["records"]
                    if (row["url"], row["publication_date"]) == target_key), None)
                if target_record:
                    # Hash the immutable original, not a signal that embeds
                    # this audit's own hash. Reconstruct the final target copy.
                    if len(survivors) != 1:
                        raise ValueError("editorial_group_target_identity_not_unique")
                    target_effective, _, target_paid, target_assessment = derive(
                        survivors[0].get("editorial_review") or {}, target_key)
                    target_original = target_record["original_signal"]
                    if (survivors[0] != target_effective or len(survivor_items) != 1
                            or survivor_items[0].get("raw", {}).get("metadata", {}).get("editorial_assessment") != target_assessment
                            or target_record.get("decision") not in {"accept", "correct"}):
                        raise ValueError("editorial_group_target_reviewed_effective_state_changed")
                else:
                    parent_document = json.loads(local_capture_path(root, audit["independent_review"]["path"]).read_bytes())
                    target_producer = producer(parent_document, review_path in FOLLOWUP_REVIEW_PINS)
                    original_targets = [row for row in target_producer["history"]["signals"]
                        if (row.get("source_url"), row.get("event_date")) == target_key]
                    paid_targets = [row for row in target_producer["queue"].values()
                        if (row.get("raw", {}).get("url"), row.get("raw", {}).get("event_date")) == target_key]
                    if explicit_target:
                        original_targets = [signal for signal in original_targets
                                            if object_digest(signal) == target["survivor_signal_sha256"]]
                        paid_targets = [candidate for fingerprint, candidate in target_producer["queue"].items()
                            if fingerprint == target["queue_fingerprint"] and candidate.get("source") == target["source_id"]
                            and (candidate.get("raw", {}).get("url"), candidate.get("raw", {}).get("event_date")) == target_key]
                    if (len(original_targets) != 1 or len(paid_targets) != 1
                            or survivors != original_targets or survivor_items != paid_targets):
                        raise ValueError("editorial_group_target_not_in_immutable_published_producer")
                    target_original, target_paid = original_targets[0], paid_targets[0]
                    target_assessment = target_paid.get("raw", {}).get("metadata", {}).get("editorial_assessment") or {}
                if (target_key == key or len(survivors) != 1 or len(survivor_items) != 1 or len(feeds) != 1
                        or survivor_items[0].get("status") != "published" or survivors[0].get("feed_visibility") is False
                        or survivors[0].get("editorial_decision") in {"reject", "group"}
                        or type(survivors[0].get("editorial_relevance")) is not int or survivors[0]["editorial_relevance"] < 72
                        or target_paid.get("status") != "published"
                        or (not explicit_target or target["source_id"] == SOURCE) and (
                            target_assessment.get("decision") != "published" or target_assessment.get("threshold") != 72
                            or target_assessment.get("relevance_score") != survivors[0]["editorial_relevance"])
                        or explicit_target and target["source_id"] != SOURCE and (
                            survivors[0].get("source_type") not in {"official", "press_high_trust"}
                            or target_paid.get("raw", {}).get("metadata", {}).get("what_happened") != survivors[0].get("what_happened")
                            or target_paid.get("raw", {}).get("metadata", {}).get("why_it_matters") != survivors[0].get("why_it_matters")
                            or target_assessment and (
                                target_assessment.get("threshold") != 72
                                or target_assessment.get("score") != survivors[0]["editorial_relevance"]
                                or target_assessment.get("decision") not in {None, "published"}))
                        or normalized_url(target_key[0]) and survivors[0].get("evidence_maturity") != "media_reported"
                        or explicit_target and reader.get("duplicate_survivor_binding") != target
                        or reader.get("duplicate_of") != target_key[0]
                        or reader.get("duplicate_of_event_date", target.get("event_date") if explicit_target else None) != target_key[1]
                        or reader.get("duplicate_target_signal_sha256",
                            reader.get("target_signal_sha256") if explicit_target else None) != object_digest(target_original)
                        or reader.get("duplicate_target_queue_sha256",
                            reader.get("target_queue_entry_sha256") if explicit_target else None) != object_digest(target_paid)
                        or explicit_target and (
                            reader.get("full_target_original_body_read") is not True
                            or reader.get("full_target_signal_read") is not True
                            or reader.get("target_full_signal") != target_original
                            or reader.get("target_full_queue_entry") != target_paid
                            or not isinstance(reader.get("target_full_primary_content"), str)
                            or reader["target_full_primary_content"] != target_paid.get("raw", {}).get("metadata", {}).get("page_text")
                            or digest(reader["target_full_primary_content"].encode()) != reader.get("target_body_sha256")
                            or not reader.get("target_supporting_verbatim_quotes")
                            or any(not isinstance(quote.get("text"), str)
                                or len(" ".join(quote["text"].split())) < 20
                                or " ".join(quote["text"].split()) not in " ".join(reader["target_full_primary_content"].split())
                                for quote in reader["target_supporting_verbatim_quotes"]))
                        or any(feeds[0].get(field) != survivors[0].get(field) for field in (
                            "what_happened", "why_it_matters", "event_date", "publication_date", "editorial_relevance", "evidence_maturity",
                            "category", "event_status", "prospective_evidence"))):
                    raise ValueError("editorial_group_target_not_actual_unique_published_survivor")
                from copy import deepcopy
                from radar_salud.editorial_gate import publication_ready
                if not publication_ready(deepcopy(survivors[0]))[0]:
                    raise ValueError("editorial_group_target_fails_existing_publication_gate")
            verified[key[0]] = provenance
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            finding = dict(domain="processing", code="additional_editorial_review_unverified", url=key[0], error=str(error))
            if finding not in failures:
                failures.append(finding)
        finally:
            active.clear()
    if required_records - set(cache):
        failures.append(dict(domain="processing", code="additional_editorial_review_incomplete_current_records",
                             omitted_records=sorted([list(key) for key in required_records - set(cache)])))
    return ({} if failures else verified), failures


def verify_bound_editorial_review(queue, history, snapshot, root):
    """Verify the exact independently reviewed ALL32 correction, not flags.

    Original model outputs remain immutable in the pinned audit. A withdrawal
    is allowed only when its complete effective history, queue assessment and
    provenance match that audit; the reader never applies a correction.
    """
    additional, additional_failures = verify_additional_editorial_reviews(queue, history, snapshot, root)
    source_queue = [item for item in queue.values() if item.get("source") == SOURCE]
    claimed = [item for item in source_queue if item.get("raw", {}).get("metadata", {}).get("editorial_review")]
    claimed_history = [item for item in history if normalized_url(item.get("source_url"))
                       and item.get("editorial_review")]
    if not claimed and not claimed_history:
        return additional, additional_failures
    findings, verified = list(additional_failures), dict(additional)
    def fail(code, **evidence):
        findings.append(dict(domain="processing", code=code, **evidence))
    try:
        raw = (root / EDITORIAL_REVIEW_PATH).read_bytes()
        independent_raw = (root / INDEPENDENT_EDITORIAL_PATH).read_bytes()
        if digest(raw) != EDITORIAL_REVIEW_SHA256 or digest(independent_raw) != INDEPENDENT_EDITORIAL_SHA256:
            raise ValueError("independent_editorial_review_file_changed")
        audit, independent = json.loads(raw), json.loads(independent_raw)
        records = audit["records"]
        originals = {(row["url"], row["publication_date"]): row for row in independent["all_signals"]}
        if (len(records) != 32 or len(originals) != 32
                or audit["independent_review"] != dict(path=INDEPENDENT_EDITORIAL_PATH, sha256=INDEPENDENT_EDITORIAL_SHA256)
                or {(row["url"], row["publication_date"]) for row in records} != set(originals)):
            raise ValueError("independent_editorial_review_incomplete")
    except (OSError, ValueError, KeyError, TypeError) as error:
        fail("independent_editorial_review_unverified", error=str(error))
        return {}, findings
    keys = {(row["url"], row["publication_date"]) for row in records}
    if (any((item["raw"].get("url"), item["raw"].get("event_date")) not in keys and item["raw"].get("url") not in additional for item in claimed)
            or any((item.get("source_url"), item.get("event_date")) not in keys and item.get("source_url") not in additional for item in claimed_history)):
        fail("unbound_editorial_review_record")
    feed = snapshot.get("signals", [])
    for record in records:
        url, day = record["url"], record["publication_date"]
        ancestor = additional.get(url)
        while isinstance(ancestor, dict) and ancestor.get("review_file") != EDITORIAL_REVIEW_PATH:
            ancestor = ancestor.get("previous_editorial_review")
        if (isinstance(ancestor, dict) and ancestor.get("review_sha256") == EDITORIAL_REVIEW_SHA256
                and ancestor.get("publication_date") == day
                and ancestor.get("record_sha256") == object_digest(record)):
            # derive() already verified this exact frozen predecessor, full
            # immutable paid primary, and the authorized later effective state.
            continue
        original, decision = record["original_signal"], record["decision"]
        independent_record = originals[(url, day)]
        matches = [item for item in source_queue if item.get("raw", {}).get("url") == url
                   and item.get("raw", {}).get("event_date") == day]
        signals = [item for item in history if item.get("source_url") == url and item.get("event_date") == day]
        if len(matches) != 1 or len(signals) != 1:
            fail("editorial_review_history_queue_identity_missing_or_ambiguous", url=url)
            continue
        item, signal = matches[0], signals[0]
        metadata = item["raw"].get("metadata", {})
        body = metadata.get("page_text")
        approved_quotes = {quote["text"] for quote in independent_record["supporting_verbatim_quotes"]
                           if quote.get("origin") == "original"}
        if (record["independent_review_record_sha256"] != object_digest(independent_record)
                or object_digest(original) != record["original_signal_sha256"]
                or not isinstance(body, str) or digest(body.encode()) != record["original_body_sha256"]
                or metadata.get("article_body_sha256") != record["original_body_sha256"]
                or metadata.get("analysis_base_article_body_sha256") != record["original_body_sha256"]
                or not set(record["evidence_quotes"]) <= approved_quotes
                or any(" ".join(quote.split()) not in " ".join(body.split()) for quote in record["evidence_quotes"])
                or original.get("evidence_maturity") != "media_reported"
                or original.get("publication_date") != day or original.get("event_date") != day
                or original.get("source_url") != url or type(original.get("editorial_relevance")) is not int
                or original["editorial_relevance"] < 72
                or metadata.get("canonical_url") != url or metadata.get("publication_date") != day
                or any(metadata.get(key) is not True for key in
                       ("article_verified", "article_body_complete", "primary_identity_verified", "publication_date_verified"))):
            fail("editorial_review_original_output_body_or_date_unverified", url=url)
        provenance = dict(schema_version="pulso_editorial_review_v1", review_id=audit["review_id"],
            review_file=EDITORIAL_REVIEW_PATH, review_sha256=EDITORIAL_REVIEW_SHA256,
            record_sha256=object_digest(record), original_signal_sha256=record["original_signal_sha256"],
            original_body_sha256=record["original_body_sha256"], publication_date=day, decision=decision,
            reason=record["reason"], evidence_quotes=record["evidence_quotes"], original_terminal_status="published",
            original_model_assessment=record["original_model_assessment"],
            original_model_what_happened=original["what_happened"], original_model_why_it_matters=original["why_it_matters"])
        if record.get("duplicate_of"):
            provenance["duplicate_of"] = record["duplicate_of"]
        expected = dict(original, editorial_review=provenance,
            editorial_decision=decision if decision in {"reject", "group"} else "accept",
            editorial_review_reason=record["reason"], feed_visibility=decision not in {"reject", "group"})
        assessment = record["original_model_assessment"]
        original_assessment = dict(decision="published", relevance_score=original["editorial_relevance"],
                                   threshold=72, analysis_reason=assessment.get("analysis_reason"))
        if assessment != original_assessment or not assessment.get("analysis_reason"):
            fail("editorial_review_original_paid_gate_unverified", url=url)
        if decision == "correct":
            expected.update(record["proposed"], event_status=record["event_status"],
                            prospective_evidence=record["event_status"] in {"proposed", "planned"})
            assessment = dict(decision="published", reason="independent_editorial_copy_corrected",
                relevance_score=original["editorial_relevance"], threshold=72,
                original_model_assessment=record["original_model_assessment"], review_sha256=EDITORIAL_REVIEW_SHA256)
        elif decision in {"reject", "group"}:
            assessment = dict(decision="rejected", reason="independent_editorial_review:" + record["reason"],
                relevance_score=original["editorial_relevance"], threshold=72,
                original_model_assessment=record["original_model_assessment"], review_sha256=EDITORIAL_REVIEW_SHA256)
            if item.get("last_error") != assessment["reason"] or metadata.get("rejection_reason") != assessment["reason"]:
                fail("editorial_review_rejection_reason_changed", url=url)
        if (signal != expected or metadata.get("editorial_review") != provenance
                or metadata.get("editorial_assessment") != assessment
                or metadata.get("what_happened") != expected["what_happened"]
                or metadata.get("why_it_matters") != expected["why_it_matters"]
                or item.get("status") != ("rejected" if decision in {"reject", "group"} else "published")
                or type(item.get("attempts")) is not int or item["attempts"] < 1):
            fail("editorial_review_effective_state_or_provenance_changed", url=url)
        present = [row for row in feed if row.get("source_url") == url and row.get("event_date") == day]
        if decision in {"reject", "group"} and present:
            fail("withdrawn_editorial_publication_still_in_serialized_feed", url=url)
        if decision not in {"reject", "group"} and len(present) != 1:
            fail("reviewed_retained_publication_missing_or_duplicated_in_serialized_feed", url=url)
        if present and any(row.get(key) != expected.get(key) for row in present for key in
                           ("what_happened", "why_it_matters", "publication_date", "editorial_relevance",
                            "evidence_maturity", "category", "editorial_review", "editorial_decision", "feed_visibility", "event_status", "prospective_evidence")):
            fail("editorial_review_serialized_feed_changed", url=url)
        verified[url] = provenance
    return ({} if findings else verified), findings


def explicit_media_attribution(value):
    """Recognize a named report/citation/interview, not a publisher mention.

    The first real process used passive citations and an interview attribution;
    the old publisher-before-report regex rejected those valid statements.
    This says nothing about whether the attributed facts are correct.
    """
    if not isinstance(value, str):
        return False
    publisher = r"(?:pulso(?:\s*/\s*la tercera)?|la tercera)"
    reporting = r"(?:report[aó](?:n|ron)?|inform[aó](?:n|ron)?|public[aó](?:n|ron)?|señal[aó](?:n|ron)?)"
    patterns = (
        r"\bseg[uú]n\s+(?:" + reporting + r"\s+)?" + publisher + r"\b",
        r"\bseg[uú]n\s+(?:la\s+)?(?:nota|reportaje|publicaci[oó]n)\s+de\s+" + publisher + r"\b",
        publisher + r"\s+" + reporting + r"\b",
        r"\b(?:reportad[oa]s?|citad[oa]s?)\s+por\s+" + publisher + r"\b",
        r"\bentrevista\s+con\s+" + publisher + r"\b",
    )
    return any(re.search(pattern, value, re.I) for pattern in patterns)


def normalized_url(value):
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value or "")
    if parsed.scheme != "https" or parsed.netloc not in {"www.latercera.com", "latercera.com"}:
        return None
    return urlunsplit(("https", "www.latercera.com", parsed.path.rstrip("/") + "/", "", ""))


def stamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def publisher_day(value):
    try:
        return date.fromisoformat(value).isoformat() if len(value) == 10 else (
            stamp(value).astimezone(ZoneInfo("America/Santiago")).date().isoformat())
    except (ValueError, TypeError, AttributeError):
        return None


def timestamp_calendar_day(value):
    """Keep the publisher's explicit ISO calendar; never infer a naive zone."""
    if isinstance(value, str) and len(value) == 10:
        return publisher_day(value)
    parsed = stamp(value)
    return parsed.date().isoformat() if parsed else None


def date_convention(values, visible_day):
    """All primary timestamps must corroborate one calendar convention."""
    if not values or not visible_day:
        return None
    calendar = [timestamp_calendar_day(value) for value in values]
    santiago = [publisher_day(value) for value in values]
    calendar_matches = all(day == visible_day for day in calendar)
    santiago_matches = all(day == visible_day for day in santiago)
    return ("calendar_agreement" if calendar_matches and santiago_matches else
            "timestamp_calendar" if calendar_matches else "america_santiago" if santiago_matches else None)


def visible_byline_day(text):
    months = {name: index for index, name in enumerate((
        "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
        "septiembre", "octubre", "noviembre", "diciembre"), 1)}
    match = re.fullmatch(r"\s*(\d{1,2})\s+(?:de\s+)?(" + "|".join(months) +
                         r")\s+(?:de\s+)?(\d{4})\s*", text.casefold())
    try:
        return date(int(match[3]), months[match[2]], int(match[1])).isoformat() if match else None
    except ValueError:
        return None


def queue_timestamp_corroborates(metadata, day):
    values = [entry.get("timestamp") for entry in metadata.get("publication_evidence", [])
              if isinstance(entry, dict)] or [metadata.get("publication_timestamp")]
    if metadata.get("publication_date_source") == "visible_article_byline":
        return (metadata.get("visible_publication_date") == day and
                date_convention(values, day) is not None)
    return all(publisher_day(value) == day for value in values)


def section_slug(value):
    if not isinstance(value, str):
        return None
    text = "".join(character for character in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


class PrimaryDates(HTMLParser):
    """Independent URL/date projection, without importing the source parser."""
    def __init__(self):
        super().__init__()
        self.canonical, self.published, self.nodes, self.parts = None, [], [], None
        self.article_depth, self.article_text, self.title_text = 0, [], []
        self.in_title, self.blocked = False, 0
        self.contexts, self.bylines, self.byline = [], [], None
        self.paragraph, self.primary_paragraphs, self.body_contexts = None, [], []
        self.commercial_contexts, self.commercial_regions, self.commercial_body_text = [], 0, []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        classes = attr.get("class", "").split()
        blocked_context = (self.contexts[-1][1] if self.contexts else False) or tag in {
            "nav", "aside", "footer", "script", "style", "noscript"} or any(
            term in attr.get("class", "") for term in ("latest-news", "related", "story-card"))
        if tag not in {"meta", "link", "br", "hr", "img", "input", "source", "area", "base", "wbr", "embed", "param", "track", "col"}:
            self.contexts.append((tag, blocked_context))
            region = "article-right-rail__body" in classes
            self.commercial_regions += int(region)
            previous = self.commercial_contexts[-1] if self.commercial_contexts else (None, False, False)
            wrapper = previous[2] or blocked_context or tag == "svg" or any(
                label.startswith(("article-body__byline", "article-body__social", "article-body__tags",
                                  "article-body__figure", "coral__")) for label in classes)
            self.commercial_contexts.append((tag, previous[1] or region, wrapper))
            parent_body = self.body_contexts[-1][1] if self.body_contexts else False
            body = parent_body or tag == "article" or attr.get("itemprop") == "articleBody" or (
                tag == "p" and "article-body__paragraph" in classes) or any(
                term in attr.get("class", "") for term in ("article-body__raw-html", "article-body__content", "body-chain", "article__body"))
            self.body_contexts.append((tag, body))
            if tag == "p" and body and not blocked_context:
                self.paragraph = []
        if (tag == "time" and "article-body__byline__date" in classes and not blocked_context
                and self.title_text and attr.get("itemprop") != "dateModified"):
            self.byline = dict(timestamp=attr.get("datetime"), text=[])
        if tag == "link" and "canonical" in attr.get("rel", "").split():
            self.canonical = normalized_url(attr.get("href"))
        if tag == "meta" and (attr.get("property") or attr.get("name")) == "article:published_time":
            self.published.append(attr.get("content"))
        if tag == "script" and attr.get("type") == "application/ld+json":
            self.parts = []
        if tag in {"script", "style", "noscript"}:
            self.blocked += 1
        if tag == "article":
            self.article_depth += 1
        if tag == "h1":
            self.in_title = True

    def handle_data(self, data):
        if self.parts is not None:
            self.parts.append(data)
        if not self.blocked and self.article_depth:
            self.article_text.append(data)
        if not self.blocked and self.in_title:
            self.title_text.append(data)
        if self.byline is not None and not self.blocked:
            self.byline["text"].append(data)
        if self.paragraph is not None and not self.blocked and not (self.contexts and self.contexts[-1][1]):
            self.paragraph.append(data)
        if self.commercial_contexts and self.commercial_contexts[-1][1] and not self.commercial_contexts[-1][2] and data.strip():
            self.commercial_body_text.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.parts is not None:
            try:
                self.nodes.extend(self.walk(json.loads("".join(self.parts))))
            except (ValueError, TypeError):
                pass
            self.parts = None
        if tag in {"script", "style", "noscript"}:
            self.blocked = max(0, self.blocked - 1)
        if tag == "article":
            self.article_depth = max(0, self.article_depth - 1)
        if tag == "h1":
            self.in_title = False
        if tag == "time" and self.byline is not None:
            self.bylines.append(dict(timestamp=self.byline["timestamp"], text=" ".join(self.byline["text"])))
            self.byline = None
        if tag == "p" and self.paragraph is not None:
            # Inline emphasis/links split HTMLParser data callbacks. Preserve
            # the rendered text before normalizing spaces; joining callbacks
            # with spaces would invent "M inisterio" or "Pizarro ,".
            self.primary_paragraphs.append(" ".join("".join(self.paragraph).split()))
            self.paragraph = None
        for index in range(len(self.contexts) - 1, -1, -1):
            if self.contexts[index][0] == tag:
                del self.contexts[index:]
                break
        for index in range(len(self.body_contexts) - 1, -1, -1):
            if self.body_contexts[index][0] == tag:
                del self.body_contexts[index:]
                break
        for index in range(len(self.commercial_contexts) - 1, -1, -1):
            if self.commercial_contexts[index][0] == tag:
                del self.commercial_contexts[index:]
                break

    @classmethod
    def walk(cls, node):
        if isinstance(node, list):
            return [value for child in node for value in cls.walk(child)]
        if not isinstance(node, dict):
            return []
        return [node] + cls.walk(node.get("@graph", []))

    def publication_evidence_for(self, url):
        dates = list(self.published) if self.canonical == url else []
        for node in self.nodes:
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            entity = node.get("mainEntityOfPage")
            entity = entity.get("@id") if isinstance(entity, dict) else entity
            identities = (node.get("url"), node.get("@id"), entity)
            if "NewsArticle" in types and any(normalized_url(value) == url for value in identities if isinstance(value, str)):
                dates.append(node.get("datePublished"))
        if self.canonical == url and self.bylines:
            visible = {visible_byline_day(value["text"]) for value in self.bylines}
            if None in visible or len(visible) != 1:
                return dict(reason="ambiguous_or_invalid_primary_visible_byline")
            day = visible.pop()
            # Publisher originals can expose a byline datetime a few minutes
            # after their datePublished while corroborating the same calendar
            # day. Preserve the two instants; verification here establishes
            # the publication day, never their equality or an invented time.
            instants = {stamp(value) for value in dates if stamp(value)}
            if any(not stamp(value["timestamp"]) for value in self.bylines):
                return dict(reason="primary_byline_timestamp_invalid")
            convention = date_convention(dates + [value["timestamp"] for value in self.bylines], day)
            if not convention:
                return dict(reason="visible_byline_not_consistent_with_one_timestamp_convention")
            return dict(publication_date=day, publisher_date_convention=convention,
                        visible_bylines=self.bylines, primary_timestamps=dates,
                        primary_byline_instants_match_metadata=all(stamp(value["timestamp"]) in instants for value in self.bylines))
        days = {publisher_day(value) for value in dates if publisher_day(value)}
        if len(days) == 1:
            return dict(publication_date=days.pop(), publisher_date_convention="america_santiago_metadata_only",
                        primary_timestamps=dates)
        return dict(reason="missing_or_conflicting_url_bound_primary_timestamps")

    def days_for(self, url):
        day = self.publication_evidence_for(url).get("publication_date")
        return {day} if day else set()

    def primary_text(self, url):
        for node in self.nodes:
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if "NewsArticle" in types and normalized_url(node.get("url") or node.get("@id")) == url:
                body, title = node.get("articleBody"), node.get("headline")
                if isinstance(body, str) and len(body.strip()) >= 160 and isinstance(title, str):
                    return title, body
        if self.canonical == url:
            return " ".join(self.title_text), " ".join(self.article_text)
        return "", ""

    def bound_nodes(self, url, required_type):
        result = []
        for node in self.nodes:
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            entity = node.get("mainEntityOfPage")
            entity = entity.get("@id") if isinstance(entity, dict) else entity
            if required_type in types and any(normalized_url(value) == url for value in (
                    node.get("url"), node.get("@id"), entity) if isinstance(value, str)):
                result.append(node)
        return result

    def strict_original_projection(self, url, *, unresolved_date_conflict=False):
        """Expose publisher facts even when no publication day can be adopted."""
        articles = self.bound_nodes(url, "NewsArticle")
        if self.canonical != url or len(articles) != 1:
            raise ValueError("exception_original_identity_ambiguous_or_unbound")
        article = articles[0]
        values = [article.get("datePublished")] + self.published
        if not values or any(not timestamp_calendar_day(value) or not publisher_day(value) for value in values):
            raise ValueError("exception_original_timestamps_missing_or_invalid")
        visible = {visible_byline_day(value["text"]) for value in self.bylines}
        if not self.bylines or None in visible or len(visible) != 1:
            raise ValueError("exception_original_visible_byline_missing_or_ambiguous")
        if unresolved_date_conflict:
            # The four real originals expose a publisher byline datetime
            # different from their own metadata datePublished. Preserve that
            # contradiction; require the primary time's own displayed day to
            # corroborate its datetime, never a navigation/event timestamp.
            if any(not stamp(value["timestamp"]) or date_convention(
                    [value["timestamp"]], visible_byline_day(value["text"])) is None for value in self.bylines):
                raise ValueError("exception_conflict_primary_byline_datetime_invalid")
        elif not date_convention(values + [value["timestamp"] for value in self.bylines], next(iter(visible))):
            raise ValueError("exception_original_primary_calendars_not_corroborated")
        title = article.get("headline") or " ".join(self.title_text)
        json_body = article.get("articleBody")
        body = " ".join(json_body.split()) if isinstance(json_body, str) and json_body.strip() else " ".join(self.primary_paragraphs)
        if not isinstance(title, str) or not title.strip():
            raise ValueError("exception_original_primary_title_missing")
        return dict(article=article, primary_timestamps=values, visible_publication_date=visible.pop(),
                    title=title, body=body)


def local_capture_path(root, relative):
    path = Path(relative or "")
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("unsafe_capture_path")
    if path.parts[0] == "responses":
        path = Path("data/audits/pulso_runtime_capture") / path
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("unsafe_capture_path")
    return target


def retained_exception_provenance_matches(record, root):
    """Accept named retained manifests only after matching their actual record."""
    provenance = record.get("capture_provenance")
    if provenance == "preserved_original_http_response":
        return SHA.fullmatch(str(record.get("original_capture_manifest_sha256", ""))) is not None
    modes = {
        "preserved_original_cold_core_editorial_or_video_exception": (
            "pulso_editorial_exception_real", "offline_original_editorial_and_video_exception_retention_no_inventory_injection"),
        "preserved_original_cold_core_incomplete_detail": (
            "pulso_thin_primary_real", "exact_offline_retention_of_all_cold_incomplete_detail_originals_no_inventory_injection"),
    }
    if provenance not in modes or not SHA.fullmatch(str(record.get("original_capture_manifest_sha256", ""))):
        return False
    directory, mode = modes[provenance]
    folder = root / "tests/fixtures" / directory
    try:
        manifest = json.loads((folder / "manifest.json").read_text())
        target = local_capture_path(Path(record.get("_capture_root") or root), record.get("gzip_file"))
        if manifest.get("source") != SOURCE or manifest.get("mode") != mode:
            return False
        for original in manifest.get("requests", []):
            if (original.get("original_bytes_verified") is True and original.get("capture_provenance") == provenance
                    and local_capture_path(folder, original.get("gzip_file")) == target
                    and all(original.get(key) == record.get(key) for key in (
                        "url", "status", "sha256", "gzip_sha256", "captured_at", "original_capture_manifest_sha256"))):
                return True
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return False


def original_taxonomy(article, url):
    """Exact publisher labels on one URL-bound article, not incidental prose."""
    keywords = article.get("keywords", [])
    labels = keywords.split(",") if isinstance(keywords, str) else keywords
    labels = [value.strip() for value in labels if isinstance(value, str)] if isinstance(labels, list) else []
    opinion_labels = {"opinión", "opinion", "columna", "columna de opinión", "columna de opinion", "editorial"}
    matched = [value for value in labels if value.casefold() in opinion_labels]
    section = article.get("articleSection")
    section_key = str(section).strip().casefold()
    classification = ("opinion" if matched or section_key in opinion_labels else "sponsored"
                      if section_key in {"branded", "publirreportajes"} and urlsplit(url).path.split("/")[1] == section_key else "factual")
    return dict(source="url_bound_json_ld", canonical_url=url, article_type=article.get("@type"), section=section,
                labels=labels, matched_opinion_labels=matched, classification=classification)


def original_sponsored_empty_text_evidence(html, url, article, parser):
    """Independently inspect the absent body, including the bound ANS story."""
    markers = list(re.finditer(r"\bFusion\.globalContent\s*=\s*", html))
    json_body = article.get("articleBody")
    if (len(markers) != 1 or parser.primary_paragraphs or parser.commercial_regions != 1
            or parser.commercial_body_text
            or json_body is not None and (not isinstance(json_body, str) or json_body.strip())):
        raise ValueError("commercial_primary_text_absence_not_proven")
    story, _ = json.JSONDecoder().raw_decode(html[markers[0].end():])
    elements = story.get("content_elements")
    canonical = normalized_url(urljoin(url, story.get("canonical_url") or ""))
    site = normalized_url(urljoin(url, story.get("websites", {}).get("la-tercera", {}).get("website_url") or ""))
    if (not story.get("canonical_url") or not story.get("websites", {}).get("la-tercera", {}).get("website_url")
            or canonical != url or site != url or story.get("type") != "story"
            or not isinstance(story.get("_id"), str) or not story["_id"]
            or story.get("first_publish_date") != article.get("datePublished")
            or story.get("headlines", {}).get("basic") != article.get("headline")
            or not isinstance(elements, list) or not elements
            or any(not isinstance(entry, dict) or entry.get("type") != "text"
                   or not isinstance(entry.get("content"), str) or entry["content"].strip() for entry in elements)):
        raise ValueError("commercial_empty_fusion_story_identity_or_text_unverified")
    return dict(source="url_bound_json_ld_and_empty_fusion_story", canonical_url=url,
                article_type=article.get("@type"), fusion_story_id=story["_id"],
                fusion_canonical_url=canonical, fusion_first_publish_date=story["first_publish_date"],
                json_article_body_available=False, primary_paragraph_count=0,
                primary_body_region_count=1, primary_body_region_text_characters=0,
                fusion_content_element_count=len(elements), fusion_text_characters=0,
                original_html_sha256=digest(html.encode()))


def verify_primary_capture(row, root, date_evidence=None):
    """Require original bytes matching the primary detail hash and URL/date."""
    url, expected = row["url"], row.get("primary_detail_sha256")
    errors = []
    for record in row.get("original_http_captures", []):
        if record.get("status") != 200 or normalized_url(record.get("url")) != url:
            continue
        if expected not in {record.get("sha256"), record.get("returned_text_utf8_sha256")}:
            continue
        try:
            compressed = local_capture_path(root, record.get("gzip_file")).read_bytes()
            if record.get("gzip_sha256") and digest(compressed) != record["gzip_sha256"]:
                raise ValueError("gzip_sha256_mismatch")
            raw = gzip.decompress(compressed)
            if digest(raw) != record.get("sha256"):
                raise ValueError("original_bytes_sha256_mismatch")
            text = raw.decode(record.get("charset") or "utf-8", errors="replace")
            if digest(text.encode()) != expected:
                raise ValueError("primary_returned_text_sha256_mismatch")
            parser = PrimaryDates()
            parser.feed(text)
            if parser.canonical != url or parser.days_for(url) != {row.get("publication_date")}:
                raise ValueError("independent_primary_url_or_publication_date_mismatch")
            title, body = parser.primary_text(url)
            if len(title.strip()) < 18 or len(body.strip()) < 160:
                raise ValueError("original_primary_title_or_body_missing")
            if row.get("primary_detail_cache_hit"):
                if record.get("capture_provenance") != "preserved_original_http_response":
                    raise ValueError("cached_primary_capture_provenance_missing")
                if not SHA.fullmatch(str(record.get("original_capture_manifest_sha256", ""))):
                    raise ValueError("cached_primary_manifest_sha256_missing")
            if date_evidence is not None:
                date_evidence.update(parser.publication_evidence_for(url), url=url, original_html_sha256=expected)
            return None
        except (OSError, ValueError, TypeError, UnicodeError, EOFError) as error:
            errors.append(type(error).__name__ + ":" + str(error))
    return errors or ["matching_original_primary_capture_missing"]


def verify_publisher_exception(row, metadata, traces, root):
    """Verify a bounded publisher limitation against exact original HTML.

    This cannot excuse transport/parser failures or verify a textual control.
    The returned proof explicitly keeps publication and content availability
    separate; a conflicting original never acquires a convenient date.
    """
    url, expected = row.get("url"), row.get("primary_detail_sha256")
    reason = metadata.get("publisher_exception_reason") or metadata.get("source_content_unavailable_reason")
    errors = []
    if reason not in {VIDEO_HOLD, DATE_HOLD, SPONSORED_HOLD, SPONSORED_TEXT_HOLD}:
        return None, ["unsupported_publisher_exception"]
    article_verified = reason == SPONSORED_HOLD
    if (metadata.get("primary_identity_verified") is not True or metadata.get("article_verified") is not article_verified
            or normalized_url(metadata.get("canonical_url")) != url or metadata.get("html_sha256") != expected
            or not SHA.fullmatch(str(expected or ""))):
        return None, ["exception_queue_identity_or_original_hash_unverified"]
    if not traces or any(trace.get("status") != "discovered_metadata_only" or trace.get("reason") != reason
                          or trace.get("primary_identity_verified") is not True
                          or trace.get("article_verified") is not article_verified
                          or trace.get("html_sha256") != expected for trace in traces):
        return None, ["exception_not_bound_to_actual_core_traces"]
    for record in row.get("original_http_captures", []):
        if (record.get("status") != 200 or normalized_url(record.get("url")) != url
                or expected not in {record.get("sha256"), record.get("returned_text_utf8_sha256")}):
            continue
        try:
            base = Path(record.get("_capture_root") or root)
            compressed = local_capture_path(base, record.get("gzip_file")).read_bytes()
            if record.get("gzip_sha256") and digest(compressed) != record["gzip_sha256"]:
                raise ValueError("exception_original_gzip_hash_mismatch")
            raw = gzip.decompress(compressed)
            text = raw.decode(record.get("charset") or "utf-8", errors="replace")
            if digest(raw) != record.get("sha256") or digest(text.encode()) != expected:
                raise ValueError("exception_original_html_hash_mismatch")
            if row.get("primary_detail_cache_hit") and not retained_exception_provenance_matches(record, root):
                raise ValueError("exception_cached_original_provenance_missing")
            parser = PrimaryDates()
            parser.feed(text)
            projection = parser.strict_original_projection(url, unresolved_date_conflict=reason == DATE_HOLD)
            body, visible = projection["body"], projection["visible_publication_date"]
            values = projection["primary_timestamps"]
            queued_values = [entry.get("timestamp") for entry in metadata.get("publication_evidence", []) if isinstance(entry, dict)]
            if (not queued_values or not set(values) <= set(queued_values)
                    or any(value not in set(values) | {entry["timestamp"] for entry in parser.bylines} for value in queued_values)
                    or metadata.get("visible_publication_date") != visible):
                raise ValueError("exception_original_date_evidence_not_preserved")
            if (metadata.get("page_text") != body or metadata.get("article_body_characters") != len(body)
                    or metadata.get("article_body_sha256") != digest(body.encode())):
                raise ValueError("exception_primary_body_hash_or_text_disagrees")
            convention = date_convention(values + [entry["timestamp"] for entry in parser.bylines], visible)
            taxonomy = original_taxonomy(projection["article"], url)
            if metadata.get("publisher_taxonomy") is not None and (
                    metadata.get("publisher_taxonomy") != taxonomy
                    or metadata.get("publisher_content_classification") != taxonomy["classification"]):
                raise ValueError("exception_publisher_taxonomy_disagrees_with_original")
            if reason == VIDEO_HOLD:
                videos = parser.bound_nodes(url, "VideoObject")
                if (urlsplit(url).path.split("/")[1] != "videos" or len(videos) != 1
                        or normalized_url(videos[0].get("url")) != url or videos[0].get("@id") != url + "#video"
                        or not videos[0].get("embedUrl") or convention is None or len(body.strip()) >= 160):
                    raise ValueError("exception_original_video_identity_date_or_unavailable_text_unverified")
                expected_video = dict(type="VideoObject", url=videos[0].get("url"), id=videos[0].get("@id"),
                                      embed_url=videos[0].get("embedUrl"), upload_date=videos[0].get("uploadDate"))
                if (metadata.get("video_evidence") != expected_video or metadata.get("video_identity_verified") is not True
                        or metadata.get("publisher_document_type") != "video" or metadata.get("article_body_complete") is not False
                        or metadata.get("publication_date_verified") is not True or metadata.get("publication_date") != visible
                        or row.get("publication_date") != visible or row.get("publication_date_verified") is not True
                        or metadata.get("source_quality_gate") != "deferred_video_text"
                        or any(trace.get("publication_date") != visible or trace.get("publication_date_verified") is not True
                               or trace.get("article_body_complete") is not False or trace.get("video_evidence") != expected_video for trace in traces)):
                    raise ValueError("exception_video_claims_do_not_match_original")
                publication_verified, content_verified = True, False
            elif reason == DATE_HOLD:
                possible = sorted({visible} | {timestamp_calendar_day(value) for value in values}
                                  | {publisher_day(value) for value in values})
                if convention is not None or len(body.strip()) < 160:
                    raise ValueError("exception_genuine_primary_date_conflict_not_proven")
                if (metadata.get("publication_date") is not None or metadata.get("publication_timestamp") is not None
                        or metadata.get("publication_date_verified") is not False or metadata.get("article_body_complete") is not True
                        or metadata.get("possible_publication_days") != possible or row.get("publication_date") is not None
                        or row.get("publication_date_verified") is not False
                        or metadata.get("publication_date_source") != "unresolved_primary_publisher_date_conflict"
                        or metadata.get("source_quality_gate") != "deferred_publication_date"
                        or metadata.get("editorial_hold") != DATE_HOLD
                        or any(trace.get("publication_date") is not None or trace.get("publication_date_verified") is not False
                               or trace.get("possible_publication_days") != possible for trace in traces)):
                    raise ValueError("exception_conflict_adopted_date_or_lost_original_days")
                publication_verified, content_verified = False, True
            elif reason == SPONSORED_TEXT_HOLD:
                empty = original_sponsored_empty_text_evidence(text, url, projection["article"], parser)
                saved_empty = metadata.get("sponsored_text_evidence", {})
                if (body != "" or taxonomy["classification"] != "sponsored" or convention is None
                        or metadata.get("publisher_taxonomy") != taxonomy
                        or metadata.get("publisher_content_classification") != "sponsored"
                        or saved_empty != empty or any(type(saved_empty.get(key)) is not int for key in (
                            "primary_paragraph_count", "primary_body_region_count", "primary_body_region_text_characters",
                            "fusion_content_element_count", "fusion_text_characters"))
                        or metadata.get("article_body_complete") is not False
                        or metadata.get("publication_date_verified") is not True or metadata.get("publication_date") != visible
                        or row.get("publication_date") != visible or row.get("publication_date_verified") is not True
                        or metadata.get("publisher_document_type") != "sponsored_without_text"
                        or metadata.get("body_source") != "publisher_sponsored_no_textual_article_body"
                        or metadata.get("source_content_unavailable_reason") != SPONSORED_TEXT_HOLD
                        or metadata.get("publisher_exception_reason") != SPONSORED_TEXT_HOLD
                        or metadata.get("source_quality_gate") != "deferred_sponsored_text"
                        or metadata.get("editorial_hold") != SPONSORED_TEXT_HOLD
                        or any(trace.get("publication_date") != visible or trace.get("publication_date_verified") is not True
                               or trace.get("article_body_complete") is not False or trace.get("sponsored_text_evidence") != empty
                               or trace.get("publisher_taxonomy") != taxonomy for trace in traces)):
                    raise ValueError("commercial_unavailable_body_claim_disagrees_with_original")
                publication_verified, content_verified = True, False
            else:
                if (taxonomy["classification"] != "sponsored" or metadata.get("publisher_taxonomy") != taxonomy
                        or metadata.get("publisher_content_classification") != "sponsored" or convention is None
                        or len(body.strip()) < 160 or metadata.get("article_body_complete") is not True
                        or metadata.get("publication_date_verified") is not True or metadata.get("publication_date") != visible
                        or row.get("publication_date") != visible or row.get("publication_date_verified") is not True
                        or metadata.get("source_quality_gate") != "deferred_sponsored_content_review"
                        or metadata.get("editorial_hold") != SPONSORED_HOLD
                        or any(trace.get("publication_date") != visible or trace.get("publication_date_verified") is not True
                               or trace.get("article_body_complete") is not True or trace.get("publisher_taxonomy") != taxonomy
                               or trace.get("publisher_content_classification") != "sponsored" for trace in traces)):
                    raise ValueError("exception_sponsored_hold_not_bound_to_original_commercial_section")
                publication_verified, content_verified = True, True
            return dict(url=url, reason=reason, original_html_sha256=expected,
                        publication_date_verified=publication_verified, article_content_verified=content_verified,
                        publication_date=visible if publication_verified else None,
                        visible_publication_date=visible, original_primary_timestamps=values,
                        original_primary_bylines=parser.bylines,
                        publisher_date_convention=convention, body_characters=len(body)), None
        except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, EOFError) as error:
            errors.append(type(error).__name__ + ":" + str(error))
    return None, errors or ["matching_original_publisher_exception_capture_missing"]


def budget_delta(execution):
    delta = {}
    try:
        for tier in ("fast", "deep"):
            delta[tier] = {}
            for metric in ("attempted", "successful", "failed"):
                values = []
                for scope in ("run", "month"):
                    before = execution["budget_before"][scope][tier][metric]
                    after = execution["budget_after"][scope][tier][metric]
                    if type(before) is not int or type(after) is not int or before < 0 or after < before:
                        raise ValueError("ledger_counter_decreased_or_invalid")
                    values.append(after - before)
                if values[0] != values[1]:
                    raise ValueError("run_and_month_delta_disagree")
                delta[tier][metric] = values[0]
            if delta[tier]["attempted"] != delta[tier]["successful"] + delta[tier]["failed"]:
                raise ValueError("attempts_without_recorded_results")
        return delta, None
    except (KeyError, TypeError, ValueError) as error:
        return delta, str(error)


def workflow_limits(path):
    text = path.read_text()
    return dict(re.findall(r"^\s+(RADAR_(?:FAST|DEEP)_PER_(?:RUN|MONTH)):\s*(\d+)\s*$", text, re.M))


def api_page_key(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "www.latercera.com":
            return None
        query = json.loads(parse_qs(parsed.query)["query"][0])
        if parsed.path.endswith("/story-feed-sections-fetch"):
            feed = "section:" + query["includeSections"].lstrip("/")
        elif parsed.path.endswith("/story-feed-tag-fetch"):
            feed = "tag:" + query["tagSlug"]
        else:
            return None
        return feed, query["feedOffset"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def factual_api_urls(entries):
    urls = []
    for entry in entries:
        site = entry.get("websites", {}).get("la-tercera", {})
        candidate = site.get("website_url") or entry.get("website_url") or entry.get("canonical_url")
        url = normalized_url(urljoin("https://www.latercera.com/", candidate)) if isinstance(candidate, str) else None
        if not url:
            continue
        path = urlsplit(url).path
        if re.fullmatch(r"/[a-z0-9-]+/noticia/[^/]+(?:/[A-Za-z0-9]{26})?/", path) and path.split("/")[1] not in {
                "opinion", "editorial", "columnas", "cartas-al-director"}:
            urls.append(url)
    return urls


def api_capture_index(records):
    """Index a complete capture once; large real inventories are not samples."""
    if isinstance(records, dict):
        return records
    index = {}
    for record in records:
        key = api_page_key(record.get("url", ""))
        if key:
            index.setdefault(key, []).append(record)
    return index


def verify_api_pages(pages, records, root, details=()):
    """HTTP hashes for the cursor chain; original JSON for first/boundary pages."""
    failures = []
    indexed = api_capture_index(records)
    proof_offsets = {row.get("offset") for row in pages[:1] + pages[-3:]}
    for index, page in enumerate(pages):
        key = (page.get("feed"), page.get("offset"))
        if not SHA.fullmatch(str(page.get("json_sha256", ""))):
            failures.append(dict(code="public_api_page_hash_missing", offset=page.get("offset")))
            continue
        candidates = [record for record in indexed.get(key, []) if record.get("status") == 200
                      and page.get("json_sha256") in {record.get("sha256"), record.get("returned_text_utf8_sha256")}
                      and stamp(record.get("captured_at"))]
        if not candidates:
            failures.append(dict(code="public_api_http_chain_unproven", offset=page.get("offset")))
            continue
        if index and (pages[index - 1].get("next") != page.get("offset") or page.get("offset", -1) <= pages[index - 1].get("offset", -1)):
            failures.append(dict(code="public_api_cursor_chain_nonadvancing", offset=page.get("offset")))
        if page.get("offset") not in proof_offsets:
            continue
        verified = False
        for record in candidates:
            try:
                base = Path(record.get("_capture_root") or root)
                relative = Path(record.get("gzip_file") or "")
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("unsafe_capture_path")
                path = (base / relative).resolve()
                if not path.is_relative_to(base.resolve()):
                    raise ValueError("unsafe_capture_path")
                compressed = path.read_bytes()
                raw = gzip.decompress(compressed)
                text = raw.decode(record.get("charset") or "utf-8", errors="replace")
                if digest(raw) != record.get("sha256") or digest(text.encode()) != page.get("json_sha256"):
                    raise ValueError("raw_api_sha256_mismatch")
                if record.get("gzip_sha256") and digest(compressed) != record["gzip_sha256"]:
                    raise ValueError("raw_api_gzip_sha256_mismatch")
                document = json.loads(text)
                document = document.get("data", document)
                entries = document["content_elements"]
                if (not isinstance(entries, list) or len(entries) != page.get("primary_entries")
                        or document.get("count") != page.get("count") or document.get("next") != page.get("next")):
                    raise ValueError("raw_api_inventory_or_cursor_disagrees")
                days = [publisher_day(entry.get("first_publish_date")) for entry in entries]
                if page.get("inventory_day_max") and (None in days or max(days) != page["inventory_day_max"]):
                    raise ValueError("raw_api_publication_boundary_disagrees")
                if page.get("boundary_pages", 0) > 0:
                    cutoff = (date.fromisoformat(WINDOWS["90"][0]) - timedelta(days=2)).isoformat()
                    urls = factual_api_urls(entries)
                    if page.get("verified_details") != len(urls):
                        failures.append(dict(code="public_api_boundary_factual_details_incomplete", offset=page.get("offset")))
                    for url in urls:
                        traces = [row for row in details if normalized_url(row.get("url")) == url
                                  and row.get("status") in {"discovered", "discovered_metadata_only", "excluded"}]
                        if (not traces or any(row.get("publication_date_source") not in PRIMARY_DATE_SOURCES
                                              or row.get("publication_date_verified") is False
                                              or not SHA.fullmatch(str(row.get("html_sha256", "")))
                                              or not publisher_day(row.get("publication_date")) for row in traces)):
                            failures.append(dict(code="public_api_boundary_original_detail_date_unverified", offset=page.get("offset"), url=url))
                        elif len({row["publication_date"] for row in traces}) != 1 or traces[0]["publication_date"] >= cutoff:
                            failures.append(dict(code="public_api_boundary_detail_dates_not_old", offset=page.get("offset"), url=url))
                verified = True
                break
            except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, EOFError):
                continue
        if not verified:
            failures.append(dict(code="public_api_original_boundary_json_missing_or_invalid", offset=page.get("offset")))
    return failures


def capture_records(root, artifact=None):
    """Read live, retained or downloaded original proof without restoring state."""
    paths = [root / "data/audits/pulso_runtime_capture/manifest.json"] + [
        root / "tests/fixtures" / directory / "manifest.json" for directory in (
            "pulso_runtime_real", "pulso_editorial_exception_real", "pulso_thin_primary_real", "pulso_targeted_primary_real")]
    if artifact and artifact.exists():
        paths.extend(artifact.rglob("manifest.json"))
    records = []
    for path in paths:
        if not path.exists():
            continue
        value = json.loads(path.read_text())
        if value.get("source") == SOURCE:
            records.extend(dict(record, _capture_root=str(path.parent)) for record in value.get("requests", []))
    return records


def count_exhaustion_proven(summary, pages):
    """An exact, stable publisher total must bound a gap-free position traversal.

    A small invented summary total cannot override the original API count.
    Moving counts, gaps, overlaps or a capped total require another traversal;
    reaching an offset greater than the summary is not proof of exhaustion.
    Original first/last JSON counts are separately bound by verify_api_pages.
    """
    total = summary.get("publisher_count")
    if type(total) is not int or not 0 <= total < 10000 or not pages:
        return False
    expected_offset = 0
    for page in pages:
        entries, offset, count = page.get("primary_entries"), page.get("offset"), page.get("count")
        if (type(entries) is not int or not 0 <= entries <= 24
                or type(offset) is not int or offset != expected_offset
                or type(count) is not int or count != total):
            return False
        expected_offset += entries
        if expected_offset > total:
            return False
    return expected_offset == total


def verify_processing_selection(report, discovery, queue, root, enumerated):
    """A focused run must intersect the immutable body-reviewed core cohort.

    Selection changes processing membership, never discovery or an editorial
    verdict. Queue snapshots independently expose attempts outside the cohort.
    """
    execution = report.get("last_core_execution") or report.get("execution", {})
    selected = execution.get("processing_selection")
    recorded = discovery.get("processing_selection")
    if not selected and not recorded:
        return {}, []
    findings, checks = [], {}
    def fail(code, **evidence):
        findings.append(dict(domain="processing", code=code, **evidence))
    if not isinstance(selected, dict) or selected != recorded:
        fail("processing_selection_not_bound_to_actual_core")
        return checks, findings
    if selected.get("validation_error") or selected.get("reason") != "explicit_queue_selection":
        fail("processing_selection_validation_failed", error=selected.get("validation_error"))
    try:
        path = root / PROCESSING_COHORT_PATH
        raw = path.read_bytes()
        if digest(raw) != PROCESSING_COHORT_SHA256:
            raise ValueError("immutable_processing_cohort_hash_mismatch")
        cohort = json.loads(raw)
        urls = cohort["urls"]
        items = {item["url"]: item for item in cohort["items"]}
        if (len(urls) != 113 or len(set(urls)) != 113 or set(urls) != set(items)
                or cohort.get("source") != SOURCE
                or any(normalized_url(url) != url for url in urls)):
            raise ValueError("immutable_processing_cohort_identity_invalid")
        # The immutable file cites complete independent reviews, including
        # negative/uncertain cases; none supplies a publication decision.
        referenced = {}
        for key in ("frozen_control", "independent_primary_review", "expanded_negative_review"):
            reference = cohort["inputs"][key]
            content = local_capture_path(root, reference["path"]).read_bytes()
            if digest(content) != reference["sha256"]:
                raise ValueError("processing_cohort_independent_reference_changed:" + key)
            referenced[key] = json.loads(content)
        if cohort["inputs"]["frozen_control"]["sha256"] != FROZEN_CONTROL_SHA256:
            raise ValueError("processing_cohort_control_not_frozen")
        primary = {item["url"] for item in referenced["independent_primary_review"]["all_controls"]}
        negatives = referenced["expanded_negative_review"]["all_287_initial_negative_full_body_semantic_reviews"]
        material = {item["url"] for item in negatives if item["independent_review_decision"] == "concrete_false_negative_for_editorial_analysis"}
        uncertain = {item["url"] for item in negatives if item["independent_review_decision"] == "uncertain_requires_editorial_review"}
        if len(primary) != 79 or len(material) != 20 or len(uncertain) != 17 or set(urls) != primary | material | uncertain:
            raise ValueError("processing_cohort_independent_groups_changed")
    except (OSError, ValueError, KeyError, TypeError) as error:
        fail("processing_selection_immutable_cohort_unverified", error=str(error))
        return checks, findings
    if (selected.get("source") != SOURCE or selected.get("sha256") != PROCESSING_COHORT_SHA256
            or selected.get("file_sha256") != PROCESSING_COHORT_SHA256
            or selected.get("selected_urls") != urls
            or type(selected.get("selected_url_count")) is not int or selected["selected_url_count"] != 113
            or type(selected.get("matched_existing_url_count")) is not int or selected["matched_existing_url_count"] != 113):
        fail("processing_selection_recorded_manifest_mismatch")
    if not set(urls) <= enumerated:
        fail("processing_selection_urls_not_returned_by_current_core", missing=sorted(set(urls) - enumerated))
    current = {}
    for key, item in queue.items():
        if item.get("source") == SOURCE:
            current.setdefault(normalized_url(item.get("raw", {}).get("url")), []).append((key, item))
    baseline = {item["url"]: item for item in report.get("baseline_queue", [])}
    for url in urls:
        matches = current.get(url, [])
        if len(matches) != 1 or matches[0][0] != items[url]["queue_fingerprint"]:
            fail("processing_selection_durable_identity_missing_or_ambiguous", url=url)
            continue
        _, item = matches[0]
        raw, original = item.get("raw", {}), items[url]
        metadata = raw.get("metadata", {})
        text = metadata.get("page_text")
        if (not isinstance(text, str) or digest(text.encode()) != original["body_sha256"]
                or len(text) != original["body_characters"]
                or metadata.get("article_body_sha256") != original["body_sha256"]
                or raw.get("event_date") != original["publication_date"]):
            fail("processing_selection_reviewed_original_body_or_day_changed", url=url)
    partition = []
    for key in ("ready_selected_urls", "skipped_terminal_urls", "skipped_not_due_urls", "skipped_in_progress_urls"):
        values = selected.get(key)
        if not isinstance(values, list) or any(not isinstance(url, str) for url in values):
            fail("processing_selection_ready_partition_invalid", field=key)
            continue
        partition.extend(values)
    if len(partition) != 113 or len(set(partition)) != 113 or set(partition) != set(urls):
        fail("processing_selection_ready_partition_invalid")
    terminal_urls = selected.get("skipped_terminal_urls")
    for url in terminal_urls if isinstance(terminal_urls, list) else []:
        before = baseline.get(url, {})
        matches = current.get(url, [])
        if (before.get("status") not in {"published", "rejected", "archived"} or len(matches) != 1
                or matches[0][1].get("status") != before.get("status")
                or matches[0][1].get("attempts", 0) != before.get("attempts", 0)):
            fail("processing_selection_terminal_reset_or_skip_unproven", url=url)
    outside_pending = 0
    matrix = {item.get("url"): item for item in report.get("matrix", [])}
    for url, matches in current.items():
        if url in set(urls):
            continue
        for key, item in matches:
            before = baseline.get(url, {})
            if item.get("attempts", 0) != before.get("attempts", 0):
                fail("processing_selection_processed_outside_cohort", url=url)
            if item.get("status") in {"pending", "retry", "processing"}:
                outside_pending += 1
            row = matrix.get(url, {})
            if row.get("exact_reason") == "processing_not_attempted:explicit_queue_selection_excluded":
                proof = row.get("processing_selection_evidence", {})
                if proof != dict(sha256=PROCESSING_COHORT_SHA256, selected=False, source=SOURCE):
                    fail("processing_selection_excluded_reason_without_membership_proof", url=url)
    if (type(selected.get("outside_selection_pending_url_count")) is not int
            or selected["outside_selection_pending_url_count"] != outside_pending
            or selected.get("outside_selection_pending_reason") != "processing_not_attempted:explicit_queue_selection_excluded"):
        fail("processing_selection_outside_pending_count_or_reason_unproven", observed=outside_pending)
    checks.update(sha256=PROCESSING_COHORT_SHA256, selected_urls=113, independent_primary_controls=79,
                  independent_material_cases=20, independent_uncertain_cases=17,
                  outside_pending_preserved=outside_pending, publication_quota=False)
    return checks, findings


def technical_processing_deferral(item, row):
    """Read failed processing evidence independently of a retry label.

    A future retry time or a renamed queue reason does not turn an invalid
    primary identity, failed model proof or unavailable analysis into a settled
    editorial decision. Publisher exceptions are checked separately and do not
    belong to the body-reviewed processing cohort.
    """
    metadata = item.get("raw", {}).get("metadata", {})
    assessment = metadata.get("editorial_assessment") or {}
    validation = metadata.get("pulso_editorial_proof_validation")
    binding = metadata.get("primary_item_binding")
    failures = []
    if isinstance(validation, dict) and validation.get("decision") == "deferred":
        failures.append("pulso_editorial_proof_validation_deferred")
    if isinstance(binding, dict) and binding.get("verified") is False:
        failures.append("primary_item_binding_unverified")
    if metadata.get("analysis_input_complete") is False:
        failures.append("complete_analysis_input_unverified")
    if metadata.get("article_body_complete") is False:
        failures.append("complete_primary_article_body_unverified")
    if item.get("status") in {"pending", "retry", "processing"}:
        technical = {"analysis_unavailable", "article_verification_failed", "budget_or_analysis_deferred",
                     "analysis_complete_primary_body_not_proven", "fast_analysis_capacity_exhausted",
                     "publisher_liveblog_entry_dates_unverified"}
        reasons = (assessment.get("reason"), item.get("reason"), metadata.get("editorial_hold"),
                   row.get("exact_reason"))
        for reason in reasons:
            if isinstance(reason, str) and (reason in technical or reason.startswith(
                    ("pulso_editorial_", "pulso_primary_", "processing_not_attempted:"))):
                failures.append(reason)
    return sorted(set(failures))


def verify_genuine_idempotence(baseline, proof, *, root, report, discovery, queue, history, snapshot, telemetry):
    """A zero-call replay can pass only after bound, genuine paid processing.

    Recompute the helper's observations independently. A status or PASS label
    in a mutable compact JSON is insufficient to exempt the positive-AI check.
    """
    if baseline is None and proof is None:
        return {}, []
    findings = []
    def require(condition, reason):
        if not condition:
            raise ValueError(reason)
    def compact(value):
        if isinstance(value, dict):
            return {key: (({"value_type": "str", "utf8_sha256": digest(item.encode()), "characters": len(item)}
                          if isinstance(item, str) else {"value_type": type(item).__name__, "value": compact(item)})
                          if key in {"page_text", "raw_text"} else compact(item))
                    for key, item in value.items() if key not in {"last_checked_at", "cache_hit"}}
        return [compact(item) for item in value] if isinstance(value, list) else value
    try:
        require(isinstance(baseline, dict) and isinstance(proof, dict), "both_baseline_and_actual_replay_proof_required")
        terminal = baseline.get("mode") == "genuine_terminal_followthrough_processing_baseline"
        composite = terminal or baseline.get("mode") == "genuine_revalidated_processing_baseline"
        require(baseline.get("schema_version") == "pulso_idempotence_v1"
                and baseline.get("mode") in {"genuine_processing_baseline", "genuine_revalidated_processing_baseline",
                                             "genuine_terminal_followthrough_processing_baseline"}
                and baseline.get("read_only") is True,
                "invalid_paid_idempotence_baseline")
        require(baseline.get("payload_sha256") == object_digest({k: v for k, v in baseline.items() if k != "payload_sha256"}),
                "baseline_payload_changed")
        quality = baseline["processing_qa"]
        require(quality.get("phase") == "real_core_processing" and quality.get("requested_phase") == "processing"
                and quality.get("verdict") == "PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW"
                and quality.get("discovery_qa") == quality.get("processing_qa") == "PASS"
                and quality.get("acceptance") == "PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW",
                "genuine_paid_processing_qa_missing")
        paid, current = baseline["baseline_execution"], report.get("last_core_execution") or report["execution"]
        old_delta, error = budget_delta(paid)
        if terminal:
            observed_lineage = verify_terminal_followthrough_execution(root,report=report,queue=queue,
                history=history,snapshot=snapshot,telemetry=telemetry,execution=paid)
            require(baseline.get("terminal_followthrough_provenance") == observed_lineage,
                    "terminal_followthrough_original_and_live9_provenance_changed")
            require(not error and old_delta == baseline.get("terminal_budget_delta")
                    and not any(value for tier in old_delta.values() for value in tier.values())
                    and baseline.get("terminal_successful_response_ids") == [] and paid.get("processing_attempts_increased") == 0
                    and "paid_budget_delta" not in baseline and "paid_successful_response_ids" not in baseline,
                    "terminal_followthrough_current_zero_retagged_as_paid")
            paid_window = observed_lineage["paid_model_lineage"]["original_execution"]
            paid_delta = observed_lineage["paid_model_lineage"]["original_budget_delta"]
            paid_ids = observed_lineage["paid_model_lineage"]["original_successful_response_ids"]
        elif composite:
            observed_lineage = verify_final_revalidated_execution(root, report=report, queue=queue,
                history=history, telemetry=telemetry, execution=paid)
            require(all(baseline.get(key) == observed_lineage[key] for key in
                    ("paid_model_lineage", "launch_stock", "current_revalidation_receipts")),
                    "composite_original_paid_or_real_revalidation_proof_changed")
            require(not error and old_delta == baseline["revalidated_budget_delta"]
                    and not any(value for tier in old_delta.values() for value in tier.values())
                    and baseline.get("revalidated_successful_response_ids") == []
                    and "paid_budget_delta" not in baseline and "paid_successful_response_ids" not in baseline,
                    "composite_revalidation_retagged_as_paid")
            paid_window = observed_lineage["paid_model_lineage"]["original_execution"]
            paid_delta = observed_lineage["paid_model_lineage"]["original_budget_delta"]
            paid_ids = observed_lineage["paid_model_lineage"]["original_successful_response_ids"]
        else:
            require(not error and old_delta == baseline["paid_budget_delta"] and old_delta["fast"]["successful"] > 0,
                    "genuine_positive_paid_ledger_missing")
            paid_window, paid_delta, paid_ids = paid, old_delta, baseline["paid_successful_response_ids"]
        require(quality["checks"].get("actual_ai_budget_delta") == old_delta
                and quality["checks"].get("actual_fast_response_events") == old_delta["fast"]["attempted"]
                and quality["checks"].get("processing_selection", {}).get("sha256") == PROCESSING_COHORT_SHA256
                and quality["checks"]["processing_selection"].get("selected_urls") == 113,
                "paid_qa_not_bound_to_actual_ledger_and_cohort")
        first_start, first_end = stamp(paid.get("started_at")), stamp(paid.get("finished_at"))
        start, end = stamp(current.get("started_at")), stamp(current.get("finished_at"))
        require(paid.get("mode") == "real_core_processing" and paid.get("engine_called") is True
                and paid.get("engine_completed") is True and first_start and first_end and start and end
                and first_start <= first_end < start <= end and paid.get("ai_guardrails_modified") is False,
                "paid_baseline_or_second_core_not_genuine_and_fresh")
        cohort = json.loads((root / PROCESSING_COHORT_PATH).read_bytes())
        require(digest((root / PROCESSING_COHORT_PATH).read_bytes()) == PROCESSING_COHORT_SHA256
                and baseline["selection"].get("sha256") == PROCESSING_COHORT_SHA256
                and baseline["selection"].get("count") == 113 and baseline["selection"].get("urls") == cohort["urls"]
                and paid.get("processing_selection", {}).get("sha256") == PROCESSING_COHORT_SHA256
                and paid["processing_selection"].get("selected_urls") == cohort["urls"],
                "paid_baseline_not_bound_to_immutable_113_core_selection")
        fingerprint = baseline["runtime_fingerprint"]
        files = fingerprint["files"]
        required = {str(path.relative_to(root)) for path in (root / "src/radar_salud").glob("*.py")}
        required.update({"scripts/qa_pulso_recovery.py", "scripts/audit_pulso_runtime.py", "scripts/pulso_idempotence.py",
            "scripts/export_web_snapshot.py", "scripts/retain_pulso_runtime_fixtures.py",
            "scripts/apply_pulso_editorial_review.py", "scripts/pulso_recovery_command.py", "scripts/product_report.py", "pyproject.toml",
            ".github/workflows/daily-radar.yml", ".github/workflows/pulso-runtime-recovery.yml"})
        required.update("config/" + name for name in ("sources.json", "beta_source_configs.json",
            "source_quality_gate.json", "media_early_signal_gate.json", "model_routing_v1.json", "taxonomy_v2.json",
            "editorial_rules_v2.json", "editorial_copy_overrides_v1.json", "editorial_intelligence_committee_v1.json",
            "normative_editorial_v2.json", "pulso_editorial_repair_admission_2026_10_11.json"))
        require(required <= set(files) and object_digest(files) == fingerprint.get("sha256")
                and fingerprint.get("git_or_marker_sha_used") is False
                and all(digest(local_capture_path(root, path).read_bytes()) == sha for path, sha in files.items())
                and paid.get("runtime_fingerprint") == current.get("runtime_fingerprint") == fingerprint
                and re.fullmatch(r"[0-9a-f]{40}", str(paid.get("code_sha", "")))
                and re.fullmatch(r"[0-9a-f]{40}", str(current.get("code_sha", "")))
                and proof.get("runtime_fingerprint") == fingerprint,
                "genuine_paid_and_replay_implementation_or_policy_changed")
        require(proof.get("schema_version") == "pulso_idempotence_v1" and proof.get("mode") == "after_genuine_core"
                and proof.get("verdict") == "PASS" and not proof.get("findings") and proof.get("read_only") is True
                and proof.get("baseline_sha256") == baseline["payload_sha256"], "actual_replay_proof_missing_or_failed")
        delta, error = budget_delta(current)
        require(not error and not any(v for tier in delta.values() for v in tier.values())
                and proof.get("actual_budget_delta") == delta and current.get("processing_attempts_increased") == 0
                and discovery.get("processing_attempts") == 0,
                "actual_replay_consumed_model_budget_or_attempts")
        paid_start, paid_end = stamp(paid_window.get("started_at")), stamp(paid_window.get("finished_at"))
        events = [row for row in telemetry if stamp(row.get("at")) and paid_start <= stamp(row["at"]) <= paid_end]
        ids = [row.get("response_id") for row in events if row.get("success") is True]
        require(ids == paid_ids and all(isinstance(value, str) and value for value in ids)
                and len(set(ids)) == len(ids), "baseline_paid_response_ids_not_in_actual_telemetry")
        for tier in ("fast", "deep"):
            tier_events = [row for row in events if row.get("kind") == tier]
            require(len(tier_events) == paid_delta[tier]["attempted"]
                    and sum(row.get("success") is True for row in tier_events) == paid_delta[tier]["successful"],
                    "baseline_paid_telemetry_ledger_mismatch")
        old = baseline["semantic"]
        if composite:
            require({key: object_digest(item) for key,item in queue.items() if item.get("source") != SOURCE}
                    == old["native_queue"], "replay_changed_native_connector_queue")
        require([object_digest(row) for row in telemetry] == old["response_event_sha256s"]
                and [row.get("response_id") for row in telemetry if row.get("success") is True] == old["actual_response_ids"],
                "replay_response_events_changed")
        require(idempotence_signal_hashes(history) == old["history"]
                and idempotence_signal_hashes(snapshot.get("signals", [])) == old["feed"],
                "replay_changed_effective_history_or_serialized_feed")
        ledgers = {path.name: json.loads(path.read_bytes()) for path in (root / "data/ai_usage").glob("????-??.json")}
        require(ledgers == old["ledgers"] and ledgers[first_end.strftime("%Y-%m") + ".json"] == paid["budget_after"]["month"],
                "replay_monthly_paid_ledger_changed")
        current_queue = {}
        for key, item in queue.items():
            if item.get("source") != SOURCE:
                continue
            url = item.get("raw", {}).get("url")
            require(url not in current_queue, "duplicate_source_queue_identity")
            metadata = item.get("raw", {}).get("metadata", {})
            current_queue[url] = dict(fingerprint=key, status=item.get("status"), attempts=item.get("attempts", 0),
                semantic_sha256=object_digest(terminal_source_inventory_semantic(item) if terminal else compact(item)), retry_at=item.get("retry_at"),
                publication_date=item.get("raw", {}).get("event_date"), lane=item.get("lane"), reason=item.get("reason"),
                assessment=metadata.get("editorial_assessment"), editorial_hold=metadata.get("editorial_hold"),
                body_sha256=metadata.get("article_body_sha256"), body_characters=metadata.get("article_body_characters"),
                source_quality_gate=metadata.get("source_quality_gate"),
                editorial_proof_validation=metadata.get("pulso_editorial_proof_validation"),
                primary_item_binding=metadata.get("primary_item_binding"),
                analysis_input_complete=metadata.get("analysis_input_complete"),
                article_body_complete=metadata.get("article_body_complete"),
                editorial_review_sha256=object_digest(metadata["editorial_review"]) if metadata.get("editorial_review") else None)
            if url in cohort["urls"]:
                require(not technical_processing_deferral(item, {}), "replay_selected_processing_evidence_unresolved")
        require(all(current_queue.get(url) == item for url, item in old["source_queue"].items()),
                "replay_changed_existing_queue_state_or_original_proof")
        primary = {}
        for row in report.get("matrix", []):
            if row.get("current_core_detected"):
                primary[row["url"]] = dict(publication_date=row.get("publication_date"),
                    publication_date_verified=row.get("publication_date_verified"),
                    current_core_verified_health=row.get("current_core_verified_health"),
                    metadata_only_candidate=row.get("metadata_only_candidate"),
                    publisher_exception_reason=row.get("publisher_exception_reason"),
                    body_sha256s=sorted({trace["article_body_sha256"] for trace in row.get("current_discovery_trace", [])
                                        if trace.get("article_body_sha256")}))
        require(primary and all(primary.get(url) == row for url, row in old["source_primary"].items()),
                "replay_changed_existing_primary_dates_or_content_coverage")
        references = {cohort["inputs"][key]["path"] for key in
                      ("frozen_control", "independent_primary_review", "expanded_negative_review")}
        reviews = [row.get("editorial_review", {}) for row in history]
        reviews.extend(item.get("raw", {}).get("metadata", {}).get("editorial_review", {}) for item in queue.values())
        references.update(row["review_file"] for row in reviews if isinstance(row, dict) and isinstance(row.get("review_file"), str))
        if local_capture_path(root, EDITORIAL_REGISTRY_PATH).exists():
            references.add(EDITORIAL_REGISTRY_PATH)
            registry = json.loads(local_capture_path(root, EDITORIAL_REGISTRY_PATH).read_bytes())
            for entry in registry["reviews"]:
                for path_key, sha_key in (("review_file", "review_sha256"),
                                          ("independent_review_file", "independent_review_sha256")):
                    require(digest(local_capture_path(root, entry[path_key]).read_bytes()) == entry[sha_key],
                            "replay_registered_editorial_dual_reader_changed")
                    references.add(entry[path_key])
        for item in queue.values():
            if item.get("source") == SOURCE and verify_incremental_addendum_reference(item.get("raw", {}), root):
                references.add(INCREMENTAL_ADDENDUM_PATH)
            review = item.get("raw", {}).get("metadata", {}).get("incremental_review")
            if item.get("source") != SOURCE or not isinstance(review, dict):
                continue
            require(review.get("review_ref") == INCREMENTAL_REVIEW_PATH
                    and review.get("review_sha256") == INCREMENTAL_REVIEW_SHA256
                    and digest(local_capture_path(root, INCREMENTAL_REVIEW_PATH).read_bytes()) == INCREMENTAL_REVIEW_SHA256,
                    "replay_incremental_review_reference_unverified")
            references.add(INCREMENTAL_REVIEW_PATH)
        references.update(paid_revalidation_proof_files(root))
        references.update(current_paid_proof_files(root))
        references.update(followup_paid_proof_files(root))
        references.update(final_paid_proof_files(root))
        if terminal:
            references.update(terminal_live9_proof_files(root))
        require({path: digest(local_capture_path(root, path).read_bytes()) for path in references} == old["referenced_proof_files"],
                "replay_changed_independent_body_reviews_or_editorial_provenance")
        require(not old.get("reviewed_hold_bindings"), "reviewed_duplicate_hold_requires_independent_target_validation")
        added = set(current_queue) - set(old["source_queue"])
        require(not added & set(cohort["urls"]) and all(current_queue[url]["attempts"] == 0
                and current_queue[url]["status"] in {"pending", "archived"} for url in added),
                "replay_processed_new_unselected_discovery")
        selected = current.get("processing_selection", {})
        require(selected == discovery.get("processing_selection") and not selected.get("ready_selected_urls")
                and not selected.get("skipped_in_progress_urls"), "actual_terminal_skip_not_proven")
        require(proof.get("selected_partition") == dict(terminal_urls=sorted(selected["skipped_terminal_urls"]),
                held_not_due_urls=sorted(selected["skipped_not_due_urls"])), "actual_replay_partition_mismatch")
        observed = proof["observed_files"]
        required_observations = {"data/audits/pulso_runtime_2026_10_11.json", "data/state/discovery_run.json",
            "data/state/pending_queue.json", "data/history/superintendencia_signals.json", "web/data/radar_today.json",
            "data/ai_usage/responses.jsonl", PROCESSING_COHORT_PATH}
        require(required_observations <= set(observed) and all(
            digest(local_capture_path(root, path).read_bytes()) == observed[path] for path in required_observations),
            "actual_replay_file_bytes_not_bound")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        findings.append(dict(domain="processing", code="genuine_idempotent_replay_not_verified", reason=str(error)))
        return {}, findings
    return dict(baseline_sha256=baseline["payload_sha256"], paid_successful_response_ids=len(ids), selected_urls=113,
                actual_attempts=0, actual_ai_calls=0, unchanged_history_and_feed=True,
                unchanged_existing_queue=True, additional_unselected_discovery=len(added)), []


def evaluate(report, control, *, root, discovery, queue, history, snapshot, telemetry=(), control_sha=None, captures=(), phase="auto",
             idempotence_baseline=None, idempotence_proof=None):
    findings, checks = [], {}
    def fail(domain, code, **evidence):
        findings.append(dict(domain=domain, code=code, **evidence))
    execution = report.get("last_core_execution") or report.get("execution", {})
    mode = execution.get("mode")
    actual_processing = mode == "real_core_processing"
    processing = actual_processing and phase != "discovery"
    if mode not in {"discovery_only", "real_core_processing"}:
        fail("discovery", "genuine_core_execution_missing", mode=mode)
    if phase == "processing" and not actual_processing:
        fail("processing", "requested_processing_has_no_actual_processing_execution")
    if not execution.get("engine_called") or not execution.get("engine_completed"):
        fail("discovery", "core_did_not_complete", error=execution.get("error_type"))
    start, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    discovered_at = stamp(report.get("discovery_run_at"))
    if not start or not end or end < start or not discovered_at or not start <= discovered_at <= end:
        fail("discovery", "stale_or_unbound_discovery_timestamp")
    if report.get("runtime") != "daily_core" or report.get("selected_sources") != [SOURCE] or not report.get("core_source_present"):
        fail("discovery", "real_source_scoped_core_missing")
    if report.get("audit_discovery_error"):
        fail("discovery", "audit_discovery_error", error=report["audit_discovery_error"])
    if report.get("unrelated_queue_unchanged") is not True:
        fail("discovery", "other_source_queue_changed_or_unproven")
    if execution.get("ai_guardrails_modified") is not False:
        fail("discovery", "ai_guardrails_preservation_unproven")
    try:
        daily = workflow_limits(root / ".github/workflows/daily-radar.yml")
        recovery = workflow_limits(root / ".github/workflows/pulso-runtime-recovery.yml")
        if len(daily) != 4 or daily != recovery:
            fail("discovery", "recovery_budget_limits_differ_from_daily_core", daily=daily, recovery=recovery)
    except OSError as error:
        fail("discovery", "budget_workflow_evidence_missing", error=str(error))
    delta, error = budget_delta(execution)
    checks["actual_ai_budget_delta"] = delta
    if error:
        fail("discovery", "ai_ledger_invalid", error=error)
    elif not actual_processing and any(value for tier in delta.values() for value in tier.values()):
        fail("discovery", "discovery_consumed_analysis_budget")
    if control_sha != FROZEN_CONTROL_SHA256:
        fail("discovery", "independent_control_identity_not_frozen", expected_sha256=FROZEN_CONTROL_SHA256, observed_sha256=control_sha)
    if report.get("external_control_sha256") != control_sha:
        fail("discovery", "frozen_control_hash_mismatch")
    controls = {normalized_url(row.get("url")): row for row in control.get("articles", [])}
    rows = {row.get("url"): row for row in report.get("matrix", [])}
    details = discovery.get("source_details", {}).get(SOURCE, [])
    text_candidates = {normalized_url(row.get("url")) for row in details if row.get("status") == "discovered"}
    metadata_candidates = {normalized_url(row.get("url")) for row in details if row.get("status") == "discovered_metadata_only"}
    source_result = discovery.get("sources", {}).get(SOURCE)
    source_error = (source_result or {}).get("error_type")
    returned_to_core = source_result is not None and source_error in (None, "partial_discovery")
    actual = text_candidates if returned_to_core else set()
    metadata_only = metadata_candidates if returned_to_core else set()
    checks["core_inventory_registration"] = dict(returned_to_core=returned_to_core,
        text_candidate_trace_urls=len(text_candidates), metadata_candidate_trace_urls=len(metadata_candidates),
        source_discovered=(source_result or {}).get("discovered"), source_error_type=source_error)
    if source_error or not returned_to_core or report.get("source_inventory_returned_to_core") is False:
        fail("discovery", "core_source_error_or_inventory_not_registered", source_error_type=source_error)
    if returned_to_core and ((source_result or {}).get("discovered") != len(actual | metadata_only)
                            or type((source_result or {}).get("discovered")) is not int):
        fail("discovery", "source_returned_inventory_count_not_supported_by_traces")
    if None in actual | metadata_only or actual & metadata_only:
        fail("discovery", "core_inventory_identity_or_text_metadata_partition_invalid")
    enumerated = actual | metadata_only
    if processing:
        selection_checks, selection_findings = verify_processing_selection(report, discovery, queue, root, enumerated)
        if selection_checks:
            checks["processing_selection"] = selection_checks
        findings.extend(selection_findings)
    for key, expected in (("current_core_discovered_urls", len(enumerated)),
                          ("current_core_verified_health_urls", len(actual)), ("metadata_only_candidates", len(metadata_only))):
        if key in report.get("counts", {}) and report["counts"][key] != expected:
            fail("discovery", "reported_inventory_partition_not_supported_by_core", field=key, expected=expected)
    errors = [row for row in details if row.get("status") == "detail_error"]
    if errors:
        fail("discovery", "unresolved_transport_or_primary_parser_errors", errors=errors)
    for days, (first, last, count) in WINDOWS.items():
        expected = {url for url, article in controls.items() if url and article.get("recall_expected")
                    and first <= (article.get("publication_date") or "") <= last}
        window = report.get("windows", {}).get(days, {})
        misses = sorted(expected - actual)
        checks["window_" + days] = dict(start=first, end=last, frozen_expected=len(expected), detected=len(expected & actual), misses=misses)
        if control.get("window_" + days, {}).get("start") != first or control.get("window_" + days, {}).get("end") != last:
            fail("discovery", "complete_calendar_window_changed", days=days)
        if (len(expected) != count or control.get("counts", {}).get("primary_recall_expected_" + days) != count
                or window.get("control_expected") != count or window.get("control_declared_expected") != count
                or window.get("control_denominator_consistent") is not True):
            fail("discovery", "frozen_control_denominator_changed", days=days, expected=count, observed=len(expected))
        if window.get("start") != first or window.get("end") != last:
            fail("discovery", "reported_window_incomplete", days=days)
        actual_recall = len(expected & actual) / len(expected) if expected else None
        if window.get("control_detected_by_current_core") != len(expected & actual) or window.get("recall") != actual_recall:
            fail("discovery", "reported_recall_not_supported_by_core_traces", days=days)
        if misses:
            fail("discovery", "important_external_control_omissions", days=days,
                 omissions=[dict(url=url, explanation=rows.get(url, {}).get("omission")) for url in misses])
        if window.get("date_conflicts"):
            fail("discovery", "external_publication_date_conflicts", days=days, urls=window["date_conflicts"])
    coverage = report.get("primary_coverage") or {}
    declared = set(coverage.get("required_feeds", []))
    summaries = {row.get("feed"): row for row in report.get("coverage", []) if row.get("status") == "public_feed_coverage"}
    if coverage.get("status") != "runtime_coverage" or coverage.get("coverage_complete") is not True or declared != REQUIRED_FEEDS:
        fail("discovery", "primary_required_public_feed_coverage_incomplete", missing=sorted(REQUIRED_FEEDS - declared))
    date_exception_count = 0
    feeds_without_content = []
    indexed_captures = api_capture_index(captures)
    for name in REQUIRED_FEEDS:
        summary = summaries.get(name, {})
        ending = summary.get("termination")
        pages = [row for row in details if row.get("status") == "public_feed_page" and row.get("feed") == name]
        if not pages or pages[0].get("offset") != 0 or len(pages) != summary.get("pages_attempted"):
            fail("discovery", "complete_public_api_page_chain_missing", feed=name)
        for problem in verify_api_pages(pages, indexed_captures, root, details):
            fail("discovery", problem.pop("code"), feed=name, **problem)
        if not summary.get("coverage_complete") or summary.get("errors") != 0:
            fail("discovery", "feed_incomplete_or_errors", feed=name, summary=summary)
        elif ending == "three_publication_ordered_detail_verified_old_pages":
            boundary = pages[-3:]
            cutoff = (date.fromisoformat(WINDOWS["90"][0]) - timedelta(days=2)).isoformat()
            if len(boundary) != 3 or any(row.get("primary_entries") != 24 or not row.get("inventory_day_max")
                                       or row["inventory_day_max"] >= cutoff for row in boundary) or boundary[-1].get("boundary_pages", 0) < 3:
                fail("discovery", "three_old_pages_boundary_unproven", feed=name)
        elif ending == "all_feed_count_delimited_articles":
            if not count_exhaustion_proven(summary, pages):
                fail("discovery", "count_delimited_feed_exhaustion_unproven", feed=name,
                     summary_publisher_count=summary.get("publisher_count"),
                     last_page_count=pages[-1].get("count") if pages else None,
                     enumerated_entries=sum(row.get("primary_entries", 0) for row in pages if type(row.get("primary_entries")) is int))
        else:
            fail("discovery", "feed_cap_or_unknown_boundary", feed=name, termination=ending)
        conflicts = [row for row in details if row.get("feed") == name and row.get("publisher_exception_reason") == DATE_HOLD]
        videos = [row for row in details if row.get("feed") == name and row.get("status") == "discovered_metadata_only"
                  and row.get("source_content_unavailable_reason") == VIDEO_HOLD]
        date_exception_count += len(conflicts)
        if conflicts or videos:
            feeds_without_content.append(name)
        if conflicts and (summary.get("publisher_exceptions") != len(conflicts)
                          or summary.get("enumerated_with_editorial_exceptions") is not True
                          or summary.get("publication_date_coverage_complete") is not False):
            fail("discovery", "feed_date_exceptions_erased_or_falsely_verified", feed=name)
        if (conflicts or videos) and summary.get("article_content_coverage_complete") is not False:
            fail("discovery", "feed_exception_content_falsely_complete", feed=name)
    if date_exception_count and (coverage.get("publisher_exceptions") != date_exception_count
                                 or coverage.get("enumerated_with_editorial_exceptions") is not True
                                 or coverage.get("publication_date_coverage_complete") is not False):
        fail("discovery", "aggregate_date_exceptions_erased_or_falsely_verified")
    if feeds_without_content and coverage.get("article_content_coverage_complete") is not False:
        fail("discovery", "aggregate_exception_content_falsely_complete")
    checks["coverage_dimensions"] = dict(enumeration_complete=coverage.get("coverage_complete") is True,
        publication_dates_complete=coverage.get("publication_date_coverage_complete", not date_exception_count),
        article_content_complete=coverage.get("article_content_coverage_complete", not feeds_without_content),
        date_conflict_occurrences=date_exception_count, feeds_with_editorial_content_exceptions=sorted(feeds_without_content))
    current_queue = {}
    for fingerprint, item in queue.items():
        if item.get("source") == SOURCE:
            url = normalized_url(item.get("raw", {}).get("url"))
            current_queue.setdefault(url, []).append((fingerprint, item))
    reviewed_outputs, review_findings = verify_bound_editorial_review(queue, history, snapshot, root)
    findings.extend(review_findings)
    if reviewed_outputs:
        legacy = [proof for proof in reviewed_outputs.values() if proof["review_file"] == EDITORIAL_REVIEW_PATH]
        checks["bound_independent_editorial_corrections"] = dict(
            review_sha256=EDITORIAL_REVIEW_SHA256, records=len(legacy),
            withdrawn=sum(proof["decision"] in {"reject", "group"} for proof in legacy),
            retained=sum(proof["decision"] not in {"reject", "group"} for proof in legacy),
            additional_records=len(reviewed_outputs) - len(legacy),
            additional_review_files=sorted({proof["review_file"] for proof in reviewed_outputs.values()
                                            if proof["review_file"] != EDITORIAL_REVIEW_PATH}))
    for baseline in report.get("baseline_queue", []):
        candidates = current_queue.get(baseline.get("url"), [])
        item = next((item for key, item in candidates if key == baseline.get("fingerprint")), None)
        if (not item or any(item.get(key) != baseline.get(key) for key in ("lane", "detected_at"))
                or item.get("attempts", 0) < baseline.get("attempts", 0)
                or baseline.get("status") in {"published", "rejected", "archived"} and item.get("status") != baseline["status"]
                and not (baseline["status"] == "published" and item.get("status") == "rejected"
                         and reviewed_outputs.get(baseline.get("url"), {}).get("decision") in {"reject", "group"})):
            fail("discovery", "baseline_queue_identity_or_bookkeeping_changed", url=baseline.get("url"))
    historical_urls = {normalized_url(row.get("source_url")) for row in history}
    feed_urls = {normalized_url(row.get("source_url")) for row in snapshot.get("signals", [])}
    for url in metadata_only:
        row = rows.get(url, {})
        traces = [trace for trace in details if normalized_url(trace.get("url")) == url
                  and trace.get("status") == "discovered_metadata_only"]
        if (row.get("current_core_detected") is not True or row.get("current_core_verified_health") is not False
                or row.get("metadata_only_candidate") is not True):
            fail("discovery", "metadata_inventory_falsely_labeled_verified_text", url=url)
        candidates = current_queue.get(url, [])
        if len(candidates) != 1:
            fail("discovery", "canonical_queue_missing_or_duplicated", url=url, count=len(candidates))
            continue
        item = candidates[0][1]
        raw = item.get("raw", {})
        metadata = raw.get("metadata", {})
        proof, error = verify_publisher_exception(row, metadata, traces, root)
        if error:
            fail("discovery", "publisher_exception_original_not_verified", url=url, errors=error)
        else:
            checks.setdefault("original_publisher_exception_validation", []).append(proof)
        reason = metadata.get("publisher_exception_reason") or metadata.get("source_content_unavailable_reason")
        assessment = metadata.get("editorial_assessment") or {}
        aged_hold = (item.get("status") == "archived" and item.get("reason") == "outside_90_day_backfill"
            and item.get("attempts") == 0 and metadata.get("publication_date_verified") is True
            and raw.get("event_date") == metadata.get("publication_date") and end
            and (end.date() - date.fromisoformat(metadata["publication_date"])).days > 90)
        if (raw.get("event_date") != metadata.get("publication_date") or item.get("status") not in {"pending", "retry"} and not aged_hold
                or assessment.get("decision") != "pending" or assessment.get("reason") != reason
                or any(assessment.get(key) is not None for key in ("relevance_score", "analysis_reason"))
                or row.get("exact_reason") != ("outside_90_day_backfill" if aged_hold else reason) or row.get("passed_gate") is not None):
            fail("discovery", "publisher_exception_exact_editorial_hold_missing", url=url)
        if (url in historical_urls | feed_urls or row.get("history_present") or row.get("feed_present")
                or row.get("editorial_outcome") not in ({"archived"} if aged_hold else {"pending", "deferred"})):
            fail("discovery", "unverified_publisher_exception_published_or_terminal", url=url)
        captured = stamp(row.get("primary_detail_captured_at"))
        if not captured or end and captured > end or not row.get("primary_detail_cache_hit") and start and captured < start:
            fail("discovery", "publisher_exception_capture_freshness_unproven", url=url)
        if row.get("primary_detail_cache_hit") and not row.get("publisher_lastmod"):
            fail("discovery", "publisher_exception_cached_original_lastmod_missing", url=url)
        if reason in {VIDEO_HOLD, SPONSORED_HOLD, SPONSORED_TEXT_HOLD} and row.get("publication_date_evidence") != (
                "reused_verified_primary_byline_unchanged_publisher_lastmod" if row.get("primary_detail_cache_hit") else "current_verified_detail"):
            fail("discovery", "publisher_video_date_falsely_labeled_fresh_or_unverified", url=url)
        if reason == DATE_HOLD and row.get("publication_date_evidence") not in {
                "unverified", "unresolved_primary_publisher_date_conflict"}:
            fail("discovery", "publisher_conflict_falsely_labeled_verified_date", url=url)
    for url in actual:
        row = rows.get(url, {})
        if row.get("current_core_detected") is not True:
            fail("discovery", "matrix_not_bound_to_actual_discovery", url=url)
        if row.get("metadata_only_candidate") or row.get("current_core_verified_health") is False:
            fail("discovery", "verified_text_falsely_labeled_metadata_only", url=url)
        if row.get("publication_date_source") not in PRIMARY_DATE_SOURCES or not SHA.fullmatch(str(row.get("primary_detail_sha256", ""))):
            fail("discovery", "primary_publication_evidence_missing", url=url)
        if url in controls and controls[url].get("publication_date") != row.get("publication_date"):
            fail("discovery", "original_control_date_disagrees", url=url)
        if url in controls:
            canonical_section = urlsplit(url).path.strip("/").split("/")[0]
            control_section = section_slug(controls[url].get("section"))
            if control_section != canonical_section:
                fail("discovery", "external_control_section_not_bound_to_original_url", url=url)
            if section_slug(row.get("section")) != canonical_section:
                checks.setdefault("publisher_section_taxonomy_review", []).append(dict(
                    url=url, canonical_section=canonical_section, reported_section=row.get("section")))
            checks.setdefault("external_topic_comparison", []).append(dict(
                url=url, independent_topic=controls[url].get("topic"), publisher_topics=row.get("topics", []),
                policy="Independent topic and publisher taxonomy may be aliases; semantic comparison requires reviewer, not literal equality."))
        captured = stamp(row.get("primary_detail_captured_at"))
        if not captured or end and captured > end:
            fail("discovery", "primary_capture_timestamp_invalid", url=url)
        if row.get("primary_detail_cache_hit"):
            if (row.get("publication_date_evidence") != "reused_verified_primary_byline_unchanged_publisher_lastmod"
                    or not row.get("publisher_lastmod")):
                fail("discovery", "cached_primary_falsely_labeled_fresh_or_unbound", url=url)
        elif row.get("publication_date_evidence") != "current_verified_detail" or start and captured and captured < start:
            fail("discovery", "current_primary_capture_freshness_unproven", url=url)
        # Original bytes for every independent important control, not just a
        # manually chosen tiny positive sample. Other positives keep SHA traces.
        if url in controls and controls[url].get("recall_expected"):
            date_evidence = {}
            error = verify_primary_capture(row, root, date_evidence)
            if error:
                fail("discovery", "original_primary_capture_not_verified", url=url, errors=error)
            else:
                checks.setdefault("original_publication_date_validation", []).append(date_evidence)
        candidates = current_queue.get(url, [])
        if len(candidates) != 1:
            fail("discovery", "canonical_queue_missing_or_duplicated", url=url, count=len(candidates))
            continue
        metadata = candidates[0][1].get("raw", {}).get("metadata", {})
        if (metadata.get("article_verified") is not True or metadata.get("source_quality_gate") != "passed"
                or normalized_url(metadata.get("canonical_url")) != url
                or metadata.get("publication_date") != row.get("publication_date")
                or metadata.get("publication_date_source") not in PRIMARY_DATE_SOURCES
                or not queue_timestamp_corroborates(metadata, row.get("publication_date"))
                or metadata.get("html_sha256") != row.get("primary_detail_sha256")
                or len(str(metadata.get("page_text") or "").strip()) < 160):
            fail("discovery", "queue_primary_detail_evidence_unverified", url=url)
    if processing:
        replay_checks, replay_findings = verify_genuine_idempotence(idempotence_baseline, idempotence_proof,
            root=root, report=report, discovery=discovery, queue=queue, history=history, snapshot=snapshot, telemetry=telemetry)
        findings.extend(replay_findings)
        if replay_checks:
            checks["genuine_selected_core_idempotence"] = replay_checks
        final_evaluation = None
        terminal_evaluation = None
        terminal_origin = None
        if not replay_checks and execution.get("processing_attempts_increased") == 0 and any(
                has_final_paid_claim(item.get("raw", {}).get("metadata", {})) for item in queue.values()):
            try:
                terminal_origin = terminal_followthrough_origin(root)
                terminal_evaluation = verify_terminal_followthrough_execution(root,report=report,queue=queue,
                    history=history,snapshot=snapshot,telemetry=telemetry,execution=execution,origin=terminal_origin)
                checks["genuine_terminal_followthrough_paid_model_lineage"] = terminal_evaluation
            except (OSError,ValueError,KeyError,TypeError,AttributeError) as error:
                fail("processing","genuine_terminal_followthrough_provenance_unverified",error=str(error))
        if not replay_checks and not terminal_evaluation and execution.get("processing_attempts_increased") != 0 and any(
                has_final_paid_claim(item.get("raw", {}).get("metadata", {})) for item in queue.values()):
            try:
                final_evaluation = verify_final_revalidated_execution(root, report=report, queue=queue,
                    history=history, telemetry=telemetry, execution=execution)
                checks["genuine_revalidated_paid_model_lineage"] = final_evaluation
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                fail("processing", "genuine_revalidated_paid_model_lineage_unverified", error=str(error))
        if not replay_checks and not final_evaluation and not terminal_evaluation and (not delta.get("fast", {}).get("attempted") or not delta.get("fast", {}).get("successful")):
            fail("processing", "no_actual_successful_fast_editorial_analysis")
        events = [row for row in telemetry if stamp(row.get("at")) and start and end and start <= stamp(row["at"]) <= end and row.get("kind") == "fast"]
        if len(events) != delta.get("fast", {}).get("attempted") or sum(row.get("success") is True for row in events) != delta.get("fast", {}).get("successful"):
            fail("processing", "actual_api_telemetry_and_ledger_delta_disagree")
        if any(row.get("success") is True and not row.get("response_id") for row in events):
            fail("processing", "successful_analysis_without_actual_api_response_id")
        checks["actual_fast_response_events"] = len(events)
        feed = {normalized_url(row.get("source_url")): row for row in snapshot.get("signals", [])}
        historical = {normalized_url(row.get("source_url")): row for row in history}
        feed_evidence = report.get("feed_evidence", {})
        if not feed_evidence.get("serialized_feed_verified") or feed_evidence.get("generated_after_current_history") is not True:
            fail("processing", "actual_serialized_feed_missing_or_stale")
        if report.get("source_attribution_findings") or report.get("unresolved_recent_feed_exclusions"):
            fail("processing", "unresolved_media_attribution_or_feed_loss")
        if report.get("unresolved_pending_operational_reasons"):
            fail("processing", "pending_operational_reasons_unresolved")
        selected_urls = set((execution.get("processing_selection") or {}).get("selected_urls", []))
        paid_origin = None
        current_origin = None
        followup_origin = None
        final_origin = None
        if any(item.get("source") == SOURCE and has_paid_revalidation_claim(item.get("raw", {}).get("metadata", {}))
               for item in queue.values()):
            try:
                paid_origin = paid_revalidation_origin(root)
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                fail("processing", "paid_guard_revalidation_originals_unverified", error=str(error))
        if local_capture_path(root, CURRENT_PAID_PATH).exists():
            try:
                current_origin = current_paid_origin(root, previous_origin=paid_origin)
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                fail("processing", "current_paid_originals_or_two_current_readers_unverified", error=str(error))
        if local_capture_path(root, FOLLOWUP_PAID_PATH).exists():
            try:
                followup_origin = followup_paid_origin(root, current_origin=current_origin)
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                fail("processing", "followup_paid_originals_or_two_current_readers_unverified", error=str(error))
        if local_capture_path(root, FINAL_PAID_PATH).exists():
            try:
                final_origin = final_paid_origin(root, followup_origin=followup_origin)
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                fail("processing", "final_paid_originals_or_two_current_readers_unverified", error=str(error))
        for url in actual:
            row = rows.get(url, {})
            reason = row.get("exact_reason") or ""
            if not reason or any(term in reason for term in ("no_editorial_verdict", "processor_rejected", "reason_missing", "unknown", "specific exclusion is not emitted")):
                fail("processing", "outcome_reason_unresolved", url=url, reason=reason)
            if row.get("consistency_findings") or row.get("traceability_unresolved"):
                fail("processing", "queue_history_feed_inconsistent", url=url)
            if bool(row.get("feed_present")) != (url in feed) or bool(row.get("history_present")) != (url in historical):
                fail("processing", "reported_history_or_feed_presence_not_actual", url=url)
            if len(current_queue.get(url, [])) != 1:
                continue
            item = current_queue[url][0][1]
            try:
                addendum = verify_incremental_addendum_reference(item.get("raw", {}), root)
                if addendum:
                    checks.setdefault("immutable_incremental_analysis_releases", {})[url] = addendum
            except (OSError, ValueError, KeyError, TypeError) as error:
                fail("processing", "incremental_addendum_original_or_provenance_unverified", url=url, error=str(error))
            try:
                repair = verify_code_repair_reference(item.get("raw", {}), root,
                    successful_response_ids={event.get("response_id") for event in telemetry
                        if event.get("success") is True and event.get("kind") == "fast"},
                    require_new_assessment=True)
                if repair:
                    checks.setdefault("immutable_code_repair_assessments", {})[url] = repair
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                code = ("code_repair_actual_paid_validation_deferred"
                        if str(error) == "code_repair_new_genuine_v5_validation_deferred"
                        else "code_repair_old_or_new_paid_evidence_unverified")
                fail("processing", code, url=url, error=str(error))
            if requires_final_paid_authority(item, final_origin):
                try:
                    if final_origin is None:
                        raise ValueError("final_paid_origin_unavailable")
                    validation_execution = idempotence_baseline["baseline_execution"] if replay_checks else execution
                    if terminal_origin is None and (terminal_evaluation or replay_checks and idempotence_baseline.get("mode") == "genuine_terminal_followthrough_processing_baseline"):
                        terminal_origin = terminal_followthrough_origin(root)
                    previous_execution = unchanged_final_paid_execution(item,terminal_origin)
                    if previous_execution is not None:
                        validation_execution = previous_execution
                    revalidated = verify_final_paid_revalidation(item, root, execution=validation_execution,
                        telemetry=telemetry, origin=final_origin,archived_execution=previous_execution is not None)
                    checks.setdefault("immutable_final_paid_guard_revalidations", {})[url] = revalidated
                except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                    code = ("final_paid_actual_validation_deferred"
                            if str(error) == "final_paid_actual_bound_validation_still_deferred"
                            else "final_paid_revalidation_provenance_unverified")
                    fail("processing", code, url=url, error=str(error))
            elif requires_followup_paid_authority(item, followup_origin):
                try:
                    if followup_origin is None:
                        raise ValueError("followup_paid_origin_unavailable")
                    validation_execution = idempotence_baseline["baseline_execution"] if replay_checks else execution
                    previous_execution = unchanged_followup_paid_execution(item, final_origin)
                    # The unchanged323 held pair remains historical evidence,
                    # never a fictitious final revalidation.
                    if (previous_execution is None and final_origin is not None
                            and not requires_final_paid_authority(item, final_origin)
                            and url in final_origin["rows"]):
                        previous_execution = final_origin["execution"]
                    if previous_execution is not None:
                        validation_execution = previous_execution
                    revalidated = verify_followup_paid_revalidation(item, root, execution=validation_execution,
                        telemetry=telemetry, origin=followup_origin, archived_execution=previous_execution is not None)
                    checks.setdefault("immutable_followup_paid_guard_revalidations", {})[url] = revalidated
                except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                    code = ("followup_paid_actual_validation_deferred"
                            if str(error) == "followup_paid_actual_bound_validation_still_deferred"
                            else "followup_paid_revalidation_provenance_unverified")
                    fail("processing", code, url=url, error=str(error))
            elif requires_current_paid_authority(item, current_origin):
                try:
                    if current_origin is None:
                        raise ValueError("current_paid_origin_unavailable")
                    validation_execution = idempotence_baseline["baseline_execution"] if replay_checks else execution
                    previous_execution = unchanged_current_paid_execution(item, followup_origin)
                    # Original66 held responses keep their actual failed validator;
                    # only a new followup claim can establish a different verdict.
                    if (previous_execution is None and followup_origin is not None
                            and not requires_followup_paid_authority(item, followup_origin)
                            and url in followup_origin["rows"]):
                        previous_execution = followup_origin["execution"]
                    if previous_execution is not None:
                        validation_execution = previous_execution
                    revalidated = verify_current_paid_revalidation(item, root, execution=validation_execution,
                        telemetry=telemetry, origin=current_origin, archived_execution=previous_execution is not None)
                    checks.setdefault("immutable_current_paid_guard_revalidations", {})[url] = revalidated
                except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                    code = ("current_paid_actual_validation_deferred"
                            if str(error) == "current_paid_actual_bound_validation_still_deferred"
                            else "current_paid_revalidation_provenance_unverified")
                    fail("processing", code, url=url, error=str(error))
            elif has_paid_revalidation_claim(item.get("raw", {}).get("metadata", {})):
                try:
                    if paid_origin is None:
                        raise ValueError("paid_revalidation_origin_unavailable")
                    validation_execution = idempotence_baseline["baseline_execution"] if replay_checks else execution
                    previous_execution = unchanged_previous_paid_execution(item, current_origin)
                    if previous_execution is not None:
                        validation_execution = previous_execution
                    revalidated = verify_paid_guard_revalidation(item, root, execution=validation_execution,
                        telemetry=telemetry, origin=paid_origin, archived_execution=previous_execution is not None)
                    checks.setdefault("immutable_paid_guard_revalidations", {})[url] = revalidated
                except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                    code = ("paid_guard_actual_validation_deferred"
                            if str(error) == "paid_revalidation_actual_validation_still_deferred"
                            else "paid_guard_revalidation_provenance_unverified")
                    fail("processing", code, url=url, error=str(error))
            assessment = item.get("raw", {}).get("metadata", {}).get("editorial_assessment") or {}
            score = assessment.get("relevance_score")
            if url in selected_urls:
                technical_failures = technical_processing_deferral(item, row)
                if technical_failures:
                    fail("processing", "selected_reviewed_text_processing_evidence_unresolved", url=url,
                         failures=technical_failures, status=item.get("status"), reason=reason)
            if score is not None and assessment.get("threshold") != 72:
                fail("processing", "media_editorial_threshold_changed", url=url, assessment=assessment)
            if url in controls and controls[url].get("recall_expected"):
                if item.get("status") not in {"published", "rejected"}:
                    fail("processing", "important_control_not_editorially_processed", url=url, reason=reason)
            if item.get("status") == "published":
                gate_analysis_reason = assessment.get("analysis_reason")
                if url in reviewed_outputs:
                    gate_analysis_reason = reviewed_outputs[url]["original_model_assessment"].get("analysis_reason")
                if assessment.get("decision") != "published" or type(score) is not int or score < 72 or not gate_analysis_reason:
                    fail("processing", "published_without_unchanged_editorial_gate_trace", url=url)
                published = historical.get(url, {})
                text = " ".join(str(published.get(key) or "") for key in ("title", "what_happened", "why_it_matters"))
                if (published.get("evidence_maturity") != "media_reported"
                        or not explicit_media_attribution(published.get("what_happened"))
                        or published.get("publication_date") != row.get("publication_date")):
                    fail("processing", "published_media_attribution_or_real_date_invalid", url=url)
                if "presupuesto-salud-2027-rebajas" in url and not re.search(r"propuest|proyect|discusi|tramit", text, re.I):
                    fail("processing", "budget_proposal_presented_as_enacted", url=url)
                if "isapres-logran-detener-la-fuga" in url and (not re.search(r"mayo", text, re.I) or not re.search(r"contrat|suscrip|firm", text, re.I)):
                    fail("processing", "historical_contract_flow_period_or_metric_lost", url=url)
                if "senior-housing-los-grupos" in url and re.search(r"fne\s+(?:aprob[oó]|autoriz[oó])", text, re.I):
                    fail("processing", "publisher_fne_notification_upgraded_to_approval", url=url)
            elif item.get("status") == "rejected" and (assessment.get("decision") != "rejected" or not assessment.get("reason")):
                fail("processing", "rejection_without_exact_assessment", url=url)
            elif item.get("status") == "retry" and (assessment.get("decision") != "pending" or assessment.get("reason") != reason):
                fail("processing", "deferred_without_exact_assessment", url=url)
    discovery_failures = [row for row in findings if row["domain"] == "discovery"]
    processing_failures = [row for row in findings if row["domain"] == "processing"]
    return dict(schema_version=1, source=SOURCE, reviewed_code_sha=report.get("code_sha"), phase=mode, requested_phase=phase,
                discovery_qa="FAIL" if discovery_failures else "PASS",
                processing_qa=("FAIL" if processing_failures or discovery_failures else "PASS") if processing else "NOT_RUN",
                verdict="FAIL" if findings else "PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW" if processing else "PASS_DISCOVERY_ONLY_NOT_END_TO_END_ACCEPTANCE",
                acceptance="NOT_ACCEPTED" if findings or not processing else "PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW",
                findings=findings, checks=checks,
                limitations=["Frozen 29/79 controls benchmark recall; they are not a publication quota or proof of every publisher article.",
                             "Enumeration can pass with byte-verified publisher limitations; unresolved original dates and missing video text remain explicit editorial holds, not verified health coverage.",
                             "An automated PASS cannot settle semantic editorial correctness, final staging QA, or close issues/PR acceptance."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path, default=Path("data/audits/pulso_runtime_2026_10_11.json"))
    parser.add_argument("--control", type=Path, default=Path("data/audits/pulso_external_control_2026_10_11.json"))
    parser.add_argument("--output", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--discovery", action="store_true", help="Check discovery only; never infer end-to-end acceptance")
    modes.add_argument("--processing", action="store_true", help="Require a genuine processing execution and editorial outcomes")
    parser.add_argument("--capture-artifact", type=Path, default=Path(".scratch/pulso-prior-capture"))
    parser.add_argument("--idempotence-baseline", type=Path, help="A retained passing genuine paid-processing baseline")
    parser.add_argument("--idempotence-proof", type=Path, help="Observations of the subsequent genuine zero-call core run")
    args = parser.parse_args()
    root = args.root.resolve()
    def path(value):
        return value if value.is_absolute() else root / value
    def read(value):
        return json.loads(path(Path(value)).read_text())
    try:
        if (args.idempotence_baseline or args.idempotence_proof) and (not args.processing
                or not args.idempotence_baseline or not args.idempotence_proof):
            raise ValueError("idempotence_requires_processing_and_both_bound_evidence_files")
        report, control = read(args.report), read(args.control)
        history = read("data/history/superintendencia_signals.json")
        history = history.get("signals", []) if isinstance(history, dict) else history
        telemetry_path = root / "data/ai_usage/responses.jsonl"
        telemetry = [json.loads(line) for line in telemetry_path.read_text().splitlines() if line.strip()] if telemetry_path.exists() else []
        result = evaluate(report, control, root=root, discovery=read("data/state/discovery_run.json"),
                          queue=read("data/state/pending_queue.json"), history=history,
                          snapshot=read("web/data/radar_today.json"), telemetry=telemetry,
                          control_sha=digest(path(args.control).read_bytes()),
                          captures=capture_records(root, path(args.capture_artifact)),
                          phase="processing" if args.processing else "discovery" if args.discovery else "auto",
                          idempotence_baseline=read(args.idempotence_baseline) if args.idempotence_baseline else None,
                          idempotence_proof=read(args.idempotence_proof) if args.idempotence_proof else None)
        if not args.discovery and (report.get("last_core_execution") or report.get("execution", {})).get("mode") == "real_core_processing":
            if report.get("feed_evidence", {}).get("sha256") != digest((root / "web/data/radar_today.json").read_bytes()):
                result["findings"].append(dict(domain="processing", code="serialized_feed_hash_changed_after_audit"))
                result.update(processing_qa="FAIL", verdict="FAIL", acceptance="NOT_ACCEPTED")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        result = dict(discovery_qa="FAIL", processing_qa="NOT_RUN", verdict="FAIL", acceptance="NOT_ACCEPTED",
                      findings=[dict(domain="evidence", code="required_evidence_unreadable", error=type(error).__name__ + ":" + str(error))])
    if args.output:
        destination = path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["verdict"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
