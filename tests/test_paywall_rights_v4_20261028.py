"""Third review FAIL fixes (28-oct-2026) for the paywalled-press rights policy.

1. a teaser re-analysis archives the paid output it replaces (rule 6), never overwrites it;
2. La Tercera per-article access flags are stored at capture (no body text); unflagged
   items keep the path classification with ``access_verified: false``; an open path that
   reproduces a paywalled body is paywalled (or loses the overlapping sentences);
3. the 10-oct weekly archive keeps receipts of the rewritten reasons;
4. a rights review bypasses the public-text check only after an independent QA;
5. (see test_paywall_rights_v3) unbilled failures: backoff, 3 attempts, then deferred;
6. per-run cap RADAR_PAYWALL_REANALYSIS_PER_RUN (default 20).
"""
import copy
import gzip
import hashlib
import json
import re
from pathlib import Path

import pytest

from radar_salud import pulso_paywall
from radar_salud.models import RawItem
from radar_salud.pulso_source import complete_article_body, extract_article, public_capture
from radar_salud.source_rights import (MODEL_OUTPUT_RIGHTS, OVERLAP_KEY, _field_sha, access_classification,
                                       apply_overlap_policy, body_fingerprints, contains_fingerprinted,
                                       is_paywalled, model_output_digest, publisher_access_flags,
                                       redact_public_payload, restrict_raw_to_public, review_qa_approved,
                                       scrub_queue_item, verified_model_output_digest)

ROOT = Path(__file__).resolve().parents[1]
PULSO_URL = "https://www.latercera.com/pulso/noticia/isapre-x-anuncia-alza/"
OPEN_URL = "https://www.latercera.com/sustentabilidad/noticia/isapre-x-anuncia-alza/"
TITLE = "Isapre X anuncia alza de planes"
TEASER = "La institución anunció la suspensión temporal de sus operaciones tras daños en su infraestructura."
QUOTE = "El primer párrafo bloqueado tiene información exclusiva para suscriptores del diario financiero."
SECOND = "La segunda oración bloqueada detalla cifras internas que no aparecen en la bajada pública."
BODY = (QUOTE + " " + SECOND + " ") * 6
BODY_SHA = hashlib.sha256(BODY.encode()).hexdigest()
OPEN_SENTENCES = " ".join(f"Oración abierta número {i} con contenido propio de la sección abierta del diario."
                          for i in range(8))


def _paid(what="La isapre subirá 7,9% sus planes desde marzo."):
    return {"relevance_score": 80, "what_happened": what, "why_it_matters": "La institución anunció la suspensión.",
            "reason": "r", "pulso_editorial_proof": {"actor_quote": QUOTE, "scope_reason": "salud humana"},
            "_pulso_analysis_meta": {"response_id": "resp_full", "analysis_text_sha256": BODY_SHA,
                                     "request_input_sha256": "c" * 64, "source_name": "Pulso / La Tercera",
                                     "schema_version": "pulso_editorial_proof_v5", "model": "m",
                                     "raw_model_output_sha256": "b" * 64}}


def _paid_item():
    model = _paid()
    md = {"page_text": BODY, "article_body_sha256": BODY_SHA, "article_body_characters": len(BODY),
          "description": TEASER, "canonical_url": PULSO_URL, "article_verified": True,
          "analysis_base_article_body_sha256": BODY_SHA, "analysis_input_body_sha256": BODY_SHA,
          "analysis_request_input_sha256": "c" * 64, "analysis_model_output": model,
          "pulso_editorial_proof_validation": {"decision": "ready", "model_output_sha256": model_output_digest(model),
                                               "version": "pulso_editorial_proof_v5"}}
    raw = {"source_slug": "pulso_latercera", "title": TITLE, "url": PULSO_URL, "source_name": "Pulso / La Tercera",
           "source_type": "press_high_trust", "event_date": "2026-10-20", "raw_text": BODY, "metadata": md}
    return {"source": "pulso_latercera", "status": "published", "raw": raw}


def _processing_raw(item):
    raw = RawItem(**item["raw"])
    restrict_raw_to_public(raw)
    raw.metadata.update(market_role="media", primary_identity_verified=True, publication_date_verified=True,
                        publication_date="2026-10-20", article_body_complete=True)
    return raw


def _teaser_answer(**_):
    from radar_salud import llm_analysis
    llm_analysis._LAST_CALL.clear()
    llm_analysis._LAST_CALL.update(sent=True, response=True, input_tokens=300, output_tokens=200,
                                   response_id="resp_teaser")
    return {"relevance_score": 60, "what_happened": TEASER, "why_it_matters": "", "reason": "teaser",
            "_pulso_analysis_meta": {"response_id": "resp_teaser", "analysis_text_sha256": "e" * 64,
                                     "request_input_sha256": "f" * 64, "source_name": "Pulso / La Tercera"}}


# --- 1. rule 6: the replaced paid output is archived, never overwritten ------------------

def test_teaser_reanalysis_archives_the_full_body_paid_output_instead_of_overwriting_it(monkeypatch):
    from radar_salud import beta_sources, llm_analysis
    item = _paid_item()
    original = copy.deepcopy(item["raw"]["metadata"]["analysis_model_output"])
    original_validation = copy.deepcopy(item["raw"]["metadata"]["pulso_editorial_proof_validation"])
    scrub_queue_item(item, body_fingerprints(BODY, [TITLE, TEASER]))  # rights migration: quotes -> receipts
    redacted = copy.deepcopy(item["raw"]["metadata"]["analysis_model_output"])
    rights = copy.deepcopy(item["raw"]["metadata"][MODEL_OUTPUT_RIGHTS])
    raw = _processing_raw(item)
    calls = []
    monkeypatch.setattr(pulso_paywall, "capacity_available", lambda: True)
    monkeypatch.setattr(llm_analysis, "analyze_news", lambda **kw: calls.append(kw) or _teaser_answer())
    try:
        beta_sources.process_curated_beta_source(raw, {"slug": "pulso_latercera", "market_role": "media"})
    except Exception:  # the teaser answer's own outcome is irrelevant here
        pass
    assert len(calls) == 1 and calls[0]["text"] == TEASER
    md = raw.metadata
    # The new teaser answer took the live slot ...
    assert md["analysis_model_output"]["_pulso_analysis_meta"]["response_id"] == "resp_teaser"
    # ... and the earlier paid answer, its validation and rights record are archived intact.
    archived, = md[pulso_paywall.SUPERSEDED]
    assert archived["analysis_model_output"] == redacted
    assert archived["pulso_editorial_proof_validation"] == original_validation
    assert archived[MODEL_OUTPUT_RIGHTS] == rights
    assert archived["original_model_output_sha256"] == model_output_digest(original)
    assert archived["original_model_output_sha256"] == original_validation["model_output_sha256"]
    assert archived["stored_model_output_sha256"] == model_output_digest(redacted)
    assert archived["response_id"] == "resp_full" and archived["prior_binding"]["analysis_input_body_sha256"] == BODY_SHA
    # The archived form is the redacted one: its receipts verify against the original digest.
    assert verified_model_output_digest(archived) == (model_output_digest(original), "redacted_output_verified")
    assert QUOTE not in json.dumps(md, ensure_ascii=False)


def test_archive_is_idempotent_and_skips_items_without_a_paid_output():
    item = _paid_item()
    raw = RawItem(**item["raw"])
    prior = pulso_paywall.prior_binding(raw.metadata)
    first = pulso_paywall.archive_paid_output(raw, prior, "x")
    assert first and "analysis_model_output" not in raw.metadata
    assert pulso_paywall.archive_paid_output(raw, prior, "x") is None
    assert len(raw.metadata[pulso_paywall.SUPERSEDED]) == 1


# --- 6. per-run cap -----------------------------------------------------------------------

def test_run_cap_defaults_to_20_and_reads_the_environment(monkeypatch):
    monkeypatch.delenv(pulso_paywall.RUN_CAP_ENV, raising=False)
    assert pulso_paywall.run_cap() == 20
    monkeypatch.setenv(pulso_paywall.RUN_CAP_ENV, "not-a-number")
    assert pulso_paywall.run_cap() == 20
    monkeypatch.setenv(pulso_paywall.RUN_CAP_ENV, "2")
    assert [pulso_paywall.take_run_slot() for _ in range(3)] == [True, True, False]


def test_run_cap_defers_further_reanalyses_without_a_call(monkeypatch):
    from radar_salud import beta_sources, llm_analysis
    from radar_salud.processing import DeferredProcessing
    monkeypatch.setenv(pulso_paywall.RUN_CAP_ENV, "1")
    monkeypatch.setattr(pulso_paywall, "capacity_available", lambda: True)
    calls = []
    monkeypatch.setattr(llm_analysis, "analyze_news", lambda **kw: calls.append(kw) or _teaser_answer())
    first, second = _processing_raw(_paid_item()), _processing_raw(_paid_item())
    try:
        beta_sources.process_curated_beta_source(first, {"slug": "pulso_latercera", "market_role": "media"})
    except Exception:
        pass
    with pytest.raises(DeferredProcessing, match="pulso_paywalled_reanalysis_run_cap_deferred"):
        beta_sources.process_curated_beta_source(second, {"slug": "pulso_latercera", "market_role": "media"})
    assert len(calls) == 1
    # The capped item keeps its paid output and has no attempt recorded: next run it is processed.
    assert second.metadata["analysis_model_output"]["_pulso_analysis_meta"]["response_id"] == "resp_full"
    assert pulso_paywall.STATE not in second.metadata


# --- 2. per-article access flags ---------------------------------------------------------

@pytest.fixture
def path_scoped_policy(monkeypatch):
    """Policy 1.2.0 scope for La Tercera (premium prefixes/sections/article flag): the rules
    that still decide for any path-scoped source, exercised here on La Tercera pages."""
    from radar_salud.source_rights import load_policy
    for rule in load_policy()["sources"]:
        if rule.get("metered_sections_paywalled"):
            monkeypatch.setitem(rule, "scope", "path_prefix_section_or_article_flag")
            monkeypatch.setitem(rule, "metered_sections_paywalled", False)


def _fixture(name):
    html = gzip.decompress((ROOT / "tests/fixtures" / name).read_bytes()).decode()
    return html, re.search(r'<link rel="canonical" href="([^"]+)"', html).group(1)


def test_capture_stores_lock_flags_as_booleans_and_flags_the_article():
    html, url = _fixture("pulso_runtime_real/c6f21fa1420002e2a7626c02cbd8bf7bb51a47b1fc4e3656dd12e06cda9ba52a.html.gz")
    _, body, md = extract_article(html, url)
    record = md["publisher_access"]
    assert md["access_verified"] is True and md["publisher_paywall"] is True and record["lock_element"] is True
    assert "article-body__teaser--locked" in record["lock_element_classes"]
    # Small tokens only: no publisher text in the access record.
    assert all(len(json.dumps(v)) < 120 for v in record.values())
    assert body[:80] not in json.dumps(record)


def test_metered_page_without_flags_is_paid_by_section_and_unverified():
    html, url = _fixture("pulso_targeted_primary_real/5c3a703740c29e685be525adddb2a9773205b55fee43014cb0dde58035b6bfe0.html.gz")
    _, _, md = extract_article(html, url)
    assert md["access_verified"] is False and "publisher_paywall" not in md
    assert md["publisher_access"]["paywall_slot_present"] is True  # page chrome, never a flag
    # Dirección 28-oct: metered sections (/nacional/...) are paid.
    assert access_classification(url, md) == {"paywalled": True, "basis": "metered_section", "access_verified": False}


def test_without_flags_the_path_scoped_rule_keeps_it_open_and_unverified(path_scoped_policy):
    html, url = _fixture("pulso_targeted_primary_real/5c3a703740c29e685be525adddb2a9773205b55fee43014cb0dde58035b6bfe0.html.gz")
    _, _, md = extract_article(html, url)
    assert access_classification(url, md) == {"paywalled": False, "basis": "open_path", "access_verified": False}


@pytest.mark.parametrize("node,metas,html,paywalled", [
    ({"isAccessibleForFree": False}, {}, "", True),
    ({"isAccessibleForFree": "False"}, {}, "", True),
    ({"isAccessibleForFree": True}, {}, "", False),
    ({"hasPart": [{"@type": "WebPageElement", "isAccessibleForFree": False, "cssSelector": ".paywall"}]}, {}, "", True),
    ({}, {"article:content_tier": "locked"}, "", True),
    ({}, {"article:content_tier": "metered"}, "", False),
    ({}, {}, '<div id="lt-paywall-slot"></div>', False),
])
def test_publisher_access_flags_drive_the_article_classification(node, metas, html, paywalled, path_scoped_policy):
    md = publisher_access_flags(node, metas, html)
    assert md["access_verified"] is (bool(node) or bool(metas))
    assert is_paywalled("https://www.latercera.com/nacional/noticia/x/", md) is paywalled


# --- 2. sentence overlap with a known paywalled body -------------------------------------

def _open_record(text):
    return {"url": OPEN_URL, "title": TITLE, "raw_text": text,
            "metadata": {"page_text": text, "article_body_sha256": hashlib.sha256(text.encode()).hexdigest(),
                         "article_body_characters": len(text), "description": TEASER, "section": "Sustentabilidad"}}


def test_open_path_reproducing_a_paywalled_body_is_paywalled_and_redacted(path_scoped_policy):
    fps = body_fingerprints(BODY, [TITLE, TEASER])
    record = _open_record(BODY)
    record["body"] = record.pop("raw_text")  # Pulso discovery cache shape
    assert not is_paywalled(OPEN_URL, record["metadata"])
    assert apply_overlap_policy(record, fps) == "paywalled"
    md = record["metadata"]
    assert md[OVERLAP_KEY]["paywalled"] is True and md[OVERLAP_KEY]["ratio"] >= 0.5
    assert access_classification(OPEN_URL, md)["basis"] == "sentence_overlap"
    public_capture(record)
    assert md["page_text"] == md["public_teaser"] == TEASER and QUOTE not in json.dumps(record, ensure_ascii=False)
    assert complete_article_body(md)  # receipt proves the capture: no re-fetch
    assert apply_overlap_policy(record, fps) is None  # idempotent


def test_partial_overlap_redacts_only_the_overlapping_sentences_and_keeps_the_body_provable(path_scoped_policy):
    fps = body_fingerprints(BODY, [TITLE, TEASER])
    text = OPEN_SENTENCES + " " + QUOTE + " " + OPEN_SENTENCES
    record = _open_record(text)
    assert apply_overlap_policy(record, fps) == "sentences"
    md = record["metadata"]
    assert not is_paywalled(OPEN_URL, md)
    assert QUOTE not in md["page_text"] and QUOTE not in record["raw_text"]
    assert OPEN_SENTENCES in md["page_text"] and "[redactado: muro de pago; sha256=" in md["page_text"]
    assert {r["sha256"] for r in md["rights_sentence_redactions"]} == {hashlib.sha256(QUOTE.encode()).hexdigest()}
    assert not contains_fingerprinted(md["page_text"], fps)
    assert complete_article_body(md)  # capture hash still provable; nothing re-fetched
    before = copy.deepcopy(record)
    assert apply_overlap_policy(record, fps) is None and record == before


def test_stored_fiestas_patrias_open_capture_is_paywalled_by_overlap():
    queue = json.loads((ROOT / "data/state/pending_queue.json").read_text(encoding="utf-8"))
    rows = [item["raw"] for item in queue.values() if (item.get("raw") or {}).get("url", "").startswith(
        "https://www.latercera.com/sustentabilidad/noticia/fiestas-patrias-disparan")]
    assert rows
    for raw in rows:
        md = raw["metadata"]
        assert is_paywalled(raw["url"], md)
        assert access_classification(raw["url"], md)["basis"] == "sentence_overlap"
        assert md["body_redacted"] is True and len(md["page_text"]) <= 600



@pytest.mark.parametrize("path", ["data/state/pending_queue.json", "data/state/pulso_discovery_cache.json"])
def test_no_stored_la_tercera_item_is_open_and_every_one_carries_its_access_basis(path):
    payload = json.loads((ROOT / path).read_text(encoding="utf-8"))
    records = ([item.get("raw") or {} for item in payload.values()] if "queue" in path
               else [dict(e, url=u) for u, e in payload["articles"].items()])
    lt = [r for r in records if "latercera.com" in str(r.get("url"))]
    assert lt
    for record in lt:
        md = record["metadata"]
        assert is_paywalled(record["url"], md) and md["paywalled"] is True and md["access_verified"] in (True, False)
        assert len(md.get("page_text") or "") <= 600
    receipt = json.loads((ROOT / "data/audits/rights_links_migration_2026_10_28.json").read_text(encoding="utf-8"))
    access = receipt["counts"]["la_tercera_access"]["queue" if "queue" in path else "cache"]
    assert access.get("open_by_path_only", 0) == 0 and access["total"] == len(lt)
    assert not any(k.startswith("open_by_") for k in access)
    assert receipt["counts"]["remaining_fingerprinted"]["paywalled_context_characters"] == 0


# --- 3. 10-oct archive receipts ------------------------------------------------------------

def test_rewritten_reasons_in_the_10_oct_archive_keep_receipts_of_the_original():
    archive = json.loads((ROOT / "data/weekly_insight/archive/2026-10-10.json").read_text(encoding="utf-8"))
    for idx in (0, 2):
        node = archive["top3"][idx]
        receipts = [r for r in node["rights_redactions"] if r["field"] == "reason"
                    and r["reason"] == "rewritten_to_public_text_only"]
        assert len(receipts) == 1
        r = receipts[0]
        assert re.fullmatch(r"[0-9a-f]{64}", r["sha256"]) and isinstance(r["characters"], int)
        assert r["sha256"] != hashlib.sha256(node["reason"].encode()).hexdigest()


# --- 4. rights reviews need an independent QA ------------------------------------------------

DF_URL = "https://www.df.cl/empresas/salud/x"


def _reviewed_node(**review):
    node = {"title": "Isapre X", "url": DF_URL, "reason": "Afirmación que no está en la bajada pública: margen 12%."}
    node["rights_review"] = {"basis": "b", "reviewer": "Claude (migración)",
                             "fields": {"reason": _field_sha(node["reason"])}, **review}
    return node


@pytest.mark.parametrize("review,kept", [
    ({}, False),
    ({"qa_status": "pending"}, False),
    ({"qa_status": "approved"}, False),                                   # no qa_by
    ({"qa_status": "approved", "qa_by": "Claude (migración)"}, False),     # not independent
    ({"qa_status": "approved", "qa_by": "independent-qa-agent"}, True),
])
def test_rights_review_bypasses_the_public_text_check_only_after_independent_qa(review, kept):
    node = _reviewed_node(**review)
    out = redact_public_payload({"items": [node]}, {DF_URL: "Bajada pública de la pieza."})["items"][0]
    assert bool(out["reason"]) is kept
    assert review_qa_approved(node["rights_review"]) is kept


def test_weekly_rights_reviews_record_independent_qa_and_evidence():
    for path in ("data/weekly_insight/latest.json", "data/weekly_insight/archive/2026-10-10.json"):
        doc = json.loads((ROOT / path).read_text(encoding="utf-8"))
        nodes = [doc["top3"][0], doc["top3"][2], doc["weekly_insight"]]
        for node in nodes:
            review = node["rights_review"]
            assert review_qa_approved(review) and review["qa_by"] == "independent-qa-agent"
            assert review["qa_evidence_urls"] and "qa_unverified" in review
            assert "pendiente QA" not in review["reviewer"]
            for field, sha in review["fields"].items():
                assert sha == _field_sha(node[field])
        assert "Fuente oficial confirma" not in doc["top3"][0]["reason"]
        assert not any("página oficial consultada" in k for k in doc["weekly_insight"]["key_figures"])
        # The public payload check keeps the QA-approved text.
        for node in nodes:
            assert redact_public_payload(node) == node
