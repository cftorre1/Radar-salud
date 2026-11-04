"""F4 (GES) and F6 (Boletín IP) statistics fichas: formulas, denominators, HOLD, Lectura scope, rendering data.

No network and no model calls: downloads are a fixture ``fetch`` and the Lectura model is a fake.
Every KPI is recomputed here from the fixture inputs, independently of the builders.
"""
import json
import re
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
    r = fx.make_root(tmp_path / "root", readings_until="2026-06")
    fx.capture_all(r, fx.fetcher(r))
    return r


def reg():
    return sf.load_registry()


def reg_ok():
    """F4 needs a reviewer-confirmed measure (registry F4.measure.confirmed); the committed registry never has it."""
    return fx.confirmed_registry()


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
    """(Fonasa, Isapre) year-to-date totals of the fixture (the SIS 'Ingresos entre Ene y …' column)."""
    rows = fx.GES_YTD[period]
    return sum(f for f, _ in rows.values()), sum(i for _, i in rows.values())


def cum_total(period, codes=None):
    """(Fonasa, Isapre) cumulative-since-July-2005 totals of the fixture at one cut (optionally over ``codes``)."""
    rows = fx.ges_cumulative(fx.GES_YTD)[period]
    codes = rows if codes is None else codes
    return sum(rows.get(c, (0, 0))[0] for c in codes), sum(rows.get(c, (0, 0))[1] for c in codes)


# ---------------------------------------------------------------------------------------------
# F4 · measure (Dirección 3-nov-2026: "Ene–jun vs ene–jun"), formulas and denominators, recomputed here


def test_f4_measure_is_confirmed_in_the_registry_and_never_holds_unconfirmed(root):
    m = reg()["families"]["F4"]["measure"]
    assert m["declared"] == "ytd" and m["confirmed"] is True and "Dirección" in m["confirmed_by"]
    assert "nunca acumulados desde 2005" in m["confirmed_by"]
    out = f4.run(root, today=TODAY, registry=reg(), llm=False)  # the committed registry, no test reviewer
    # Only the first-publication review gate holds it (no reconciliation or measure hold).
    assert out["status"] == "hold" and out["errors"] == [f4.FIRST_REVIEW_HOLD], out.get("errors")
    assert "measure_unconfirmed" not in json.dumps(out, ensure_ascii=False)
    ungated = reg()
    ungated["families"]["F4"]["first_pass_requires_review"] = False
    assert f4.run(root, today=TODAY, registry=ungated, llm=False)["status"] == "pass"
    assert "Dirección" in f4.build_package(root, reg())["kpis"]["measure_how"]
    # Without the confirmation the ficha HOLDs, whatever the header says.
    unconfirmed = reg()
    unconfirmed["families"]["F4"]["measure"].update(confirmed=False, confirmed_by=None)
    unconfirmed["families"]["F4"]["first_pass_requires_review"] = False
    held = f4.run(root, today=TODAY, registry=unconfirmed, llm=False)
    assert held["status"] == "hold" and "measure_unconfirmed" in " ".join(held["errors"])


def test_f4_year_to_date_yoy_share_and_rate_recomputed(root):
    p = f4.build_package(root, reg_ok())
    assert p["reconciliation"]["ok"], p["reconciliation"]
    v = {k: e["value"] for k, e in p["values"].items()}
    # Current year: the SIS year-to-date column (ene–jun 2026).
    (f26, i26) = ytd("2026-06")
    assert (v["ges.ytd.2026-06.fonasa"], v["ges.ytd.2026-06.isapre"]) == (f26, i26) == (85740, 12183)
    # Same months one year earlier, from the same workbook: cum(jun 2025) − cum(dic 2024) (since-2005 cuts).
    (cj, ij), (cd, id_) = cum_total("2025-06"), cum_total("2024-12")
    assert (v["ges.ytd.2025-06.fonasa"], v["ges.ytd.2025-06.isapre"]) == (cj - cd, ij - id_) == ytd("2025-06") == (76640, 10418)
    assert p["values"]["ges.ytd.2025-06.fonasa"]["inputs"] == ["ges.cut.2025-06.fonasa", "ges.cut.2024-12.fonasa"]
    tot, base = f26 + i26, 76640 + 10418
    assert v["ges.ytd.2026-06.total"] == tot and v["ges.yoy.total"] == tot - base
    assert v["ges.yoy.total_pct"] == pytest.approx((tot - base) / base * 100)  # 11,79 %
    assert v["ges.yoy.fonasa_pct"] == pytest.approx((85740 - 76640) / 76640 * 100)
    assert v["ges.yoy.isapre_pct"] == pytest.approx((12183 - 10418) / 10418 * 100)
    # Isapre share: denominator = cases of both insurers in the same months.
    assert v["ges.ytd.2026-06.isapre_share"] == pytest.approx(12183 / tot * 100)
    # Rate: Isapre cases / mean of the Isapre month-end stocks of January–June (F1) × 1.000.
    port = json.loads((root / "data/market/isapre_portfolio.json").read_text(encoding="utf-8"))
    stocks = {c["period"]: c["total_beneficiaries"] for c in port["coverage"]}
    avg = sum(stocks[f"2026-{m:02d}"] for m in range(1, 7)) / 6
    assert v["benef.isapre.avg.ytd.2026-06"] == pytest.approx(avg)
    assert v["ges.ytd.2026-06.isapre_rate"] == pytest.approx(12183 / avg * 1000)
    assert "ges.ytd.2025-06.isapre_rate" not in v  # 2025 Isapre stocks are not captured: no rate, no estimate
    assert not any("fonasa_rate" in k or "benef.fonasa" in k for k in v)  # Fonasa beneficiaries never invented


def test_f4_quarters_by_difference_and_q1_against_previous_december(root):
    p = f4.build_package(root, reg_ok())
    v = {k: e["value"] for k, e in p["values"].items()}
    codes26 = fx.GES_YTD["2026-06"].keys()
    for ins, i in (("fonasa", 0), ("isapre", 1)):
        # Q1 2026 = cum(mar 2026) − cum(dic 2025), never the March cumulative (since July 2005) alone. Problem 85
        # (new in 2026) enters with 0.
        q1 = cum_total("2026-03")[i] - cum_total("2025-12", codes26)[i]
        assert v[f"ges.q.2026T1.{ins}"] == q1 == ytd("2026-03")[i] and q1 != cum_total("2026-03")[i]
        assert p["values"][f"ges.q.2026T1.{ins}"]["inputs"] == [f"ges.cut.2026-03.{ins}", f"ges.cut.2025-12.{ins}"]
        assert v[f"ges.q.2026T2.{ins}"] == cum_total("2026-06")[i] - cum_total("2026-03")[i]
        # No list change between 2024 and 2025: the declared December total is the base.
        assert v[f"ges.q.2025T1.{ins}"] == cum_total("2025-03")[i] - cum_total("2024-12")[i]
        assert p["values"][f"ges.q.2025T1.{ins}"]["inputs"] == [f"ges.cut.2025-03.{ins}", f"ges.cut.2024-12.{ins}"]
        # The quarters of the year add up to its year-to-date column.
        assert v[f"ges.q.2026T1.{ins}"] + v[f"ges.q.2026T2.{ins}"] == ytd("2026-06")[i]
    assert p["kpis"]["quarter_cuts"]["2026T1"] == ["2025-12", "2026-03"]
    assert p["kpis"]["quarters"] == [(2025, 1), (2025, 2), (2025, 3), (2025, 4), (2026, 1), (2026, 2)]
    fi = f4.compose(p, reg_ok(), today=TODAY)
    trend = next(c for t in fi["tabs"] for c in t["charts"] if c["id"] == "f4-trend")
    assert ["T1 2026", fx_int(v["ges.q.2026T1.total"]), "mar 2026 − dic 2025"] in trend["table"]["rows"]


def fx_int(n):
    return sf.fmt_int(n)


def test_f4_ytd_reconciliation_identity_holds_on_receipt_figures_and_breaks_on_mismatch():
    """Figures copied from the SIS text receipt of the June 2026 workbook (sha256 5a84c70c…, problems 1–3):
    ingresos ene–jun 2026 = acumulado jun-2026 − acumulado dic-2025, per problem and in total, per insurer."""
    from radar_salud import ges_workbook as gw
    labels = {1: "Insuficiencia Renal Crónica Terminal", 2: "Cardiopatías Congénitas Operables", 3: "Cáncer Cérvicouterino"}
    cum = {"2024-12": {1: (89213, 6845), 2: (116966, 6556), 3: (9178671, 33254)},
           "2025-03": {1: (90929, 6991), 2: (118009, 6628), 3: (9384184, 34215)},
           "2025-06": {1: (92920, 7277), 2: (119208, 6791), 3: (9653018, 36126)},
           "2025-09": {1: (94862, 7388), 2: (120224, 6844), 3: (9907403, 37247)},
           "2025-12": {1: (96680, 7499), 2: (121248, 6900), 3: (10137845, 38295)},
           "2026-03": {1: (98443, 7598), 2: (122449, 6958), 3: (10341802, 39352)},
           "2026-06": {1: (99499, 7703), 2: (123542, 7010), 3: (10575182, 40458)}}
    ytd_cols = {"2025-12": {1: (7467, 654), 2: (4282, 344), 3: (959174, 5041)},
                "2026-06": {1: (2819, 204), 2: (2294, 110), 3: (437337, 2163)}}
    title = "Estadística Trimestral de Casos GES (AUGE) de Fonasa y Sistema ISAPRE – a junio 2026"
    book = fx.ges_workbook("2026-06", ytd_cols, cum=cum, first_year=2024, labels=labels)
    assert gw.parse(book, title)["hold_reason"] == "HOLD_GES_TOO_FEW_PROBLEMS"  # an excerpt is never a full GES table
    r = gw.parse(book, title, min_rows=3)  # the 3-problem excerpt, explicitly
    assert r["status"] == "validated", r
    p1 = gw.expand_sheet(r["years"]["2026"])["problems"]["1"]
    q1, q2 = 98443 - 96680, 99499 - 98443
    assert (q1, q2, q1 + q2) == (1763, 1056, 2819) == (p1["cut"]["2026-03"][0] - 96680, p1["cut"]["2026-06"][0] - p1["cut"]["2026-03"][0],
                                                        p1["ytd"]["2026-06"][0])
    assert r["header"]["ytd"] == "Ingresos entre Ene y Jun 2026"
    assert all("2005" in t for t in r["header"]["cuts"].values())  # the cuts are cumulative since July 2005
    # One problem's year-to-date figure off by one (its total too, so the rows still add up): HOLD, no figure.
    bad = gw.parse(fx.ges_workbook("2026-06", ytd_cols, cum=cum, first_year=2024, labels=labels, ytd_delta={1: (1, 0)}), title, min_rows=3)
    assert bad["status"] == "HOLD" and bad["hold_reason"] == "HOLD_GES_YTD_IDENTITY"
    assert "2026-06:ps1:fonasa" in bad["mismatches"] and "2026-06:total:fonasa" in bad["mismatches"]
    assert "years" not in bad and bad["insights"] == []


def test_f4_cumulative_since_2005_never_shown(root):
    out = f4.run(root, today=TODAY, registry=reg_ok(), llm=False)
    assert out["status"] == "pass", out.get("errors")
    fi, v = out["ficha"], out["ficha"]["evidence"]["values"]
    cums = {e["value"] for k, e in v.items() if k.startswith("ges.cut.")}
    totals = {e["value"] for k, e in v.items() if k.startswith("ges.cut.") and ".p." not in k}
    assert totals and min(totals) > 100_000  # the fixture's since-2005 totals are large, never confused with a flow
    # Every public key of the ficha (sf.PUBLIC_KEYS, revisions included) and the feed card built from it.
    shown = json.dumps([sf.public_ficha(fi), sf.ficha_card(fi, reg_ok()["families"]["F4"])], ensure_ascii=False)
    for n in cums:
        assert sf.fmt_int(n) not in shown and not re.search(rf"(?<![\d.]){int(n)}(?![\d])", shown), n
    # A cumulative input is never a showable number nor a revision.
    assert all(e["kind"] == f4.CUMULATIVE for k, e in v.items() if k.startswith("ges.cut."))
    p = f4.build_package(root, reg_ok())
    assert not set(cums) & set(sf.number_pool(p)) - {e["value"] for k, e in p["values"].items() if not k.startswith("ges.cut.")}
    # A previous live ficha whose cut values differ (e.g. built before this kind existed) yields no public revision.
    old = json.loads(json.dumps(fi))
    for k, e in old["evidence"]["values"].items():
        if k.startswith("ges.cut."):
            e.update(kind="captured", value=e["value"] + 7)
    p2 = f4.build_package(root, reg_ok(), {"evidence": old["evidence"]})
    assert not any(r["id"].startswith("ges.cut.") for r in p2["revisions"]) and not any(
        k.startswith("ges.cut.") and k.endswith(".previous") for k in p2["values"])
    head = json.dumps([fi["headline"], fi["dek"], fi["kpis"]], ensure_ascii=False)
    assert "2005" not in head and "acumulad" not in head.lower()
    # Every KPI and headline figure traces to a year-to-date or derived value, never to a cumulative cut.
    for k in fi["kpis"]:
        assert not any(r.startswith("ges.cut.") for r in k["refs"]), k
    # The period is explicit: January–June 2026 against January–June 2025.
    assert fi["headline"] == "Casos GES entre enero y junio de 2026: 97.923, +12,5% frente a enero–junio de 2025"
    assert "entre enero y junio de 2026" in fi["dek"]
    assert [k["label"] for k in fi["kpis"]] == ["Casos GES ene–jun 2026", "Fonasa ene–jun 2026", "Isapres ene–jun 2026",
                                                "Tasa bruta Isapre"]
    assert fi["kpis"][0]["lines"][0] == "+12,5% vs. ene–jun 2025"


def test_f4_top_problems_threshold_and_decree_change(root):
    p = f4.build_package(root, reg_ok())
    k, v = p["kpis"], p["values"]
    t, b = fx.GES_YTD["2026-06"], fx.GES_YTD["2025-06"]
    growth = {}
    for code in t:
        if code in b and sum(b[code]) >= 500:
            growth[fx.GES_LABELS[code]] = round((sum(t[code]) - sum(b[code])) / sum(b[code]) * 100, 1)
    assert {r["label"]: r["pct"] for r in k["ranked"]} == growth
    crossing = {lab for lab, g in growth.items() if g >= 15}
    assert {r["label"] for r in k["crossing"]} == crossing == {"Cáncer de mama en personas de 15 años y más",
                                                                "Depresión en personas de 15 años y más",
                                                                "Hipoacusia bilateral en personas de 65 años y más"}
    # Decree change: a problem without base and one that disappeared are flagged and kept out of the ranking.
    assert k["added"] == [f4.pkey(fx.NEW_CODE)] and k["dropped"] == []
    assert "Problema nuevo de prueba" not in {r["label"] for r in k["ranked"]}
    comp_t = sum(sum(t[c]) for c in t if c in b)
    comp_b = sum(sum(b[c]) for c in b if c in t)
    assert v["ges.yoy.total_comparable_pct"]["value"] == pytest.approx((comp_t - comp_b) / comp_b * 100)
    ficha = f4.compose(p, reg_ok(), today=TODAY)
    tab = next(t for t in ficha["tabs"] if t["id"] == "problemas")
    assert any("posible cambio de decreto GES" in x for x in tab["text"])
    assert "+10,0% solo problemas comparables" in ficha["kpis"][0]["lines"]


def test_f4_ficha_publishes_with_tabs_kpis_and_tasa_bruta(root):
    out = f4.run(root, today=TODAY, registry=reg_ok(), llm=False)
    assert out["status"] == "pass", out.get("errors")
    fi = out["ficha"]
    assert [t["label"] for t in fi["tabs"]] == ["Totales", "Top problemas", "Fonasa vs Isapre", "Tendencia trimestral"]
    assert fi["kicker_meta"].startswith("datos de enero–junio de 2026 · ")
    assert "tasa no disponible" in " ".join(fi["kpis"][1]["lines"])
    assert fi["featured"] is True and "threshold_crossed" in fi["triggers"]  # |a/a| ≥ 5 %
    assert fi["verification"]["verdict"] == "PASS" and fi["reconciliation"]["ok"]
    assert fi["reconciliation"]["cross_release"] == {"release": "2025-06", "equal": True}
    assert all(s["sha256"] and s["url"].startswith("https://") for s in fi["sources"])
    text = json.dumps(fi, ensure_ascii=False).lower()
    assert "tasa bruta" in text and "cuenta casos, no personas" in text
    assert not any(t.get("id") == "por_que" or "Por qué importa" in t.get("label", "") for t in fi["tabs"])
    assert any("notas de la sis" in n["text"].lower() for n in fi["notes"])  # captured 'Notas' sheet, paraphrased
    assert sf.lens_checks(fi, f4.build_package(root, reg_ok()))["data"] == []
    written = sf.publish(out, root)
    assert written["published"] and sf.load_live(root, "f4_ges")["status"] == "PASS"


def test_f4_chart_headline_count_is_derived_from_data(root):
    p = f4.build_package(root, reg_ok())
    fi = f4.compose(p, reg_ok(), today=TODAY)
    top = next(c for t in fi["tabs"] for c in t["charts"] if c["id"] == "f4-top")
    n = p["values"]["conteo.problemas_sobre_umbral"]["value"]
    assert n == 3 and top["headline"].startswith("Tres problemas superan")
    assert sf.lens_checks(fi, p)["data"] == []
    top["headline"] = "Dos problemas superan 15% a/a"
    assert "chart_headline_count_not_in_evidence:f4-top:dos" in " ".join(sf.lens_checks(fi, p)["data"])


@pytest.mark.parametrize("case", ["total_mismatch", "ytd_identity", "ytd_decreases", "sheet_not_pinned", "ytd_column_missing",
                                  "offline"])
def test_f4_holds_and_never_publishes(tmp_path, case):
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    url = fx.GES_URL.format(period="2026-06")
    books, fail = {}, set()
    if case == "total_mismatch":
        books[url] = fx.ges_workbook("2026-06", total_delta=(1, 0))
    elif case == "ytd_identity":
        books[url] = fx.ges_workbook("2026-06", ytd_delta={2: (0, 3)})
    elif case == "ytd_decreases":
        ytd_ = {**fx.GES_YTD, "2026-06": {**fx.GES_YTD["2026-06"], 1: (100, 10)}}  # lower than the March cut
        books[url] = fx.ges_workbook("2026-06", ytd_)
    elif case == "sheet_not_pinned":
        books[url] = fx.ges_workbook("2026-06", extra=("Año 2005", "Resumen 2026"))
    elif case == "ytd_column_missing":  # a quarter column instead of 'Ingresos entre Ene y Jun 2026'
        books[url] = fx.ges_workbook("2026-06", ytd_header="Casos acumulados del trimestre abr-jun 2026")
    else:
        fail.add(url)
    fx.capture_all(r, fx.fetcher(r, books, fail=fail))
    out = f4.run(r, today=TODAY, registry=reg_ok(), llm=False)
    assert out["status"] == "hold"
    joined = " ".join(out["errors"])
    expected = {"total_mismatch": "HOLD_GES_RECONCILIATION", "ytd_identity": "HOLD_GES_YTD_IDENTITY",
                "ytd_decreases": "ytd_row_decreases:2026-06:ps01", "sheet_not_pinned": "HOLD_GES_SHEET_NOT_PINNED",
                "ytd_column_missing": "HOLD_GES_COLUMN_MISSING", "offline": "fetch_failed"}[case]
    assert expected in joined and "HOLD_RECONCILIATION" in joined
    if case != "offline":
        assert "HOLD_MISSING_HASH" not in joined  # the file was captured and hashed: the hold names the parse
    written = sf.publish(out, r)
    assert not written["published"] and Path(written["hold"]).exists() and sf.load_live(r, "f4_ges") is None


def test_f4_older_parser_capture_holds_until_the_daily_run_rechecks_it(tmp_path, monkeypatch):
    """A file parsed by an older GES parser (v2 never matched the SIS two-row header) HOLDs with that reason, not
    with a missing hash; the next capture re-reads the same bytes once with the current parser (hash-checked)."""
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    fetch = fx.fetcher(r)
    old = {"family": "ges", "status": "HOLD", "hold_reason": "HOLD_GES_SCHEMA_NOT_VALIDATED",
           "parser": "ges_pinned_year_reconciled_v2", "insights": []}
    # The code before this parser: parse and parser name of v2.
    monkeypatch.setattr(cap.data_insights, "parse_ges_workbook", lambda b, t: {**old, "period": cap.title_period(t)})
    monkeypatch.setattr(cap.data_insights, "GES_PARSER", old["parser"])
    fx.capture_all(r, fetch)
    out = f4.run(r, today=TODAY, registry=reg_ok(), llm=False)
    assert out["status"] == "hold"
    assert out["errors"] == ["HOLD_RECONCILIATION:latest_release_not_valid:2026-06:parser_outdated:"
                             "ges_pinned_year_reconciled_v2:recheck_pending"]
    monkeypatch.undo()
    n = len(fetch.calls)
    cap.capture(r, fetch=fetch)
    ges_urls = [c for c in fetch.calls[n:] if "/fixture/ges-" in c]
    assert sorted(ges_urls) == sorted(fx.GES_URL.format(period=p) for p in fx.GES_RELEASES)  # once each, newest first
    store = json.loads((r / "data/stats_fichas/captures/ges_quarterly.json").read_text(encoding="utf-8"))
    doc = next(x for x in store["releases"] if x["period"] == "2026-06")["document"]
    assert doc["parse"]["parser"] == sf.GES_PARSER and doc["rechecked_from_parser"] == "ges_pinned_year_reconciled_v2"
    assert doc["previous_parse"]["hold_reason"] == "HOLD_GES_SCHEMA_NOT_VALIDATED"
    p = f4.build_package(r, reg_ok())
    assert p["sources"]["ges_2026-06"]["fetched_at"] == doc["rechecked_at"]  # the bytes were re-read on that date
    cap.capture(r, fetch=fetch)
    assert len([c for c in fetch.calls if "/fixture/ges-" in c]) == len(ges_urls) + len(fx.GES_RELEASES)  # never again
    assert f4.run(r, today=TODAY, registry=reg_ok(), llm=False)["status"] == "pass"
    # Bytes that no longer hash to the recorded SHA-256: HOLD hash_mismatch, never a silent re-capture.
    r2 = fx.make_root(tmp_path / "r2", readings_until="2026-06")
    monkeypatch.setattr(cap.data_insights, "parse_ges_workbook", lambda b, t: {**old, "period": cap.title_period(t)})
    monkeypatch.setattr(cap.data_insights, "GES_PARSER", old["parser"])
    fx.capture_all(r2, fx.fetcher(r2))
    monkeypatch.undo()
    url = fx.GES_URL.format(period="2026-06")
    cap.capture(r2, fetch=fx.fetcher(r2, {url: fx.ges_workbook("2026-06", total_delta=(0, 0), extra=("Notas",))}))
    out2 = f4.run(r2, today=TODAY, registry=reg_ok(), llm=False)
    assert out2["status"] == "hold" and "latest_release_not_valid:2026-06:hash_mismatch" in " ".join(out2["errors"])


def test_f4_without_beneficiaries_says_not_available(tmp_path):
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    port = json.loads((r / "data/market/isapre_portfolio.json").read_text(encoding="utf-8"))
    port["coverage"] = [c for c in port["coverage"] if c["period"] not in ("2026-05",)]
    (r / "data/market/isapre_portfolio.json").write_text(json.dumps(port), encoding="utf-8")
    fx.capture_all(r, fx.fetcher(r))
    out = f4.run(r, today=TODAY, registry=reg_ok(), llm=False)
    assert out["status"] == "pass", out.get("errors")
    fi = out["ficha"]
    assert fi["kpis"][3]["value"] == "no disponible" and "ges.ytd.2026-06.isapre_rate" not in fi["evidence"]["values"]
    assert "Sin tasas por beneficiario para este período." in fi["dek"]


# ---------------------------------------------------------------------------------------------
# F4 · Lectura: scope, period and base


def test_f4_lectura_pool_declares_scope_period_and_base(root):
    p = f4.build_package(root, reg_ok())
    for e in p["lectura_pool"]:
        assert e["scope"] in ("system", "isapres", "insurer:fonasa"), e
        assert e["period_kind"] == "ytd" and e["periods"][0].endswith("-01"), e  # year-to-date: from January
        if e["unit"] in ("%", "pp", "per_1000"):
            assert e["base"], e
        assert not e["id"].startswith("ges.cut."), e  # a since-2005 cumulative is never Lectura material
    by = {e["id"]: e for e in p["lectura_pool"]}
    assert by["ges.ytd.2026-06.isapre_rate"]["base"] == "beneficiarios_mismo_seguro"
    assert by["ges.ytd.2026-06.isapre_share"]["base"] == "casos_ambos_seguros"
    assert by["ges.yoy.total_pct"]["base"] == "casos_mismo_periodo_anio_anterior"
    assert by["ges.ytd.2026-06.fonasa"]["scope"] == "insurer:fonasa" and by["ges.ytd.2026-06.isapre"]["scope"] == "isapres"


F4_GOOD = "Para las aseguradoras, la carga GES de Fonasa equivale a 7,0 veces la de las Isapres entre enero y junio de 2026."


@pytest.mark.parametrize("text,error", [
    (F4_GOOD, None),
    ("Para las aseguradoras, las Isapres informaron 85.740 casos entre enero y junio de 2026.", "number_entity_mismatch"),
    ("Para las aseguradoras, la carga GES de Fonasa equivale a 7,0 veces la de las Isapres en junio.", "number_period_mismatch"),
    ("Para las Isapres, su tasa bruta fue 4,9 casos por cada mil personas entre enero y junio de 2026.", "share_base_unstated"),
    ("Para el regulador, las Isapres crecieron 16,9% en el segundo trimestre de 2026.", "number_period_mismatch"),
    ("Para la competencia entre aseguradoras, la demanda Isapre aumentó en 1.765 casos entre enero y junio de 2026 frente a "
     "enero y junio de 2025.", None),
    ("Para el regulador, Fonasa sumó 1.765 casos más entre enero y junio de 2026 que un año antes.", "number_entity_mismatch"),
    ("Para el regulador, Banmédica informó 7,0 veces los casos entre enero y junio de 2026.", "insurer_not_in_package"),
])
def test_f4_verifier_checks_scope_period_and_base(root, text, error):
    p = f4.build_package(root, reg_ok())
    fi = f4.compose(p, reg_ok(), today=TODAY)
    res = sf.verify_lectura(text, p, ficha=fi)
    if error is None:
        assert res["verdict"] == "PASS", res
    else:
        assert res["verdict"] == "FAIL" and any(error in e for e in res["errors"]), res


def test_f4_good_lectura_publishes_end_to_end_with_review_and_no_real_model(root):
    model = fake_model(F4_GOOD)
    out = f4.run(root, today=TODAY, registry=reg_ok(), llm=True, model_call=model, budget=ALLOW)
    lect = out["ficha"]["lectura"]
    assert lect["status"] == "pass" and lect["text"] == F4_GOOD and lect["review"]["verdict"] == "PASS"
    assert [c["feature"] for c in model.calls] == ["stats_ficha_lectura", "stats_ficha_lectura_review"]
    # A Lectura with an untraceable figure is dropped; the reviewer is never paid and the ficha still publishes.
    r2 = fx.make_root(root.parent / "r2", readings_until="2026-06")
    fx.capture_all(r2, fx.fetcher(r2))
    bad = fake_model("Para las aseguradoras, Fonasa atendió 9 veces los casos de las Isapres entre enero y junio de 2026.")
    out2 = f4.run(r2, today=TODAY, registry=reg_ok(), llm=True, model_call=bad, budget=ALLOW)
    assert out2["status"] == "pass" and out2["ficha"]["lectura"]["status"] == "verifier_fail"
    assert [c["feature"] for c in bad.calls] == ["stats_ficha_lectura"]
    # No budget: no call at all, Lectura omitted.
    r3 = fx.make_root(root.parent / "r3", readings_until="2026-06")
    fx.capture_all(r3, fx.fetcher(r3))
    none = fake_model(F4_GOOD)
    out3 = f4.run(r3, today=TODAY, registry=reg_ok(), llm=True, model_call=none, budget=lambda w: (False, "no_capacity"))
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
    m = {k: val for d in cfg["primary_review"]["documents"] if "-n2-2026-" in d["url"] for k, val in d["verified_metrics"].items()}
    assert v["acr.acreditados"] == m["accredited_providers"] == 971
    assert v["acr.sin_observaciones"] == 971 - 101 == 870
    assert v["acr.observaciones_pct"] == pytest.approx(101 / 971 * 100)  # denominator: accredited
    assert v["acr.tramite.privadas"] + v["acr.tramite.publicas"] == v["acr.tramite"] == 584
    assert v["acr.privadas_pct"] == pytest.approx(367 / 584 * 100)  # denominator: applications in process
    assert v["rec.pct"] == pytest.approx((1996 - 1530) / 1530 * 100) and round(v["rec.pct"]) == m["reported_growth_percent_rounded"]
    assert v["med.mediadores"] == 175 and v["med.solicitudes_acumuladas"] == 12067
    # RNPI gates the release (its PDF and reading are checked) but its figures never enter the package or number pool.
    assert not any(k.startswith("rnpi.") for k in v) and 1004982 not in sf.number_pool(p) and "rnpi" in p["sources"]
    # Stocks are never summed across releases: no derived value adds two cuts.
    assert not any("Σ" in str(e.get("formula") or "") for e in p["values"].values())
    assert p["kpis"]["comparisons"] == {}  # only one verified release: quarter-on-quarter stays pending


def test_f6_ficha_tabs_and_rejected_release(root):
    out = f6.run(root, today=TODAY, registry=reg(), llm=False)
    assert out["status"] == "pass", out.get("errors")
    fi = out["ficha"]
    # Approved structure (Dirección 2-nov): four topics, no RNPI; headline from verified values. Without a verified
    # previous bulletin the headline gives the level only (never a made-up change).
    assert [t["label"] for t in fi["tabs"]] == ["Acreditación", "Con observaciones", "Reclamos", "Mediación"]
    assert fi["headline"] == "Prestadores acreditados suman 971 a junio; 101 con observaciones"
    assert fi["headline_type"] == "default"
    shown = " ".join(sf.displayed_texts(fi))
    assert "RNPI" not in shown and "1.004.982" not in shown and "4.036" not in shown
    assert not any("rnpi" in s["url"] for s in fi["sources"])
    assert next(t for t in fi["tabs"] if t["id"] == "observaciones")["index_line"] == \
        "101 con observaciones · 10,4% de los acreditados"
    # The 'Septiembre 2026' page links the January–June PDFs: rejected, never relabelled.
    store = json.loads((root / "data/stats_fichas/captures/boletin_ip.json").read_text(encoding="utf-8"))
    rej = store["rejected_releases"]
    assert rej and rej[0]["title"].endswith("Septiembre 2026") and "documents_belong_to_other_release" in rej[0]["reasons"]
    # N°3-2026 (enero–septiembre) arrived as loose listing PDFs (1-nov): captured, not verified, so the watch item says
    # the new bulletin is being verified instead of repeating the September page rejection.
    assert fi["watch"][0]["headline"] == "Nuevo boletín (datos a septiembre 2026): cifras en verificación."
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
    assert c["acr.acreditados"] == 971 - 950 and c["acr.tramite"] == 584 - 600
    assert not any(k.startswith(("rnpi.", "med.")) for k in c)  # hidden RNPI; mediación shows its level only
    fi = f6.compose(p, reg(), today=TODAY)
    assert "+21 vs. marzo 2026" in fi["kpis"][0]["lines"]
    # The headline wording follows the sign of the verified change; a fall reads 'bajan … menos', never '−21 más'.
    assert fi["headline"] == "Prestadores acreditados llegan a 971 a junio, 21 más que en marzo; 101 con observaciones"
    p["kpis"]["comparisons"]["acr.acreditados"] = -21
    assert f6.compose(p, reg(), today=TODAY)["headline"] == \
        "Prestadores acreditados bajan a 971 a junio, 21 menos que en marzo; 101 con observaciones"
    p["kpis"]["comparisons"]["acr.acreditados"] = 0
    assert f6.compose(p, reg(), today=TODAY)["headline"].startswith("Prestadores acreditados se mantienen en 971 a junio")


@pytest.mark.parametrize("case", ["figure_missing", "sum_mismatch", "offline"])
def test_f6_holds(tmp_path, case):
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    books, fail = {}, set()
    acc = "https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf"
    if case == "figure_missing":
        books[acc] = fx.pdf_with_text([fx.figure_line("accredited_providers", 970), fx.figure_line("with_observations", 101),
                                       fx.figure_line("pending_applications", 584), fx.figure_line("private_pending", 367),
                                       fx.figure_line("public_pending", 217)])
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
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    fetch = fx.fetcher(r)
    fx.capture_all(r, fetch)
    n = len(fetch.calls)
    # 4 GES files + 6 Boletines × 4 PDFs: five release pages and N°3-2026 from the loose listing PDFs (1-nov); the
    # mislabeled 'Septiembre 2026' page is never fetched.
    assert n == len(fx.GES_RELEASES) + 6 * 4
    fx.capture_all(r, fetch)
    assert len(fetch.calls) == n  # already captured: never downloaded again
    for name in ("ges_quarterly.json", "boletin_ip.json"):
        raw = (r / "data/stats_fichas/captures" / name).read_text(encoding="utf-8")
        # GES keeps one flat line per problem (85 problems × 3 sheets × 4 releases in the fixture): values, never bytes.
        assert len(raw) < 150_000 and "%PDF" not in raw and "PK\u0003" not in raw
    ges = json.loads((r / "data/stats_fichas/captures/ges_quarterly.json").read_text(encoding="utf-8"))
    assert all(len(x["document"]["sha256"]) == 64 and x["document"]["format"] == "xlsx" for x in ges["releases"])
    assert cap.file_format(b"%PDF-1.4") == "pdf" and cap.file_format(b"PK\x03\x04") == "xlsx"


def test_capture_retries_failed_downloads_a_bounded_number_of_times(tmp_path):
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
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
    confirmed = reg_ok()
    monkeypatch.setattr(runner.stats_fichas, "load_registry", lambda: confirmed)
    assert runner.main(["--root", str(root), "--as-of", "2026-10-29", "--family", "F4", "--family", "F6"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert seen and summary["F4"]["status"] == "pass" and summary["F6"]["status"] == "pass"
    assert summary["F4"]["lectura"] == "not_attempted"  # no key: no model call
    assert runner.main(["--root", str(root), "--as-of", "2026-10-29", "--family", "F4", "--no-capture"]) == 0
    assert len(seen) == 1
    reg_ = reg()
    active = {f for f, c in reg_["families"].items() if c["status"] == "active"}
    # Every active family has a builder and runs in the daily default; F4/F6 documents go through stats_capture and
    # F2 (active since 2-nov-2026) through stats_capture_fefi (tests/test_stats_ficha_f2.py covers that run).
    assert {"F4", "F6"} <= active <= set(runner.BUILDERS) and runner.CAPTURED == {"F4", "F6"}
    assert "F2" in active and runner.FEFI_CAPTURED == {"F2"} and reg_["families"]["F2"]["lectura_enabled"] is False
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
    # Confirmed by Dirección on 3-nov-2026 (year-to-date, "ene–jun vs ene–jun"); never by the code.
    assert a["measure"]["declared"] == "ytd" and a["measure"]["confirmed"] is True
    assert a["measure"]["confirmed_by"].startswith("Dirección (cftorre1), 3-nov-2026")
    assert "T1 = corte de marzo − corte de diciembre del año anterior" in a["kpis"]["casos_ges"]["formula"]
    assert "(T1 = corte de marzo)" not in json.dumps(a, ensure_ascii=False)
    assert a["capture"]["parser"] == sf.GES_PARSER
    assert a["supersedes"]["stat_families"] == ["ges"] and b["supersedes"]["stat_families"] == ["boletin_ip"]
    assert [t["label"] for t in a["tabs"]] == ["Totales", "Top problemas", "Fonasa vs Isapre", "Tendencia trimestral"]
    assert [t["label"] for t in b["tabs"]] == ["Acreditación", "Con observaciones", "Reclamos", "Mediación"]
    assert list(b["hidden_topics"]) == ["rnpi"] and f6.HIDDEN_TOPICS == ("rnpi",)


def test_snapshot_ges_card_leaves_hold_only_when_f4_passes(root):
    hist = json.loads((REPO / "data/history/superintendencia_signals.json").read_text(encoding="utf-8"))["signals"]
    # Statistics cards only: SIS news (e.g. "Más de 62 millones de casos GES…", 29-oct) also mention GES cases.
    ges = [sf.sanitize_ges_signal(s) for s in hist if "casos ges" in cap._fold(s.get("title"))
           and cap._fold(s.get("title")).startswith("estadistica") and s.get("source_name") == "Superintendencia de Salud"]
    assert any((s.get("statistical_view") or {}).get("publication_status") == "HOLD" for s in ges)
    cards = [{**s, "signal_types": s.get("signal_types") or ["Datos"]} for s in ges]
    # No PASS: no live F4 ficha, the loose GES cards stay as they are (in HOLD).
    assert sf.live_fichas(root) == [] or all(f["family"] != "F4" for f in sf.live_fichas(root))
    out = f4.run(root, today=TODAY, registry=reg_ok(), llm=False)
    sf.publish(out, root)
    fichas = [f for f in sf.live_fichas(root) if f["family"] == "F4"]
    assert fichas and fichas[0]["status"] == "PASS"
    result = sf.apply_to_snapshot(cards, fichas)
    assert [c for c in result if c.get("stats_ficha")][0]["scopes"] == ["Isapres", "Fonasa"]
    left = [c for c in result if not c.get("stats_ficha")]
    assert all(sf.loose_card_period(c) > fichas[0]["period"] for c in left)  # only releases newer than the ficha stay


def test_committed_fixture_cards_match_the_builders(tmp_path):
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    fx.capture_all(r, fx.fetcher(r))
    for fam, mod in (("F4", f4), ("F6", f6)):
        fi = mod.run(r, today=TODAY, registry=reg_ok(), llm=False)["ficha"]
        card = json.loads((fx.FIXTURE_DIR / f"{reg()['families'][fam]['slug']}.card.json").read_text(encoding="utf-8"))
        for key in ("headline", "dek", "kpis", "tabs", "watch", "notes"):
            assert card["stats_ficha"][key] == json.loads(json.dumps(fi[key], ensure_ascii=False)), key


# ---------------------------------------------------------------------------------------------
# Review fixes (independent review FAIL on 80c7f530): measure, ranking sign, thresholds, provenance, F6 sign


@pytest.mark.parametrize("header,expected", [
    ("casos acumulados enero a junio", "ytd"), ("acumulado del año", "ytd"), ("casos acumulados del trimestre", "quarter"),
    ("acumulado en el trimestre", "quarter"), ("casos del trimestre", "quarter"), ("casos acumulados", None), ("casos", None),
    ("casos acumulados desde 2005", "since_2005"), ("trimestre enero a marzo", "ambiguous"),
    ("Ingresos entre Ene y Jun 2026", "ytd"), ("Número de casos acumulados Jul-2005 a Jun-2026", "since_2005")])
def test_f4_header_measure_reads_quarter_cumulative_as_quarter(header, expected):
    assert f4.header_measure({"header": {"fonasa": f"Fonasa {header}", "isapre": f"Isapre {header}"}}) == expected


def test_f4_holds_without_reviewer_flag_whatever_the_header_says():
    cfg = reg()["families"]["F4"]
    cfg["measure"].update(confirmed=False, confirmed_by=None)
    ytd_head = {"header": {"fonasa": "Fonasa casos acumulados enero a junio", "isapre": "Isapre casos acumulados enero a junio"}}
    assert f4.measure_of(ytd_head, cfg) == (None, "unconfirmed")
    ok = reg_ok()["families"]["F4"]
    assert f4.measure_of(ytd_head, ok)[0] == "ytd"
    quarter_head = {"header": {"fonasa": "Fonasa acumulado del trimestre", "isapre": "Isapre acumulado del trimestre"}}
    assert f4.measure_of(quarter_head, ok) == (None, "header_contradicts_reviewer:quarter")  # never read as YTD
    assert f4.measure_of({"header": {"above": ["desde julio de 2005"]}}, ok) == (None, "source_declares_since_2005")
    # v3 parse: the measure column is the year-to-date column; a since-2005 title there vetoes.
    assert f4.measure_of({"header": {"ytd": "Ingresos entre Ene y Jun 2026"}}, ok)[0] == "ytd"
    assert f4.measure_of({"header": {"ytd": "Casos acumulados Jul-2005 a Jun-2026"}}, ok) == (None, "source_declares_since_2005")


def test_f4_header_contradicting_reviewer_holds(tmp_path, monkeypatch):
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    fx.capture_all(r, fx.fetcher(r))
    store_path = r / "data/stats_fichas/captures/ges_quarterly.json"
    store = json.loads(store_path.read_text(encoding="utf-8"))
    for rel in store["releases"]:  # a parse whose measure column says 'quarter' is never read as year-to-date
        rel["document"]["parse"]["header"]["ytd"] = "Casos acumulados del trimestre"
    store_path.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    out = f4.run(r, today=TODAY, registry=reg_ok(), llm=False)
    assert out["status"] == "hold" and "header_contradicts_reviewer" in " ".join(out["errors"])


def test_f4_ranking_never_draws_a_decline_as_a_positive_bar(tmp_path):
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    ytd_ = {**fx.GES_YTD, "2026-06": {**fx.GES_YTD["2026-06"], 2: (38000, 4000)}}  # 42.000 ene–jun 2026 < 45.100 in 2025
    fx.capture_all(r, fx.fetcher(r, {fx.GES_URL.format(period="2026-06"): fx.ges_workbook("2026-06", ytd_)}))
    p = f4.build_package(r, reg_ok())
    assert any(x["pct"] < 0 for x in p["kpis"]["ranked"])
    fi = f4.compose(p, reg_ok(), today=TODAY)
    tab = next(t for t in fi["tabs"] if t["id"] == "problemas")
    top = tab["charts"][0]
    assert top["rows"] and all(x["value"] > 0 for x in top["rows"]) and "crecen" in top["subtitle"]
    assert all(not row[-1].startswith(("−", "-")) for row in top["table"]["rows"])
    assert any("Un problema comparable bajó" in x for x in tab["text"])
    assert p["values"]["conteo.problemas_bajan"]["value"] == 1


def test_f4_thresholds_come_from_the_registry(root):
    registry = reg_ok()
    registry["families"]["F4"]["kpis"]["casos_ges"]["threshold"]["yoy_pct"] = 12.0  # fixture: +12,5% ene–jun a/a
    fi = f4.compose(f4.build_package(root, registry), registry, today=TODAY)
    assert fi["kpis"][0]["badge"] == "Cruza umbral (12% a/a)"
    assert "Una variación de 12% o más" in fi["watch"][0]["explanation"]
    import re
    assert not re.search(r"(?<![\d,])5%", json.dumps([fi["kpis"], fi["watch"]], ensure_ascii=False))
    assert not re.search(r"(?<![\d,{])5%", (REPO / "src/radar_salud/stats_ficha_f4.py").read_text(encoding="utf-8"))


def test_f4_problem_values_trace_to_sheet_rows(root):
    p = f4.build_package(root, reg_ok())
    v = p["values"]
    key = f4.pkey(3)  # Cáncer de mama en personas de 15 años y más
    # Current year: the problem's row of the year-to-date column.
    e = v[f"ges.p.{key}.ytd.2026-06"]
    assert e["inputs"] == [f"ges.ytd.2026-06.p.{key}.fonasa", f"ges.ytd.2026-06.p.{key}.isapre"]
    assert e["value"] == sum(v[i]["value"] for i in e["inputs"]) == sum(fx.GES_YTD["2026-06"][3])
    # The row number is the captured row of the problem in the pinned sheet (fixture: header row 3, subheader 4, dates 5,
    # problems from row 6, a 'Subtotal' row after the second problem).
    assert v[f"ges.ytd.2026-06.p.{key}.fonasa"]["locator"].startswith("Año 2026!fila 9 (problema N°3) · Ingresos entre Ene y Jun 2026")
    # Same months of 2025: cum(jun 2025) − cum(dic 2024) of the problem's rows.
    e = v[f"ges.p.{key}.ytd.2025-06"]
    assert sorted(e["inputs"]) == sorted(f"ges.cut.{c}.p.{key}.{ins}" for c in ("2025-06", "2024-12") for ins in ("fonasa", "isapre"))
    for i in e["inputs"]:
        src = v[i]
        assert src["kind"] == f4.CUMULATIVE and src["source"] in p["sources"] and "!fila " in src["locator"] and "Jul-2005" in src["locator"]
    c = {(i.split(".")[2], i.rsplit(".", 1)[1]): v[i]["value"] for i in e["inputs"]}
    assert e["value"] == sum(c[("2025-06", ins)] - c[("2024-12", ins)] for ins in ("fonasa", "isapre")) == sum(fx.GES_YTD["2025-06"][3])


def test_f6_claims_wording_follows_the_sign(root):
    p = f6.build_package(root, reg())
    fi = f6.compose(p, reg(), today=TODAY)
    text = " ".join(next(t for t in fi["tabs"] if t["id"] == "reclamos")["text"])
    assert "466 más al mes" in text
    p["values"]["rec.delta"]["value"] = -466
    fi = f6.compose(p, reg(), today=TODAY)
    text = " ".join(next(t for t in fi["tabs"] if t["id"] == "reclamos")["text"])
    assert "466 menos al mes" in text and "más al mes" not in text
    # The dek too: a fall reads "3,2% menos", never "−3,2% menos" (review 29-oct).
    p["values"]["rec.pct"]["value"] = -3.2
    fi = f6.compose(p, reg(), today=TODAY)
    assert "3,2% menos que el promedio" in fi["dek"] and "−3,2% menos" not in fi["dek"] and "-3,2% menos" not in fi["dek"]


def test_read_capped_stops_at_the_capture_deadline():
    from radar_salud.stats_capture import read_capped
    ticks = iter([0.0, 5.0, 11.0, 12.0])
    resp = FakeResponse("https://www.superdesalud.gob.cl/x.xlsx", b"a" * (64 * 1024 * 4))
    with pytest.raises(TimeoutError):
        read_capped(resp, 10**9, deadline=10.0, clock=lambda: next(ticks))


# ---------------------------------------------------------------------------------------------
# Capture network guard (no network: a fake opener stands in for urllib)


class FakeResponse:
    def __init__(self, url, body, headers=None):
        self.url, self._body, self.headers, self.reads = url, body, headers or {}, 0

    def geturl(self):
        return self.url

    def read(self, n=-1):
        self.reads += 1
        out, self._body = (self._body, b"") if n is None or n < 0 else (self._body[:n], self._body[n:])
        return out

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    """url → bytes | int (HTTP status) | Exception | (final_url, bytes)."""

    def __init__(self, routes):
        self.routes, self.calls, self.timeouts = routes, [], []

    def open(self, req, timeout=None):
        from urllib.error import HTTPError
        url = req.full_url
        self.calls.append(url)
        self.timeouts.append(timeout)
        r = self.routes.get(url, 404)
        if isinstance(r, Exception):
            raise r
        if isinstance(r, int):
            raise HTTPError(url, r, "status", {}, None)
        final, body = r if isinstance(r, tuple) else (url, r)
        return FakeResponse(final, body)


SIS_DOC = "https://www.superdesalud.gob.cl/app/uploads/2026/10/doc.xlsx"
SIS_ROBOTS = "https://www.superdesalud.gob.cl/robots.txt"


def test_fetch_rejects_off_allowlist_hosts_before_any_request():
    opener = FakeOpener({})
    fetch = cap.SisFetcher(opener=opener)
    for url in ("https://evil.example/doc.xlsx", "http://www.superdesalud.gob.cl/doc.xlsx",
                "https://www.superdesalud.gob.cl.evil.example/doc.xlsx", "https://user:pw@www.superdesalud.gob.cl/doc.xlsx",
                "https://www.superdesalud.gob.cl:8443/doc.xlsx"):
        with pytest.raises(PermissionError, match="host_not_allowlisted"):
            fetch(url)
    assert opener.calls == []
    assert cap.sis_url_ok("https://superdesalud.gob.cl/x.pdf") and cap.sis_url_ok(SIS_DOC)


def test_redirect_off_allowlist_is_blocked():
    from urllib.request import Request
    handler = cap.sis_redirect_handler()
    req = Request(SIS_DOC)
    with pytest.raises(PermissionError, match="redirect_off_allowlist"):
        handler.redirect_request(req, None, 302, "Found", {}, "https://cdn.evil.example/doc.xlsx")
    assert handler.redirect_request(req, None, 302, "Found", {}, "https://superdesalud.gob.cl/doc.xlsx") is not None
    # A response whose final URL left the allowlist is rejected too (defence in depth).
    opener = FakeOpener({SIS_ROBOTS: b"User-agent: *\nAllow: /\n", SIS_DOC: ("https://evil.example/doc.xlsx", b"PK\x03\x04")})
    with pytest.raises(PermissionError, match="redirect_off_allowlist"):
        cap.SisFetcher(opener=opener)(SIS_DOC)


def test_oversize_download_is_aborted_while_reading():
    big = b"x" * (3 * 64 * 1024)
    resp = FakeResponse(SIS_DOC, big)
    with pytest.raises(ValueError, match="response_too_large"):
        cap.read_capped(resp, 100 * 1024)
    assert resp.reads == 2  # stopped at the chunk that passed the cap, the rest is never read
    with pytest.raises(ValueError, match="response_too_large: declared"):
        cap.read_capped(FakeResponse(SIS_DOC, b"", {"Content-Length": str(cap.MAX_BYTES + 1)}), cap.MAX_BYTES)
    opener = FakeOpener({SIS_ROBOTS: 404, SIS_DOC: big})
    with pytest.raises(ValueError, match="response_too_large"):
        cap.SisFetcher(opener=opener, max_bytes=100 * 1024)(SIS_DOC)
    assert cap.MAX_BYTES == 25 * 1024 * 1024 and cap.REQUEST_TIMEOUT_S == 30 and cap.TIME_BUDGET_S == 480


def test_robots_disallow_is_respected_and_unknown_policy_fails_closed():
    opener = FakeOpener({SIS_ROBOTS: b"User-agent: *\nDisallow: /app/uploads/\n", SIS_DOC: b"PK\x03\x04"})
    with pytest.raises(PermissionError, match="robots_disallowed"):
        cap.SisFetcher(opener=opener)(SIS_DOC)
    assert SIS_DOC not in opener.calls
    for status in (401, 403, 429, 500, 503):
        opener = FakeOpener({SIS_ROBOTS: status, SIS_DOC: b"PK\x03\x04"})
        with pytest.raises(PermissionError):
            cap.SisFetcher(opener=opener)(SIS_DOC)
        assert SIS_DOC not in opener.calls, status
    opener = FakeOpener({SIS_ROBOTS: OSError("network down"), SIS_DOC: b"PK\x03\x04"})
    with pytest.raises(PermissionError, match="robots_unavailable"):
        cap.SisFetcher(opener=opener)(SIS_DOC)
    # 404: no robots file → allowed; robots.txt is read once per host and run; the request timeout is 30 s.
    opener = FakeOpener({SIS_ROBOTS: 404, SIS_DOC: b"PK\x03\x04"})
    fetch = cap.SisFetcher(opener=opener)
    assert fetch(SIS_DOC) == b"PK\x03\x04" and fetch(SIS_DOC) == b"PK\x03\x04"
    assert opener.calls.count(SIS_ROBOTS) == 1 and max(opener.timeouts) <= 30


def test_capture_time_budget_stops_new_downloads(tmp_path):
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    fetch = fx.fetcher(r)
    now = {"t": 0.0}

    def slow(url):
        now["t"] += 200.0  # each download takes 200 s of the 480 s budget
        return fetch(url)
    summary = cap.capture(r, fetch=slow, clock=lambda: now["t"])
    assert len(fetch.calls) == 3 and summary["time_budget_exhausted"] is True  # 0 → 200 → 400 → 600: no 4th start
    store = json.loads((r / "data/stats_fichas/captures/boletin_ip.json").read_text(encoding="utf-8"))
    assert all(d.get("status") == "not_fetched" for rel in store["releases"] for d in rel["documents"])  # no attempt burned
    # The default fetcher gets the remaining budget as its deadline (per-request timeout ≤ 30 s, never past it).
    f = cap.SisFetcher(opener=FakeOpener({}), deadline=10.0, clock=lambda: 0.0)
    assert f._timeout() == 10.0
    with pytest.raises(TimeoutError):
        cap.SisFetcher(opener=FakeOpener({}), deadline=0.0, clock=lambda: 5.0)._timeout()


def test_parse_failure_is_recorded_and_not_redownloaded_for_seven_days(tmp_path, monkeypatch):
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    url = fx.GES_URL.format(period="2026-06")
    monkeypatch.setattr(cap.data_insights, "parse_ges_workbook",
                        lambda b, t: (_ for _ in ()).throw(RuntimeError("broken workbook")) if "junio 2026" in t
                        else fx_parse(b, t))
    fetch = fx.fetcher(r)
    for _ in range(4):
        cap.capture(r, fetch=fetch)
    assert fetch.calls.count(url) == 1
    store = json.loads((r / "data/stats_fichas/captures/ges_quarterly.json").read_text(encoding="utf-8"))
    doc = next(x for x in store["releases"] if x["period"] == "2026-06")["document"]
    assert doc["status"] == "parse_failed" and "broken workbook" in doc["error"] and len(doc["sha256"]) == 64
    assert sum(1 for x in store["releases"] if x["document"]["status"] == "captured") == 3  # the other files still parse
    # Eight days later the file is downloaded again once.
    doc["fetched_at"] = "2026-01-01T00:00:00+00:00"
    (r / "data/stats_fichas/captures/ges_quarterly.json").write_text(json.dumps(store), encoding="utf-8")
    cap.capture(r, fetch=fetch)
    assert fetch.calls.count(url) == 2


from radar_salud import data_insights as _di  # noqa: E402

fx_parse = _di.parse_ges_workbook


def test_verified_figure_must_sit_on_a_cited_page_next_to_its_context_word():
    m = {"accredited_providers": 971, "with_observations": 101, "registered_mediators": 175,
         "reported_growth_percent_rounded": 30}
    good = fx.pdf_with_text([], pages=[["Indice"], [fx.figure_line(k, v) for k, v in m.items()]])
    assert cap.parse_boletin_pdf(good, m, [2])["status"] == "verified"
    assert cap.parse_boletin_pdf(good, m, [1])["status"] == "verified_figure_missing"  # right numbers, uncited page
    assert cap.parse_boletin_pdf(good, m, None)["status"] == "verified_figure_missing"  # no cited pages: fail closed
    # Small numbers anywhere (page numbers, dates, codes) are not the verified figures.
    loose = fx.pdf_with_text([], pages=[["Indice"], ["Pagina 30 de 175", "Seccion 101", "Codigo 971", "Prestadores"]])
    res = cap.parse_boletin_pdf(loose, m, [2])
    assert res["status"] == "verified_figure_missing" and not any(res["verified_present"].values())
    assert not cap.present_in("Prestadores acreditados en el periodo" + " " * 200 + "971", 971, ("acreditad",))
    assert cap.present_in("971 prestadores acreditados", 971, ("acreditad",))


# ---------------------------------------------------------------------------------------------
# Review of PR #129 (3-nov-2026): table structure, cumulative inputs, first-publication gate, dek wording


GES_TITLE = "Estadística Trimestral de Casos GES (AUGE) de Fonasa y Sistema ISAPRE – a junio 2026"


def edit_book(book: bytes, fn) -> bytes:
    from io import BytesIO
    from openpyxl import load_workbook
    wb = load_workbook(BytesIO(book))
    fn(wb)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def year_sheets(wb):
    return [ws for ws in wb.worksheets if ws.title.startswith("Año 20") and ws.title != "Año 2005"]


def row_of(ws, code):
    return next(r[0].row for r in ws.iter_rows() if r[0].value == code)


def early_total(wb):
    """A decree total labelled 'Total Decreto…' after problem 3 (with the partial sums), in every year sheet."""
    for ws in year_sheets(wb):
        at = row_of(ws, 3) + 1
        sums = [sum(ws.cell(row_of(ws, c), col).value or 0 for c in (1, 2, 3)) or None for col in range(3, ws.max_column + 1)]
        ws.insert_rows(at)
        ws.cell(at, 2, "Total Decreto Supremo N°1")
        for j, x in enumerate(sums):
            ws.cell(at, 3 + j, x)


def coded_after_total(wb):
    ws = wb["Año 2026"]
    ws.append([86, "Problema escondido tras el total", 1, 1])


def gap(wb):
    ws = wb["Año 2026"]
    ws.delete_rows(row_of(ws, 40))


def duplicate(wb):
    ws = wb["Año 2026"]
    ws.cell(row_of(ws, 41), 1, 40)


def no_code_column(wb):
    ws = wb["Año 2026"]
    ws.cell(3, 1, "Orden")


def swapped(wb):
    ws = wb["Año 2026"]
    for c in range(3, ws.max_column + 1, 2):
        ws.cell(4, c, "ISAPRE")
        ws.cell(4, c + 1, "FONASA")


def no_subheader(wb):
    ws = wb["Año 2026"]
    ws.delete_rows(4, ws.max_row)


@pytest.mark.parametrize("fn,reason,detail", [
    (early_total, "HOLD_GES_ROWS_AFTER_TOTAL", None),
    (coded_after_total, "HOLD_GES_ROWS_AFTER_TOTAL", None),
    (gap, "HOLD_GES_PROBLEM_NUMBERS_NOT_CONTIGUOUS", None),
    (duplicate, "HOLD_GES_DUPLICATE_PROBLEM", None),
    (no_code_column, "HOLD_GES_SCHEMA_NOT_VALIDATED", "no_code_column"),
    (no_subheader, "HOLD_GES_SCHEMA_NOT_VALIDATED", "no_subheader"),
    (swapped, "HOLD_GES_HEADER_NOT_VALIDATED", "fonasa_isapre"),
])
def test_ges_table_structure_holds_with_its_reason(fn, reason, detail):
    from radar_salud import ges_workbook as gw
    r = gw.parse(edit_book(fx.ges_workbook("2026-06"), fn), GES_TITLE)
    assert r["status"] == "HOLD" and r["hold_reason"] == reason and "years" not in r, r
    assert r.get("detail") == detail
    if fn is gap:
        assert r["missing"] == [40]


def test_ges_minimum_problem_count_comes_from_the_registry():
    from radar_salud import ges_workbook as gw
    assert gw.min_problems() == reg()["families"]["F4"]["capture"]["min_problems"] == 80
    full = fx.ges_workbook("2026-06")
    assert gw.parse(full, GES_TITLE)["status"] == "validated"  # 85 problems in 2026, 84 before
    r = gw.parse(full, GES_TITLE, min_rows=85)  # the 2025 and 2024 sheets carry 84
    assert r["hold_reason"] == "HOLD_GES_TOO_FEW_PROBLEMS" and r["problems"] == 84 and r["min_problems"] == 85


def test_f4_early_total_row_never_publishes_an_undercount(tmp_path):
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    books = {fx.GES_URL.format(period=p): edit_book(fx.ges_workbook(p), early_total) for p in fx.GES_RELEASES}
    fx.capture_all(r, fx.fetcher(r, books))
    out = f4.run(r, today=TODAY, registry=reg_ok(), llm=False)
    assert out["status"] == "hold" and "HOLD_GES_ROWS_AFTER_TOTAL" in " ".join(out["errors"])


def test_f4_first_publication_waits_for_a_human_review_of_that_release(root):
    registry = reg_ok()
    registry["families"]["F4"]["first_pass_requires_review"] = True
    out = f4.run(root, today=TODAY, registry=registry, llm=False)
    assert out["status"] == "hold" and out["errors"] == [f4.FIRST_REVIEW_HOLD]
    assert "awaiting_first_review" in " ".join(out["decision"]["holds"]) and out["candidate"]["status"] == "AWAITING_FIRST_REVIEW"
    written = sf.publish(out, root)
    hold = json.loads(Path(written["hold"]).read_text(encoding="utf-8"))
    assert not written["published"] and sf.load_live(root, "f4_ges") is None
    cand = hold["candidate"]  # the full rendered ficha, for the reviewer
    assert cand["headline"].startswith("Casos GES entre enero y junio de 2026") and cand["kpis"] and cand["tabs"]
    sha = cand["review_request"]["release_sha256"]
    store = json.loads((root / "data/stats_fichas/captures/ges_quarterly.json").read_text(encoding="utf-8"))
    assert sha == next(x for x in store["releases"] if x["period"] == "2026-06")["document"]["sha256"]
    # A review recorded for another file does not open the gate; one for this file does.
    registry["families"]["F4"]["first_review"].update(reviewed_by="revisor de prueba", reviewed_at="2026-11-04",
                                                      reviewed_sha256="0" * 64)
    assert f4.run(root, today=TODAY, registry=registry, llm=False)["status"] == "hold"
    registry["families"]["F4"]["first_review"].update(reviewed_sha256=sha, reviewed_by=None)
    assert f4.run(root, today=TODAY, registry=registry, llm=False)["status"] == "hold"  # who reviewed is required
    registry["families"]["F4"]["first_review"].update(reviewed_by="revisor de prueba")
    out = f4.run(root, today=TODAY, registry=registry, llm=False)
    assert out["status"] == "pass" and sf.publish(out, root)["published"]
    # Once a year-to-date ficha is live, later releases follow the normal policy (no new review needed).
    registry["families"]["F4"]["first_review"].update(reviewed_sha256="f" * 64)
    assert f4.run(root, today=TODAY, registry=registry, llm=False)["status"] in ("pass", "no_change")
    # The committed registry keeps the gate on and records no review yet.
    committed = reg()["families"]["F4"]
    assert committed["first_pass_requires_review"] is True and committed["first_review"]["reviewed_sha256"] is None


def test_f4_dek_names_the_rate_period_and_the_decree_caveat(root):
    out = f4.run(root, today=TODAY, registry=reg_ok(), llm=False)
    dek = out["ficha"]["dek"]
    assert "casos de enero a junio de 2026 por 1.000 beneficiarios" in dek
    assert "La variación incluye 1 problema nuevo por decreto; comparable: +10,0%." in dek
    assert len(dek.split()) <= 40
    # Without a list change there is no caveat.
    p = f4.build_package(root, reg_ok())
    p["kpis"]["added"] = []
    assert "decreto" not in f4.compose(p, reg_ok(), today=TODAY)["dek"]


def test_f4_dropped_problem_stays_in_last_years_base_and_the_dek_says_so(tmp_path):
    """Problem 84 leaves the list in 2026 (the last number: the table stays contiguous). Its 2025 flows remain in the
    January–June 2025 base; the comparable change excludes it, and the dek says the base includes it."""
    import copy
    y = copy.deepcopy(fx.GES_YTD)
    for per in ("2026-03", "2026-06"):
        y[per].pop(84)
        y[per].pop(fx.NEW_CODE)
    y["2025-03"][84], y["2025-06"][84], y["2025-09"][84], y["2025-12"][84] = (4500, 450), (9000, 900), (13500, 1350), (18000, 1800)
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    fx.capture_all(r, fx.fetcher(r, {fx.GES_URL.format(period=p): fx.ges_workbook(p, y) for p in fx.GES_RELEASES}))
    p = f4.build_package(r, reg_ok())
    assert p["reconciliation"]["ok"], p["reconciliation"]
    v = {k: e["value"] for k, e in p["values"].items()}
    base = sum(sum(x) for x in y["2025-06"].values())
    assert v["ges.ytd.2025-06.total"] == base and v["ges.ytd.2025-06.total_comparable"] == base - (9000 + 900)
    assert p["kpis"]["dropped"] == [f4.pkey(84)] and p["kpis"]["added"] == []
    # T1 2026 is computed over the problems of 2026: the December base leaves problem 84 out.
    assert p["values"]["ges.q.2026T1.fonasa"]["inputs"] == ["ges.cut.2026-03.fonasa", "ges.cut.2025-12.base_2026.fonasa"]
    assert v["ges.q.2026T1.fonasa"] == sum(f for f, _ in y["2026-03"].values())
    fi = f4.compose(p, reg_ok(), today=TODAY)
    assert v["ges.yoy.total_pct"] < 0 < v["ges.yoy.total_comparable_pct"]
    assert ("La base de enero–junio de 2025 incluye 1 problema retirado; comparable: "
            + sf.fmt_dec(v["ges.yoy.total_comparable_pct"], 1, signed=True) + "%.") in fi["dek"]
    assert "excluye" not in fi["dek"] and len(fi["dek"].split()) <= 40
    out = f4.run(r, today=TODAY, registry=reg_ok(), llm=False)
    assert out["status"] == "pass", out.get("errors")


def test_f4_gated_run_never_calls_the_model_and_marks_the_candidate(root):
    registry = reg_ok()
    registry["families"]["F4"]["first_pass_requires_review"] = True
    model = fake_model(F4_GOOD)
    out = f4.run(root, today=TODAY, registry=registry, llm=True, model_call=model, budget=ALLOW)
    assert out["status"] == "hold" and out["errors"] == [f4.FIRST_REVIEW_HOLD]
    assert model.calls == []  # no paid Lectura while the gate is closed
    assert out["candidate"]["status"] == "AWAITING_FIRST_REVIEW" and out["candidate"]["lectura"]["status"] == "not_attempted"
    # With the review recorded for this file, the same run calls the model once (writer + reviewer) and publishes.
    registry["families"]["F4"]["first_review"].update(reviewed_by="revisor de prueba", reviewed_at="2026-11-04",
                                                      reviewed_sha256=out["candidate"]["review_request"]["release_sha256"])
    out = f4.run(root, today=TODAY, registry=registry, llm=True, model_call=model, budget=ALLOW)
    assert out["status"] == "pass" and [c["feature"] for c in model.calls] == ["stats_ficha_lectura", "stats_ficha_lectura_review"]


# ---------------------------------------------------------------------------------------------
# Daily run 3-nov-2026 on the real SIS workbooks: HOLD_GES_ROW_UNRECOGNIZED 'Sin Problema de Salud Informado'
# (Año 2026 row 97, Año 2025 row 94): an un-numbered row of cases with no problem informed, part of the Total.

def _unassigned_value(per: str) -> tuple[int, int]:
    q = (int(per[:4]) - 2023) * 4 + int(per[5:7]) // 3  # grows with every cut: cumulative never decreases
    return 7 * q, 3 * q


def sin_problema(wb):
    """Insert the SIS 'Sin Problema de Salud Informado' row (no N°) above the Total, adding it to the Total."""
    for ws in year_sheets(wb):
        year = int(ws.title[-4:])
        if year < 2023:
            continue
        total_row = next(r[0].row for r in ws.iter_rows() if str(r[1].value or "").startswith("Total"))
        vals = [None] * (ws.max_column - 2)
        for c in range(3, ws.max_column + 1, 2):
            head = str(ws.cell(3, c).value or "")
            tail = head.split("2005 a")[-1] if "acumulados" in head else head.split("y")[-1]  # the cut month, never Jul-2005
            mon = fx.MON3.index(next(m for m in fx.MON3 if m in tail)) + 1
            per = f"{year}-{mon:02d}"
            if ws.cell(total_row, c).value is None:
                continue
            u = _unassigned_value(per)
            if "acumulados" not in head:  # year to date = cumulative now − cumulative previous December
                b = _unassigned_value(f"{year - 1}-12")
                u = (u[0] - b[0], u[1] - b[1])
            vals[c - 3], vals[c - 2] = u
            ws.cell(total_row, c, ws.cell(total_row, c).value + u[0])
            ws.cell(total_row, c + 1, ws.cell(total_row, c + 1).value + u[1])
        ws.insert_rows(total_row)
        ws.cell(total_row, 2, "Sin Problema de Salud Informado")
        for j, v in enumerate(vals):
            ws.cell(total_row, 3 + j, v)


def test_ges_unassigned_row_is_reconciled_with_the_total_and_never_a_problem():
    from radar_salud import ges_workbook as gw
    r = gw.parse(edit_book(fx.ges_workbook("2026-06"), sin_problema), GES_TITLE)
    assert r["status"] == "validated", r
    cur = gw.expand_sheet(r["years"]["2026"])
    assert cur["unassigned"]["cut"]["2026-06"] == list(_unassigned_value("2026-06"))
    assert all(p["label"] != "Sin problema de salud informado" for p in cur["problems"].values())
    plain = gw.expand_sheet(gw.parse(fx.ges_workbook("2026-06"), GES_TITLE)["years"]["2026"])
    assert set(cur["problems"]) == set(plain["problems"])
    u = _unassigned_value("2026-06")
    assert cur["totals"]["cut"]["2026-06"] == [plain["totals"]["cut"]["2026-06"][0] + u[0],
                                               plain["totals"]["cut"]["2026-06"][1] + u[1]]


def test_ges_unassigned_row_that_does_not_add_up_holds():
    from radar_salud import ges_workbook as gw

    def broken(wb):
        sin_problema(wb)
        ws = wb["Año 2026"]
        at = next(r[0].row for r in ws.iter_rows() if r[1].value == "Sin Problema de Salud Informado")
        ws.cell(at, 3, ws.cell(at, 3).value + 1)  # the row no longer adds up to the declared Total
    r = gw.parse(edit_book(fx.ges_workbook("2026-06"), broken), GES_TITLE)
    assert r["status"] == "HOLD" and r["hold_reason"] == "HOLD_GES_RECONCILIATION"


def test_ges_other_unnumbered_rows_still_hold():
    from radar_salud import ges_workbook as gw

    def other(wb):
        ws = wb["Año 2026"]
        at = next(r[0].row for r in ws.iter_rows() if str(r[1].value or "").startswith("Total"))
        ws.insert_rows(at)
        ws.cell(at, 2, "Casos sin clasificar")
    r = gw.parse(edit_book(fx.ges_workbook("2026-06"), other), GES_TITLE)
    assert r["hold_reason"] == "HOLD_GES_ROW_UNRECOGNIZED" and r["label"] == "Casos sin clasificar"


def test_ges_invalid_numeric_count_records_its_value():
    from radar_salud import ges_workbook as gw

    def negative(wb):
        ws = wb["Año 2025"]
        ws.cell(row_of(ws, 5), 3, -4)
    r = gw.parse(edit_book(fx.ges_workbook("2026-06"), negative), GES_TITLE)
    assert r["hold_reason"] == "HOLD_GES_INVALID_COUNT" and r["value"] == "-4" and r["at"].startswith("Año 2025!")
    # v5: the hold names the row, the column and the insurer (the real 2025 files held at 'Año 2025!65' with -30/-25/-22).
    assert r["insurer"] == "fonasa" and r["column"].startswith(("cut:", "ytd:")) and r["label"] and r["column_title"]


@pytest.mark.parametrize("marker", ["-", "S/N", "0", "(*)", "0.0", 0])
def test_ges_unassigned_row_with_a_marker_in_the_code_cell_is_read(marker):
    """The real SIS sheets put a marker in the N° cell of 'Sin Problema de Salud Informado' (v4 held on it): any
    non-numeric marker (or 0) is accepted for that exact label and recorded; a positive number stays a problem code."""
    from radar_salud import ges_workbook as gw

    def marked(wb):
        sin_problema(wb)
        for ws in year_sheets(wb):
            for row in ws.iter_rows():
                if row[1].value == "Sin Problema de Salud Informado":
                    row[0].value = marker
    r = gw.parse(edit_book(fx.ges_workbook("2026-06"), marked), GES_TITLE)
    assert r["status"] == "validated", r
    u = gw.expand_sheet(r["years"]["2026"])["unassigned"]
    assert u["cut"]["2026-06"] == list(_unassigned_value("2026-06"))
    assert u["code_cell"] == str(marker)  # kept in the stored parse, so the real marker can be audited


def test_ges_unassigned_label_with_a_problem_number_holds():
    """Numbered as if it were problem n+1, the row would enter the ranking: HOLD instead (review of #134)."""
    from radar_salud import ges_workbook as gw

    def numbered(wb):
        sin_problema(wb)
        ws = wb["Año 2026"]
        n = max(int(r[0].value) for r in ws.iter_rows() if isinstance(r[0].value, (int, float)) and r[0].value)
        for row in ws.iter_rows():
            if row[1].value == "Sin Problema de Salud Informado":
                row[0].value = n + 1
    r = gw.parse(edit_book(fx.ges_workbook("2026-06"), numbered), GES_TITLE)
    assert r["status"] == "HOLD" and r["hold_reason"] == "HOLD_GES_UNASSIGNED_NUMBERED"


def test_f4_with_unassigned_row_counts_it_in_the_year_to_date_total(tmp_path):
    r = fx.make_root(tmp_path / "r", readings_until="2026-06")
    books = {fx.GES_URL.format(period=p): edit_book(fx.ges_workbook(p), sin_problema) for p in fx.GES_RELEASES}
    fx.capture_all(r, fx.fetcher(r, books))
    out = f4.run(r, today=TODAY, registry=reg_ok(), llm=False)
    assert not out.get("errors"), out.get("errors")
    r0 = fx.make_root(tmp_path / "r0", readings_until="2026-06")
    fx.capture_all(r0, fx.fetcher(r0, {fx.GES_URL.format(period=p): fx.ges_workbook(p) for p in fx.GES_RELEASES}))
    base = f4.run(r0, today=TODAY, registry=reg_ok(), llm=False)
    u = _unassigned_value("2026-06")
    b = _unassigned_value("2025-12")
    extra = (u[0] - b[0]) + (u[1] - b[1])
    ytd = lambda o: sum(v["value"] for k, v in o["ficha"]["evidence"]["values"].items()  # noqa: E731
                        if k in ("ges.ytd.2026-06.fonasa", "ges.ytd.2026-06.isapre"))
    assert ytd(out) == ytd(base) + extra
    # The year-before base and the quarters are derived (cut − December base): each must move by exactly the row's own
    # flow, never by its whole cumulative since 2005 (review of #132: a base without the row passed the check above).
    v, v0 = out["ficha"]["evidence"]["values"], base["ficha"]["evidence"]["values"]
    flow = lambda a, z: tuple(x - y for x, y in zip(_unassigned_value(a), _unassigned_value(z)))  # noqa: E731
    for vid, (a, z) in {"ges.ytd.2025-06": ("2025-06", "2024-12"), "ges.q.2025T1": ("2025-03", "2024-12"),
                        "ges.q.2026T1": ("2026-03", "2025-12"), "ges.q.2026T2": ("2026-06", "2026-03")}.items():
        for i, ins in enumerate(("fonasa", "isapre")):
            assert v[f"{vid}.{ins}"]["value"] == v0[f"{vid}.{ins}"]["value"] + flow(a, z)[i], (vid, ins)
    for per, (a, z) in {"2026-06": ("2026-06", "2025-12"), "2025-06": ("2025-06", "2024-12")}.items():
        assert v[f"ges.ytd.{per}.total_comparable"]["value"] == v0[f"ges.ytd.{per}.total_comparable"]["value"] + sum(flow(a, z))
