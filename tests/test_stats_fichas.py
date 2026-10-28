"""Statistics fichas (Dirección 28-oct-2026): formulas, denominators, triggers, verifier, HOLD, GES.

No network and no model calls: the Lectura model is always a fake.
"""
import json
import shutil
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from radar_salud import data_insights, stats_ficha_f1 as f1, stats_fichas as sf

REPO = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 28)
INPUTS = ("data/market/isapre_portfolio.json", "data/excel/validated_series.json", "data/entities/isapres.json",
          "data/history/superintendencia_signals.json")


@pytest.fixture(autouse=True)
def isolated_ledgers(tmp_path, monkeypatch):
    """Budget counters (ai_budget) write under RADAR_ROOT: never touch the real data/ai_usage ledger."""
    monkeypatch.setenv("RADAR_ROOT", str(tmp_path / "ledger-root"))


@pytest.fixture
def root(tmp_path):
    for rel in INPUTS:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp_path / rel)
    return tmp_path


def portfolio(root):
    return json.loads((root / INPUTS[0]).read_text(encoding="utf-8"))


def save_portfolio(root, data):
    (root / INPUTS[0]).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def fake_model(text, cost=0.0004):
    calls = []

    def call(prompt, **kw):
        calls.append({"prompt": prompt, **kw})
        return SimpleNamespace(output={"lectura": text}, model="gpt-5.6-luna", estimated_cost_usd=cost, response_id="r1")
    call.calls = calls
    return call


ALLOW = lambda worst: (True, "ok")  # noqa: E731
GOOD = ("Para la base de ingresos importan más los cotizantes que los beneficiarios: quien paga se mantiene y lo que "
        "se reduce son cargas. Para la competencia, la pregunta es si Banmédica estabiliza su cartera antes de que "
        "Esencial y Nueva Masvida consoliden lo ganado.")


# ---------------------------------------------------------------------------------------------
# Formulas and denominators


def test_package_formulas_use_stocks_open_denominator_and_reconcile(root):
    p = f1.build_package(root)
    v = p["values"]
    assert p["reconciliation"]["ok"] is True and p["period"] == "2026-08"
    assert v["sistema.beneficiarios.2026-08"]["value"] == 2486683 == v["cartera.declarado.beneficiarios.2026-08"]["value"]
    assert v["sistema.beneficiarios.mm.2026-08"]["value"] == -814
    # Stock rule: the year change is end minus start, never a sum of months.
    assert v["sistema.beneficiarios.ytd"]["value"] == 2486683 - 2514038 == -27355
    assert v["sistema.cotizantes.mm.2026-08"]["value"] == 1296 and v["sistema.cotizantes.mm.2026-07"]["value"] == 475
    # Market share: only the 7 open Isapres in the denominator.
    assert v["abiertas.beneficiarios.2026-08"]["value"] == 2419986
    assert len(v["abiertas.beneficiarios.2026-08"]["inputs"]) == 7
    share_sum = sum(v[f"share.{c}.2026-08"]["value"] for c in (67, 78, 80, 81, 99, 107, 108))
    assert abs(share_sum - 100) < 1e-9
    assert "share.63.2026-08" not in v  # closed Isapres never get a market share
    assert round(v["contrib.99"]["value"]) == 77 and round(v["cargas.contrib"]["value"]) == 78
    assert round(v["mezcla.2026-08"]["value"], 3) == 0.603 and round(v["mezcla.2026-01"]["value"], 3) == 0.615
    assert v["movilidad.diferencia_intervalo"]["value"] == -17700
    for item in v.values():  # provenance on every captured value
        if item["kind"] == "captured":
            assert item["locator"] and item["source"] in p["sources"]
    assert all(sf.HEX64.fullmatch(s["sha256"]) for s in p["sources"].values())


def test_contribution_not_computed_when_system_change_is_small(root):
    data = portfolio(root)
    # Make Aug equal Jan for every code: |Δ system| = 0 < 5.000.
    jan = {(o["official_code"], o["metric_id"]): o["value"] for o in data["observations"] if o["period"] == "2026-01"}
    for o in data["observations"]:
        if o["period"] == "2026-08" and o["metric_id"] in ("beneficiarios", "cotizantes", "cargas"):
            o["value"] = jan[(o["official_code"], o["metric_id"])]
    data["coverage"][-1]["total_beneficiaries"] = data["coverage"][0]["total_beneficiaries"]
    save_portfolio(root, data)
    p = f1.build_package(root)
    assert p["reconciliation"]["ok"] is True
    assert not any(k.startswith("contrib.") for k in p["values"])
    assert not any(f["type"] == "concentration" for f in p["findings"])


def test_ficha_shows_august_and_keeps_yoy_pending(root):
    r = f1.run(root, today=TODAY, llm=False)
    assert r["status"] == "pass"
    fi = r["ficha"]
    assert fi["period"] == "2026-08" and "agosto 2026" in fi["kicker_meta"]
    assert fi["headline_type"] == "record_low_decline" and "814" in fi["headline"]
    assert "2.486.683" in fi["dek"] and len(fi["dek"].split()) <= 40
    assert fi["kpis"][0]["badge"] == "Sin umbral cruzado · a/a pendiente"
    assert any("pendiente" in n["text"] for n in fi["notes"])
    tabs = {t["id"]: t for t in fi["tabs"]}
    assert list(tabs) == ["total", "isapres", "mezcla", "movilidad", "regional"]
    assert [c["form"] for c in tabs["total"]["charts"]] == ["columns_signed", "line"]
    assert [row["label"] for row in tabs["total"]["charts"][0]["rows"]][-1] == "Ago"
    share = tabs["isapres"]["charts"][1]
    assert share["form"] == "dots" and len(share["rows"]) == 7  # open Isapres only
    assert tabs["regional"]["status"] == "pendiente" and tabs["regional"]["links"][0]["url"].endswith("a-nivel-regional-agosto-2026/")
    assert fi["verification"]["verdict"] == "PASS" and fi["featured"] is True
    assert fi["verification"]["lenses"] == {"data": "PASS", "editorial": "PASS", "ui": "PASS", "business": "PASS"}
    assert fi["lectura"]["status"] == "not_attempted"


# ---------------------------------------------------------------------------------------------
# Triggers and HOLD


def test_triggers_new_period_then_no_change_then_revision(root):
    first = f1.run(root, today=TODAY, llm=False)
    sf.publish(first, root)
    again = f1.run(root, today=TODAY, llm=False)
    assert again["status"] == "no_change"
    # A new release that revises July by more than 0,5 % republishes with a 'revisado' note.
    data = portfolio(root)
    row = next(o for o in data["observations"] if o["period"] == "2026-07" and o["official_code"] == 99 and o["metric_id"] == "cargas")
    benef = next(o for o in data["observations"] if o["period"] == "2026-07" and o["official_code"] == 99 and o["metric_id"] == "beneficiarios")
    row["value"] += 20000
    benef["value"] += 20000
    data["coverage"][-2]["total_beneficiaries"] += 20000
    for o in data["observations"]:
        o["source_sha256"] = "b" * 64
    save_portfolio(root, data)
    revised = f1.run(root, today=TODAY, llm=False)
    assert revised["status"] == "pass"
    assert "revision" in revised["decision"]["triggers"]
    assert any(n["text"].startswith("Revisado (Total Sistema, beneficiarios, julio 2026): 2.487.497 → 2.507.497") for n in revised["ficha"]["notes"])


def test_hold_on_reconciliation_failure_keeps_live(root):
    sf.publish(f1.run(root, today=TODAY, llm=False), root)
    live_before = sf.load_live(root, "f1_cartera")
    data = portfolio(root)
    data["coverage"][-1]["total_beneficiaries"] += 1  # Σ by Isapre ≠ declared total
    for o in data["observations"]:
        o["source_sha256"] = "c" * 64
    save_portfolio(root, data)
    r = f1.run(root, today=TODAY, llm=False)
    assert r["status"] == "hold" and any(e.startswith("HOLD_RECONCILIATION") and "total_2026-08" in e for e in r["errors"])
    out = sf.publish(r, root)
    assert out["published"] is False and Path(out["hold"]).exists()
    assert sf.load_live(root, "f1_cartera") == live_before


def test_hold_on_missing_hash_and_older_period():
    base = {"reconciliation": {"ok": True}, "primary_source": {"sha256": "a" * 64}, "period": "2026-08",
            "release_key": "2026-08:x", "published_at": "2026-10-02", "findings": [], "revisions": []}
    cal = {"expected_release_interval_days": 31, "late_tolerance_days": 21}
    assert sf.evaluate_triggers({**base, "primary_source": {"sha256": ""}}, None, today=TODAY, calendar=cal)["holds"] == ["HOLD_MISSING_HASH"]
    older = sf.evaluate_triggers({**base, "period": "2026-07"}, {"period": "2026-08", "release_key": "z"}, today=TODAY, calendar=cal)
    assert older["decision"] == "HOLD" and "HOLD_OLDER_PERIOD" in older["holds"]
    fresh = sf.evaluate_triggers(base, None, today=TODAY, calendar=cal)
    assert fresh["decision"] == "PUBLISH" and fresh["triggers"] == ["new_period"] and fresh["featured"] is False


def test_late_release_adds_watch_item_and_republishes_once(root):
    sf.publish(f1.run(root, today=TODAY, llm=False), root)
    late_day = date(2026, 11, 30)  # 2 oct + 31 + 21 = 23 nov
    r = f1.run(root, today=late_day, llm=False)
    assert r["status"] == "pass" and "late_release" in r["decision"]["triggers"]
    assert "atrasada" in r["ficha"]["watch"][0]["headline"]
    sf.publish(r, root)
    assert f1.run(root, today=late_day, llm=False)["status"] == "no_change"


def test_publish_archives_previous_live(root):
    sf.publish(f1.run(root, today=TODAY, llm=False), root)
    data = portfolio(root)
    for o in data["observations"]:
        o["source_sha256"] = "d" * 64
    save_portfolio(root, data)
    out = sf.publish(f1.run(root, today=TODAY, llm=False), root)
    assert out["published"] is True and out["archived"] and Path(out["archived"]).exists()


# ---------------------------------------------------------------------------------------------
# Lectura verifier and budgeted generation (fake model only)


def test_verifier_accepts_traced_text_and_rejects_violations(root):
    p = f1.build_package(root)
    assert sf.verify_lectura(GOOD, p)["verdict"] == "PASS"
    assert sf.verify_lectura("La cartera bajó en 814 beneficiarios y 77% lo concentra Banmédica.", p)["verdict"] == "PASS"
    bad_number = sf.verify_lectura("La cartera perdió 9.999 beneficiarios.", p)
    assert "number_not_in_evidence:9.999" in bad_number["errors"]
    causal = sf.verify_lectura("La baja se debe a la ley corta y el alza de precios provoca salidas.", p)
    assert any(e.startswith("causal_without_note") for e in causal["errors"])
    assert sf.verify_lectura("La lectura general de la cartera es estable.", p)["verdict"] == "PASS"  # 'general' is not 'genera'
    other = sf.verify_lectura("Banmédica pierde cartera.", {**p, "entity_codes": [67]})
    assert "isapre_not_in_package:99" in other["errors"]
    assert any(e.startswith("over_90_words") for e in sf.verify_lectura("palabra " * 91, p)["errors"])
    with_note = sf.verify_lectura("La baja se debe a cargas.", {**p, "causal_note": "Nota causal verificada"})
    assert not any(e.startswith("causal") for e in with_note["errors"])


def test_lectura_pass_is_published_and_not_paid_twice(root):
    model = fake_model(GOOD)
    r = f1.run(root, today=TODAY, llm=True, model_call=model, budget=ALLOW)
    assert r["ficha"]["lectura"]["status"] == "pass" and r["ficha"]["lectura"]["text"] == GOOD
    assert model.calls[0]["feature"] == "stats_ficha_lectura" and model.calls[0]["allow_luna_fallback"] is False
    assert sf.verify_ficha(r["ficha"], f1.build_package(root))["verdict"] == "PASS"
    sf.publish(r, root)
    again = f1.run(root, today=TODAY, llm=True, model_call=model, budget=ALLOW)
    assert again["status"] == "no_change" and len(model.calls) == 1


def test_lectura_omitted_on_verifier_fail_or_no_budget_ficha_still_publishes(root):
    bad = fake_model("Las Isapres perdieron 123.456 afiliados debido a la ley corta.")
    r = f1.run(root, today=TODAY, llm=True, model_call=bad, budget=ALLOW)
    assert r["status"] == "pass" and r["ficha"]["lectura"]["status"] == "verifier_fail"
    assert sf.public_ficha(r["ficha"])["lectura"] is None
    sf.publish(r, root)
    retry = fake_model(GOOD)
    assert f1.run(root, today=TODAY, llm=True, model_call=retry, budget=ALLOW)["status"] == "no_change"
    assert retry.calls == []  # a paid FAIL is not retried for the same release
    shutil.rmtree(root / "data/stats_fichas")
    blocked = fake_model(GOOD)
    nb = f1.run(root, today=TODAY, llm=True, model_call=blocked, budget=lambda worst: (False, "paced_budget_would_be_exceeded"))
    assert nb["status"] == "pass" and nb["ficha"]["lectura"]["status"] == "no_budget" and blocked.calls == []
    sf.publish(nb, root)
    filled = f1.run(root, today=TODAY, llm=True, model_call=blocked, budget=ALLOW)
    assert filled["status"] == "pass" and filled["ficha"]["lectura"]["status"] == "pass" and len(blocked.calls) == 1


def test_default_budget_respects_paced_monthly_budget(monkeypatch):
    from radar_salud import ai_budget, ai_pricing
    monkeypatch.setattr(ai_budget, "has_capacity", lambda kind: True)
    monkeypatch.setattr(ai_pricing, "month_spend_usd", lambda root=None, now=None: 9.99)
    monkeypatch.setattr(ai_pricing, "paced_budget_usd", lambda now=None: 10.0)
    called = []
    monkeypatch.setattr(ai_budget, "allow_call", lambda kind: called.append(kind) or True)
    assert sf._default_budget(0.05) == (False, "paced_budget_would_be_exceeded") and called == []


def test_verify_ficha_rejects_untraced_numbers(root):
    fi = f1.run(root, today=TODAY, llm=False)["ficha"]
    p = f1.build_package(root)
    tampered = {**fi, "dek": fi["dek"].replace("2.486.683", "2.486.684")}
    assert "number_not_in_evidence:2.486.684" in sf.verify_ficha(tampered, p)["errors"]
    tabs = json.loads(json.dumps(fi["tabs"]))
    tabs[0]["charts"][0]["rows"][0]["value"] += 1
    assert any(e.startswith("chart_row_not_in_evidence") for e in sf.verify_ficha({**fi, "tabs": tabs}, p)["errors"])


def test_four_lenses_reject_redundancy_ui_overload_and_missing_denominator(root):
    fi = f1.run(root, today=TODAY, llm=False)["ficha"]
    p = f1.build_package(root)
    repeated = {**fi, "tabs": [{**fi["tabs"][0], "text": [fi["facts"]["paragraphs"][0]]}, *fi["tabs"][1:]]}
    assert any(e.startswith("editorial:repeated_sentence") for e in sf.verify_ficha(repeated, p)["errors"])
    crowded = {**fi, "tabs": [{**fi["tabs"][0], "charts": fi["tabs"][0]["charts"] * 2}, *fi["tabs"][1:]]}
    assert "ui:tab_over_2_charts:total" in sf.verify_ficha(crowded, p)["errors"]
    no_den = {**fi, "notes": [n for n in fi["notes"] if "denominador" not in n["text"]]}
    assert "data:denominator_not_stated" in sf.verify_ficha(no_den, p)["errors"]
    assert "business:watch_out_of_range" in sf.verify_ficha({**fi, "watch": fi["watch"][:1]}, p)["errors"]
    assert "business_lens_no_audience" in sf.verify_lectura("La serie muestra una trayectoria estable en el período.", p)["errors"]


def test_lectura_prompt_encodes_four_lenses(root):
    fi = f1.run(root, today=TODAY, llm=False)["ficha"]
    prompt = sf.lectura_prompt(fi, f1.build_package(root))
    for lens in ("Negocio de salud", "Analítica de datos", "Editorial", "UI/UX"):
        assert lens in prompt
    assert "Banmédica" in prompt and "Cartera total" in prompt


def test_share_page_has_og_preview_and_deep_link(root, tmp_path):
    sf.publish(f1.run(root, today=TODAY, llm=False), root)
    card = sf.apply_to_snapshot([], sf.live_fichas(root))[0]
    assert card["share_url"] == "data/fichas/f1_cartera.html"
    written = sf.write_share_pages([card], tmp_path / "web/data")
    html = Path(written[0]).read_text(encoding="utf-8")
    assert '<meta property="og:title" content="La salida de afiliados' in html
    assert 'og:image" content="https://cftorre1.github.io/Radar-salud/assets/' in html
    assert 'url=../../index.html#sig-stats-ficha:F1:2026-08' in html


# ---------------------------------------------------------------------------------------------
# Snapshot: one live ficha per family


def test_snapshot_replaces_pulse_and_loose_cartera_cards(root):
    sf.publish(f1.run(root, today=TODAY, llm=False), root)
    fichas = sf.live_fichas(root)
    pulse = {"title": "Pulso Isapre · datos a 2026-07", "event_type": "DATA_PULSE", "source_name": "Superintendencia de Salud", "signal_types": ["Datos"]}
    loose = {"title": "Estadística mensual de cartera de beneficiarios a nivel regional", "source_name": "Superintendencia de Salud", "signal_types": ["Datos"]}
    keep = {"title": "Estadística Trimestral de Casos GES", "source_name": "Superintendencia de Salud", "signal_types": ["Datos"]}
    out = sf.apply_to_snapshot([pulse, loose, keep], fichas)
    titles = [c["title"] for c in out]
    assert pulse["title"] not in titles and loose["title"] not in titles and keep["title"] in titles
    card = out[-1]
    assert card["stats_ficha"]["period"] == "2026-08" and card["data_period"] == "2026-08"
    assert card["editorial_committee"]["verdict"] == "PASS" and card["piece_id"] == "stats-ficha:F1:2026-08"
    assert "evidence" not in card["stats_ficha"] and card["radar_score"] >= 85
    for key in ("title", "signal_types", "scopes", "event_date", "source_name", "source_url", "card_what"):
        assert card[key]


def test_repo_snapshot_has_august_ficha_and_no_wrong_ges_finding():
    rows = json.loads((REPO / "web/data/radar_today.json").read_text(encoding="utf-8"))["signals"]
    fichas = [s for s in rows if s.get("stats_ficha")]
    assert len(fichas) == 1 and fichas[0]["data_period"] == "2026-08"
    assert not any(str(s.get("title", "")).startswith("Pulso Isapre") for s in rows)
    text = json.dumps(rows, ensure_ascii=False)
    assert "presenta el mayor volumen" not in text
    ges = next(s for s in rows if "casos-ges-auge-de-fonasa-y-sistema-isapre-a-junio-2026" in str(s.get("source_url")))
    assert ges["data_insights"] == [] and ges["statistical_view"]["publication_status"] == "HOLD"


# ---------------------------------------------------------------------------------------------
# GES card bug: pinned current-year sheet, sum vs declared total, HOLD


def ges_book(rows_2026, extra_sheets=("Año 2005",)):
    from openpyxl import Workbook
    book = Workbook()
    first = True
    for name in extra_sheets:
        ws = book.active if first else book.create_sheet(name)
        ws.title = name
        first = False
        ws.append(["N°", "Problema de salud", "Fonasa", "Isapre"])
        ws.append([21, 21, 900000, 900000])
        ws.append([22, 22, 1, 1])
        ws.append([23, 23, 1, 1])
    ws = book.create_sheet("Año 2026") if not first else book.active
    ws.title = "Año 2026"
    ws.append(["N°", "Problema de salud", "Fonasa", "Isapre"])
    for r in rows_2026:
        ws.append(r)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


TITLE = "Estadística Trimestral de Casos GES (AUGE) de Fonasa y Sistema ISAPRE – a junio 2026"
ROWS = [[1, "Diabetes", 120, 30], [2, "Cáncer de mama", 80, 40], [3, "Hipertensión", 150, 20]]


def test_ges_pins_current_year_sheet_and_reconciles():
    r = data_insights.parse_ges_workbook(ges_book(ROWS + [[None, "Total", 350, 90]]), TITLE)
    assert r["status"] == "validated" and r["sheet"] == "Año 2026" and r["parser"] == sf.GES_PARSER
    assert r["reconciliation"] == {"ok": True, "rows_sum": [350, 90], "declared_total": [350, 90], "total_row": 5}
    assert r["insights"][0].startswith("Hipertensión") and "21" not in r["insights"][0]
    assert sf.ges_finding_valid(r)


@pytest.mark.parametrize("rows,extra,reason", [
    (ROWS + [[None, "Total", 351, 90]], ("Año 2005",), "HOLD_GES_RECONCILIATION"),
    (ROWS, ("Año 2005",), "HOLD_GES_TOTAL_MISSING"),
    ([[1, "21", 120, 30], [2, "22", 80, 40], [3, "23", 150, 20], [None, "Total", 350, 90]], ("Año 2005",), "HOLD_GES_LABEL_NOT_TEXT"),
])
def test_ges_holds_on_failures(rows, extra, reason):
    r = data_insights.parse_ges_workbook(ges_book(rows, extra), TITLE)
    assert r["status"] == "HOLD" and r["hold_reason"] == reason and r["insights"] == []


def test_ges_holds_when_year_sheet_is_not_unique():
    from openpyxl import Workbook
    book = Workbook()
    book.active.title = "Año 2005"
    stream = BytesIO()
    book.save(stream)
    r = data_insights.parse_ges_workbook(stream.getvalue(), TITLE)
    assert r["status"] == "HOLD" and r["hold_reason"] == "HOLD_GES_SHEET_NOT_PINNED"


def test_old_ges_finding_goes_to_hold_without_its_text():
    old = {"title": "GES", "source_url": "https://x/ges", "data_insights": ["21 presenta el mayor volumen combinado…"],
           "data_insight_meta": {"family": "ges", "status": "validated", "sheet": "Año 2005", "insights": ["21 presenta…"]}}
    out = sf.sanitize_ges_signal(old)
    assert out["data_insights"] == [] and out["data_insight_meta"]["status"] == "HOLD"
    assert out["statistical_view"]["publication_status"] == "HOLD"
    assert "21 presenta" not in json.dumps(out, ensure_ascii=False)
    good = {"data_insights": ["x"], "data_insight_meta": {"family": "ges", "status": "validated", "parser": sf.GES_PARSER, "reconciliation": {"ok": True}}}
    assert sf.sanitize_ges_signal(good) is good


def test_registry_declares_f1_rules():
    reg = sf.load_registry()
    f1cfg = reg["families"]["F1"]
    assert f1cfg["status"] == "active" and len(f1cfg["open_codes"]) == 7
    assert "abiertas" in f1cfg["kpis"]["participacion"]["denominator"].lower()
    assert reg["families"]["F2"]["status"] == "planned" and reg["lectura"]["max_words"] == 90
