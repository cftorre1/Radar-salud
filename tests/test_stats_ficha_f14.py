"""F14 · GES por patología: builder on fixtures, privacy and leak checks, minimum cells, HOLDs, first-review gate,
registry, runner, committed aggregates and Python 3.11 parse; plus the GES part of the historical backfill
(``scripts/sis_historico_ges.py``, tests brought over from ``tests/test_sis_historico.py`` on claude/sis-historico).

Fixtures are SYNTHETIC: pipe-delimited rows in in-memory ZIPs aggregated with the real ``sis_historico_ges.run_quarter``,
so the builder reads exactly the files the script writes. Codes, providers, amounts and hashes are test values, not SIS
figures. Each headline figure is recomputed here from the raw rows.
"""
import ast
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

from radar_salud import datos_index as di
from radar_salud import ges_privacy as gp
from radar_salud import review_preview as rp
from radar_salud import sis_open_data as so
from radar_salud import stats_ficha_f14 as f14
from radar_salud import stats_fichas as sf

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))
TODAY = date(2026, 11, 10)
SECRET = "ENC"  # every encrypted identifier of the fixtures starts like this; it must never reach an output


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ges = _load("sis_historico_ges")
pub = _load("ges_f14_publicable")
REF = json.loads((REPO / "data/reference/ges_problemas_ds29_2025.json").read_text(encoding="utf-8"))


def row(isapre="67", prov="ENCPROV1", region="13", cobertura="GES", atencion="Atención Ambulatoria", freq=1, fact=10000,
        bonif=6000, gpp="X", id_ges="X", q="2026t3"):
    f = [""] * 30
    f[0], f[1], f[2], f[3], f[4], f[5], f[6] = isapre, q, "Curativa", "ENCBEN1", "Femenino", "36-40", "Cotizante"
    f[7], f[8], f[9], f[10], f[11], f[12], f[13] = prov, region, "No", "ENCPAM", "0", "ENCBONO", "0"
    f[14], f[15], f[16], f[17], f[18], f[19] = "0101001", "FONASA", cobertura, q, "Privado", atencion
    f[20], f[21], f[22], f[23] = str(freq), str(fact), str(bonif), str(fact - bonif)
    f[24], f[25], f[26], f[27], f[28], f[29] = "No", "Cobertura general", "No aplicable", "No", gpp, id_ges
    return f


# problem -> (cases in the oldest quarter, price per case, regions)
PROBLEMS = {21: (160, 30000, 1), 7: (160, 90000, 1), 34: (156, 200000, 13), 75: (120, 250000, 1), 8: (120, 800000, 1),
            70: (120, 2000000, 1), 61: (120, 60000, 1), 38: (120, 80000, 1), 18: (120, 900000, 1), 11: (120, 400000, 1),
            41: (120, 50000, 1), 54: (120, 300000, 1)}
REGS13 = ["13", "5", "8", "7", "9", "10", "6", "4", "2", "1", "14", "16", "3"]
ISAPRES = ["67", "78", "99", "63"]
QS = ("2024t3", "2025t3", "2026t3")


def quarter_rows(q, fact_growth=0.10, case_growth=1):
    y = QS.index(q)
    out = []
    for p, (n0, price, nreg) in PROBLEMS.items():
        n = n0 + case_growth * y * (13 if nreg > 1 else 4)
        regs = REGS13 if nreg > 1 else ["13"]
        unit = round(price * (1 + fact_growth) ** y)
        for c in range(n):
            reg = regs[c % len(regs)]
            isa = ISAPRES[c % 4]
            prov = f"ENCP{p}_{reg}_{(c // max(len(regs), 4)) % 4}"
            out.append(row(isapre=isa, prov=prov, region=reg, gpp=f"{p}T1", id_ges=f"ENCGES{p}_{c}", fact=unit,
                           bonif=int(unit * 0.8), q=q))
    out += [row(cobertura="Plan Complementario", fact=50_000_000, q=q, prov=f"ENCNG{i}") for i in range(40)]
    return out


def zipped(path, rows):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("p.txt", ("\r\n".join("|".join(r) + "|" for r in rows) + "\r\n").encode("latin-1"))
    return path


def make_root(tmp_path, quarters=QS, **kw):
    root = tmp_path / "root"
    (root / "data/entities").mkdir(parents=True)
    shutil.copy(REPO / "data/entities/isapres.json", root / "data/entities/isapres.json")
    (root / "data/reference").mkdir(parents=True)
    shutil.copy(REPO / f14.REF, root / f14.REF)
    out = root / f14.ROOT_DIR
    for q in quarters:
        z = zipped(tmp_path / f"{q}.zip", quarter_rows(q, **kw))
        rec = ges.run_quarter(q, out, z)
        assert rec["estado"] == "ok", rec
        p = out / q / f"receipts_{q}.json"
        d = json.loads(p.read_text())
        d["archivo"]["url"] = f"https://datos.superdesalud.gob.cl/archivos/Prestaciones%20Bonificadas/{q[:4]}/Prestaciones_Bonificadas_{q}.zip"
        d["estado"] = "ok"
        p.write_text(json.dumps(d))
    return root


def reg_open():
    reg = copy.deepcopy(sf.load_registry())
    reg["families"]["F14"]["first_pass_requires_review"] = False
    return reg


def edit(root, q, fn, name="ges_gpp_publicable_{q}.json"):
    p = root / f14.ROOT_DIR / q / name.format(q=q)
    d = json.loads(p.read_text())
    fn(d)
    p.write_text(json.dumps(d))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return make_root(tmp_path_factory.mktemp("f14"))


@pytest.fixture
def root(built, tmp_path):
    dst = tmp_path / "r"
    shutil.copytree(built, dst)
    return dst


def build(root, reg=None):
    reg = reg or reg_open()
    p = f14.build_package(root, reg)
    assert p["reconciliation"]["ok"], p["reconciliation"]["failures"]
    fi = f14.compose(p, reg, today=TODAY, decision={"triggers": ["new_period"]})
    return p, fi


# ---------------------------------------------------------------------------------------------------------------------
# Builder


def test_f14_pass_and_headline_recomputed_from_raw_rows(root):
    out = f14.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "pass", out.get("errors")
    fi = out["ficha"]
    assert fi["verification"]["verdict"] == "PASS"
    # independent recomputation from the raw rows (all GES rows pass the minimums in this fixture)
    tot = {}
    for q in ("2025t3", "2026t3"):
        rows = [r for r in quarter_rows(q) if r[28] != "X"]
        tot[q] = (sum(int(r[21]) for r in rows), len({(r[0], r[29]) for r in rows}))
    fact = (tot["2026t3"][0] / tot["2025t3"][0] - 1) * 100
    cases = (tot["2026t3"][1] / tot["2025t3"][1] - 1) * 100
    assert fi["headline_type"] == "gap_spend_cases"
    assert fi["headline"].startswith(f"GES en Isapres: facturado +{f14.fmt(fact, 1)}%, casos +{f14.fmt(cases, 1)}%; por caso sube en ")
    assert fi["kpis"][0]["value"] == f"{f14.fmt(tot['2026t3'][0] / 1e6, 0)} MM$"
    # «Nuevos problemas» (Dirección 13-nov-2026) appears only when problems 88–90 have data; the fixture has none.
    assert [t["id"] for t in fi["tabs"]] == [x for x in f14.TAB_ORDER if x != "nuevos"]
    assert fi["sources"][0]["url"].endswith("Prestaciones_Bonificadas_2026t3.zip")
    assert len(fi["headline"]) <= 140 and len(fi["dek"].split()) <= 40
    assert SECRET not in json.dumps(fi, ensure_ascii=False)


def test_f14_headline_falls_back_when_spend_does_not_outgrow_cases(tmp_path):
    root = make_root(tmp_path, fact_growth=0.0, case_growth=1)
    p, fi = build(root)
    assert fi["headline_type"] == "default" and "facturados en jul–sep 2026" in fi["headline"]
    assert not p["kpis"]["checks"]["actual"]
    assert sf.verify_ficha(fi, p)["verdict"] == "PASS"


def test_f14_headline_needs_the_previous_year_too(root):
    # when the gap fails one year earlier there is no systemic headline
    reg = reg_open()
    p = f14.build_package(root, reg)
    p["kpis"]["checks"]["anio_anterior"] = False
    fi = f14.compose(p, reg, today=TODAY, decision={})
    assert fi["headline_type"] == "default"


def test_sign_aware_wording_and_no_causal_words(root):
    p, fi = build(root)
    text = " ".join(sf.displayed_texts(fi))
    assert not sf.SIGNED_WITH_WORD.search(text)
    for w in ("porque", "debido a", "explica", "causa"):
        assert w not in sf._fold(fi["headline"] + " " + fi["dek"] + " ".join(t["dek"] or "" for t in fi["tabs"]))


# ---------------------------------------------------------------------------------------------------------------------
# Privacy: minimum cells, providers, leak check


def test_published_rows_meet_minimums_and_no_encrypted_ids(root):
    for q in QS:
        d = json.loads((root / f14.ROOT_DIR / q / f"ges_gpp_publicable_{q}.json").read_text())
        assert gp.check(d, REF) == []
        for t in gp.TABLES:
            for r in d[t]["filas"]:
                assert r["casos"] >= 10 and r["n_prestadores"] >= 3
        assert not {"por_problema_isapre", "por_problema_isapre_region", "por_problema_intervencion"} & set(d)
        for p in (root / f14.ROOT_DIR / q).glob("*.json"):
            assert SECRET not in p.read_text(encoding="utf-8"), p.name


def _src(fam_rows, prob_rows, fi_rows=(), pr_rows=(), total=None):
    t = {"facturado": total if total is not None else sum(r["facturado"] for r in fam_rows), "bonificado": 0, "frecuencia": 0,
         "pct_facturado_del_trimestre": 5.0}
    for r in [*fam_rows, *prob_rows, *fi_rows, *pr_rows]:
        r.setdefault("bonificado", 0)
        r.setdefault("frecuencia", 0)
    return {"totales": t, "por_familia_nacional": {"filas": list(fam_rows)}, "por_problema_nacional": {"filas": list(prob_rows)},
            "por_familia_isapre": {"filas": list(fi_rows)}, "por_problema_region": {"filas": list(pr_rows)}}


def R(**kw):
    return {"n_prestadores": 5, **kw}


def test_sanitize_drops_single_and_two_provider_rows():
    src = _src([R(familia="cancer", casos=100, facturado=1000)],
               [R(problema=8, familia="cancer", casos=40, facturado=400), R(problema=70, familia="cancer", casos=30, facturado=300),
                R(problema=27, familia="cancer", casos=30, facturado=300, n_prestadores=2)])
    doc, rep = gp.sanitize(src, REF)
    assert rep["suprimidas_por_prestadores"] == 1
    # the 2-provider row would be the only hidden child: one more problem is hidden with it
    assert len(doc["por_problema_nacional"]["filas"]) == 1 and gp.check(doc, REF) == []


def test_sanitize_hides_one_more_when_the_source_hid_a_single_problem():
    # family 100 cases; published problems add up to 92: the 8 hidden cases would be recovered by subtraction
    src = _src([R(familia="cancer", casos=100, facturado=1000)],
               [R(problema=8, familia="cancer", casos=50, facturado=500), R(problema=70, familia="cancer", casos=42, facturado=420)])
    assert any(x.startswith("hidden_cases_under_10") for x in gp.check({**src, "version_publicable": gp.PUBLIC_VERSION}, REF))
    doc, rep = gp.sanitize(src, REF)
    assert rep["suprimidas_complementarias"] >= 1 and gp.check(doc, REF) == []
    assert [r["problema"] for r in doc["por_problema_nacional"]["filas"]] == [8]


def test_check_flags_a_hidden_region_that_is_the_only_candidate():
    doc = _src([R(familia="otros", casos=100, facturado=1000)], [R(problema=18, familia="otros", casos=100, facturado=1000)],
               pr_rows=[R(problema=18, region="13", casos=60, facturado=600), R(problema=18, region="5", casos=20, facturado=200),
                        R(problema=7, region="8", casos=20, facturado=200)])
    doc["version_publicable"] = gp.PUBLIC_VERSION
    f = gp.check(doc, REF)
    # problem 18 hides 200 in a single candidate region (8); problem 7 shows a region while its national row is hidden
    assert "single_candidate:problema<-region:18" in f and "region_row_of_hidden_problem:7:8" in f


def _regions_case():
    """Replica of the PR #165 review finding: the sanitizer hides one two-provider region of problem 75; the
    pseudo-region "0" shows a single row elsewhere and must not count as a place for the remainder."""
    probs = [R(problema=p, familia="salud_mental", casos=200, facturado=2000) for p in (15, 34, 75)]
    regs = []
    for p in (15, 34, 75):
        regs += [R(problema=p, region="13", casos=100, facturado=1000), R(problema=p, region="5", casos=40, facturado=400),
                 R(problema=p, region="8", casos=30, facturado=300),
                 R(problema=p, region="9", casos=30, facturado=300, n_prestadores=2 if p == 75 else 5)]
    regs.append(R(problema=15, region="0", casos=10, facturado=1))
    probs[0]["facturado"] += 1
    fam = [R(familia="salud_mental", casos=600, facturado=sum(r["facturado"] for r in probs))]
    return _src(fam, probs, pr_rows=regs)


def test_check_does_not_count_a_near_empty_pseudo_region_as_cover():
    doc = copy.deepcopy(_regions_case())
    doc["por_problema_region"]["filas"] = [r for r in doc["por_problema_region"]["filas"] if r["n_prestadores"] >= 3]
    doc["version_publicable"] = gp.PUBLIC_VERSION
    # the old check saw two candidates ("9" and "0"); "0" has one shown row, so the remainder is attributable to "9"
    assert "single_candidate:problema<-region:75" in gp.check(doc, REF)


def test_sanitize_hides_a_second_cell_wherever_it_hides_one_itself():
    src = _regions_case()
    doc, rep = gp.sanitize(src, REF)
    assert rep["suprimidas_por_prestadores"] == 1 and rep["suprimidas_complementarias"] >= 1 and gp.check(doc, REF) == []
    shown75 = {r["region"] for r in doc["por_problema_region"]["filas"] if r["problema"] == 75}
    assert len({"13", "5", "8", "9"} - shown75) >= 2


def test_sanitize_keeps_every_hidden_part_under_the_margin():
    # problem 3 (two providers) is 95% of what the sanitizer must hide: the next hidden cell must bring it under 90%
    probs = [R(problema=3, familia="cancer", casos=500, facturado=95_000, n_prestadores=2),
             R(problema=4, familia="cancer", casos=20, facturado=2_000), R(problema=8, familia="cancer", casos=300, facturado=30_000),
             R(problema=14, familia="cancer", casos=400, facturado=40_000)]
    src = _src([R(familia="cancer", casos=1220, facturado=167_000)], probs)
    doc, _ = gp.sanitize(src, REF)
    shown = {r["problema"] for r in doc["por_problema_nacional"]["filas"]}
    hidden = [r["facturado"] for r in probs if r["problema"] not in shown]
    assert len(hidden) >= 2 and max(hidden) / sum(hidden) < gp.MAX_SHARE and gp.check(doc, REF) == []


def test_published_totals_keep_only_the_allowed_keys():
    src = _src([R(familia="cancer", casos=100, facturado=1000)], [])
    src["totales"].update(filas_gpp_sin_id_ges=3, ges_sin_gpp={"filas": 2, "facturado": 50})
    doc, _ = gp.sanitize(src, REF)
    assert set(doc["totales"]) <= set(gp.TOTAL_KEYS) and gp.check(doc, REF) == []
    assert "total_key_not_allowed:ges_sin_gpp" in gp.check({**doc, "totales": src["totales"]}, REF)


def test_builder_holds_when_a_committed_file_leaks(root):
    def leak(d):
        d["por_problema_nacional"]["filas"].append({**d["por_problema_nacional"]["filas"][0], "problema": 99, "n_prestadores": 2})
    edit(root, "2026t3", leak)
    out = f14.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "hold" and any("privacy:2026t3:cell_under_3_providers" in e for e in out["errors"]), out["errors"]


# ---------------------------------------------------------------------------------------------------------------------
# HOLDs


@pytest.mark.parametrize("fn,reason", [
    (lambda d: d.update(sha256_zip="0" * 64), "aggregate_hash_mismatch:2026t3"),
    (lambda d: d.update(periodo="2026t2"), "aggregate_period_mismatch:2026t3"),
    (lambda d: d.update(filas_zip=1), "aggregate_rows_mismatch:2026t3"),
    (lambda d: d["totales"].update(facturado=d["totales"]["facturado"] + 10_000), "families_dont_add_to_total:2026t3"),
    (lambda d: d["totales"].update(pct_facturado_del_trimestre=1.0), "ges_share_mismatch:2026t3"),
    (lambda d: d["por_problema_nacional"]["filas"][0].update(nombre="otro nombre"), "problem_name_mismatch:2026t3"),
])
def test_f14_holds_on_mismatched_files(root, fn, reason):
    edit(root, "2026t3", fn)
    out = f14.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "hold" and any(reason in e for e in out["errors"]), out["errors"]


def test_f14_holds_on_a_receipt_outside_the_sis_host(root):
    edit(root, "2025t3", lambda d: d["archivo"].update(url="https://example.com/x.zip"), name="receipts_{q}.json")
    out = f14.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "hold" and any("source_not_sis_https:2025t3" in e for e in out["errors"])


def test_f14_holds_without_the_same_quarter_one_year_earlier(tmp_path):
    root = make_root(tmp_path, quarters=("2026t3",))
    out = f14.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "hold" and any("previous_year_missing:2025t3" in e for e in out["errors"]), out["errors"]


# ---------------------------------------------------------------------------------------------------------------------
# Publication gate, registry, runner


def test_first_publication_waits_for_review_and_shows_in_preview(root):
    reg = copy.deepcopy(sf.load_registry())
    assert reg["families"]["F14"]["first_pass_requires_review"] is True and reg["families"]["F14"]["first_review"]["reviewed_sha256"]  # recorded 10-nov-2026 under Dirección authorisation
    out = f14.run(root, today=TODAY, registry=reg, llm=False)
    assert out["status"] == "hold" and out["errors"] == [so.FIRST_REVIEW_HOLD]
    cand = out["candidate"]
    assert cand["status"] == "AWAITING_FIRST_REVIEW" and cand["verification"]["verdict"] == "PASS"
    ev = cand["review_request"]["evidence_sha256"]
    assert ev == so.evidence_sha256({s["key"]: s for s in cand["sources"]})
    assert not sf.publish(out, root)["published"]
    web = root / "web/data"
    assert rp.write(root, web) == ["f14_ges_patologia"]
    reg["families"]["F14"]["first_review"] = {"reviewed_by": "revisor de prueba", "reviewed_at": "2026-11-10", "reviewed_sha256": "0" * 64}
    assert f14.run(root, today=TODAY, registry=reg, llm=False)["status"] == "hold"
    reg["families"]["F14"]["first_review"]["reviewed_sha256"] = ev
    out = f14.run(root, today=TODAY, registry=reg, llm=False)
    assert out["status"] == "pass" and sf.publish(out, root)["published"]


def test_no_model_call_even_with_llm_requested(root):
    def model(*a, **k):
        raise AssertionError("model called")
    out = f14.run(root, today=TODAY, registry=reg_open(), llm=True, model_call=model, budget=lambda usd: (True, "ok"))
    assert out["status"] == "pass" and out["ficha"]["lectura"]["status"] == "not_attempted"


def test_registry_runner_and_datos_row(root):
    reg = sf.load_registry()
    cfg = reg["families"]["F14"]
    assert cfg["status"] == "active" and cfg["group"] == "aseguradores" and cfg["slug"] == "f14_ges_patologia"
    assert cfg["builder_version"] == f14.BUILDER_VERSION and cfg["lectura_enabled"] is False
    assert cfg["disclosure_rule"]["min_cases"] == gp.MIN_CASES == 10 and cfg["disclosure_rule"]["min_providers"] == gp.MIN_PROVIDERS == 3
    spec = importlib.util.spec_from_file_location("run_stats_fichas", SCRIPTS / "run_stats_fichas.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    assert runner.BUILDERS["F14"] is f14.run and "F14" not in runner.CAPTURED | runner.FEFI_CAPTURED | runner.DIPRES_CAPTURED
    fi = f14.run(root, today=TODAY, registry=reg_open(), llm=False)["ficha"]
    row = next(r for r in di.build([sf.ficha_card(fi, cfg)], root=root)["families"] if r["family"] == "F14")
    assert row["state"] == "live" and row["source"] == "SIS" and row["period_label"] == "jul–sep 2026"
    assert [x["id"] for x in row["kpis"]] == cfg["datos_kpis"]


# ---------------------------------------------------------------------------------------------------------------------
# Committed aggregates (real SIS data aggregated in Actions): assert the rules, not the counts (PLAYBOOK §4).


def _real():
    return f14.quarters(REPO)


@pytest.mark.skipif(not _real(), reason="no committed GES aggregates")
def test_committed_ges_files_pass_the_leak_check_and_name_their_sources():
    for q in _real():
        folder = REPO / f14.ROOT_DIR / q
        d = json.loads((folder / f"ges_gpp_publicable_{q}.json").read_text(encoding="utf-8"))
        rec = json.loads((folder / f"receipts_{q}.json").read_text(encoding="utf-8"))
        assert gp.check(d, REF) == [], q
        assert d["sha256_zip"] == rec["archivo"]["sha256"] and d["filas_zip"] == rec["archivo"]["parse"]["rows_ok"]
        assert sf.HEX64.fullmatch(d["fuente_agregada"]["sha256"])
        assert not (folder / f"ges_gpp_{q}.json").exists()  # the unsanitized backfill file is never committed here


@pytest.mark.skipif(not _real(), reason="no committed GES aggregates")
@pytest.mark.parametrize("q,p", [("2021t1", 75), ("2021t1", 76), ("2021t4", 21), ("2021t4", 76), ("2022t2", 76), ("2022t3", 76)])
def test_review_cells_are_no_longer_recoverable_from_the_regions(q, p):
    # PR #165 review: these two-provider regional cells equalled problem total − published regions
    d = json.loads((REPO / f14.ROOT_DIR / q / f"ges_gpp_publicable_{q}.json").read_text(encoding="utf-8"))
    nat = {r["problema"]: r for r in d["por_problema_nacional"]["filas"]}
    regs = [r for r in d["por_problema_region"]["filas"] if r["problema"] == p]
    assert set(d["totales"]) <= set(gp.TOTAL_KEYS)
    if p not in nat:
        assert regs == []
        return
    rest = nat[p]["facturado"] - sum(r["facturado"] for r in regs)
    count = {}
    for r in d["por_problema_region"]["filas"]:
        count[r["region"]] = count.get(r["region"], 0) + 1
    cover = {x for x, n in count.items() if n >= gp.COVER_MIN_ROWS} - {r["region"] for r in regs}
    assert rest <= len(regs) + 1 or len(cover) >= 2, (q, p, rest, cover)


@pytest.mark.skipif(not _real(), reason="no committed GES aggregates")
def test_committed_aggregates_reconcile_and_verify():
    reg = copy.deepcopy(sf.load_registry())
    p = f14.build_package(REPO, reg)
    assert p["reconciliation"]["ok"], p["reconciliation"]["failures"]
    fi = f14.compose(p, reg, today=TODAY, decision={"triggers": ["new_period"]})
    ver = sf.verify_ficha(fi, p)
    assert ver["verdict"] == "PASS", ver["errors"]


NEW_FILES = ["src/radar_salud/stats_ficha_f14.py", "src/radar_salud/ges_privacy.py", "scripts/sis_historico_ges.py",
             "scripts/ges_f14_publicable.py", "scripts/run_stats_fichas.py"]


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
# GES part of the historical backfill (brought over from tests/test_sis_historico.py)


@pytest.mark.parametrize("gpp,expected", [("21T1", (21, "T")), ("7t6", (7, "T")), ("34T8", (34, "T")),
                                          ("1T29", (1, "T")), ("88D1", (88, "D")), ("X", None), ("", None),
                                          ("T21", None), ("21-T1", None), ("2101", None)])
def test_gpp_prefix_parsing(gpp, expected):
    assert ges.parse_gpp(gpp) == expected


def test_ges_reference_covers_90_problems_and_families_partition():
    ref = ges.load_ges_reference()
    assert sorted(ref["names"]) == list(range(1, 91))
    assert set(ref["family"]) == set(range(1, 91))
    assert ref["family"][7] == "cardiometabolico" and ref["family"][34] == "salud_mental"
    assert ref["family"][8] == "cancer" and ref["family"][61] == "respiratorio"
    assert set(REF["verificacion"]["contrastados_sin_diferencias"]) <= set(range(1, 91))


def ges_rows(problem, isapre, region, n_cases, rows_per_case=1, providers=3):
    return [row(isapre=isapre, region=region, gpp=f"{problem}T1", id_ges=f"ENCGES{isapre}{region}{c}", prov=f"ENCPROV{c % providers}")
            for c in range(n_cases) for _ in range(rows_per_case)]


def feed(rows):
    a = ges.GesAgg()
    for f in rows:
        a.add(f)
    return a


def test_ges_min_cell_and_complementary_suppression():
    rows = ges_rows(21, "67", "13", 12) + ges_rows(21, "99", "13", 15) + ges_rows(21, "107", "5", 4)
    t = feed(rows).ges_tables(ges.load_ges_reference())
    nat = t["por_problema_nacional"]["filas"]
    assert nat[0]["problema"] == 21 and nat[0]["casos"] == 31 and nat[0]["familia"] == "cardiometabolico"
    isa = {r["isapre"]: r for r in t["por_problema_isapre"]["filas"]}
    assert "107" not in isa and "67" not in isa and isa["99"]["casos"] == 15
    assert t["por_problema_isapre"]["celdas_suprimidas"] == 2


def test_ges_cases_are_distinct_ids_and_counted_per_isapre():
    t = feed(ges_rows(34, "67", "13", 10, rows_per_case=3)).ges_tables(ges.load_ges_reference())
    r = t["por_problema_nacional"]["filas"][0]
    assert r["casos"] == 10 and r["frecuencia"] == 30


def test_ges_without_gpp_is_reported_apart():
    t = feed([row(cobertura="GES", gpp="X")] * 3).ges_tables(ges.load_ges_reference())
    assert t["totales"]["ges_sin_gpp"]["filas"] == 3 and t["por_problema_nacional"]["filas"] == []


def test_run_quarter_writes_only_publishable_tables_and_no_encrypted_ids(tmp_path):
    rows = ges_rows(21, "67", "13", 30) + ges_rows(21, "99", "13", 30) + ges_rows(7, "67", "13", 25, providers=2)
    z = zipped(tmp_path / "z.zip", rows)
    rec = ges.run_quarter("2026t3", tmp_path / "out", z)
    assert rec["estado"] == "ok" and rec["archivos_escritos"] == ["ges_gpp_publicable_2026t3.json"]
    d = json.loads((tmp_path / "out/2026t3/ges_gpp_publicable_2026t3.json").read_text())
    assert gp.check(d, REF) == [] and d["sha256_zip"] == rec["archivo"]["sha256"]
    assert 7 not in {r["problema"] for r in d["por_problema_nacional"]["filas"]}  # 2 providers: never shown
    for p in (tmp_path / "out").rglob("*.json"):
        assert SECRET not in p.read_text(encoding="utf-8"), p.name


def test_publicable_conversion_names_the_source_hash(tmp_path):
    src = tmp_path / "src" / "2026t3"
    src.mkdir(parents=True)
    t = feed(ges_rows(21, "67", "13", 30) + ges_rows(21, "99", "13", 30)).ges_tables(ges.load_ges_reference())
    (src / "ges_gpp_2026t3.json").write_text(json.dumps({"periodo": "2026t3", "script_version": "sis_historico_v3", **t}))
    (src / "receipts_2026t3.json").write_text(json.dumps({"periodo": "2026t3", "archivo": {"sha256": "a" * 64, "parse": {"rows_ok": 60}}}))
    pub.main(["--source", str(tmp_path / "src"), "--out", str(tmp_path / "out")])
    d = json.loads((tmp_path / "out/2026t3/ges_gpp_publicable_2026t3.json").read_text())
    import hashlib
    assert d["fuente_agregada"]["sha256"] == hashlib.sha256((src / "ges_gpp_2026t3.json").read_bytes()).hexdigest()
    assert (tmp_path / "out/2026t3/receipts_2026t3.json").read_bytes() == (src / "receipts_2026t3.json").read_bytes()
