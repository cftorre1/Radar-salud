import copy
import json
from pathlib import Path

from radar_salud.isapre_pulse import RELEASE_URLS, build_pulse


def canonical():
    return json.loads(Path("data/excel/validated_series.json").read_text(encoding="utf-8"))


def releases():
    return json.loads(Path("data/history/superintendencia_signals.json").read_text(encoding="utf-8"))["signals"]


def test_pulse_reconciles_real_three_family_series():
    pulse = build_pulse(canonical(), releases())
    assert pulse is not None
    assert pulse["data_insight_meta"]["families"] == ["cartera", "suscripciones", "movilidad"]
    assert pulse["data_period"] == "2026-07"
    assert pulse["event_date"] == pulse["publication_date"] == "2026-09-07"
    assert pulse["validation_date"] == "2026-09-24"
    assert "2.487.497" in pulse["what_happened"]
    assert "-17.700" in " ".join(pulse["key_points"])
    assert pulse["ingestion_mode"] == "BACKFILL"
    assert len(pulse["data_insights"]) == 5
    assert len(pulse["data_insight_evidence"]) == 5
    assert "Datos" not in pulse["data_insights"][0]
    assert pulse["data_insight_evidence"][0]["period"] == "2026-01 → 2026-07"
    assert {x["analysis_kind"] for x in pulse["data_insight_evidence"]} == {
        "beneficiary_stock_change", "portfolio_mix_shift", "beneficiary_streak",
        "subscriptions_voluntary_gap", "mobility_interval"}
    mix = next(x for x in pulse["data_insight_evidence"] if x["analysis_kind"] == "portfolio_mix_shift")
    assert "0.615 → 0.605" in mix["text"]
    assert "72.9%" in mix["text"]
    assert "no causa ni ingreso" in mix["text"]
    assert "6 bajas mensuales" in pulse["why_it_matters"]
    assert "otras terminaciones" in pulse["why_it_matters"]
    assert pulse["data_insight_meta"]["business_review"] == "sustained_contraction_and_mix_watch_without_causal_attribution"
    assert len(pulse["source_alternatives"]) == 3
    assert {x["family"] for x in pulse["source_alternatives"]} == {"cartera", "suscripciones", "movilidad"}
    assert all(x["event_date"] == "2026-09-07" and "/biblioteca-digital/" in x["url"]
               for x in pulse["source_alternatives"])


def test_pulse_fails_closed_for_missing_unvalidated_or_unreconciled_family():
    base = canonical()
    for change in (
        lambda v: v["families"].pop("movilidad"),
        lambda v: v["families"]["cartera"].update(status="pending"),
        lambda v: v["families"]["suscripciones"]["series"][-1].update(period="2026-06"),
        lambda v: v["families"]["movilidad"]["series"][-1]["metrics"].update(entradas_intervalo=1),
        lambda v: v["families"]["cartera"]["series"][-1]["metrics"].update(beneficiarios=1),
        lambda v: v["families"]["cartera"].update(sha256="0" * 63 + "z"),
        lambda v: v["families"]["cartera"].update(source_url="https://example.org/file.xlsx"),
        lambda v: v["families"]["cartera"]["series"][1]["metrics"].update(beneficiarios=1),
        lambda v: v["families"]["cartera"]["series"][0].update(period="2026-07"),
        lambda v: v["families"]["suscripciones"]["series"][5]["metrics"].update(contratos_suscritos=0),
        lambda v: v["families"]["movilidad"]["series"][0].update(period_start="2026-06"),
    ):
        altered = copy.deepcopy(base)
        change(altered)
        assert build_pulse(altered, releases()) is None


def test_business_reading_uses_current_reconciled_series_instead_of_frozen_copy():
    changed = canonical()
    january = changed["families"]["cartera"]["series"][0]["metrics"]
    january["cotizantes"] += 1000
    january["beneficiarios"] += 1000
    pulse = build_pulse(changed, releases())
    assert pulse is not None
    assert "27.541 beneficiarios menos" in pulse["why_it_matters"]
    assert "26.541 beneficiarios menos" not in pulse["why_it_matters"]
    assert pulse["data_insight_meta"]["business_metrics"]["beneficiary_decline"] == 27541


def test_pulse_fails_closed_without_three_dated_official_release_pages():
    base = releases()
    assert build_pulse(canonical(), []) is None
    for change in (
        lambda rows: rows.__setitem__(slice(None), [x for x in rows if "Suscripciones y Desahucios" not in x.get("title", "")]),
        lambda rows: next(x for x in rows if "Movilidad de Cartera" in x.get("title", "")).update(event_date="periodo julio 2026"),
        lambda rows: next(x for x in rows if "Cartera de Beneficiarios del Sistema ISAPRE – año 2026" in x.get("title", "")).update(source_url="https://example.org/cartera"),
        lambda rows: next(x for x in rows if "Movilidad de Cartera" in x.get("title", "")).update(source_url=RELEASE_URLS["cartera"]),
    ):
        altered = copy.deepcopy(base)
        change(altered)
        assert build_pulse(canonical(), altered) is None


def test_pulse_fails_closed_for_future_publication_or_validation_dates():
    future_releases = copy.deepcopy(releases())
    for item in future_releases:
        if item.get("source_url") in RELEASE_URLS.values():
            item["event_date"] = "2030-01-01"
    assert build_pulse(canonical(), future_releases) is None

    future_validation = canonical()
    future_validation["validated_at"] = "2030-01-02T12:00:00Z"
    assert build_pulse(future_validation, releases()) is None
