import copy
import json
from pathlib import Path

from radar_salud.isapre_insights import derive


def canonical():
    return json.loads(Path("data/excel/validated_series.json").read_text())


def test_real_series_have_reconciled_periods_formulas_and_official_sources():
    result = derive(canonical())
    assert result["status"] == "validated"
    assert len(result["insights"]) == 8
    for item in result["insights"]:
        assert item["family"] in {"cartera", "suscripciones", "movilidad"}
        assert item["period"] and item["formula"] and item["sheet"]
        assert item["source_url"].startswith("https://www.superdesalud.gob.cl/")
        assert len(item["sha256"]) == 64
    assert "-1.761" in result["insights"][0]["text"]
    assert "no equivalen a cambio neto" in result["insights"][4]["text"]
    assert result["insights"][-1]["period"] == "2025-07 → 2026-07"
    assert "No es variación mensual" in result["insights"][-1]["text"]
    assert all(x["observations"] == 6 for x in result["anomaly_checks"].values())


def test_adversarial_period_schema_and_denominators_fail_closed():
    changes = (
        lambda x: x["families"]["cartera"]["series"].pop(1),
        lambda x: x["families"]["suscripciones"]["series"][3].update(period="2026-05"),
        lambda x: x["families"]["cartera"]["series"][2]["metrics"].update(beneficiarios=0),
        lambda x: x["families"]["suscripciones"]["series"][5]["metrics"].update(contratos_suscritos=0),
        lambda x: x["families"]["movilidad"]["series"][0].update(period_start="2026-06"),
        lambda x: x["families"]["movilidad"]["series"][0]["metrics"].update(diferencia_intervalo=-17700.0),
        lambda x: x["families"]["cartera"].update(schema="unknown"),
        lambda x: x["families"]["cartera"].update(family="movilidad"),
        lambda x: x["families"]["cartera"].update(sha256="bad"),
    )
    for change in changes:
        altered = copy.deepcopy(canonical())
        change(altered)
        result = derive(altered)
        assert result["insights"] == []
        assert result["status"] != "validated"
