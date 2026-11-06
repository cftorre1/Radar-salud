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
    """Dirección 5-nov-2026: price with >= 2 providers and >= 30 frecuencia (p25-p75 only with >= 4); exactly 1
    provider: no price, only a concentration flag; every provider counts nationally; top share always shown."""
    a = agg.PrestacionesAgg()
    # region 13: 3 providers, total freq 30 -> median only
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
    # 3 providers: median only (p25, median and p75 would give away all three unit prices)
    assert p13["estado"] == "publicable" and p13["precio_mediana"] == 200 and p13["precio_p25"] is None
    assert p13["precio_p75"] is None and p13["share_prestador_mayor_pct"] == pytest.approx(33.33)
    assert p13["facturado"] == 6000
    p5 = rows[("0101001", "5")]
    assert p5["estado"] == "publicable" and p5["precio_mediana"] == 300  # (100 + 500) / 2
    assert p5["precio_p25"] is None and p5["precio_p75"] is None and p5["n_prestadores"] == 2
    assert p5["share_prestador_mayor_pct"] == "60-80" and p5["facturado"] is None and p5["pct_bonificado"] is None
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


def test_p25_p75_only_with_four_or_more_providers():
    """With 3 providers, p25/median/p75 (linear quantiles) solve all three unit prices: a = 2·p25 − m, c = 2·p75 − m.
    So the range needs >= 4 providers; with 4 the published p25/median/p75 fit more than one set of prices."""
    def row(units):
        a = agg.PrestacionesAgg()
        for i, u in enumerate(units):
            a.add(prest_row(prov=f"P{i}", freq=10, fact=u * 10))
        t = a.price_table()
        return {r[1]: dict(zip(t["columns"], r)) for r in t["rows"]}["13"]
    three = row([100, 200, 300])
    assert three["precio_mediana"] == 200 and three["precio_p25"] is None and three["precio_p75"] is None
    x, y = row([100, 175, 225, 300]), row([97, 176, 224, 303])
    for r in (x, y):
        assert r["precio_p25"] is not None and r["precio_p75"] is not None
    # different individual prices, identical published quartiles → not recoverable
    assert (x["precio_p25"], x["precio_mediana"], x["precio_p75"]) == (y["precio_p25"], y["precio_mediana"], y["precio_p75"])
    assert agg.IQR_MIN_PROVIDERS == 4


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
    a.add(prest_row(isapre="67", prov="A", freq=10, bonif=1200))
    a.add(prest_row(isapre="78", prov="A", freq=10, bonif=800))
    a.add(prest_row(isapre="67", prov="B", freq=20, bonif=2000))  # single-Isapre cell: excluded
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
    # 99 (3) is under 10; 81 (10) is then suppressed too, or total − 81 would reveal 99's three licences
    assert isap["filas"] == [] and isap["celdas_suprimidas"] == 2 and isap["licencias_en_celdas_suprimidas"] == 13
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
    names = sorted(p.name for p in (out / "2026t2").iterdir() if "cambio_mismo_prestador" not in p.name)
    assert (out / "2026t2" / "prestaciones_2026t2_cambio_mismo_prestador.json").exists()
    assert names == ["licencias_2026t2.json", "prestaciones_2026t2_consistencia_ids.json",
                     "prestaciones_2026t2_indice_isapre_mismo_prestador.json",
                     "prestaciones_2026t2_precios_fonasa_region.json", "prestaciones_2026t2_precios_tipo_prestador.json",
                     "prestaciones_2026t2_resumen.json", "prestaciones_2026t2_top_codigos.json", "receipts_2026t2.json"]
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
    for isapre, n in (("81", 30), ("99", 25)):
        for _ in range(n):
            lic.add(lic_row(isapre=isapre, diag="J00-J99"))
    for _ in range(10):
        lic.add(lic_row(isapre="81", diag="F00-F99", resol="Rechácese", aut=0))
    for _ in range(12):
        lic.add(lic_row(isapre="99", diag="F00-F99"))
    lic.add(lic_row(isapre="99", diag="M00-M99"))
    cr = lic.result()["cruces"]["isapre_x_diagnostico"]
    shown = {(r["isapre"], r["diagnostico"]) for r in cr["filas"]}
    # 99×M (1) is under 10 → within Isapre 99 the next-smallest cell (99×F, 12) is also suppressed; then within
    # diagnosis F the remainder 12 ≥ 10, so 81×F stays; every row/column remainder is 0 or ≥ 10.
    assert shown == {("81", "J00-J99"), ("99", "J00-J99"), ("81", "F00-F99")}
    assert cr["celdas_suprimidas"] == 2 and cr["licencias_en_celdas_suprimidas"] == 13
    assert next(r for r in cr["filas"] if r["diagnostico"] == "F00-F99")["rechazadas"] == 10


def test_complementary_suppression_never_leaves_a_remainder_under_10():
    """Review of PR #152: one suppressed actividad with 1 licence could be recovered as total − published cells."""
    lic = agg.LicenciasAgg()
    for act, n in (("Servicios", 40), ("Comercio", 15), ("Mineria", 11), ("Agricultura", 1)):
        for _ in range(n):
            lic.add(lic_row(act=act, dias=7, aut=3, sub=12345))
    out = lic.result()
    b = out["breakdowns"]["actividad_laboral"]
    assert [r["grupo"] for r in b["filas"]] == ["Servicios", "Comercio"]  # Mineria (11) suppressed with Agricultura (1)
    assert b["licencias_en_celdas_suprimidas"] == 12
    tot = out["total"]
    for key in ("licencias", "dias_solicitados", "dias_autorizados", "subsidio_total"):
        remainder = tot[key] - sum(r[key] for r in b["filas"])
        # what subtraction recovers always covers ≥ 10 licences (here 12), never one licence
        assert remainder == {"licencias": 12, "dias_solicitados": 84, "dias_autorizados": 36, "subsidio_total": 12 * 12345}[key]
    # the rule on any synthetic table: the suppressed total of every group is 0 or ≥ 10
    import random
    rng = random.Random(7)
    for _ in range(200):
        cells = {f"c{i}": rng.randint(1, 40) for i in range(rng.randint(1, 8))}
        sup = agg.complementary_suppression(cells, [list(cells)])
        hidden = sum(cells[k] for k in sup)
        assert hidden == 0 or hidden >= 10 or len(sup) == len(cells)
        assert all(k in sup for k, n in cells.items() if n < 10)
    assert agg.suppressed_count(4) == {"licencias_en_celdas_suprimidas": None, "licencias_en_celdas_suprimidas_texto": "<10"}


def test_two_provider_cell_never_reveals_each_provider_price():
    """Review of PR #152: with n = 2, median + facturado + frecuencia + exact top share solve both unit prices.
    Now facturado, % bonificado and % copago are null and the share is a band: two different pairs of providers
    with the same median, frecuencia and band publish identical rows, so no combination recovers the prices."""
    def cell(p1, f1, p2, f2):
        a = agg.PrestacionesAgg()
        a.add(prest_row(prov="A", region="3", freq=f1, fact=p1 * f1, bonif=p1 * f1 // 2, copago=p1 * f1 // 2))
        a.add(prest_row(prov="B", region="3", freq=f2, fact=p2 * f2, bonif=p2 * f2 // 2, copago=p2 * f2 // 2))
        t = a.price_table()
        return {r[1]: dict(zip(t["columns"], r)) for r in t["rows"]}
    x = cell(59000, 20, 68000, 13)   # median 63.500, freq 33, top share 60,6 % → band 60-80
    y = cell(55000, 25, 72000, 8)    # median 63.500, freq 33, top share 75,8 % → band 60-80
    for cells in (x, y):
        r3 = cells["3"]
        assert r3["n_prestadores"] == 2 and r3["precio_mediana"] == 63500 and r3["share_prestador_mayor_pct"] == "60-80"
        assert r3["facturado"] is None and r3["pct_bonificado"] is None and r3["pct_copago"] is None
        assert r3["precio_p25"] is None and r3["precio_p75"] is None
    assert x["3"] == y["3"]  # same published row, different individual prices: not recoverable
    # the national cell has the same 2 providers here, so it obeys the same rule
    assert x["NACIONAL"]["facturado"] is None and x["NACIONAL"]["share_prestador_mayor_pct"] == "60-80"
    assert [agg.share_band(s) for s in (50, 60, 60.1, 80, 80.1)] == ["50-60", "50-60", "60-80", "60-80", ">80"]


def test_two_provider_rule_leaves_system_totals_untouched():
    a = agg.PrestacionesAgg()
    a.add(prest_row(isapre="67", prov="A", region="3", freq=20, fact=2000, bonif=1500, copago=500))
    a.add(prest_row(isapre="67", prov="B", region="3", freq=20, fact=3000, bonif=1500, copago=1500))
    tot = {(r["isapre"], r["tipo_atencion"]): r for r in a.isapre_table()}[("67", "TOTAL")]
    assert tot["facturado"] == 5000 and tot["pct_bonificado"] == 60.0
    assert {r["region"]: r for r in a.concentration()["regiones"]}["NACIONAL"]["facturado"] == 5000
    assert a.top_codes(1)[0]["facturado"] == 5000


def test_cross_index_needs_ten_frecuencia_per_isapre():
    a = agg.PrestacionesAgg()
    a.add(prest_row(isapre="67", prov="A", freq=10, bonif=1200))
    a.add(prest_row(isapre="78", prov="A", freq=9, bonif=800))
    assert a.cross_isapre()["celdas_con_2_o_mas_isapres"] == 0
    a.add(prest_row(isapre="78", prov="A", freq=1, bonif=100))
    assert a.cross_isapre()["celdas_con_2_o_mas_isapres"] == 1


def test_arancel_description_is_verbatim(tmp_path):
    line = "76|202604|202603|ISAPRE|UF|0405001|0|DESCRIPCION X|Prestaci\u00f3n Incluida en el Arancel Fonasa| | | |1.10|0.00|0|0|2026|"
    z = make_zip(tmp_path / "a.zip", "a.txt", [line, line.replace("0405001", "0101001")])
    out = agg.arancel_descriptions(z, {"0405001"}, {})
    assert out == {"0405001": [{"descripcion": "DESCRIPCION X",
                                "clasificacion": "Prestaci\u00f3n Incluida en el Arancel Fonasa", "filas_isapre_plan": 1}]}


def test_concentration_top3_top10_top50_and_fonasa_totals():
    a = agg.PrestacionesAgg()
    for i, f in enumerate([50, 20, 10, 5, 5, 5, 5]):
        a.add(prest_row(prov=f"P{i}", fact=f, bonif=0, copago=f))
    reg = {x["region"]: x for x in a.concentration()["regiones"]}["13"]
    assert (reg["share_top1_pct"], reg["share_top3_pct"], reg["share_top5_pct"]) == (50.0, 80.0, 90.0)
    assert reg["share_top10_pct"] == reg["share_top50_pct"] == 100.0
    assert a.fonasa_totals() == {"facturado_fonasa": 100, "frecuencia_fonasa": 7}


def test_public_private_prices_follow_the_disclosure_rule():
    a = agg.PrestacionesAgg()
    for prov, unit in (("A", 100), ("B", 300)):
        a.add(prest_row(prov=prov, freq=20, fact=unit * 20, tipo_prest="Privado"))
    a.add(prest_row(prov="C", freq=50, fact=50 * 80, tipo_prest="Público"))
    t = a.tipo_table()
    rows = {(r[1], r[2]): dict(zip(t["columns"], r)) for r in t["rows"]}
    assert rows[("13", "Privado")]["precio_mediana"] == 200 and rows[("13", "Privado")]["n_prestadores"] == 2
    assert rows[("13", "Público")]["precio_mediana"] is None  # 1 provider: no price
    assert '"C"' not in json.dumps(t)


def test_same_provider_price_change_uses_only_providers_in_both_quarters():
    prev, cur = agg.PrestacionesAgg(), agg.PrestacionesAgg()
    for i, (p0, p1) in enumerate([(100, 110), (200, 220), (300, 330), (400, 440)]):
        prev.add(prest_row(prov=f"P{i}", freq=10, fact=p0 * 10))
        cur.add(prest_row(prov=f"P{i}", freq=10, fact=p1 * 10))
    cur.add(prest_row(prov="NEW", freq=100, fact=100 * 10))  # only in the current quarter: ignored
    t = agg.price_change(cur, prev.price)
    rows = {r[1]: dict(zip(t["columns"], r)) for r in t["rows"]}
    assert rows["13"]["n_prestadores_ambos"] == 4 and rows["13"]["indice_laspeyres_pct"] == 10.0
    assert rows["13"]["mediana_relativos_pct"] == 10.0 and rows["NACIONAL"]["indice_laspeyres_pct"] == 10.0
    prev3 = agg.PrestacionesAgg()
    for i in range(3):
        prev3.add(prest_row(prov=f"P{i}", freq=20, fact=2000))
    assert agg.price_change(cur, prev3.price)["rows"] == []  # 3 matched providers: not published
