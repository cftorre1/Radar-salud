"""Second review FAIL fixes (28-oct-2026) for the paywalled-press rights policy.

1. paid outputs keep their integrity: body quotes become in-place receipts and the
   pre-redaction digest stays the reuse key;
2. new La Tercera premium prefixes/sections; working-tree scan of all tracked data;
4. the Presupuesto 2027 synthesis keeps its read identity after its link moved to Minsal;
5. the public-text check requires content words, not only numbers and names;
6. a failed teaser call that billed nothing gets one bounded retry; a billed one never.
"""
import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest

from radar_salud import pulso_paywall
from radar_salud.models import RawItem
from radar_salud.source_rights import (MODEL_OUTPUT_RIGHTS, QUOTE_REASON, body_fingerprints, is_paywalled,
                                       model_output_digest, paywall_policy, public_text_supported,
                                       restrict_raw_to_public, scrub_queue_item, verified_model_output_digest)

ROOT = Path(__file__).resolve().parents[1]
PULSO_URL = "https://www.latercera.com/pulso/noticia/isapre-x-anuncia-alza/"
TITLE = "Isapre X anuncia alza de planes"
TEASER = "La institución anunció la suspensión temporal de sus operaciones tras daños en su infraestructura."
QUOTE = "El primer párrafo bloqueado tiene información exclusiva para suscriptores del diario financiero."
BODY = (QUOTE + " La segunda oración bloqueada detalla cifras internas que no aparecen en la bajada pública. ") * 6
BODY_SHA = hashlib.sha256(BODY.encode()).hexdigest()


def _paid(what=TITLE + ".", why="La institución anunció la suspensión temporal de sus operaciones."):
    return {"relevance_score": 80, "what_happened": what, "why_it_matters": why, "reason": "r",
            "pulso_editorial_proof": {"actor_quote": QUOTE, "future_claims": [{"source_quote": QUOTE}],
                                      "scope_reason": "salud humana"},
            "_pulso_analysis_meta": {"response_id": "resp_1", "analysis_text_sha256": BODY_SHA,
                                     "request_input_sha256": "c" * 64, "source_name": "Pulso / La Tercera",
                                     "schema_version": "pulso_editorial_proof_v5", "model": "m",
                                     "raw_model_output_sha256": "b" * 64}}


def _item(model=None, decision="ready"):
    model = model or _paid()
    md = {"page_text": BODY, "article_body_sha256": BODY_SHA, "article_body_characters": len(BODY),
          "description": TEASER, "canonical_url": PULSO_URL, "article_verified": True,
          "analysis_base_article_body_sha256": BODY_SHA, "analysis_input_body_sha256": BODY_SHA,
          "analysis_request_input_sha256": "c" * 64, "analysis_model_output": model,
          "pulso_editorial_proof_validation": {"decision": decision, "model_output_sha256": model_output_digest(model),
                                               "version": "pulso_editorial_proof_v5"}}
    raw = {"source_slug": "pulso_latercera", "title": TITLE, "url": PULSO_URL, "source_name": "Pulso / La Tercera",
           "source_type": "press_high_trust", "event_date": "2026-10-20", "raw_text": BODY, "metadata": md}
    return {"source": "pulso_latercera", "status": "published", "raw": raw}


def _raw(item):
    return RawItem(**item["raw"])


# --- 1. paid-output integrity --------------------------------------------------------

def test_body_quotes_in_a_paid_output_become_in_place_receipts_with_the_original_digest():
    item = _item()
    original = copy.deepcopy(item["raw"]["metadata"]["analysis_model_output"])
    scrub_queue_item(item, body_fingerprints(BODY, [TITLE, TEASER]))
    md = item["raw"]["metadata"]
    model = md["analysis_model_output"]
    assert QUOTE not in json.dumps(item, ensure_ascii=False)
    # Structure kept: same keys, same list lengths; the quote is a marked receipt in place.
    assert set(model) == set(original) and len(model["pulso_editorial_proof"]["future_claims"]) == 1
    quote = model["pulso_editorial_proof"]["actor_quote"]
    assert quote["redacted"] is True and quote["reason"] == QUOTE_REASON
    assert quote["sha256"] == hashlib.sha256(QUOTE.encode()).hexdigest() and quote["characters"] == len(QUOTE)
    assert model["_pulso_analysis_meta"] == original["_pulso_analysis_meta"]
    record = md[MODEL_OUTPUT_RIGHTS]
    assert record["original_model_output_sha256"] == model_output_digest(original)
    assert record["redacted_model_output_sha256"] == model_output_digest(model)
    assert [r["path"] for r in record["redactions"]] == ["pulso_editorial_proof.actor_quote",
                                                         "pulso_editorial_proof.future_claims[0].source_quote"]
    assert verified_model_output_digest(md) == (model_output_digest(original), "redacted_output_verified")
    # Idempotent: a second pass changes nothing and keeps the original key.
    again = copy.deepcopy(item)
    scrub_queue_item(again, body_fingerprints(BODY, [TITLE, TEASER]))
    assert again == item


def test_redacted_paid_output_is_reused_against_its_original_validation_without_a_call():
    item = _item()
    scrub_queue_item(item, body_fingerprints(BODY, [TITLE, TEASER]))
    raw = _raw(item)
    restrict_raw_to_public(raw)
    prior = pulso_paywall.prior_binding(raw.metadata)
    outcome = pulso_paywall.decide(raw, prior, text=TEASER, request_input="req")
    assert outcome["kind"] == "reuse_full"
    receipt = pulso_paywall.record_reuse(raw, prior)
    assert receipt["model_output_sha256"] == raw.metadata["pulso_editorial_proof_validation"]["model_output_sha256"]
    assert receipt["model_output_basis"] == "redacted_output_verified" and receipt["new_model_request"] is False


@pytest.mark.parametrize("tamper,reason", [
    ("edit_output", "redacted_output_record_mismatch"),
    ("drop_record", "redacted_output_record_mismatch"),
    ("forge_record", "redacted_output_record_mismatch"),
    ("other_validation", "prior_validation_not_bound_to_paid_output"),
])
def test_tampered_redacted_output_or_unbound_validation_is_never_reused(tamper, reason):
    item = _item()
    scrub_queue_item(item, body_fingerprints(BODY, [TITLE, TEASER]))
    md = item["raw"]["metadata"]
    if tamper == "edit_output":
        md["analysis_model_output"]["relevance_score"] = 95
    elif tamper == "drop_record":
        md.pop(MODEL_OUTPUT_RIGHTS)
    elif tamper == "forge_record":
        md[MODEL_OUTPUT_RIGHTS]["redactions"] = md[MODEL_OUTPUT_RIGHTS]["redactions"][:1]
    else:
        md["pulso_editorial_proof_validation"]["model_output_sha256"] = "d" * 64
    raw = _raw(item)
    restrict_raw_to_public(raw)
    model, why = pulso_paywall.full_body_output(raw.metadata, pulso_paywall.prior_binding(raw.metadata),
                                                f"{TITLE} {TEASER}")
    assert model is None and why == reason


def test_deferred_validation_is_reported_as_not_terminal_not_as_a_digest_mismatch():
    item = _item(decision="deferred")
    scrub_queue_item(item, body_fingerprints(BODY, [TITLE, TEASER]))
    raw = _raw(item)
    restrict_raw_to_public(raw)
    _, why = pulso_paywall.full_body_output(raw.metadata, pulso_paywall.prior_binding(raw.metadata),
                                            f"{TITLE} {TEASER}")
    assert why == "prior_validation_not_terminal"


def test_real_queue_paid_outputs_are_verifiable_against_their_validations():
    """Every redacted paid output in the queue proves its pre-redaction digest (no 0/77 regression)."""
    queue = json.loads((ROOT / "data/state/pending_queue.json").read_bytes())
    receipt = json.loads((ROOT / "data/audits/rights_links_migration_2026_10_28.json").read_bytes())
    checked = bound = 0
    for item in queue.values():
        md = (item.get("raw") or {}).get("metadata") or {}
        if not isinstance(md.get(MODEL_OUTPUT_RIGHTS), dict):
            continue
        checked += 1
        key, basis = verified_model_output_digest(md)
        assert basis == "redacted_output_verified", item["raw"]["url"]
        validation = md.get("pulso_editorial_proof_validation") or {}
        bound += validation.get("model_output_sha256") == key
    simulation = receipt["counts"]["paid_reuse_simulation"]
    assert checked == receipt["counts"]["paid_model_outputs_with_redacted_quotes"]["top_level_items"] > 0
    assert "prior_validation_not_terminal" not in simulation["reasons"] or bound
    assert bound >= checked - simulation["reasons"].get("prior_validation_not_bound_to_paid_output", 0)


# --- 2. premium prefixes and sections --------------------------------------------------

@pytest.mark.parametrize("url,metadata,expected", [
    ("https://www.latercera.com/pulso-pm/noticia/x/", None, True),
    ("https://www.latercera.com/earlyaccess/noticia/x/", None, True),
    ("https://www.latercera.com/la-tercera-sabado/noticia/x/", None, True),
    ("https://www.latercera.com/la-tercera-domingo/noticia/x/", None, True),
    ("https://www.latercera.com/sustentabilidad/noticia/x/", {"section": "Pulso"}, True),
    # Metered sections are paid since Dirección 28-oct (policy 1.3.0).
    ("https://www.latercera.com/nacional/noticia/x/", {"section": "Nacional"}, True),
    ("https://www.latercera.com/nacional/noticia/x/", None, True),
    ("https://www.latercera.com/que-pasa/noticia/x/", None, True),
])
def test_la_tercera_premium_prefixes_and_sections(url, metadata, expected):
    assert is_paywalled(url, metadata) is expected
    if expected:
        assert paywall_policy(url, metadata)["id"] == "la_tercera_premium"


def test_working_tree_scan_covers_all_tracked_data_and_reports_truthfully():
    import importlib.util
    spec = importlib.util.spec_from_file_location("mig3", ROOT / "scripts/migrate_source_rights_links_2026_10_28.py")
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    receipt = json.loads((ROOT / "data/audits/rights_links_migration_2026_10_28.json").read_bytes())
    remaining = receipt["counts"]["remaining_fingerprinted"]
    assert remaining["files_scanned"] > 1000  # every tracked text file outside tests/fixtures
    assert remaining["characters"] == sum(f["characters"] for f in remaining["by_file"].values())
    assert not any(path.startswith("tests/fixtures/") for path in remaining["by_file"])
    # The scan itself finds a planted sentence anywhere, with or without a URL context.
    fps = body_fingerprints(BODY)
    planted = ROOT / "data" / "_scan_probe.json"
    try:
        planted.write_text(json.dumps({"notes": [QUOTE]}), encoding="utf-8")
        result = mig.remaining_fingerprinted(fps, ["data/_scan_probe.json"])
    finally:
        planted.unlink()
    assert result["characters"] == len(QUOTE) and result["paywalled_context_characters"] == len(QUOTE)


# --- 4. read identity -----------------------------------------------------------------

def test_presupuesto_synthesis_keeps_its_read_identity_after_its_link_moved_to_minsal():
    old_url = ("https://www.df.cl/economia-y-politica/macro/"
               "presupuesto-2027-avanzan-los-recursos-para-salud-y-se-abre-negociacion-en")
    legacy_id = base64.b64encode(f"{old_url}|2026-10-22|STORY_SUMMARY".encode()).decode()
    groups = json.loads((ROOT / "config/editorial_story_groups.json").read_text(encoding="utf-8"))
    card = next(g["card"] for g in groups["groups"] if g.get("id") == "presupuesto-salud-2027")
    assert card["source_url"].startswith("https://www.minsal.cl/") and card["piece_id"] == legacy_id
    snapshot = json.loads((ROOT / "web/data/radar_today.json").read_text(encoding="utf-8"))
    rows = [s for s in snapshot["signals"] if s.get("story_group") == "presupuesto-salud-2027"]
    assert rows and all(s["piece_id"] == legacy_id for s in rows)  # app.js idFor(s) returns piece_id first
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert "function idFor(s){if(s.piece_id)return s.piece_id;" in app


# --- 5. stricter public-text check ------------------------------------------------------

LUKSIC_PUBLIC = ("Alcalde de Huechuraba propone alianza municipal para mejorar la ejecución de recursos de APS "
                 "El alcalde de Huechuraba y líder del equipo de salud de la AMUCH señala que esta comuna devolvía "
                 "$ 300 millones al Minsal, recursos que ahora ejecutan por completo.")


def test_public_text_check_requires_content_words_not_only_numbers_and_names():
    ok, missing = public_text_supported(
        "Plantea mejorar la ejecución de recursos de APS sin aumentar presupuesto; aún no es una medida sectorial adoptada.",
        LUKSIC_PUBLIC)
    assert not ok and {"~aumen", "~presu"} <= set(missing)
    assert public_text_supported(
        "Plantea mejorar la ejecución de recursos de APS; aún no es una medida sectorial adoptada.", LUKSIC_PUBLIC)[0]
    # Numbers and names are still required.
    assert not public_text_supported("La comuna devolvía $ 500 millones al Minsal.", LUKSIC_PUBLIC)[0]
    assert not public_text_supported("La comuna devolvía $ 300 millones a Fonasa.", LUKSIC_PUBLIC)[0]


def test_luksic_archive_item_keeps_supported_what_and_drops_unsupported_why():
    archive = json.loads((ROOT / "data/weekly_insight/archive/2026-09-14.json").read_text(encoding="utf-8"))
    items = []

    def walk(node):
        if isinstance(node, dict):
            if "max-luksic" in str(node.get("url", "")):
                items.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(archive)
    item, = items
    public = f"{item['title']} {item['public_teaser']}"
    assert item["what"] and public_text_supported(item["what"], public)[0]
    assert public_text_supported(item["why"], public)[0] and "presupuesto" not in item["why"]
    assert "rights_review_required" not in item


# --- 6. bounded retry only when nothing was billed --------------------------------------

def _reanalysis_raw():
    item = _item(_paid(what="La isapre subirá 7,9% sus planes desde marzo."))
    raw = _raw(item)
    restrict_raw_to_public(raw)
    return raw


@pytest.mark.parametrize("call,outcome,next_kind", [
    ({"sent": False, "response": False}, "failed_unbilled", "reanalyse"),
    ({"sent": True, "response": False, "error_type": "APIConnectionError"}, "failed_unbilled", "reanalyse"),
    ({"sent": True, "response": False, "error_type": "RateLimitError"}, "failed_unbilled", "reanalyse"),
    ({"sent": True, "response": False, "error_type": "APITimeoutError"}, "failed_possibly_billed", "exhausted"),
    ({"sent": True, "response": True, "input_tokens": 900, "output_tokens": 0}, "failed_possibly_billed", "exhausted"),
    ({}, "failed_possibly_billed", "exhausted"),  # unknown: assume billed
])
def test_failed_call_retries_only_when_nothing_was_billed(call, outcome, next_kind):
    from datetime import datetime, timedelta, timezone
    later = datetime.now(timezone.utc) + timedelta(days=2)  # past every backoff
    raw = _reanalysis_raw()
    prior = pulso_paywall.prior_binding(raw.metadata)
    first = pulso_paywall.decide(raw, prior, text=TEASER, request_input="req")
    assert first["kind"] == "reanalyse"
    pulso_paywall.mark_reanalysis(raw, first["detail"], TEASER)
    assert pulso_paywall.record_outcome(raw, None, call) == outcome
    second = pulso_paywall.decide(raw, prior, text=TEASER, request_input="req", now=later)
    assert second["kind"] == next_kind
    if next_kind == "reanalyse":
        # Bounded: up to 3 unbilled failures across runs, then deferred (never rejected).
        for _ in range(2):
            pulso_paywall.mark_reanalysis(raw, second["detail"], TEASER)
            pulso_paywall.record_outcome(raw, None, call)
        third = pulso_paywall.decide(raw, prior, text=TEASER, request_input="req", now=later)
        assert third["kind"] == "deferred_unbilled" and third["unbilled_failures"] == 3


def test_crash_during_the_call_counts_as_paid():
    raw = _reanalysis_raw()
    prior = pulso_paywall.prior_binding(raw.metadata)
    pulso_paywall.mark_reanalysis(raw, "x", TEASER)  # process died before record_outcome
    assert pulso_paywall.decide(raw, prior, text=TEASER, request_input="req")["kind"] == "exhausted"


@pytest.mark.parametrize("error_type,max_calls", [("APIConnectionError", 3), ("RateLimitError", 3),
                                                  ("APITimeoutError", 1), (None, 1)])
def test_processor_never_pays_twice_and_defers_after_three_unbilled_failures(monkeypatch, error_type, max_calls):
    from radar_salud import beta_sources, llm_analysis
    calls = []

    def fake(**kw):
        calls.append(kw)
        llm_analysis._LAST_CALL.clear()
        if error_type:
            llm_analysis._LAST_CALL.update(sent=True, response=False, error_type=error_type)
        else:  # a response arrived (billed) but was unusable
            llm_analysis._LAST_CALL.update(sent=True, response=True, input_tokens=800, output_tokens=40)
        return None

    monkeypatch.setattr(pulso_paywall, "capacity_available", lambda: True)
    monkeypatch.setattr(pulso_paywall, "UNBILLED_BACKOFF_HOURS", (0, 0))  # every run is past the backoff
    monkeypatch.setattr(llm_analysis, "analyze_news", fake)
    raw = _reanalysis_raw()
    raw.metadata.update(market_role="media", primary_identity_verified=True, publication_date_verified=True,
                        publication_date="2026-10-20", article_body_complete=True)
    outcomes = []
    for _ in range(5):
        pulso_paywall.reset_run_counter()  # one run each
        try:
            outcomes.append(beta_sources.process_curated_beta_source(
                raw, {"slug": "pulso_latercera", "market_role": "media"}))
        except Exception as exc:  # DeferredProcessing between runs
            outcomes.append(str(exc))
    assert len(calls) == max_calls
    assert all(c["text"] == TEASER for c in calls)
    history = raw.metadata[pulso_paywall.STATE]["history"]
    assert sum(h["outcome"] != "failed_unbilled" for h in history) <= 1
    if error_type in ("APIConnectionError", "RateLimitError"):
        # Deferred, not rejected: no rejection reason, and a revival re-opens it.
        assert outcomes[-1] == "pulso_paywalled_reanalysis_unbilled_attempts_deferred"
        assert "rejection_reason" not in raw.metadata
        pulso_paywall.revive(raw, "provider restored")
        prior = pulso_paywall.prior_binding(raw.metadata)
        assert pulso_paywall.decide(raw, prior, text=TEASER, request_input="req")["kind"] == "reanalyse"


def test_unbilled_failure_waits_for_its_backoff():
    from datetime import datetime, timedelta, timezone
    raw = _reanalysis_raw()
    prior = pulso_paywall.prior_binding(raw.metadata)
    pulso_paywall.mark_reanalysis(raw, "x", TEASER)
    pulso_paywall.record_outcome(raw, None, {"sent": True, "response": False, "error_type": "RateLimitError"})
    now = datetime.now(timezone.utc)
    soon = pulso_paywall.decide(raw, prior, text=TEASER, request_input="req", now=now)
    assert soon["kind"] == "wait" and soon["unbilled_failures"] == 1
    assert pulso_paywall.decide(raw, prior, text=TEASER, request_input="req",
                                now=now + timedelta(hours=2))["kind"] == "reanalyse"
