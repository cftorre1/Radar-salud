import json
from datetime import date
from pathlib import Path

import scripts.export_web_snapshot as exporter
from src.radar_salud.accreditation_pulse import accreditation_pulse

SIS = "Superintendencia de Salud"


def _act(n, subject, day="2026-10-05"):
    return {"title": f"Resolución Exenta IP/N°{n}", "source_name": SIS, "event_date": day,
            "source_url": f"https://www.superdesalud.gob.cl/normativa/resolucion-exenta-ip-n{n}/",
            "official_subject": subject, "what_happened": "Análisis automático que no debe usarse."}


def test_pulse_reads_names_only_from_official_listing():
    acts = [
        _act(1, "Inscríbase en el Registro Público de Prestadores Institucionales de Salud Acreditados, al Prestador Institucional Clínica Uno, de la Ciudad de Talca, Región del Maule"),
        _act(2, "Manténgase con la inscripción N°2 en el Registro Público de Prestadores Institucionales de Salud Acreditados, al Prestador Institucional Clínica Dávila, de la Comuna de Recoleta, Región Metropolitana"),
        _act(3, "Autorizase a la sociedad denominada Alborada SpA, con nombre de fantasía Alborada para la ejecución de actividades de evaluación"),
        _act(4, "Rectifiquese la Resolución Exenta IP/N°3733"),
        _act(5, "Manténgase … al Prestador Institucional Antigua, de la Ciudad de Arica", day="2026-08-01"),
        {**_act(6, "Inscríbase … al Prestador Institucional Otra, de la Ciudad de Lota"), "source_name": "Diario Oficial"},
    ]
    p = accreditation_pulse(acts, date(2026, 10, 27))
    assert p["title"] == "Acreditación de prestadores · últimos 30 días: 4 actos"
    assert "Clínica Uno (Talca)" in p["what_happened"] and "Clínica Dávila (Recoleta)" in p["what_happened"]
    assert "Alborada" in p["what_happened"] and "1 rectificaciones" in p["what_happened"]
    assert "Antigua" not in p["what_happened"] and "Otra" not in p["what_happened"]
    assert "Análisis automático" not in json.dumps(p, ensure_ascii=False)
    assert p["accreditation_counts"] == {"new": 1, "kept": 1, "entity": 1, "fix": 1}
    assert len(p["source_alternatives"]) == 4 and p["scopes"] == ["Prestadores"]


def test_no_acts_no_card():
    assert accreditation_pulse([], date(2026, 10, 27)) is None


def test_real_history_shows_one_pulse_and_no_individual_acts():
    history = json.loads(Path("data/history/superintendencia_signals.json").read_text())["signals"]
    curated = exporter.curate(history, resolve_external=False)
    pulses = [r for r in curated if r.get("event_type") == "ACCREDITATION_PULSE"]
    assert len(pulses) == 1 and pulses[0]["source_alternatives"]
    individual = {a["url"] for a in pulses[0]["source_alternatives"]}
    assert not [r for r in curated if r.get("source_url") in individual]
