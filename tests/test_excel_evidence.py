import json
from pathlib import Path
import importlib.util
import pytest


def test_three_official_workbooks_have_reconciled_aggregate_evidence():
    families=json.loads(Path("data/excel/validated_series.json").read_text())["families"]
    assert set(families)=={"cartera","suscripciones","movilidad"}
    assert all(x["status"]=="validated" and len(x["sha256"])==64 and x["source_url"].startswith("https://www.superdesalud.gob.cl/") for x in families.values())
    assert [x["period"] for x in families["cartera"]["series"]]==[f"2026-{i:02d}" for i in range(1,8)]
    for x in families["cartera"]["series"]:
        m=x["metrics"]
        assert m["cotizantes"]+m["cargas"]==m["beneficiarios"]
    assert len(families["suscripciones"]["series"])==7
    for x in families["suscripciones"]["series"]:
        assert x["metrics"]["contratos_suscritos"]>=0 and x["metrics"]["desahucios_voluntarios"]>=0
    comparison=families["movilidad"]["series"][0]
    assert comparison["period_start"]=="2025-07" and comparison["period_end"]=="2026-07"
    assert comparison["period_type"]=="comparison_between_july_cuts"
    m=comparison["metrics"]
    assert m["entradas_intervalo"]-m["salidas_intervalo"]==m["diferencia_intervalo"]
    assert all("insights" not in x for x in families.values())


def test_schema_rejects_swapped_metric_columns_even_when_totals_would_balance():
    spec=importlib.util.spec_from_file_location("workbooks",Path("scripts/validate_isapre_workbooks.py"))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class Sheet:
        def __getitem__(self,key):
            return type("Cell",(),{"value":"ENERO 2026"})()
        def cell(self,row,column):
            headers={1:"Cód.",2:"Isapre",3:"N°\nDesahucios Voluntarios",4:"N° Contratos Suscritos",5:"N° Desahucios por parte de la Isapre"}
            return type("Cell",(),{"value":headers[column]})()
    with pytest.raises(ValueError,match="Unknown suscripciones schema"):
        module._monthly({"Enero":Sheet()},"suscripciones")
    for bad in (-1, 0.5, "3"):
        with pytest.raises(ValueError,match="Required count|Non-numeric"):
            module._count(bad)
