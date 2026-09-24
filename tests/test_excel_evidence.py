import json
from pathlib import Path


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
    m=families["movilidad"]["series"][0]["metrics"]
    assert m["entradas"]-m["salidas"]==m["diferencia"]
    assert all("insights" not in x for x in families.values())
