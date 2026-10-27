import json
from pathlib import Path

import scripts.export_web_snapshot as exporter
from src.radar_salud.editorial_gate import is_institutional_agenda, publication_ready

SUSESO = "Superintendencia de Seguridad Social (SUSESO)"


def test_regulator_agenda_is_noise_but_material_outcomes_are_not():
    assert is_institutional_agenda({"source_name": SUSESO, "title": "Suseso participa en mesa nacional para fortalecer la seguridad laboral de buzos"})
    assert not is_institutional_agenda({"source_name": SUSESO, "title": "Superintendenta presenta avances en fiscalización del uso de licencias médicas ante Comisión de Salud del Senado"})
    assert not is_institutional_agenda({"source_name": SUSESO, "title": "Suseso sanciona a emisores de licencias"})
    assert not is_institutional_agenda({"source_name": "Diario Financiero", "title": "Isapre participa en licitación"})
    r = {"source_name": SUSESO, "title": "Suseso participa en sesión especial de la Comisión de Minería", "source_url": "https://www.suseso.gob.cl/x",
         "event_date": "2026-10-22", "what_happened": "Participó.", "why_it_matters": "Contexto institucional."}
    assert publication_ready(r)[1] == "institutional_agenda"


def test_direccion_exclusions_never_reach_the_feed():
    excluded = {x["url"] for x in json.loads(Path("config/editorial_exclusions.json").read_text())["items"]}
    assert len(excluded) == 4
    history = json.loads(Path("data/history/superintendencia_signals.json").read_text())["signals"]
    shown = {r.get("source_url") for r in exporter.curate(history, resolve_external=False) if r.get("feed_visibility") is not False}
    assert not excluded & shown
