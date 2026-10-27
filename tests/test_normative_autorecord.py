import importlib.util
import json
import shutil
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import scripts.export_web_snapshot as exporter
from src.radar_salud import normative_autorecord as auto
from src.radar_salud.normative_evidence import EVIDENCE_DIR, _key

URL = "https://www.superdesalud.gob.cl/normativa/circular-if-n537/"
PDF = "https://www.superdesalud.gob.cl/app/uploads/2026/10/circular-if-n-537-2026.pdf"
EVIDENCE = ("CIRCULAR IF/N°537. Imparte instrucciones sobre el procedimiento interno de notificación de casos de "
            "urgencia vital o de secuela funcional grave GES y Ley Ricarte Soto. Los prestadores deberán contar con "
            "un procedimiento interno escrito de notificación. La notificación deberá efectuarse dentro de 24 horas. "
            "Las presentes instrucciones entrarán en vigencia a contar del 1 de marzo de 2027. " * 3)
GOOD = {"plain_language_title": "Circular IF/N°537 · Urgencias GES: exige a prestadores notificar en 24 horas",
        "subject_terms": ["Urgencias GES"], "action_terms": ["notificar"],
        "normative_context": "Obliga a los prestadores a tener un procedimiento escrito para notificar casos de urgencia vital GES y Ricarte Soto dentro de 24 horas. Rige desde el 1 de marzo de 2027.",
        "evidence_quotes": ["La notificación deberá efectuarse dentro de 24 horas.",
                            "Las presentes instrucciones entrarán en vigencia a contar del 1 de marzo de 2027."]}


def test_verify_accepts_faithful_record_and_rejects_invented_numbers():
    assert auto.verify(GOOD, "Circular IF/N°537", EVIDENCE) == []
    bad = {**GOOD, "normative_context": GOOD["normative_context"].replace("24 horas", "48 horas")}
    assert any(p.startswith("number_not_in_official_text") for p in auto.verify(bad, "Circular IF/N°537", EVIDENCE))
    assert "quote_not_literal" in auto.verify({**GOOD, "evidence_quotes": ["Esta cita completamente inventada no aparece en el texto oficial.", "Otra frase larga que tampoco existe en la circular oficial."]}, "Circular IF/N°537", EVIDENCE)
    assert "identity_must_head_title_once" in auto.verify({**GOOD, "plain_language_title": "Urgencias GES: notificar"}, "Circular IF/N°537", EVIDENCE)


def _repo(tmp_path):
    (tmp_path / "config").mkdir()
    shutil.copy("config/normative_editorial_v2.json", tmp_path / "config")
    (tmp_path / EVIDENCE_DIR).mkdir(parents=True)
    (tmp_path / EVIDENCE_DIR / f"{_key(PDF)}.json").write_text(json.dumps({"text": EVIDENCE}), encoding="utf-8")
    return [{"title": "Circular IF/N°537", "normative_document_label": "Circular IF/N°537", "source_url": URL,
             "source_name": "Superintendencia de Salud", "signal_types": ["Normativa"], "event_date": "2026-10-19",
             "official_subject": "Imparte instrucciones sobre el procedimiento interno de notificación de casos de urgencia vital",
             "source_documents": [{"url": PDF}]}]


def test_build_writes_only_records_that_pass_both_checks(tmp_path):
    signals = _repo(tmp_path)
    calls = []
    def fake(prompt, *, feature, preferred_model, allow_luna_fallback=True):
        calls.append(feature)
        return SimpleNamespace(output=GOOD if feature == "normative_autorecord" else {"verdict": "PASS"})
    assert auto.build_auto_records(tmp_path, signals, call=fake, today=date(2026, 10, 27)) == [URL]
    assert calls == ["normative_autorecord", "normative_autorecord_review"]
    assert auto.load_auto_records(tmp_path)[URL]["origin"] == "auto_verified"
    # Idempotent: no new model calls for an act that already has a record.
    assert auto.build_auto_records(tmp_path, signals, call=fake, today=date(2026, 10, 27)) == [] and len(calls) == 2


def test_failed_review_is_recorded_and_not_published(tmp_path):
    signals = _repo(tmp_path)
    def fake(prompt, *, feature, preferred_model, allow_luna_fallback=True):
        return SimpleNamespace(output=GOOD if feature == "normative_autorecord" else {"verdict": "FAIL", "reason": "exagera"})
    assert auto.build_auto_records(tmp_path, signals, call=fake, today=date(2026, 10, 27)) == []
    store = json.loads((tmp_path / auto.AUTO_PATH).read_text())
    assert URL in store["rejected"] and not store["source_records"]


def test_human_record_wins_and_auto_record_feeds_the_contract(tmp_path, monkeypatch):
    human = {"records": {}, "source_records": {URL: {"plain_language_title": "humano"}}}
    (tmp_path / "data/analysis_cache").mkdir(parents=True)
    (tmp_path / auto.AUTO_PATH).write_text(json.dumps({"source_records": {URL: {"plain_language_title": "auto"}, "x": {"plain_language_title": "solo auto"}}}))
    cfg = auto.merged_config(tmp_path, human)
    assert cfg["source_records"][URL]["plain_language_title"] == "humano" and cfg["source_records"]["x"]["plain_language_title"] == "solo auto"



def test_review_findings_are_now_rejected():
    L = "Circular IF/N°537"
    def bad(**kw): return auto.verify({**GOOD, **kw}, L, EVIDENCE)
    # number as substring of 2027 ("2 horas") is not accepted
    assert any(p.startswith("number_not_in_official_text:2") or p.startswith("number_not_backed") for p in
               bad(normative_context=GOOD["normative_context"].replace("24 horas", "2 horas")))
    # wrong month in words
    assert any(p.startswith("month_not_in_official_text:abril") for p in
               bad(normative_context=GOOD["normative_context"].replace("1 de marzo de 2027", "abril")))
    # one-character terms given as a string
    assert "terms_must_be_lists_of_words" in bad(subject_terms="U", action_terms="n")
    # short, generic quotes
    assert "quote_too_short" in bad(evidence_quotes=["GES", "urgencia"])
    # exaggerated legal effect absent from the text
    assert any(p.startswith("strong_effect_not_in_text:prohíbe") for p in
               bad(plain_language_title="Circular IF/N°537 · Urgencias GES: prohíbe y obliga a notificar en 24 horas"))
    # Nº and N.° labels normalize like N°
    assert auto.verify({**GOOD, "plain_language_title": GOOD["plain_language_title"].replace("N°", "Nº")}, L, EVIDENCE) == []


def test_numbered_human_records_are_never_shadowed(tmp_path):
    (tmp_path / "data/analysis_cache").mkdir(parents=True)
    (tmp_path / auto.AUTO_PATH).write_text(json.dumps({"source_records": {
        "https://x/535": {"legal_identity": "Circular IF/N°535", "plain_language_title": "auto"},
        "https://x/537": {"legal_identity": "Circular IF/N°537", "plain_language_title": "auto 537"}}}))
    cfg = auto.merged_config(tmp_path, {"records": {"535": {"plain_language_title": "humano"}}})
    assert "https://x/535" not in cfg["source_records"] and "https://x/537" in cfg["source_records"]


def test_builder_skips_numbered_human_act_and_survives_bad_evidence(tmp_path):
    signals = _repo(tmp_path)
    human = json.loads((tmp_path / "config/normative_editorial_v2.json").read_text())
    human.setdefault("records", {})["537"] = {"plain_language_title": "humano"}
    (tmp_path / "config/normative_editorial_v2.json").write_text(json.dumps(human))
    calls = []
    fake = lambda *a, **k: calls.append(1) or SimpleNamespace(output=GOOD)
    assert auto.build_auto_records(tmp_path, signals, call=fake, today=date(2026, 10, 27)) == [] and not calls
    del human["records"]["537"]; (tmp_path / "config/normative_editorial_v2.json").write_text(json.dumps(human))
    (tmp_path / EVIDENCE_DIR / f"{_key(PDF)}.json").write_text("{not json")
    assert auto.build_auto_records(tmp_path, signals, call=fake, today=date(2026, 10, 27)) == []
    assert (tmp_path / auto.AUTO_PATH).exists()


def test_rejected_act_is_retried_only_when_official_text_changes(tmp_path):
    signals = _repo(tmp_path)
    verdicts = iter([{"verdict": "FAIL", "reason": "x"}, {"verdict": "PASS"}])
    def fake(prompt, *, feature, preferred_model, allow_luna_fallback=True):
        return SimpleNamespace(output=GOOD if feature == "normative_autorecord" else next(verdicts))
    assert auto.build_auto_records(tmp_path, signals, call=fake, today=date(2026, 10, 27)) == []
    assert auto.build_auto_records(tmp_path, signals, call=fake, today=date(2026, 10, 27)) == []  # same text: no retry
    (tmp_path / EVIDENCE_DIR / f"{_key(PDF)}.json").write_text(json.dumps({"text": EVIDENCE + " Texto corregido."}))
    assert auto.build_auto_records(tmp_path, signals, call=fake, today=date(2026, 10, 27)) == [URL]
