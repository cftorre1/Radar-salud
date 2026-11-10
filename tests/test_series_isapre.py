"""Series largas SIS 1990-2025 (Datos): determinism, reconciliation, receipts and fail-closed behaviour."""
import hashlib
import importlib.util
import json
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data/reference/sis_series_1990_2025"
BOOK = REF / "2-cartera-de-beneficiarios-anos-1990-2025.xlsx"
OUT = ROOT / "web/data/series_isapre.json"


def load():
    spec = importlib.util.spec_from_file_location("series", ROOT / "scripts/build_series_isapre_1990_2025.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return load()


@pytest.fixture(scope="module")
def built(mod):
    return mod.build(BOOK, json.loads((REF / "receipts.json").read_text(encoding="utf-8")))


def test_published_json_is_exactly_the_builder_output(built):
    assert json.loads(OUT.read_text(encoding="utf-8")) == built


def test_every_file_has_a_receipt_with_matching_sha256_and_robots_ok():
    rec = json.loads((REF / "receipts.json").read_text(encoding="utf-8"))
    assert rec["pagina"]["status"] == 200 and rec["pagina"]["robots"] == "robots_ok"
    assert rec["pagina"]["url"].startswith("https://www.superdesalud.gob.cl/biblioteca-digital/series-estadisticas")
    assert len(rec["archivos"]) >= 8
    for a in rec["archivos"]:
        assert a["robots"] == "robots_ok" and a["status"] == 200 and "error" not in a
        assert a["url"].startswith("https://www.superdesalud.gob.cl/app/uploads/")
        assert hashlib.sha256((REF / a["archivo"]).read_bytes()).hexdigest() == a["sha256"]


def test_reconciliations_pass_and_identities_hold(built):
    v = built["verificacion"]
    assert v["status"] == "PASS" and all(x <= v["tolerancia_personas"] for x in v["diferencia_maxima"].values())
    assert v["diferencias_de_la_fuente"] == [{"control": "2.6.3.total_vs_2.1", "anio": 2002, "personas": 2251}]
    s = built["sistema"]
    for i, _ in enumerate(built["years"]):
        assert s["beneficiarios"]["total"][i] == s["cotizantes"]["total"][i] + s["cargas"]["total"][i]
        assert s["beneficiarios"]["total"][i] == s["beneficiarios"]["abiertas"][i] + s["beneficiarios"]["cerradas"][i]


def test_known_values_and_highlights(built):
    y = built["years"]
    assert y[0] == 1990 and y[-1] == 2025 and len(y) == 36
    ben = built["sistema"]["beneficiarios"]["total"]
    assert ben[0] == 2108308 and ben[-1] == 2517305 and max(ben) == ben[y.index(1997)]
    h = {k["id"]: k for k in built["highlights"]}
    assert h["beneficiarios"]["value"] == "2.517.305"
    assert h["beneficiarios"]["lines"][0] == "−112.721 vs. dic 2024 (−4,3%)"
    assert h["isapres"]["value"] == "10" and h["isapres"]["lines"][0] == "7 abiertas · 3 cerradas"
    vig = sorted(b["short"] for b in built["isapres"]["beneficiarios"] if b["short"])
    assert vig == sorted(["Banmédica", "Colmena", "Consalud", "Cruz Blanca", "Cruz del Norte", "Esencial", "Fundación",
                          "Isalud", "Nueva Masvida", "Vida Tres"])
    assert built["mercado"]["isapres_total"] == [a + c for a, c in zip(built["mercado"]["isapres_abiertas"],
                                                                         built["mercado"]["isapres_cerradas"])]


def test_a_tampered_cell_fails_closed(mod, tmp_path):
    wb = openpyxl.load_workbook(BOOK)
    ws = wb["Cartera Anual de Isapre"]
    for row in ws.iter_rows():
        if str(row[0].value).strip() == "Abiertas":
            row[5].value = (row[5].value or 0) + 500  # cotizantes abiertas 1993: total no longer reconciles
            break
    bad = tmp_path / "bad.xlsx"
    wb.save(bad)
    with pytest.raises(SystemExit, match="conciliacion_fallida"):
        mod.build(bad, {"archivos": []})


def test_a_wrong_year_header_fails_closed(mod):
    header = ["Isapres"] + list(range(1990, 2026))
    assert mod.year_columns(header)[2025] == 36
    header[15] = 2204  # the documented 2.11.1 erratum sits in the 2004 column (index 15) and is accepted
    assert mod.year_columns(header)[2004] == 15
    header[16] = 2004
    with pytest.raises(SystemExit, match="encabezado_inesperado"):
        mod.year_columns(header)
