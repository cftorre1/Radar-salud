"""Dirección 28-oct-2026 09:58: Global relevance = trends and global interest (helps the Chilean market prepare)."""
import json
from pathlib import Path

import pytest

from radar_salud.global_relevance import global_interest, source_rules, validate_rules

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "config/global_discovery.json").read_text())


def gate(title, source=None):
    return global_interest(title, (), source=source, rules=source_rules(CONFIG, source))


NOT_RELEVANT = [
    # bed use
    ("Hospital bed occupancy hits record high in England this winter", None, "bed_or_capacity_use"),
    ("ICU capacity strained as RSV cases climb", None, "bed_or_capacity_use"),
    # drug safety alerts and recalls (no "always include" rule: patient safety alerts are out too)
    ("Abbott recalls certain FreeStyle Libre 3 sensors", "fda", "safety_alert_or_recall"),
    ("FDA issues safety communication on risk of serious liver injury with Veozah", "fda", "safety_alert_or_recall"),
    ("National Patient Safety Alert: risk of death from incorrect insulin dosing", "uk_mhra", "safety_alert_or_recall"),
    ("Class 2 Medicines Recall: Accord Healthcare Ltd, Metformin 500mg tablets", "uk_mhra", "safety_alert_or_recall"),
    ("FDA warns consumers not to use contaminated eye drops", "fda", "safety_alert_or_recall"),
    # provider acquisitions
    ("HCA Healthcare to acquire five hospitals in Florida", None, "provider_transaction"),
    ("Optum completes acquisition of physician group in Ohio", None, "provider_transaction"),
    # new center openings
    ("Mayo Clinic opens new cancer center in Phoenix", None, "facility_opening"),
    ("OPS inaugura nuevo centro de vacunación en Bolivia", "paho", "facility_opening"),
    # single-product approvals (FDA press / EMA)
    ("FDA approves Zepbound for obstructive sleep apnea", "fda", "single_product_approval"),
    ("EMA recommends approval of Kisunla for early Alzheimer's disease", "ema", "single_product_approval"),
    ("FDA approves first generic of Victoza", "fda", None),  # "first generic" is still a single product: no exception for generics
    # routine/one-off by source rule or with no global-interest signal
    ("Kisunla", "ema", "no_global_interest_signal"),
    ("FDA Roundup: October 24, 2026", "fda", "source_rule_exclusion"),
    ("Notes from the Field: Measles Outbreak Linked to a Child Care Center — Texas, 2026", "cdc", "source_rule_exclusion"),
    ("Communicable disease threats report, 19-25 October 2026, week 43", "ecdc", "source_rule_exclusion"),
    ("Disease Outbreak News: Marburg virus disease - Ethiopia", "who", "source_rule_exclusion"),
    ("Alerta epidemiológica: sarampión en la Región de las Américas", "paho", "source_rule_exclusion"),
    ("World Mental Health Day 2026: messages from the Director-General", "who", "source_rule_exclusion"),
    # review 28-oct: a generic "law" without a health-system term is not a system reform
    ("When abortion and surrogacy law collide, contracts can't answer the hardest questions", "the_conversation",
     "no_global_interest_signal"),
    # review 28-oct: one-off diplomatic or single-country items
    ("Mexico and the EU kick off High-Level Dialogue on Health", "ec_health", "one_off_diplomatic_or_country"),
    ("Country report: ECDC Public Health Emergency Preparedness Assessment for Norway", "ecdc",
     "one_off_diplomatic_or_country"),
    # a single private-equity acquisition of one provider is still a one-off transaction
    ("Private equity firm buys methadone clinic in Ohio", None, "provider_transaction"),
    ("Investor group bought a rural hospital in Kansas", None, "provider_transaction"),
]

RELEVANT = [
    ("FDA approves first gene therapy for sickle cell disease", "fda"),
    ("FDA authorizes first AI-based device to detect skin cancer in primary care", "fda"),
    ("FDA launches pilot program to speed review of novel biosimilars", "fda"),
    ("WHO releases first global report on artificial intelligence in health", "who"),
    ("Medicare finalizes 2027 physician fee schedule with new payment model for primary care", "federal_register_cms"),
    ("OECD study: health spending to outpace GDP growth in most countries", None),
    ("Nurse staffing shortages worsen across Europe, survey finds", "ecdc"),
    ("European Health Data Space regulation enters into force", "ec_health"),
    ("Commission proposes Critical Medicines Act to secure supply in the EU", "ec_health"),
    ("Germany passes hospital reform to cut inpatient capacity and fund outpatient care", None),
    ("Large NIH study finds GLP-1 drugs linked to lower dementia risk", "nih"),
    ("Value-based payment models cut costs in diabetes care, analysis shows", "kff_health_news"),
    ("FTC sues to block hospital merger, citing price increases", None),
    ("La OPS insta a fortalecer la atención primaria en América Latina", "paho"),
    ("Global obesity rates continue rising, new estimates show", "who"),
    ("How AI scribes are changing doctors' workload", "the_conversation"),
    ("EU pharmaceutical legislation: Council and Parliament reach deal", "ema"),
    ("Prevalence of long COVID among US adults, 2025", "cdc"),
    # review 28-oct: private equity moving into care is a financing trend
    ("Private equity is buying up more methadone clinics, raising concerns about care", "kff_health_news"),
    # review 28-oct: a study/evidence finding (modelled impact) is an international study
    ("As the cold season nears, immunisation of newborns against universal RSV could significantly reduce infant "
     "hospitalisations", "ecdc"),
    ("As the cold season nears, immunisation of newborns against universal RSV could significantly reduce infant hos…",
     "ecdc"),
    # a generic policy word next to a health-system term still passes
    ("New law caps insulin out-of-pocket costs for insured patients", None),
]


@pytest.mark.parametrize("title,source,category", NOT_RELEVANT)
def test_operational_one_offs_are_not_global_interest(title, source, category):
    result = gate(title, source)
    assert result["relevant"] is False, (title, result)
    if category:
        assert result["category"] == category, (title, result)


@pytest.mark.parametrize("title,source", RELEVANT)
def test_trends_reforms_financing_ai_and_workforce_are_global_interest(title, source):
    result = gate(title, source)
    assert result["relevant"] is True, (title, result)
    assert result["signals"]


def test_rules_are_configured_for_every_global_source_and_have_no_include_always():
    validate_rules(CONFIG)
    sources = set(CONFIG["global_relevance"]["sources"])
    assert {f["id"] for f in CONFIG["feeds"]} | {r["source"] for r in CONFIG["routes"]} <= sources
    bad = json.loads(json.dumps(CONFIG))
    bad["global_relevance"]["sources"]["uk_mhra"]["include_title_patterns"] = [r"\bsafety alert\b"]
    with pytest.raises(ValueError, match="no include-always rule"):
        validate_rules(bad)


def test_source_interest_never_overrides_a_global_exclusion():
    rules = {"interest_title_patterns": [r"\brecall\b"]}
    assert global_interest("Company recall of insulin pens", rules=rules)["relevant"] is False


def test_vaccination_coverage_is_not_a_financing_signal():
    assert gate("Measles vaccination coverage among kindergartners", None)["relevant"] is False


def test_policy_signal_requires_a_health_system_term():
    assert gate("Parliament passes new surrogacy law")["relevant"] is False
    result = gate("Parliament passes new law on health insurance reimbursement")
    assert result["relevant"] is True and "policy_or_system_reform" in result["signals"]


def test_private_equity_trend_signals_and_single_deal_exclusion():
    trend = gate("Private equity is buying up more methadone clinics, raising concerns about care", "kff_health_news")
    assert trend["signals"] == ["financing_and_payment"]
    single = gate("Private equity firm acquires Lakeside Clinic")
    assert single["relevant"] is False and single["category"] == "provider_transaction"
