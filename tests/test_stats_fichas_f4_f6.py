"""F4 (GES) and F6 (Boletín IP) statistics fichas: formulas, denominators, HOLD, Lectura scope, rendering data.

No network and no model calls: downloads are a fixture ``fetch`` and the Lectura model is a fake.
Every KPI is recomputed here from the fixture inputs, independently of the builders.
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import stats_ficha_fixtures as fx  # noqa: E402
from radar_salud import stats_capture as cap  # noqa: E402
from radar_salud import stats_ficha_f4 as f4, stats_ficha_f6 as f6, stats_fichas as sf  # noqa: E402

REPO = fx.REPO
TODAY = date(2026, 10, 29)
ALLOW = lambda worst: (True, "ok")  # noqa: E731


@pytest.fixture(autouse=True)
def isolated_ledgers(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_ROOT", str(tmp_path / "ledger-root"))


@pytest.fixture
def root(tmp_path):
    r = fx.make_root(tmp_path / "root")
    fx.capture_all(r, fx.fetcher(r))
    return r


def reg():
    return sf.load_registry()


def fake_model(text, review="PASS"):
    calls = []

    def call(prompt, **kw):
        calls.append({"prompt": prompt, **kw})
        if str(kw.get("feature", "")).endswith("_review"):
            return SimpleNamespace(output={"verdict": review, "claim": ""}, model="fake", estimated_cost_usd=0.0001, response_id="rv")
        return SimpleNamespace(output={"lectura": text}, model="fake", estimated_cost_usd=0.0004, response_id="r")
    call.calls = calls
    return call


def ytd(period):
    rows = fx.GES_CUTS[period]
    return sum(f for f, _ in rows.values()), sum(i for _, i in rows.values())


# ---------------------------------------------------------------------------------------------
# F4 · formulas and denominators, recomputed here


def test_f4_quarter_flows_yoy_share_and_rate_recomputed(root):
    p = f4.build_package(root, reg())
    assert p["reconciliation"]["ok"], p["reconciliation"]
    v = {k: e["value"] for k, e in p["values"].items()}
    # Quarter = YTD(jun) − YTD(mar) of the same year; Q1 = the March cut. Never a sum of cuts.
    (f26j, i26j), (f26m, i26m), (f25j, i25j), (f25m, i25m) = (ytd(x) for x in ("2026-06", "2026-03", "2025-06", "2025-03"))
    assert (v["ges.q.2026T2.fonasa"], v["ges.q.2026T2.isapre"]) == (f26j - f26m, i26j - i26m) == (44250, 6265)
    assert (v["ges.q.2025T2.fonasa"], v["ges.q.2025T2.isapre"]) == (f25j - f25m, i25j - i25m) == (39550, 5330)
    assert (v["ges.q.2026T1.fonasa"], v["ges.q.2026T1.isapre"]) == (f26m, i26m)
    tot, base = 44250 + 6265, 39550 + 5330
    assert v["ges.q.2026T2.total"] == tot and v["ges.yoy.total"] == tot - base
    assert v["ges.yoy.total_pct"] == pytest.approx((tot - base) / base * 100)  # 12,56 %
    assert v["ges.yoy.fonasa_pct"] == pytest.approx((44250 - 39550) / 39550 * 100)
    assert v["ges.yoy.isapre_pct"] == pytest.approx((6265 - 5330) / 5330 * 100)
    # Isapre share: denominator = cases of both insurers in the same quarter.
    assert v["ges.q.2026T2.isapre_share"] == pytest.approx(6265 / tot * 100)
    # Rate: Isapre cases / mean of the Isapre month-end stocks of April–June (F1) × 1.000.
    port = json.loads((root / "data/market/isapre_portfolio.json").read_text(encoding="utf-8"))
    stocks = {c["period"]: c["total_beneficiaries"] for c in port["coverage"]}
    avg = sum(stocks[m] for m in ("2026-04", "2026-05", "2026-06")) / 3
    assert v["benef.isapre.avg.2026T2"] == pytest.approx(avg)
    assert v["ges.q.2026T2.isapre_rate"] == pytest.approx(6265 / avg * 1000)
    assert "ges.q.2025T2.isapre_rate" not in v  # 2025 Isapre stocks are not captured: no rate, no estimate
    assert not any("fonasa_rate" in k or "benef.fonasa" in k for k in v)  # Fonasa beneficiaries never invented


def test_f4_top_problems_threshold_and_decree_change(root):
    p = f4.build_package(root, reg())
    k, v = p["kpis"], p["values"]
    q = lambda per, lab: sum(fx.GES_CUTS[per][lab]) - (sum(fx.GES_CUTS[per.replace("-06", "-03")][lab]))  # noqa: E731
    growth = {}
    for lab in fx.GES_CUTS["2026-06"]:
        if lab in fx.GES_CUTS["2025-06"] and q("2025-06", lab) >= 500:
            growth[lab] = round((q("2026-06", lab) - q("2025-06", lab)) / q("2025-06", lab) * 100, 1)
    assert {r["label"]: r["pct"] for r in k["ranked"]} == growth
    crossing = {lab for lab, g in growth.items() if g >= 15}
    assert {r["label"] for r in k["crossing"]} == crossing == {"Cáncer de mama en personas de 15 años y más",
                                                                "Depresión en personas de 15 años y más"}
    # Decree change: a problem without base and one that disappeared are flagged and kept out of the ranking.
    assert [*k["added"]] == [f4.slug("Problema nuevo de prueba")] and [*k["dropped"]] == [f4.slug("Problema retirado de prueba")]
    assert "Problema nuevo de prueba" not in {r["label"] for r in k["ranked"]}
    comp_t = sum(q("2026-06", lab) for lab in fx.GES_CUTS["2026-06"] if lab in fx.GES_CUTS["2025-06"])
    comp_b = sum(q("2025-06", lab) for lab in fx.GES_CUTS["2025-06"] if lab in fx.GES_CUTS["2026-06"])
    assert v["ges.yoy.total_comparable_pct"]["value"] == pytest.approx((comp_t - comp_b) / comp_b * 100)
    ficha = f4.compose(p, reg(), today=TODAY)
    tab = next(t for t in ficha["tabs"] if t["id"] == "problemas")
    assert any("posible cambio de decreto GES" in x for x in tab["text"])
    assert "+10,8% solo problemas comparables" in ficha["kpis"][0]["lines"]


def test_f4_ficha_publishes_with_tabs_kpis_and_tasa_bruta(root):
    out = f4.run(root, today=TODAY, registry=reg(), llm=False)
    assert out["status"] == "pass", out.get("errors")
    fi = out["ficha"]
    assert [t["label"] for t in fi["tabs"]] == ["Totales", "Top problemas", "Fonasa vs Isapre", "Tendencia trimestral"]
    assert fi["headline"] == "Casos GES del segundo trimestre de 2026: 50.515, +12,6% frente al mismo trimestre del año anterior"
    assert [k["label"] for k in fi["kpis"]] == ["Casos GES", "Fonasa", "Isapres", "Tasa bruta Isapre"]
    assert "tasa no disponible" in " ".join(fi["kpis"][1]["lines"])
    assert fi["featured"] is True and "threshold_crossed" in fi["triggers"]  # |a/a| ≥ 5 %
    assert fi["verification"]["verdict"] == "PASS" and fi["reconciliation"]["ok"]
    assert all(s["sha256"] and s["url"].startswith("https://") for s in fi["sources"])
    assert "tasa bruta" in json.dumps(fi, ensure_ascii=False).lower()
    assert not any(t.get("id") == "por_que" or "Por qué importa" in t.get("label", "") for t in fi["tabs"])
    written = sf.publish(out, root)
    assert written["published"] and sf.load_live(root, "f4_ges")["status"] == "PASS"


def test_f4_chart_headline_count_is_derived_from_data(root):
    p = f4.build_package(root, reg())
    fi = f4.compose(p, reg(), today=TODAY)
    top = next(c for t in fi["tabs"] for c in t["charts"] if c["id"] == "f4-top")
    n = next(r["value"] for r in p["derived_ratios"] if r["id"] == "conteo.problemas_sobre_umbral")
    assert n == 2 and top["headline"].startswith("Dos problemas superan")
    assert sf.lens_checks(fi, p)["data"] == []
    top["headline"] = "Tres problemas superan 15% a/a"
    assert "chart_headline_count_not_in_evidence:f4-top:tres" in " ".join(sf.lens_checks(fi, p)["data"])


@pytest.mark.parametrize("case", ["total_mismatch", "measure_unconfirmed", "ytd_decreases", "sheet_not_pinned", "offline"])
def test_f4_holds_and_never_publishes(tmp_path, case):
    r = fx.make_root(tmp_path / "r")
    url = fx.GES_URL.format(period="2026-06")
    books, fail = {}, set()
    if case == "total_mismatch":
        books[url] = fx.ges_workbook("2026-06", fx.GES_CUTS["2026-06"], total_delta=(1, 0))
    elif case == "measure_unconfirmed":
        books[url] = fx.ges_workbook("2026-06", fx.GES_CUTS["2026-06"], header="casos")
    elif case == "ytd_decreases":
        rows = dict(fx.GES_CUTS["2026-06"])
        rows["Diabetes Mellitus Tipo 2"] = (100, 10)  # lower than the March cut of the same year
        books[url] = fx.ges_workbook("2026-06", rows)
    elif case == "sheet_not_pinned":
        books[url] = fx.ges_workbook("2026-06", fx.GES_CUTS["2026-06"], extra=("Año 2005", "Resumen 2026"))
    else:
        fail.add(url)
    fx.capture_all(r, fx.fetcher(r, books, fail=fail))
    out = f4.run(r, today=TODAY, registry=reg(), llm=False)
    assert out["status"] == "hold"
    joined = " ".join(out["errors"])
    expected = {"total_mismatch": "HOLD_GES_RECONCILIATION", "measure_unconfirmed": "measure_unconfirmed",
                "ytd_decreases": "ytd_row_decreases:2026-06", "sheet_not_pinned": "HOLD_GES_SHEET_NOT_PINNED",
                "offline": "fetch_failed"}[case]
    assert expected in joined and "HOLD_RECONCILIATION" in joined
    written = sf.publish(out, r)
    assert not written["published"] and Path(written["hold"]).exists() and sf.load_live(r, "f4_ges") is None


def test_f4_reviewer_confirmed_measure_publishes_unlabelled_header(tmp_path):
    r = fx.make_root(tmp_path / "r")
    books = {fx.GES_URL.format(period=p): fx.ges_workbook(p, rows, header="casos") for p, rows in fx.GES_CUTS.items()}
    fx.capture_all(r, fx.fetcher(r, books))
    registry = reg()
    assert f4.run(r, today=TODAY, registry=registry, llm=False)["status"] == "hold"
    registry["families"]["F4"]["measure"].update(confirmed=True, confirmed_by="revisor de prueba")
    out = f4.run(r, today=TODAY, registry=registry, llm=False)
    assert out["status"] == "pass" and "revisor de prueba" in json.dumps(f4.build_package(r, registry)["kpis"]["measure_how"])


def test_f4_without_yoy_or_beneficiaries_says_not_available(tmp_path):
    r = fx.make_root(tmp_path / "r")
    hist = json.loads((r / fx.INPUTS[2]).read_text(encoding="utf-8"))  # no base year captured
    hist["signals"] = [s for s in hist["signals"] if "fixture-ges-2025" not in str(s.get("source_url"))]
    (r / fx.INPUTS[2]).write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    port = json.loads((r / "data/market/isapre_portfolio.json").read_text(encoding="utf-8"))
    port["coverage"] = [c for c in port["coverage"] if c["period"] not in ("2026-05",)]
    (r / "data/market/isapre_portfolio.json").write_text(json.dumps(port), encoding="utf-8")
    fx.capture_all(r, fx.fetcher(r))
    out = f4.run(r, today=TODAY, registry=reg(), llm=False)
    assert out["status"] == "pass", out.get("errors")
    fi = out["ficha"]
    assert fi["headline_type"] == "no_yoy" and "a/a no disponible" in fi["kpis"][0]["lines"]
    assert fi["kpis"][3]["value"] == "no disponible" and "ges.q.2026T2.isapre_rate" not in out["ficha"]["evidence"]["values"]


# ---------------------------------------------------------------------------------------------
# F4 · Lectura: scope, period and base


def test_f4_lectura_pool_declares_scope_period_and_base(root):
    p = f4.build_package(root, reg())
    for e in p["lectura_pool"]:
        assert e["scope"] in ("system", "isapres", "insurer:fonasa"), e
        assert e["period_kind"] in ("quarter", "quarter_yoy"), e
        if e["unit"] in ("%", "pp", "per_1000"):
            assert e["base"], e
    by = {e["id"]: e for e in p["lectura_pool"]}
    assert by["ges.q.2026T2.isapre_rate"]["base"] == "beneficiarios_mismo_seguro"
    assert by["ges.q.2026T2.isapre_share"]["base"] == "casos_ambos_seguros"
    assert by["ges.q.2026T2.fonasa"]["scope"] == "insurer:fonasa" and by["ges.q.2026T2.isapre"]["scope"] == "isapres"


F4_GOOD = "Para las aseguradoras, la carga GES de Fonasa equivale a 7,1 veces la de las Isapres en el segundo trimestre de 2026."


@pytest.mark.parametrize("text,error", [
    (F4_GOOD, None),
    ("Para las aseguradoras, las Isapres informaron 44.250 casos en el segundo trimestre de 2026.", "number_entity_mismatch"),
    ("Para las aseguradoras, la carga GES de Fonasa equivale a 7,1 veces la de las Isapres en junio.", "number_period_mismatch"),
    ("Para las Isapres, su tasa bruta fue 2,5 casos por cada mil personas en el segundo trimestre de 2026.", "share_base_unstated"),
    ("Para el regulador, las Isapres crecieron 17,5% en el segundo trimestre de 2026.", "number_period_mismatch"),
    ("Para la competencia entre aseguradoras, la demanda Isapre aumentó en 935 casos frente al mismo trimestre de 2025, ya en "
     "el segundo trimestre.", None),
    ("Para el regulador, en el segundo trimestre las Isapres sumaron 935 casos más que en 2025.", "number_period_mismatch"),
    ("Para el regulador, Fonasa sumó 935 casos más que un año antes en el segundo trimestre.", "number_entity_mismatch"),
    ("Para el regulador, Banmédica informó 7,1 veces los casos en el segundo trimestre de 2026.", "insurer_not_in_package"),
])
def test_f4_verifier_checks_scope_period_and_base(root, text, error):
    p = f4.build_package(root, reg())
    fi = f4.compose(p, reg(), today=TODAY)
    res = sf.verify_lectura(text, p, ficha=fi)
    if error is None:
        assert res["verdict"] == "PASS", res
    else:
        assert res["verdict"] == "FAIL" and any(error in e for e in res["errors"]), res


def test_f4_good_lectura_publishes_end_to_end_with_review_and_no_real_model(root):
    model = fake_model(F4_GOOD)
    out = f4.run(root, today=TODAY, registry=reg(), llm=True, model_call=model, budget=ALLOW)
    lect = out["ficha"]["lectura"]
    assert lect["status"] == "pass" and lect["text"] == F4_GOOD and lect["review"]["verdict"] == "PASS"
    assert [c["feature"] for c in model.calls] == ["stats_ficha_lectura", "stats_ficha_lectura_review"]
    # A Lectura with an untraceable figure is dropped; the reviewer is never paid and the ficha still publishes.
    r2 = fx.make_root(root.parent / "r2")
    fx.capture_all(r2, fx.fetcher(r2))
    bad = fake_model("Para las aseguradoras, Fonasa atendió 9 veces los casos de las Isapres en el segundo trimestre de 2026.")
    out2 = f4.run(r2, today=TODAY, registry=reg(), llm=True, model_call=bad, budget=ALLOW)
    assert out2["status"] == "pass" and out2["ficha"]["lectura"]["status"] == "verifier_fail"
    assert [c["feature"] for c in bad.calls] == ["stats_ficha_lectura"]
    # No budget: no call at all, Lectura omitted.
    r3 = fx.make_root(root.parent / "r3")
    fx.capture_all(r3, fx.fetcher(r3))
    none = fake_model(F4_GOOD)
    out3 = f4.run(r3, today=TODAY, registry=reg(), llm=True, model_call=none, budget=lambda w: (False, "no_capacity"))
    assert out3["ficha"]["lectura"]["status"] == "no_budget" and none.calls == []


# ---------------------------------------------------------------------------------------------
# F6 · Boletín IP


def verified():
    cfg = json.loads((REPO / "config/statistical_analysis_verified_v1.json").read_text(encoding="utf-8"))
    return {d["url"].rsplit("-", 4)[0].rsplit("/", 1)[-1]: d["verified_metrics"] for d in cfg["primary_review"]["documents"]}


def test_f6_figures_and_denominators_recomputed(root):
    p = f6.build_package(root, reg())
    assert p["reconciliation"]["ok"], p["reconciliation"]
    v = {k: e["value"] for k, e in p["values"].items()}
    cfg = json.loads((REPO / "config/statistical_analysis_verified_v1.json").read_text(encoding="utf-8"))
    m = {k: val for d in cfg["primary_review"]["documents"] for k, val in d["verified_metrics"].items()}
    assert v["acr.acreditados"] == m["accredited_providers"] == 971
    assert v["acr.sin_observaciones"] == 971 - 101 == 870
    assert v["acr.observaciones_pct"] == pytest.approx(101 / 971 * 100)  # denominator: accredited
    assert v["acr.tramite.privadas"] + v["acr.tramite.publicas"] == v["acr.tramite"] == 584
    assert v["acr.privadas_pct"] == pytest.approx(367 / 584 * 100)  # denominator: applications in process
    assert v["rec.pct"] == pytest.approx((1996 - 1530) / 1530 * 100) and round(v["rec.pct"]) == m["reported_growth_percent_rounded"]
    assert v["rnpi.titulos"] == 1004982 and v["med.mediadores"] == 175 and v["med.solicitudes_acumuladas"] == 12067
    # Stocks are never summed across releases: no derived value adds two cuts.
    assert not any("Σ" in str(e.get("formula") or "") for e in p["values"].values())
    assert p["kpis"]["comparisons"] == {}  # only one verified release: quarter-on-quarter stays pending


def test_f6_ficha_tabs_and_rejected_release(root):
    out = f6.run(root, today=TODAY, registry=reg(), llm=False)
    assert out["status"] == "pass", out.get("errors")
    fi = out["ficha"]
    assert [t["label"] for t in fi["tabs"]] == ["Acreditación", "Mediación", "Reclamos", "RNPI"]
    assert fi["headline"] == "Boletín IP a junio 2026: 971 prestadores acreditados y 584 solicitudes de acreditación en trámite"
    assert any("no profesionales únicos" in x for x in next(t for t in fi["tabs"] if t["id"] == "rnpi")["text"])
    # The 'Septiembre 2026' page links the January–June PDFs: rejected, never relabelled.
    store = json.loads((root / "data/stats_fichas/captures/boletin_ip.json").read_text(encoding="utf-8"))
    rej = store["rejected_releases"]
    assert rej and rej[0]["title"].endswith("Septiembre 2026") and "documents_belong_to_other_release" in rej[0]["reasons"]
    assert fi["watch"][0]["headline"].startswith("Septiembre 2026")
    assert all(d["format"] == "pdf" for r in store["releases"] for d in r["documents"] if d.get("status") == "captured")


def test_f6_quarter_on_quarter_compares_stocks_between_two_verified_releases(root):
    cfgp = root / "config/statistical_analysis_verified_v1.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    n1 = {"acreditacion": {"accredited_providers": 950, "with_observations": 99, "pending_applications": 600,
                           "private_pending": 380, "public_pending": 220},
          "mediacion": {"registered_mediators": 170}, "reclamos": {"monthly_average_2026": 1900},
          "rnpi": {"registered_titles": 990000}}
    store = json.loads((root / "data/stats_fichas/captures/boletin_ip.json").read_text(encoding="utf-8"))
    rel = next(r for r in store["releases"] if r["period"] == "2026-03")
    for d in rel["documents"]:
        cfg["primary_review"]["documents"].append({"url": d["url"], "pages_1based": [1], "verified_metrics": n1[d["topic"]]})
    cfgp.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    for d in rel["documents"]:  # re-capture N°1-2026 with the new verified figures
        d.clear()
    (root / "data/stats_fichas/captures/boletin_ip.json").write_text(json.dumps(
        {**store, "releases": [r for r in store["releases"] if r["period"] != "2026-03"]}), encoding="utf-8")
    fx.capture_all(root, fx.fetcher(root))
    p = f6.build_package(root, reg())
    assert p["reconciliation"]["ok"], p["reconciliation"]
    c = p["kpis"]["comparisons"]
    assert c["acr.acreditados"] == 971 - 950 and c["acr.tramite"] == 584 - 600 and c["rnpi.titulos"] == 1004982 - 990000
    fi = f6.compose(p, reg(), today=TODAY)
    assert "+21 vs. marzo 2026" in fi["kpis"][0]["lines"]


@pytest.mark.parametrize("case", ["figure_missing", "sum_mismatch", "offline"])
def test_f6_holds(tmp_path, case):
    r = fx.make_root(tmp_path / "r")
    books, fail = {}, set()
    acc = "https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf"
    if case == "figure_missing":
        books[acc] = fx.pdf_with_text(["accredited_providers: 970", "with_observations: 101", "pending_applications: 584",
                                       "private_pending: 367", "public_pending: 217"])
    elif case == "sum_mismatch":
        cfgp = r / "config/statistical_analysis_verified_v1.json"
        cfg = json.loads(cfgp.read_text(encoding="utf-8"))
        cfg["primary_review"]["documents"][0]["verified_metrics"]["private_pending"] = 368
        cfgp.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    else:
        fail.add(acc)
    fx.capture_all(r, fx.fetcher(r, books, fail=fail))
    out = f6.run(r, today=TODAY, registry=reg(), llm=False)
    assert out["status"] == "hold"
    expected = {"figure_missing": "verified_figure_not_in_document:acreditacion:accredited_providers",
                "sum_mismatch": "privadas_mas_publicas_distinto_de_tramite", "offline": "not_captured:acreditacion"}[case]
    assert expected in " ".join(out["errors"])
    assert not sf.publish(out, r)["published"]


F6_GOOD = "Para la competencia, las solicitudes privadas en trámite son 1,7 veces las públicas a junio de 2026."


@pytest.mark.parametrize("text,error", [
    (F6_GOOD, None),
    ("Para el regulador, el 10,4% del sistema tenía observaciones a junio de 2026.", "share_base"),
    ("Para el regulador, los públicos tenían 367 solicitudes a junio de 2026.", "number_entity_mismatch"),
    ("Para la superintendencia, la demanda de reclamos entre enero y junio de 2026 es 1,3 veces la de 2025.", None),
    ("Para la superintendencia, la demanda de reclamos en junio de 2026 es 1,3 veces la de 2025.", "number_period_mismatch"),
    ("Para la superintendencia, los reclamos subieron en 466 al mes entre enero y junio de 2026.", "restates_shown"),
])
def test_f6_verifier_checks_scope_period_and_base(root, text, error):
    p = f6.build_package(root, reg())
    fi = f6.compose(p, reg(), today=TODAY)
    for e in p["lectura_pool"]:
        assert e["scope"] in ("system", "private", "public") and e["period_kind"] in ("stock_at", "ytd", "interval")
        assert e["unit"] not in ("%", "pp") or e["base"]
    res = sf.verify_lectura(text, p, ficha=fi)
    if error is None:
        assert res["verdict"] == "PASS", res
    else:
        assert res["verdict"] == "FAIL" and any(error in e for e in res["errors"]), res


# ---------------------------------------------------------------------------------------------
# Capture, runner, registry, snapshot


def test_capture_downloads_once_and_stores_hashes_not_binaries(tmp_path):
    r = fx.make_root(tmp_path / "r")
    fetch = fx.fetcher(r)
    fx.capture_all(r, fetch)
    n = len(fetch.calls)
    assert n == len(fx.GES_CUTS) + 5 * 4  # 4 GES files + 5 Boletines × 4 PDFs (the mislabeled release is never fetched)
    fx.capture_all(r, fetch)
    assert len(fetch.calls) == n  # already captured: never downloaded again
    for name in ("ges_quarterly.json", "boletin_ip.json"):
        raw = (r / "data/stats_fichas/captures" / name).read_text(encoding="utf-8")
        assert len(raw) < 60_000 and "%PDF" not in raw and "PK\u0003" not in raw
    ges = json.loads((r / "data/stats_fichas/captures/ges_quarterly.json").read_text(encoding="utf-8"))
    assert all(len(x["document"]["sha256"]) == 64 and x["document"]["format"] == "xlsx" for x in ges["releases"])
    assert cap.file_format(b"%PDF-1.4") == "pdf" and cap.file_format(b"PK\x03\x04") == "xlsx"


def test_capture_retries_failed_downloads_a_bounded_number_of_times(tmp_path):
    r = fx.make_root(tmp_path / "r")
    url = fx.GES_URL.format(period="2026-06")
    fetch = fx.fetcher(r, fail={url})
    for _ in range(6):
        cap.capture(r, fetch=fetch)
    assert fetch.calls.count(url) == cap.MAX_ATTEMPTS


def test_runner_wires_f4_f6_capture_and_daily_workflow_needs_no_change(root, monkeypatch, capsys):
    sys.path.insert(0, str(REPO / "scripts"))
    import run_stats_fichas as runner
    seen = []
    monkeypatch.setattr(runner.stats_capture, "capture", lambda r: seen.append(r) or {"ok": True})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert runner.main(["--root", str(root), "--as-of", "2026-10-29", "--family", "F4", "--family", "F6"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert seen and summary["F4"]["status"] == "pass" and summary["F6"]["status"] == "pass"
    assert summary["F4"]["lectura"] == "not_attempted"  # no key: no model call
    assert runner.main(["--root", str(root), "--as-of", "2026-10-29", "--family", "F4", "--no-capture"]) == 0
    assert len(seen) == 1
    reg_ = reg()
    assert {f for f, c in reg_["families"].items() if c["status"] == "active"} == {"F1", "F4", "F6"}
    assert set(runner.BUILDERS) == {"F1", "F4", "F6"}
    # The daily workflow (main) runs the script without arguments and commits data/stats_fichas.
    wf = (REPO / ".github/workflows/daily-radar.yml").read_text(encoding="utf-8")
    assert "run: python scripts/run_stats_fichas.py\n" in wf and "git add data/stats_fichas" in wf
    main = subprocess.run(["git", "show", "origin/main:.github/workflows/daily-radar.yml"], cwd=REPO, capture_output=True, text=True)
    if main.returncode == 0:
        assert "run: python scripts/run_stats_fichas.py\n" in main.stdout


def test_registry_declares_f4_f6_rules():
    r = reg()
    a, b = r["families"]["F4"], r["families"]["F6"]
    assert a["builder_version"] == f4.BUILDER_VERSION and b["builder_version"] == f6.BUILDER_VERSION
    assert a["kpis"]["top_problemas"]["threshold"] == {"pct": 15.0, "min_cases": 500}
    assert "Beneficiarios del mismo seguro" in a["kpis"]["tasa_uso"]["denominator"]
    assert a["measure"]["confirmed"] is False  # never auto-confirmed
    assert a["supersedes"]["stat_families"] == ["ges"] and b["supersedes"]["stat_families"] == ["boletin_ip"]
    assert [t["label"] for t in a["tabs"]] == ["Totales", "Top problemas", "Fonasa vs Isapre", "Tendencia trimestral"]
    assert [t["label"] for t in b["tabs"]] == ["Acreditación", "Mediación", "Reclamos", "RNPI"]


def test_snapshot_ges_card_leaves_hold_only_when_f4_passes(root):
    hist = json.loads((REPO / "data/history/superintendencia_signals.json").read_text(encoding="utf-8"))["signals"]
    ges = [sf.sanitize_ges_signal(s) for s in hist if "casos ges" in cap._fold(s.get("title"))
           and s.get("source_name") == "Superintendencia de Salud"]
    assert any((s.get("statistical_view") or {}).get("publication_status") == "HOLD" for s in ges)
    cards = [{**s, "signal_types": s.get("signal_types") or ["Datos"]} for s in ges]
    # No PASS: no live F4 ficha, the loose GES cards stay as they are (in HOLD).
    assert sf.live_fichas(root) == [] or all(f["family"] != "F4" for f in sf.live_fichas(root))
    out = f4.run(root, today=TODAY, registry=reg(), llm=False)
    sf.publish(out, root)
    fichas = [f for f in sf.live_fichas(root) if f["family"] == "F4"]
    assert fichas and fichas[0]["status"] == "PASS"
    result = sf.apply_to_snapshot(cards, fichas)
    assert [c for c in result if c.get("stats_ficha")][0]["scopes"] == ["Isapres", "Fonasa"]
    left = [c for c in result if not c.get("stats_ficha")]
    assert all(sf.loose_card_period(c) > fichas[0]["period"] for c in left)  # only releases newer than the ficha stay


def test_committed_fixture_cards_match_the_builders(tmp_path):
    r = fx.make_root(tmp_path / "r")
    fx.capture_all(r, fx.fetcher(r))
    for fam, mod in (("F4", f4), ("F6", f6)):
        fi = mod.run(r, today=TODAY, registry=reg(), llm=False)["ficha"]
        card = json.loads((fx.FIXTURE_DIR / f"{reg()['families'][fam]['slug']}.card.json").read_text(encoding="utf-8"))
        for key in ("headline", "dek", "kpis", "tabs", "watch", "notes"):
            assert card["stats_ficha"][key] == json.loads(json.dumps(fi[key], ensure_ascii=False)), key
