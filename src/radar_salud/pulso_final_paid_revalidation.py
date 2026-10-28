"""Revalidate exactly two genuine c2db paid answers without another model call.

The original validator failure, request, response and all three earlier repair
histories stay immutable. The ordinary media gate decides publication.
"""
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .pinned_evidence import pinned_bytes
import json
import subprocess

from . import pulso_paid_revalidation as legacy
from . import pulso_current_paid_revalidation as current
from . import pulso_followup_paid_revalidation as followup
from .models import RawItem

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_REF = "data/audits/pulso_final2_paid_guard_revalidation_manifest_2026_10_11.json"
MANIFEST_SHA256 = "78020e40fa2ff47c59086faf58bd8413122866e25221d0a99131150cb25e0534"
PRODUCER_STATE = "323b73ef5fb0ec39410024c21d70e6fd99b065e2"
PRODUCER_CODE = "c2db17141fd55cbacbcda5b53805341aa4dfa86f"
PRODUCER_FINGERPRINT = "c960999eea01aed6e578d0ca1354cb5f45b8720ae8832993d609d0db540b0406"
PRODUCER_FILES = {
    "data/state/pending_queue.json": "b5fb262284e5ce28e6b9664703f2a94996ad7abef128a7f1c679fc0a83b26481",
    "data/audits/pulso_runtime_2026_10_11.json": "c746b44864dceb465c2d72889ed48e15510fcb7286f8d0840545f584afe6793e",
    "data/ai_usage/responses.jsonl": "19bb3e6b2ae1e15c623a97eb08ae6b3f323b1c11cec6fa74aad359f3ca04cfad",
    "data/history/superintendencia_signals.json": "39e63cc84af25227fc7cf916ab42867ab8a84a085cb6fffb3b920aa2ba0ed11a"
}
VALIDATOR_GUARD_SHA256 = "cfdfc0914a1e6d145d932ffe29063eae3be0cf72a977a522dd7e454772cb241b"
KNOWN_URLS = {
    "https://www.latercera.com/nacional/noticia/todas-somos-vulnerables-minsal-refuerza-el-llamado-a-la-deteccion-precoz-del-cancer-de-mama-para-un-tratamiento-oportuno/",
    "https://www.latercera.com/nacional/noticia/el-mapa-del-hanta-residentes-rurales-de-los-lagos-nuble-y-biobio-enfrentan-la-mayor-amenaza/",
}
STAMP = "final_paid_guard_revalidation_admission"
RECEIPT = "final_paid_guard_revalidation_receipt"
REVISION = "verified_final_paid_guard_revalidation_admission"
PRIOR_FIELDS = (legacy.STAMP, legacy.RECEIPT, legacy.NEW_FAST_RECEIPTS,
                current.STAMP, current.RECEIPT, current.NEW_FAST_RECEIPTS,
                followup.STAMP, followup.RECEIPT, followup.NEW_FAST_RECEIPTS,
                "editorial_code_repair_admission")
digest = legacy.digest
paid_raw = legacy.paid_raw


def has_claim(metadata):
    return (STAMP in metadata or RECEIPT in metadata
            or any(isinstance(revision, dict) and revision.get("reason") == REVISION
                   for revision in metadata.get("evidence_revisions", [])))


def known_original_candidate(raw):
    """A known primary URL cannot fall back after claims or responses change."""
    if raw.source_slug != "pulso_latercera":
        return False
    return raw.url in KNOWN_URLS


def _stamp(value):
    if not isinstance(value, str):
        raise ValueError("final_paid_receipt_timestamp_missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("final_paid_receipt_timestamp_timezone_missing")
    return parsed


@lru_cache(maxsize=2)
def producer(root):
    objects = {}
    if len(PRODUCER_FILES) != 4:
        raise ValueError("final_paid_original_producer_pins_missing")
    for path, expected in PRODUCER_FILES.items():
        result = subprocess.run(["git", "show", PRODUCER_STATE + ":" + path], cwd=root, capture_output=True)
        if result.returncode or digest(result.stdout) != expected:
            raise ValueError("final_paid_original_producer_blob_unavailable_or_changed")
        objects[path] = result.stdout
    report = json.loads(objects["data/audits/pulso_runtime_2026_10_11.json"])
    execution = report.get("last_core_execution") or report["execution"]
    if (execution.get("code_sha") != PRODUCER_CODE
            or execution.get("runtime_fingerprint", {}).get("sha256") != PRODUCER_FINGERPRINT
            or execution.get("mode") != "real_core_processing"
            or execution.get("engine_called") is not True or execution.get("engine_completed") is not True
            or execution.get("ai_guardrails_modified") is not False
            or execution.get("processing_selection", {}).get("sha256") != "8ed358f0cd37ecc4b554ab96cd4366048b8e6180ad1c0ee0044fc5d5f6976514"):
        raise ValueError("final_paid_original_execution_unverified")
    events = [json.loads(line) for line in objects["data/ai_usage/responses.jsonl"].splitlines() if line]
    events = [event for event in events if _stamp(execution["started_at"]) <= _stamp(event["at"]) <= _stamp(execution["finished_at"])]
    ids = {event.get("response_id") for event in events}
    if (len(events) != 2 or len(ids) != 2 or None in ids
            or any(event.get("kind") != "fast" or event.get("success") is not True for event in events)):
        raise ValueError("final_paid_original_two_response_receipts_unverified")
    for field in ("attempted", "successful"):
        if (execution["budget_after"]["month"]["fast"][field]
                - execution["budget_before"]["month"]["fast"][field] != 2
                or execution["budget_after"]["month"]["deep"][field] != execution["budget_before"]["month"]["deep"][field]):
            raise ValueError("final_paid_original_positive_ledger_unverified")
    queue = json.loads(objects["data/state/pending_queue.json"])
    held = {key: entry for key, entry in queue.items() if entry.get("source") == "pulso_latercera"
            and entry.get("status") == "retry" and entry.get("raw", {}).get("metadata", {}).get(
                "analysis_model_output", {}).get("_pulso_analysis_meta", {}).get("response_id") in ids}
    if len(held) != 2:
        raise ValueError("final_paid_complete_original_two_required")
    path = "src/radar_salud/pulso_editorial_proof.py"
    code = subprocess.run(["git", "show", PRODUCER_CODE + ":" + path], cwd=root,
                          capture_output=True, check=True).stdout
    if digest(code) != execution["runtime_fingerprint"]["files"][path]:
        raise ValueError("final_paid_original_guard_not_execution_bound")
    namespace = {"__name__": "radar_salud._original_final_paid_guard", "__file__": str(Path(root) / path)}
    exec(compile(code, namespace["__file__"], "exec"), namespace)
    for entry in held.values():
        raw, meta = entry["raw"], entry["raw"]["metadata"]
        model = meta["analysis_model_output"]
        validation = namespace["validate_pulso_editorial_proof"](model, meta["page_text"])
        validation.update(primary_article_body_sha256=meta["analysis_base_article_body_sha256"],
                          request_input_sha256=meta["analysis_request_input_sha256"],
                          model_response=model["_pulso_analysis_meta"])
        receipts = meta.get(followup.NEW_FAST_RECEIPTS, [])
        if (type(entry.get("attempts")) is not int or entry["attempts"] != 5
                or validation != meta["pulso_editorial_proof_validation"] or validation["decision"] != "deferred"
                or entry.get("reason") != validation["reason"]
                or meta.get("editorial_assessment", {}).get("decision") != "pending"
                or meta["editorial_assessment"].get("reason") != validation["reason"]
                or meta["editorial_assessment"].get("threshold") != 72
                or len(receipts) != 1 or receipts[-1]["full_model_output"] != model
                or receipts[-1]["new_validation"] != validation
                or receipts[-1]["new_response_id"] != model["_pulso_analysis_meta"]["response_id"]
                or not _stamp(execution["started_at"]) <= _stamp(receipts[-1]["assessed_at"]) <= _stamp(execution["finished_at"])
                or not namespace["model_binding_matches"](model, source_name=raw["source_name"],
                    input_text_sha256=meta["analysis_input_body_sha256"],
                    request_input_sha256=meta["analysis_request_input_sha256"])):
            raise ValueError("final_paid_original_answer_or_validation_not_genuine")
        followup.verified_processing_mode(RawItem(**deepcopy(raw)))
        current.verified_processing_mode(RawItem(**deepcopy(raw)))
        legacy.verified_paid_processing_mode(RawItem(**deepcopy(raw)))
    return dict(held=held, queue=queue, execution=execution, events=events)


def original_pin(key, entry):
    return legacy.original_pin(key, entry)


def load_manifest(root=ROOT):
    root = Path(root)
    payload = pinned_bytes(root, MANIFEST_REF, MANIFEST_SHA256)
    if digest(payload) != MANIFEST_SHA256:
        raise ValueError("final_paid_revalidation_manifest_unpinned")
    document = json.loads(payload)
    if (document.get("schema_version") != "pulso_final_paid_guard_revalidation_manifest_v1"
            or document.get("source_id") != "pulso_latercera"
            or document.get("producer_state_commit") != PRODUCER_STATE
            or document.get("producer_core_checkout") != PRODUCER_CODE
            or document.get("producer_runtime_fingerprint_sha256") != PRODUCER_FINGERPRINT
            or document.get("validator_guard_sha256") != VALIDATOR_GUARD_SHA256):
        raise ValueError("final_paid_revalidation_manifest_origin_or_validator_changed")
    refs = document.get("semantic_references", [])
    if len(refs) != 2 or len({ref.get("path") for ref in refs}) != 2:
        raise ValueError("final_paid_two_independent_current_response_reviews_required")
    for ref in refs:
        path = (root / ref["path"]).resolve()
        if not path.is_relative_to((root / "data/audits").resolve()) or digest(pinned_bytes(root, ref["path"], ref["sha256"])) != ref["sha256"]:
            raise ValueError("final_paid_semantic_review_unavailable_or_changed")
    origin = producer(str(root))
    rows = document.get("rows", [])
    if (len(rows) != 2 or {row.get("url") for row in rows} != KNOWN_URLS
            or {row.get("queue_fingerprint") for row in rows} != set(origin["held"])):
        raise ValueError("final_paid_complete_original_two_required")
    for row in rows:
        entry = origin["held"][row["queue_fingerprint"]]
        raw, meta = entry["raw"], entry["raw"]["metadata"]
        expected = dict(original_pin(row["queue_fingerprint"], entry),
                        original_full_primary_body=meta["page_text"],
                        original_full_model_output=meta["analysis_model_output"],
                        actual_pulso_validation=meta["pulso_editorial_proof_validation"],
                        actual_queue_entry_sha256=digest(entry), original_raw_sha256=digest(raw),
                        original_metadata_sha256=digest(meta))
        if (any(row.get(field) != value for field, value in expected.items())
                or row.get("runtime_route") != "reuse_code_fn" or row.get("disposition") != "reuse_code_fn"
                or row.get("publication_approved") is not False or row.get("new_model_request") is not False
                or not legacy._primary_matches(RawItem(**deepcopy(raw)), row)):
            raise ValueError("final_paid_original_response_or_primary_pins_changed")
    return document, origin


def _admission(row):
    value = dict(schema_version="pulso_final_paid_guard_revalidation_admission_v1",
                 manifest_ref=MANIFEST_REF, manifest_sha256=MANIFEST_SHA256,
                 producer_state_commit=PRODUCER_STATE, producer_core_checkout=PRODUCER_CODE,
                 producer_runtime_fingerprint_sha256=PRODUCER_FINGERPRINT,
                 validator_guard_sha256=VALIDATOR_GUARD_SHA256, disposition="reuse_code_fn",
                 new_model_request=False, publication_approved=False)
    value.update({field: row[field] for field in legacy.original_pin_fields()})
    value["admission_id"] = digest(value)
    return value


def verified_admission(fresh, existing):
    try:
        if (existing.get("status") not in {"pending", "retry"}
                or type(existing.get("attempts")) is not int or existing["attempts"] != 5
                or has_claim(existing.get("raw", {}).get("metadata", {}))):
            return None
        document, origin = load_manifest()
        row = next(row for row in document["rows"] if row["url"] == fresh.url)
        if existing != origin["held"][row["queue_fingerprint"]] or not legacy._primary_matches(fresh, row):
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
    if (meta.get(STAMP) != expected or not legacy._primary_matches(raw, row)
            or len(revisions) != 1 or revisions[0].get(STAMP) != expected
            or revisions[0].get("previous_processing_raw") != paid_raw(original["raw"])
            or any(meta.get(field) != old.get(field) for field in PRIOR_FIELDS)
            or meta.get("evidence_revisions", [])[:len(old["evidence_revisions"])] != old["evidence_revisions"]
            or meta.get("analysis_model_output") != old["analysis_model_output"]):
        raise ValueError("final_paid_primary_or_admission_or_prior_archive_unverified")
    receipt = meta.get(RECEIPT)
    if receipt is None:
        if meta.get("pulso_editorial_proof_validation") != old["pulso_editorial_proof_validation"]:
            raise ValueError("final_paid_original_validation_changed_without_receipt")
    else:
        computed = _receipt(raw, meta["analysis_model_output"], meta.get("pulso_editorial_proof_validation"),
                            expected, original, receipt.get("revalidated_at"))
        if receipt != computed:
            raise ValueError("final_paid_current_validation_receipt_unverified")
    return expected, original


def unchanged_output(raw):
    _, original = verified_processing_mode(raw)
    return deepcopy(original["raw"]["metadata"]["analysis_model_output"])


def _validation(raw, model):
    from . import pulso_editorial_proof as guard
    guard_sha = digest(Path(guard.__file__).read_bytes())
    if guard_sha != VALIDATOR_GUARD_SHA256:
        raise ValueError("final_paid_validator_bytes_not_pinned")
    value = guard.validate_pulso_editorial_proof(model, raw.metadata["page_text"])
    value.update(primary_article_body_sha256=raw.metadata["analysis_base_article_body_sha256"],
                 request_input_sha256=raw.metadata["analysis_request_input_sha256"],
                 model_response=model.get("_pulso_analysis_meta"))
    if not guard.model_binding_matches(model, source_name=raw.source_name,
            input_text_sha256=raw.metadata["analysis_input_body_sha256"],
            request_input_sha256=raw.metadata["analysis_request_input_sha256"]):
        value.update(decision="deferred", reason="pulso_editorial_model_binding_mismatch")
    return value, guard_sha, guard.VERSION


def _receipt(raw, model, validation, admission, original, at):
    expected, guard_sha, version = _validation(raw, model)
    if model != original["raw"]["metadata"]["analysis_model_output"] or validation != expected:
        raise ValueError("final_paid_unchanged_output_or_actual_guard_result_unverified")
    old = original["raw"]["metadata"]["pulso_editorial_proof_validation"]
    _stamp(at)
    return dict(schema_version="pulso_final_paid_guard_revalidation_receipt_v1", admission=deepcopy(admission),
                producer_state_commit=PRODUCER_STATE, producer_core_checkout=PRODUCER_CODE,
                producer_runtime_fingerprint_sha256=PRODUCER_FINGERPRINT,
                original_response_id=admission["original_response_id"], original_model_output_sha256=admission["model_output_sha256"],
                original_raw_model_output_sha256=admission["raw_model_output_sha256"], previous_validation=deepcopy(old),
                previous_validation_sha256=digest(old), new_validation=deepcopy(validation), new_validation_sha256=digest(validation),
                validator_guard_sha256=guard_sha, validator_version=version, revalidated_at=at,
                new_model_request=False, original_model_output_unchanged=True,
                publication_approved=False, quote_validation_is_semantic_approval=False)


def revalidation_receipt(raw, model, validation, *, now=None):
    admission, original = verified_processing_mode(raw)
    return _receipt(raw, model, validation, admission, original,
                    (now or datetime.now(timezone.utc)).isoformat())
