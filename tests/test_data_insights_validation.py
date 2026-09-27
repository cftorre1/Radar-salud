from radar_salud.data_insights import _month_key, _safe_numeric, family_from_title

def test_excel_insights_require_explicit_family_schema(monkeypatch):
    from io import BytesIO
    from openpyxl import Workbook
    from radar_salud import data_insights
    book=Workbook();sheet=book.active;sheet.title="Datos"
    sheet.append(["Isapre","2026-07","2026-08"])
    for name in ("Colmena","Consalud","Banmédica"):
        sheet.append([name,100,120])
    stream=BytesIO();book.save(stream)
    monkeypatch.setattr(data_insights,"_download",lambda url:stream.getvalue())
    result=data_insights.source_specific_insights("https://example.org/sample.xlsx","Movilidad de Isapres")
    assert result["status"]=="schema_not_validated"
    assert result["insights"]==[]

def test_invalid_month_is_not_a_comparable_period():
    assert _month_key("2026-13") is None
    assert _month_key("2026-00") is None
    assert _month_key("2026-09")== (2026,9)

def test_boolean_does_not_become_a_financial_observation():
    assert _safe_numeric(True) is None
    assert _safe_numeric("1.000") is None
    assert _safe_numeric(0)==0

def test_unknown_family_is_not_guessed():
    assert family_from_title("Resumen de información") is None


def test_ges_parser_validates_explicit_fonasa_isapre_table(monkeypatch):
    from io import BytesIO
    from openpyxl import Workbook
    from radar_salud import data_insights
    book=Workbook();sheet=book.active;sheet.title="Casos GES"
    sheet.append(["Problema de salud","Fonasa","Isapre"])
    sheet.append(["Diabetes",120,30])
    sheet.append(["Cáncer de mama",80,40])
    sheet.append(["Hipertensión",150,20])
    stream=BytesIO();book.save(stream)
    monkeypatch.setattr(data_insights,"_download",lambda url:stream.getvalue())
    result=data_insights.source_specific_insights(
        "https://example.org/ges.xlsx",
        "Estadística Trimestral de Casos GES (AUGE) de Fonasa y Sistema ISAPRE – a marzo 2026",
    )
    assert result["status"]=="validated"
    assert result["family"]=="ges"
    assert result["period"]=="2026-03"
    assert result["rows"]==3
    assert result["evidence"]["aggregation"]=="none"
    assert "Hipertensión" in result["insights"][0]

def test_ges_parser_fails_closed_without_both_system_columns(monkeypatch):
    from io import BytesIO
    from openpyxl import Workbook
    from radar_salud import data_insights
    book=Workbook();sheet=book.active
    sheet.append(["Problema de salud","Fonasa"])
    sheet.append(["Diabetes",120])
    sheet.append(["Cáncer",80])
    sheet.append(["Hipertensión",150])
    stream=BytesIO();book.save(stream)
    monkeypatch.setattr(data_insights,"_download",lambda url:stream.getvalue())
    result=data_insights.source_specific_insights(
        "https://example.org/ges.xlsx",
        "Estadística Trimestral de Casos GES (AUGE) de Fonasa y Sistema ISAPRE – a marzo 2026",
    )
    assert result["status"]=="schema_not_validated"
    assert result["insights"]==[]

def test_ges_title_is_registered_as_statistical_family():
    assert family_from_title("Estadística Trimestral de Casos GES (AUGE) de Fonasa y Sistema ISAPRE – a marzo 2026")=="ges"
