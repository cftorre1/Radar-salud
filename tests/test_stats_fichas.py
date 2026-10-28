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
    assert fi["headline_type"] == "record_low_decline"
    # Stock wording: a change between month-end stocks is not a flow of exits (those live in the mobility tab).
    assert fi["headline"] == "La cartera Isapre casi deja de caer: −814 beneficiarios en agosto, la menor baja del año"
    assert not any(w in fi["headline"].lower() for w in ("salida", "afiliados", "se detiene"))
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
    # Dirección 28-oct 08:20: each tab carries its own analysis (facts folded in); compact 'Qué mirar'.
    assert fi["facts"]["rendered_in_tabs"] is True
    assert tabs["total"]["text"][0] == fi["facts"]["paragraphs"][0]
    assert tabs["mezcla"]["text"][0] == fi["facts"]["paragraphs"][1]
    assert tabs["isapres"]["text"][0] == fi["facts"]["paragraphs"][2]
    assert len(fi["watch"]) == 2


def test_verify_ficha_rejects_invented_sources_links_and_placeholders(root):
    fi = f1.run(root, today=TODAY, llm=False)["ficha"]
    p = f1.build_package(root)
    invented = {**fi, "sources": fi["sources"] + [{"label": "Inventada", "url": "https://example.cl/x", "sha256": "e" * 64}]}
    assert "source_not_captured:Inventada" in sf.verify_ficha(invented, p)["errors"]
    tabs = json.loads(json.dumps(fi["tabs"]))
    tabs[-1]["links"] = [{"label": "Otra", "url": "https://example.cl/regional.xlsx"}]
    assert "link_not_captured:regional" in sf.verify_ficha({**fi, "tabs": tabs}, p)["errors"]
    placeholder = {**fi, "dek": fi["dek"] + " {entity} ejemplo ilustrativo."}
    assert any(e.startswith("template_placeholder") for e in sf.verify_ficha(placeholder, p)["errors"])
    assert sf.verify_ficha(fi, p)["verdict"] == "PASS"


def test_missing_entity_name_holds_instead_of_showing_a_code(root):
    ents = json.loads((root / INPUTS[2]).read_text(encoding="utf-8"))
    for e in ents["entities"]:
        if e["official_code"] == 108:
            e["commercial_name"] = None
            e.pop("legal_name", None)
    (root / INPUTS[2]).write_text(json.dumps(ents, ensure_ascii=False), encoding="utf-8")
    r = f1.run(root, today=TODAY, llm=False)
    assert r["status"] == "hold" and "entity_name_missing" in r["errors"][0]


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


def test_verifier_accepts_clean_text_and_rejects_violations(root):
    fi = f1.run(root, today=TODAY, llm=False)["ficha"]
    p = f1.build_package(root)
    assert sf.verify_lectura(GOOD, p, ficha=fi)["verdict"] == "PASS"
    causal = sf.verify_lectura("La baja se debe a la ley corta y el alza de precios provoca salidas.", p, ficha=fi)
    assert any(e.startswith("causal_without_note") for e in causal["errors"])
    assert sf.verify_lectura("La lectura general de la cartera es estable.", p, ficha=fi)["verdict"] == "PASS"  # 'general' is not 'genera'
    other = sf.verify_lectura("Banmédica pierde cartera.", {**p, "entity_codes": [67]}, ficha=fi)
    assert "insurer_not_in_package:banmedica" in other["errors"]
    assert any(e.startswith("over_60_words") for e in sf.verify_lectura("cartera " * 61, p, ficha=fi)["errors"])
    with_note = sf.verify_lectura("La baja se debe a cargas.", {**p, "causal_note": "Nota causal verificada"}, ficha=fi)
    assert not any(e.startswith("causal") for e in with_note["errors"])
    assert "url_in_lectura" in sf.verify_lectura("Para la cartera ver www.example.cl", p, ficha=fi)["errors"]


# Every bypass found by the independent review (28-oct): the Lectura carries no number at all.
@pytest.mark.parametrize("text", [
    "La cartera cayó 3% en el año.",                                # % that is not a package value
    "Banmédica bajó 50% su cartera.",                               # % with a wrong unit/meaning
    "La cartera perdió 2,5 millones de beneficiarios.",              # 'millones' with a numeral
    "La cartera perdió millones de beneficiarios.",                  # 'millones' without a numeral
    "La cartera anotó −27.355, o sea +27.355 para las Isapres.",     # signed mismatch
    "Veinte mil beneficiarios dejaron la cartera de las Isapres.",   # number words
    "Las Isapres perdieron mil beneficiarios en la cartera.",
    "La baja de Banmédica es más del doble que la del resto de la cartera.",
    "Un tercio de la cartera está en Banmédica.",
    "La mitad de la baja de la cartera es de Banmédica.",
    "Un cuarto de la cartera está en una Isapre.",
    "La cartera es el triple que hace una década.",
    "La cartera perdió 814 personas en 2027.",                       # year outside the data/publication period
    "La cartera perdió 814 beneficiarios.",                          # even a traced value: numbers stay in KPIs
    "La cartera de las Isapres baja por segundo mes.",               # ordinal
    "La cartera de las Isapres cae ½ punto.",                        # Unicode numeric character
    "La cartera de las Isapres cae ٣ puntos.",                       # non-ASCII digit
    "La cartera Isapre se mueve unos puntos porcentuales.",
])
def test_lectura_rejects_every_number_bypass(root, text):
    fi = f1.run(root, today=TODAY, llm=False)["ficha"]
    r = sf.verify_lectura(text, f1.build_package(root), ficha=fi)
    assert r["verdict"] == "FAIL" and any(e.startswith("number_in_lectura") for e in r["errors"]), r


def test_registry_forbids_numbers_in_lectura():
    assert sf.load_registry()["lectura"]["forbid_numbers"] is True


@pytest.mark.parametrize("text", [
    "La cartera se mueve impulsada por las cargas.", "Las cargas impulsan la baja de la cartera.",
    "La baja se origina en las cargas de la cartera.", "La baja de la cartera tiene su origen en las cargas.",
    "La baja responde al alza de precios en las Isapres.", "La baja de la cartera responde a los precios.",
    "Los precios provocaron la baja de la cartera.", "Los precios generaron salidas de la cartera Isapre.",
    "La baja de la cartera se debió a los precios.", "La cartera cae; esto se explica por los precios.",
    "Los precios explicarían la baja de la cartera.", "Los precios causaron la baja de la cartera.",
    "Las Isapres atribuyen la baja de la cartera a los precios.", "La baja se traduce en menos ingreso para las Isapres.",
    "La baja de la cartera lleva a menos ingreso.", "La baja de la cartera llevó a las Isapres a ajustar.",
    "La baja de la cartera produce menos ingreso.", "La cartera cae porque suben los precios.",
    "La cartera cae, ya que suben los precios.", "La cartera cae por efecto de los precios.",
])
def test_causal_conjugations_rejected_without_note(root, text):
    p = f1.build_package(root)
    errors = sf.verify_lectura(text, p)["errors"]
    assert any(e.startswith("causal_without_note") for e in errors), errors
    assert not any(e.startswith("causal") for e in sf.verify_lectura(text, {**p, "causal_note": "nota"})["errors"])


@pytest.mark.parametrize("text", ["Las Isapres crecen en general.", "La cartera muestra una generación de ingreso estable.",
                                  "La competencia entre Isapres se mantiene.", "Para la cartera, la duda es la rentabilidad."])
def test_causal_patterns_do_not_flag_plain_words(root, text):
    assert not any(e.startswith("causal") for e in sf.verify_lectura(text, f1.build_package(root))["errors"])


@pytest.mark.parametrize("text,error", [
    ("Para las Isapres, Fonasa gana espacio frente a la cartera privada.", "insurer_not_in_package:fonasa"),
    ("Para la competencia, Golden Cross mantiene su cartera.", "insurer_not_in_facts:colmena"),
    ("Para la competencia, Colmena mantiene su cartera.", "insurer_not_in_facts:colmena"),
    ("Para la competencia, Consalud mantiene su cartera.", "insurer_not_in_facts:consalud"),
    ("Para la competencia, CruzBlanca mantiene su cartera.", "insurer_not_in_facts:cruz_blanca"),
    ("Para la competencia, Vida Tres mantiene su cartera.", "insurer_not_in_facts:vida_tres"),
    ("Para la competencia, Isalud mantiene su cartera.", "insurer_not_in_facts:isalud"),
    ("Para la competencia, Isapre Fundación mantiene su cartera.", "insurer_not_in_facts:fundacion"),
    ("Para la competencia, Cruz del Norte mantiene su cartera.", "insurer_not_in_facts:cruz_del_norte"),
])
def test_lectura_rejects_insurers_outside_package_or_facts(root, text, error):
    fi = f1.run(root, today=TODAY, llm=False)["ficha"]
    p = f1.build_package(root)
    r = sf.verify_lectura(text, p, ficha=fi)
    assert r["verdict"] == "FAIL" and error in r["errors"], r["errors"]


def test_lectura_accepts_insurers_named_in_facts_with_aliases(root):
    fi = f1.run(root, today=TODAY, llm=False)["ficha"]
    p = f1.build_package(root)
    for text in ("Para la competencia, Banmedica y Nueva Más Vida siguen caminos opuestos en su cartera.",
                 "Para la competencia, Masvida y Esencial ganan cartera frente a Banmédica."):
        assert sf.verify_lectura(text, p, ficha=fi)["verdict"] == "PASS", sf.verify_lectura(text, p, ficha=fi)
    # Without the ficha nothing is in the facts, so no insurer may be named.
    assert "insurer_not_in_facts:banmedica" in sf.verify_lectura("Banmédica pierde cartera.", p)["errors"]
    # Banmédica in the package but removed from the facts → rejected.
    facts = {**fi["facts"], "paragraphs": [x for x in fi["facts"]["paragraphs"] if "Banmédica" not in x]}
    assert "insurer_not_in_facts:banmedica" in sf.verify_lectura("Banmédica pierde cartera.", p, ficha={**fi, "facts": facts})["errors"]


def test_reused_lectura_is_rechecked_with_the_current_verifier(root):
    first = f1.run(root, today=TODAY, llm=True, model_call=fake_model(GOOD), budget=ALLOW)
    first["ficha"]["lectura"]["text"] = "La cartera de las Isapres perdió 814 beneficiarios."  # passed an older verifier
    first["ficha"]["builder_version"] = "old"
    sf.publish(first, root)
    model = fake_model(GOOD)
    r = f1.run(root, today=TODAY, llm=True, model_call=model, budget=ALLOW)
    assert r["ficha"]["lectura"]["status"] == "verifier_fail" and model.calls == []  # no repeat payment
    assert any(e.startswith("number_in_lectura") for e in r["ficha"]["lectura"]["verification"]["errors"])


def test_lectura_repeating_a_ficha_sentence_is_dropped_after_attach(root):
    fi = f1.run(root, today=TODAY, llm=False)["ficha"]
    repeated = next(x for tab in fi["tabs"] for x in tab.get("text") or [] if "ingreso" in x and not any(ch.isdigit() for ch in x.split(". ")[1]))
    sentence = repeated.split(". ", 1)[1]
    text = "Para las Isapres, la señal es de estabilidad en la cartera. " + sentence
    assert sf.verify_lectura(text, f1.build_package(root), ficha=fi)["verdict"] == "PASS"  # passes alone…
    r = f1.run(root, today=TODAY, llm=True, model_call=fake_model(text), budget=ALLOW)
    assert r["status"] == "pass" and r["ficha"]["lectura"]["status"] == "verifier_fail"  # …but repeats the ficha
    assert any("repeated_sentence" in e for e in r["ficha"]["lectura"]["verification"]["ficha_errors"])
    assert sf.public_ficha(r["ficha"])["lectura"] is None


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
    # The facts now live in the tabs: the same sentence in two tabs (or in the dek) is redundant.
    repeated = {**fi, "tabs": [fi["tabs"][0], {**fi["tabs"][1], "text": fi["tabs"][1]["text"] + fi["tabs"][0]["text"][:1]}, *fi["tabs"][2:]]}
    assert any(e.startswith("editorial:repeated_sentence") for e in sf.verify_ficha(repeated, p)["errors"])
    crowded = {**fi, "tabs": [{**fi["tabs"][0], "charts": fi["tabs"][0]["charts"] * 2}, *fi["tabs"][1:]]}
    assert "ui:tab_over_2_charts:total" in sf.verify_ficha(crowded, p)["errors"]
    no_den = {**fi, "notes": [n for n in fi["notes"] if "denominador" not in n["text"]]}
    assert "data:denominator_not_stated" in sf.verify_ficha(no_den, p)["errors"]
    assert "business:watch_out_of_range" in sf.verify_ficha({**fi, "watch": fi["watch"] * 2}, p)["errors"]
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
    assert '<meta property="og:title" content="La cartera Isapre casi deja de caer' in html
    assert '<meta name="twitter:card" content="summary"/>' in html  # no real preview image
    assert 'og:image" content="https://cftorre1.github.io/Radar-salud/assets/' in html
    assert 'url=../../index.html?abrir=1#sig-stats-ficha:F1:2026-08' in html  # opens the detail


# ---------------------------------------------------------------------------------------------
# Snapshot: one live ficha per family


def test_snapshot_replaces_pulse_and_loose_cartera_cards(root):
    sf.publish(f1.run(root, today=TODAY, llm=False), root)
    fichas = sf.live_fichas(root)
    sis = {"source_name": "Superintendencia de Salud", "signal_types": ["Datos"]}
    pulse = {**sis, "title": "Pulso Isapre · datos a 2026-07", "event_type": "DATA_PULSE"}
    loose = {**sis, "title": "Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE a Nivel Regional – Agosto 2026", "event_date": "2026-10-02"}
    older = {**sis, "title": "Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE a Nivel Regional – Julio 2026", "event_date": "2026-09-07"}
    yearly = {**sis, "title": "Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE – año 2026", "event_date": "2026-09-07"}
    keep = {**sis, "title": "Estadística Trimestral de Casos GES"}
    out = sf.apply_to_snapshot([pulse, loose, older, yearly, keep], fichas)
    titles = [c["title"] for c in out]
    for gone in (pulse, loose, older, yearly):
        assert gone["title"] not in titles
    assert keep["title"] in titles
    card = out[-1]
    assert card["stats_ficha"]["period"] == "2026-08" and card["data_period"] == "2026-08"
    assert card["editorial_committee"]["verdict"] == "PASS" and card["piece_id"] == "stats-ficha:F1:2026-08"
    assert "evidence" not in card["stats_ficha"] and card["radar_score"] >= 85
    for key in ("title", "signal_types", "scopes", "event_date", "source_name", "source_url", "card_what"):
        assert card[key]


def test_snapshot_keeps_releases_newer_than_the_ficha(root):
    """Same rule as #84 (6099d0d8): a release the ficha does not cover stays visible until the ficha updates."""
    sf.publish(f1.run(root, today=TODAY, llm=False), root)
    fichas = sf.live_fichas(root)
    sis = {"source_name": "Superintendencia de Salud", "signal_types": ["Datos"]}
    september = {**sis, "title": "Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE a Nivel Regional – Septiembre 2026", "event_date": "2026-10-30"}
    by_field = {**sis, "title": "Cartera de beneficiarios regional", "data_period": "2026-09", "event_date": "2026-09-01"}
    yearly_new = {**sis, "title": "Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE – año 2026", "event_date": "2026-11-02"}
    mobility_new = {**sis, "title": "Estadística Mensual de Movilidad de Cartera de Cotizantes del Sistema ISAPRE a Nivel Regional – Año 2026", "event_date": "2026-11-02"}
    titles = [c["title"] for c in sf.apply_to_snapshot([september, by_field, yearly_new, mobility_new], fichas)]
    for kept in (september, by_field, yearly_new, mobility_new):
        assert kept["title"] in titles
    assert sf.loose_card_period(september) == "2026-09" and sf.loose_card_period(yearly_new) is None


def test_repo_snapshot_has_august_ficha_and_no_wrong_ges_finding():
    rows = json.loads((REPO / "web/data/radar_today.json").read_text(encoding="utf-8"))["signals"]
    fichas = [s for s in rows if s.get("stats_ficha")]
    assert len(fichas) == 1 and fichas[0]["data_period"] == "2026-08"
    assert not any(str(s.get("title", "")).startswith("Pulso Isapre") for s in rows)
    ges = next(s for s in rows if "casos-ges-auge-de-fonasa-y-sistema-isapre-a-junio-2026" in str(s.get("source_url")))
    assert ges["data_insights"] == [] and ges["statistical_view"]["publication_status"] == "HOLD"
    assert ges["statistical_view"]["correction"]["text"].startswith("Corregido el 28-oct:")
    # The withdrawn sentence survives only inside the correction record, never in a displayed field.
    shown = json.dumps([{k: v for k, v in s.items() if k != "data_insight_meta"} for s in rows], ensure_ascii=False)
    assert "presenta el mayor volumen" not in shown


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


WITHDRAWN = "21 presenta el mayor volumen combinado entre las filas comparables detectadas en la tabla GES del corte 2026-06."


def test_old_ges_finding_goes_to_hold_and_keeps_withdrawn_text_in_history():
    old = {"title": "GES", "source_url": "https://x/ges", "data_insights": [WITHDRAWN],
           "data_insight_meta": {"family": "ges", "status": "validated", "sheet": "Año 2005", "insights": [WITHDRAWN]}}
    out = sf.sanitize_ges_signal(old)
    assert out["data_insights"] == [] and out["data_insight_meta"]["status"] == "HOLD"
    sup = out["data_insight_meta"]["superseded_meta"]
    assert sup["withdrawn_insight_texts"] == [WITHDRAWN] and sup["withdrawn_data_insights"] == [WITHDRAWN]
    assert sup["corrected_at"] == "2026-10-28" and sup["reason"] == "parser leía hoja Año 2005"
    assert sup["superseded_parser"] == sf.GES_LEGACY_PARSER and sup["corrected_by_parser"] == sf.GES_PARSER
    view = out["statistical_view"]
    assert view["publication_status"] == "HOLD" and view["correction"]["text"].startswith("Corregido el 28-oct:")
    assert "21 presenta" not in json.dumps(view, ensure_ascii=False)  # shown text never repeats the withdrawn finding
    assert sf.sanitize_ges_signal(out) is out  # idempotent: the record is not rewritten again
    # An already-held record without the text (the first version of this fix) is upgraded, never emptied.
    legacy = {**old, "data_insights": [], "data_insight_meta": {"family": "ges", "status": "HOLD", "parser": sf.GES_PARSER,
              "superseded_meta": {"family": "ges", "sheet": "Año 2005", "withdrawn_insights": 1}}}
    up = sf.sanitize_ges_signal(legacy)
    assert up["data_insight_meta"]["superseded_meta"]["withdrawn_insights"] == 1
    assert up["statistical_view"]["correction"]["corrected_at"] == "2026-10-28"
    good = {"data_insights": ["x"], "data_insight_meta": {"family": "ges", "status": "validated", "parser": sf.GES_PARSER, "reconciliation": {"ok": True}}}
    assert sf.sanitize_ges_signal(good) is good
    fresh_hold = {"data_insights": [], "data_insight_meta": {"family": "ges", "status": "HOLD", "parser": sf.GES_PARSER}}
    assert sf.sanitize_ges_signal(fresh_hold) is fresh_hold


def test_history_keeps_the_withdrawn_ges_sentence_verbatim():
    rows = json.loads((REPO / "data/history/superintendencia_signals.json").read_text(encoding="utf-8"))["signals"]
    ges = next(s for s in rows if "casos-ges-auge-de-fonasa-y-sistema-isapre-a-junio-2026" in str(s.get("source_url")))
    sup = ges["data_insight_meta"]["superseded_meta"]
    assert sup["withdrawn_insight_texts"][0].startswith("21 presenta el mayor volumen combinado")
    assert sup["reason"] == "parser leía hoja Año 2005" and sup["corrected_at"] == "2026-10-28"


def test_registry_declares_f1_rules():
    reg = sf.load_registry()
    f1cfg = reg["families"]["F1"]
    assert f1cfg["status"] == "active" and len(f1cfg["open_codes"]) == 7
    assert "abiertas" in f1cfg["kpis"]["participacion"]["denominator"].lower()
    assert reg["families"]["F2"]["status"] == "planned" and reg["lectura"]["max_words"] == 60 <= 90  # short Lectura
