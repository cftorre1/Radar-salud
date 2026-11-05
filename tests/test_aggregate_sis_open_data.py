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
    """Dirección 5-nov-2026: price with >= 2 providers and >= 30 frecuencia (p25-p75 only with >= 3); exactly 1
    provider: no price, only a concentration flag; every provider counts nationally; top share always shown."""
    a = agg.PrestacionesAgg()
    # region 13: 3 providers, total freq 30 -> median and p25-p75
    for prov, unit in (("A", 100), ("B", 200), ("C", 300)):
        a.add(prest_row(prov=prov, freq=10, fact=unit * 10))
    # region 5: 2 providers, freq 50 -> median only
    a.add(prest_row(prov="A", region="5", freq=40, fact=4000))
    a.add(prest_row(prov="D", region="5", freq=10, fact=5000))
    # region 6: 1 provider, large frecuencia -> concentration flag, no price, no facturado
    a.add(prest_row(prov="H", region="6", freq=500, fact=50000))
    # region 8: 3 providers but freq 3 -> suppressed
    for prov in "EFG":
        a.add(prest_row(prov=prov, region="8", freq=1, fact=500))
    # non-Fonasa code ignored
    a.add(prest_row(prov="Z", region="13", codigo="X1", pertenencia="Isapre", freq=100, fact=1))
    t = a.price_table()
    rows = {(r[0], r[1]): dict(zip(t["columns"], r)) for r in t["rows"]}
    p13 = rows[("0101001", "13")]
    assert p13["estado"] == "publicable" and p13["precio_mediana"] == 200 and p13["precio_p25"] == 150
    assert p13["precio_p75"] == 250 and p13["share_prestador_mayor_pct"] == pytest.approx(33.33)
    p5 = rows[("0101001", "5")]
    assert p5["estado"] == "publicable" and p5["precio_mediana"] == 300  # (100 + 500) / 2
    assert p5["precio_p25"] is None and p5["precio_p75"] is None and p5["n_prestadores"] == 2
    assert p5["share_prestador_mayor_pct"] == 80.0
    p6 = rows[("0101001", "6")]
    assert p6["estado"] == "concentracion_un_prestador" and p6["n_prestadores"] == 1
    assert all(p6[k] is None for k in ("precio_mediana", "precio_p25", "precio_p75", "facturado", "pct_bonificado"))
    assert p6["frecuencia"] == 500 and p6["share_prestador_mayor_pct"] == 100.0
    assert rows[("0101001", "8")]["estado"] == "suprimido_frecuencia_menor_30"
    assert rows[("0101001", "8")]["precio_mediana"] is None
    assert ("X1", "13") not in rows
    nat = rows[("0101001", "NACIONAL")]
    assert nat["n_prestadores"] == 8 and nat["estado"] == "publicable"  # H (alone in region 6) counts nationally
    assert nat["frecuencia"] == 30 + 50 + 500 + 3
    est = {(e["estado"], e["nacional"]): e for e in t["conteo_estados"]}
    assert est[("concentracion_un_prestador", False)]["frecuencia"] == 500
    dumped = json.dumps(t)
    assert '"A"' not in dumped and "SECRET" not in dumped and '"H"' not in dumped


def test_top_codes_rank_by_national_frecuencia():
    a = agg.PrestacionesAgg()
    a.add(prest_row(prov="A", codigo="0101001", freq=5, fact=500, bonif=300, copago=200))
    a.add(prest_row(prov="B", codigo="0301045", region="5", freq=9, fact=900, bonif=450, copago=450))
    a.add(prest_row(prov="C", codigo="0301045", region="6", freq=2, fact=200, bonif=100, copago=100))
    top = a.top_codes(2)
    assert [c["codigo_prestacion"] for c in top] == ["0301045", "0101001"]
    assert top[0]["frecuencia"] == 11 and top[0]["pct_bonificado"] == 50.0 and top[1]["pct_copago"] == 40.0


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
    for _ in range(10):
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


def test_run_end_to_end_local_both_quarters(tmp_path):
    pz = make_zip(tmp_path / "p2.zip", "Prestaciones_Bonificadas_2026t2.txt",
                  [prest_row(prov=p, isapre=i) for p in "ABC" for i in ("67", "78")])
    pz1 = make_zip(tmp_path / "p1.zip", "Prestaciones_Bonificadas_2026t1.txt", [prest_row(prov="A")])
    lz = make_zip(tmp_path / "l.zip", "Licencias_Medicas_2026t2.txt", [lic_row() for _ in range(12)], "utf-8")
    lz1 = make_zip(tmp_path / "l1.zip", "Licencias_Medicas_2026t1.txt", [lic_row() for _ in range(11)], "utf-8")
    line = "76|202604|202603|ISAPRE|UF|0101001|0|CONSULTA X|Prestaci\u00f3n Incluida en el Arancel Fonasa| | | |1|0|0|0|2026|"
    az = make_zip(tmp_path / "a.zip", "a.txt", [line])
    out = tmp_path / "out"
    recs = agg.run("2026t2", "2026t1", out, local={"prest_2026t2": pz, "prest_2026t1": pz1, "lic_2026t2": lz,
                                                     "lic_2026t1": lz1, "arancel_2026": az})
    assert list(recs) == ["2026t1", "2026t2"]
    assert [f.get("parse", {}).get("rows_ok") for f in recs["2026t2"]["files"]] == [6, None, 12]
    assert all(len(f["sha256"]) == 64 for f in recs["2026t2"]["files"])
    assert recs["2026t2"]["script_version"] == agg.SCRIPT_VERSION
    names = sorted(p.name for p in (out / "2026t2").iterdir())
    assert names == ["licencias_2026t2.json", "prestaciones_2026t2_consistencia_ids.json",
                     "prestaciones_2026t2_indice_isapre_mismo_prestador.json",
                     "prestaciones_2026t2_precios_fonasa_region.json", "prestaciones_2026t2_resumen.json",
                     "prestaciones_2026t2_top_codigos.json", "receipts_2026t2.json"]
    assert "prestaciones_2026t1_consistencia_ids.json" not in [p.name for p in (out / "2026t1").iterdir()]
    blob = "".join(p.read_text() for q in ("2026t1", "2026t2") for p in (out / q).iterdir())
    assert "SECRET" not in blob
    ids = json.loads((out / "2026t2" / "prestaciones_2026t2_consistencia_ids.json").read_text())
    assert ids["entre_trimestres"]["pct_overlap_sobre_actual"] == pytest.approx(33.33)
    top = json.loads((out / "2026t2" / "prestaciones_2026t2_top_codigos.json").read_text())
    assert top["codigos"][0]["descripcion_arancel_isapre"][0]["descripcion"] == "CONSULTA X"
    lic = json.loads((out / "2026t2" / "licencias_2026t2.json").read_text())
    assert lic["sha256_archivo"] == recs["2026t2"]["files"][2]["sha256"] and lic["filas"] == 12


def test_quarter_discovery_never_guesses():
    links = ["https://datos.superdesalud.gob.cl/archivos/Prestaciones%20Bonificadas/2026/Prestaciones_Bonificadas_2026t1.zip",
             "https://datos.superdesalud.gob.cl/archivos/Prestaciones%20Bonificadas/2026/Prestaciones_Bonificadas_2026t2.zip",
             "https://datos.superdesalud.gob.cl/archivos/Licencias%20Medicas/2026/Licencias_Medicas_2026t3.zip"]
    assert agg.latest_quarter(links) == "2026t2"
    assert agg.latest_quarter([]) is None
    assert agg.previous_quarter("2026t1") == "2025t4" and agg.previous_quarter("2026t3") == "2026t2"
    assert agg.discover("Prestaciones Bonificadas", "2026t2", links) == links[1]


def test_download_cap_is_one_gib():
    assert agg.MAX_FILE_BYTES == 1 << 30 and set(agg.MAX_BYTES.values()) == {1 << 30}


def test_profile_lists_only_values_seen_ten_times():
    p = agg.Profiler(["a"], set())
    for v in ["x"] * 10 + ["rare"] * 3:
        p.add([v])
    assert p.result()[0]["top_values"] == [["x", 10]]


def test_licencias_isapre_by_diagnosis_cross_has_min_cell():
    lic = agg.LicenciasAgg()
    for _ in range(10):
        lic.add(lic_row(isapre="81", diag="F00-F99", resol="Rechácese", aut=0))
    for _ in range(4):
        lic.add(lic_row(isapre="99", diag="F00-F99"))
    cr = lic.result()["cruces"]["isapre_x_diagnostico"]
    assert [(r["isapre"], r["diagnostico"], r["pct_rechazadas"]) for r in cr["filas"]] == [("81", "F00-F99", 100.0)]
    assert cr["celdas_suprimidas_menor_10"] == 1 and cr["licencias_en_celdas_suprimidas"] == 4


def test_arancel_description_is_verbatim(tmp_path):
    line = "76|202604|202603|ISAPRE|UF|0405001|0|DESCRIPCION X|Prestaci\u00f3n Incluida en el Arancel Fonasa| | | |1.10|0.00|0|0|2026|"
    z = make_zip(tmp_path / "a.zip", "a.txt", [line, line.replace("0405001", "0101001")])
    out = agg.arancel_descriptions(z, {"0405001"}, {})
    assert out == {"0405001": [{"descripcion": "DESCRIPCION X",
                                "clasificacion": "Prestaci\u00f3n Incluida en el Arancel Fonasa", "filas_isapre_plan": 1}]}
