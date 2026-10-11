"""One reviewed repair of the twelve genuine 29731 paid deferrals.

The earlier 981 admission and the newer API responses keep their own origins.
A current validator receipt never rewrites a model response or approves a
publication; the ordinary media gate and history pipeline still decide it.
"""
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import json
import subprocess

from . import pulso_paid_revalidation as previous
from .llm_analysis import news_analysis_input
from .models import RawItem

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_REF = "data/audits/pulso_current12_paid_guard_revalidation_manifest_2026_10_11.json"
MANIFEST_SHA256 = "3f27a3a4450e0fbf074fadc8da380f674c18d35ab20e896971a2b19d7c55cc1b"
PRODUCER_STATE = "9083056a7127656e90ff40d4fcd7aef0ac407dbc"
PRODUCER_CODE = "29731f04d998659e5892c109871f54ef0c7f8eef"
PRODUCER_FINGERPRINT = "73b012deb1cd6729e55527f87569825136d5f5523617029ff862640eadea366d"
PRODUCER_FILES = {
    "data/state/pending_queue.json": "10b1f2e3ea5ea434be8347b06874fcec7bb3c1f3a6ab67eec803976849101202",
    "data/audits/pulso_runtime_2026_10_11.json": "eb420d6e3b74b9a2274598adc5b2ae7f2f5f7e9635e1fc34f60968c896a95bd3",
    "data/ai_usage/responses.jsonl": "d421299b6f6fbe440c166bb13ad686ba0896ccfc0cbfeda400f49932c9781037",
    "data/history/superintendencia_signals.json": "bd7e32dd341348f44cfacdb0140247c5f957c417f6bed625fdcf9762a4d0f4ca",
}
STAMP = "current_paid_guard_revalidation_admission"
RECEIPT = "current_paid_guard_revalidation_receipt"
NEW_FAST_RECEIPTS = "current_paid_new_fast_attempt_receipts"
REVISION = "verified_current_paid_guard_revalidation_admission"
DISPOSITIONS = {"reuse_code_fn", "assess_contract_or_semantic_defect"}
digest = previous.digest
paid_raw = previous.paid_raw


def has_claim(metadata):
    return (STAMP in metadata or RECEIPT in metadata or NEW_FAST_RECEIPTS in metadata
            or any(isinstance(revision, dict) and revision.get("reason") == REVISION
                   for revision in metadata.get("evidence_revisions", [])))


def _stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@lru_cache(maxsize=2)
def producer(root):
    objects = {}
    for path, expected in PRODUCER_FILES.items():
        result = subprocess.run(["git", "show", PRODUCER_STATE + ":" + path], cwd=root, capture_output=True)
        if result.returncode or digest(result.stdout) != expected:
            raise ValueError("current_paid_original_producer_blob_unavailable_or_changed")
        objects[path] = result.stdout
    report = json.loads(objects["data/audits/pulso_runtime_2026_10_11.json"])
    execution = report.get("last_core_execution") or report["execution"]
    if (execution.get("code_sha") != PRODUCER_CODE
            or execution.get("runtime_fingerprint", {}).get("sha256") != PRODUCER_FINGERPRINT
            or execution.get("mode") != "real_core_processing"
            or execution.get("engine_called") is not True or execution.get("engine_completed") is not True
            or execution.get("ai_guardrails_modified") is not False
            or execution.get("processing_selection", {}).get("sha256") != "8ed358f0cd37ecc4b554ab96cd4366048b8e6180ad1c0ee0044fc5d5f6976514"):
        raise ValueError("current_paid_original_execution_unverified")
    events = [json.loads(line) for line in objects["data/ai_usage/responses.jsonl"].splitlines() if line]
    events = [event for event in events if _stamp(execution["started_at"]) <= _stamp(event["at"]) <= _stamp(execution["finished_at"])]
    ids = {event.get("response_id") for event in events}
    if (len(events) != 25 or len(ids) != 25 or None in ids
            or any(event.get("kind") != "fast" or event.get("success") is not True for event in events)):
        raise ValueError("current_paid_original_25_response_receipts_unverified")
    for field in ("attempted", "successful"):
        if (execution["budget_after"]["month"]["fast"][field]
                - execution["budget_before"]["month"]["fast"][field] != 25
                or execution["budget_after"]["month"]["deep"][field] != execution["budget_before"]["month"]["deep"][field]):
            raise ValueError("current_paid_original_positive_ledger_unverified")
    queue = json.loads(objects["data/state/pending_queue.json"])
    held = {key: entry for key, entry in queue.items() if entry.get("source") == "pulso_latercera"
        and entry.get("status") == "retry" and entry.get("raw", {}).get("metadata", {}).get(
            "analysis_model_output", {}).get("_pulso_analysis_meta", {}).get("response_id") in ids}
    if len(held) != 12:
        raise ValueError("current_paid_original_complete_12_required")
    # Reproduce the original validator from the producer's immutable code,
    # never from today's repaired file or a rewritten model wrapper.
    path = "src/radar_salud/pulso_editorial_proof.py"
    code = subprocess.run(["git", "show", PRODUCER_CODE + ":" + path], cwd=root,
                          capture_output=True, check=True).stdout
    if digest(code) != execution["runtime_fingerprint"]["files"][path]:
        raise ValueError("current_paid_original_guard_not_execution_bound")
    namespace = {"__name__": "radar_salud._original_current_paid_guard", "__file__": str(Path(root) / path)}
    exec(compile(code, namespace["__file__"], "exec"), namespace)
    for entry in held.values():
        raw, meta = entry["raw"], entry["raw"]["metadata"]
        model = meta["analysis_model_output"]
        validation = namespace["validate_pulso_editorial_proof"](model, meta["page_text"])
        validation.update(primary_article_body_sha256=meta["analysis_base_article_body_sha256"],
            request_input_sha256=meta["analysis_request_input_sha256"], model_response=model["_pulso_analysis_meta"])
        receipts = meta.get(previous.NEW_FAST_RECEIPTS, [])
        if (entry.get("attempts") != 3 or type(entry.get("attempts")) is not int
                or validation != meta["pulso_editorial_proof_validation"] or validation["decision"] != "deferred"
                or entry.get("reason") != validation["reason"]
                or meta.get("editorial_assessment", {}).get("decision") != "pending"
                or meta["editorial_assessment"].get("reason") != validation["reason"]
                or meta["editorial_assessment"].get("threshold") != 72
                or len(receipts) != 1 or receipts[0]["full_model_output"] != model
                or receipts[0]["new_validation"] != validation
                or receipts[0]["new_response_id"] != model["_pulso_analysis_meta"]["response_id"]
                or not _stamp(execution["started_at"]) <= _stamp(receipts[0]["assessed_at"]) <= _stamp(execution["finished_at"])):
            raise ValueError("current_paid_original_answer_or_validation_not_genuine")
        previous.verified_paid_processing_mode(RawItem(**deepcopy(raw)))
    return dict(held=held, queue=queue, history=json.loads(objects["data/history/superintendencia_signals.json"])["signals"],
                execution=execution, events=events)


def original_pin(key, entry):
    return previous.original_pin(key, entry)


def _verify_context(context, raw, origin):
    from .pulso_editorial_proof import literal_quote_matches
    if (context.get("source_url") != raw["url"] or context.get("source_publication_date") != raw["event_date"]
            or context.get("source_body_sha256") != raw["metadata"]["article_body_sha256"]
            or context.get("publication_approved") is not False or context.get("rejection_approved") is not False
            or not isinstance(context.get("context_text"), str) or not context["context_text"].strip()
            or not context.get("source_verbatim_quotes")
            or any(not literal_quote_matches(quote, raw["metadata"]["page_text"], 8)
                   for quote in context["source_verbatim_quotes"])):
        raise ValueError("current_paid_reassessment_context_source_or_quotes_unverified")
    for target in context.get("published_comparison_targets", []):
        entry = origin["queue"][target["target_queue_fingerprint"]]
        target_raw, meta = entry["raw"], entry["raw"]["metadata"]
        signals = [signal for signal in origin["history"] if signal.get("source_url") == target_raw["url"]
                   and signal.get("event_date") == target_raw["event_date"]]
        assessment = meta.get("editorial_assessment", {})
        if (len(signals) != 1 or entry.get("status") != "published"
                or assessment.get("decision") != "published" or assessment.get("threshold") != 72
                or target.get("target_queue_entry_sha256") != digest(entry)
                or target.get("target_full_primary_raw") != target_raw
                or target.get("target_full_signal") != signals[0]
                or target.get("target_signal_sha256") != digest(signals[0])
                or signals[0].get("source_type") != "press_high_trust"
                or signals[0].get("evidence_maturity") != "media_reported"
                or signals[0].get("feed_visibility") is False
                or type(signals[0].get("editorial_relevance")) is not int or signals[0]["editorial_relevance"] < 72):
            raise ValueError("current_paid_reassessment_comparison_target_not_published_and_bound")


def load_manifest(root=ROOT):
    root = Path(root)
    payload = (root / MANIFEST_REF).read_bytes()
    if digest(payload) != MANIFEST_SHA256:
        raise ValueError("current_paid_revalidation_manifest_unpinned")
    document = json.loads(payload)
    if (document.get("schema_version") != "pulso_current_paid_guard_revalidation_manifest_v1"
            or document.get("source_id") != "pulso_latercera"
            or document.get("producer_state_commit") != PRODUCER_STATE
            or document.get("producer_core_checkout") != PRODUCER_CODE
            or document.get("producer_runtime_fingerprint_sha256") != PRODUCER_FINGERPRINT):
        raise ValueError("current_paid_revalidation_manifest_origin_changed")
    refs = document.get("semantic_references", [])
    if len(refs) != 2 or len({ref.get("path") for ref in refs}) != 2:
        raise ValueError("current_paid_two_independent_current_response_reviews_required")
    for ref in refs:
        path = (root / ref["path"]).resolve()
        if not path.is_relative_to((root / "data/audits").resolve()) or digest(path.read_bytes()) != ref["sha256"]:
            raise ValueError("current_paid_semantic_review_unavailable_or_changed")
    origin = producer(str(root))
    rows = document.get("rows", [])
    if (len(rows) != 12 or len({row.get("url") for row in rows}) != 12
            or {row.get("queue_fingerprint") for row in rows} != set(origin["held"])):
        raise ValueError("current_paid_complete_original12_required")
    counts = {name: 0 for name in DISPOSITIONS}
    normalized = []
    for row in rows:
        entry = origin["held"][row["queue_fingerprint"]]
        raw, meta = entry["raw"], entry["raw"]["metadata"]
        expected = original_pin(row["queue_fingerprint"], entry)
        direct = dict(expected, original_full_primary_body=meta["page_text"],
            original_full_model_output=meta["analysis_model_output"], actual_pulso_validation=meta["pulso_editorial_proof_validation"],
            actual_queue_entry_sha256=digest(entry), original_raw_sha256=digest(raw), original_metadata_sha256=digest(meta))
        if (any(row.get(field) != value for field, value in direct.items())
                or row.get("runtime_route") not in DISPOSITIONS or row.get("publication_approved") is not False
                or row.get("runtime_route_is_publication_approval") is not False or row.get("editorial_gate") != 72
                or row.get("semantic_references") != refs):
            raise ValueError("current_paid_original_pin_or_reviewed_route_changed")
        counts[row["runtime_route"]] += 1
        context = row.get("reassessment_context")
        if row["runtime_route"] == "assess_contract_or_semantic_defect":
            if not isinstance(context, dict):
                raise ValueError("current_paid_new_fast_requires_bound_contract_context")
            _verify_context(context, raw, origin)
        elif context is not None:
            raise ValueError("current_paid_reuse_cannot_inject_model_context")
        normalized.append(dict(expected, disposition=row["runtime_route"], reassessment_context=context))
    if counts != {"reuse_code_fn": 2, "assess_contract_or_semantic_defect": 10}:
        raise ValueError("current_paid_reviewed2_10_partition_changed")
    return dict(document, rows=normalized), origin


def _admission(row):
    value = dict(schema_version="pulso_current_paid_guard_revalidation_admission_v1",
        manifest_ref=MANIFEST_REF, manifest_sha256=MANIFEST_SHA256, producer_state_commit=PRODUCER_STATE,
        producer_core_checkout=PRODUCER_CODE, producer_runtime_fingerprint_sha256=PRODUCER_FINGERPRINT,
        disposition=row["disposition"], new_model_request=row["disposition"] == "assess_contract_or_semantic_defect",
        publication_approved=False)
    value.update({field: row[field] for field in previous.original_pin_fields()})
    if row.get("reassessment_context") is not None:
        value["reassessment_context_sha256"] = digest(row["reassessment_context"])
    value["admission_id"] = digest(value)
    return value


def verified_admission(fresh, existing):
    try:
        meta = existing.get("raw", {}).get("metadata", {})
        if (existing.get("status") not in {"pending", "retry"}
                or type(existing.get("attempts")) is not int or existing["attempts"] != 3
                or has_claim(meta)):
            return None
        document, origin = load_manifest()
        row = next(row for row in document["rows"] if row["url"] == fresh.url)
        original = origin["held"][row["queue_fingerprint"]]
        if (existing != original or not previous._primary_matches(fresh, row)):
            return None
        return _admission(row)
    except (OSError, ValueError, KeyError, TypeError, StopIteration, subprocess.CalledProcessError):
        return None


def verified_processing_mode(raw):
    document, origin = load_manifest()
    row = next(row for row in document["rows"] if row["url"] == raw.url)
    expected = _admission(row)
    original = origin["held"][row["queue_fingerprint"]]
    meta, old = raw.metadata, original["raw"]["metadata"]
    revisions = [revision for revision in meta.get("evidence_revisions", []) if revision.get("reason") == REVISION]
    if (meta.get(STAMP) != expected or not previous._primary_matches(raw, row)
            or len(revisions) != 1 or revisions[0].get(STAMP) != expected
            or revisions[0].get("previous_processing_raw") != paid_raw(original["raw"])
            or meta.get(previous.STAMP) != old.get(previous.STAMP)
            or meta.get("editorial_code_repair_admission") != old.get("editorial_code_repair_admission")
            or meta.get(previous.NEW_FAST_RECEIPTS, [])[:len(old[previous.NEW_FAST_RECEIPTS])] != old[previous.NEW_FAST_RECEIPTS]):
        raise ValueError("current_paid_primary_or_admission_or_prior_archive_unverified")
    current, validation = meta.get("analysis_model_output"), meta.get("pulso_editorial_proof_validation")
    original_unchanged = current == old["analysis_model_output"] and validation == old["pulso_editorial_proof_validation"]
    attempts = meta.get(NEW_FAST_RECEIPTS, [])
    resumed = False
    if attempts and expected["new_model_request"]:
        from .pulso_editorial_proof import model_binding_matches
        latest = attempts[-1]
        ids = [attempt.get("new_response_id") for attempt in attempts]
        resumed = bool(len(ids) == len(set(ids)) and expected["original_response_id"] not in ids
            and all(attempt.get("admission_id") == expected["admission_id"]
                    and attempt.get("model_output_sha256") == digest(attempt.get("full_model_output"))
                    and attempt.get("new_validation_sha256") == digest(attempt.get("new_validation")) for attempt in attempts)
            and latest.get("full_model_output") == current and latest.get("new_validation") == validation
            and latest.get("new_response_id") == (current or {}).get("_pulso_analysis_meta", {}).get("response_id")
            and model_binding_matches(current, source_name=raw.source_name,
                input_text_sha256=expected["analysis_input_sha256"], request_input_sha256=expected["request_input_sha256"]))
    if (not (original_unchanged and not attempts or resumed) or RECEIPT in meta):
        raise ValueError("current_paid_original_current_answer_or_validation_changed")
    return expected, original


def reassessment_context(raw):
    admission, _ = verified_processing_mode(raw)
    document, _ = load_manifest()
    row = next(row for row in document["rows"] if row["url"] == raw.url)
    context = row.get("reassessment_context")
    if context is not None and digest(context) != admission.get("reassessment_context_sha256"):
        raise ValueError("current_paid_contract_context_unbound")
    return deepcopy(context)


def unchanged_output(raw):
    admission, original = verified_processing_mode(raw)
    if admission["new_model_request"]:
        raise ValueError("current_paid_contract_defect_requires_new_fast")
    return deepcopy(original["raw"]["metadata"]["analysis_model_output"])


def _validation(raw, model):
    from . import pulso_editorial_proof as guard
    value = guard.validate_pulso_editorial_proof(model, raw.metadata["page_text"])
    value.update(primary_article_body_sha256=raw.metadata["analysis_base_article_body_sha256"],
                 request_input_sha256=raw.metadata["analysis_request_input_sha256"], model_response=model.get("_pulso_analysis_meta"))
    if not guard.model_binding_matches(model, source_name=raw.source_name,
            input_text_sha256=raw.metadata["analysis_input_body_sha256"], request_input_sha256=raw.metadata["analysis_request_input_sha256"]):
        value.update(decision="deferred", reason="pulso_editorial_model_binding_mismatch")
    return value, digest(Path(guard.__file__).read_bytes()), guard.VERSION


def revalidation_receipt(raw, model, validation, *, now=None):
    admission, original = verified_processing_mode(raw)
    expected, guard_sha, version = _validation(raw, model)
    if (admission["new_model_request"] or model != original["raw"]["metadata"]["analysis_model_output"]
            or validation != expected):
        raise ValueError("current_paid_unchanged_output_or_actual_guard_result_unverified")
    old = original["raw"]["metadata"]["pulso_editorial_proof_validation"]
    return dict(schema_version="pulso_current_paid_guard_revalidation_receipt_v1", admission=deepcopy(admission),
        producer_state_commit=PRODUCER_STATE, producer_core_checkout=PRODUCER_CODE,
        producer_runtime_fingerprint_sha256=PRODUCER_FINGERPRINT,
        original_response_id=admission["original_response_id"], original_model_output_sha256=admission["model_output_sha256"],
        original_raw_model_output_sha256=admission["raw_model_output_sha256"], previous_validation=deepcopy(old),
        previous_validation_sha256=digest(old), new_validation=deepcopy(validation), new_validation_sha256=digest(validation),
        validator_guard_sha256=guard_sha, validator_version=version,
        revalidated_at=(now or datetime.now(timezone.utc)).isoformat(), new_model_request=False,
        original_model_output_unchanged=True, publication_approved=False, quote_validation_is_semantic_approval=False)


def new_fast_attempt_receipt(raw, model, validation, *, now=None):
    admission, _ = verified_processing_mode(raw)
    expected, guard_sha, version = _validation(raw, model)
    response_id = model.get("_pulso_analysis_meta", {}).get("response_id")
    ids = {record["new_response_id"] for record in raw.metadata.get(previous.NEW_FAST_RECEIPTS, [])}
    if (not admission["new_model_request"] or not response_id or response_id in ids
            or validation != expected or validation.get("reason") == "pulso_editorial_model_binding_mismatch"):
        raise ValueError("current_paid_new_fast_response_reused_or_unbound")
    return dict(schema_version="pulso_current_paid_new_fast_attempt_receipt_v1", admission_id=admission["admission_id"],
        original_response_id=admission["original_response_id"], new_response_id=response_id,
        full_model_output=deepcopy(model), model_output_sha256=digest(model), new_validation=deepcopy(validation),
        new_validation_sha256=digest(validation), validator_guard_sha256=guard_sha, validator_version=version,
        assessed_at=(now or datetime.now(timezone.utc)).isoformat(), new_model_request=True, publication_approved=False)
