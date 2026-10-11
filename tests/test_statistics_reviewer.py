from scripts.statistics_reviewer import review_statistics
import importlib.util
from pathlib import Path

builder_spec = importlib.util.spec_from_file_location("statistics_builder", Path("scripts/build_statistics_deep_analysis.py"))
builder = importlib.util.module_from_spec(builder_spec)
builder_spec.loader.exec_module(builder)


URLS = {
    "ges": "https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-trimestral-de-casos-ges-auge-de-fonasa-y-sistema-isapre-a-marzo-2026/",
    "series": "https://www.superdesalud.gob.cl/biblioteca-digital/series-estadisticas-del-sistema-isapre-1990-2025/",
    "financial": "https://www.superdesalud.gob.cl/biblioteca-digital/estadisticas-financieras-del-sistema-isapre-a-marzo-2026/",
    "bulletin": "https://www.superdesalud.gob.cl/biblioteca-digital/boletin-estadistico-informativo-ip-junio-2026/",
}
GES_WORKBOOK = "https://www.superdesalud.gob.cl/app/uploads/2026/07/estadistica-trimestral-de-casos-ges-auge-de-fonasa-y-sistema-isapre-marzo-2026-1.xlsx"
SERIES_FILES = [
    "https://www.superdesalud.gob.cl/app/uploads/2026/03/2-cartera-de-beneficiarios-anos-1990-2025.xlsx",
    "https://www.superdesalud.gob.cl/app/uploads/2026/03/7-casos-ges-anos-2005-2025.xlsx",
]
FILES = [
    "https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf",
    "https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-mediacion-enero-junio-2026.pdf",
    "https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-reclamos-enero-junio-2026.pdf",
    "https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-rnpi-enero-junio-2026.pdf",
]
COMMON = {
    "methodology_visibility": "collapsed",
    "card_why_optional": True,
    "incremental_value_gate": {"table": "new information", "conclusion": "useful only"},
    "data_insights": [],
    "data_insight_evidence": [{"text": "validated source", "period": "2026", "formula": "official", "sheet": "sheet", "source_url": GES_WORKBOOK}],
}


def releases():
    ges_rows = [[f"Problema de salud {i}", 100, 50, 150, 33.3] for i in range(5)]
    series_rows = [["Beneficiarios promedio anual", "Promedio anual de stock", "personas", 2_695_070, 2_556_288, -138_782, -5.1],
                   ["Casos GES", "Flujo anual total del sistema (Isapres + Fonasa)", "casos", 3_755_592, 4_278_631, 523_039, 13.9]]
    financial_rows = [[f"Isapre {i}", 100, -10, 20] for i in range(10)]
    bulletin_rows = [
        ["Acreditación", "Prestadores acreditados", "Stock", "30-jun-2026", "971", "101 (10%)"],
        ["Mediación", "Mediadores inscritos", "Stock", "30-jun-2026", "175", "RM 45%"],
        ["Mediación", "Solicitudes", "Flujo acumulado", "ene-2019 a jun-2026", "12.067", "Total"],
        ["Reclamos", "Promedio mensual", "Promedio de flujo", "ene–jun 2026", "1.996", "+30%"],
        ["RNPI", "Títulos inscritos", "Stock", "30-jun-2026", "1.004.982", "4.036 sin fecha"],
    ]
    return [
        {**COMMON, "source_url": URLS["ges"], "statistical_value_level": "deep_analysis",
         "statistical_methodology": {"sheet": "Año 2026"},
         "summary_table": {"columns": ["Problema de salud", "Fonasa (casos)", "Isapre (casos)", "Total (casos)", "Isapre (%)"],
                           "rows": [{"cells": row} for row in ges_rows]}},
        {**COMMON, "source_url": URLS["series"], "statistical_value_level": "deep_analysis",
         "data_insight_evidence": [{**COMMON["data_insight_evidence"][0], "source_url": source} for source in SERIES_FILES],
         "statistical_methodology": {"validated_series": [
             {"variable": "Beneficiarios promedio anual", "sheet": "Promedio Anual de Cartera"},
             {"variable": "Casos GES", "sheet": "Casos Resumen"},
         ]},
         "summary_table": {"columns": ["Variable", "Tipo", "Unidad", "2024", "2025", "Cambio absoluto", "Cambio (%)"],
                           "rows": [{"cells": row} for row in series_rows]}},
        {**COMMON, "source_url": URLS["financial"], "statistical_value_level": "deep_analysis",
         "statistical_methodology": {"source_url": URLS["financial"]},
         "data_insight_evidence": [{**COMMON["data_insight_evidence"][0],
                                    "source_url": "https://www.superdesalud.gob.cl/app/uploads/2026/07/finan_ifrs_mar_2026_web_v2.xls"}],
         "summary_table": {"columns": ["Isapre", "Ingresos (CLP millones)", "Resultado operacional (CLP millones)", "Utilidad/pérdida neta (CLP millones)"],
                           "rows": [{"cells": row} for row in financial_rows]}},
        {**COMMON, "source_url": URLS["bulletin"], "statistical_value_level": "deep_analysis",
         "data_insight_evidence": [{"text": "source", "period": "2026", "formula": "official", "sheet": "boletín",
                                   "source_url": file} for file in FILES],
         "summary_table": {"columns": ["Tema", "Métrica", "Tipo", "Período", "Valor", "Detalle"],
                           "rows": [{"cells": row} for row in bulletin_rows]}},
    ]


def test_statistics_reviewer_accepts_semantically_labeled_release_tables():
    assert review_statistics(releases()) == []


def test_statistics_build_only_requests_current_release_inputs_at_day90_boundary():
    history=[{"source_url":builder.GES_PAGE,"event_date":"2026-07-10"},
             {"source_url":builder.BOLETIN_PAGE,"event_date":"2026-08-03"},
             {"source_url":"https://fixture.example/reference","event_date":"2026-10-08"}]
    assert set(builder.current_release_builders(history))=={builder.GES_PAGE,builder.BOLETIN_PAGE}
    history[-1]["event_date"]="2026-10-09"
    assert set(builder.current_release_builders(history))=={builder.BOLETIN_PAGE}
    assert history[0]["event_date"]=="2026-07-10"


def test_statistics_reviewer_fails_closed_on_outlier_and_unitless_prestaciones():
    signals = releases()
    signals[1]["summary_table"]["rows"].append({"cells": ["Prestaciones", "Desconocido", "monto", 4_526_117_479_378,
                                                           4_784_847_384_336, 258_729_904_958, 5.7]})
    findings = review_statistics(signals)
    assert "unverified_prestaciones_published" in {finding["code"] for finding in findings}
    assert "series_incomplete_or_mixed_units" in {finding["code"] for finding in findings}


def test_statistics_reviewer_rejects_miscomputed_ges_and_missing_bulletin_pdf():
    signals = releases()
    signals[0]["summary_table"]["rows"][0]["cells"][3] = 151
    signals[3]["data_insight_evidence"] = signals[3]["data_insight_evidence"][:-1]
    findings = review_statistics(signals)
    codes = {finding["code"] for finding in findings}
    assert "ges_total_mismatch" in codes
    assert "bulletin_missing_pdf" in codes


def test_series_parser_checks_schema_period_unit_and_scale(monkeypatch):
    class Sheet:
        title = "Promedio Anual de Cartera"
        def iter_rows(self, **kwargs):
            return iter([
                ("Variable", 2024, 2025),
                ("Total Sistema", 1_647_577, 1_573_534),
                ("Total Sistema", 1_047_492, 982_753),
                ("Total Sistema", 2_695_070, 2_556_288),
            ])
    class Book:
        worksheets = [Sheet()]
    monkeypatch.setattr(builder, "workbook", lambda url: Book())
    values = builder.validated_year_totals("source.xlsx", "Beneficiarios promedio anual", "personas", 500_000, 10_000_000, "Promedio Anual de Cartera")
    assert values[0] == "Promedio Anual de Cartera"
    assert values[3:] == (2_695_070, 2_556_288)


def test_series_parser_rejects_suspicious_scale(monkeypatch):
    class Sheet:
        title = "Prestaciones"
        def iter_rows(self, **kwargs):
            return iter([("Variable", 2024, 2025),
                         ("Total beneficiarios", 4_526_117_479_378, 4_784_847_384_336)])
    class Book:
        worksheets = [Sheet()]
    monkeypatch.setattr(builder, "workbook", lambda url: Book())
    try:
        builder.validated_year_totals("source.xlsx", "Beneficiarios promedio anual", "personas", 500_000, 10_000_000, "Promedio Anual de Cartera")
    except RuntimeError as error:
        assert "expected one" in str(error)
    else:
        raise AssertionError("Suspicious scale should fail closed")


def test_series_ges_parser_rejects_subtotal_rows_and_keeps_total_system_scope(monkeypatch):
    class Sheet:
        title = "Casos Resumen"
        def iter_rows(self, **kwargs):
            return iter([("Variable", 2024, 2025),
                         ("Subtotal Isapres", 150_956, 255_062),
                         ("Subtotal Fonasa", 3_604_636, 4_023_569),
                         ("Total Sistema", 3_755_592, 4_278_631)])
    class Book:
        worksheets = [Sheet()]
    monkeypatch.setattr(builder, "workbook", lambda url: Book())
    values = builder.validated_year_totals("source.xlsx", "Casos GES", "casos", 10_000, 10_000_000, "Casos Resumen")
    assert values[2].startswith("total sistema")
    assert values[3:] == (3_755_592, 4_278_631)


def test_ges_parser_handles_multilevel_insurer_headers_and_uses_source_problem_names(monkeypatch):
    class Sheet:
        title = "Año 2026"
        def iter_rows(self, **kwargs):
            return iter([
                ("N°", "PROBLEMA DE SALUD", "Número de casos acumulados Jul-2005 a Mar-2026", None),
                (None, None, "FONASA", "ISAPRE"),
                (None, None, "2026-03-31", "2026-03-31"),
                *[(str(i), f"Problema de salud validado {i}", 100 + i, 50 + i) for i in range(1, 7)],
            ])
    class Book:
        worksheets = [Sheet()]
    monkeypatch.setattr(builder, "workbook", lambda url: Book())
    result = builder.ges()
    assert result["summary_table"]["rows"][0]["cells"][0] == "Problema de salud validado 6"
    assert result["summary_table"]["rows"][0]["cells"][3] == 162
    assert result["statistical_methodology"]["sheet"] == "Año 2026"


def test_inventory_label_does_not_exempt_known_bulletin_from_inherited_gates():
    import json
    history = json.loads(Path("data/history/superintendencia_signals.json").read_text())["signals"]
    original = next(s for s in history if s.get("source_url") == URLS["bulletin"])
    expected = {
        "invalid_statistical_table", "methodology_not_collapsed",
        "missing_incremental_value_gate", "generic_why_required",
        "untraceable_statistical_evidence", "bulletin_coverage",
        "bulletin_missing_pdf", "bulletin_stock_flow_confusion",
    }
    labeled = dict(original, statistical_value_level="publication_inventory")
    assert {f["code"] for f in review_statistics([labeled])} == expected
    verified = json.loads(Path("config/statistical_analysis_verified_v1.json").read_text())["signals"][URLS["bulletin"]]
    analyzed = dict(original, **verified)
    assert review_statistics([analyzed]) == []
    analyzed.pop("summary_table")
    analyzed["statistical_value_level"] = "publication_inventory"
    assert "invalid_statistical_table" in {f["code"] for f in review_statistics([analyzed])}
