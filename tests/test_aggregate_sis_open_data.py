"""Synthetic-fixture tests for scripts/aggregate_sis_open_data.py (no network)."""
from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "aggregate_sis_open_data", Path(__file__).resolve().parents[1] / "scripts" / "aggregate_sis_open_data.py")
agg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agg)


def prest_row(isapre="67", prov="P1", codigo="0101001", region="13", freq=1, fact=10000, bonif=6000, copago=4000,
              pertenencia="Fonasa", atencion="Ambulatorio", tipo_prest="Privado"):
    f = [""] * 30
    f[0], f[1], f[2], f[3] = isapre, "2026t2", "1", "SECRETBEN"
    f[7], f[8], f[14], f[15] = prov, region, codigo, pertenencia
    f[10] = f[11] = f[12] = f[13] = "SECRETFOLIO"
    f[18], f[19], f[20], f[21], f[22], f[23] = tipo_prest, atencion, str(freq), str(fact), str(bonif), str(copago)
    return f


def lic_row(isapre="81", resol="Autoricese", dias=5, aut=5, diag="J00-J99", region="13", sub=50000,
            rec="2026t2", res="2026t2", act="Comercio", prof="Medico"):
    f = [""] * 44
    f[0], f[2], f[4], f[8], f[12], f[13] = isapre, "SECRETWORKER", str(dias), act, "SECRETDOC", prof
    f[15], f[16], f[17], f[21], f[22], f[24], f[28] = str(aut), diag, resol, rec, res, region, str(sub)
    f[42] = "SECRETEMPLOYER"
    return f


def make_zip(path: Path, name: str, lines: list, encoding="latin-1") -> Path:
    lines = [x if isinstance(x, str) else "|".join(x) + "|" for x in lines]  # real files end rows with a pipe
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(name, ("\r\n".join(lines) + "\r\n").encode(encoding))
    return path


def test_row_reader_counts_malformed_and_trailing_pipe(tmp_path):
    z = make_zip(tmp_path / "p.zip", "p.txt", [prest_row(), "1|2|3", prest_row(region="Región Ñuble")])
    rec: dict = {}
    seen = []
    agg.process_zip(z, agg.PREST_N, seen.append, rec)
    assert rec["parse"]["rows_ok"] == 2 and rec["parse"]["rows_malformed"] == 1
    assert rec["parse"]["field_count_histogram"] == {"3": 1, "30": 2}
    assert seen[1][8] == "Región Ñuble"  # latin-1 decoded


def test_header_row_is_detected_and_skipped(tmp_path):
    header = "|".join(agg.PREST_NAMES)
    z = make_zip(tmp_path / "p.zip", "p.txt", [header, prest_row()])
    rec: dict = {}
    a = agg.PrestacionesAgg()
    agg.process_zip(z, agg.PREST_N, a.add, rec)
    assert rec["parse"]["header_row_detected"] and a.rows == 1


def test_price_disclosure_rule():
    a = agg.PrestacionesAgg()
    # region 13: 3 providers, total freq 30 -> publishable
    for prov, unit in (("A", 100), ("B", 200), ("C", 300)):
        a.add(prest_row(prov=prov, freq=10, fact=unit * 10))
    # region 5: 2 providers -> concentration flag, no price
    a.add(prest_row(prov="A", region="5", freq=40, fact=4000))
    a.add(prest_row(prov="D", region="5", freq=10, fact=5000))
    # region 8: 3 providers but freq 3 -> suppressed
    for prov in "EFG":
        a.add(prest_row(prov=prov, region="8", freq=1, fact=500))
    # non-Fonasa code ignored
    a.add(prest_row(prov="Z", region="13", codigo="X1", pertenencia="Isapre", freq=100, fact=1))
    t = a.price_table()
    rows = {(r[0], r[1]): dict(zip(t["columns"], r)) for r in t["rows"]}
    p13 = rows[("0101001", "13")]
    assert p13["estado"] == "publicable" and p13["precio_mediana"] == 200 and p13["precio_p25"] == 150
    p5 = rows[("0101001", "5")]
    assert p5["estado"] == "concentracion_revision_direccion" and p5["precio_mediana"] is None
    assert p5["facturado"] is None and p5["n_prestadores"] == 2 and p5["share_prestador_mayor_pct"] == 80.0
    assert rows[("0101001", "8")]["estado"] == "suprimido_frecuencia_menor_30"
    assert ("X1", "13") not in rows
    nat = rows[("0101001", "NACIONAL")]
    assert nat["n_prestadores"] == 7 and nat["estado"] == "publicable"
    dumped = json.dumps(t)
    assert '"A"' not in dumped and "SECRET" not in dumped


def test_cross_isapre_index():
    a = agg.PrestacionesAgg()
    a.add(prest_row(isapre="67", prov="A", freq=1, bonif=120))
    a.add(prest_row(isapre="78", prov="A", freq=1, bonif=80))
    a.add(prest_row(isapre="67", prov="B", freq=2, bonif=200))  # single-Isapre cell: excluded
    out = a.cross_isapre()
    assert out["celdas_prestador_prestacion"] == 2 and out["celdas_con_2_o_mas_isapres"] == 1
    s = {x["isapre"]: x for x in out["resumen_por_isapre"]}
    assert s["67"]["indice_bonif_unit_mediana_pct"] == 20.0 and s["78"]["indice_bonif_unit_mediana_pct"] == -20.0


def test_isapre_table_concentration_and_ids():
    a = agg.PrestacionesAgg()
    a.add(prest_row(isapre="67", prov="A", fact=600, bonif=300, copago=300, atencion="Hospitalario"))
    a.add(prest_row(isapre="78", prov="A", fact=200, bonif=200, copago=0))
    a.add(prest_row(isapre="78", prov="B", fact=200, bonif=100, copago=100, tipo_prest="Público"))
    rows = {(x["isapre"], x["tipo_atencion"]): x for x in a.isapre_table()}
    assert rows[("78", "TOTAL")]["pct_bonificado"] == 75.0
    reg = {x["region"]: x for x in a.concentration()["regiones"]}["13"]
    assert reg["hhi"] == 6800 and reg["share_top1_pct"] == 80.0
    assert reg["split_tipo_prestador"]["Público"]["share_facturado_pct"] == 20.0
    prev = agg.PrestacionesAgg(ids_only=True)
    prev.add(prest_row(isapre="67", prov="A"))
    prev.add(prest_row(isapre="67", prov="Q"))
    c = agg.id_consistency(a, prev)
    assert c["trimestre_actual"]["codigos_en_2_o_mas_isapres"] == 1
    assert c["trimestre_actual"]["pct_facturado_de_codigos_en_2_o_mas_isapres"] == 80.0
    assert c["entre_trimestres"]["codigos_en_ambos"] == 1
    assert c["entre_trimestres"]["pct_overlap_sobre_actual"] == 50.0
    assert c["veredicto"]["cross_isapre_valido"] and c["veredicto"]["temporal_valido"]
    assert "SECRET" not in json.dumps(c) and '"A"' not in json.dumps(c)


def test_profile_never_exposes_sensitive_values():
    a = agg.PrestacionesAgg()
    row = prest_row()
    row[29] = "078880554"
    a.add(row)
    prof = json.dumps(a.profile.result())
    assert "078880554" not in prof
    assert "SECRET" not in prof and "P1" not in prof and "0101001" in prof


def test_licencias_rates_min_cell_and_quarter_dates():
    lic = agg.LicenciasAgg()
    for _ in range(8):
        lic.add(lic_row(resol="Autorícese"))
    lic.add(lic_row(resol="Rechácese", aut=0, sub=0))
    lic.add(lic_row(resol="Redúcese", dias=10, aut=5, res="2026t3"))
    for _ in range(3):
        lic.add(lic_row(isapre="99", region="2", diag="F00-F99"))
    out = lic.result()
    t = out["total"]
    assert t["licencias"] == 13 and t["pct_rechazadas"] == pytest.approx(7.69)
    assert t["dias_solicitados"] == 70 and t["dias_autorizados"] == 60
    assert t["pct_resuelta_mismo_trimestre_recepcion"] == pytest.approx(92.31)
    assert "mediana_dias_recepcion_resolucion" not in t and "NO es calculable" in out["nota_fechas"]
    isap = out["breakdowns"]["isapre"]
    assert [r["grupo"] for r in isap["filas"]] == ["81"] and isap["celdas_suprimidas_menor_10"] == 1
    assert isap["licencias_en_celdas_suprimidas"] == 3
    assert set(out["breakdowns"]) == {"isapre", "diagnostico", "actividad_laboral", "region", "tipo_profesional"}
    assert "SECRET" not in json.dumps(out) + json.dumps(lic.profile.result())


def test_licencias_day_dates_give_median():
    lic = agg.LicenciasAgg()
    for d in (2, 4, 9):
        lic.add(lic_row(rec="2026-04-01", res=f"2026-04-{1 + d:02d}"))
    assert lic.result()["total"]["mediana_dias_recepcion_resolucion"] == 4.0


def test_run_end_to_end_local(tmp_path):
    pz = make_zip(tmp_path / "p2.zip", "Prestaciones_Bonificadas_2026t2.txt",
                  [prest_row(prov=p, isapre=i) for p in "ABC" for i in ("67", "78")])
    pz1 = make_zip(tmp_path / "p1.zip", "Prestaciones_Bonificadas_2026t1.txt", [prest_row(prov="A")])
    lz = make_zip(tmp_path / "l.zip", "Licencias_Medicas_2026t2.txt", [lic_row() for _ in range(12)], "utf-8")
    out = tmp_path / "out"
    rec = agg.run("2026t2", "2026t1", out, local={"prest_2026t2": pz, "prest_2026t1": pz1, "lic_2026t2": lz})
    assert [f.get("parse", {}).get("rows_ok") for f in rec["files"]] == [6, 1, None, 12]
    assert all(len(f["sha256"]) == 64 for f in rec["files"] if "error" not in f)
    names = sorted(p.name for p in out.iterdir())
    assert names == ["licencias_2026t2.json", "prestaciones_2026t2_consistencia_ids.json",
                     "prestaciones_2026t2_ejemplo_codigos.json",
                     "prestaciones_2026t2_indice_isapre_mismo_prestador.json",
                     "prestaciones_2026t2_precios_fonasa_region.json", "prestaciones_2026t2_resumen.json",
                     "receipts_2026t2_licencias+prestaciones.json"]
    blob = "".join(p.read_text() for p in out.iterdir())
    assert "SECRET" not in blob
    ids = json.loads((out / "prestaciones_2026t2_consistencia_ids.json").read_text())
    assert ids["entre_trimestres"]["pct_overlap_sobre_actual"] == pytest.approx(33.33)


def test_focus_code_worked_example():
    a = agg.PrestacionesAgg(focus=["0405001"])
    for prov, unit in (("A", 100), ("B", 200), ("C", 300)):
        a.add(prest_row(prov=prov, codigo="0405001", isapre="67", freq=10, fact=unit * 10, bonif=unit * 6,
                        copago=unit * 4))
        a.add(prest_row(prov=prov, codigo="0405001", isapre="78", freq=10, fact=unit * 10, bonif=unit * 4,
                        copago=unit * 6))
    a.add(prest_row(prov="D", codigo="0405001", region="5", freq=50, fact=5000))
    rep = a.focus_report()["0405001"]
    rows = {x["region"]: x for x in rep["filas"]}
    r13 = rows["13"]
    assert r13["estado"] == "publicable" and r13["precio_mediana"] == 200 and r13["pct_bonificado"] == 50.0
    idx = {x["isapre"]: x["indice_bonif_unit_mediana_pct"] for x in r13["indice_isapre_mismo_prestador"]}
    assert idx == {"67": 20.0, "78": -20.0}
    assert rows["5"]["estado"] == "concentracion_revision_direccion" and "precio_mediana" not in rows["5"]
    assert "pct_bonificado" not in rows["5"]
    assert rows["NACIONAL"]["n_prestadores"] == 4


def test_arancel_description_is_verbatim(tmp_path):
    line = "76|202604|202603|ISAPRE|UF|0405001|0|DESCRIPCION X|Prestaci\u00f3n Incluida en el Arancel Fonasa| | | |1.10|0.00|0|0|2026|"
    z = make_zip(tmp_path / "a.zip", "a.txt", [line, line.replace("0405001", "0101001")])
    out = agg.arancel_descriptions(z, {"0405001"}, {})
    assert out == {"0405001": [{"descripcion": "DESCRIPCION X",
                                "clasificacion": "Prestaci\u00f3n Incluida en el Arancel Fonasa", "filas_isapre_plan": 1}]}
