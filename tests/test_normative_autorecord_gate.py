"""Verified automatic records must export as reviewed cards and pass the editorial gate (hourly run 10-nov-2026)."""
import importlib.util
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import radar_salud.normative_autorecord as auto
from radar_salud.normative_evidence import EVIDENCE_DIR, _key

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exporter = _load("export_web_snapshot_gate", "scripts/export_web_snapshot.py")
reviewer = _load("review_candidate_gate", "scripts/review_candidate.py")

TEXT = ("CIRCULAR IF/N°541. Aclara la determinación de la base de cálculo del deducible de la cobertura adicional "
        "para enfermedades catastróficas. Las isapres deberán considerar el deducible anual en la base de cálculo. "
        "Las presentes instrucciones entrarán en vigencia a contar de su notificación a las instituciones. ") * 3
CASES = {
    "541": dict(title="Circular IF/N°541 - Emisión: 5/11/2026", source_name="Superintendencia de Salud",
                source_url="https://www.superdesalud.gob.cl/normativa/circular-if-n541-emision-5-11-2026/",
                pdf="https://www.superdesalud.gob.cl/app/uploads/2026/11/circular-if-n-541-2026.pdf",
                identity="Circular IF/N°541"),
    "3937": dict(title="Circular 3937", source_name="Superintendencia de Seguridad Social (SUSESO)",
                 source_url="https://www.suseso.gob.cl/612/w3-article-793865.html", pdf=None,
                 identity="Circular N°3937"),
}


def _signal(case):
    c = CASES[case]
    s = {"title": c["title"], "source_name": c["source_name"], "source_url": c["source_url"],
         "signal_types": ["Normativa"], "event_type": "REGULATION", "event_date": "2026-11-05",
         "detected_at": "2026-11-07T06:16:48+00:00", "category": "Normativa",
         "official_subject": "Aclara la determinación de la base de cálculo del deducible de la cobertura adicional",
         "what_happened": "La Superintendencia aclaró la determinación de la base de cálculo del deducible CAEC.",
         "why_it_matters": "Cambia cómo las isapres calculan el deducible anual de la cobertura catastrófica.",
         "source_documents": [{"url": c["pdf"]}] if c["pdf"] else []}
    return s


def _record(identity):
    return {"plain_language_title": f"{identity} · Deducible: aclara la base de cálculo",
            "subject_terms": ["Deducible"], "action_terms": ["aclara"],
            "normative_context": "Las isapres deberán considerar el deducible anual en la base de cálculo.",
            "evidence_quotes": ["Las isapres deberán considerar el deducible anual en la base de cálculo.",
                                "Las presentes instrucciones entrarán en vigencia a contar de su notificación a las instituciones."]}


def _gate(tmp_path, signal, records, monkeypatch):
    monkeypatch.setattr(auto, "load_auto_records",
                        lambda root: {u: auto._canonical_record(r) for u, r in records.items()})
    exported = exporter._normative_contract(signal)
    web = tmp_path / "web"
    (web / "data").mkdir(parents=True)
    (web / "data/radar_today.json").write_text(json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(), "signals": [exported]}, ensure_ascii=False))
    result = reviewer.review(web, "sha")
    critical = [(f["code"], f["path"], f["detail"]) for f in result["findings"]
                if f["category"] == "editorial" and f["severity"] == "critical"]
    return exported, critical


@pytest.mark.parametrize("case", ["541", "3937"])
def test_builder_record_exports_reviewed_and_passes_editorial_gate(tmp_path, monkeypatch, case):
    c = CASES[case]
    signal = _signal(case)
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    shutil.copy(ROOT / "config/normative_editorial_v2.json", root / "config")
    doc = c["pdf"] or c["source_url"]
    (root / EVIDENCE_DIR).mkdir(parents=True)
    (root / EVIDENCE_DIR / f"{_key(doc)}.json").write_text(json.dumps({"text": TEXT}), encoding="utf-8")
    prompts = []
    def fake(prompt, *, feature, preferred_model, allow_luna_fallback=True):
        prompts.append(prompt)
        out = {"verdict": "PASS"} if feature == auto.REVIEW_FEATURE else _record(c["identity"])
        return SimpleNamespace(output=out, estimated_cost_usd=0.01)
    written = auto.build_auto_records(root, [signal], call=fake, today=date(2026, 11, 10), run_id="r1",
                                      headroom=lambda: 1.0)
    assert written == [c["source_url"]]
    assert f"'{c['identity']} · '" in prompts[0]  # the model is asked for the canonical identity
    records = json.loads((root / auto.AUTO_PATH).read_text(encoding="utf-8"))["source_records"]
    assert records[c["source_url"]]["legal_identity"] == c["identity"]
    exported, critical = _gate(tmp_path, signal, records, monkeypatch)
    assert exported["normative_editorial"]["editorial_state"] == "reviewed" and not exported.get("normative_minimal")
    assert exported["display_title"] == f"{c['identity']} · Deducible: aclara la base de cálculo"
    assert critical == []


def test_records_written_with_listing_identity_are_canonicalised_on_read(tmp_path, monkeypatch):
    # Shape the 10-nov hourly run wrote for SUSESO acts: listing identity "Circular 3937".
    signal = _signal("3937")
    legacy = {**_record("Circular 3937"), "legal_identity": "Circular 3937", "origin": "auto_verified"}
    exported, critical = _gate(tmp_path, signal, {CASES["3937"]["source_url"]: legacy}, monkeypatch)
    assert exported["display_title"].startswith("Circular N°3937 · ") and critical == []
    # Before this fix the exporter fell back to the minimal card and the gate rejected it.
    monkeypatch.setattr(auto, "load_auto_records", lambda root: {CASES["3937"]["source_url"]: legacy})
    exported = exporter._normative_contract(signal)
    assert exported.get("normative_minimal")


def test_canonical_identity_matches_the_exporter():
    titles = ["Circular IF/N°541 - Emisión: 5/11/2026", "Circular 3937", "Resolución Exenta IF/N°12",
              "Oficio Circular IF/N°20", "Circular IP N°99", "Dictamen 159061-2026", "Circular N°3.938"]
    for t in titles:
        r = exporter._normative_contract({"title": t, "signal_types": ["Normativa"], "source_url": "https://x/" + t})
        assert auto.canonical_identity(t) == r["legal_identity"], t
    assert auto.canonical_identity("Dictamen O-01-S-04558-2026") == "Dictamen O-01-S-04558-2026"
