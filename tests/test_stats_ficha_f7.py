"""F7 · Financiamiento público (DIPRES Partida 16): PASS, every HOLD, no nested sums, dates, first-review gate.

Fixtures are SYNTHETIC lanes (``data/market/dipres_health_budget.json`` written in tmp_path): amounts and hashes are
test values, not DIPRES figures. Each KPI is recomputed here from the raw records, independently of the builder.
"""
import copy
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from radar_salud import datos_index as di
from radar_salud import stats_ficha_f7 as f7
from radar_salud import stats_fichas as sf

REPO = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 4)
URL = "https://www.dipres.gob.cl/597/articles-{n}_doc_pdf.pdf"
LAST = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31}

# Partida (accumulated executed, vigente) per month, in miles de $ (synthetic).
PARTIDA = {"2026-01": (2_000_000, 17_000_000), "2026-02": (3_500_000, 17_000_000), "2026-03": (5_100_000, 17_400_000)}
CAP02 = {"2026-01": (1_500_000, 14_000_000), "2026-02": (2_700_000, 14_000_000), "2026-03": (4_000_000, 14_300_000)}
PROG = ("2026-03", 3_900_000, 14_100_000)  # programa 02.01, comparative table
INITIAL = 16_800_000


def sha(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def _rec(n, state, val, *, period, ent, year, column=None, start=True, published_at=None):
    p, sub, ch, pr = ent
    r = {"source_url": URL.format(n=n), "source_sha256": sha(str(n)), "currency": "CLP", "unit": "thousand_CLP",
         "published_at": published_at, "event_date": None, "effective_date": None, "date_reason": "fixture",
         "partida": p, "subpartida": sub, "chapter": ch, "program": pr, "metric": "gastos", "fiscal_year": year,
         "period": period, "budget_state": state, "measurement_basis": "nominal", "price_base_year": year, "value": val,
         "reporting_level": "program" if pr else "chapter" if ch else "partida"}
    if state == "executed" or start:
        r.update(period_start=f"{year}-01-01" if state == "executed" else None,
                 period_end=f"{period}-{LAST[int(period[5:7])]:02d}" if state == "executed" else None)
    if column:
        r["source_column"] = column
    else:
        r["accounting_basis"] = "accrued"
    return r


def informe(n, period, executed, vigente, ent, initial=INITIAL, **kw):
    y = int(period[:4])
    return [_rec(n, "approved_initial", initial, period=period, ent=ent, year=y, **kw),
            _rec(n, "modified", vigente, period=period, ent=ent, year=y, **kw),
            _rec(n, "executed", executed, period=period, ent=ent, year=y, **kw)]


def comparativo(n, period, executed, vigente, ent):
    y = int(period[:4])
    return [_rec(n, "modified", vigente, period=str(y), ent=ent, year=y, column=2),
            _rec(n, "executed", executed, period=period, ent=ent, year=y, column=3)]


P, C, G = f7.ENTITIES["partida"], f7.ENTITIES["cap02"], f7.ENTITIES["prog0201"]


def lane(*, partida=PARTIDA, cap=CAP02, prog=PROG, extra=()):
    recs, ledger, n = [], [], 1000
    for per, (e, v) in partida.items():
        recs += informe(n, per, e, v, P); ledger.append((n, "Informe Ejecución Partida")); n += 1
    for per, (e, v) in cap.items():
        recs += informe(n, per, e, v, C, initial=13_900_000); ledger.append((n, "Informe Ejecución Capítulo")); n += 1
    if prog:
        recs += comparativo(n, prog[0], prog[1], prog[2], G); ledger.append((n, "Cuadro Comparativo Analítico Años 2026-2027")); n += 1
    for rs, kind in extra:
        recs += rs
        ledger.append((int(rs[0]["source_url"].split("-")[1].split("_")[0]), kind))
    return {"schema_version": 1, "records": recs,
            "document_ledger": [{"source_url": URL.format(n=k), "source_sha256": sha(str(k)), "kind": f"Documento PDF : {kind}",
                                 "fetched_at": "2026-10-11T14:00:00+00:00", "disposition": "data_snapshot"} for k, kind in ledger],
            "aggregation_rule": "Do not sum nested fiscal levels or transfer-financed programs. Execution is accumulated, not monthly flow.",
            "coverage_complete": False, "coverage_reason": "fixture"}


def write(root: Path, data: dict) -> Path:
    path = root / f7.LANE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return root


def reg_open():
    reg = copy.deepcopy(sf.load_registry())
    reg["families"]["F7"]["first_pass_requires_review"] = False
    return reg


def failures(data, tmp_path):
    p = f7.build_package(write(tmp_path, data), reg_open())
    return p["reconciliation"]["failures"] if not p["reconciliation"]["ok"] else []


# ---------------------------------------------------------------------------------------------------------------------
# PASS


def test_pass_recomputes_every_kpi_from_the_raw_records(tmp_path):
    root = write(tmp_path, lane())
    p = f7.build_package(root, reg_open())
    assert p["reconciliation"]["ok"], p["reconciliation"]
    assert p["period"] == "2026-03" and p["kpis"]["tp"] == "2026-03"
    v = {k: e["value"] for k, e in p["values"].items()}
    e, vg = PARTIDA["2026-03"]
    assert v["partida.2026-03.ejecutado"] == e / 1000 and v["partida.2026-03.vigente"] == vg / 1000
    assert v["partida.2026-03.pct"] == pytest.approx(e / vg * 100)
    assert v["prog0201.2026-03.pct"] == pytest.approx(PROG[1] / PROG[2] * 100)
    assert v["partida.2026-03.modificaciones"] == pytest.approx((vg - INITIAL) / 1000)
    out = f7.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "pass", out.get("errors")
    fi = out["ficha"]
    assert fi["verification"]["verdict"] == "PASS"
    assert fi["headline"] == "Salud ejecutó el 29,3% de su presupuesto vigente a marzo 2026"  # the partida only
    assert [k["id"] for k in fi["kpis"]][:2] == ["ejecucion_partida", "ejecucion_fonasa"]
    assert fi["kpis"][0]["value"] == "29,3%" and fi["kpis"][0]["lines"][:2] == ["a marzo 2026", "devengado 5.100 de 17.400 MM$"]
    # Same cut: the programme card; its comparative 'Ejecución' column is 'ejecutado', never 'devengado'.
    assert fi["kpis"][1]["label"] == "Ejecución programa Fonasa" and fi["kpis"][1]["value"] == "27,7%"
    assert fi["kpis"][1]["lines"][:2] == ["a marzo 2026", "ejecutado 3.900 de 14.100 MM$"]
    assert fi["kicker"] == "Financiamiento público · corte 31 mar 2026"
    assert "devengó" not in " ".join(x for x in fi["facts"]["paragraphs"] if "programa" in x)
    assert "600 MM$ más que la ley inicial (+3,6%)" in fi["dek"] and len(fi["dek"].split()) <= 40
    assert "sin comparación a/a" in fi["kpis"][0]["lines"]
    # Non-causal and nominal labels.
    text = " ".join(sf.displayed_texts(fi))
    assert "nominal" in text and "porque" not in text.casefold()
    assert all(s["url"].startswith("https://www.dipres.gob.cl/") and sf.HEX64.fullmatch(s["sha256"]) for s in fi["sources"])


def test_yoy_only_against_the_same_month_and_kind_of_document(tmp_path):
    prev = informe(2000, "2025-03", 4_000_000, 16_000_000, P)
    data = lane(extra=[(prev, "Informe Ejecución Partida")])
    p = f7.build_package(write(tmp_path, data), reg_open())
    v = {k: e["value"] for k, e in p["values"].items()}
    assert p["kpis"]["yoy"]["partida"] == "2025-03"
    assert v["partida.yoy.pp"] == pytest.approx(round(5_100_000 / 17_400_000 * 100, 1) - round(4_000_000 / 16_000_000 * 100, 1))
    assert v["partida.yoy.ejecutado_pct"] == pytest.approx((5_100 - 4_000) / 4_000 * 100)
    fi = f7.run(tmp_path, today=TODAY, registry=reg_open(), llm=False)["ficha"]
    assert fi["kpis"][0]["lines"][2] == "marzo 2025: 25,0% (+4,3 pp)" and "+4,3 pp a/a" in fi["tabs"][0]["index_line"]
    # A previous-year cut from another kind of document (comparative table) or another month is never compared.
    for rs, kind in ((comparativo(2001, "2025-03", 4_000_000, 16_000_000, P), "Cuadro Comparativo Analítico Años 2025-2026"),
                     (informe(2002, "2025-02", 3_000_000, 16_000_000, P), "Informe Ejecución Partida")):
        p = f7.build_package(write(tmp_path, lane(extra=[(rs, kind)])), reg_open())
        assert p["reconciliation"]["ok"] and p["kpis"]["yoy"]["partida"] is None


def test_negative_budget_change_is_worded_by_its_sign(tmp_path):
    data = lane(partida={"2026-01": (2_000_000, 16_000_000), "2026-02": (3_000_000, 16_500_000)})
    fi = f7.run(write(tmp_path, data), today=TODAY, registry=reg_open(), llm=False)["ficha"]
    assert "300 MM$ menos que la ley inicial (−1,8%)" in fi["dek"]
    assert not sf.SIGNED_WITH_WORD.search(fi["dek"])


# ---------------------------------------------------------------------------------------------------------------------
# Cuts are never mixed without a label (review of PR #139)

MONTH_RX = "|".join(sf.MONTHS_ES)


def unlabelled_other_cuts(fi: dict) -> list[str]:
    """Headline, dek and KPI lines: a month other than the partida's cut appears only with its distance written next to
    it ('… después/antes del corte de la partida') or as the labelled same-month-last-year comparison."""
    import re
    month = sf.month_name(fi["period"])
    out = []
    blocks = [fi["headline"], fi["dek"], *[x for k in fi["kpis"] for x in [k["value"], *k["lines"]]]]
    for text in blocks:
        span_free = re.sub(rf"enero–({MONTH_RX})", r"\1", text)  # an accumulated span ends at its cut month
        for m in re.findall(rf"\b({MONTH_RX})\b", span_free):
            if m != month and "del corte de la partida" not in text:
                out.append(text)
    return out


@pytest.mark.parametrize("prog,cap,card,label", [
    (("2026-03", 3_900_000, 14_100_000), CAP02, "Ejecución programa Fonasa", "a marzo 2026"),  # same cut: programme
    (("2026-04", 5_200_000, 14_100_000), CAP02, "Ejecución Fonasa (capítulo 02)", "a marzo 2026"),  # later: chapter
    (("2026-04", 5_200_000, 14_100_000), {}, "Ejecución programa Fonasa",
     "a abril 2026, un mes después del corte de la partida"),  # no chapter at the cut: labelled distance
])
def test_headline_and_kpis_never_mix_cuts_unlabelled(tmp_path, prog, cap, card, label):
    fi = f7.run(write(tmp_path, lane(prog=prog, cap=cap)), today=TODAY, registry=reg_open(), llm=False)["ficha"]
    assert fi["period"] == "2026-03" and "Fonasa" not in fi["headline"]
    assert unlabelled_other_cuts(fi) == []
    assert fi["kpis"][1]["label"] == card and fi["kpis"][1]["lines"][0] == label
    if prog[0] != "2026-03":  # the programme chart says its cut is another one
        ch = next(c for t in fi["tabs"] for c in t["charts"] if c["id"] == "f7-prog0201-niveles")
        assert "un mes después del corte de la partida" in ch["subtitle"]
    # The checker itself catches the old headline (programme at another month, side by side).
    bad = dict(fi, headline=fi["headline"] + "; el programa Fonasa, el 36,9% a abril 2026")
    assert unlabelled_other_cuts(bad)


def test_committed_lane_keeps_the_partida_cut_on_every_card():
    fi = f7.compose(f7.build_package(REPO, reg_open()), reg_open(), today=TODAY)
    assert unlabelled_other_cuts(fi) == []
    assert all(k["lines"][0] == f"a {sf.month_label(fi['period'])}" for k in fi["kpis"][:3])


# ---------------------------------------------------------------------------------------------------------------------
# HOLD: each reconciliation rule


def test_hold_vigente_not_positive(tmp_path):
    bad = dict(PARTIDA, **{"2026-03": (0, 0)})
    assert "vigente_not_positive:partida:2026-03" in failures(lane(partida=bad), tmp_path)


def test_hold_duplicate_vigente_in_one_document(tmp_path):
    data = lane()
    vig = next(r for r in data["records"] if r["source_url"] == URL.format(n=1002) and r["budget_state"] == "modified")
    data["records"].append(dict(vig, value=vig["value"] + 1))
    assert any(f.startswith(f"vigente_not_unique:2026-03:{URL.format(n=1002)}:2") for f in failures(data, tmp_path))
    data["records"][-1]["value"] = vig["value"]  # even an identical duplicate is not silently accepted
    assert any(f.startswith("vigente_not_unique:2026-03") for f in failures(data, tmp_path))


def test_same_cut_conflict_compares_the_vigente_too(tmp_path):
    other = comparativo(2202, "2026-03", 5_100_000, 17_500_000, P)  # same executed, different vigente
    assert "same_cut_conflict:partida:2026-03" in failures(lane(extra=[(other, "Cuadro Comparativo Analítico")]), tmp_path)


def test_hold_executed_over_vigente(tmp_path):
    bad = dict(PARTIDA, **{"2026-03": (17_500_000, 17_400_000)})
    assert "executed_over_vigente:partida:2026-03" in failures(lane(partida=bad), tmp_path)


def test_hold_when_accumulated_execution_decreases(tmp_path):
    bad = dict(PARTIDA, **{"2026-03": (3_400_000, 17_400_000)})
    assert "executed_decreases:partida:2026-02>2026-03" in failures(lane(partida=bad), tmp_path)


def test_hold_when_a_narrower_perimeter_is_mislabelled_as_the_partida(tmp_path):
    """The real lane's 2027 comparative table reports subpartida 1603 at August (lower than the partida in July). Read
    as a subpartida it is excluded; if a parser dropped the subpartida, monotonicity HOLDs instead of publishing it."""
    sub = comparativo(2100, "2026-04", 4_000_000, 14_000_000, ("16", "1603", None, None))
    fi = f7.run(write(tmp_path, lane(extra=[(sub, "Cuadro Comparativo Analítico Años 2026-2027")])), today=TODAY,
                registry=reg_open(), llm=False)["ficha"]
    assert any("subpartida 1603 (Servicios de Salud)" in n["text"] for n in fi["notes"])
    p = f7.build_package(write(tmp_path, lane(extra=[(sub, "Cuadro Comparativo Analítico Años 2026-2027")])), reg_open())
    assert p["reconciliation"]["ok"] and p["period"] == "2026-03" and p["kpis"]["excluded"] == [["1603", "2026-04"]]
    assert not any(k.startswith("partida.2026-04") for k in p["values"])
    mislabelled = comparativo(2101, "2026-04", 4_000_000, 14_000_000, P)
    assert "executed_decreases:partida:2026-03>2026-04" in failures(
        lane(extra=[(mislabelled, "Cuadro Comparativo Analítico Años 2026-2027")]), tmp_path)


def test_hold_when_two_documents_disagree_on_one_cut(tmp_path):
    other = comparativo(2200, "2026-03", 5_200_000, 17_400_000, P)
    assert "same_cut_conflict:partida:2026-03" in failures(lane(extra=[(other, "Cuadro Comparativo Analítico")]), tmp_path)
    same = comparativo(2201, "2026-03", 5_100_000, 17_400_000, P)  # agrees: the monthly report is used
    p = f7.build_package(write(tmp_path, lane(extra=[(same, "Cuadro Comparativo Analítico")])), reg_open())
    assert p["reconciliation"]["ok"] and p["values"]["partida.2026-03.ejecutado"]["record"]["url"] == URL.format(n=1002)


@pytest.mark.parametrize("mutate,reason", [
    (lambda d: d["document_ledger"].pop(2), "source_not_in_ledger:partida:2026-03"),
    (lambda d: d["document_ledger"][2].update(source_sha256="0" * 64), "source_hash_mismatch:partida:2026-03"),
    (lambda d: [r.update(source_sha256="nohash") for r in d["records"] if r["source_url"] == URL.format(n=1002)],
     "source_without_hash:partida:2026-03"),
])
def test_hold_when_a_value_is_not_traced_to_its_document_hash(tmp_path, mutate, reason):
    data = lane()
    mutate(data)
    assert reason in failures(data, tmp_path)


def test_hold_on_a_non_dipres_or_http_url(tmp_path):
    data = lane()
    for r in data["records"] + data["document_ledger"]:
        if r["source_url"] == URL.format(n=1002):
            r["source_url"] = "http://www.dipres.gob.cl/597/articles-1002_doc_pdf.pdf"
    assert "source_not_dipres_https:partida:2026-03" in failures(data, tmp_path)


@pytest.mark.parametrize("field,val,reason", [
    ("unit", "CLP", "unit_or_basis_unverified:partida:2026-03:executed"),
    ("measurement_basis", "constant_prices", "unit_or_basis_unverified:partida:2026-03:executed"),
    ("period_end", "2026-03-15", "cut_not_accumulated_to_month_end:partida:2026-03"),
    ("period_start", "2026-03-01", "cut_not_accumulated_to_month_end:partida:2026-03"),
    ("published_at", "2026-03-31", "publication_not_after_cut:partida:2026-03"),
])
def test_hold_on_units_and_dates(tmp_path, field, val, reason):
    data = lane()
    for r in data["records"]:
        if r["source_url"] == URL.format(n=1002) and r["budget_state"] == "executed":
            r[field] = val
    assert reason in failures(data, tmp_path)


def test_hold_when_captured_before_the_cut(tmp_path):
    data = lane()
    data["document_ledger"][2]["fetched_at"] = "2026-03-20T00:00:00+00:00"
    assert "captured_before_cut:partida:2026-03" in failures(data, tmp_path)


def test_hold_reaches_run_and_never_publishes(tmp_path):
    bad = dict(PARTIDA, **{"2026-03": (17_500_000, 17_400_000)})
    root = write(tmp_path, lane(partida=bad))
    out = f7.run(root, today=TODAY, registry=reg_open(), llm=False)
    assert out["status"] == "hold" and "executed_over_vigente" in " ".join(out["errors"])
    written = sf.publish(out, root)
    assert not written["published"] and sf.load_live(root, "f7_financiamiento") is None
    assert Path(written["hold"]).name == "f7_financiamiento-2026-03.json"


# ---------------------------------------------------------------------------------------------------------------------
# Nested levels are never summed


def test_partida_never_comes_from_its_chapters(tmp_path):
    """Chapters exist for March but the partida report does not: the partida stays at February (its own record),
    never the sum of chapters; with no partida record at all, HOLD."""
    only_two = {k: v for k, v in PARTIDA.items() if k != "2026-03"}
    p = f7.build_package(write(tmp_path, lane(partida=only_two)), reg_open())
    assert p["reconciliation"]["ok"] and p["period"] == "2026-02"
    assert p["values"]["partida.2026-02.ejecutado"]["value"] == PARTIDA["2026-02"][0] / 1000
    assert "no_partida_cut" in failures(lane(partida={}), tmp_path)


def test_trace_check_rejects_a_summed_or_mixed_value(tmp_path):
    root = write(tmp_path, lane())
    p = f7.build_package(root, reg_open())
    recs = json.loads((root / f7.LANE).read_text())["records"]
    assert f7.trace_failures(p["values"], recs) == []
    summed = copy.deepcopy(p["values"])  # partida := capítulo 02 + programa 02.01 (what the lane forbids)
    summed["partida.2026-03.ejecutado"]["value"] = (CAP02["2026-03"][0] + PROG[1]) / 1000
    assert "value_not_single_record:partida.2026-03.ejecutado" in f7.trace_failures(summed, recs)
    relabelled = copy.deepcopy(p["values"])  # a chapter record cited as the partida
    relabelled["partida.2026-03.ejecutado"]["record"] = relabelled["cap02.2026-03.ejecutado"]["record"]
    assert "value_not_single_record:partida.2026-03.ejecutado" in f7.trace_failures(relabelled, recs)
    mixed = copy.deepcopy(p["values"])  # a ratio across levels
    mixed["partida.2026-03.pct"]["inputs"] = ["cap02.2026-03.ejecutado", "partida.2026-03.vigente"]
    assert "nested_levels_mixed:partida.2026-03.pct" in f7.trace_failures(mixed, recs)
    # No derived value anywhere combines two entities.
    for v in p["values"].values():
        if v["kind"] == "derived":
            assert {p["values"][i]["entity"] for i in v["inputs"]} == {v["entity"]}


# ---------------------------------------------------------------------------------------------------------------------
# Dates: cut ≠ publication; never invent a publication date


def test_without_a_verified_publication_the_ficha_is_dated_by_capture(tmp_path):
    fi = f7.run(write(tmp_path, lane()), today=TODAY, registry=reg_open(), llm=False)["ficha"]
    assert fi["date_basis"] == "first_detected" and fi["published_at"] == "2026-10-11"
    assert fi["kicker_meta"].startswith("datos al 31 mar 2026 (corte; captura manual, próxima actualización pendiente) · detectado por Alicanto el 11 oct")
    # Freshness: the lane is captured by hand; nothing claims a monthly refresh.
    assert "captura manual, próxima actualización pendiente" in fi["kicker_meta"]
    assert "se actualiza" not in " ".join(sf.displayed_texts(fi)) and "manual" in fi["watch"][0]["explanation"]
    card = sf.ficha_card(fi, reg_open()["families"]["F7"])
    assert card["publication_date"] is None and card["first_detected_at"] == "2026-10-11"
    assert card["source_name"] == "Dirección de Presupuestos"


def test_a_verified_publication_after_the_cut_is_labelled_as_such(tmp_path):
    data = lane()
    for r in data["records"]:
        if r["source_url"] == URL.format(n=1002):
            r["published_at"] = "2026-04-28"
    fi = f7.run(write(tmp_path, data), today=TODAY, registry=reg_open(), llm=False)["ficha"]
    assert "date_basis" not in fi and fi["published_at"] == "2026-04-28"
    assert "publicado por DIPRES el 28 abr" in fi["kicker_meta"]


# ---------------------------------------------------------------------------------------------------------------------
# First publication waits for Dirección; no model calls


def test_first_publication_waits_for_a_review_of_that_evidence(tmp_path):
    root = write(tmp_path, lane())
    reg = copy.deepcopy(sf.load_registry())
    assert reg["families"]["F7"]["first_pass_requires_review"] is True
    out = f7.run(root, today=TODAY, registry=reg, llm=False)
    assert out["status"] == "hold" and out["errors"] == [f7.FIRST_REVIEW_HOLD]
    cand = out["candidate"]
    assert cand["status"] == "AWAITING_FIRST_REVIEW" and cand["headline"] and cand["kpis"] and cand["tabs"]
    ev = cand["review_request"]["evidence_sha256"]
    assert ev == f7.evidence_sha256({s["key"]: s for s in cand["sources"]})
    written = sf.publish(out, root)
    assert not written["published"] and json.loads(Path(written["hold"]).read_text())["candidate"]["evidence_sha256"] == ev
    reg["families"]["F7"]["first_review"].update(reviewed_by="revisor de prueba", reviewed_at="2026-11-04", reviewed_sha256="0" * 64)
    assert f7.run(root, today=TODAY, registry=reg, llm=False)["status"] == "hold"
    reg["families"]["F7"]["first_review"].update(reviewed_sha256=ev, reviewed_by=None)
    assert f7.run(root, today=TODAY, registry=reg, llm=False)["status"] == "hold"
    reg["families"]["F7"]["first_review"].update(reviewed_by="revisor de prueba")
    out = f7.run(root, today=TODAY, registry=reg, llm=False)
    assert out["status"] == "pass" and sf.publish(out, root)["published"]
    reg["families"]["F7"]["first_review"].update(reviewed_sha256="f" * 64)  # once live, the normal policy rules
    assert f7.run(root, today=TODAY, registry=reg, llm=False)["status"] in ("pass", "no_change")
    committed = sf.load_registry()["families"]["F7"]
    # Dirección approved the first real F7 ficha on 4-nov-2026 (evidence of the July-2026 cut); Lectura stays off.
    assert committed["first_review"]["reviewed_sha256"] == "d685bc1319275102876917e10a7d3d43ee481faa7b83a0664472c05cafedafd1"
    assert committed["first_review"]["reviewed_by"] and committed["lectura_enabled"] is False


def test_no_model_call_even_with_llm_requested(tmp_path):
    def model(*a, **k):
        raise AssertionError("model called")
    out = f7.run(write(tmp_path, lane()), today=TODAY, registry=reg_open(), llm=True, model_call=model,
                 budget=lambda usd: (True, "ok"))
    assert out["status"] == "pass" and out["ficha"]["lectura"]["status"] == "not_attempted"


# ---------------------------------------------------------------------------------------------------------------------
# Registry, runner, Datos page and the committed lane


def test_registry_runner_and_datos_row(tmp_path):
    import importlib.util
    cfg = sf.load_registry()["families"]["F7"]
    assert cfg["status"] == "active" and cfg["group"] == "sector_publico" and cfg["builder_version"] == f7.BUILDER_VERSION
    assert cfg["datos_kpis"] == ["ejecucion_partida", "ejecucion_fonasa"] and cfg["first_pass_requires_review"] is True
    spec = importlib.util.spec_from_file_location("run_stats_fichas", REPO / "scripts/run_stats_fichas.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    assert runner.BUILDERS["F7"] is f7.run and "F7" not in runner.CAPTURED | runner.FEFI_CAPTURED  # no download
    fi = f7.run(write(tmp_path, lane()), today=TODAY, registry=reg_open(), llm=False)["ficha"]
    card = sf.ficha_card(fi, cfg)
    row = next(r for r in di.build([card], root=tmp_path)["families"] if r["family"] == "F7")
    assert row["state"] == "live" and row["source"] == "DIPRES"
    assert [k["value"] for k in row["kpis"]] == [fi["kpis"][0]["value"], fi["kpis"][1]["value"]]


def test_committed_lane_passes_reconciliation_and_traces_every_kpi():
    """The committed DIPRES lane: assert the rules, not the counts (PLAYBOOK §4)."""
    reg = reg_open()
    p = f7.build_package(REPO, reg)
    assert p["reconciliation"]["ok"], p["reconciliation"]["failures"]
    lane_recs = json.loads((REPO / f7.LANE).read_text(encoding="utf-8"))["records"]
    assert f7.trace_failures(p["values"], lane_recs) == []
    t = p["period"]
    e, vg = (next(r["value"] for r in lane_recs if f7.entity_key(r) == f7.ENTITIES["partida"] and r["metric"] == "gastos"
                  and r["budget_state"] == s and r["source_url"] == p["primary_source"]["url"]) for s in ("executed", "modified"))
    assert p["values"][f"partida.{t}.pct"]["value"] == pytest.approx(e / vg * 100)
    # Other perimeters (subpartidas) are listed in the notes, never read as the partida: no partida figure comes from
    # a subpartida's document. (A month may have both: a partida report and a subpartida table, 5-nov-2026.)
    sub_urls = {r["source_url"] for r in lane_recs if r.get("subpartida")}
    for sub, per in p["kpis"]["excluded"]:
        assert sub and per
    assert not any(v.get("record", {}).get("url") in sub_urls for v in p["values"].values() if v.get("entity") == "partida")
    from radar_salud.stats_fichas import run_family
    out = run_family("F7", builder_version=f7.BUILDER_VERSION, build_package=f7.build_package, compose=f7.compose,
                     root=REPO, today=TODAY, registry=reg, llm=False)
    assert out["status"] in ("pass", "no_change"), out.get("errors")


def test_card_links_the_latest_report_first():
    """Dirección 5-nov-2026: 'Fuente original' opened the January report. Each DIPRES report is cumulative to its cut,
    so the card links the latest one (the primary source) and the ficha lists it first."""
    reg = reg_open()
    p = f7.build_package(REPO, reg)
    fi = f7.compose(p, reg, today=TODAY)
    assert fi["sources"][0]["url"] == p["primary_source"]["url"]
    from radar_salud.stats_fichas import ficha_card
    assert ficha_card({**fi, "status": "PASS"}, reg["families"]["F7"])["source_url"] == p["primary_source"]["url"]


def test_verifier_rejects_a_ficha_whose_first_source_is_not_the_primary():
    from radar_salud.stats_fichas import verify_ficha
    reg = reg_open()
    p = f7.build_package(REPO, reg)
    fi = f7.compose(p, reg, today=TODAY)
    assert "first_source_not_primary" not in verify_ficha(fi, p)["errors"]
    fi["sources"] = fi["sources"][::-1]
    assert "first_source_not_primary" in verify_ficha(fi, p)["errors"]
