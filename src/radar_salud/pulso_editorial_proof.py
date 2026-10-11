"""Ground Pulso's single-call editorial assessment in its complete input text.

Literal quotes establish provenance, not independent semantic approval. The
unchanged relevance/publication gates and independent publication review still
apply after this validator permits editorial processing to continue.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata

VERSION = "pulso_editorial_proof_v4"
SCOPES = ("human_health_specific", "incidental_health", "non_human_health", "marketing", "opinion")
STATUSES = ("actual", "proposal", "plan", "mixed_actual_and_future", "historical_context")
NOVELTY = ("new_material_information", "repetition_or_context", "uncertain")
FUTURE_SOURCE = re.compile(r"\b(?:habr[aá]|permitir[aá]n?|ser[aá]n?|podr[ií]an?|previst[oa]s?|"
                           r"se prev[eé]|se propone(?:n)?|incorporar[aá]n?|alcanzar[aá]n?|implementar[aá]n?)\b", re.I)
FORMAL_BUDGET_PROJECT = re.compile(r"\bproyecto de (?:ley de )?presupuestos?\b", re.I)
REFERENCED_BUDGET_PROJECT = re.compile(
    r"\ben (?:el|este) proyecto\b[^.;!?]{0,80}\bpresupuesto\b", re.I)
# Approval/enactment is an actual legislative step when it explicitly governs
# this same formal budget project. A bare project reference is still a proposal.
ACTUAL_BUDGET_LEGISLATIVE_STEP = re.compile(
    r"\b(?:aprob[oó]|promulg[oó])\s+(?:el\s+)?proyecto de (?:ley de )?presupuestos?\b|"
    r"\bproyecto de (?:ley de )?presupuestos?\b[^.;!?]{0,80}\b"
    r"(?:fue|ha sido)\s+(?:aprobado|promulgado)\b", re.I)
FUTURE_COPY = re.compile(r"\b(?:propuest[oa]s?|propon\w*|proyecto|plan(?:ea|eado)?|prev[eé]|"
                         r"previst[oa]s?|proyect\w*|habr[aá]|permitir[aáí]\w*|"
                         r"podr[ií]\w*|puede\w*|ser[aá]n?|futur[oa]s?|de aprobarse|"
                         r"incorporar[aá]n?|alcanzar[aá]n?|implementar[aá]n?|ampliar[aá]n?|"
                         r"si se (?:aprueba|implementa|concreta))\b", re.I)
ACHIEVED_COPY = re.compile(r"\b(?:ya (?:se )?(?:alcanz\w*|incorpor\w*|aument\w*|ampli\w*|"
                           r"implement\w*|ejecut\w*|concret\w*)|"
                           r"se ejecut[oó]|termin[oó])\b", re.I)
NON_HUMAN_HEALTH = re.compile(
    r"\b(?:salud|sanidad)\s+(?:animal(?:\s+o\s+vegetal)?|vegetal|veterinari[ao])\b|"
    r"\b(?:cl[ií]nic\w*|hospital\w*|medicin\w*|vacun\w*)\s+veterinari\w*", re.I)

PROOF_SCHEMA = {
    "type": "object", "properties": {
        "scope_decision": {"type": "string", "enum": list(SCOPES)},
        "scope_reason": {"type": "string"},
        "human_health_scope_quote": {"type": "string"},
        **{name: {"type": "string"} for name in (
            "actor", "actor_quote", "action", "action_quote", "consequence", "consequence_quote")},
        "event_status": {"type": "string", "enum": list(STATUSES)},
        "event_status_quote": {"type": "string"},
        "novelty_decision": {"type": "string", "enum": list(NOVELTY)},
        "novelty_reason": {"type": "string"},
        "novelty_quote": {"type": "string"},
        "future_claims": {"type": "array", "items": {
            "type": "object", "properties": {
                "summary_field": {"type": "string", "enum": ["what_happened", "why_it_matters"]},
                "summary_quote": {"type": "string"}, "source_quote": {"type": "string"}},
            "required": ["summary_field", "summary_quote", "source_quote"], "additionalProperties": False}},
    }, "additionalProperties": False,
}
PROOF_SCHEMA["required"] = list(PROOF_SCHEMA["properties"])


def normalized(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def validate_pulso_editorial_proof(analysis, analysis_text):
    """Return ready/rejected/deferred without inventing a score or publication."""
    result = dict(version=VERSION, source="pulso_latercera",
                  analysis_text_sha256=hashlib.sha256(analysis_text.encode()).hexdigest(),
                  quote_validation_is_semantic_approval=False, publication_approved=False)
    def verdict(decision, reason, **extra):
        return dict(result, decision=decision, reason=reason, **extra)
    if not isinstance(analysis, dict):
        return verdict("deferred", "pulso_editorial_proof_missing")
    result["model_output_sha256"] = hashlib.sha256(json.dumps(
        analysis, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    proof = analysis.get("pulso_editorial_proof")
    if not isinstance(proof, dict):
        return verdict("deferred", "pulso_editorial_proof_missing")
    result["proof"] = proof
    if set(proof) != set(PROOF_SCHEMA["properties"]):
        return verdict("deferred", "pulso_editorial_proof_invalid_schema")
    if (proof.get("scope_decision") not in SCOPES or proof.get("event_status") not in STATUSES
            or proof.get("novelty_decision") not in NOVELTY):
        return verdict("deferred", "pulso_editorial_proof_invalid_schema")
    score = analysis.get("relevance_score")
    if type(score) is not int or not 0 <= score <= 100:
        return verdict("deferred", "pulso_editorial_proof_invalid_score")
    if any(not isinstance(analysis.get(field), str) for field in ("what_happened", "why_it_matters", "reason")):
        return verdict("deferred", "pulso_editorial_analysis_invalid_schema")
    string_fields = set(PROOF_SCHEMA["properties"]) - {"future_claims"}
    if (any(not isinstance(proof.get(field), str) for field in string_fields)
            or not isinstance(proof.get("future_claims"), list)):
        return verdict("deferred", "pulso_editorial_proof_invalid_schema")
    if len(proof["scope_reason"].strip()) < 12:
        return verdict("deferred", "pulso_editorial_scope_reason_missing")
    body = normalized(analysis_text)
    def quote_matches(value, minimum=20):
        return isinstance(value, str) and len(normalized(value)) >= minimum and normalized(value) in body
    if not quote_matches(proof["human_health_scope_quote"]):
        return verdict("deferred", "pulso_editorial_scope_quote_not_in_input")
    if proof["scope_decision"] != "human_health_specific":
        return verdict("rejected", "pulso_editorial_" + proof["scope_decision"])
    from .pulso_source import health_anchor
    scope_quote = proof["human_health_scope_quote"]
    # A generic discovery anchor deliberately admits animal/plant references.
    # They cannot substantiate a human-health editorial assertion on their own.
    # Preserve any independent human-health evidence in the same primary quote,
    # and defer contradictory model labels rather than infer a rejection.
    if (NON_HUMAN_HEALTH.search(scope_quote)
            and not health_anchor(NON_HUMAN_HEALTH.sub("", scope_quote))):
        return verdict("deferred", "pulso_editorial_human_scope_conflicts_with_non_human_quote")
    if not health_anchor(scope_quote):
        return verdict("deferred", "pulso_editorial_scope_not_grounded")
    for field, minimum in (("actor", 8), ("action", 20), ("consequence", 20)):
        quote = proof[field + "_quote"]
        value = proof[field]
        if (not quote_matches(quote, minimum) or len(value.strip()) < 3
                or normalized(value).casefold() not in normalized(quote).casefold()):
            return verdict("deferred", "pulso_editorial_" + field + "_not_grounded")
    if (not quote_matches(proof["event_status_quote"], 12)
            or not quote_matches(proof["novelty_quote"])
            or len(proof["novelty_reason"].strip()) < 12):
        return verdict("deferred", "pulso_editorial_status_or_novelty_not_grounded")
    if proof["novelty_decision"] == "uncertain":
        return verdict("deferred", "pulso_editorial_incremental_value_uncertain")
    if proof["novelty_decision"] == "repetition_or_context" or proof["event_status"] == "historical_context":
        return verdict("rejected", "pulso_editorial_repetition_or_context")
    future = proof["event_status"] in ("proposal", "plan", "mixed_actual_and_future")
    claims = proof["future_claims"]
    if not isinstance(claims, list):
        return verdict("deferred", "pulso_editorial_future_claims_invalid")
    if not future and (claims or any(
            FUTURE_SOURCE.search(proof[field])
            or ((FORMAL_BUDGET_PROJECT.search(proof[field])
                 or (FORMAL_BUDGET_PROJECT.search(body)
                     and REFERENCED_BUDGET_PROJECT.search(proof[field])))
                and not ACTUAL_BUDGET_LEGISLATIVE_STEP.search(proof[field])) for field in (
            "event_status_quote", "action_quote", "consequence_quote"))):
        return verdict("deferred", "pulso_editorial_future_status_mismatch")
    covered = set()
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {"summary_field", "summary_quote", "source_quote"}:
            return verdict("deferred", "pulso_editorial_future_claims_invalid")
        field = claim["summary_field"]
        summary = analysis.get(field)
        if (field not in ("what_happened", "why_it_matters") or not isinstance(summary, str)
                or not isinstance(claim["summary_quote"], str)
                or not normalized(claim["summary_quote"])
                or normalized(claim["summary_quote"]) != normalized(summary)
                or not quote_matches(claim["source_quote"])
                or not FUTURE_COPY.search(claim["summary_quote"])
                or ACHIEVED_COPY.search(claim["summary_quote"])):
            return verdict("deferred", "pulso_editorial_future_copy_not_grounded")
        covered.add(field)
    if future and covered != {"what_happened", "why_it_matters"}:
        return verdict("deferred", "pulso_editorial_future_copy_not_grounded")
    return verdict("ready", "pulso_editorial_grounded_assessment", prospective_evidence=future)


def model_binding_matches(analysis, *, source_name, input_text_sha256, request_input_sha256):
    """The structured answer must identify the same complete model request."""
    meta = analysis.get("_pulso_analysis_meta") if isinstance(analysis, dict) else None
    return bool(isinstance(meta, dict) and meta.get("schema_version") == VERSION
                and meta.get("source_name") == source_name
                and meta.get("analysis_text_sha256") == input_text_sha256
                and meta.get("request_input_sha256") == request_input_sha256
                and isinstance(meta.get("response_id"), str) and meta["response_id"].strip()
                and isinstance(meta.get("model"), str) and meta["model"].strip()
                and isinstance(meta.get("raw_model_output_sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", meta["raw_model_output_sha256"]))
