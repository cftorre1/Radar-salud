import copy
import json
from pathlib import Path

from radar_salud.isapre_pulse import build_pulse


def canonical():
    return json.loads(Path("data/excel/validated_series.json").read_text(encoding="utf-8"))


def test_pulse_reconciles_real_three_family_series():
    pulse = build_pulse(canonical())
    assert pulse is not None
    assert pulse["data_insight_meta"]["families"] == ["cartera", "suscripciones", "movilidad"]
    assert pulse["data_period"] == "2026-07"
    assert pulse["event_date"] == "2026-07-31"
    assert "2.487.497" in pulse["what_happened"]
    assert "-17.700" in " ".join(pulse["key_points"])
    assert pulse["ingestion_mode"] == "BACKFILL"
    assert len(pulse["data_insights"]) == 1
    assert len(pulse["data_insight_evidence"]) == 1
    assert "Datos" not in pulse["data_insights"][0]
    assert pulse["data_insight_evidence"][0]["period"] == "2026-06 → 2026-07"


def test_pulse_fails_closed_for_missing_unvalidated_or_unreconciled_family():
    base = canonical()
    for change in (
        lambda v: v["families"].pop("movilidad"),
        lambda v: v["families"]["cartera"].update(status="pending"),
        lambda v: v["families"]["suscripciones"]["series"][-1].update(period="2026-06"),
        lambda v: v["families"]["movilidad"]["series"][-1]["metrics"].update(entradas_intervalo=1),
        lambda v: v["families"]["cartera"]["series"][-1]["metrics"].update(beneficiarios=1),
        lambda v: v["families"]["cartera"].update(sha256="0" * 63 + "z"),
        lambda v: v["families"]["cartera"].update(source_url="https://example.org/file.xlsx"),
        lambda v: v["families"]["cartera"]["series"][1]["metrics"].update(beneficiarios=1),
        lambda v: v["families"]["cartera"]["series"][0].update(period="2026-07"),
        lambda v: v["families"]["suscripciones"]["series"][5]["metrics"].update(contratos_suscritos=0),
        lambda v: v["families"]["movilidad"]["series"][0].update(period_start="2026-06"),
    ):
        altered = copy.deepcopy(base)
        change(altered)
        assert build_pulse(altered) is None
