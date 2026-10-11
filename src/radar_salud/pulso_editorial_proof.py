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
from pathlib import Path

VERSION = "pulso_editorial_proof_v5"
REPAIR_ADMISSION_PIN_SHA256 = "7f915bf1f8b4ee14d6426a41541cf3b6c319ad2e2acd384b8cc9fefa53224731"
REPAIR_COHORT_SHA256 = "8ed358f0cd37ecc4b554ab96cd4366048b8e6180ad1c0ee0044fc5d5f6976514"
SCOPES = ("human_health_specific", "incidental_health", "non_human_health", "marketing", "opinion")
STATUSES = ("actual", "proposal", "plan", "mixed_actual_and_future", "historical_context")
NOVELTY = ("new_material_information", "repetition_or_context", "uncertain")
# Spanish regular future inflection in the selected primary evidence, rather
# than a growing list of health measures. A judicial/operative obligation
# 'deberán pagar' can already be an actual binding decision and is not a plan.
REGULAR_FUTURE_VERB = (
    r"\b(?!deber[aá]n?\b)[a-záéíóúñü]{3,}(?:ar|er|ir)(?:é|ás?|emos|éis|án)\b")
# Regular conditional inflection is not a completed outcome. Exclude common
# nouns with the same ending rather than treating 'secretaría' as a proposal.
REGULAR_CONDITIONAL_VERB = (
    r"\b(?!(?:secretar[ií]a|comisar[ií]a|notar[ií]a|enfermer[ií]a|"
    r"ingenier[ií]a|miner[ií]a|loter[ií]a|porter[ií]a|guarder[ií]a|"
    r"panader[ií]a|librer[ií]a|tesorer[ií]a|bater[ií]a|consejer[ií]a)\b)"
    r"[a-záéíóúñü]{3,}(?:ar|er|ir)ía(?:s|mos|is|n)?\b")
FUTURE_SOURCE = re.compile(REGULAR_FUTURE_VERB + r"|\b(?:habr[aá]|permitir[aá]n?|ser[aá]n?|podr(?:[aá]n?|[ií]an?)|previst[oa]s?|"
                           r"se prev[eé]|se propone(?:n)?|incorporar[aá]n?|alcanzar[aá]n?|implementar[aá]n?|"
                           r"coordinaci(?:ones|[oó]n)\b[^.;!?]{0,160}\bpara instalar|"
                           r"se estima que tendr[aá]n?|se espera una inyecci[oó]n de recursos)\b", re.I)
FORMAL_BUDGET_PROJECT = re.compile(r"\bproyecto de (?:ley de )?presupuestos?\b", re.I)
REFERENCED_BUDGET_PROJECT = re.compile(
    r"\ben (?:el|este) proyecto\b[^.;!?]{0,80}\bpresupuesto\b", re.I)
# Approval/enactment is an actual legislative step when it explicitly governs
# this same formal budget project. A bare project reference is still a proposal.
ACTUAL_BUDGET_LEGISLATIVE_STEP = re.compile(
    r"\b(?:aprob[oó]|promulg[oó])\s+(?:el\s+)?proyecto de (?:ley de )?presupuestos?\b|"
    r"\bproyecto de (?:ley de )?presupuestos?\b[^.;!?]{0,80}\b"
    r"(?:fue|ha sido)\s+(?:aprobado|promulgado)\b", re.I)
FUTURE_COPY = re.compile(REGULAR_CONDITIONAL_VERB + r"|\b(?:propuest[oa]s?|propon\w*|proyecto|plan(?:ea|eado)?|prev[eé]|"
                         r"previst[oa]s?|proyect\w*|habr[aá]|permitir[aáí]\w*|"
                         r"podr(?:[aá]n?|[ií]\w*)|deber[aá]n?|eventual(?:es)?|puede\w*|ser[aá]n?|futur[oa]s?|de aprobarse|"
                         r"(?:habr|tendr|vendr|pondr|saldr|cabr|dir|har|querr|sabr|ser|ir)[ií]a(?:s|mos|is|n)?|"
                         r"incorporar[aá]n?|alcanzar[aá]n?|implementar[aá]n?|ampliar[aá]n?|"
                         r"si se (?:aprueba|implementa|concreta)|"
                         r"a[uú]n (?:est[aá] )?en fase de coordinaci[oó]n|"
                         r"todav[ií]a no constituye capacidad disponible)\b", re.I)
ACHIEVED_COPY = re.compile(r"\b(?:ya (?:se )?(?:alcanz\w*|incorpor\w*|aument\w*|ampli\w*|"
                           r"implement\w*|ejecut\w*|concret\w*|instal\w*|realiz\w*)|"
                           r"ya (?:tiene|dispone de|cuenta con)\b[^.;!?]{0,80}\bcapacidad disponible|"
                           r"se ejecut[oó]|termin[oó])\b", re.I)
# Actual v5 answers use the past tense to describe an intention or estimate as
# observed on an earlier publication day. Only accept these narrower phrases
# with explicit observation-date/publication context in the complete field.
OBSERVATION_DATE_COPY = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}-\d{2}-\d{4}\b|"
    r"\b\d{1,2} de (?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre) de \d{4}\b|"
    r"\ba la fecha de publicaci[oó]n\b", re.I)
HISTORICAL_FUTURE_COPY = re.compile(
    r"\b(?:pod[ií]an?|deb[ií]an?|pudiera[n]?|pudiese[n]?|condicionalmente|"
    r"condicionad[oa]s?|se esperaba|pretend[ií]an?|intenci[oó]n anunciada|"
    r"posibilidad en evaluaci[oó]n|efecto esperado|capacidad estimada|"
    r"estimaci[oó]n reportada|actuaci[oó]n posterior|pr[oó]ximo juicio|"
    r"objetivo era|buscaba[n]?|programad[oa]s?|"
    r"no acredita|no demuestra|no permite (?:afirmar|verificar))\b", re.I)
NEGATED_ACHIEVEMENT_PREFIX = re.compile(
    r"\bno\s*$|\bno como (?:resultados|acciones|medidas|logros)\s*$|"
    r"\bno (?:deben?|pueden?) (?:entenderse|considerarse|presentarse|tratarse) como\s*$",
    re.I)
NON_HUMAN_HEALTH = re.compile(
    r"\b(?:salud|sanidad)\s+(?:animal(?:\s+o\s+vegetal)?|vegetal|veterinari[ao])\b|"
    r"\b(?:cl[ií]nic\w*|hospital\w*|medicin\w*|vacun\w*)\s+veterinari\w*|"
    r"\batenci[oó]n m[eé]dica (?:de|a|para) (?:los |las )?(?:animales|mascotas)\b|"
    r"\bpacientes? (?:animales|veterinari\w*)\b|"
    r"\b(?:procedimientos? cl[ií]nicos?|ex[aá]menes? de diagn[oó]stico) veterinari\w*", re.I)

# These clinical terms are present in exact quotes from the first real model
# cohort but absent from the broader discovery anchor. Keep this check local to
# editorial proof; generic sector/team/demographic wording is insufficient.
HUMAN_CLINICAL_SCOPE = re.compile(
    r"\bminsal\b|\bcolmed\b|\bred asistencial\b|\boncol[oó]g\w*|"
    r"\bconsultas? de especialidad\b|\bcirug[ií]as? est[eé]ticas?\b|"
    r"\benfermedades? (?:catastr[oó]ficas?|no transmisibles?)\b|"
    r"\b(?:listeriosis|sepsis|meningitis|meningoencefalitis|virus respiratorios?)\b|"
    r"\bconsumo humano\b|\bm[eé]dicos\b[^.;!?]{0,180}\binterrupci[oó]n del embarazo\b|"
    r"\batenci[oó]n (?:de (?:los )?pacientes|m[eé]dica)\b|"
    r"\bprocedimientos? cl[ií]nicos?\b|\bex[aá]menes? de diagn[oó]stico\b|"
    r"\bacceder a una consulta, procedimiento o tratamiento\b|"
    r"\balerta alimentaria\b[^.;!?]{0,120}\blisteria monocytogenes\b|"
    r"\bpersona presenta s[ií]ntomas\b[^.;!?]{0,180}\bsospechar y testear\b", re.I)


def human_health_scope_anchor(quote):
    from .pulso_source import health_anchor
    return health_anchor(quote) or bool(HUMAN_CLINICAL_SCOPE.search(quote))

PROOF_SCHEMA = {
    "type": "object", "properties": {
        "scope_decision": {"type": "string", "enum": list(SCOPES)},
        "scope_reason": {"type": "string"},
        "human_health_scope_quote": {"type": "string", "description": "Copia un fragmento CONTIGUO literal del contenido (mínimo 20 caracteres) que nombre el vínculo directo de salud humana; no una frase genérica de sector/equipo."},
        **{name: {"type": "string", "description":
                 ("Fragmento breve EXACTO copiado dentro de " + name + "_quote (mínimo 3 caracteres). No lo parafrasees, no agregues actores ni cambies verbos o cifras.")}
           for name in ("actor", "action", "consequence")},
        **{name + "_quote": {"type": "string", "description":
                 ("Copia UN fragmento CONTIGUO literal del contenido, mínimo " + str(minimum) + " caracteres, que incluya el valor de " + name + ". Sin comillas exteriores añadidas, elipsis ni unión de fragmentos separados.")}
           for name, minimum in (("actor", 8), ("action", 20), ("consequence", 20))},
        "event_status": {"type": "string", "enum": list(STATUSES)},
        "event_status_quote": {"type": "string", "description": "Cita CONTIGUA literal del contenido, mínimo 12 caracteres. Demuestra estado real/propuesta/plan sin unir frases separadas."},
        "novelty_decision": {"type": "string", "enum": list(NOVELTY)},
        "novelty_reason": {"type": "string"},
        "novelty_quote": {"type": "string", "description": "Cita CONTIGUA literal del contenido, mínimo 20 caracteres, que sustente información material nueva; sin elipsis ni paráfrasis."},
        "future_claims": {"type": "array", "items": {
            "type": "object", "properties": {
                "summary_field": {"type": "string", "enum": ["what_happened", "why_it_matters"]},
                "summary_quote": {"type": "string", "description": "Copia TODO el campo what_happened o why_it_matters correspondiente, idéntico, incluyendo todas sus frases. Ambos campos deben distinguir explícitamente futuro/condicional de logros reales."},
                "source_quote": {"type": "string", "description": "Cita CONTIGUA literal del contenido, mínimo 20 caracteres, que sustenta la medida futura o condicional."}},
            "required": ["summary_field", "summary_quote", "source_quote"], "additionalProperties": False}},
    }, "additionalProperties": False,
}
PROOF_SCHEMA["required"] = list(PROOF_SCHEMA["properties"])


def normalized(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def literal_quote_form(value):
    """Equivalent typography only; retain words, numbers and all punctuation."""
    return normalized(value).translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})).casefold()


def literal_quote_matches(value, body, minimum=20):
    if not isinstance(value, str):
        return False
    quote = literal_quote_form(value)
    if len(quote) < minimum:
        return False
    primary = literal_quote_form(body)
    if quote in primary:
        return True
    # A model-added quotation wrapper has no factual content. Removing exactly
    # one matching exterior pair still requires the complete inner contiguous
    # sequence, including punctuation and any negations/numbers, in the source.
    return (len(quote) >= minimum + 2 and quote[0] == quote[-1] and quote[0] in ('"', "'")
            and quote[1:-1] in primary)


def future_copy_qualified(value):
    return bool(FUTURE_COPY.search(value) or (
        OBSERVATION_DATE_COPY.search(value) and HISTORICAL_FUTURE_COPY.search(value)))


def unqualified_achieved_copy(value):
    """A local explicit denial is not an assertion of completed execution."""
    for match in ACHIEVED_COPY.finditer(value):
        # A denial in another clause cannot cancel an achievement assertion.
        prefix = re.split(r"[.,;:!?]", value[:match.start()])[-1]
        if not NEGATED_ACHIEVEMENT_PREFIX.search(prefix):
            return True
    return False


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
    # Validate nested structure before the conservative score rejection too.
    # A malformed provider response cannot be turned into an editorial verdict.
    for claim in proof["future_claims"]:
        if (not isinstance(claim, dict)
                or set(claim) != {"summary_field", "summary_quote", "source_quote"}
                or claim["summary_field"] not in ("what_happened", "why_it_matters")
                or not isinstance(claim["summary_quote"], str)
                or not isinstance(claim["source_quote"], str)):
            return verdict("deferred", "pulso_editorial_future_claims_invalid")
    # A genuine structured score below the unchanged media threshold cannot
    # publish. Invalid shapes/scores still defer above, and the processor must
    # independently verify the actual response/request binding afterwards.
    if score < 72:
        return verdict("rejected", "editorial_relevance_below_threshold")
    body = normalized(analysis_text)
    def quote_matches(value, minimum=20):
        return literal_quote_matches(value, body, minimum)
    if not quote_matches(proof["human_health_scope_quote"]):
        return verdict("deferred", "pulso_editorial_scope_quote_not_in_input")
    if proof["scope_decision"] != "human_health_specific":
        return verdict("rejected", "pulso_editorial_" + proof["scope_decision"])
    scope_quote = proof["human_health_scope_quote"]
    # A generic discovery anchor deliberately admits animal/plant references.
    # They cannot substantiate a human-health editorial assertion on their own.
    # Preserve any independent human-health evidence in the same primary quote,
    # and defer contradictory model labels rather than infer a rejection.
    from .pulso_source import health_anchor
    if (NON_HUMAN_HEALTH.search(scope_quote)
            and not health_anchor(NON_HUMAN_HEALTH.sub("", scope_quote))):
        return verdict("deferred", "pulso_editorial_human_scope_conflicts_with_non_human_quote")
    if not human_health_scope_anchor(scope_quote):
        return verdict("deferred", "pulso_editorial_scope_not_grounded")
    for field, minimum in (("actor", 8), ("action", 20), ("consequence", 20)):
        quote = proof[field + "_quote"]
        value = proof[field]
        if (not quote_matches(quote, minimum) or len(value.strip()) < 3
                or literal_quote_form(value) not in literal_quote_form(quote)):
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
                or not future_copy_qualified(claim["summary_quote"])
                or unqualified_achieved_copy(claim["summary_quote"])):
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


def verified_code_repair_admission(fresh, previous_raw, previous_reason):
    """Admit one new assessment for a pinned real v4 failure, never its reuse.

    This pure verifier neither changes queue state nor overrides editorial or
    budget gates. The caller must limit it to pending/retry and retain the prior
    response, attempts and all primary evidence in its evidence revision.
    """
    from .pulso_source import complete_article_body
    from .llm_analysis import news_analysis_input
    if not isinstance(previous_raw, dict) or not isinstance(previous_reason, str):
        return None
    try:
        path = Path(__file__).resolve().parents[2] / "config/pulso_editorial_repair_admission_2026_10_11.json"
        captured = path.read_bytes()
        if hashlib.sha256(captured).hexdigest() != REPAIR_ADMISSION_PIN_SHA256:
            return None
        manifest = json.loads(captured)
        if (manifest.get("repair_version") != VERSION or manifest.get("cohort_sha256") != REPAIR_COHORT_SHA256
                or manifest.get("producer_run_id") != 38149773071 or len(manifest.get("pins", [])) != 69):
            return None
        pin = next((p for p in manifest["pins"] if p["url"] == fresh.url), None)
        if not pin or pin["previous_reason"] != previous_reason:
            return None
        new, old = fresh.metadata, previous_raw.get("metadata", {})
        if (fresh.source_slug != "pulso_latercera" or previous_raw.get("source_slug") != "pulso_latercera"
                or fresh.source_type != "press_high_trust" or previous_raw.get("source_type") != "press_high_trust"
                or fresh.source_name != "Pulso / La Tercera" or previous_raw.get("source_name") != fresh.source_name
                or fresh.title != pin["title"] or previous_raw.get("title") != pin["title"]
                or previous_raw.get("url") != pin["url"]
                or fresh.event_date != pin["publication_date"]
                or previous_raw.get("event_date") != pin["publication_date"]):
            return None
        for metadata in (new, old):
            if (not isinstance(metadata, dict) or not complete_article_body(metadata)
                    or any(metadata.get(flag) is not True for flag in (
                        "article_verified", "article_body_complete", "primary_identity_verified", "publication_date_verified"))
                    or metadata.get("source_quality_gate") != "passed"
                    or metadata.get("canonical_url") != pin["url"]
                    or metadata.get("publication_date") != pin["publication_date"]
                    or metadata.get("article_body_sha256") != pin["article_body_sha256"]
                    or metadata.get("html_sha256") != pin["html_sha256"]
                    or metadata.get("editorial_hold") or metadata.get("publisher_exception_reason")):
                return None
        if new["page_text"] != old["page_text"]:
            return None
        ai, validation = old.get("analysis_model_output"), old.get("pulso_editorial_proof_validation")
        if not isinstance(ai, dict) or not isinstance(validation, dict):
            return None
        binding = old.get("primary_item_binding")
        if (not isinstance(binding, dict) or binding.get("verified") is not True
                or binding.get("raw_url") != pin["url"] or binding.get("primary_canonical_url") != pin["url"]
                or binding.get("raw_event_date") != pin["publication_date"]
                or binding.get("primary_publication_date") != pin["publication_date"]
                or binding.get("primary_verification_flags") != {
                    "primary_identity_verified": True, "publication_date_verified": True}):
            return None
        output_sha = hashlib.sha256(json.dumps(ai, ensure_ascii=False, sort_keys=True,
                                               separators=(",", ":")).encode()).hexdigest()
        request_sha = hashlib.sha256(news_analysis_input(title=fresh.title, text=new["page_text"],
            source_name=fresh.source_name, full_text=True).encode()).hexdigest()
        if (output_sha != pin["previous_model_output_sha256"]
                or ai.get("_pulso_analysis_meta") != pin["model_response"]
                or pin["model_response"].get("schema_version") != "pulso_editorial_proof_v4"
                or pin["model_response"].get("analysis_text_sha256") != pin["article_body_sha256"]
                or pin["model_response"].get("request_input_sha256") != request_sha
                or validation.get("version") != "pulso_editorial_proof_v4"
                or validation.get("decision") != "deferred" or validation.get("reason") != previous_reason
                or validation.get("model_output_sha256") != output_sha
                or validation.get("analysis_text_sha256") != pin["article_body_sha256"]
                or validation.get("request_input_sha256") != request_sha
                or validation.get("model_response") != pin["model_response"]
                or old.get("analysis_input_complete") is not True
                or old.get("analysis_input_format") != "full_primary_article_body"
                or old.get("analysis_input_body_sha256") != pin["article_body_sha256"]
                or old.get("analysis_request_input_sha256") != request_sha):
            return None
        previous_response_id = pin["model_response"]["response_id"]
        admission_id = hashlib.sha256((VERSION + "\n" + REPAIR_ADMISSION_PIN_SHA256 + "\n"
            + pin["url"] + "\n" + previous_reason + "\n" + previous_response_id).encode()).hexdigest()
        return dict(repair_version=VERSION, admission_id=admission_id,
                    pins_sha256=REPAIR_ADMISSION_PIN_SHA256, cohort_sha256=REPAIR_COHORT_SHA256,
                    producer_run_id=38149773071, previous_response_id=previous_response_id,
                    previous_model_output_sha256=output_sha, previous_reason=previous_reason,
                    url=pin["url"], publication_date=pin["publication_date"],
                    article_body_sha256=pin["article_body_sha256"], html_sha256=pin["html_sha256"],
                    request_input_sha256=request_sha, new_assessment_required=True,
                    old_response_reuse=False, publication_approved=False,
                    other_editorial_and_budget_gates_still_apply=True)
    except (AttributeError, KeyError, TypeError, ValueError, OSError):
        return None
