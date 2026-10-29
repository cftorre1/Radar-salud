"""Fourth independent review of the paywall rights policy (28-oct-2026, FAIL): regressions.

1. Story groups are judged by their member and cited sources, not by the card's link.
2. Rights reviews: the self-QA is revoked; ``qa_by`` must differ from implementer and reviewer.
3. A deferral never overwrites the paid binding (reuse and archive stay bound to it).
4. ``revive`` runs from the engine, bounded; run-cap/backoff deferrals are not attempts.
5. The 2-nov candidate is on HOLD; its open Minsal figures are restored with a fact trace.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from radar_salud import pulso_paywall
from radar_salud.pending_queue import PendingQueue
from radar_salud.source_rights import (_field_sha, public_teaser_index, redact_public_payload, review_qa_approved,
                                       rights_review_entry, story_group_problems, traced_field_problems)
from radar_salud.story_groups import apply_story_groups, load_groups
from test_paywall_rights_v4_20261028 import (BODY_SHA, TEASER, _paid_item, _processing_raw, _teaser_answer)

ROOT = Path(__file__).resolve().parents[1]
M21 = ("https://www.minsal.cl/tercera-subcomision-mixta-de-presupuestos-aprueba-partida-del-ministerio-de-salud-"
       "para-2027-recursos-aumentan-47-y-superan-los-183-billones/")
LT_NACIONAL = "https://www.latercera.com/nacional/noticia/presupuesto-salud-2027-x/"
LT_LEAD = "La propuesta del Ejecutivo crece en términos reales y pone énfasis en la atención primaria."
REMOVED_FIGURES = ("3.960.097", "3.595.710", "166.951", "189.696", "14,6%", "10,7%", "91,7%", "2,4%", "6,8%")


def _json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _history():
    return _json("data/history/superintendencia_signals.json")["signals"]


def _queue_page(url):
    for item in _json("data/state/pending_queue.json").values():
        if (item.get("raw") or {}).get("url") == url:
            return item["raw"]["metadata"]["page_text"]
    raise KeyError(url)


def _fragments(excerpt, page):
    """Stored excerpts join verbatim sentences: split greedily into the longest runs found in ``page``."""
    words, out, i = excerpt.split(), [], 0
    while i < len(words):
        j = i + 1
        while j <= len(words) and " ".join(words[i:j]) in page:
            j += 1
        out.append(" ".join(words[i:j - 1]))
        assert j - 1 - i >= 8, (" ".join(words[i:i + 12]), "not verbatim in the stored page")
        i = j - 1
    return out


def _story(**card):
    base = {"title": "Presupuesto 2027 de Salud", "source_url": M21, "derived_from": "editorial_story_group",
            "event_type": "STORY_SUMMARY", "what_happened": "El presupuesto de Salud crece 4,7%.",
            "source_alternatives": [{"url": M21, "title": "Minsal: recursos aumentan 4,7%"},
                                    {"url": LT_NACIONAL, "title": "Presupuesto Salud 2027: foco en atención primaria"}],
            "fact_trace": {"sources": {M21: {"basis": "open_official", "source_name": "Minsal",
                                             "title": "Presupuesto 2027 de Salud: recursos aumentan 4,7%",
                                             "excerpt": "El presupuesto de Salud crece 4,7%."}},
                           "fields": {"title": [M21], "what_happened": [M21]}}}
    base.update(card)
    return base


# --- 1. story groups -------------------------------------------------------------------------

def test_story_group_citing_a_paywalled_source_fails_unless_each_fact_traces_to_an_allowed_source():
    teasers = {LT_NACIONAL.rstrip("/"): LT_LEAD}
    assert story_group_problems(_story(), teasers=teasers) == []
    # A body-only figure attributed to the paid member, with no trace: fails.
    leak = _story(key_points=["Atención Primaria: de $3.595.710 a $3.960.097 millones (+6,8% real), según La Tercera."])
    assert story_group_problems(leak, teasers=teasers)
    # Traced to the paid member's public lead: still fails (the figure is not in the lead) ...
    traced_leak = copy.deepcopy(leak)
    traced_leak["fact_trace"]["sources"][LT_NACIONAL] = {"basis": "public_lead", "source_name": "La Tercera",
                                                         "title": "Presupuesto Salud 2027", "excerpt": LT_LEAD}
    traced_leak["fact_trace"]["fields"]["key_points"] = [[LT_NACIONAL]]
    assert any("#3960097" in p for p in story_group_problems(traced_leak, teasers=teasers))
    # ... and citing the paid piece as an open source fails whatever its text.
    as_open = copy.deepcopy(traced_leak)
    as_open["fact_trace"]["sources"][LT_NACIONAL]["basis"] = "open_official"
    as_open["key_points"] = ["La propuesta pone énfasis en la atención primaria."]
    assert any(p.startswith("key_points[0]:paywalled_source_cited_as_open_official")
               for p in story_group_problems(as_open, teasers=teasers))
    assert story_group_problems(_story(source_documents_open=[LT_NACIONAL]), teasers=teasers)
    # Supported by the paid member's public lead: passes.
    ok = copy.deepcopy(traced_leak)
    ok["key_points"] = ["La propuesta crece en términos reales y pone énfasis en la atención primaria."]
    assert story_group_problems(ok, teasers=teasers) == []


def test_redact_public_payload_judges_story_groups_by_their_members_not_the_card_link():
    leak = _story(key_points=["Ricarte Soto -14,6% real ($189.696 a $166.951 millones)."])
    out = redact_public_payload({"signals": [leak]}, {LT_NACIONAL.rstrip("/"): LT_LEAD})["signals"][0]
    assert out["key_points"] == [] and out["rights_review_required"] is True and out["feed_visibility"] is False
    assert any(r["field"] == "key_points" for r in out["rights_redactions"])
    group = {"id": "g", "mode": "summary", "member_urls": [M21, LT_NACIONAL], "card": dict(leak)}
    for key in ("derived_from", "event_type", "source_alternatives"):
        group["card"].pop(key)
    redacted = redact_public_payload({"groups": [group]})["groups"][0]["card"]
    assert redacted["key_points"] == [] and redacted["rights_review_required"] is True


def test_presupuesto_synthesis_carries_only_traced_open_or_public_lead_facts():
    groups = load_groups(ROOT)
    group = next(g for g in groups if g["id"] == "presupuesto-salud-2027")
    card = group["card"]
    teasers = public_teaser_index(_history())
    assert story_group_problems(card, group["member_urls"], teasers) == []
    visible = json.dumps([card[k] for k in ("title", "what_happened", "why_it_matters", "key_points")], ensure_ascii=False)
    for figure in REMOVED_FIGURES:
        assert figure not in visible, figure
    assert "Sugg" in visible and "15%" not in visible
    # Every open excerpt is stored verbatim in the open page captured in the queue.
    for url, src in card["fact_trace"]["sources"].items():
        if src["basis"] == "open_official":
            page = " ".join(_queue_page(url).split())
            assert _fragments(src["excerpt"], page)
    # And the synthesis shown in the snapshot passes the same check.
    snapshot = _json("web/data/radar_today.json")["signals"]
    shown = [c for c in snapshot if c.get("story_group") == "presupuesto-salud-2027"]
    assert len(shown) == 1 and story_group_problems(shown[0], teasers=teasers) == []
    assert not any(f in json.dumps(shown[0], ensure_ascii=False) for f in ("3.960.097", "166.951", "91,7%"))


def test_a_rejected_synthesis_keeps_its_members_visible():
    cards = [{"source_url": M21, "title": "a", "event_date": "2026-10-21"},
             {"source_url": LT_NACIONAL, "title": "b", "event_date": "2026-10-20"}]
    group = {"id": "g", "mode": "summary", "member_urls": [M21, LT_NACIONAL],
             "card": {"title": "t", "key_points": ["Ricarte Soto -14,6% real."]}}
    teasers = {LT_NACIONAL.rstrip("/"): LT_LEAD}
    remaining, summaries = apply_story_groups(copy.deepcopy(cards), [group],
                                              gate=lambda c: not story_group_problems(c, teasers=teasers))
    assert summaries == [] and len(remaining) == 2


# --- 2. rights reviews ---------------------------------------------------------------------------

@pytest.mark.parametrize("roles,approved", [
    ({"implemented_by": "impl", "reviewer": "rev", "qa_by": "qa"}, True),
    ({"reviewer": "rev", "qa_by": "qa"}, False),                          # implementer not recorded
    ({"implemented_by": "impl", "reviewer": "rev", "qa_by": "impl"}, False),  # QA is the implementer
    ({"implemented_by": "impl", "reviewer": "rev", "qa_by": " REV "}, False),  # QA is the reviewer
    ({"implemented_by": "same", "reviewer": "same", "qa_by": "qa"}, False),  # one identity, two roles
])
def test_qa_must_differ_from_implementer_and_reviewer(roles, approved):
    node = {"reason": "x"}
    review = rights_review_entry(node, ["reason"], "b", roles.get("reviewer"), roles.get("implemented_by"))
    review.update(qa_status="approved", qa_by=roles["qa_by"])
    if "implemented_by" not in roles:
        review.pop("implemented_by")
    assert review_qa_approved(review) is approved


def test_weekly_reviews_revoke_the_self_qa_and_keep_only_allowed_text():
    for path in ("data/weekly_insight/latest.json", "data/weekly_insight/archive/2026-10-10.json"):
        doc = _json(path)
        san_carlos, labs, weekly = doc["top3"][0], doc["top3"][2], doc["weekly_insight"]
        for node in (san_carlos, labs, weekly):
            review = node["rights_review"]
            assert review_qa_approved(review) and review["qa_by"] == "independent-reviewer-4th-review"
            assert review["qa_by"] not in (review["implemented_by"], review["reviewer"])
            assert "Cuarta revisión independiente" in review["qa_review_ref"]
            assert all(sha == _field_sha(node[f]) for f, sha in review["fields"].items())
            revoked, = node["rights_review_revoked"]
            assert revoked["qa_by"] == "independent-qa-agent" and revoked["qa_status"] == "revoked"
            assert redact_public_payload(node) == node
        assert "redistribu" not in san_carlos["reason"]
        assert labs["reason"].startswith("Reporte DF del 9-oct; sólo título y bajada públicos")
        shown = json.dumps([weekly[f] for f in review["fields"]] + [s["label"] for s in weekly["sources"]],
                           ensure_ascii=False)
        for gone in ("servicios de apoyo", "El Alba", "redistribu"):
            assert gone not in shown
        receipts = {(r["field"], r["reason"]) for n in (san_carlos, weekly) for r in n["rights_redactions"]}
        for field in ("reason", "key_figures", "insight_reading"):
            assert (field, "independent_review_4_claim_not_in_allowed_text") in receipts


def test_a_self_qa_no_longer_bypasses_the_public_text_check():
    node = {"title": "Isapre X", "url": "https://www.df.cl/empresas/salud/x", "reason": "Margen de 12% en 2025."}
    node["rights_review"] = {"basis": "b", "reviewer": "Claude", "fields": {"reason": _field_sha(node["reason"])},
                             "qa_status": "approved", "qa_by": "independent-qa-agent"}  # no implemented_by
    out = redact_public_payload(node, {"https://www.df.cl/empresas/salud/x": "Bajada pública."})
    assert out["reason"] == ""


# --- 3. a deferral keeps the paid binding ---------------------------------------------------

def _binding(md):
    return {k: md.get(k) for k in pulso_paywall.BINDING_FIELDS}


def test_run_cap_deferral_keeps_the_paid_binding_and_the_next_run_archives_it(monkeypatch):
    from radar_salud import beta_sources, llm_analysis
    from radar_salud.processing import DeferredProcessing
    monkeypatch.setenv(pulso_paywall.RUN_CAP_ENV, "1")
    monkeypatch.setattr(pulso_paywall, "capacity_available", lambda: True)
    calls = []
    monkeypatch.setattr(llm_analysis, "analyze_news", lambda **kw: calls.append(kw) or _teaser_answer())
    first, second = _processing_raw(_paid_item()), _processing_raw(_paid_item())
    paid_binding = _binding(second.metadata)
    assert paid_binding["analysis_input_body_sha256"] == BODY_SHA
    cfg = {"slug": "pulso_latercera", "market_role": "media"}
    try:
        beta_sources.process_curated_beta_source(first, cfg)
    except Exception:
        pass
    with pytest.raises(DeferredProcessing, match="run_cap_deferred"):
        beta_sources.process_curated_beta_source(second, cfg)
    # Deferred: the persisted binding is still the paid one, not the teaser's.
    assert _binding(second.metadata) == paid_binding
    # Next run: the slot is free, the single teaser re-analysis runs and archives
    # the paid output with the binding it was produced under.
    pulso_paywall.reset_run_counter()
    stored = RawItem_roundtrip(second)
    try:
        beta_sources.process_curated_beta_source(stored, cfg)
    except Exception:
        pass
    assert len(calls) == 2
    archived, = stored.metadata[pulso_paywall.SUPERSEDED]
    assert archived["prior_binding"] == paid_binding
    assert archived["response_id"] == "resp_full"
    # After the successful teaser answer the live binding is the teaser request's.
    teaser_sha = hashlib.sha256(TEASER.encode()).hexdigest()
    assert stored.metadata["analysis_input_body_sha256"] == teaser_sha
    assert stored.metadata["analysis_input_format"] == "public_teaser_only_paywalled"


def RawItem_roundtrip(raw):
    """What the queue persists between runs (engine_cli: ``asdict(processing_raw)``)."""
    from dataclasses import asdict
    from radar_salud.models import RawItem
    return RawItem(**json.loads(json.dumps(asdict(raw))))


def test_budget_deferral_keeps_the_paid_binding(monkeypatch):
    from radar_salud import beta_sources
    from radar_salud.processing import DeferredProcessing
    monkeypatch.setattr(pulso_paywall, "capacity_available", lambda: False)
    raw = _processing_raw(_paid_item())
    before = _binding(raw.metadata)
    with pytest.raises(DeferredProcessing, match="budget_deferred"):
        beta_sources.process_curated_beta_source(raw, {"slug": "pulso_latercera", "market_role": "media"})
    assert _binding(raw.metadata) == before
    assert raw.metadata["analysis_model_output"]["_pulso_analysis_meta"]["response_id"] == "resp_full"


# --- 4. revive + attempts --------------------------------------------------------------------

def _unbilled_item(hours_ago=30, status="deferred", detected="2026-10-20T00:00:00+00:00", billed=False):
    at = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    history = [{"requested_at": at, "outcome": "failed_unbilled"} for _ in range(3)]
    if billed:
        history.append({"requested_at": at, "outcome": "failed_possibly_billed"})
    return {"source": "pulso_latercera", "status": status, "attempts": 4, "lane": "BACKFILL", "detected_at": detected,
            "raw": {"url": "u", "metadata": {pulso_paywall.STATE: {"history": history}}}}


def test_revive_is_bounded_and_reopens_only_unbilled_exhausted_items():
    items = {f"k{i}": _unbilled_item(detected=f"2026-10-2{i}T00:00:00+00:00") for i in range(3)}
    items["recent"] = _unbilled_item(hours_ago=1)
    items["billed"] = _unbilled_item(billed=True)
    revived = pulso_paywall.revive_deferred(items, limit=2)
    assert revived == ["k0", "k1"]
    for key in revived:
        assert items[key]["status"] == "retry" and items[key]["retry_at"] is None
        state = items[key]["raw"]["metadata"][pulso_paywall.STATE]
        assert state["revived_at"] and len(state["history"]) == 3  # history kept
        assert pulso_paywall._attempts(state) == (0, 0)
    assert items["k2"]["status"] == items["recent"]["status"] == items["billed"]["status"] == "deferred"


def test_engine_revives_before_processing():
    source = (ROOT / "src/radar_salud/engine_cli.py").read_text(encoding="utf-8")
    assert source.index("pulso_paywall.revive_deferred(queue.items)") < source.index("ready=((key,item)")
    assert "counted=reason not in NOT_ATTEMPTED_REASONS" in source


@pytest.mark.parametrize("reason", sorted(pulso_paywall.NOT_ATTEMPTED_REASONS))
def test_not_attempted_deferrals_do_not_count_toward_the_attempt_limit(tmp_path, reason):
    queue = PendingQueue(tmp_path / "q.json")
    queue.items["k"] = {"source": "pulso_latercera", "status": "retry", "attempts": 3, "lane": "LIVE",
                        "detected_at": "2026-10-28T00:00:00+00:00", "raw": {"url": "https://example.org/x"}}
    for _ in range(5):
        queue.start("k")
        queue.finish("k", "retry", reason, counted=False)
    assert queue.items["k"]["attempts"] == 3 and queue.items["k"]["uncounted_deferrals"] == 5
    assert queue.defer_exhausted(4) == 0 and queue.items["k"]["status"] == "retry"
    queue.start("k")
    queue.finish("k", "retry", "pulso_paywalled_reanalysis_call_failed_unbilled")  # a real attempt
    assert queue.items["k"]["attempts"] == 4 and queue.defer_exhausted(4) == 1


def test_run_cap_and_backoff_are_not_attempts():
    assert {"pulso_paywalled_reanalysis_run_cap_deferred",
            "pulso_paywalled_reanalysis_unbilled_backoff"} <= pulso_paywall.NOT_ATTEMPTED_REASONS
    assert "pulso_paywalled_reanalysis_call_failed_unbilled" not in pulso_paywall.NOT_ATTEMPTED_REASONS


# --- 5. 2-nov candidate ----------------------------------------------------------------------

def test_2_nov_candidate_is_on_hold_with_traced_minsal_figures_restored():
    doc = _json("data/weekly_insight/candidates/2026-11-02-wow.json")
    assert doc["status"] == "hold"
    assert doc["hold"]["reason"] == "rights_traceability_failed_after_metered_policy"
    assert doc["hold"]["date"] == "2026-10-28"
    insight = doc["weekly_insight"]
    assert insight["key_figures"] and all("Minsal" in k for k in insight["key_figures"])
    assert traced_field_problems(insight, "key_figures") == []
    assert all("minsal.cl" in u for urls in insight["fact_trace"]["fields"]["key_figures"] for u in urls)
    for url, src in insight["fact_trace"]["sources"].items():
        page = " ".join(_queue_page(url).split())
        assert _fragments(src["excerpt"], page)
    removed = next(r for r in insight["rights_redactions"] if r["field"] == "key_figures")
    assert insight["rights_restorations"][0]["receipt_of_removed_list"] == removed["sha256"]
    assert redact_public_payload(doc) == doc
