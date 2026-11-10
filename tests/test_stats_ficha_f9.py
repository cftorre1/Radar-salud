"""F9 Benchmark de planes: builder on synthetic fixtures (all rows invented), reconciliation HOLDs, robustness rule,
minimum cells, open/closed rule, no model call, and the Python 3.11 parse of the new files."""
from __future__ import annotations

import ast
import importlib.util
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

from radar_salud import stats_ficha_f9 as f9
from radar_salud import stats_fichas as sf

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("aggregate_sis_planes", REPO / "scripts" / "aggregate_sis_planes.py")
agg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agg)

TYPES = {"67": "open", "99": "open", "63": "closed"}
NAMES = {"67": "Colmena", "99": "Banmédica", "63": "Isalud"}
TODAY = date(2026, 11, 10)


def plan_row(month, isapre, pid, comer, cot, precio, mod="Prestador Preferente", tipo="Individual"):
    f = [" "] * 38
    f[0], f[1], f[2], f[3], f[4], f[5] = month, isapre, pid, "N" + pid, "L", "202001"
    f[8], f[10], f[11], f[14], f[15], f[16], f[23] = comer, tipo, mod, "UF", f"{precio:.2f}", "T", f"{precio:.2f}"
    f[26], f[27], f[31], f[32] = "70", "90", str(cot), str(cot // 2)
    return f


def month_rows(month, *, sale_price=3.0, stock_price=2.0, closed_share=True, small_isapre=False):
    """Per open Isapre: 8 plans on sale (few cotizantes) and 12 not on sale (many cotizantes); closed Isapre 63 too."""
    rows = []
    for isapre in ("67", "99", "63"):
        for i in range(8):
            rows.append(plan_row(month, isapre, f"V{isapre}{i}", "Si Comer.", 2 + i, sale_price + i / 100))
        n_old = 2 if (small_isapre and isapre == "63") else 12
        for i in range(n_old):
            cot = (100 + i) if closed_share else 1
            rows.append(plan_row(month, isapre, f"N{isapre}{i}", "No Comer.", cot, stock_price + i / 100, mod="Libre elección"))
    return rows


def cob_rows(month, plan_rows, amb=70, hosp=90):
    out = []
    for f in plan_rows:
        if f[8] != "Si Comer.":
            continue
        for code in agg.CANASTA["amb"]:
            out.append([f[1], month, f[2], str(amb), "Con Tope", "", "", "", "0", "Sin Tope", "", "", "", code, "0", "0"])
        for code in agg.CANASTA["hosp"]:
            out.append([f[1], month, f[2], "0", "Sin Tope", "", "", "", str(hosp), "Con Tope", "", "", "", code, "0", "0"])
    return out


def zipped(path: Path, rows) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(path.stem + ".txt", ("\r\n".join("|".join(r) + "|" for r in rows) + "\r\n").encode("latin-1"))
    return path


def make_root(tmp_path: Path, months=("202609", "202608", "202509"), f1_months=("202608",), **kw) -> Path:
    root = tmp_path / "root"
    (root / "data/entities").mkdir(parents=True)
    (root / "data/market").mkdir(parents=True)
    (root / "data/entities/isapres.json").write_text(json.dumps({"entities": [
        {"official_code": int(c), "commercial_name": NAMES[c], "isapre_type": TYPES[c]} for c in TYPES]}), encoding="utf-8")
    local, all_rows = {}, {}
    zdir = tmp_path / "zips"
    zdir.mkdir()
    for m in months:
        rows = month_rows(m, **kw.get(m, {}))
        all_rows[m] = rows
        local[f"{agg.PLANES}:{m}"] = zipped(zdir / f"Planes_de_Salud_{m}.zip", rows)
        local[f"{agg.COBERTURA}:{m}"] = zipped(zdir / f"Cobertura_Planes_Salud_{m}.zip", cob_rows(m, rows))
    out = root / f9.AGG_ROOT
    agg.run(months[0], list(months), out, None, local=local, types=TYPES)
    for m in months:  # local runs record 'local:' URLs; the real workflow records the SIS URL
        p = out / m / f"receipts_{m}.json"
        rec = json.loads(p.read_text(encoding="utf-8"))
        for x in rec["files"]:
            folder = "Planes%20de%20Salud" if x["dataset"] == agg.PLANES else "Cobertura%20Planes"
            x["url"] = f"https://datos.superdesalud.gob.cl/archivos/{folder}/{m[:4]}/{x['url'].split(':', 1)[1]}"
        p.write_text(json.dumps(rec), encoding="utf-8")
    obs = []
    for m in f1_months:
        for c in TYPES:
            cot = sum(int(f[31]) for f in all_rows[m] if f[1] == c)
            car = sum(int(f[32]) for f in all_rows[m] if f[1] == c)
            for metric, val in (("cotizantes", cot), ("cargas", car)):
                obs.append({"official_code": int(c), "metric_id": metric, "value": val, "period": f"{m[:4]}-{m[4:]}",
                            "source_url": "https://www.superdesalud.gob.cl/app/uploads/2026/09/cartera-sintetica.xlsx",
                            "source_sha256": "a" * 64})
    (root / "data/market/isapre_portfolio.json").write_text(json.dumps({"observations": obs}), encoding="utf-8")
    return root


def registry():
    return sf.load_registry()


def test_builder_passes_on_fixtures_and_waits_for_first_review(tmp_path):
    root = make_root(tmp_path)
    out = f9.run(root, today=TODAY, registry=registry(), llm=False)
    assert out["status"] == "hold" and out["errors"] == [so_hold()]
    c = out["candidate"]
    assert c["status"] == "AWAITING_FIRST_REVIEW" and c["verification"]["verdict"] == "PASS"
    assert c["review_request"]["evidence_sha256"] == c["evidence_sha256"]
    # Independent recomputation of the headline share from the fixture rows (open Isapres only).
    rows = month_rows("202609")
    open_rows = [f for f in rows if TYPES[f[1]] == "open"]
    share = 100 * sum(int(f[31]) for f in open_rows if f[8] == "No Comer.") / sum(int(f[31]) for f in open_rows)
    assert c["headline"].startswith(f"El {f9.fmt(share, 1)}% de los cotizantes de Isapres abiertas")
    assert "septiembre 2026" in c["headline"] and len(c["headline"]) <= 140
    on_sale = sum(1 for f in open_rows if f[8] == "Si Comer.")
    assert c["kpis"][1]["value"] == f9.fmt(on_sale, 0)
    assert 4 <= len(c["tabs"]) <= 6 and all(t.get("dek") for t in c["tabs"])
    assert len(c["dek"].split()) <= 40


def so_hold():
    from radar_salud import sis_open_data
    return sis_open_data.FIRST_REVIEW_HOLD


def test_closed_isapres_marked_and_never_in_comparisons(tmp_path):
    root = make_root(tmp_path)
    c = f9.run(root, today=TODAY, registry=registry(), llm=False)["candidate"]
    tagged = {r["label"] for ch in sf.all_charts(c) for r in ch["rows"] if r.get("tag") == "cerrada"}
    assert tagged == {"Isalud"}
    assert any("Isalud: Isapre cerrada (afiliación restringida)" in n["text"] for n in c["notes"])
    titles = [c["headline"], c["dek"], *[t["dek"] for t in c["tabs"]], *[t["index_line"] for t in c["tabs"]]]
    assert not any("Isalud" in x for x in titles)


def test_title_is_neutral_when_not_robust(tmp_path):
    # Only month t: no previous month nor year, so no finding can repeat → descriptive titles and fallback headline.
    root = make_root(tmp_path, months=("202609",), f1_months=("202609",))
    c = f9.run(root, today=TODAY, registry=registry(), llm=False)["candidate"]
    assert c["headline"] == "Planes de salud Isapre, septiembre 2026"
    assert not any(r["robusto"] for r in c["robustness"].values())
    assert c["tabs"][0]["dek"] == "Cotizantes en planes que ya no se venden, por Isapre"


def test_price_title_needs_weighted_and_unweighted_to_agree(tmp_path):
    root = make_root(tmp_path)
    pkg = f9.build_package(root, registry())
    assert pkg["robustness"]["precio_venta_vs_vigentes"]["robusto"]
    # Break agreement: the weighted median of plans in force moves above the on-sale one, the unweighted does not.
    v = pkg["values"]
    v["pl.202609.ab.vig.pond"]["value"] = v["pl.202609.ab.venta.pond"]["value"] + 1
    rb = f9.robustness(pkg)
    assert rb["precio_venta_vs_vigentes"]["t"] is None and not rb["precio_venta_vs_vigentes"]["robusto"]


def test_minimum_cells_suppress_medians(tmp_path):
    root = make_root(tmp_path, **{"202609": {"small_isapre": True}})
    pl = json.loads((root / f9.AGG_ROOT / "202609/planes_202609.json").read_text(encoding="utf-8"))
    cell = pl["grupos"]["isapre:63"]["no_venta"]["precio_uf"]
    assert cell["n"] == 2 and cell["mediana"] is None and cell["suprimido"] == "<5 planes"
    assert pl["grupos"]["isapre:63"]["no_venta"]["cotizantes"] == 201  # counts are always published
    pkg = f9.build_package(root, registry())
    assert "pl.202609.63.nv.med" not in pkg["values"] and "pl.202609.63.nv.cot" in pkg["values"]


def test_hold_when_cotizantes_do_not_match_the_cartera_workbook(tmp_path):
    root = make_root(tmp_path)
    p = root / "data/market/isapre_portfolio.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["observations"][0]["value"] += 50
    p.write_text(json.dumps(d), encoding="utf-8")
    assert f9.run(root, today=TODAY, registry=registry(), llm=False)["status"] == "hold"
    fails = f9.build_package(root, registry())["reconciliation"]["failures"]
    assert any(e.startswith("t1:f1_mismatch:202608:67:cotizantes") for e in fails)


def test_hold_without_any_month_in_common_with_the_cartera(tmp_path):
    root = make_root(tmp_path, f1_months=())
    pkg = f9.build_package(root, registry())
    assert pkg["reconciliation"]["failures"] == ["f1_no_common_month"]


@pytest.mark.parametrize("edit, reason", [
    (lambda d: d.update(sha256_archivo="0" * 64), "aggregate_hash_mismatch:planes_202609.json"),
    (lambda d: d.update(script_version="old"), "aggregate_script_version:planes_202609.json:old"),
    (lambda d: d["grupos"]["isapre:67"]["todos"].update(cotizantes=d["grupos"]["isapre:67"]["todos"]["cotizantes"] + 1),
     "isapres_do_not_add:202609:todos:cotizantes"),
    (lambda d: d.update(periodos_en_archivo={"202609": 1, "202608": 1}), "file_period_not_month:planes_202609.json:202608,202609"),
])
def test_reconciliation_failures_hold(tmp_path, edit, reason):
    root = make_root(tmp_path)
    p = root / f9.AGG_ROOT / "202609/planes_202609.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    edit(d)
    p.write_text(json.dumps(d), encoding="utf-8")
    pkg = f9.build_package(root, registry())
    assert not pkg["reconciliation"]["ok"] and reason in pkg["reconciliation"]["failures"]


def test_source_off_sis_host_holds(tmp_path):
    root = make_root(tmp_path)
    p = root / f9.AGG_ROOT / "202609/receipts_202609.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["files"][0]["url"] = "http://example.org/x.zip"
    p.write_text(json.dumps(d), encoding="utf-8")
    assert "source_not_sis_https:Planes de Salud:202609" in f9.build_package(root, registry())["reconciliation"]["failures"]


def test_no_model_call_even_with_llm_requested(tmp_path):
    root = make_root(tmp_path)

    def boom(*a, **k):
        raise AssertionError("model called")
    out = f9.run(root, today=TODAY, registry=registry(), llm=True, model_call=boom, budget=lambda usd: (True, "ok"))
    assert out["candidate"]["lectura"]["status"] == "not_attempted"


def test_registry_entry():
    cfg = registry()["families"]["F9"]
    assert cfg["slug"] == "f9_planes" and cfg["status"] == "active" and cfg["lectura_enabled"] is False
    assert cfg["first_pass_requires_review"] is True and cfg["first_review"] is None
    assert cfg["headline_priority"][0] == "cerrados_venta" and cfg["builder_version"] == f9.BUILDER_VERSION
    assert f9.SCRIPT_VERSION == agg.SCRIPT_VERSION


@pytest.mark.parametrize("rel", ["src/radar_salud/stats_ficha_f9.py", "scripts/aggregate_sis_planes.py",
                                 "tests/test_stats_ficha_f9.py", "tests/test_aggregate_sis_planes.py"])
def test_python_311_parse(rel):
    ast.parse((REPO / rel).read_text(encoding="utf-8"), filename=rel, feature_version=(3, 11))
