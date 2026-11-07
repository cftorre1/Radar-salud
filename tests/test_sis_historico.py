"""Pruebas con fixtures sintéticas del backfill y censo histórico SIS (sin red)."""
from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hist = _load("sis_historico_backfill")
census = _load("sis_historico_census")
resumen = _load("sis_historico_resumen")

SECRET = "ENC"  # todo identificador cifrado de las fixtures empieza así; nunca debe aparecer en una salida


def row(isapre="67", ben="ENCBEN1", prov="ENCPROV1", region="13", pam="ENCPAM1", compl="0", codigo="0101001",
        pertenencia="FONASA", cobertura="Plan Complementario", atencion="Atención Hospitalaria", freq=1, fact=10000,
        bonif=6000, gpp="X", id_ges="X", tipo_reg="Curativa"):
    f = [""] * 30
    f[0], f[1], f[2], f[3], f[4], f[5], f[6] = isapre, "2026t3", tipo_reg, ben, "Femenino", "36-40", "Cotizante"
    f[7], f[8], f[9], f[10], f[11], f[12], f[13] = prov, region, "No", pam, compl, "ENCBONO", "0"
    f[14], f[15], f[16], f[17], f[18], f[19] = codigo, pertenencia, cobertura, "2026t3", "Privado", atencion
    f[20], f[21], f[22], f[23] = str(freq), str(fact), str(bonif), str(fact - bonif)
    f[24], f[25], f[26], f[27], f[28], f[29] = "No", "Cobertura general", "No aplicable", "No", gpp, id_ges
    return f


def feed(rows, **kw):
    a = hist.QuarterAgg(kw.pop("mle", {"2104129": 442260.0, "0201001": 9440.0, "1202064": 391180.0}), **kw)
    for f in rows:
        a.add(f)
    return a


def assert_no_secret(obj):
    s = json.dumps(obj, ensure_ascii=False)
    assert SECRET not in s, "un identificador cifrado llegó a la salida"


# ---------------------------------------------------------------- GPP
@pytest.mark.parametrize("gpp,expected", [("21T1", (21, "T")), ("7t6", (7, "T")), ("34T8", (34, "T")),
                                          ("1T29", (1, "T")), ("88D1", (88, "D")), ("X", None), ("", None),
                                          ("T21", None), ("21-T1", None), ("2101", None)])
def test_gpp_prefix_parsing(gpp, expected):
    assert hist.parse_gpp(gpp) == expected


def test_ges_reference_covers_90_problems_and_families_partition():
    ref = hist.load_ges_reference()
    assert sorted(ref["names"]) == list(range(1, 91))
    assert set(ref["family"]) == set(range(1, 91))
    assert ref["family"][7] == "cardiometabolico" and ref["family"][34] == "salud_mental"
    assert ref["family"][8] == "cancer" and ref["family"][61] == "respiratorio"


# ---------------------------------------------------------------- GES: mínimo de 10 casos y complementaria
def ges_rows(problem, isapre, region, n_cases, rows_per_case=1):
    out = []
    for c in range(n_cases):
        for _ in range(rows_per_case):
            out.append(row(isapre=isapre, region=region, gpp=f"{problem}T1", id_ges=f"ENCGES{isapre}{region}{c}",
                           cobertura="GES", atencion="Atención Ambulatoria", pam="ENCPH"))
    return out


def test_ges_min_cell_and_complementary_suppression():
    rows = ges_rows(21, "67", "13", 12) + ges_rows(21, "99", "13", 15) + ges_rows(21, "107", "5", 4)
    a = feed(rows)
    t = a.ges_tables(hist.load_ges_reference())
    nat = t["por_problema_nacional"]["filas"]
    assert nat[0]["problema"] == 21 and nat[0]["casos"] == 31 and nat[0]["familia"] == "cardiometabolico"
    isa = {r["isapre"]: r for r in t["por_problema_isapre"]["filas"]}
    # 107 tiene 4 casos (< 10): se suprime, y la complementaria suprime además la menor publicada (67, 12 casos)
    assert "107" not in isa and "67" not in isa and isa["99"]["casos"] == 15
    assert t["por_problema_isapre"]["celdas_suprimidas"] == 2
    for r in t["por_problema_isapre_region"]["filas"]:
        assert r["casos"] >= hist.GES_MIN_CASES
    assert_no_secret(t)


def test_ges_cases_are_distinct_ids_and_counted_per_isapre():
    rows = ges_rows(34, "67", "13", 10, rows_per_case=3)
    t = feed(rows).ges_tables(hist.load_ges_reference())
    r = t["por_problema_nacional"]["filas"][0]
    assert r["casos"] == 10 and r["frecuencia"] == 30


def test_ges_without_gpp_is_reported_apart():
    a = feed([row(cobertura="GES", gpp="X")] * 3)
    t = a.ges_tables(hist.load_ges_reference())
    assert t["totales"]["ges_sin_gpp"]["filas"] == 3 and t["por_problema_nacional"]["filas"] == []


# ---------------------------------------------------------------- índice de precios: regla de divulgación
def price_rows(n_prov, p0, p1, freq=20, code="2104129", region="13", atn="Atención Hospitalaria"):
    prev = [row(prov=f"ENCP{i}", codigo=code, region=region, atencion=atn, freq=freq, fact=p0 * freq,
                bonif=int(p0 * freq * 0.6), pam=f"ENCPAMa{i}") for i in range(n_prov)]
    cur = [row(prov=f"ENCP{i}", codigo=code, region=region, atencion=atn, freq=freq, fact=p1 * freq,
               bonif=int(p1 * freq * 0.6), pam=f"ENCPAMb{i}") for i in range(n_prov)]
    return prev, cur


def rel_table(n_prov, p0=1000, p1=1100, **kw):
    prev, cur = price_rows(n_prov, p0, p1, **kw)
    return hist.price_relatives(feed(prev, warmup=True).price, feed(cur).price)


def test_price_relatives_published_with_three_providers():
    t = rel_table(3)
    cols = t["columns"]
    rows = [dict(zip(cols, r)) for r in t["rows"]]
    nat = next(r for r in rows if r["region"] == "NACIONAL")
    assert nat["estado"] == "publicable" and nat["n_prestadores"] == 3
    assert nat["rel_facturado_media_pond_pct"] == pytest.approx(10.0)
    assert nat["rel_facturado_mediana_pct"] == pytest.approx(10.0)
    agg = {(a["grupo_mle"], a["tipo_atencion"]): a for a in t["agregados"]}
    assert agg[("21", "Hospitalaria")]["laspeyres_facturado_pct"] == pytest.approx(10.0)
    assert_no_secret(t)


def test_price_relatives_two_providers_expose_nothing_recoverable():
    t = rel_table(2)
    cols = t["columns"]
    for r in t["rows"]:
        d = dict(zip(cols, r))
        assert d["estado"] == "suprimido_dos_prestadores" and d["n_prestadores"] == 2
        for c in cols[5:]:
            assert d[c] is None, f"{c} publicado con 2 prestadores"
    assert all(a["estado"] != "publicable" for a in t["agregados"])


def test_price_relatives_single_provider_is_only_a_status():
    t = rel_table(1)
    assert t["rows"] == []
    assert {c["estado"] for c in t["conteo_estados"]} == {"concentracion_un_prestador"}


def test_price_relatives_require_previous_frequency():
    t = rel_table(3, freq=5)  # 15 < 30 de frecuencia anterior
    assert all(r[3].startswith("suprimido_frecuencia") for r in t["rows"]) or t["rows"] == []


def test_price_index_scope_excludes_ges_and_non_fonasa():
    a = feed([row(cobertura="GES"), row(pertenencia="Asegurador"), row(tipo_reg="Examen Medicina Preventiva"),
              row(fact=0), row()])
    assert len(a.price) == 1


# ---------------------------------------------------------------- probe de folios y especialidades
def pam_rows(n_pam, isapre="67", code="2104129", atn="Atención Hospitalaria", n_prov=4, cost=500000, prefix="ENCPAM"):
    out = []
    for i in range(n_pam):
        prov = f"ENCPROV{i % n_prov}"
        out.append(row(isapre=isapre, ben=f"ENCBEN{i}", prov=prov, pam=f"{prefix}{i}", codigo=code, atencion=atn,
                       fact=cost))
        out.append(row(isapre=isapre, ben=f"ENCBEN{i}", prov=prov, pam=f"{prefix}{i}", codigo="0201001", atencion=atn,
                       fact=100000))
    return out


def placeholder_rows(n):
    return [row(pam="ENCZERO", atencion="Atención Ambulatoria", codigo="0101001", ben=f"ENCB{i}") for i in range(n)]


def test_folio_probe_counts_only_and_detects_placeholder():
    rows = pam_rows(20) + placeholder_rows(30)
    a = feed(rows, placeholder_min_rows=25)
    p = a.folio_probe(prev_pam_hashes=set())
    assert p["marcador_sin_pam"]["valores_distintos_detectados"] == 1
    assert p["marcador_sin_pam"]["filas"] == 30
    assert p["pam"]["n"] == 20 and p["pam"]["pct_pam_con_mas_de_un_beneficiario"] == 0
    assert p["pam"]["pct_pam_con_mas_de_un_codigo"] == 100
    assert p["filas_con_pam_real"]["pct_de_hospitalarias_con_pam"] == 100
    assert p["veredicto"]["agrupacion_por_pam_valida"]
    assert p["entre_trimestres"]["pam_del_trimestre_presentes_en_el_anterior"] == 0
    assert_no_secret(p)


def test_folio_probe_cross_quarter_overlap_and_multi_beneficiary():
    prev = feed(pam_rows(10), warmup=True)
    rows = pam_rows(10) + [row(pam="ENCPAM0", ben="ENCOTHER")]
    a = feed(rows)
    p = a.folio_probe(prev.real_pam_hashes())
    assert p["entre_trimestres"]["pam_del_trimestre_presentes_en_el_anterior"] == 10
    assert p["pam"]["pct_pam_con_mas_de_un_beneficiario"] == 10.0


def test_folio_probe_flags_same_value_in_two_isapres():
    a = feed(pam_rows(10, isapre="67") + pam_rows(10, isapre="99"))
    p = a.folio_probe(None)
    assert p["pam"]["pct_valores_folio_en_2_o_mas_isapres"] == 100
    assert not p["veredicto"]["agrupacion_por_pam_valida"]


def spec_table(rows, **kw):
    return feed(rows, **kw).specialty_tables()


def test_specialty_min_cells_and_providers():
    rows = pam_rows(12, code="2104129", n_prov=4) + pam_rows(12, code="1202064", n_prov=2, prefix="ENCQ") \
        + pam_rows(5, code="1802081", n_prov=5, prefix="ENCR")
    t = spec_table(rows)
    by = {(r["especialidad"], r["tipo_atencion"]): r for r in t["filas"]}
    assert by[("traumatologia", "Hospitalaria")]["estado"] == "publicable"
    assert by[("traumatologia", "Hospitalaria")]["episodios"] == 12
    assert by[("traumatologia", "Hospitalaria")]["costo_episodio_mediana"] == 600000
    assert by[("oftalmologia", "Hospitalaria")]["estado"] == "suprimido"      # 2 prestadores
    assert by[("cirugia_digestiva", "Hospitalaria")]["estado"] == "suprimido"  # 5 episodios
    for r in t["filas"]:
        if r["estado"] == "publicable":
            assert r["episodios"] >= hist.SPEC_MIN_EPISODES and r["n_prestadores"] >= hist.SPEC_MIN_PROVIDERS
    assert t["experimental"] is True
    assert_no_secret(t)


def test_specialty_concentration_over_80_pct_is_suppressed():
    rows = pam_rows(9, n_prov=1) + pam_rows(1, prefix="ENCX1", n_prov=1) + pam_rows(1, prefix="ENCX2", n_prov=1)
    for i, f in enumerate(rows[-4:]):
        f[7] = f"ENCOTHERPROV{i // 2}"
    t = spec_table(rows)
    row_ = next(r for r in t["filas"] if r["especialidad"] == "traumatologia" and r["tipo_atencion"] == "Hospitalaria")
    assert row_["estado"] == "suprimido"


def test_specialty_complementary_hides_lone_suppressed_tipo():
    rows = pam_rows(15, n_prov=4) + pam_rows(3, n_prov=3, atn="Atención Ambulatoria", prefix="ENCAMB")
    t = spec_table(rows)
    by = {(r["especialidad"], r["tipo_atencion"]): r["estado"] for r in t["filas"]}
    assert by[("traumatologia", "Ambulatoria")] == "suprimido"
    # Hospitalaria + Ambulatoria = TOTAL: con un único oculto se despejaría, así que se oculta otra celda
    assert "suprimido" in (by[("traumatologia", "Hospitalaria")], by[("traumatologia", "TOTAL")])


def test_specialty_fallback_dia_cama_and_multiespecialidad():
    rows = []
    for i in range(12):
        rows.append(row(pam=f"ENCM{i}", prov=f"ENCPV{i % 3}", codigo="0201001", ben=f"ENCB{i}"))
    for i in range(12):
        p = f"ENCMS{i}"
        rows.append(row(pam=p, prov=f"ENCPV{i % 3}", codigo="2104129", ben=f"ENCC{i}"))
        rows.append(row(pam=p, prov=f"ENCPV{i % 3}", codigo="1202064", ben=f"ENCC{i}"))
    t = spec_table(rows)
    specs = {r["especialidad"] for r in t["filas"] if r["estado"] == "publicable"}
    assert "medicina_interna" in specs and "multiespecialidad" in specs


# ---------------------------------------------------------------- esquema
def test_schema_unknown_values_skip_quarter():
    a = feed([row(atencion="Z")] * 10)
    s = a.schema_check({"lines_read": 10, "rows_malformed": 0})
    assert not s["ok"] and any("tipo_atencion" in x for x in s["razones"])


def test_schema_numeric_codes_from_compendio_are_mapped():
    a = feed([row(atencion="2", pertenencia="1", cobertura="4", tipo_reg="1")] * 5)
    assert a.schema_check({"lines_read": 5})["ok"] and len(a.price) == 1


def make_zip(path: Path, rows, n=None) -> Path:
    lines = ["|".join(f) + "|" for f in rows]
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("p.txt", ("\r\n".join(lines) + "\r\n").encode("latin-1"))
    return path


def test_run_block_end_to_end_writes_no_encrypted_ids(tmp_path):
    prev, cur = price_rows(4, 1000, 1200, code="1202064")  # grupo 12, ausente de pam_rows
    z1 = make_zip(tmp_path / "a.zip", prev + pam_rows(12) + ges_rows(7, "67", "13", 11))
    z2 = make_zip(tmp_path / "b.zip", cur + pam_rows(12) + ges_rows(7, "67", "13", 11))
    bad = make_zip(tmp_path / "c.zip", [r[:28] for r in cur])
    out = tmp_path / "out"
    hist.run_block(["2026t2", "2026t3", "2026t4"], out, local={"2026t1": z1, "2026t2": z1, "2026t3": z2, "2026t4": bad})
    files = sorted(p.name for p in out.rglob("*.json"))
    assert "indice_precios_2026t2_2026t3.json" in files and "ges_gpp_2026t3.json" in files
    rec4 = json.loads((out / "2026t4" / "receipts_2026t4.json").read_text())
    assert rec4["estado"] == "omitido" and rec4["razon_omision"]
    assert not (out / "2026t4" / "ges_gpp_2026t4.json").exists()
    for p in out.rglob("*.json"):
        assert SECRET not in p.read_text(encoding="utf-8"), p.name
    ix = json.loads((out / "2026t3" / "indice_precios_2026t2_2026t3.json").read_text())
    agg = {(a["grupo_mle"], a["tipo_atencion"]): a for a in ix["agregados"]}
    assert agg[("12", "Hospitalaria")]["laspeyres_facturado_pct"] == pytest.approx(20.0)
    # reanudable: un segundo llamado no reprocesa nada
    assert hist.run_block(["2026t2", "2026t3"], out, local={}) == []
    res = resumen.build(out)
    assert res["trimestres"]["2026t4"]["estado"] == "omitido"
    assert res["indice_encadenado"]["12|Hospitalaria"]["laspeyres_facturado_recortado_pct"]["serie"]["2026t3"] == 120.0
    assert SECRET not in json.dumps(res)


def test_census_fingerprint_and_no_values_for_unknown_layout(tmp_path):
    z = make_zip(tmp_path / "p.zip", [row(), row()])
    r = census.census_zip(z, "Prestaciones Bonificadas")
    assert r["filas"] == 2 and r["n_campos_modal"] == 30 and r["layout_2026_compatible_por_n_campos"]
    assert "tipo_atencion" in r["vocabularios"] and len(r["huella_esquema"]) == 16
    z2 = make_zip(tmp_path / "q.zip", [row()[:25]] * 12)
    r2 = census.census_zip(z2, "Prestaciones Bonificadas")
    assert "vocabularios" not in r2 and not r2["layout_2026_compatible_por_n_campos"]
    assert r2["huella_esquema"] != r["huella_esquema"]
    assert SECRET not in json.dumps(r) and SECRET not in json.dumps(r2)
