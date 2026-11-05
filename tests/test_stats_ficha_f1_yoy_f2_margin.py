"""Roadmap increment 4 (4-nov-2026): F1 year on year and F2 margen operacional por beneficiario.

No network and no model calls.
- F1 a/a: the base is the previous-year SIS monthly cartera workbook, captured by the cartera lane into
  ``data/market/isapre_portfolio_<año>.json``. The 2025 bases used here are SYNTHETIC: the committed 2026 capture with
  every period relabelled to 2025 and counts scaled (marked in each helper). Without a base the ficha says 'a/a pendiente'.
- Capture: ``scripts/probe_source_expansion.py`` seeds the 2025 release page from the 2026 one and skips it once complete;
  ``market_sources.collect_prior_portfolio`` parses the linked 2025 workbook with the same fail-closed parser. The
  workbook is the committed native 2026 SIS file with its sheet titles relabelled to 2025 (synthetic).
- F2 margin: (ganancia bruta − GAV) / beneficiarios promedio of the same Isapres and months; every expected value is
  recomputed here from the fixture workbook values and the cartera capture, independently of the builder.
"""
import copy
import importlib.util
import io
import json
import re
import shutil
from datetime import date
from pathlib import Path
from zipfile import ZipFile

import pytest

from radar_salud import market_sources as ms
from radar_salud import stats_ficha_f1 as f1
from radar_salud import stats_ficha_f2 as f2
from radar_salud import stats_fichas as sf

import test_stats_ficha_f2 as t2

REPO = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 4)
PORTFOLIO = "data/market/isapre_portfolio.json"
F1_INPUTS = (PORTFOLIO, "data/excel/validated_series.json", "data/entities/isapres.json",
             "data/history/superintendencia_signals.json")
CODES = (63, 67, 76, 78, 80, 81, 94, 99, 107, 108)
CLOSED = (63, 76, 94)
URL_2025 = "https://www.superdesalud.gob.cl/app/uploads/fixture/estadistica-mensual-de-cartera-de-beneficiarios-2025.xlsx"


@pytest.fixture(autouse=True)
def isolated_ledgers(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_ROOT", str(tmp_path / "ledger-root"))


def committed_portfolio() -> dict:
    return json.loads((REPO / PORTFOLIO).read_text(encoding="utf-8"))


def synthetic_prior(scale=1.01, sha="c" * 64, url=URL_2025) -> dict:
    """SYNTHETIC 2025 base: the committed 2026 capture relabelled to 2025, cotizantes and cargas scaled, beneficiarios
    = cotizantes + cargas and the declared totals recomputed, so the file reconciles like a real SIS workbook."""
    data = copy.deepcopy(committed_portfolio())
    grid = {}
    for o in data["observations"]:
        o["period"] = "2025" + o["period"][4:]
        o["source_sha256"], o["source_url"] = sha, url
        if o["metric_id"] in ("cotizantes", "cargas"):
            o["value"] = int(o["value"] * scale)
        grid.setdefault((o["period"], o["official_code"]), {})[o["metric_id"]] = o
    for cell in grid.values():
        cell["beneficiarios"]["value"] = cell["cotizantes"]["value"] + cell["cargas"]["value"]
    for c in data["coverage"]:
        c["period"] = "2025" + c["period"][4:]
        c["total_beneficiaries"] = sum(cell["beneficiarios"]["value"] for (p, _), cell in grid.items() if p == c["period"])
    data.update(published_at="2026-01-27", reporting_period="2025-08", year=2025)
    return data


def f1_root(tmp_path, prior=None) -> Path:
    root = tmp_path / "f1"
    for rel in F1_INPUTS:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, root / rel)
    if prior is not None:
        (root / "data/market/isapre_portfolio_2025.json").write_text(json.dumps(prior, ensure_ascii=False), encoding="utf-8")
    return root


def benef(data, period) -> dict[int, int]:
    return {o["official_code"]: o["value"] for o in data["observations"] if o["metric_id"] == "beneficiarios" and o["period"] == period}


# ---------------------------------------------------------------------------------------------
# F1 · a/a


def test_without_the_previous_year_base_the_ficha_says_aa_pendiente(tmp_path):
    root = f1_root(tmp_path)
    pkg = f1.build_package(root)
    assert pkg["yoy"] == {"status": "pendiente", "reason": "base_2025_no_capturada"}
    assert not any(".yoy" in vid or vid.startswith("aa.") for vid in pkg["values"])
    res = f1.run(root, today=TODAY, llm=False)
    assert res["status"] == "pass", res.get("errors")
    fi = res["ficha"]
    assert fi["kpis"][0]["badge"].endswith("a/a pendiente")
    n1 = next(n["text"] for n in fi["notes"] if n["id"] == "n1")
    assert "A/a pendiente" in n1 and "no la estima" in n1
    assert "2025" not in fi["dek"] and {s["key"] for s in fi["sources"]} == {"cartera", "movilidad", "suscripciones"}


def test_yoy_uses_the_same_month_a_year_earlier_from_the_captured_base(tmp_path):
    prior = synthetic_prior()
    root = f1_root(tmp_path, prior)
    res = f1.run(root, today=TODAY, llm=False)
    assert res["status"] == "pass", res.get("errors")
    fi = res["ficha"]
    v = fi["evidence"]["values"]
    now, before = benef(committed_portfolio(), "2026-08"), benef(prior, "2025-08")
    yoy = sum(now.values()) - sum(before.values())
    assert v["sistema.beneficiarios.yoy"]["value"] == yoy
    assert v["sistema.beneficiarios.yoy_pct"]["value"] == pytest.approx(yoy / sum(before.values()) * 100)
    for c in CODES:
        assert v[f"delta.{c}.yoy"]["value"] == now[c] - before[c]
        assert v[f"aa.cartera.{c}.beneficiarios.2025-08"]["source"] == "cartera_prev"
    assert v["delta.cerradas.yoy"]["value"] == sum(now[c] - before[c] for c in CLOSED)
    # Shown: KPI line, dek clause (≤ 40 words), 'Ver datos' columns, the hashed 2025 source; badge without 'pendiente'.
    kpi = fi["kpis"][0]
    assert kpi["lines"][-1] == f"{sf.fmt_signed(yoy)} vs. agosto 2025 ({sf.fmt_dec(yoy / sum(before.values()) * 100, 2, signed=True)}%)"
    assert "pendiente" not in kpi["badge"]
    assert f"{sf.fmt_int(abs(yoy))} {'menos' if yoy < 0 else 'más'} que en agosto 2025" in fi["dek"]
    assert len(fi["dek"].split()) <= 40
    table = next(t for t in fi["tabs"] if t["id"] == "isapres")["charts"][0]["table"]
    assert table["columns"][-2:] == ["Cambio vs. agosto 2025", "% a/a"]
    assert table["rows"][-1][-2] == sf.fmt_signed(yoy)
    src = next(s for s in fi["sources"] if s["key"] == "cartera_prev")
    assert src["url"] == URL_2025 and src["sha256"] == "c" * 64
    assert fi["verification"]["verdict"] == "PASS"
    assert "planilla mensual 2025" in next(n["text"] for n in fi["notes"] if n["id"] == "n1")


def _edit(prior, fn):
    fn(prior)
    return prior


@pytest.mark.parametrize("edit,reason", [
    (lambda d: d["coverage"][-1].update(total_beneficiaries=d["coverage"][-1]["total_beneficiaries"] + 1), "base_total_2025-08"),
    (lambda d: next(o for o in d["observations"] if o["metric_id"] == "cargas").update(source_sha256="d" * 64),
     "base_2025_mixed_release"),
    (lambda d: d["observations"].__setitem__(slice(None), [o for o in d["observations"] if o["period"] != "2025-08"]),
     "base_sin_2025-08"),
    (lambda d: d["observations"][0].update(period="2024-12"), "base_2025_period_outside_year"),
    (lambda d: [o.update(source_sha256="nohash") for o in d["observations"]], "base_2025_sin_hash"),
    (lambda d: next(o for o in d["observations"] if o["period"] == "2025-08" and o["metric_id"] == "cargas").update(value=1),
     None),  # cotizantes + cargas ≠ beneficiarios
])
def test_a_base_that_does_not_reconcile_is_never_used(tmp_path, edit, reason):
    root = f1_root(tmp_path, _edit(synthetic_prior(), edit))
    pkg = f1.build_package(root)
    assert pkg["yoy"]["status"] == "pendiente"
    assert pkg["yoy"]["reason"] == reason if reason else pkg["yoy"]["reason"].startswith("base_cot_plus_cargas_2025-08")
    assert "sistema.beneficiarios.yoy" not in pkg["values"]
    res = f1.run(root, today=TODAY, llm=False)
    assert res["status"] == "pass" and res["ficha"]["kpis"][0]["badge"].endswith("a/a pendiente")


# ---------------------------------------------------------------------------------------------
# Capture of the previous-year workbook


def probe():
    spec = importlib.util.spec_from_file_location("probe", REPO / "scripts/probe_source_expansion.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_probe_seeds_the_previous_year_page_from_the_current_one_and_skips_it_when_complete(tmp_path):
    mod = probe()
    seeds = json.loads((REPO / "config/source_expansion_runtime.json").read_text(encoding="utf-8"))["seeds"]
    out = [s for s in mod.period_seeds(seeds, date(2026, 11, 4), root=tmp_path) if s["kind"] == "cartera_release_prior"]
    assert [s["url"] for s in out] == [
        "https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2025/"]
    assert urlhost(out[0]["url"]) in mod.HOSTS and out[0]["package"] == "isapres"
    # Once the 12 months of 2025 are stored from one hash, the page is no longer fetched every day.
    full = synthetic_prior()
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    full["coverage"] = [{"period": p, "total_beneficiaries": 1} for p in months]
    (tmp_path / "data/market").mkdir(parents=True)
    (tmp_path / "data/market/isapre_portfolio_2025.json").write_text(json.dumps(full), encoding="utf-8")
    assert not [s for s in mod.period_seeds(seeds, date(2026, 11, 4), root=tmp_path) if s["kind"] == "cartera_release_prior"]
    # Fetching still goes through robots.txt and the host allowlist (no bypass for the new seed).
    mod.ROBOTS["https://www.superdesalud.gob.cl"] = ("disallow_all", None)
    receipt, _ = mod.fetch(out[0]["url"], tmp_path / "cap")
    assert receipt["transport_ok"] is False and receipt["blocked_reason"] == "robots_disallowed"


def urlhost(url):
    from urllib.parse import urlsplit
    return urlsplit(url).hostname


class FakeCaptures:
    """Receipts as the probe writes them; bodies kept in memory (no network)."""

    def __init__(self, receipts, bodies):
        self.receipts, self.bodies = receipts, bodies

    def body(self, r):
        return self.bodies[r["url"]]

    def html(self, r):
        return self.bodies[r["url"]].decode("utf-8")


PAGE_2025 = "https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-mensual-de-cartera-de-beneficiarios-del-sistema-isapre-ano-2025/"
PAGE_HTML = ("<html><body><p>Fecha de publicación: 27 de enero de 2026</p><p>Información actualizada a agosto 2025</p>"
             "</body></html>")


def workbook_2025() -> bytes:
    """SYNTHETIC: the committed native SIS 2026 cartera workbook (cached values, formulas dropped) with each month's
    title (A4, a formula on the year in the SIS file) written as '<MES> 2025'."""
    from openpyxl import load_workbook
    with ZipFile(REPO / "data/audits/source_expansion/native_initial.zip") as z:
        receipts = json.loads(z.read("receipts.json"))["receipts"]
        book = next(r for r in receipts if ".xlsx" in r["url"])
        wb = load_workbook(io.BytesIO(z.read(book["body_file"])), data_only=True)
    for ws in wb.worksheets:
        if isinstance(ws["A4"].value, str) and re.fullmatch(r"\w+ 2026", ws["A4"].value.strip()):
            ws["A4"] = ws.title.upper() + " 2025"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def entities():
    return json.loads((REPO / "data/entities/isapres.json").read_text(encoding="utf-8"))["entities"]


def page_receipt(links, ok=True):
    return {"package": "isapres", "kind": "cartera_release_prior", "url": PAGE_2025, "transport_ok": ok,
            "links": [{"url": u, "label": "Descargar"} for u in links]}


def book_receipt(url, sha):
    return {"package": "isapres", "kind": "Descargar", "url": url, "transport_ok": True, "sha256": sha,
            "completed_at": "2026-11-05T00:30:00+00:00"}


def test_collector_writes_the_previous_year_file_with_its_hash(tmp_path):
    import hashlib
    body = workbook_2025()
    sha = hashlib.sha256(body).hexdigest()
    caps = FakeCaptures([page_receipt([URL_2025, "https://www.superdesalud.gob.cl/app/uploads/x-regional-202508.xlsx"]),
                         book_receipt(URL_2025, sha)], {PAGE_2025: PAGE_HTML.encode(), URL_2025: body})
    out = ms.collect_prior_portfolio(caps, tmp_path, entities())
    assert out["status"] == "ok" and out["year"] == 2025 and out["sha256"] == sha
    data = json.loads((tmp_path / "data/market/isapre_portfolio_2025.json").read_text(encoding="utf-8"))
    assert {o["source_sha256"] for o in data["observations"]} == {sha}
    assert data["coverage"][-1]["period"] == "2025-08" and data["reporting_period"] == "2025-08"
    # The F1 ficha then compares August with August, from that file.
    root = f1_root(tmp_path)
    shutil.copy(tmp_path / "data/market/isapre_portfolio_2025.json", root / "data/market/isapre_portfolio_2025.json")
    pkg = f1.build_package(root)
    assert pkg["yoy"] == {"status": "ok", "period": "2025-08"}
    assert pkg["sources"]["cartera_prev"]["sha256"] == sha


@pytest.mark.parametrize("receipts,why", [
    ([], "not_in_capture"),
    ([page_receipt([URL_2025], ok=False)], "page_transport_failed"),
    ([page_receipt([])], "workbook_links:0"),
    ([page_receipt([URL_2025, URL_2025.replace(".xlsx", "-1.xlsx")])], "workbook_links:2"),
    ([page_receipt([URL_2025])], "workbook_not_captured"),
])
def test_collector_fails_closed_and_keeps_the_stored_file(tmp_path, receipts, why):
    stored = tmp_path / "data/market/isapre_portfolio_2025.json"
    stored.parent.mkdir(parents=True)
    stored.write_text("{\"keep\": true}", encoding="utf-8")
    out = ms.collect_prior_portfolio(FakeCaptures(receipts, {PAGE_2025: PAGE_HTML.encode()}), tmp_path, entities())
    assert out["status"] == ("not_in_capture" if why == "not_in_capture" else "error")
    assert why == "not_in_capture" or out["reason"] == why
    assert json.loads(stored.read_text(encoding="utf-8")) == {"keep": True}


def test_collector_refuses_a_workbook_of_another_year(tmp_path):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(workbook_2025()))
    wb["Enero"]["A4"] = "ENERO 2024"
    buf = io.BytesIO()
    wb.save(buf)
    caps = FakeCaptures([page_receipt([URL_2025]), book_receipt(URL_2025, "e" * 64)], {PAGE_2025: PAGE_HTML.encode(), URL_2025: buf.getvalue()})
    out = ms.collect_prior_portfolio(caps, tmp_path, entities())
    assert out == {"status": "error", "year": 2025, "reason": "period_outside_year"}
    assert not (tmp_path / "data/market/isapre_portfolio_2025.json").exists()


# ---------------------------------------------------------------------------------------------
# F2 · margen operacional por beneficiario


F2_CODES = [c for c in t2.CODES if c != "108"]  # Esencial excluded by the Dirección rule


def f2_root(tmp_path, portfolio=None, prev=False, prior=None):
    root = t2.make_root(tmp_path, prev=prev)
    if portfolio is not False:
        (root / "data/market").mkdir(parents=True, exist_ok=True)
        (root / PORTFOLIO).write_text(json.dumps(portfolio or committed_portfolio(), ensure_ascii=False), encoding="utf-8")
    if prior is not None:
        (root / "data/market/isapre_portfolio_2025.json").write_text(json.dumps(prior, ensure_ascii=False), encoding="utf-8")
    files = {t2.URL: t2.workbook()}
    if prev:
        files[t2.URL_PREV] = t2.workbook(t2.prev_data(), year="2025")
    t2.capture(root, files=files, max_new=2)
    res = t2.run(root)
    assert res["status"] == "pass", res.get("errors")
    return root, res["ficha"]


def expected_margin(data, port, year="2026"):
    """(ganancia bruta − GAV) in pesos / mean of the January–March stocks, per Isapre and for the 9 Isapres together."""
    d = t2.full(data)
    avg = {c: sum(benef(port, f"{year}-{m:02d}")[int(c)] for m in (1, 2, 3)) / 3 for c in F2_CODES}
    op = {c: (d["bruta"][t2.CODES.index(c)] - d["gav"][t2.CODES.index(c)]) * 1000 for c in F2_CODES}  # miles → pesos
    out = {c: op[c] / avg[c] for c in F2_CODES}
    out["sistema"] = sum(op.values()) / sum(avg.values())
    return out, avg


def test_margin_per_beneficiary_uses_the_same_isapres_and_months(tmp_path):
    _, fi = f2_root(tmp_path)
    ev = fi["evidence"]["values"]
    want, avg = expected_margin(t2.REAL, committed_portfolio())
    for w, m in want.items():
        assert ev[f"margen_beneficiario.{w}.2026-03"]["value"] == pytest.approx(m, rel=1e-12)
    assert ev["benef_prom.sistema.2026-03"]["value"] == pytest.approx(sum(avg.values()))
    assert not any(vid.startswith(("cartera.108.", "benef_prom.108", "margen_beneficiario.108")) for vid in ev)
    for c in F2_CODES:  # the denominator traces to three captured month-end stocks with locators
        ins = ev[f"benef_prom.{c}.2026-03"]["inputs"]
        assert ins == [f"cartera.{c}.beneficiarios.2026-0{m}" for m in (1, 2, 3)]
        assert all(ev[i]["source"] == "cartera" and re.fullmatch(r".+!E\d+", ev[i]["locator"]) for i in ins)
    tab = next(t for t in fi["tabs"] if t["id"] == "resultados")
    card = tab["kpis"][0]
    assert card["id"] == "tema-margen" and card["value"] == f2.money(want["sistema"])
    assert card["lines"][0] == f"enero–marzo 2026; {sf.fmt_int(sum(avg.values()))} beneficiarios promedio"
    table = tab["charts"][-1]["table"]
    assert table["columns"][-3:] == ["Res. operacional (MM$)", "Benef. promedio", "$ por beneficiario, enero–marzo (pesos)"]
    assert table["rows"][-1][-1] == f2.money(want["sistema"])
    n4 = next(n["text"] for n in fi["notes"] if n["id"] == "n4")
    assert "ganancia bruta − gastos de administración" in n4 and "Denominador: promedio simple" in n4
    assert {s["key"] for s in fi["sources"]} >= {"fefi", "cartera"}
    assert fi["verification"]["verdict"] == "PASS" and len(fi["dek"].split()) <= 40


def test_money_is_sign_aware():
    assert f2.money(48471.6) == "$48.472" and f2.money(-4322.3) == "−$4.322" and f2.money(0.2) == "$0"


def test_without_the_cartera_the_margin_is_held_and_the_ficha_still_publishes(tmp_path):
    _, fi = f2_root(tmp_path, portfolio=False)
    assert not any(v.startswith(("margen_beneficiario.", "benef_prom.")) for v in fi["evidence"]["values"])
    assert not next(t for t in fi["tabs"] if t["id"] == "resultados")["kpis"]
    n4b = next(n["text"] for n in fi["notes"] if n["id"] == "n4b")
    assert "retenido para marzo 2026" in n4b and "no lo aproxima" in n4b


def _drop_month(port, month):
    port["observations"] = [o for o in port["observations"] if o["period"] != month]
    port["coverage"] = [c for c in port["coverage"] if c["period"] != month]
    return port


def _swap_code(port, month, code, new):
    for o in port["observations"]:
        if o["period"] == month and o["official_code"] == code:
            o["official_code"] = new
    return port


@pytest.mark.parametrize("edit,reason", [
    (lambda p: _drop_month(p, "2026-02"), "cartera_sin_mes:2026-02"),
    (lambda p: _swap_code(p, "2026-02", 67, 999), "perimetro_distinto:2026-02:67"),
    (lambda p: p["coverage"][0].update(total_beneficiaries=p["coverage"][0]["total_beneficiaries"] - 1), "cartera_total:2026-01"),
    (lambda p: p["observations"][0].update(source_sha256="f" * 64), "cartera_mixed_release"),
])
def test_a_period_or_perimeter_that_does_not_match_exactly_holds_the_figure(tmp_path, edit, reason):
    port = committed_portfolio()
    edit(port)
    root, fi = f2_root(tmp_path, portfolio=port)
    pkg = f2.build_package(root, t2.registry())
    assert {"period": "2026-03", "reason": reason} in pkg["margin"]["holds"]
    assert "margen_beneficiario.sistema.2026-03" not in fi["evidence"]["values"]
    assert any(n["id"] == "n4b" for n in fi["notes"]) and fi["verification"]["verdict"] == "PASS"


def test_margin_year_on_year_needs_the_previous_year_cartera(tmp_path):
    # FEFI 2025-03 verified, cartera 2025 missing: the 2026 margin shows, its comparison says 'a/a pendiente'.
    _, fi = f2_root(tmp_path / "a", prev=True)
    card = next(t for t in fi["tabs"] if t["id"] == "resultados")["kpis"][0]
    assert card["lines"][-1] == "a/a pendiente"
    assert "retenido para marzo 2025" in next(n["text"] for n in fi["notes"] if n["id"] == "n4b")
    # With the (synthetic) 2025 cartera: both levels and the absolute change, never a %.
    prior = synthetic_prior()
    _, fi = f2_root(tmp_path / "b", prev=True, prior=prior)
    ev = fi["evidence"]["values"]
    want_prev, _ = expected_margin(t2.prev_data(), prior, year="2025")
    want_now, _ = expected_margin(t2.REAL, committed_portfolio())
    assert ev["margen_beneficiario.sistema.2025-03"]["value"] == pytest.approx(want_prev["sistema"], rel=1e-12)
    assert ev["margen_beneficiario.sistema.delta"]["value"] == pytest.approx(want_now["sistema"] - want_prev["sistema"], rel=1e-9)
    assert not any(v.startswith("margen_beneficiario.") and v.endswith(".pct") for v in ev)
    assert ev["cartera.67.beneficiarios.2025-01"]["source"] == "cartera_prev"
    card = next(t for t in fi["tabs"] if t["id"] == "resultados")["kpis"][0]
    assert card["lines"][-1] == f"enero–marzo 2025: {f2.money(want_prev['sistema'])}"
    assert {s["key"] for s in fi["sources"]} >= {"fefi", "fefi_prev", "cartera", "cartera_prev"}
    assert not any(n["id"] == "n4b" for n in fi["notes"]) and fi["verification"]["verdict"] == "PASS"


def test_registry_states_the_margin_formula_and_denominator():
    k = sf.load_registry()["families"]["F2"]["kpis"]["margen_beneficiario"]
    assert "ganancia bruta − gastos de administración" in k["formula"] and "promedio simple" in k["denominator"].lower()
    assert sf.load_registry()["families"]["F2"]["builder_version"] == f2.BUILDER_VERSION
    assert sf.load_registry()["families"]["F1"]["builder_version"] == f1.BUILDER_VERSION
