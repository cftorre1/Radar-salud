"""Rights redaction (Dirección 28-oct-2026) must never reopen a committee HOLD/REJECT.

A paywalled DF row is redacted to title + public lead; its editorial decision, committee
verdict, independent-review decision and feed_visibility are publication contracts and
must survive, so the exported feed keeps the item hidden. A PASS control proves the
fixture would otherwise be published.
"""
import copy
import importlib.util
import json
from datetime import date
from pathlib import Path

from radar_salud.source_rights import redact_signal

spec = importlib.util.spec_from_file_location("snap_rights_gate", Path("scripts/export_web_snapshot.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

HISTORY = Path("data/history/superintendencia_signals.json")
DF_URL = "https://www.df.cl/economia-y-politica/actualidad/aluvion-en-las-condes-obliga-a-cerrar-por-semanas-la-clinica-san-carlos"
LOCKED = "Cuerpo bajo muro de pago que no puede publicarse. " * 8


def _base():
    rows = json.loads(HISTORY.read_text(encoding="utf-8"))["signals"]
    row = copy.deepcopy(next(s for s in rows if s.get("source_url") == DF_URL))
    # Reintroduce locked-body prose so the redaction has real work to do.
    row.update(why_it_matters=LOCKED, card_why=LOCKED, key_points=[LOCKED], paywalled=False)
    return row


def _variant(base, slug, verdict, decision):
    row = copy.deepcopy(base)
    row["source_url"] = f"{DF_URL}-{slug}"
    row["title"] = f"{base['title']} ({slug})"
    if decision:
        row["editorial_decision"] = decision
        row["feed_visibility"] = False
        row["editorial_review"] = {"schema_version": "pulso_editorial_review_v1", "decision": decision,
                                   "reason": "Comité: " + LOCKED, "reviewed_at": "2026-10-11"}
    row["editorial_committee"] = dict(row.get("editorial_committee") or {}, verdict=verdict,
                                      publication_decision=decision or "accept", why_it_matters=LOCKED)
    return row


def test_redaction_keeps_committee_reject_and_hold_out_of_the_export(monkeypatch):
    base = _base()
    control = _variant(base, "pass", "PASS", None)
    rejected = _variant(base, "reject", "REJECT", "reject")
    held = _variant(base, "hold", "HOLD", "group")
    redacted = [redact_signal(r, r.get("public_teaser") or r["what_happened"][:300]) for r in (control, rejected, held)]

    for before, after in zip((control, rejected, held), redacted):
        assert after["paywalled"] is True and after["why_it_matters"] == "" and "key_points" not in after
        assert LOCKED.strip() not in json.dumps(after, ensure_ascii=False)
        assert after["editorial_committee"]["verdict"] == before["editorial_committee"]["verdict"]
        assert after.get("editorial_decision") == before.get("editorial_decision")
        assert after.get("feed_visibility") == before.get("feed_visibility")
        if before.get("editorial_review"):
            assert after["editorial_review"]["decision"] == before["editorial_review"]["decision"]
            assert after["editorial_review"]["schema_version"] == "pulso_editorial_review_v1"

    # The persistent audit also rejects one of them by URL (keyed by URL, not by text).
    monkeypatch.setattr(m, "_audit_map", lambda: {rejected["source_url"]: {"decision": "reject"}})
    monkeypatch.setattr(m, "_exclusions", lambda: {})
    cards = m.curate(copy.deepcopy(redacted), resolve_external=False, as_of=date(2026, 10, 12))
    cards = [redact_signal(c) for c in cards]
    urls = {c.get("source_url") for c in cards if c.get("feed_visibility") is not False}
    assert control["source_url"] in urls, "PASS control must publish (fixture sanity)"
    assert rejected["source_url"] not in urls
    assert held["source_url"] not in urls
    for card in cards:
        if card.get("source_url") == control["source_url"]:
            assert card["editorial_committee"]["verdict"] == "PASS" and card["card_why_optional"] is True
