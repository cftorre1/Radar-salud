"""F1 v9 · Concentración (3-nov-2026): market share and HHI of the open Isapres.

No network and no model calls. Inputs are the committed SIS cartera capture (``data/market/isapre_portfolio.json``)
copied to a temporary root; every share and HHI asserted here is recomputed in this file from the integer beneficiary
counts, independently of the builder. HOLD paths are produced by editing the copy (marked as synthetic in each test).
"""
import copy
import json
import re
import shutil
from datetime import date
from fractions import Fraction
from pathlib import Path

import pytest

from radar_salud import stats_ficha_f1 as f1, stats_fichas as sf

REPO = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 28)
INPUTS = ("data/market/isapre_portfolio.json", "data/excel/validated_series.json", "data/entities/isapres.json",
          "data/history/superintendencia_signals.json")
OPEN = (67, 78, 80, 81, 99, 107, 108)
CLOSED = (63, 76, 94)


@pytest.fixture(autouse=True)
def isolated_ledgers(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_ROOT", str(tmp_path / "ledger-root"))


@pytest.fixture
def root(tmp_path):
    for rel in INPUTS:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def portfolio(root):
    return json.loads((root / INPUTS[0]).read_text(encoding="utf-8"))


def save(root, data):
    (root / INPUTS[0]).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def benef(data, period):
    return {o["official_code"]: o["value"] for o in data["observations"]
            if o["metric_id"] == "beneficiarios" and o["period"] == period}


def expected(data, period):
    """Shares (%) of the open Isapres and HHI, recomputed here from the integer counts."""
    b = benef(data, period)
    den = sum(b[c] for c in OPEN)
    shares = {c: Fraction(b[c] * 100, den) for c in OPEN}
    return shares, sum(s * s for s in shares.values())


def test_shares_and_hhi_use_only_the_open_isapres_every_month(root):
    data = portfolio(root)
    pkg = f1.build_package(root)
    assert pkg["reconciliation"]["ok"], pkg["reconciliation"]["failures"]
    v = pkg["values"]
    for p in pkg["periods"]:
        shares, h = expected(data, p)
        assert sum(shares.values()) == 100
        for c in OPEN:
            assert v[f"share.{c}.{p}"]["value"] == pytest.approx(float(shares[c]), abs=1e-12)
            assert v[f"hhi_aporte.{c}.{p}"]["value"] == pytest.approx(float(shares[c] ** 2), abs=1e-9)
        assert v[f"hhi.{p}"]["value"] == pytest.approx(float(h), abs=1e-9)
        assert {int(i.split(".")[1]) for i in v[f"hhi.{p}"]["inputs"]} == set(OPEN)
        for c in CLOSED:  # closed Isapres never get a share or an HHI part
            assert f"share.{c}.{p}" not in v and f"hhi_aporte.{c}.{p}" not in v
    t, base = pkg["period"], pkg["base_period"]
    assert v["hhi.delta"]["value"] == pytest.approx(v[f"hhi.{t}"]["value"] - v[f"hhi.{base}"]["value"])
    assert v["hhi.delta_shown"]["value"] == round(v[f"hhi.{t}"]["value"]) - round(v[f"hhi.{base}"]["value"])
    assert any("HHI = Σ s_i²" in c for c in pkg["reconciliation"]["checks"])


def test_hhi_exact_is_an_independent_path_to_the_same_number():
    counts = [573597, 352659, 139782, 299432, 544534, 459075, 59893]
    shares = [b / sum(counts) * 100 for b in counts]
    assert float(f1.hhi_exact(counts)) == pytest.approx(f1.hhi(shares), abs=1e-9)
    assert f1.hhi_exact([10]) == 10000 and f1.hhi_exact([1, 1]) == 5000


def test_concentration_topic_shows_the_series_first_then_each_isapre(root):
    res = f1.run(root, today=TODAY, llm=False)
    assert res["status"] == "pass", res.get("errors")
    fi = res["ficha"]
    ids = [t["id"] for t in fi["tabs"]]
    assert ids.index("concentracion") == ids.index("regional") - 1 and 2 <= len(ids) <= 6
    tab = next(t for t in fi["tabs"] if t["id"] == "concentracion")
    assert tab["label"] == "Concentración" and [c["id"] for c in tab["charts"]] == ["f1-hhi", "f1-hhi-aporte"]
    ev = fi["evidence"]["values"]
    t = fi["period"]
    h, d = ev[f"hhi.{t}"]["value"], ev["hhi.delta_shown"]["value"]
    assert tab["index_line"] == f"HHI {sf.fmt_int(h)} puntos · {sf.fmt_signed(d)} desde enero"
    assert tab["index_refs"] == [f"hhi.{t}", "hhi.delta_shown"]
    line, parts = tab["charts"]
    months = sorted(k.split(".")[1] for k in ev if re.fullmatch(r"hhi\.\d{4}-\d{2}", k))
    assert months[0] == "2026-01" and months[-1] == t
    assert line["form"] == "line" and [r["ref"] for r in line["rows"]] == [f"hhi.{p}" for p in months]
    assert parts["form"] == "bars" and len(parts["rows"]) == 7
    assert parts["table"]["rows"][-1] == ["HHI abiertas", "", sf.fmt_int(h)]
    assert [r[0] for r in parts["table"]["rows"][:-1]] == [r["label"] for r in parts["rows"]]
    assert "solo las 7 Isapres abiertas" in parts["source"]
    n2c = next(n["text"] for n in fi["notes"] if n["id"] == "n2c")
    assert "el HHI por grupo controlador queda pendiente" in n2c and "no aplica umbrales" in n2c
    # No interpretation thresholds without an official FNE source cited in the notes.
    shown = " ".join(sf.displayed_texts(fi))
    assert not re.search(r"\b(1\.500|2\.500|moderadamente|altamente) ?(concentrad|puntos)?", shown), shown
    assert "FNE" not in shown
    assert fi["verification"]["verdict"] == "PASS" and fi["builder_version"] == f1.BUILDER_VERSION


def edit_share(root, period, code, *, delta=0.0, population=None):
    """Synthetic edit of the copied capture: one captured beneficiary_share value or its population."""
    data = portfolio(root)
    for o in data["observations"]:
        if o["metric_id"] == "beneficiary_share" and o["period"] == period and o["official_code"] == code:
            o["value"] += delta
            if population:
                o["population"] = population
    save(root, data)


@pytest.mark.parametrize("code,delta,population,why", [
    (67, 0.01, None, "share_capture_mismatch:2026-08"),
    (63, 0.0, "open", "share_population_mismatch:2026-08"),  # a closed Isapre labelled 'open' never enters silently
    (78, 0.0, "closed", "share_population_mismatch:2026-08"),
])
def test_a_captured_share_that_does_not_reconcile_holds(root, code, delta, population, why):
    edit_share(root, "2026-08", code, delta=delta, population=population)
    pkg = f1.build_package(root)
    assert pkg["reconciliation"]["ok"] is False and pkg["reconciliation"]["failures"] == [why]
    assert f1.run(root, today=TODAY, llm=False)["status"] == "hold"


def test_captured_shares_must_add_up_to_100(root):
    edit_share(root, "2026-03", 99, delta=0.06)
    fails = f1.build_package(root)["reconciliation"]["failures"]
    assert "captured_share_sum_not_100:2026-03" in fails and "share_capture_mismatch:2026-03" in fails


def test_concentration_failures_flags_shares_off_100_and_closed_inputs(root):
    pkg = f1.build_package(root)
    data = portfolio(root)
    cap = {(o["period"], o["official_code"]): o for o in data["observations"] if o["metric_id"] == "beneficiary_share"}
    periods, opn, cls = pkg["periods"], set(OPEN), set(CLOSED)
    assert f1.concentration_failures(pkg["values"], cap, periods, opn, cls) == []
    bad = copy.deepcopy(pkg["values"])
    bad["share.80.2026-05"]["value"] += 0.06
    assert "share_sum_not_100:2026-05" in f1.concentration_failures(bad, cap, periods, opn, cls)
    bad = copy.deepcopy(pkg["values"])
    bad["hhi.2026-02"]["inputs"].append("share.63.2026-02")
    assert f1.concentration_failures(bad, cap, periods, opn, cls) == ["hhi_codes_not_open:2026-02"]


def test_an_hhi_that_differs_from_the_exact_recomputation_holds(root, monkeypatch):
    """Mutation guard: a wrong HHI formula (here off by 0,01 point) must HOLD; removing the recomputation check from
    build_package makes this test fail."""
    monkeypatch.setattr(f1, "hhi", lambda shares: sum(x * x for x in shares) + 0.01)
    pkg = f1.build_package(root)
    assert pkg["reconciliation"]["ok"] is False
    assert pkg["reconciliation"]["failures"] == [f"hhi_recompute_mismatch:{p}" for p in pkg["periods"]]
    res = f1.run(root, today=TODAY, llm=False)
    assert res["status"] == "hold" and not (root / "data/stats_fichas/live/f1_cartera.json").exists()


def test_new_builder_version_republishes_without_a_new_paid_call(root):
    first = f1.run(root, today=TODAY, llm=False)
    sf.publish(first, root)
    live = root / "data/stats_fichas/live/f1_cartera.json"
    old = json.loads(live.read_text(encoding="utf-8"))
    old["builder_version"] = "f1_index_topic_v8"
    old["lectura"] = {"status": "verifier_fail", "text": None}  # a paid attempt already made for this release
    live.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    calls = []
    res = f1.run(root, today=TODAY, llm=True, model_call=lambda *a, **k: calls.append(1),
                 budget=lambda w: calls.append(w) or (True, "ok"))
    assert res["status"] == "pass" and "format_update" in res["ficha"]["triggers"] and calls == []
    assert any(t["id"] == "concentracion" for t in res["ficha"]["tabs"])
    assert sf.load_registry()["families"]["F1"]["builder_version"] == f1.BUILDER_VERSION



@pytest.mark.lectura_retired
def test_retired_lectura_never_calls_the_model_even_on_a_retry(root):
    """Dirección 12-nov-2026: no «Lectura Alicanto». Production switch on: no model call, no retry, no omitted-note."""
    assert sf.LECTURA_RETIRED is True
    first = f1.run(root, today=TODAY, llm=False)
    sf.publish(first, root)
    live = root / "data/stats_fichas/live/f1_cartera.json"
    old = json.loads(live.read_text(encoding="utf-8"))
    old["lectura"] = {"status": "not_attempted", "text": None}  # the old retry trigger
    live.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    calls = []
    res = f1.run(root, today=TODAY, llm=True, model_call=lambda *a, **k: calls.append(1),
                 budget=lambda w: calls.append(w) or (True, "ok"))
    assert calls == []
    assert res["status"] in ("no_change", "pass")
    old["builder_version"] = "f1_index_topic_v1"
    live.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    res = f1.run(root, today=TODAY, llm=True, model_call=lambda *a, **k: calls.append(1),
                 budget=lambda w: calls.append(w) or (True, "ok"))
    assert res["status"] == "pass" and calls == []
    assert res["ficha"]["lectura"]["status"] == "retired" and "Lectura Alicanto omitida" not in res["ficha"]["machine_note"]
