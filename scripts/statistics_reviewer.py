"""Independent fail-closed checks for public statistical releases."""
from urllib.parse import urlparse

STATISTIC_PAGES = {
    "ges": "estadistica-trimestral-de-casos-ges-auge-de-fonasa-y-sistema-isapre-a-marzo-2026/",
    "series": "series-estadisticas-del-sistema-isapre-1990-2025/",
    "financial": "estadisticas-financieras-del-sistema-isapre-a-marzo-2026/",
    "bulletin": "boletin-estadistico-informativo-ip-junio-2026/",
}
OFFICIAL_HOST = "www.superdesalud.gob.cl"


def review_statistics(signals):
    findings = []

    def fail(code, url, detail):
        findings.append({"category": "statistics", "code": code, "path": url, "detail": detail, "severity": "critical"})

    by_page = {}
    for signal in signals:
        url = str(signal.get("source_url") or "")
        for family, slug in STATISTIC_PAGES.items():
            if slug in url:
                by_page[family] = signal
                break
    if not by_page:
        return findings

    for family, signal in by_page.items():
        url = signal.get("source_url", "")
        table = signal.get("summary_table") or {}
        columns = table.get("columns") or []
        rows = table.get("rows") or []
        if urlparse(url).scheme != "https" or urlparse(url).netloc != OFFICIAL_HOST:
            fail("nonofficial_statistical_source", url, "Primary statistical page must use HTTPS on Superintendencia de Salud")
        if not rows or not columns or any(len(row.get("cells") or []) != len(columns) for row in rows):
            fail("invalid_statistical_table", url, "Every visible statistical row must map to the declared columns")
        if signal.get("methodology_visibility") != "collapsed":
            fail("methodology_not_collapsed", url, "Technical traceability must be available in a collapsed layer")
        if not isinstance(signal.get("incremental_value_gate"), dict):
            fail("missing_incremental_value_gate", url, "Visible blocks need an explicit incremental value decision")
        if signal.get("data_insights"):
            fail("duplicated_statistical_narrative", url, "Do not repeat table values in a second list of insights")
        if not signal.get("card_why_optional"):
            fail("generic_why_required", url, "Statistical cards must allow omission of generic impact copy")
        evidence = signal.get("data_insight_evidence") or []
        if not evidence or any(urlparse(item.get("source_url", "")).netloc != OFFICIAL_HOST for item in evidence):
            fail("untraceable_statistical_evidence", url, "Data evidence must link to an official source")

        if family == "ges":
            required = ["Problema de salud", "Fonasa (casos)", "Isapre (casos)", "Total (casos)", "Isapre (%)"]
            if columns != required or len(rows) < 5:
                fail("ges_columns_or_coverage", url, "GES must show problem name, Fonasa, Isapre, total and reported-case share")
            for row in rows:
                cells = row.get("cells") or []
                if len(cells) != 5 or not isinstance(cells[0], str) or cells[0].isdigit():
                    fail("opaque_ges_problem", url, "GES problem rows need validated names, not codes")
                    continue
                fonasa, isapre, total, share = cells[1:]
                if not all(isinstance(value, (int, float)) for value in (fonasa, isapre, total)) or total != fonasa + isapre:
                    fail("ges_total_mismatch", url, "GES total must equal Fonasa plus Isapre cases")
                elif total and abs(share - round(isapre / total * 100, 1)) > 0.1:
                    fail("ges_share_mismatch", url, "Isapre share denominator must be reported cases from both insurers")
            method = signal.get("statistical_methodology") or {}
            if "2026" not in str(method.get("sheet", "")):
                fail("ges_wrong_period_sheet", url, "March 2026 figures must come from the 2026 worksheet")
            if any(not str(item.get("source_url") or "").endswith("marzo-2026-1.xlsx") for item in evidence):
                fail("ges_workbook_mismatch", url, "Evidence must link to the official March 2026 GES workbook")

        elif family == "series":
            if columns != ["Variable", "Tipo", "Unidad", "2024", "2025", "Cambio absoluto", "Cambio (%)"]:
                fail("series_base_columns", url, "Annual series must expose 2024 and 2025 bases, type, unit and absolute/percentage changes")
            variables = []
            for row in rows:
                cells = row.get("cells") or []
                if len(cells) != 7:
                    continue
                name, series_type, unit, first, last, delta, percent = cells
                variables.append(name)
                if name == "Prestaciones":
                    fail("unverified_prestaciones_published", url, "Prestaciones are excluded until their semantic unit and scale are verified")
                expected_type = {"Beneficiarios promedio anual": "Promedio anual de stock", "Casos GES": "Flujo anual total del sistema (Isapres + Fonasa)"}
                if unit not in ("personas", "casos") or series_type != expected_type.get(name) or not all(isinstance(value, (int, float)) for value in (first, last, delta, percent)):
                    fail("series_unit_or_type", url, "Series variable, unit and numeric types must be explicit")
                elif not (0 < first <= 10_000_000 and 0 <= last <= 10_000_000 and delta == last - first and abs(percent - round(delta / first * 100, 1)) <= 0.1):
                    fail("series_scale_or_delta", url, "Series magnitude and changes failed sanity checks")
            if set(variables) != {"Beneficiarios promedio anual", "Casos GES"}:
                fail("series_incomplete_or_mixed_units", url, "Only semantically validated beneficiary and GES case-count series are eligible")
            expected_series = {"2-cartera-de-beneficiarios-anos-1990-2025.xlsx", "7-casos-ges-anos-2005-2025.xlsx"}
            if {str(item.get("source_url") or "").rsplit("/", 1)[-1] for item in evidence} != expected_series:
                fail("series_source_document_mismatch", url, "Each published series needs its matching official workbook")
            trace = (signal.get("statistical_methodology") or {}).get("validated_series") or []
            expected_sheets = {"Beneficiarios promedio anual": "promedio anual de cartera", "Casos GES": "casos resumen"}
            if {item.get("variable") for item in trace} != set(expected_sheets) or any(expected_sheets.get(item.get("variable"), "") not in str(item.get("sheet", "")).lower() for item in trace):
                fail("series_sheet_or_type_mismatch", url, "Variable type must be sourced from its expected official worksheet")

        elif family == "financial":
            expected = ["Isapre", "Ingresos (CLP millones)", "Resultado operacional (CLP millones)", "Utilidad/pérdida neta (CLP millones)"]
            if columns != expected or len(rows) != 10:
                fail("financial_definitions_or_rows", url, "Financial table must define the three CLP-million variables and include ten institutions")
            for row in rows:
                cells = row.get("cells") or []
                if len(cells) != 4 or not isinstance(cells[0], str) or not all(isinstance(value, (int, float)) and abs(value) < 1_000_000 for value in cells[1:]):
                    fail("financial_unit_or_magnitude", url, "Financial rows must be numeric and plausible in CLP millions")
            if url not in str((signal.get("statistical_methodology") or {}).get("source_url", "")):
                fail("financial_page_mismatch", url, "Financial source evidence must reference the matching statistical release")
            if any(not str(item.get("source_url") or "").endswith("finan_ifrs_mar_2026_web_v2.xls") for item in evidence):
                fail("financial_source_document_mismatch", url, "Financial workbook evidence must link to the March 2026 IFRS workbook")

        elif family == "bulletin":
            topics = {row.get("cells", [None])[0] for row in rows if row.get("cells")}
            if not {"Acreditación", "Mediación", "Reclamos", "RNPI"}.issubset(topics):
                fail("bulletin_coverage", url, "June 2026 audit must include accreditation, mediation, complaints and RNPI")
            if not all(any(str(item.get("source_url", "")).endswith(name) for item in evidence) for name in (
                "boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf",
                "boletin-n2-2026-mediacion-enero-junio-2026.pdf",
                "boletin-n2-2026-reclamos-enero-junio-2026.pdf",
                "boletin-n2-2026-rnpi-enero-junio-2026.pdf",
            )):
                fail("bulletin_missing_pdf", url, "All four official June 2026 bulletin PDFs must be traceable")
            kinds = {row.get("cells", [None, None, None])[2] for row in rows if len(row.get("cells") or []) >= 3}
            if not {"Stock", "Flujo acumulado", "Promedio de flujo"}.issubset(kinds):
                fail("bulletin_stock_flow_confusion", url, "Stock, cumulative flow and monthly flow must be labelled separately")
    return findings
