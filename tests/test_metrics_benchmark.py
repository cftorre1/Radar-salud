from radar_salud.models import MetricDefinition, MetricObservation
from radar_salud.metrics import validate_observation, latest_by_entity, benchmark_metric, group_metric_summary


def definition():
    return MetricDefinition(
        metric_id="isapre_gasto_prestaciones_per_capita",
        name="Gasto en prestaciones per cápita",
        family="PRESTACIONES_Y_USO",
        institution_types=["ISAPRE"],
        unit="CLP_per_beneficiary",
        description="Gasto en prestaciones dividido por beneficiarios del período",
        denominator_definition="beneficiarios promedio del período",
        segment_dimensions=["sex", "age_band"],
        source_preferences=["SUPERINTENDENCIA_SALUD"],
    )


def obs(entity, value, period_end="2026-06-30", sex=None):
    return MetricObservation(
        entity_id=entity,
        metric_id="isapre_gasto_prestaciones_per_capita",
        value=value,
        unit="CLP_per_beneficiary",
        period_start="2026-01-01",
        period_end=period_end,
        source_name="Superintendencia de Salud",
        source_url="https://example.com/data",
        institution_type="ISAPRE",
        segment={} if sex is None else {"sex": sex},
    )


def test_metric_observation_validates_against_definition():
    assert validate_observation(obs("A", 100.0), definition()) == []


def test_unit_mismatch_is_rejected():
    o = obs("A", 100.0)
    o.unit = "UF"
    assert any("unit mismatch" in e for e in validate_observation(o, definition()))


def test_latest_by_entity_uses_latest_period():
    values = [obs("A", 100, "2026-03-31"), obs("A", 120, "2026-06-30"), obs("B", 90, "2026-06-30")]
    latest = latest_by_entity(values, definition().metric_id)
    assert latest["A"].value == 120
    assert latest["B"].value == 90


def test_benchmark_metric_keeps_source_and_period():
    rows = benchmark_metric([obs("A", 120), obs("B", 90)], definition())
    assert rows[0]["entity_id"] == "A"
    assert rows[0]["source_name"] == "Superintendencia de Salud"
    assert rows[0]["period_end"] == "2026-06-30"


def test_group_summary_uses_explicit_segment_dimension():
    rows = [obs("A", 120, sex="F"), obs("B", 100, sex="F"), obs("A", 80, sex="M")]
    summary = group_metric_summary(rows, definition().metric_id, "sex")
    assert summary["F"]["mean"] == 110
    assert summary["M"]["mean"] == 80
