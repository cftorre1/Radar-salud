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
                            "entrarán en vigencia a contar del 1 de marzo de 2027"]}


def test_verify_accepts_faithful_record_and_rejects_invented_numbers():
    assert auto.verify(GOOD, "Circular IF/N°537", EVIDENCE) == []
    bad = {**GOOD, "normative_context": GOOD["normative_context"].replace("24 horas", "48 horas")}
    assert any(p.startswith("number_not_in_official_text") for p in auto.verify(bad, "Circular IF/N°537", EVIDENCE))
    assert "quote_not_literal" in auto.verify({**GOOD, "evidence_quotes": ["cita inventada", "otra"]}, "Circular IF/N°537", EVIDENCE)
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
