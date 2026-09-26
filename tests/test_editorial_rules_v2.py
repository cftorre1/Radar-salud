import json
from pathlib import Path

from src.radar_salud.editorial_gate import publication_ready
from src.radar_salud.editorial_rules_v2 import evaluate_editorial_v2, load_rules


def test_rules_config_has_complete_weights_and_taxonomy():
    rules = load_rules()
    assert round(sum(rules["materiality"]["dimensions"].values()), 6) == 1
    assert len(rules["taxonomy"]) == 11
    assert set(rules["decisions"]) == {"accept", "degrade", "group", "reject"}


def test_editorial_fixtures_regress_expected_decisions():
    fixtures = json.loads(Path("tests/fixtures/editorial_rules_v2.json").read_text())
    for case in fixtures["cases"]:
        result = evaluate_editorial_v2(case["candidate"])
        assert result.decision == case["expected"], case["id"]


def test_pipeline_gate_enforces_v2_decision_when_assessment_is_present():
    fixture = json.loads(Path("tests/fixtures/editorial_rules_v2.json").read_text())
    accepted = fixture["cases"][0]["candidate"] | {
        "title": "Cambio regulatorio material para isapres",
        "what_happened": "La autoridad instruyó una adecuación operativa verificable para las isapres.",
        "why_it_matters": "Las isapres deben cambiar el flujo antes del plazo regulatorio y revisar su implementación.",
        "source_url": "https://example.org/resolution",
        "event_date": "2026-09-26",
    }
    assert publication_ready(accepted)[0] is True
    rejected = accepted | {"editorial_v2": fixture["cases"][1]["candidate"]["editorial_v2"]}
    ready, reason, _ = publication_ready(rejected)
    assert ready is False
    assert reason == "editorial_v2_reject"


def test_empty_v2_structure_cannot_bypass_pipeline_gate():
    candidate = {
        "title": "Título aparentemente suficiente para la puerta anterior",
        "what_happened": "Un actor realizó una acción descrita con suficiente extensión para el gate anterior.",
        "why_it_matters": "La redacción genérica también supera la longitud, pero no aporta estructura v2.",
        "source_url": "https://example.org/item",
        "event_date": "2026-09-26",
        "editorial_v2": {},
    }
    ready, reason, _ = publication_ready(candidate)
    assert ready is False
    assert reason == "editorial_v2_reject"


def test_special_piece_requires_structured_refs_from_independent_sources():
    fixtures = json.loads(Path("tests/fixtures/editorial_rules_v2.json").read_text())
    global_case = fixtures["cases"][4]["candidate"]
    malformed = json.loads(json.dumps(global_case))
    malformed["editorial_v2"]["evidence_refs"] = ["a", "b"]
    result = evaluate_editorial_v2(malformed)
    assert result.decision == "degrade"
    assert "missing_impact_evidence" in result.reasons
    same_source = json.loads(json.dumps(global_case))
    same_source["editorial_v2"]["evidence_refs"] = [
        {"url": "https://example.org/a", "source": "WHO"},
        {"url": "https://example.org/b", "source": "WHO"},
    ]
    result = evaluate_editorial_v2(same_source)
    assert result.decision == "degrade"
    assert "insufficient_independent_evidence" in result.reasons


def test_missing_evidence_degrades_before_routine_grouping():
    fixtures = json.loads(Path("tests/fixtures/editorial_rules_v2.json").read_text())
    routine = json.loads(json.dumps(fixtures["cases"][2]["candidate"]))
    routine["editorial_v2"]["evidence_refs"] = []
    result = evaluate_editorial_v2(routine)
    assert result.decision == "degrade"
    assert result.reasons == ("missing_impact_evidence",)


def test_malformed_v2_inputs_fail_closed_without_exceptions():
    fixtures = json.loads(Path("tests/fixtures/editorial_rules_v2.json").read_text())
    base = fixtures["cases"][0]["candidate"]
    assert evaluate_editorial_v2({"editorial_v2": "invalid"}).decision == "reject"
    bad_materiality = json.loads(json.dumps(base))
    bad_materiality["editorial_v2"]["materiality"] = []
    assert evaluate_editorial_v2(bad_materiality).decision == "reject"
    bad_url = json.loads(json.dumps(base))
    bad_url["editorial_v2"]["evidence_refs"] = [
        {"url": "https://[invalid", "source": "Declared source"}
    ]
    result = evaluate_editorial_v2(bad_url)
    assert result.decision == "degrade"
    assert "missing_impact_evidence" in result.reasons
    no_host = json.loads(json.dumps(fixtures["cases"][4]["candidate"]))
    no_host["editorial_v2"]["evidence_refs"] = [
        {"url": "https:foo", "source": "A"},
        {"url": "https:bar", "source": "B"},
    ]
    assert evaluate_editorial_v2(no_host).decision == "degrade"
    pipeline_candidate = {
        "title": "Cambio material informado por una fuente oficial",
        "what_happened": "La autoridad informó una acción suficientemente extensa para el gate anterior.",
        "why_it_matters": "La pieza parece extensa, pero la estructura editorial v2 es deliberadamente inválida.",
        "source_url": "https://example.org/item",
        "event_date": "2026-09-26",
        "editorial_v2": "invalid",
    }
    assert publication_ready(pipeline_candidate)[:2] == (False, "editorial_v2_reject")
