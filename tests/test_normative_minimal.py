import importlib.util
import json
from pathlib import Path

import scripts.export_web_snapshot as exporter
from src.radar_salud.normative_minimal import (
    BADGE, DISCLAIMER, INTERPRETIVE_FIELDS, act_scope, minimal_card)

SIS = "Superintendencia de Salud"
SUSESO = "Superintendencia de Seguridad Social (SUSESO)"
OFFICIAL_537 = ("Imparte instrucciones sobre el procedimiento interno de notificación de casos de urgencia "
                "vital o de secuela funcional grave GES y Ley Ricarte Soto en la aplicación informática de la "
                "Superintendencia de Salud.")


def _if537(**extra):
    row = {"title": "Circular IF/N°537", "source_name": SIS, "event_date": "2026-10-19",
           "source_url": "https://www.superdesalud.gob.cl/normativa/circular-if-n537/",
           "official_subject": OFFICIAL_537,
           "what_happened": "Interpretación automática que no debe publicarse sin revisión.",
           "why_it_matters": "Impacto interpretado.", "scopes": ["Prestadores"],
           "key_points": ["Punto automático"], "validity_text": "Vigencia interpretada",
           "related_reference_contexts": [{"id": "Circular IF/N°77", "relationship": "modificado"}]}
    row.update(extra)
    return row


def _curated_by_url():
    history = json.loads(Path("data/history/superintendencia_signals.json").read_text())["signals"]
    return {r["source_url"]: r for r in exporter.curate(history, resolve_external=False)}


def test_general_act_gets_only_listing_facts_badge_and_disclaimer():
    card = minimal_card(_if537(), "Circular IF/N°537")
    assert card["display_title"].startswith("Circular IF/N°537 · Superintendencia de Salud: Imparte instrucciones")
    assert card["normative_context"].startswith("Emitida por Superintendencia de Salud con fecha 2026-10-19. Asunto oficial: Imparte")
    assert card["editorial_badge"] == BADGE and card["why_it_matters"] == DISCLAIMER == card["card_why"]
    text = json.dumps(card, ensure_ascii=False)
    for leaked in ("Interpretación automática", "Impacto interpretado", "Punto automático", "Vigencia interpretada", "Circular IF/N°77"):
        assert leaked not in text
    assert all(card[f] is None for f in INTERPRETIVE_FIELDS)


def test_without_official_subject_nothing_is_published():
    assert minimal_card(_if537(official_subject=None), "Circular IF/N°537") is None


def test_individual_acts_never_get_a_card():
    for subject in ("Inscríbase en el Registro Público de Prestadores Institucionales de Salud Acreditados, al Prestador X",
                    "Manténgase con la inscripción N°1104 en el Registro Público de Prestadores",
                    "Rectifíquese la Resolución Exenta IP/N°3733",
                    "Autoriza, de forma excepcional a la Isapre Colmena Golden Cross S.A. a efectuar la reliquidación"):
        row = _if537(title="Resolución Exenta IF/N°1", official_subject=subject)
        assert act_scope(row, "Resolución Exenta IF/N°1") == "particular"
        assert minimal_card(row, "Resolución Exenta IF/N°1") is None


def test_unofficial_domain_or_diario_oficial_stay_held():
    assert minimal_card(_if537(source_url="https://superdesalud.gob.cl.example.com/x"), "Circular IF/N°537") is None
    assert minimal_card(_if537(source_name="Diario Oficial", source_url="https://www.diariooficial.interior.gob.cl/x.pdf"),
                        "Circular IF/N°537") is None


def test_real_history_minimal_rows_carry_no_interpretation():
    rows = _curated_by_url()
    if537 = rows["https://www.superdesalud.gob.cl/normativa/circular-if-n537/"]
    assert if537["normative_minimal"] and if537["editorial_badge"] == BADGE
    assert "procedimiento interno de notificación" in if537["display_title"]
    minimal = [r for r in rows.values() if r.get("normative_minimal")]
    assert minimal and all(not r.get(f) for r in minimal for f in INTERPRETIVE_FIELDS)
    c3921 = next(r for r in minimal if r.get("normative_document_label", "").endswith("3921"))
    assert "Vigencia" not in json.dumps(c3921, ensure_ascii=False)
    # IF/11168 is an exceptional authorization to one Isapre (official subject): never a card,
    # and its automated analysis (bound to IF/11156's PDF) must not surface.
    assert "https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n11168/" not in rows


def test_reviewer_accepts_real_minimal_card_and_rejects_leaks(tmp_path):
    spec = importlib.util.spec_from_file_location("reviewer", Path("scripts/review_candidate.py"))
    reviewer = importlib.util.module_from_spec(spec); spec.loader.exec_module(reviewer)
    base = _curated_by_url()["https://www.superdesalud.gob.cl/normativa/circular-if-n537/"]
    (tmp_path / "data").mkdir()

    def codes(sig):
        (tmp_path / "data/radar_today.json").write_text(
            json.dumps({"generated_at": "2026-10-26T00:00:00+00:00", "signals": [sig]}), encoding="utf-8")
        return [f["code"] for f in reviewer.review(tmp_path, "sha")["findings"] if f["category"] == "editorial"]

    assert "normative_minimal_contract" not in codes(base)
    for bad in ({"why_it_matters": "Las isapres deberán cambiar procesos."}, {"editorial_badge": None},
                {"key_points": ["interpretación"]}, {"validity_text": "desde marzo"}, {"card_why": None},
                {"display_title": "Circular IF/N°537 · Nuevo deber de notificar en 24 horas"}):
        assert "normative_minimal_contract" in codes({**base, **bad}), bad
