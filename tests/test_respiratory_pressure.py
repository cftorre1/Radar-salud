import copy
import json
from datetime import date
from pathlib import Path

from radar_salud.respiratory_pressure import build_respiratory_pressure
from radar_salud.editorial_rules_v2 import evaluate_editorial_v2


DATASET = json.loads(Path("data/epidemiology/respiratory_pressure_2026.json").read_text(encoding="utf-8"))


def test_official_weekly_report_builds_noncausal_provider_ready_signal():
    signal = build_respiratory_pressure(DATASET, date(2026, 9, 26))
    assert signal is not None
    assert signal["distribution"] == "provider_ready_not_promoted"
    assert signal["ingestion_mode"] == "BACKFILL"
    assert signal["data_period"] == "SE 37 · 2026-09-13 a 2026-09-19"
    assert "93.1%" in signal["why_it_matters"]
    assert "no atribuye causalidad" in signal["why_it_matters"]
    assert evaluate_editorial_v2(signal).decision == "accept"
    assert len(signal["editorial_v2"]["evidence_refs"]) == 1
    assert any("inconsistencia" in note for note in signal["risk_notes"])


def test_future_malformed_or_nonofficial_evidence_fails_closed():
    future = copy.deepcopy(DATASET)
    future["report_date"] = "2026-09-27"
    assert build_respiratory_pressure(future, date(2026, 9, 26)) is None
    spoofed = copy.deepcopy(DATASET)
    spoofed["source"]["url"] = "https://example.org/report.pdf"
    assert build_respiratory_pressure(spoofed, date(2026, 9, 26)) is None
    malformed = copy.deepcopy(DATASET)
    malformed["care_pressure"]["adult_critical_bed_occupancy_pct"] = "93.1"
    assert build_respiratory_pressure(malformed, date(2026, 9, 26)) is None


def test_missing_risk_note_or_virus_dimension_fails_closed():
    no_risk = copy.deepcopy(DATASET)
    no_risk["risk_notes"] = []
    assert build_respiratory_pressure(no_risk, date(2026, 9, 26)) is None
    missing = copy.deepcopy(DATASET)
    del missing["virus_surveillance"]["distribution_pct"]["metapneumovirus"]
    assert build_respiratory_pressure(missing, date(2026, 9, 26)) is None


def test_future_valid_increase_and_new_occupancy_are_not_rendered_as_decline_or_old_value():
    changed = copy.deepcopy(DATASET)
    changed["care_pressure"]["respiratory_emergency_share_pct"] = 33.0
    changed["care_pressure"]["lower_respiratory_emergency_visits_weekly_change_pct"] = 4.2
    changed["care_pressure"]["respiratory_hospitalizations_weekly_change_pct"] = 1.1
    changed["care_pressure"]["adult_critical_bed_occupancy_pct"] = 88.0
    changed["virus_surveillance"]["positivity_pct"] = 65.0
    signal = build_respiratory_pressure(changed, date(2026, 9, 26))
    assert signal is not None
    assert "sube" in signal["title"] and "88.0%" in signal["title"]
    assert "positividad respiratoria subió de 56.7% a 65.0%" in signal["what_happened"]
    assert "aumentaron 4.2%" in signal["why_it_matters"]
    assert "aumentaron 1.1%" in signal["why_it_matters"]
    assert "disminuyeron" not in signal["why_it_matters"]
