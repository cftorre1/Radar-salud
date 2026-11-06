"""F12 · Prestaciones bonificadas and F13 · Licencias médicas (SIS open data): PASS, disclosure rule, minimum cell,
HOLD on mismatched files, first-review gate, preview, registry, runner and Datos.

Fixtures are SYNTHETIC: pipe-delimited rows written into in-memory ZIPs and aggregated with the real
``scripts/aggregate_sis_open_data.py`` (``run(local=...)``), so the builders read exactly the files the workflow writes.
Codes, providers, amounts and hashes are test values, not SIS figures. Each KPI is recomputed here from the raw rows.
"""
import ast
import copy
import importlib.util
import json
import shutil
import subprocess
import zipfile
from datetime import date
from pathlib import Path

import pytest

from radar_salud import datos_index as di
from radar_salud import review_preview as rp
from radar_salud import sis_open_data as so
from radar_salud import stats_ficha_f12 as f12
from radar_salud import stats_ficha_f13 as f13
from radar_salud import stats_fichas as sf

REPO = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 5)
SPEC = importlib.util.spec_from_file_location("aggregate_sis_open_data", REPO / "scripts" / "aggregate_sis_open_data.py")
agg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agg)
HOST = "https://datos.superdesalud.gob.cl/archivos/{ds}/{y}/{f}"


def prest(q, isapre, prov, codigo, region, freq, fact, bonif, atencion="Atención Ambulatoria"):
    f = [""] * 30
    f[0], f[1], f[2], f[3], f[7], f[8], f[14], f[15] = isapre, q, "1", "SECRETBEN", prov, region, codigo, "FONASA"
    f[10] = f[11] = f[12] = f[13] = "SECRETFOLIO"
    f[18], f[19], f[20], f[21], f[22], f[23] = "Privado", atencion, str(freq), str(fact), str(bonif), str(fact - bonif)
    return f


def lic(isapre, resol="Autorícese", dias=10, aut=10, diag="J00-J99", region="13", sub=100000, act="Comercio", prof="Medico", q="2026t2"):
    f = [""] * 44
    f[0], f[2], f[4], f[8], f[12], f[13] = isapre, "SECRETWORKER", str(dias), act, "SECRETDOC", prof
    f[15], f[16], f[17], f[21], f[22], f[24], f[28], f[42] = str(aut), diag, resol, q, q, region, str(sub), "SECRETEMPLOYER"
    return f


CODES = ("0101001", "0301045", "0305001", "0401001")
# Isapre → bonificado share of facturado (synthetic): 67 covers more than 78 for the same provider and code.
COVER = {"67": 0.8, "78": 0.6, "99": 0.7}


def prest_rows(q):
    rows = []
    for ci, code in enumerate(CODES):
        for pi, prov in enumerate(("P1", "P2", "P3", "P4")):
            unit = 10000 * (ci + 1) + 2000 * pi
            for isapre, cov in COVER.items():
                for att in ("Atención Ambulatoria", "Atención Hospitalaria"):
                    rows.append(prest(q, isapre, prov, code, "13", 10, unit * 10, int(unit * 10 * cov), att))
    # region 5: exactly 2 providers (price, no p25-p75); region 6: 1 provider (no price); region 8: 2 providers, freq < 30
    rows += [prest(q, "67", "P5", "0101001", "5", 20, 200000, 160000), prest(q, "78", "P6", "0101001", "5", 20, 300000, 180000)]
    rows += [prest(q, "67", "P9", "0101001", "6", 400, 4400000, 3520000)]
    rows += [prest(q, "67", "P7", "0101001", "8", 2, 20000, 16000), prest(q, "78", "P8", "0101001", "8", 2, 30000, 18000)]
    return rows


def lic_rows(q):
    rows = []
    for isapre, rej_mental in (("67", 6), ("78", 3)):
        rows += [lic(isapre, diag="F00-F99", q=q, resol="Rechácese", aut=0, sub=0) for _ in range(rej_mental)]
        rows += [lic(isapre, diag="F00-F99", q=q) for _ in range(12 - rej_mental)]
        rows += [lic(isapre, diag="J00-J99", q=q, resol="Rechácese", aut=0, sub=0)]
        rows += [lic(isapre, diag="J00-J99", q=q, resol="Redúcese", dias=10, aut=5, sub=50000) for _ in range(2)]
        rows += [lic(isapre, diag="J00-J99", q=q, act="Mineria", region="2", prof="Matrona") for _ in range(11)]
    rows += [lic("99", diag="M00-M99", q=q) for _ in range(4)]  # Isapre cells under 10: suppressed (4 + 6 = 10)
    rows += [lic("94", diag="M00-M99", q=q) for _ in range(6)]
    return rows


def zipped(path: Path, name: str, rows: list, enc="latin-1") -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(name, ("\r\n".join("|".join(r) + "|" for r in rows) + "\r\n").encode(enc))
    return path


def make_root(tmp_path: Path, *, quarters=("2026t1", "2026t2")) -> Path:
    root = tmp_path / "root"
    (root / "data/entities").mkdir(parents=True)
    shutil.copy(REPO / "data/entities/isapres.json", root / "data/entities/isapres.json")
    src = tmp_path / "zips"
    src.mkdir()
    local = {}
    for q in quarters:
        local[f"prest_{q}"] = zipped(src / f"p{q}.zip", f"Prestaciones_Bonificadas_{q}.txt", prest_rows(q))
        local[f"lic_{q}"] = zipped(src / f"l{q}.zip", f"Licencias_Medicas_{q}.txt", lic_rows(q), "utf-8")
    arancel = "|".join(["76", "202604", "202603", "ISAPRE", "UF", "0101001", "0", "CONSULTA MEDICA ELECTIVA",
                        "Prestación Incluida en el Arancel Fonasa", " ", " ", " ", "1", "0", "0", "0", "2026"]) + "|"
    with zipfile.ZipFile(src / "a.zip", "w") as zf:
        zf.writestr("a.txt", arancel.encode("utf-8"))
    local["arancel_2026"] = src / "a.zip"
    agg.run(quarters[-1], quarters[0] if len(quarters) > 1 else None, root / so.AGG_ROOT, local=local)
    for q in quarters:  # the workflow downloads from the SIS host: give the receipts its URLs
        p = root / so.AGG_ROOT / q / f"receipts_{q}.json"
        rec = json.loads(p.read_text())
        for f in rec["files"]:
            fname = f"{f['dataset'].replace(' ', '_')}_{f['period']}.zip"
            f["url"] = HOST.format(ds=f["dataset"].replace(" ", "%20"), y=f["period"][:4], f=fname)
        p.write_text(json.dumps(rec))
    return root


def reg_open(**over):
    reg = copy.deepcopy(sf.load_registry())
    for fam in ("F12", "F13"):
        reg["families"][fam]["first_pass_requires_review"] = False
    reg["families"]["F12"]["cross_min_cells"] = over.get("cross_min_cells", 1)
    reg["families"]["F12"]["top_codes"] = 15
    return reg


def edit(root: Path, q: str, name: str, fn) -> None:
    p = root / so.AGG_ROOT / q / name
    d = json.loads(p.read_text())
    fn(d)
    p.write_text(json.dumps(d))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return make_root(tmp_path_factory.mktemp("f12f13"))


@pytest.fixture
def root(built, tmp_path):
    dst = tmp_path / "r"
    shutil.copytree(built, dst)
    return dst


# ---------------------------------------------------------------------------------------------------------------------
# F12


def test_f12_pass_recomputes_every_kpi_from_the_raw_rows(root):
    out = f12.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "pass", out.get("errors")
    fi = out["ficha"]
    assert fi["verification"]["verdict"] == "PASS" and fi["period"] == "2026-06" and fi["family"] == "F12"
    rows = prest_rows("2026t2")
    fact = sum(int(r[21]) for r in rows)
    bonif = sum(int(r[22]) for r in rows)
    k = {x["id"]: x for x in fi["kpis"]}
    assert k["bonificado_sistema"]["value"] == f12.fmt(bonif / fact * 100, 1) + "%"
    # same provider and code: 67 covers 0.8, 78 0.6, 99 0.7 → index vs. the mean 0.7: +14,3% and −14,3%
    assert k["brecha_mismo_prestador"]["value"] == f12.fmt(0.8 / 0.7 * 100 - 0.6 / 0.7 * 100, 1) + " pp"
    # Dirección 5-nov 21:25: the headline leads with prices — the most frequent code, named by its Arancel description,
    # national p25–p75 over all providers (unit prices 10, 10, 10, 11, 12, 14, 15, 15, 16 thousand → 10.000 and 15.000)
    units = sorted([10000, 12000, 14000, 16000, 10000, 15000, 11000, 10000, 15000])
    assert (agg.quantile(units, .25), agg.quantile(units, .75)) == (10000, 15000)
    assert fi["headline"] == "Consulta medica electiva cuesta entre $10.000 y $15.000 según el prestador (p25–p75, abril–junio 2026)"
    assert not any(n in fi["headline"] for n in ("Colmena", "Cruz Blanca", "Banmédica", "bonific"))
    # open Isapres whose median and weighted mean agree in sign and are ≥ 3 %: the coverage gap card, named as medians
    assert "medianas" in k["brecha_mismo_prestador"]["lines"][1] and "promedio" not in json.dumps(k["brecha_mismo_prestador"])
    assert [x["id"] for x in fi["kpis"]][:2] == ["dispersion_precios", "bonificado_sistema"]
    assert fi["kicker"] == "Prestaciones bonificadas · abril–junio 2026" and fi["date_basis"] == "first_detected"
    assert fi["sources"][0]["url"].endswith("Prestaciones_Bonificadas_2026t2.zip")
    assert [t["id"] for t in fi["tabs"]] == ["cobertura", "mismo-prestador", "precios", "regiones", "concentracion"]
    blob = json.dumps(fi, ensure_ascii=False)
    assert "SECRET" not in blob and '"P1"' not in blob and "P9" not in blob


def test_f12_disclosure_rule_one_provider_no_price_two_providers_price_national_counts_all(root):
    p = f12.build_package(root, reg_open())
    assert p["reconciliation"]["ok"], p["reconciliation"]["failures"]
    v = p["values"]
    b = "precio.0101001"
    # region 6: exactly 1 provider → no price, only n, frecuencia and top share (100 %)
    assert v[f"{b}.6.n"]["value"] == 1 and f"{b}.6.mediana" not in v and f"{b}.6.p25" not in v
    assert v[f"{b}.6.share_top"]["value"] == 100.0
    # region 5: 2 providers and ≥ 30 frecuencia → median (unit prices 10.000 and 15.000), no p25–p75
    assert v[f"{b}.5.mediana"]["value"] == 12500 and f"{b}.5.p25" not in v
    assert f"{b}.5.share_top" not in v and p["kpis"]["bands"][f"{b}.5"] == "50-60"  # n = 2: share only as a band
    # region 8: 2 providers but frecuencia < 30 → no price
    assert f"{b}.8.mediana" not in v and v[f"{b}.8.n"]["value"] == 2
    # national: every provider counts, including the one alone in region 6
    assert v[f"{b}.NACIONAL.n"]["value"] == 4 + 2 + 1 + 2
    assert v[f"{b}.NACIONAL.frec"]["value"] == 4 * 60 + 40 + 400 + 4
    fi = f12.compose(p, reg_open(), today=TODAY)
    table = next(c for t in fi["tabs"] for c in t["charts"] if c["id"] == "f12-precio-region")["table"]["rows"]
    r6 = next(r for r in table if r[0] == "0101001" and r[1] == "O'Higgins")
    assert r6[4] == "1 prestador: sin precio" and r6[5] == "100,0%"
    r5 = next(r for r in table if r[0] == "0101001" and r[1] == "Valparaíso")
    assert r5[4] == "$12.500" and r5[5] == "50–60%"
    assert any("≥ 2 prestadores distintos y ≥ 30 atenciones" in n["text"] for n in fi["notes"])


def test_f12_single_provider_row_with_a_price_holds(root):
    def inject(d):
        cols = d["columns"]
        for r in d["rows"]:
            row = dict(zip(cols, r))
            if row["n_prestadores"] == 1:
                r[cols.index("precio_mediana")] = 11000
                return
    edit(root, "2026t2", "prestaciones_2026t2_precios_fonasa_region.json", inject)
    out = f12.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "hold" and any("single_provider_with_price" in e for e in out["errors"])
    assert not sf.publish(out, root)["published"]


@pytest.mark.parametrize("q,name,fn,reason", [
    ("2026t2", "prestaciones_2026t2_resumen.json", lambda d: d.update(sha256_archivo="0" * 64), "aggregate_hash_mismatch"),
    ("2026t2", "prestaciones_2026t2_top_codigos.json", lambda d: d.update(filas=d["filas"] + 1), "aggregate_rows_mismatch"),
    ("2026t2", "prestaciones_2026t2_indice_isapre_mismo_prestador.json", lambda d: d.update(periodo="2026t1"), "aggregate_period_mismatch"),
    ("2026t2", "prestaciones_2026t2_precios_fonasa_region.json", lambda d: d.update(script_version="v1"), "aggregate_script_version"),
    ("2026t1", "prestaciones_2026t1_resumen.json", lambda d: d.update(sha256_archivo="f" * 64), "previous:aggregate_hash_mismatch"),
    ("2026t2", "receipts_2026t2.json", lambda d: d["files"][0].update(url="http://example.com/x.zip"), "source_not_sis_https"),
    ("2026t2", "receipts_2026t2.json", lambda d: d["files"][0].update(bytes=(1 << 30) + 1), "bytes_out_of_range"),
    ("2026t2", "receipts_2026t2.json", lambda d: d["files"][0]["parse"].update(rows_malformed=10), "malformed_rows_over_0.1pct"),
    ("2026t2", "receipts_2026t2.json", lambda d: d["files"][1].update(sha256="1" * 64), "arancel_hash_mismatch"),
    ("2026t2", "prestaciones_2026t2_resumen.json", lambda d: d["periodos_en_archivo"].update({"2026t1": 3}), "file_period_not_quarter"),
    ("2026t2", "prestaciones_2026t2_resumen.json",
     lambda d: d["por_isapre_tipo_atencion"][0].update(facturado=d["por_isapre_tipo_atencion"][0]["facturado"] + 5), "isapre_split_mismatch"),
    ("2026t2", "prestaciones_2026t2_resumen.json",
     lambda d: [r.update(isapre="555") for r in d["por_isapre_tipo_atencion"] if r["isapre"] == "99"], "isapre_without_name:555"),
])
def test_f12_holds_on_mismatched_files(root, q, name, fn, reason):
    edit(root, q, name, fn)
    out = f12.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "hold" and any(reason in e for e in out["errors"]), out["errors"]


def test_f12_cross_headline_needs_median_and_weighted_mean_to_agree(root):
    """Review of PR #152: if the weighted mean disagrees in sign (or is under 3 %), the comparison is not the headline;
    the fallback is the bonification range among open Isapres. Closed Isapres never lead."""
    def flip(d):
        for r in d["resumen_por_isapre"]:
            if r["isapre"] in ("67", "78"):
                r["indice_bonif_unit_media_ponderada_frec_pct"] = -r["indice_bonif_unit_media_ponderada_frec_pct"]
    edit(root, "2026t2", "prestaciones_2026t2_indice_isapre_mismo_prestador.json", flip)
    fi = f12.run(root, today=TODAY, registry=reg_open(), llm=False)["ficha"]
    assert fi["verification"]["verdict"] == "PASS"
    assert "brecha_mismo_prestador" not in [x["id"] for x in fi["kpis"]]  # no robust gap: no card, no claim
    tab = next(t for t in fi["tabs"] if t["id"] == "mismo-prestador")
    assert [c["id"] for c in tab["charts"]] == ["f12-mismo-prestador", "f12-mismo-prestador-ponderada"]


def test_f12_closed_isapres_stay_in_topics_but_never_lead(root):
    reg = reg_open()
    names = so.isapre_names(root)
    p = f12.build_package(root, reg)
    # make Colmena (open, top) look closed: the headline must switch to the other open Isapres
    ent = json.loads((root / "data/entities/isapres.json").read_text())
    for e in ent["entities"]:
        if e["official_code"] == 67:
            e["isapre_type"] = "closed"
    (root / "data/entities/isapres.json").write_text(json.dumps(ent))
    fi = f12.run(root, today=TODAY, registry=reg, llm=False)["ficha"]
    assert fi["verification"]["verdict"] == "PASS"
    assert "Colmena" not in json.dumps([x for x in fi["kpis"] if x["id"] == "brecha_mismo_prestador"], ensure_ascii=False)
    cob = next(c for t in fi["tabs"] for c in t["charts"] if c["id"] == "f12-bonif-isapre")
    assert any(r.get("tag") == "cerrada" and r["label"] == names["67"] for r in cob["rows"])
    assert any("Isapre cerrada (afiliación restringida)" in n["text"] for n in fi["notes"])
    assert p["kpis"]["strong"]


def test_f12_small_isapre_is_included_with_a_note_and_regional_fallback(root):
    """Dirección 5-nov 21:25: no Isapre-level minimum excludes an Isapre; below cross_min_cells it gets a note."""
    reg = reg_open(cross_min_cells=10 ** 6)
    fi = f12.run(root, today=TODAY, registry=reg, llm=False)["ficha"]
    assert "mismo-prestador" in [t["id"] for t in fi["tabs"]] and fi["verification"]["verdict"] == "PASS"
    assert any(n["text"].startswith("Base pequeña") for n in fi["notes"])
    reg["families"]["F12"]["headline_priority"] = ["precio_codigo_region"]
    fi = f12.run(root, today=TODAY, registry=reg, llm=False)["ficha"]
    # region 5 (2 providers, median 12.500) vs. Metropolitana (median 13.000): only disclosure-rule cells
    assert fi["headline"] == ("Consulta medica electiva cuesta 3,8% menos en Valparaíso que en la Metropolitana "
                              "(mediana entre prestadores, abril–junio 2026)")
    assert fi["verification"]["verdict"] == "PASS"


def test_f12_cross_topic_needs_valid_ids(root):
    edit(root, "2026t2", "prestaciones_2026t2_consistencia_ids.json", lambda d: d["veredicto"].update(cross_isapre_valido=False))
    fi = f12.run(root, today=TODAY, registry=reg_open(), llm=False)["ficha"]
    assert "mismo-prestador" not in [t["id"] for t in fi["tabs"]]
    assert any("verificación de los RUT cifrados" in n["text"] for n in fi["notes"])


# ---------------------------------------------------------------------------------------------------------------------
# F13


def test_f13_pass_recomputes_kpis_and_headline(root):
    out = f13.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "pass", out.get("errors")
    fi = out["ficha"]
    rows = lic_rows("2026t2")
    n = len(rows)
    rej = sum(1 for r in rows if r[17].startswith("Rech"))
    red = sum(1 for r in rows if r[17].startswith("Red"))
    k = {x["id"]: x for x in fi["kpis"]}
    assert k["rechazo"]["value"] == f13.fmt(rej / n * 100, 1) + "%"
    assert k["reduccion"]["value"] == f13.fmt(red / n * 100, 1) + "%"
    assert k["dias"]["value"] == f13.fmt(sum(int(r[15]) for r in rows) / sum(int(r[4]) for r in rows) * 100, 1) + "%"
    mental = [r for r in rows if r[16] == "F00-F99"]
    resp = [r for r in rows if r[16] == "J00-J99"]
    pm = sum(1 for r in mental if r[17].startswith("Rech")) / len(mental) * 100
    pr = sum(1 for r in resp if r[17].startswith("Rech")) / len(resp) * 100
    assert fi["headline"] == (f"Las Isapres rechazan el {f13.fmt(pm, 1)}% de las licencias de salud mental y el "
                              f"{f13.fmt(pr, 1)}% de las respiratorias en abril–junio 2026")
    assert [t["id"] for t in fi["tabs"]] == ["isapres", "diagnostico", "industria", "region", "dias", "subsidio"]
    assert any("no se calculan días hasta la resolución" in n["text"] for n in fi["notes"])
    blob = json.dumps(fi, ensure_ascii=False)
    assert "SECRET" not in blob and "Banmédica" not in blob and "Cruz del Norte" not in blob  # cells < 10: never shown
    assert k["rechazo"]["lines"][0] == f"{f13.fmt(rej, 0)} de {f13.fmt(n, 0)} licencias informadas"
    assert fi["dek"].startswith(f"De {f13.fmt(n, 0)} licencias informadas, las Isapres rechazaron {rej} (")


def test_f13_min_cell_suppressed_isapre_never_shown_and_rechecked(root):
    p = f13.build_package(root, reg_open())
    assert p["reconciliation"]["ok"], p["reconciliation"]["failures"]
    assert not any(k.startswith("lic.2026t2.isapre.99.") for k in p["values"])
    assert not any(k.startswith("lic.2026t2.isapre.94.") for k in p["values"])
    assert p["values"]["lic.2026t2.isapre.suprimidas"]["value"] == 10
    # a cell under 10 that slipped into the aggregate HOLDs
    edit(root, "2026t2", "licencias_2026t2.json",
         lambda d: d["breakdowns"]["isapre"]["filas"].append({**d["breakdowns"]["isapre"]["filas"][0], "grupo": "99", "licencias": 4})
         or d["breakdowns"]["isapre"].update(licencias_en_celdas_suprimidas=6))
    out = f13.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "hold" and any(e.startswith("HOLD_RECONCILIATION") and "cell_under_min" in e for e in out["errors"])


def _expose_one(d):
    """An aggregate without complementary suppression: one published cell of 1 licence moved out of the remainder."""
    b = d["breakdowns"]["isapre"]
    b["filas"].append({**b["filas"][0], "grupo": "94", "licencias": 6})
    b["licencias_en_celdas_suprimidas"] = 4


@pytest.mark.parametrize("fn,reason", [
    (lambda d: d["breakdowns"]["region"].update(licencias_en_celdas_suprimidas=7), "breakdown_does_not_add"),
    (_expose_one, "recoverable_remainder"),
    (lambda d: d.update(sha256_archivo="0" * 64), "aggregate_hash_mismatch"),
    (lambda d: d["total"].update(pct_rechazadas=50.0), "resolution_shares_do_not_add"),
    (lambda d: d.update(regla_celda_minima=5), "min_cell_rule"),
])
def test_f13_holds_on_mismatched_files(root, fn, reason):
    edit(root, "2026t2", "licencias_2026t2.json", fn)
    out = f13.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "hold" and any(reason in e for e in out["errors"]), out["errors"]


# ---------------------------------------------------------------------------------------------------------------------
# Both: first review, preview, no model, registry, runner, Datos, Python 3.11


@pytest.mark.parametrize("mod,fam", [(f12, "F12"), (f13, "F13")])
def test_first_publication_waits_for_review_and_shows_in_preview(root, mod, fam):
    reg = copy.deepcopy(reg_open())
    reg["families"][fam]["first_pass_requires_review"] = True
    out = mod.run(root, today=TODAY, registry=reg, llm=False)
    assert out["status"] == "hold" and out["errors"] == [so.FIRST_REVIEW_HOLD]
    cand = out["candidate"]
    assert cand["status"] == "AWAITING_FIRST_REVIEW" and cand["verification"]["verdict"] == "PASS"
    ev = cand["review_request"]["evidence_sha256"]
    assert ev == so.evidence_sha256({s["key"]: s for s in cand["sources"]})
    assert not sf.publish(out, root)["published"]
    web = root / "web/data"
    assert rp.write(root, web) == [reg["families"][fam]["slug"]]
    assert json.loads((web / "preview" / f"{reg['families'][fam]['slug']}.json").read_text())["ficha"]["headline"] == cand["headline"]
    reg["families"][fam]["first_review"] = {"reviewed_by": "revisor de prueba", "reviewed_at": "2026-11-05", "reviewed_sha256": "0" * 64}
    assert mod.run(root, today=TODAY, registry=reg, llm=False)["status"] == "hold"
    reg["families"][fam]["first_review"]["reviewed_sha256"] = ev
    out = mod.run(root, today=TODAY, registry=reg, llm=False)
    assert out["status"] == "pass" and sf.publish(out, root)["published"]


@pytest.mark.parametrize("mod", [f12, f13])
def test_no_model_call_even_with_llm_requested(root, mod):
    def model(*a, **k):
        raise AssertionError("model called")
    out = mod.run(root, today=TODAY, registry=reg_open(), llm=True, model_call=model, budget=lambda usd: (True, "ok"))
    assert out["status"] == "pass" and out["ficha"]["lectura"]["status"] == "not_attempted"


def test_single_quarter_has_no_comparison_and_still_passes(tmp_path):
    root = make_root(tmp_path, quarters=("2026t2",))
    for mod in (f12, f13):
        out = mod.run(root, today=TODAY, registry=reg_open(), llm=False)
        assert out["status"] == "pass", out.get("errors")
        assert "trim." not in json.dumps(out["ficha"]["kpis"], ensure_ascii=False)


def test_registry_runner_and_datos_rows(root):
    reg = sf.load_registry()
    spec = importlib.util.spec_from_file_location("run_stats_fichas", REPO / "scripts/run_stats_fichas.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    for mod, fam, group in ((f12, "F12", "prestadores"), (f13, "F13", "empleadores_licencias")):
        cfg = reg["families"][fam]
        assert cfg["status"] == "active" and cfg["group"] == group and cfg["builder_version"] == mod.BUILDER_VERSION
        assert cfg["first_pass_requires_review"] is True and cfg["first_review"] is None and cfg["lectura_enabled"] is False
        assert cfg["cadence"].startswith("trimestral") and cfg["period_kind"] == "quarter"
        assert runner.BUILDERS[fam] is mod.run and fam not in runner.CAPTURED | runner.FEFI_CAPTURED | runner.DIPRES_CAPTURED
        fi = mod.run(root, today=TODAY, registry=reg_open(), llm=False)["ficha"]
        card = sf.ficha_card(fi, cfg)
        row = next(r for r in di.build([card], root=root)["families"] if r["family"] == fam)
        assert row["state"] == "live" and row["source"] == "SIS" and row["period_label"] == "abr–jun 2026"
        assert [x["id"] for x in row["kpis"]] == cfg["datos_kpis"]
    rows = {r["family"]: r for r in di.build([], root=root)["families"]}
    assert rows["F12"]["state"] == rows["F13"]["state"] == "pending"  # active, held by first review: no figures


def test_disclosure_rule_registered_as_decided():
    rule = sf.load_registry()["families"]["F12"]["disclosure_rule"]
    assert (rule["price_min_providers"], rule["price_min_frecuencia"], rule["iqr_min_providers"]) == (2, 30, 3)
    assert (f12.PRICE_MIN_PROVIDERS, f12.PRICE_MIN_FREQ, f12.IQR_MIN_PROVIDERS) == (agg.PRICE_MIN_PROVIDERS, agg.PRICE_MIN_FREQ,
                                                                                   agg.IQR_MIN_PROVIDERS) == (2, 30, 3)
    assert so.SCRIPT_VERSION == agg.SCRIPT_VERSION and so.MAX_FILE_BYTES == agg.MAX_FILE_BYTES == 1 << 30
    assert sf.load_registry()["families"]["F13"]["min_cell"] == f13.MIN_CELL == agg.LIC_MIN_CELL == 10


NEW_FILES = ["src/radar_salud/sis_open_data.py", "src/radar_salud/stats_ficha_f12.py", "src/radar_salud/stats_ficha_f13.py",
             "src/radar_salud/datos_index.py", "scripts/aggregate_sis_open_data.py", "scripts/run_stats_fichas.py"]


@pytest.mark.parametrize("rel", NEW_FILES)
def test_parses_with_python_3_11(rel):
    path = REPO / rel
    ast.parse(path.read_text(encoding="utf-8"), filename=rel, feature_version=(3, 11))
    py311 = shutil.which("python3.11")
    if py311:
        res = subprocess.run([py311, "-I", "-c", "import ast,sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())", str(path)],
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stderr


# ---------------------------------------------------------------------------------------------------------------------
# Committed aggregates (real SIS files, aggregated in Actions): assert the rules, not the counts (PLAYBOOK §4).


def _real():
    return [q for q in so.quarters(REPO)
            if (so.load_json(REPO / so.AGG_ROOT / q / f"receipts_{q}.json") or {}).get("script_version") == so.SCRIPT_VERSION]


@pytest.mark.skipif(not _real(), reason="no committed v2 aggregates yet")
@pytest.mark.parametrize("mod", [f12, f13])
def test_committed_aggregates_reconcile_and_verify(mod):
    reg = copy.deepcopy(sf.load_registry())
    p = mod.build_package(REPO, reg)
    assert p["reconciliation"]["ok"], p["reconciliation"]["failures"]
    fi = mod.compose(p, reg, today=TODAY, decision={"triggers": ["new_period"]})
    ver = sf.verify_ficha(fi, p)
    assert ver["verdict"] == "PASS", ver["errors"]
    blob = json.dumps(fi, ensure_ascii=False)
    assert "SECRET" not in blob


@pytest.mark.skipif(not _real(), reason="no committed v2 aggregates yet")
def test_committed_price_rows_obey_the_disclosure_rule():
    for q in _real():
        d = so.load_json(REPO / so.AGG_ROOT / q / f"prestaciones_{q}_precios_fonasa_region.json")
        if d:
            assert f12.disclosure_failures(d["columns"], d["rows"]) == []
