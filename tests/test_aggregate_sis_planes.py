"""Synthetic-fixture tests for scripts/aggregate_sis_planes.py (no network). All rows are invented."""
from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "aggregate_sis_planes", Path(__file__).resolve().parents[1] / "scripts" / "aggregate_sis_planes.py")
agg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agg)

TYPES = {"67": "open", "99": "open", "63": "closed"}


def plan_row(isapre="67", pid="SECRETPLAN1", comer="Comer.", tipo="Individual", mod="Libre Elección", mprecio="UF",
             precio="2.50", cot=10, cargas=5, amb="70", hosp="90", month="202608"):
    f = [" "] * 38
    f[0], f[1], f[2], f[3], f[4], f[5] = month, isapre, pid, "NOMBRE " + pid, "LINEASECRETA", "202001"
    f[8], f[10], f[11], f[14], f[15], f[16], f[23] = comer, tipo, mod, mprecio, precio, "T", precio
    f[26], f[27], f[31], f[32] = amb, hosp, str(cot), str(cargas)
    return f


def cob_row(isapre="67", pid="SECRETPLAN1", code="0101001", amb="70", hosp="0.00", tope="Con Tope", month="202608"):
    return [isapre, month, pid, amb, tope, "0.00", "0.56", "0.00", hosp, "Sin Tope", "0.00", "0.00", "0.00", code, "0", "0"]


def make_zip(path: Path, rows: list) -> Path:
    lines = ["|".join(x) + "|" for x in rows]
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(path.stem + ".txt", ("\r\n".join(lines) + "\r\n").encode("latin-1"))
    return path


def test_weighted_quantile_and_min_cells():
    assert agg.wquantile([(1.0, 1), (2.0, 1), (3.0, 10)], 0.5) == 3.0
    assert agg.wquantile([(1.0, 10), (2.0, 1), (3.0, 1)], 0.5) == 1.0
    d = agg.dist([1.0, 2.0, 3.0, 4.0], [10, 10, 10, 10])
    assert d["mediana"] is None and d["suprimido"] == "<5 planes" and d["mediana_pond"] is None
    d = agg.dist([1.0, 2.0, 3.0, 4.0, 5.0], [1, 1, 1, 1, 1])
    assert d["mediana"] == 3.0 and d["mediana_pond"] is None  # < 30 cotizantes of weight
    d = agg.dist([1.0, 2.0, 3.0, 4.0, 5.0], [10, 10, 10, 10, 100])
    assert d["mediana_pond"] == 5.0
    assert not {"media", "media_pond", "n", "peso", "n_con_peso"} & set(d)  # nothing additive in a distribution


def test_planes_sets_and_groups():
    a = agg.PlanesAgg(TYPES)
    for i in range(6):
        a.add(plan_row(pid=f"V{i}", comer="Comer.", precio=f"{2 + i / 10:.2f}", cot=i))
    for i in range(6):
        a.add(plan_row(pid=f"N{i}", comer="No Comer.", precio=f"{1 + i / 10:.2f}", cot=100, mod="Prestador Preferente"))
    a.add(plan_row(pid="S7", mprecio="7%", precio="0", cot=50, comer="No Comer."))
    for i in range(6):
        a.add(plan_row(isapre="99", pid=f"V{i}", cot=3))  # same plan ids, another Isapre: different plans
        a.add(plan_row(isapre="63", pid=f"C{i}", comer="No Comer.", cot=40))
    a.add(plan_row(isapre="99", pid="N0", comer="No Comer.", cot=7))
    a.add(plan_row(isapre="99", pid="N1", comer="No Comer.", cot=8))
    a.add(plan_row(isapre="99", pid="N2", comer="No Comer.", cot=9, mod="Prestador Preferente"))
    a.add(plan_row(pid="V0", cot=999))  # duplicate (isapre, plan): ignored and counted
    res = a.result()
    g = res["grupos"]
    assert res["filas_duplicadas_isapre_plan"] == 1 and res["planes_unicos"] == 28
    o = g["isapre:67"]
    assert o["todos"]["cotizantes"] == sum(range(6)) + 600 + 50 and o["todos"]["cargas"] == 13 * 5
    assert o["todos"]["precio_uf"]["mediana"] == 1.75  # 12 priced plans; the 7% plan stays out
    # Only two open Isapres here: 99 is hidden below its total, so 67 is hidden with it (else open − 67 = 99).
    assert o["venta"]["planes"] is None and o["venta"]["suprimido"] == "complementaria"
    assert g["abiertas"]["todos"]["planes"] == 22 and g["cerradas"]["todos"]["cotizantes"] == 240
    assert g["sistema"]["todos"]["planes"] == 28
    # Isapre 99 has 3 plans not on sale: that cell is hidden, and so is every cell that would give it back by subtraction.
    assert g["isapre:99"]["no_venta"]["planes"] is None and g["isapre:99"]["no_venta"]["suprimido"] == "<5 planes"
    assert g["isapre:99"]["todos"]["planes"] == 9  # reconciled with the cartera workbook: never hidden
    sup = res["supresion"]
    assert sup["primarias"] >= 1 and sup["complementarias"] >= 1 and sup["verificacion"] == "sin celdas recuperables"
    assert agg.disclosure.check(res) == []
    assert g["cerradas"]["todos"]["precio_uf"]["mediana"] is None  # no medians for the closed group


def test_coverage_basket_joins_plans_and_takes_highest_record():
    a = agg.PlanesAgg(TYPES)
    rows = []
    for i in range(5):
        a.add(plan_row(pid=f"P{i}", cot=10 * (i + 1)))
        for code in agg.CANASTA["amb"]:
            rows.append(cob_row(pid=f"P{i}", code=code, amb=str(60 + i)))
        for code in [*agg.CANASTA["hosp"], *agg.DETALLE["hosp"]]:
            rows.append(cob_row(pid=f"P{i}", code=code, amb="0", hosp=str(80 + i)))
    rows.append(cob_row(pid="P0", code="0101001", amb="95"))  # second record for the same plan x code: highest kept
    rows.append(cob_row(pid="GHOST", code="0101001", amb="10"))  # plan absent from Planes: never joined
    c = agg.CoberturaAgg(a.plans, TYPES)
    for f in rows:
        c.add(f)
    res = c.result()
    o = res["grupos"]["isapre:67"]
    assert "planes" not in o and res["planes_sin_fila_en_planes_de_salud"] == 1 and res["planes_canasta_unidos"] == 5
    assert o["codigos"]["0101001"]["mediana"] == 63.0 and res["registros_multiples_por_plan_codigo"] == {"0101001": 1}
    assert o["codigos"]["0201001"]["mediana"] == 82.0 and o["canasta"]["hosp"]["mediana"] == 82.0
    assert "0201001" not in agg.CANASTA["hosp"] and set(o["codigos"]) == set(agg.CANASTA_CODES)
    assert o["canasta"]["amb"]["mediana"] == 63.0 and "n" not in o["canasta"]["amb"]


def test_coverage_counts_only_individual_plans_on_sale():
    a = agg.PlanesAgg(TYPES)
    rows = []
    for i in range(8):
        comer, tipo = ("Comer.", "Individual") if i < 5 else ("No Comer.", "Individual") if i < 7 else ("Comer.", "Grupal")
        a.add(plan_row(pid=f"P{i}", comer=comer, tipo=tipo))
        rows += [cob_row(pid=f"P{i}", code=code, amb=str(50 if i < 5 else 99)) for code in agg.CANASTA["amb"]]
    c = agg.CoberturaAgg(a.plans, TYPES)
    for f in rows:
        c.add(f)
    res = c.result()
    assert res["planes_canasta_unidos"] == 5 and res["grupos"]["isapre:67"]["canasta"]["amb"]["p75"] == 50.0


def leaky_table():
    """Three closed Isapres, one with a single plan on sale (the case of the review of PR #167)."""
    a = agg.PlanesAgg({"67": "open", "99": "open", "63": "closed", "65": "closed", "94": "closed"})
    for isa, n_sale, n_old in (("67", 30, 40), ("99", 20, 25), ("63", 8, 12), ("65", 6, 9), ("94", 1, 4)):
        for i in range(n_sale):
            a.add(plan_row(isapre=isa, pid=f"S{i}", comer="Comer.", cot=10 + i,
                           mod="Prestador Preferente" if i % 3 else "Libre Elección"))
        for i in range(n_old):
            a.add(plan_row(isapre=isa, pid=f"N{i}", comer="No Comer.", cot=100 + i, mod="Libre Elección"))
    return a.result()


def test_subtraction_cannot_recover_a_hidden_cell():
    res = leaky_table()
    g = res["grupos"]
    cdn = g["isapre:94"]
    assert cdn["venta"]["planes"] is None and cdn["venta"]["cotizantes"] is None
    assert all(x["planes"] is None for x in cdn["venta"]["por_modalidad"].values())  # no "0 % preferente" line
    # The attack of the review: closed group minus the other closed Isapres, and all minus not on sale.
    for metric in ("planes", "cotizantes"):
        attacks = [(g["cerradas"]["venta"][metric], g["isapre:63"]["venta"][metric], g["isapre:65"]["venta"][metric]),
                   (cdn["todos"][metric], cdn["no_venta"][metric]),
                   (g["sistema"]["venta"][metric], g["abiertas"]["venta"][metric], g["isapre:63"]["venta"][metric],
                    g["isapre:65"]["venta"][metric])]
        assert all(None in a for a in attacks), metric
    assert agg.disclosure.check(res) == []
    print("hidden:", res["supresion"]["primarias"], "primary,", res["supresion"]["complementarias"], "complementary")


def test_leak_check_catches_a_cell_put_back():
    res = leaky_table()
    g = res["grupos"]
    # Undo the complementary cell of the review's attack (closed group on sale): the check must find the leak.
    assert "cerradas/venta" in res["supresion"]["celdas"]
    leaky = json.loads(json.dumps(res))
    leaky["grupos"]["cerradas"]["venta"].update(planes=15, cotizantes=999)
    leaky["grupos"]["cerradas"]["venta"].pop("suprimido")
    assert "small_cell_recoverable:isapre:94/venta:P" in agg.disclosure.check(leaky)
    # And a published cell of 1-4 plans is reported as such.
    leaky = json.loads(json.dumps(res))
    leaky["grupos"]["isapre:94"]["venta"].update(planes=1, cotizantes=10)
    assert "small_cell_published:isapre:94/venta" in agg.disclosure.check(leaky)


def test_month_discovery_never_guesses():
    links = ["https://datos.superdesalud.gob.cl/archivos/Planes%20de%20Salud/2026/Planes_de_Salud_202608.zip",
             "https://datos.superdesalud.gob.cl/archivos/Planes%20de%20Salud/2026/Planes_de_Salud_202607.zip",
             "https://datos.superdesalud.gob.cl/archivos/Planes%20de%20Salud/2025/Planes_de_Salud_202508.zip",
             "https://datos.superdesalud.gob.cl/archivos/Planes%20de%20Salud/2006/Planes_de_salud_200601.zip"]
    assert agg.plan_months(links) == ("202608", ["202608", "202607", "202508"])
    assert agg.plan_months(links[:1]) == ("202608", ["202608"])
    assert agg.plan_months([]) == (None, [])
    assert agg.month_add("202601", -1) == "202512" and agg.month_add("202608", -12) == "202508"


def test_run_local_writes_only_aggregates(tmp_path):
    prow = [plan_row(pid=f"PLANSECRET{i}", cot=i + 1) for i in range(6)]
    crow = [cob_row(pid=f"PLANSECRET{i}", code=c) for i in range(6) for c in agg.CANASTA["amb"]]
    local = {f"{agg.PLANES}:202608": make_zip(tmp_path / "Planes_de_Salud_202608.zip", prow),
             f"{agg.COBERTURA}:202608": make_zip(tmp_path / "Cobertura_Planes_Salud_202608.zip", crow),
             f"{agg.PLANES}:202607": make_zip(tmp_path / "Planes_de_Salud_202607.zip", prow)}
    out = tmp_path / "out"
    agg.run("202608", ["202608", "202607"], out, None, local=local, types=TYPES)
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.json"))
    assert files == ["202607/planes_202607.json", "202607/receipts_202607.json", "202608/cobertura_202608.json",
                     "202608/planes_202608.json", "202608/receipts_202608.json"]
    text = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*.json"))
    assert "PLANSECRET" not in text and "LINEASECRETA" not in text
    pl = json.loads((out / "202608/planes_202608.json").read_text(encoding="utf-8"))
    assert pl["filas"] == 6 and pl["grupos"]["isapre:67"]["todos"]["cotizantes"] == 21
    assert any(c.get("sensitive") for c in pl["perfil_columnas"] if c["name"] == "id_plan")
    rec = json.loads((out / "202608/receipts_202608.json").read_text(encoding="utf-8"))
    assert rec["script_version"] == agg.SCRIPT_VERSION and len(rec["files"]) == 2
    assert all(len(f["sha256"]) == 64 for f in rec["files"])
    assert not list((out / "202607").glob("cobertura_*"))  # no local Cobertura file for that month


def test_download_cap_is_one_gib():
    assert agg.MAX_FILE_BYTES == 1 << 30
