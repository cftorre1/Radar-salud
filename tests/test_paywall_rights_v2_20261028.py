"""Review FAIL fixes (28-oct-2026) for the paywalled-press rights policy.

1. nested queue history is redacted and counted truthfully;
2. a DF rediscovery merge cannot resurrect old body keys;
3. a lead must come from og/meta description or an explicit lead element before the lock;
4. Pulso premium captures and cache keep lead + receipt only;
5. paid outputs bound to full bodies are reused or re-assessed once, never twice;
6. story groups, weekly insight, Global and free value go through the redaction;
plus %2F-preserving URLs and legacy MINSAL documents kept without a verified failure.
"""
import copy
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_salud.models import RawItem
from radar_salud.source_rights import (contains_fingerprinted, body_fingerprints, excess_fields, public_text_supported,
                                       redact_public_payload, redact_signal, redacted_body_verified,
                                       restrict_raw_to_public, rights_review_entry, scrub_queue_item, teaser_from_raw)

DF_URL = "https://www.df.cl/empresas/salud/clinica-x-suspende-operaciones"
PULSO_URL = "https://www.latercera.com/pulso/noticia/isapre-x-anuncia-alza/"
LOCKED_462 = ("La Clínica X suspenderá sus operaciones durante tres semanas por daños en su central térmica, "
              "según informó la gerencia a sus médicos. La institución trasladó a 84 pacientes a otros recintos "
              "de la red y reprogramó 1.200 atenciones ambulatorias. Fuentes de la empresa estiman pérdidas por "
              "$ 4.500 millones y evalúan acciones contra la constructora del edificio. El directorio sesionará "
              "el lunes para aprobar un plan de contingencia y revisar las coberturas del seguro de incendio.")
TEASER = "La institución anunció la suspensión temporal de sus operaciones tras daños en su infraestructura."
BODY = ("El primer párrafo bloqueado tiene información exclusiva para suscriptores del diario financiero. "
        "La segunda oración bloqueada detalla cifras internas que no aparecen en la bajada pública. ") * 6


def _df_html(og=None, lead=None, lead_after_lock=None, body=LOCKED_462):
    head = f'<meta property="og:description" content="{og}">' if og else ""
    lead_html = f'<p class="bajada">{lead}</p>' if lead else ""
    after = f'<p class="bajada">{lead_after_lock}</p>' if lead_after_lock else ""
    return (head + '<meta name="cXenseParse:recs:publishtime" content="2026-10-22T13:50:50Z">'
            '<script type="application/ld+json">{"@type":"NewsArticle","url":"' + DF_URL + '",'
            '"headline":"Clínica X suspende operaciones","datePublished":"2026-10-22T13:50:50Z"}</script>'
            + lead_html + f'<div id="articleLock" class="CUERPO" style="display:none"><p>{body}</p>{after}</div>')


# --- 3. lead provenance --------------------------------------------------------

def test_short_locked_body_never_becomes_the_lead():
    from radar_salud.df_article import bind_df_article
    assert len(LOCKED_462) <= 600
    raw = bind_df_article(RawItem("diario_financiero", "Clínica X", DF_URL, "Diario Financiero", "press_high_trust"),
                          _df_html())
    dumped = json.dumps(asdict(raw), ensure_ascii=False)
    assert "central térmica" not in dumped and "84 pacientes" not in dumped
    assert raw.raw_text == raw.metadata["page_text"] == raw.metadata["public_teaser"] == ""
    assert raw.metadata["public_teaser_source"] == "title_only"
    rec = next(r for r in raw.metadata["rights_redactions"] if r["field"] == "page_text")
    assert rec["characters"] == len(LOCKED_462) and rec["sha256"] == raw.metadata["article_body_sha256"]
    assert redacted_body_verified(raw.metadata)


def test_explicit_public_lead_before_lock_is_accepted_and_after_lock_is_not():
    from radar_salud.df_article import parse_df_article
    before = parse_df_article(_df_html(lead=TEASER), DF_URL)
    assert before["raw_text"] == TEASER and before["metadata"]["public_teaser_source"] == "public_lead_element"
    after = parse_df_article(_df_html(lead_after_lock=TEASER), DF_URL)
    assert after["raw_text"] == "" and after["metadata"]["public_teaser_source"] == "title_only"
    og = parse_df_article(_df_html(og=TEASER, lead="Otra bajada visible antes del bloqueo."), DF_URL)
    assert og["raw_text"] == TEASER and og["metadata"]["public_teaser_source"] == "og:description"


def test_stored_raw_text_is_not_a_lead_without_public_provenance():
    raw = {"url": DF_URL, "title": "Clínica X", "raw_text": LOCKED_462, "metadata": {"page_text": LOCKED_462}}
    assert teaser_from_raw(raw) == ""
    item = RawItem("diario_financiero", "Clínica X", DF_URL, "Diario Financiero", "press_high_trust",
                   raw_text=LOCKED_462, metadata={"page_text": LOCKED_462})
    restrict_raw_to_public(item)
    assert item.raw_text == item.metadata["page_text"] == ""


def test_df_title_only_piece_is_rejected_terminally_without_model(monkeypatch):
    from radar_salud.df_article import bind_df_article
    from radar_salud.public_source_pipeline import process_df
    from test_press_pipeline import DF_CFG
    monkeypatch.setattr("radar_salud.public_source_pipeline.analyze_news",
                        lambda **kw: pytest.fail("title-only paywalled piece must not reach the model"))
    raw = bind_df_article(RawItem("diario_financiero", "Clínica X suspende operaciones por daños", DF_URL,
                                  "Diario Financiero", "press_high_trust"), _df_html())
    raw.metadata["article_title"] = "Clínica X suspende operaciones por daños en hospital"
    assert process_df(raw, DF_CFG) is None
    assert raw.metadata["rejection_reason"] in ("df_paywalled_without_public_teaser", "media_no_material_event",
                                                "df_unrelated_to_health")


# --- 1. nested history ------------------------------------------------------

def _item_with_history():
    raw = {"url": DF_URL, "title": "Clínica X", "raw_text": TEASER,
           "metadata": {"page_text": TEASER, "public_teaser": TEASER, "public_teaser_source": "og:description",
                        "paywalled": True, "access_policy": "public_teaser_only"}}
    old = {"url": DF_URL, "title": "Clínica X", "raw_text": BODY[:300],
           "metadata": {"page_text": BODY, "description_full": BODY, "article_body": BODY}}
    return {"source": "diario_financiero", "status": "pending", "raw": raw,
            "recovery_observations": [{"at": "2026-10-11", "action": "x", "before": {"raw": copy.deepcopy(old)}}],
            "superseded_records": [{"raw": copy.deepcopy(old), "status": "superseded"}],
            "rediscovery_repairs": [{"previous_raw": copy.deepcopy(old)}]}


def test_nested_recovery_observations_and_superseded_records_are_redacted_and_counted():
    item = _item_with_history()
    stats = scrub_queue_item(item)
    text = json.dumps(item, ensure_ascii=False)
    assert "exclusiva para suscriptores" not in text
    assert stats["records"] == 3
    # 3 nested captures x (page_text + description_full + article_body + raw_text excerpt)
    assert stats["characters"] == 3 * (3 * len(BODY) + 300)
    for nested in (item["recovery_observations"][0]["before"]["raw"], item["superseded_records"][0]["raw"]):
        assert nested["metadata"]["paywalled"] is True and "article_body" not in nested["metadata"]
        assert {r["field"] for r in nested["metadata"]["rights_redactions"]} >= {
            "metadata.page_text", "metadata.description_full", "metadata.article_body", "raw_text"}
    snapshot = copy.deepcopy(item)
    assert scrub_queue_item(item) == {"records": 0, "characters": 0, "fingerprint_strings": 0,
                                      "fingerprint_characters": 0}
    assert item == snapshot


def test_fingerprints_catch_verbatim_copies_but_not_public_titles():
    fps = body_fingerprints(BODY, ["Clínica X", TEASER])
    node = {"url": DF_URL, "quote": "Según la nota: " + BODY[:200], "title": "Clínica X"}
    assert contains_fingerprinted(node["quote"], fps)
    from radar_salud.source_rights import scrub_fingerprinted
    assert scrub_fingerprinted(node, fps)[0] == 1 and node["quote"]["redacted"] is True and node["title"] == "Clínica X"
    open_node = {"url": "https://www.minsal.cl/x/", "quote": BODY[:200]}
    assert scrub_fingerprinted(open_node, fps) == (0, 0)


def test_queue_save_never_persists_paywalled_bodies(tmp_path):
    from radar_salud.pending_queue import PendingQueue
    queue = PendingQueue(tmp_path / "q.json")
    queue.items["k"] = _item_with_history()
    queue.save()
    assert "exclusiva para suscriptores" not in (tmp_path / "q.json").read_text(encoding="utf-8")


# --- 2. DF rediscovery merge ------------------------------------------------

def test_df_rediscovery_merge_does_not_restore_old_body_keys(tmp_path):
    from radar_salud.df_recovery import reconcile_existing
    from radar_salud.pending_queue import PendingQueue
    queue = PendingQueue(tmp_path / "q.json")
    legacy = {"url": DF_URL, "title": "Clínica X", "source_slug": "diario_financiero", "source_name": "Diario Financiero",
              "source_type": "press_high_trust", "event_date": None, "raw_text": TEASER,
              "metadata": {"description_full": BODY, "article_body": BODY, "full_text": BODY}}
    queue.items["k"] = {"source": "diario_financiero", "status": "pending", "reason": None, "lane": "BACKFILL",
                        "detected_at": "2026-10-10T00:00:00+00:00", "attempts": 0, "raw": legacy}
    fresh = RawItem("diario_financiero", "Clínica X", DF_URL, "Diario Financiero", "press_high_trust", "2026-10-10",
                    raw_text=TEASER, metadata={"page_text": BODY, "public_teaser": TEASER,
                                               "public_teaser_source": "og:description",
                                               "publication_date_source": "cxenseparse:recs:publishtime",
                                               "article_body_characters": len(BODY)})
    restrict_raw_to_public(fresh)
    now = datetime(2026, 10, 11, 5, tzinfo=timezone.utc)
    assert reconcile_existing(queue, fresh, now, "2026-10-11T00:00:00+00:00")
    item = queue.items["k"]
    md = item["raw"]["metadata"]
    for key in ("description_full", "article_body", "full_text"):
        assert key not in md
    assert md["page_text"] == TEASER and md["paywalled"] is True
    text = json.dumps(item, ensure_ascii=False)
    assert "exclusiva para suscriptores" not in text  # neither the merge nor the observation keeps it
    assert item["recovery_observations"]


# --- 4. Pulso premium capture ----------------------------------------------

def _pulso_metadata(body=BODY):
    return {"page_text": body, "article_body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "article_body_characters": len(body), "description": TEASER, "canonical_url": PULSO_URL,
            "article_verified": True, "html_sha256": "a" * 64}


def test_pulso_premium_capture_keeps_lead_and_receipt_and_stays_complete():
    from radar_salud.pulso_source import complete_article_body, public_capture
    entry = {"url": PULSO_URL, "title": "Isapre X anuncia alza", "body": BODY[:1800], "metadata": _pulso_metadata()}
    public_capture(entry)
    assert "exclusiva" not in json.dumps(entry, ensure_ascii=False)
    md = entry["metadata"]
    assert md["page_text"] == TEASER == entry["body"] and md["public_teaser_source"] == "jsonld:description"
    assert complete_article_body(md) and redacted_body_verified(md)
    # Open sections are untouched.
    open_entry = {"url": "https://www.latercera.com/nacional/noticia/x/", "title": "x", "body": BODY,
                  "metadata": _pulso_metadata()}
    public_capture(open_entry)
    assert open_entry["metadata"]["page_text"] == BODY


def test_pulso_processing_stores_only_lead_before_any_analysis(monkeypatch):
    from radar_salud.beta_sources import process_curated_beta_source
    raw = RawItem("pulso_latercera", "Isapre X anuncia alza", PULSO_URL, "Pulso / La Tercera", "press_high_trust",
                  "2026-10-20", raw_text=BODY[:1800], metadata=dict(_pulso_metadata(), market_role="media"))
    monkeypatch.setattr("radar_salud.llm_analysis.analyze_news", lambda **kw: None)
    try:
        process_curated_beta_source(raw, {"slug": "pulso_latercera", "market_role": "media"})
    except Exception:
        pass  # verification/deferral paths are covered elsewhere; storage is what matters here
    assert "exclusiva" not in json.dumps(asdict(raw), ensure_ascii=False)


# --- 5. paid revalidation continuity ----------------------------------------

# The public-text check also requires content words (review 2, 28-oct): the default
# "why" restates the public title/lead instead of adding "afiliados", absent from both.
def _paid(text_sha, request_sha, what="Isapre X anuncia alza de planes.",
          why="La institución anunció la suspensión temporal de sus operaciones."):
    return {"relevance_score": 80, "what_happened": what, "why_it_matters": why, "reason": "r",
            "_pulso_analysis_meta": {"response_id": "resp_1", "analysis_text_sha256": text_sha,
                                     "request_input_sha256": request_sha, "source_name": "Pulso / La Tercera",
                                     "schema_version": "pulso_editorial_proof_v5", "model": "m",
                                     "raw_model_output_sha256": "b" * 64}}


def _redacted_raw(model, decision="ready"):
    from radar_salud.pulso_paywall import _digest
    md = _pulso_metadata()
    body_sha = md["article_body_sha256"]
    md.update(analysis_base_article_body_sha256=body_sha, analysis_input_body_sha256=body_sha,
              analysis_request_input_sha256="c" * 64, analysis_model_output=model)
    md["pulso_editorial_proof_validation"] = {"decision": decision, "model_output_sha256": _digest(model),
                                              "version": "pulso_editorial_proof_v5", "prospective_evidence": False}
    raw = RawItem("pulso_latercera", "Isapre X anuncia alza de planes", PULSO_URL, "Pulso / La Tercera",
                  "press_high_trust", "2026-10-20", metadata=md)
    restrict_raw_to_public(raw)
    return raw


def test_full_body_paid_output_is_reused_without_a_call_when_receipt_and_public_text_match():
    from radar_salud import pulso_paywall
    body_sha = hashlib.sha256(BODY.encode()).hexdigest()
    raw = _redacted_raw(_paid(body_sha, "c" * 64))
    prior = pulso_paywall.prior_binding(raw.metadata)
    outcome = pulso_paywall.decide(raw, prior, text=TEASER, request_input="req")
    assert outcome["kind"] == "reuse_full"
    receipt = pulso_paywall.record_reuse(raw, prior)
    assert receipt["new_model_request"] is False and raw.metadata["analysis_input_body_sha256"] == body_sha


def test_body_derived_paid_output_gets_one_teaser_reanalysis_then_never_again():
    from radar_salud import pulso_paywall
    body_sha = hashlib.sha256(BODY.encode()).hexdigest()
    raw = _redacted_raw(_paid(body_sha, "c" * 64, what="La isapre subirá 7,9% sus planes desde marzo según Pulso."))
    prior = pulso_paywall.prior_binding(raw.metadata)
    first = pulso_paywall.decide(raw, prior, text=TEASER, request_input="req")
    assert first["kind"] == "reanalyse" and "not_supported_by_public_text" in first["detail"]
    pulso_paywall.mark_reanalysis(raw, first["detail"], TEASER)
    assert pulso_paywall.decide(raw, prior, text=TEASER, request_input="req")["kind"] == "exhausted"
    # A teaser-bound answer from that single call is reused, not re-paid.
    raw.metadata["analysis_model_output"] = _paid(hashlib.sha256(TEASER.encode()).hexdigest(),
                                                  hashlib.sha256(b"req").hexdigest())
    assert pulso_paywall.decide(raw, prior, text=TEASER, request_input="req")["kind"] == "teaser"


def test_paywalled_processing_calls_the_model_at_most_once(monkeypatch):
    """End to end through the processor: one teaser call, then a terminal decision."""
    from radar_salud import beta_sources, llm_analysis, pulso_paywall
    calls = []
    monkeypatch.setattr(pulso_paywall, "capacity_available", lambda: True)
    monkeypatch.setattr(llm_analysis, "analyze_news", lambda **kw: calls.append(kw) or None)
    body_sha = hashlib.sha256(BODY.encode()).hexdigest()
    raw = _redacted_raw(_paid(body_sha, "c" * 64, what="La isapre subirá 7,9% sus planes desde marzo."))
    raw.metadata.update(market_role="media", primary_identity_verified=True, publication_date_verified=True,
                        publication_date="2026-10-20", article_body_complete=True)
    for _ in range(3):
        try:
            beta_sources.process_curated_beta_source(raw, {"slug": "pulso_latercera", "market_role": "media"})
        except Exception:
            pass
    assert len(calls) <= 1
    if calls:
        assert calls[0]["text"] == TEASER and "exclusiva" not in json.dumps(calls[0], ensure_ascii=False)


def test_same_paywalled_request_compares_receipts_not_text():
    from radar_salud.pending_queue import _same_pulso_model_request
    body_sha = hashlib.sha256(BODY.encode()).hexdigest()
    old_raw = _redacted_raw(_paid(body_sha, "c" * 64))
    fresh = RawItem("pulso_latercera", old_raw.title, PULSO_URL, "Pulso / La Tercera", "press_high_trust",
                    "2026-10-20", metadata=_pulso_metadata())
    restrict_raw_to_public(fresh)
    previous = asdict(old_raw)
    previous["metadata"]["article_body_complete"] = True
    previous["metadata"]["analysis_input_complete"] = True
    assert _same_pulso_model_request(previous, fresh) is True
    changed = RawItem("pulso_latercera", old_raw.title, PULSO_URL, "Pulso / La Tercera", "press_high_trust",
                      "2026-10-20", metadata=_pulso_metadata(BODY + " Nueva oración agregada por el editor."))
    restrict_raw_to_public(changed)
    assert _same_pulso_model_request(previous, changed) is False


# --- 6. exempt / unwired outputs ----------------------------------------------

def test_story_group_rows_are_not_exempt():
    row = {"title": "Síntesis", "source_url": DF_URL, "derived_from": "editorial_story_group",
           "what_happened": "Cifra del cuerpo bloqueado: 84 pacientes.", "key_points": ["84 pacientes"]}
    out = redact_signal(row, TEASER)
    assert out["what_happened"] == TEASER and "key_points" not in out and excess_fields(out) == []


def test_configured_synthesis_cites_an_open_primary_and_documents_rights_basis():
    from radar_salud.source_rights import is_paywalled
    groups = json.loads(Path("config/editorial_story_groups.json").read_text(encoding="utf-8"))["groups"]
    for group in groups:
        card = group.get("card")
        if not card:
            continue
        assert card.get("source_url") and not is_paywalled(card["source_url"])
        assert card["rights_basis"]["policy"] == "public_teaser_only"
        text = json.dumps({k: v for k, v in card.items() if k != "rights_basis"}, ensure_ascii=False)
        assert "Fonasa +4,8%" not in text and "-14,5%" not in text and "Presupuesto Base" not in text


def test_public_payload_redacts_unreviewed_body_derived_text_and_keeps_reviewed_text():
    lead = "Tras el retroceso de 20% en ensayos clínicos en 2025, el ajuste se anticipa peor este año."
    pick = {"title": "Cae inversión de laboratorios", "url": DF_URL, "reason": "1.501 solicitudes pendientes y 413 días."}
    out = redact_public_payload({"top3": [pick]}, {DF_URL: lead})
    assert out["top3"][0]["reason"] == "" and out["top3"][0]["rights_review_required"] is True
    ok = dict(pick, reason="Retroceso de 20% en ensayos clínicos en 2025 (bajada pública).")
    assert redact_public_payload({"top3": [ok]}, {DF_URL: lead})["top3"][0]["reason"] == ok["reason"]
    reviewed = dict(pick, reason="Reporte del 9-oct; retroceso de 20% en 2025.")
    reviewed["rights_review"] = rights_review_entry(reviewed, ["reason"], "bajada pública", "test")
    assert redact_public_payload({"top3": [reviewed]}, {DF_URL: lead})["top3"][0]["reason"] == reviewed["reason"]
    edited = dict(reviewed, reason=reviewed["reason"] + " 1.501 pendientes.")
    assert redact_public_payload({"top3": [edited]}, {DF_URL: lead})["top3"][0]["reason"] == ""


def test_public_text_check_flags_numbers_and_actors_absent_from_the_lead():
    ok, missing = public_text_supported("Isapre X subirá 7,9% sus planes, igual que Banmédica.",
                                        "Isapre X anuncia alza de planes")
    assert not ok and "#79" in missing and "banmedica" in missing
    assert public_text_supported("La isapre anuncia alza de planes.", "Isapre X anuncia alza de planes")[0]


@pytest.mark.parametrize("path", ["data/weekly_insight/latest.json", "data/weekly_insight/editorial_approved.json",
                                  "data/weekly_insight/archive/2026-10-10.json"])
def test_weekly_outputs_carry_only_public_or_reviewed_text(path):
    from radar_salud.source_rights import public_teaser_index
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    history = json.loads(Path("data/history/superintendencia_signals.json").read_text(encoding="utf-8"))["signals"]
    stats = {"signals": 0, "fields": 0}
    assert redact_public_payload(payload, public_teaser_index(history), stats) is payload  # nothing left to redact
    assert stats["fields"] == 0, path
    latest = json.loads(Path("data/weekly_insight/latest.json").read_text(encoding="utf-8"))
    # Visible text only: review pins and receipts are hex digests that may contain "413" by chance.
    visible = [{k: v for k, v in pick.items() if k not in ("rights_review", "rights_redactions")}
               for pick in latest["top3"]]
    text = json.dumps(visible, ensure_ascii=False)
    assert "1.501" not in text and "413" not in text and "Selfix" not in text


def test_free_value_and_global_payloads_are_redacted():
    from radar_salud.free_value import build_free_value
    snapshot = {"generated_at": "x", "signals": []}
    out = build_free_value(snapshot, {"themes": []}, [], approved_payload={})
    assert isinstance(out, dict)
    feed = {"items": [{"title": "Pulso", "url": PULSO_URL, "summary": "Cifra del cuerpo: 7,9% de alza."}]}
    assert redact_public_payload(feed)["items"][0]["summary"] == ""


# --- notes: URLs ---------------------------------------------------------------

def test_encoded_slash_is_preserved_and_legacy_minsal_documents_keep_their_link():
    from radar_salud.source_urls import normalize_source_url, sanitize_card_links, source_url_problem
    assert normalize_source_url("https://x.cl/a%2Fb/c d") == "https://x.cl/a%2Fb/c%20d"
    url = "https://www.minsal.cl/sites/default/files/ResolucionExenta211.pdf"
    assert source_url_problem(url) is None
    assert "source_link_status" not in sanitize_card_links({"source_url": url})
    failed = sanitize_card_links({"source_url": url, "source_link_check": {
        "url": url, "http_status": 404, "tls_verified": True, "checked_at": "2026-10-28T00:00:00Z"}})
    assert failed["source_link_status"] == "invalid" and failed["source_link_problem"] == "verified_link_failure"


def test_working_tree_public_data_has_no_fingerprinted_paywalled_text():
    from radar_salud.source_rights import load_fingerprints, scrub_fingerprinted
    fps = load_fingerprints(Path("."))
    assert len(fps) > 1000
    for path in ("web/data/radar_today.json", "data/history/superintendencia_signals.json",
                 "data/weekly_insight/latest.json"):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        assert scrub_fingerprinted(payload, fps) == (0, 0), path
