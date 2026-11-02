"""F2 · FEFI (financial statements of the Isapres): template, capture, Esencial exclusion rule and the ficha.

No network and no model calls. The workbook is rebuilt here with openpyxl in the real layout printed by CI on PR #117
(finan_ifrs_mar_2026_web_v2.xls, sha256 e3c4f7b3…): the 'Ctas. de Resultados I. Abierta ' (trailing space) and
'… I. Cerradas' sheets, rows r1–r16 with the real values (miles de $), the real A18 note, and an 'en millones de $'
sheet with mixed scales that must never be read. Rows the annotations did not show (r17+) are fixture values.
Every figure asserted below is recomputed here from these inputs.
"""
import copy
import hashlib
import json
import re
import shutil
import sys
import types
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest

from radar_salud import figure_templates as ft
from radar_salud import stats_capture_fefi as fc
from radar_salud import stats_ficha_f2 as f2
from radar_salud import stats_fichas as sf

REPO = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 1)
URL = "https://www.superdesalud.gob.cl/app/uploads/fixture/finan_ifrs_mar_2026_fixture.xls"
URL_PREV = "https://www.superdesalud.gob.cl/app/uploads/fixture/finan_ifrs_mar_2025_fixture.xls"
A18 = "La Isapre Esencial no presenta información a marzo 2026, dado que sus cifras se encuentran en proceso de revisión."
OPEN = ("67", "78", "80", "81", "99", "107", "108")
OPEN_NAMES = ("Colmena Golden Cross", "Cruz Blanca", "Vida Tres", "Nueva Masvida", "Banmédica", "Consalud", "Esencial")
CLOSED = ("63", "76", "94")
CLOSED_NAMES = ("Isalud", "Fundación", "Cruz del Norte")
ING = "Ingresos de actividades ordinarias"
GAV = "Gastos de administración y otros gastos por función"
# Ctas. rows: (section in column A, account in column B, key). Totals ('ingresos', 'costo', 'gav') are computed from their
# parts unless ``fixed`` overrides them, so a test that edits one component keeps or breaks the identity on purpose.
CTAS_ROWS = [(ING, "Cotización legal (7%)", "legal"), (None, "Cotización adicional voluntaria", "adicional"),
             (None, "Aporte adicional", "aporte"), (None, "Ingresos por fondo de compensación", "fondo"), (None, "Otros", "otros"),
             ("Total ingresos de actividades ordinarias", None, "ingresos"),
             ("Costo de ventas", "Costos por prestaciones de salud", "prest"), (None, "Subsidios por incapacidad laboral", "sil"),
             (None, "Prestaciones ocurridas y no liquidadas", "ocurridas"), (None, "Prestaciones en litigio", "litigio"),
             (None, "Egresos por fondo de compensación", "egresos"), (None, "Otros costos de operación", "otroscostos"),
             ("Total costo de ventas", None, "costo"),
             (GAV, "Publicidad", "publicidad"), (None, "Deterioro por deudores de cotizaciones", "detcot"),
             (None, "Deterioro por deudores de préstamos de salud", "detpres"), (None, "Remuneraciones del personal", "remun"),
             (None, "Remuneraciones y comisiones del personal de ventas", "remventas"), (None, "Otros", "gotros"),
             ("Total gastos de administración y otros gastos por función", None, "gav")]
PARTS = {"ingresos": ("legal", "adicional", "aporte", "fondo", "otros"),
         "costo": ("prest", "sil", "ocurridas", "litigio", "egresos", "otroscostos"),
         "gav": ("publicidad", "detcot", "detpres", "remun", "remventas", "gotros")}
# E. Resultados rows: (code, label, key); 'bruta' = ingresos − costo unless fixed. Real codes and labels (CI annotation on
# b3019747); 30190 'continuadas' repeats the result and must not be read (the template anchors 23070).
ERES_ROWS = [(30010, "Ingresos de actividades ordinarias", "ingresos"), (30020, "Costo de ventas (menos)", "costo"),
             (30030, "Ganancia bruta", "bruta"), (30060, "Otros ingresos, por función", "otrosing"),
             (30080, "Gasto de administración (menos)", "gav"), (30090, "Otros gastos, por función (menos)", "otrosgastos"),
             (30170, "Ganancia (pérdida), antes de impuestos", "antes"), (30180, "Gasto por impuestos a las ganancias (menos)", "imp"),
             (30190, "Ganancia (pérdida) procedente de operaciones continuadas", "gan"), (23070, "Ganancia (pérdida)", "gan")]
# Values per Isapre in miles de $, order OPEN + CLOSED. Real (CI annotations on PR #117) unless marked.
REAL = {
    "legal": [186844880, 118341178, 37846717, 89708775, 152605566, 132430126, 15743566, 12905476, 8874426, 284163],
    "adicional": [80469918, 53035972, 29474781, 25808000, 76927265, 59959413, 13319092, 2031083, 727920, 42757],
    "aporte": [32020, 107104, 0, 0, 368801, 649348, 0, 17512276, 2573264, 472000],
    "fondo": [0, 0, 604038, 0, 477479, 234583, 0, 0, 0, 0],
    "otros": [0] * 10,
    "prest": [183534521, 121258868, 56275124, 69201925, 169301377, 120357578, 21377883, 30477935, 7930026, 507976],
    "sil": [33779167, 21306464, 5693076, 18235811, 30972360, 32399738, 2248012, 2109658, 1618265, 186351],
    "ocurridas": [22959294, 27987, 395204, 955716, 4885409, 252621, -383536, 0, 201286, -61172],
    "litigio": [-754415, -337914, 38744, 260992, 79162, 2046748, 0, 0, -2507, 0],
    "egresos": [0, 67239, 0, 466890, 0, 0, 336182, 0, 0, 0],
    "otroscostos": [9779243, 7180610, 2674379, 5992747, 5568520, 143836, 28754, 282953, 562162, 0],
    "publicidad": [514183, 239470, 101496, 52007, 306541, 176989, 298473, 0, 8511, 0],
    "detcot": [162946, 82603, 135737, 0, 584858, 424231, 0, 0, 1825, 0],
    "detpres": [442431, 1246, 202924, 0, 363378, 19811, 0, 0, 148086, 5298],
    "remun": [7487225, 4825805, 1695779, 2819201, 5821111, 6971415, 1967621, 1805662, 915205, 62974],
    "remventas": [5656940, 2623064, 881925, 11245376, 5626456, 5007995, 776356, 209051, 0, 0],
    "gotros": [6254837, 6944809, 1516386, 6152909, 5177658, 3265667, 2363241, 1037310, 539128, 63553],
    "otrosing": [2374226, 115859, 252440, 1414756, 2396218, 1657291, 51613, 5603788, 523243, 33],
    "otrosgastos": [2363903, 606234, 45116, 15686, -130, 150907, 0, 199866, 82629, 0],
    "antes": [1976441, 9291788, -708959, 2273475, 5421031, 24711719, -62835, 2005553, 952296, 52888],
    "imp": [492529, 2509427, -83597, 569676, 1502878, 6671227, -33130, -21713, 193194, 22253],
    "gan": [1483912, 6782361, -625362, 1703799, 3918153, 18040492, -29705, 2027266, 759102, 30635],
}
CODES = OPEN + CLOSED
ESENCIAL = CODES.index("108")


def full(data=None, fixed=None) -> dict:
    """The fixture values with totals computed from their parts (``fixed`` overrides any key)."""
    d = copy.deepcopy(data or REAL)
    for total, parts in PARTS.items():
        d[total] = [sum(d[p][i] for p in parts) for i in range(10)]
    d["bruta"] = [d["ingresos"][i] - d["costo"][i] for i in range(10)]
    d.update(copy.deepcopy(fixed or {}))
    return d


def sin_esencial(key, data=None):
    vals = full(data)[key]
    return sum(x for i, x in enumerate(vals) if i != ESENCIAL) / 1000  # MM$


def workbook(data=None, *, fixed=None, note=A18, extra_col=False, total_delta=0, total_in_b=False, year="2026",
             delta_key=None) -> bytes:
    """``total_delta`` shifts the prestaciones total column; ``delta_key`` shifts that account's total column by 7 (the
    Isapres no longer add up); ``fixed`` overrides values (e.g. a total that no longer equals its parts)."""
    from openpyxl import Workbook
    d = full(data, fixed)
    wb = Workbook()
    ws = wb.active
    ws.title = "Indice"
    ws["A8"] = f"Indice información financiera a marzo {year}"
    ws = wb.create_sheet("Notas Explicativas")
    ws["A12"] = "Nota general (fixture)."
    ws["A18"] = note
    ws = wb.create_sheet("E. Resultados comparado por Isa")
    for row in ([], ["Cuadro N° 1.1 b"], ["Principales rubros del estado de resultados por función por Isapre al 31 de marzo"],
                ["En millones de $"], ["Cod.", "Isapres", "Ingresos de actividades ordinarias", "Costo de ventas (menos)"],
                [67, "Colmena Golden Cross", 267346818, 249297.81]):  # mixed scales (display format), never read
        ws.append(row)
    for kind, codes, names in (("abiertas", OPEN, OPEN_NAMES), ("cerradas", CLOSED, CLOSED_NAMES)):
        idx = [CODES.index(c) for c in codes]
        extra = [0] if extra_col and codes == OPEN else []
        for sheet, rows, cuadro in ((f"Ctas. de Resultados I. {'Abierta ' if kind == 'abiertas' else 'Cerradas'}", CTAS_ROWS,
                                     8 if kind == "abiertas" else 9),
                                    (f"E. Resultados I. {kind.capitalize()}", ERES_ROWS, 6 if kind == "abiertas" else 7)):
            ws = wb.create_sheet(sheet)
            ws.append([])
            ws.append([f"Cuadro N° 1.{cuadro}"])
            ws.append([f"Cuentas de resultados de las Isapres {kind}"])
            if kind == "cerradas":
                ws.append([f"Al 31 de marzo de {year}"])
            ws.append(["En miles de $"])
            first = ["Cuentas", None] if rows is CTAS_ROWS else ["Cod", "Cuentas"]
            ws.append([*first, *names, *(["Isapre Nueva"] if extra else []), "Total"])
            ws.append([])
            for a, b, key in rows:
                vals = [d[key][i] for i in idx]
                tot = sum(vals) + (total_delta if key == "prest" else 0) + (7 if key == delta_key and rows is CTAS_ROWS else 0)
                if total_in_b and key == "ingresos" and rows is CTAS_ROWS:
                    a, b = None, "Total ingresos de actividades ordinarias"
                ws.append([a, b, *vals, *extra, tot])
            ws.append(["Fuente: Superintendencia de Salud, ficha económica financiera de Isapres al 31/03/2026"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def committed_template():
    return copy.deepcopy(sf.load_registry()["families"]["F2"]["parser_template"])


def reviewed_template():
    """The committed template, reviewed by Dirección on 2-nov-2026: every fixture is read through it as it is."""
    tpl = committed_template()
    assert ft.review_state(tpl) == "ok"
    return tpl


def pending_template():
    """A copy in the pre-approval state (reviewed_by 'pendiente', no date): the HOLD it must cause stays covered."""
    return {**committed_template(), "reviewed_by": "pendiente", "reviewed_at": None}


def placeholder_template():
    """A copy with one row back to a ``<<…>>`` placeholder (review fields kept): still HOLD."""
    tpl = committed_template()
    acc = next(iter(tpl["tables"]["ctas_abiertas"]["accounts"].values()))
    acc["pattern"] = "<<fila por confirmar>>"
    return tpl


def registry(template=None):
    reg = copy.deepcopy(sf.load_registry())
    reg["families"]["F2"]["parser_template"] = reviewed_template() if template is None else template
    return reg


def rules(mode="rule"):
    """'rule': the committed Dirección rule (hold superseded); 'hold': hold without resolution; 'none': neither."""
    real = json.loads((REPO / "config/editorial_rules_v3.json").read_text(encoding="utf-8"))
    if mode == "rule":
        return real
    out = {k: v for k, v in real.items() if k not in ("rules", "hold_resolutions")}
    if mode == "none":
        out["holds"] = {k: v for k, v in real["holds"].items() if not k.startswith("fefi")}
    return out


def make_root(tmp_path, *, mode="rule", template=None, prev=False) -> Path:
    root = tmp_path / "root"
    for d in ("config", "data/entities", "data/history"):
        (root / d).mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "data/entities/isapres.json", root / "data/entities/isapres.json")
    (root / "config/editorial_rules_v3.json").write_text(json.dumps(rules(mode), ensure_ascii=False), encoding="utf-8")
    (root / "config/stats_fichas_v1.json").write_text(json.dumps(registry(template), ensure_ascii=False), encoding="utf-8")

    def sig(period, day, url):
        return {"title": f"Estadísticas Financieras del Sistema ISAPRE a {period}", "source_name": "Superintendencia de Salud",
                "event_date": day, "source_url": "https://www.superdesalud.gob.cl/biblioteca-digital/fixture-fefi/",
                "source_documents": [{"url": url}]}
    signals = [sig("marzo 2026", "2026-07-07", URL)]
    if prev:
        signals += [sig("marzo 2025", "2025-06-16", URL_PREV),
                    sig("diciembre 2025", "2026-04-22", "https://www.superdesalud.gob.cl/app/uploads/fixture/dic25.xls")]
    (root / "data/history/superintendencia_signals.json").write_text(json.dumps({"signals": signals}), encoding="utf-8")
    return root


def fetcher(files: dict[str, bytes]):
    calls = []

    def fetch(url):
        calls.append(url)
        if url not in files:
            raise PermissionError("fixture: not served")
        return files[url]
    fetch.calls = calls
    return fetch


def capture(root, data=None, template=None, files=None, max_new=2):
    tpl = registry(template)["families"]["F2"]["parser_template"] if template is None else template
    fetch = fetcher(files or {URL: data or workbook()})
    fc.capture_fefi(root, fetch=fetch, template=tpl, max_new=max_new)
    return fetch


def stored_doc(root, period="2026-03"):
    rels = json.loads((root / fc.STORE).read_text(encoding="utf-8"))["releases"]
    return next(r for r in rels if r["period"] == period)["document"]


def run(root, template=None):
    return f2.run(root, today=TODAY, registry=registry(template), llm=False)


def published(tmp_path, **kw):
    root = make_root(tmp_path, **kw)
    capture(root)
    res = run(root)
    assert res["status"] == "pass", res.get("errors")
    return root, res["ficha"]


@pytest.fixture(autouse=True)
def isolated_ledgers(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_ROOT", str(tmp_path / "ledger-root"))


# ---------------------------------------------------------------------------------------------
# Committed state


def test_committed_template_is_reviewed_f2_is_active_and_reads_only_the_miles_sheets():
    cfg = sf.load_registry()["families"]["F2"]
    tpl = cfg["parser_template"]
    # Dirección approved the template and activated F2 on 2-nov-2026; the Lectura (paid) stays off.
    assert cfg["status"] == "active" and "blocked_by" not in cfg and cfg["lectura_enabled"] is False
    assert cfg["activated_by"].startswith("Dirección") and date.fromisoformat(cfg["activated_at"])
    assert tpl["reviewed_by"].startswith("Dirección") and date.fromisoformat(tpl["reviewed_at"]) <= date.fromisoformat(cfg["activated_at"])
    assert ft.review_state(tpl) == "ok" and not ft.has_placeholder({k: v for k, v in tpl.items() if k != "_doc"})
    assert "A18" in tpl["review_note"] and "Esencial" in tpl["review_note"]
    assert cfg["templates"]["kicker"].format(label=cfg["label"], period_label="marzo 2026") == "Estados financieros Isapres · marzo 2026"
    assert {t["sheet"] for t in tpl["tables"].values()} == {
        r"^ctas\. de resultados i\. abierta$", r"^ctas\. de resultados i\. cerradas$",
        r"^e\. resultados i\. abiertas$", r"^e\. resultados i\. cerradas$"}  # never a sheet 'en millones', never E. Sit. Fin.
    assert all(t["unit"]["pattern"] == r"^en miles de \$$" and t["unit"]["to_mm_clp"] == 0.001 for t in tpl["tables"].values())
    assert {i for t in ("eres_abiertas", "eres_cerradas") for i in (a["item"] for a in tpl["tables"][t]["accounts"].values())} == {
        "ganancia_bruta", "resultado_antes_impuestos", "gasto_impuestos", "resultado_ejercicio"}
    assert set(tpl["tables"]["ctas_abiertas"]["parts"]) == {"ingresos_operacionales", "costo_operacional", "gav"}
    assert [c["name"] for c in tpl["cross_checks"]] == ["ganancia_bruta", "impuestos"]
    assert not any("patrimonio" == a["item"] for t in tpl["tables"].values() for a in t["accounts"].values())
    assert all(s["item"] in fc.ITEMS for t in tpl["tables"].values() for s in t["accounts"].values())


def test_committed_rules_record_the_decision_and_keep_the_old_hold():
    real = json.loads((REPO / "config/editorial_rules_v3.json").read_text(encoding="utf-8"))
    assert real["holds"]["fefi_2026_03"].startswith("HOLD_COVERAGE_ESENCIAL: Notas Explicativas A18")  # history kept verbatim
    res = real["hold_resolutions"]["fefi_2026_03"]
    assert res["original_hold"] == real["holds"]["fefi_2026_03"] and res["by_rule"] == "fefi_esencial_exclusion"
    rule = real["rules"]["fefi_esencial_exclusion"]
    assert rule["decided_at"] == "2026-11-01" and rule["entity_code"] == 108 and rule["condition"]["locator"] == "Notas Explicativas!A18"
    assert rule["condition"]["quote_2026_03"] == A18
    assert f2.esencial_hold(REPO) is None and f2.exclusion_rule(REPO)[0] == "fefi_esencial_exclusion"


def test_committed_template_verifies_and_publishes_the_f2_ficha(tmp_path):
    root = make_root(tmp_path, template=committed_template(), prev=True)
    capture(root, template=committed_template(), files={URL: workbook(), URL_PREV: workbook(prev_data(), year="2025")})
    assert stored_doc(root)["parse"]["status"] == "verified" and stored_doc(root, "2025-03")["parse"]["status"] == "verified"
    res = run(root, template=committed_template())
    assert res["status"] == "pass", res.get("errors")
    fi = res["ficha"]
    assert fi["kicker"] == "Estados financieros Isapres · marzo 2026" and fi["period"] == "2026-03"
    assert "marzo 2025" in fi["headline"] and {s["key"] for s in fi["sources"]} == {"fefi", "fefi_prev"}
    assert all(k["label"].endswith("(sistema sin Esencial)") for k in fi["kpis"])
    assert any(n["id"] == "n0" and "Notas Explicativas!A18" in n["text"] for n in fi["notes"])
    assert not any(".108." in vid for vid in fi["evidence"]["values"])
    assert fi["lectura"]["status"] == "not_attempted"


@pytest.mark.parametrize("make,state", [(pending_template, "unreviewed"), (placeholder_template, "placeholder")])
def test_pending_or_placeholder_copies_of_the_template_parse_nothing_and_hold(tmp_path, make, state):
    tpl = make()
    root = make_root(tmp_path, template=tpl)
    capture(root, template=tpl)
    assert stored_doc(root)["parse"]["status"] == f"template_{state}" and not stored_doc(root)["parse"].get("tables")
    res = run(root, template=tpl)
    assert res["status"] == "hold" and any(f"parser_template_{state}" in e for e in res["errors"])


@pytest.mark.parametrize("patch,state", [({"reviewed_by": "pendiente"}, "unreviewed"), ({"reviewed_by": ""}, "unreviewed"),
                                         ({"reviewed_at": None}, "unreviewed")])
def test_unreviewed_template_holds(tmp_path, patch, state):
    tpl = {**reviewed_template(), **patch}
    root = make_root(tmp_path, template=tpl)
    capture(root, template=tpl)
    assert stored_doc(root)["parse"]["status"] == f"template_{state}"
    res = run(root, template=tpl)
    assert res["status"] == "hold" and any(f"parser_template_{state}" in e for e in res["errors"])


# ---------------------------------------------------------------------------------------------
# Parser on the real layout


def test_reviewed_template_reads_the_real_ctas_layout():
    p = fc.parse_fefi_workbook(workbook(), reviewed_template(), "2026-03")
    assert p["status"] == "verified", p.get("failures")
    ab = p["tables"]["ctas_abiertas"]
    assert ab["sheet"] == "Ctas. de Resultados I. Abierta " and ab["header_row"] == 5  # the trailing space is the SIS name
    assert ab["entity_columns"]["67"] == "C" and ab["entity_columns"]["total"] == "J"
    assert ab["cells"]["cotizacion_legal.t"]["67"] == "C7" and ab["cells"]["ingresos_operacionales.t"]["108"] == "I12"
    assert ab["values"]["ingresos_operacionales.t"]["67"] == pytest.approx(267346.818)  # miles → millones
    assert ab["values"]["costo_prestaciones.t"]["total"] == pytest.approx(741307.276)
    ce = p["tables"]["ctas_cerradas"]
    assert ce["header_row"] == 6 and ce["cells"]["costo_sil.t"]["94"] == "E15"
    assert p["coverage_note"] == {"sheet": "Notas Explicativas", "cell": "A18", "text": A18,
                                  "text_sha256": hashlib.sha256(A18.encode()).hexdigest()}
    er = p["tables"]["eres_abiertas"]
    assert er["sheet"] == "E. Resultados I. Abiertas" and er["cells"]["ganancia_bruta.t"]["67"] == "C9"
    assert er["values"]["ganancia_bruta.t"]["67"] == pytest.approx(18049.008)  # 267346818 − 249297810 miles
    assert ab["values"]["costo_operacional.t"]["67"] == pytest.approx(249297.81) and ab["values"]["gav.t"]["total"] == pytest.approx(99191.1)
    assert p["tables"]["eres_cerradas"]["values"]["resultado_ejercicio.t"]["63"] == pytest.approx(2027.266)
    assert "E. Resultados comparado por Isa" in p["sheet_names"]
    assert "E. Resultados comparado por Isa" not in {t["sheet"] for t in p["tables"].values()}


def test_total_label_in_column_b_is_still_one_anchored_row():
    assert fc.parse_fefi_workbook(workbook(total_in_b=True), reviewed_template(), "2026-03")["status"] == "verified"


def test_millones_sheets_are_refused_whatever_the_template_says():
    tpl = reviewed_template()
    tpl["tables"]["ctas_abiertas"]["sheet"] = r"^e\. resultados comparado por isa$"
    p = fc.parse_fefi_workbook(workbook(), tpl, "2026-03")
    assert "ctas_abiertas:unit_millones_refused" in p["failures"] and p["tables"] == {}


def test_sum_guard_is_at_most_one_miles_even_if_the_template_allows_more():
    tpl = reviewed_template()
    tpl["tables"]["ctas_abiertas"]["sum_tolerance"] = 50
    assert fc.parse_fefi_workbook(workbook(total_delta=1), tpl, "2026-03")["status"] == "verified"
    p = fc.parse_fefi_workbook(workbook(total_delta=2), tpl, "2026-03")
    assert "ctas_abiertas:sum_mismatch:costo_prestaciones.t" in p["failures"]


def test_mixed_magnitudes_are_refused():
    data = copy.deepcopy(REAL)
    data["prest"][0] = 183534.521  # Colmena's prestaciones written in millions next to ingresos in miles (×1.000)
    p = fc.parse_fefi_workbook(workbook(data), reviewed_template(), "2026-03")
    assert any(f.startswith("ctas_abiertas:mixed_magnitudes:67:") for f in p["failures"]), p["failures"]


def test_components_must_add_up_to_total_ingresos():
    data = copy.deepcopy(REAL)
    data["aporte"][1] += 5000  # the component changes, Total ingresos does not
    p = fc.parse_fefi_workbook(workbook(data, fixed={"ingresos": full()["ingresos"]}), reviewed_template(), "2026-03")
    assert "ctas_abiertas:parts_do_not_add_up:ingresos_operacionales.t:78" in p["failures"]
    data = copy.deepcopy(REAL)
    data["remun"][8] += 10  # an admin component of Fundación (cerradas), total kept
    p = fc.parse_fefi_workbook(workbook(data, fixed={"gav": full()["gav"]}), reviewed_template(), "2026-03")
    assert "ctas_cerradas:parts_do_not_add_up:gav.t:76" in p["failures"]
    data = copy.deepcopy(REAL)
    data["otroscostos"][0] += 2
    p = fc.parse_fefi_workbook(workbook(data, fixed={"costo": full()["costo"]}), reviewed_template(), "2026-03")
    assert "ctas_abiertas:parts_do_not_add_up:costo_operacional.t:67" in p["failures"]


def test_ganancia_bruta_and_taxes_cross_check_across_sheets():
    bruta = full()["bruta"]
    bruta[0] += 2  # E. Resultados ganancia bruta of Colmena no longer equals Ctas. ingresos − costo de ventas
    p = fc.parse_fefi_workbook(workbook(fixed={"bruta": bruta}), reviewed_template(), "2026-03")
    assert p["failures"] == ["cross_check_failed:ganancia_bruta:67"]
    gan = list(REAL["gan"])
    gan[7] += 5  # Isalud: antes de impuestos − impuestos ≠ ganancia
    p = fc.parse_fefi_workbook(workbook(fixed={"gan": gan}), reviewed_template(), "2026-03")
    assert p["failures"] == ["cross_check_failed:impuestos:63"]


def test_e_resultados_millones_or_mixed_magnitudes_are_refused():
    gan = list(REAL["gan"])
    gan[1] = 6782.361  # Cruz Blanca's result in millions next to miles (and its antes de impuestos in miles)
    antes, imp = list(REAL["antes"]), list(REAL["imp"])
    imp[1] = antes[1] - gan[1]
    p = fc.parse_fefi_workbook(workbook(fixed={"gan": gan, "imp": imp}), reviewed_template(), "2026-03")
    assert any(f.startswith("eres_abiertas:mixed_magnitudes:78:") for f in p["failures"]), p["failures"]


@pytest.mark.parametrize("kwargs,why", [({"extra_col": True}, "ctas_abiertas:header_no_match"),
                                        ({"delta_key": "sil"}, "ctas_abiertas:sum_mismatch:costo_sil.t")])
def test_parser_fails_closed(kwargs, why):
    p = fc.parse_fefi_workbook(workbook(**kwargs), reviewed_template(), "2026-03")
    assert p["status"] == "failed" and why in p["failures"], p["failures"]


def test_an_isapre_column_the_template_does_not_list_is_never_dropped():
    tpl = reviewed_template()
    tpl["tables"]["ctas_abiertas"]["header_row"] = r"^cuentas \| colmena golden cross \|"  # looser header: next guard holds
    p = fc.parse_fefi_workbook(workbook(extra_col=True), tpl, "2026-03")
    assert "ctas_abiertas:unlisted_column:J" in p["failures"], p["failures"]


def test_legacy_xls_needs_xlrd_and_reads_through_it(monkeypatch):
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 64
    monkeypatch.setitem(sys.modules, "xlrd", None)
    assert fc.parse_fefi_workbook(ole, reviewed_template(), "2026-03")["status"] == "xls_reader_unavailable"
    from openpyxl import load_workbook
    real = load_workbook(BytesIO(workbook()), data_only=True)

    class Sheet:
        def __init__(self, ws):
            self.name, self._rows = ws.title, [list(r) for r in ws.iter_rows(values_only=True)]
            self.nrows = len(self._rows)

        def row_values(self, i):
            return ["" if v is None else v for v in self._rows[i]]

    class Book:
        def __init__(self):
            self._s = [Sheet(ws) for ws in real.worksheets]
            self.nsheets = len(self._s)

        def sheet_by_index(self, i):
            return self._s[i]
    monkeypatch.setitem(sys.modules, "xlrd", types.SimpleNamespace(open_workbook=lambda file_contents, on_demand: Book()))
    p = fc.parse_fefi_workbook(ole, reviewed_template(), "2026-03")
    assert p["format"] == "xls" and p["status"] == "verified", p.get("failures")


# ---------------------------------------------------------------------------------------------
# Esencial: exclusion rule conditional on A18


def test_ficha_shows_nine_isapres_and_recomputes_the_system_without_esencial(tmp_path):
    _, fi = published(tmp_path)
    ev = fi["evidence"]["values"]
    assert not any(".108." in vid or vid.endswith(".108") for vid in ev)  # no Esencial figure in the package
    assert fi["evidence"]["entity_codes"] == sorted(int(c) for c in CODES if c != "108")
    assert ev["ingresos_operacionales.sistema.2026-03"]["value"] == pytest.approx(sin_esencial("ingresos"))
    assert ev["ingresos_operacionales.sistema.2026-03"]["kind"] == "derived"  # recomputed, never the SIS total column
    s = (sin_esencial("prest") + sin_esencial("sil")) / sin_esencial("ingresos") * 100
    assert ev["siniestralidad.sistema.2026-03"]["value"] == pytest.approx(s)
    k = {x["id"]: x for x in fi["kpis"]}
    assert k["ingresos"]["label"] == "Ingresos (sistema sin Esencial)" and k["ingresos"]["value"] == "1.091.349 MM$"
    assert k["siniestralidad"]["value"] == "82,9%"
    gan = sin_esencial("gan")
    assert fi["headline"] == f"Isapres sin Esencial a marzo 2026: utilidad de {sf.fmt_int(gan)} MM$ entre enero y marzo"
    bridge = next(c for c in sf.all_charts(fi) if c["id"] == "f2-resultado-puente")
    assert [r["label"] for r in bridge["rows"]] == ["Ganancia bruta", "Antes de impuestos", "Impuestos", "Ganancia"]
    assert bridge["rows"][2]["value"] == pytest.approx(-sin_esencial("imp")) and bridge["rows"][3]["value"] == pytest.approx(gan)
    assert ev["gav_pct.sistema.2026-03"]["value"] == pytest.approx(sin_esencial("gav") / sin_esencial("ingresos") * 100)
    costs = next(c for c in sf.all_charts(fi) if c["id"] == "f2-costos-composicion")
    assert costs["table"]["rows"][-1] == ["Total costo de ventas", sf.fmt_int(sin_esencial("costo"))]
    n0 = next(n for n in fi["notes"] if n["id"] == "n0")["text"]
    assert f'Notas Explicativas!A18: "{A18}"' in n0 and "1 nov 2026" in n0 and "otras 9 Isapres" in n0
    shown = " ".join(sf.displayed_texts(fi))
    esencial = full()
    for key in esencial:  # no Esencial figure in charts, tables, 'Ver datos'
        x = esencial[key][ESENCIAL] / 1000
        if abs(x) >= 100:
            tok = re.compile(r"(?<![\d.,])" + re.escape(sf.fmt_int(abs(x))) + r"(?![\d]|[.,]\d)")
            assert not tok.search(shown), (key, sf.fmt_int(x))
    for c in sf.all_charts(fi):
        assert "Esencial" not in [r["label"] for r in c["rows"]] and all(r["label"] != "Sistema" for r in c["rows"])
        assert all("Esencial" not in str(row[0]) or row[0] == "Sistema sin Esencial" for row in c["table"]["rows"])
    assert [t["id"] for t in fi["tabs"]] == ["resultados", "ingresos", "costos", "gastos", "siniestralidad"]  # no patrimonio
    assert fi["verification"]["verdict"] == "PASS" and fi["lectura"]["status"] == "not_attempted"


def test_without_the_previous_year_the_ficha_shows_levels_only(tmp_path):
    _, fi = published(tmp_path)
    ev = fi["evidence"]["values"]
    assert not any(vid.endswith((".pct", ".delta", ".pp", ".2025-03")) for vid in ev)
    assert next(k for k in fi["kpis"] if k["id"] == "ingresos")["lines"] == ["enero–marzo 2026; sin comparación a/a"]
    assert any(n["id"] == "n5" and "marzo 2025" in n["text"] for n in fi["notes"])


def test_dek_adds_composition_and_spread(tmp_path):
    _, fi = published(tmp_path)
    share = sin_esencial("legal") / sin_esencial("ingresos") * 100
    assert fi["dek"].startswith(f"La cotización legal aporta el {sf.fmt_dec(share, 1)}% de los ingresos.")
    assert "Por Isapre, la siniestralidad va de" in fi["dek"] and "Esencial" not in fi["dek"]


@pytest.mark.parametrize("note", [
    "Las cifras de todas las Isapres corresponden a sus estados financieros.",
    A18 + " A partir de junio se publicarán.",
])
def test_exclusion_does_not_persist_silently_when_a18_changes(tmp_path, note):
    root = make_root(tmp_path)
    capture(root, workbook(note=note))
    res = run(root)
    assert res["status"] == "hold" and any("esencial_exclusion_condition_not_met:Notas Explicativas!A18" in e
                                           for e in res["errors"]), res["errors"]


def test_exclusion_condition_follows_the_period_and_the_locator():
    rule = f2.exclusion_rule(REPO)[1]
    june = {"sheet": "Notas Explicativas", "cell": "A18",
            "text": "La Isapre Esencial no presenta información a junio 2026, dado que sus cifras se encuentran en proceso de revisión."}
    assert f2.exclusion_applies(rule, june, "2026-06")
    assert not f2.exclusion_applies(rule, june, "2026-03")  # the note must speak of the ficha's own period
    assert not f2.exclusion_applies(rule, {**june, "cell": "A19"}, "2026-06")
    assert not f2.exclusion_applies(rule, None, "2026-06")


def test_unresolved_esencial_hold_still_holds_everything(tmp_path):
    root = make_root(tmp_path, mode="hold")
    capture(root)
    pkg = f2.build_package(root, registry())
    assert any(x.startswith("HOLD_COVERAGE_ESENCIAL:fefi_2026_03") for x in pkg["reconciliation"]["failures"])
    assert pkg["values"] == {} and run(root)["status"] == "hold"


def test_without_rule_or_hold_all_ten_isapres_are_published(tmp_path):
    _, fi = published(tmp_path, mode="none")
    assert len(fi["evidence"]["entity_codes"]) == 10 and fi["headline"].startswith("Isapres a marzo 2026:")
    assert not any(n["id"] == "n0" for n in fi["notes"])


def test_unreadable_editorial_rules_fail_closed(tmp_path):
    root = make_root(tmp_path)
    (root / "config/editorial_rules_v3.json").write_text("{", encoding="utf-8")
    assert "HOLD_COVERAGE_ESENCIAL" in f2.esencial_hold(root)


# ---------------------------------------------------------------------------------------------
# Year on year with the 2025-03 file; loss → profit


def prev_data(scale=0.9):
    out = {k: [round(x * scale) for x in v] for k, v in REAL.items()}
    out["imp"] = [out["antes"][i] - out["gan"][i] for i in range(10)]  # keep the tax identity exact after rounding
    return out


def test_capture_takes_the_latest_and_the_same_quarter_a_year_earlier_first(tmp_path):
    root = make_root(tmp_path, prev=True)
    fetch = capture(root, files={URL: workbook(), URL_PREV: workbook(prev_data(), year="2025")}, max_new=2)
    assert fetch.calls == [URL, URL_PREV]  # diciembre 2025 waits for the next run


def test_year_on_year_needs_the_previous_file_verified_with_the_same_template(tmp_path):
    root = make_root(tmp_path, prev=True)
    capture(root, files={URL: workbook(), URL_PREV: workbook(prev_data(), year="2025")}, max_new=2)
    res = run(root)
    assert res["status"] == "pass", res.get("errors")
    fi = res["ficha"]
    ev = fi["evidence"]["values"]
    assert ev["ingresos_operacionales.sistema.2025-03"]["value"] == pytest.approx(sin_esencial("ingresos", prev_data()))
    pct = (sin_esencial("ingresos") / sin_esencial("ingresos", prev_data()) - 1) * 100
    assert ev["ingresos_operacionales.sistema.pct"]["value"] == pytest.approx(pct)
    assert not any(".108." in vid for vid in ev)  # Esencial excluded in both periods
    assert {s["key"] for s in fi["sources"]} == {"fefi", "fefi_prev"} and not any(n["id"] == "n5" for n in fi["notes"])
    # A previous file that does not verify: levels only, never an estimated comparison.
    root2 = make_root(tmp_path / "b", prev=True)
    bad = prev_data()
    bad["aporte"][0] += 99_000
    capture(root2, files={URL: workbook(), URL_PREV: workbook(bad, fixed={"ingresos": full(prev_data())["ingresos"]}, year="2025")},
            max_new=2)
    assert stored_doc(root2, "2025-03")["parse"]["status"] == "failed"
    assert not any(v.endswith(".pct") for v in run(root2)["ficha"]["evidence"]["values"])


def test_loss_to_profit_uses_absolute_change_and_na(tmp_path):
    cur = [12_000_000, 8_000_000, 1_000_000, 2_500_000, 9_000_000, 1_500_000, -2_000_000, 500_000, 1_090_653, 500_000]
    old = [-3_000_000, 1_000_000, 200_000, -500_000, 2_000_000, -1_000_000, -500_000, 300_000, 226_715, 200_000]
    res_rows = lambda g: {"gan": g, "antes": g, "imp": [0] * 10}  # noqa: E731
    root = make_root(tmp_path, prev=True)
    capture(root, files={URL: workbook(fixed=res_rows(cur)), URL_PREV: workbook(prev_data(), fixed=res_rows(old), year="2025")},
            max_new=2)
    res = run(root)
    assert res["status"] == "pass", res.get("errors")
    fi = res["ficha"]
    r_t = sum(x for i, x in enumerate(cur) if i != ESENCIAL) / 1000
    r_1 = sum(x for i, x in enumerate(old) if i != ESENCIAL) / 1000
    assert r_1 < 0 < r_t
    assert fi["headline"] == (f"Isapres sin Esencial a marzo 2026: utilidad de {sf.fmt_int(r_t)} MM$, tras una pérdida de "
                              f"{sf.fmt_int(abs(r_1))} MM$ en marzo 2025")
    k = {x["id"]: x for x in fi["kpis"]}
    assert "N/A (cambia de signo)" in k["resultado"]["lines"][0]
    ev = fi["evidence"]["values"]
    assert "resultado_ejercicio.sistema.pct" not in ev and ev["resultado_ejercicio.sistema.delta"]["value"] == pytest.approx(r_t - r_1)
    assert ev["resultado_ejercicio.67.delta"]["value"] == pytest.approx(15_000) and "resultado_ejercicio.67.pct" not in ev
    assert ev["resultado_ejercicio.78.pct"]["value"] == pytest.approx(700)
    table = next(c for c in sf.all_charts(fi) if c["id"] == "f2-resultado-isapres")["table"]["rows"]
    assert table[-1][0] == "Sistema sin Esencial" and table[-1][-1] == "N/A"
    assert fi["tabs"][0]["index_line"] == f"{sf.fmt_int(r_t)} MM$ · 9 de 9 Isapres con utilidad"
    for text in sf.displayed_texts(fi):
        assert not sf.SIGNED_WITH_WORD.search(text), text


def test_threshold_is_evaluated_on_the_rounded_value_shown(tmp_path):
    def simple(prest):
        d = {k: [0] * 10 for k in REAL}
        d["legal"] = [1000] * 10
        d["ingresos"] = [1000] * 10
        d["prest"] = prest
        return d
    cur = simple([900] * 6 + [500] + [900, 900, 896])  # 9 sin Esencial: 8.096 / 9.000 = 89,955… → shown 90,0%
    old = simple([890] * 10)  # 89,0%
    root = make_root(tmp_path, prev=True)
    capture(root, files={URL: workbook(cur), URL_PREV: workbook(old, year="2025")}, max_new=2)
    pkg = f2.build_package(root, registry())
    assert pkg["reconciliation"]["ok"], pkg["reconciliation"]["failures"]
    assert any(f.get("kpi") == "siniestralidad" and f.get("level") == 90 for f in pkg["findings"])
    assert pkg["values"]["siniestralidad.sistema.pp"]["value"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------------------------
# Capture: once, hash-bound re-check when the template changes


def test_template_change_triggers_one_hash_bound_recheck_and_keeps_the_previous_parse(tmp_path):
    # A workbook captured under the pending template (as before 2-nov) is re-checked once under the approved one.
    root = make_root(tmp_path, template=pending_template())
    data = workbook()
    assert len(capture(root, data, template=pending_template()).calls) == 1
    assert len(capture(root, data, template=pending_template()).calls) == 0  # downloaded once
    assert len(capture(root, data, template=committed_template()).calls) == 1  # template changed: one re-check
    doc = stored_doc(root)
    assert doc["parse"]["status"] == "verified" and doc["previous_parse"]["status"] == "template_unreviewed" and doc["rechecked_at"]
    assert doc["parse"]["template_sha256"] == ft.templates_sha256(committed_template())
    assert len(capture(root, data, template=committed_template()).calls) == 0
    tpl2 = {**committed_template(), "reviewed_at": "2026-11-03"}
    capture(root, workbook(note=A18 + " "), template=tpl2)  # other bytes on the re-check
    doc = stored_doc(root)
    assert doc["status"] == "hash_mismatch" and doc["recheck"]["recorded_sha256"] == hashlib.sha256(data).hexdigest()
    res = run(root, template=tpl2)
    assert res["status"] == "hold" and any("sha256_mismatch_on_recheck" in e for e in res["errors"])


def test_parse_made_with_another_template_holds(tmp_path):
    root = make_root(tmp_path)
    capture(root)
    res = run(root, template={**reviewed_template(), "reviewed_at": "2026-11-03"})
    assert res["status"] == "hold" and any("parse_made_with_another_template" in e for e in res["errors"])


def test_capture_only_talks_to_the_sis_fetcher_by_default(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    seen = []

    class Fake:
        def __init__(self, **kw):
            seen.append(kw)

        def __call__(self, url):
            raise PermissionError("robots_disallowed: fixture")
    monkeypatch.setattr(fc.cap, "SisFetcher", Fake)
    fc.capture_fefi(root, template=reviewed_template())
    doc = stored_doc(root)
    assert seen and doc["status"] == "fetch_failed" and "robots_disallowed" in doc["error"]


# ---------------------------------------------------------------------------------------------
# Wording, verification, budget


@pytest.mark.parametrize("prev,cur,expected,pct", [
    (-273.285, 34090.653, "utilidad de 34.091 MM$, tras una pérdida de 273 MM$ en marzo 2025", None),
    (500.0, -200.0, "pérdida de 200 MM$, tras una utilidad de 500 MM$ en marzo 2025", None),
    (-500.0, -200.0, "pérdida de 200 MM$, menor que la de 500 MM$ en marzo 2025", None),
    (-200.0, -500.0, "pérdida de 500 MM$, mayor que la de 200 MM$ en marzo 2025", None),
    (1000.0, 968.0, "utilidad de 968 MM$, 3,2% menos que en marzo 2025", -3.2),
    (1000.0, 1032.0, "utilidad de 1.032 MM$, 3,2% más que en marzo 2025", 3.2),
])
def test_result_wording_follows_the_sign(prev, cur, expected, pct):
    assert f2.result_phrase(prev, cur, "marzo 2025") == expected
    c = f2.change(prev, cur, result=True)
    assert (c["pct"] is None) == (pct is None) and (pct is None or round(c["pct"], 1) == pct)
    assert not sf.SIGNED_WITH_WORD.search(expected)


def test_verify_ficha_rejects_a_signed_figure_with_a_direction_word(tmp_path):
    root, fi = published(tmp_path)
    pkg = f2.build_package(root, registry())
    bad = copy.deepcopy(fi)
    bad["watch"][0]["explanation"] = "La siniestralidad fue −3,2% menos que el año anterior."
    assert any(e.startswith("signed_figure_with_direction_word:−3,2% menos") for e in sf.verify_ficha(bad, pkg)["errors"])


def test_f2_never_calls_a_model_while_lectura_is_disabled(tmp_path):
    root = make_root(tmp_path)
    capture(root)
    calls = []
    res = f2.run(root, today=TODAY, registry=registry(), llm=True, model_call=lambda *a, **k: calls.append(1),
                 budget=lambda w: (True, "ok"))
    assert res["status"] == "pass" and calls == [] and res["ficha"]["lectura"]["status"] == "not_attempted"


def test_daily_default_runs_and_captures_f2_with_no_paid_call(tmp_path, monkeypatch, capsys):
    """scripts/run_stats_fichas.py without --family (what the daily workflow runs) now includes F2: it captures the latest
    FEFI workbook and the same quarter a year earlier, publishes on PASS, and never asks for a Lectura even with a key."""
    sys.path.insert(0, str(REPO / "scripts"))
    import run_stats_fichas as runner
    reg = sf.load_registry()
    root = make_root(tmp_path, prev=True)
    fetch = fetcher({URL: workbook(), URL_PREV: workbook(prev_data(), year="2025")})
    real_capture = runner.stats_capture_fefi.capture_fefi
    fefi_calls = []
    monkeypatch.setattr(runner.stats_capture_fefi, "capture_fefi", lambda r: fefi_calls.append(r) or real_capture(r, fetch=fetch))
    monkeypatch.setattr(runner.stats_capture, "capture", lambda r: {"stub": True})
    others = []
    for fam in set(runner.BUILDERS) - {"F2"}:  # the other families are covered by their own suites
        monkeypatch.setitem(runner.BUILDERS, fam, lambda r, fam=fam, **kw: others.append(fam) or
                            {"status": "no_change", "family": fam, "slug": reg["families"][fam]["slug"], "period": None})
    lectura_enabled = []
    real_lectura = sf.generate_lectura
    monkeypatch.setattr(sf, "generate_lectura", lambda *a, **kw: lectura_enabled.append(kw.get("enabled")) or real_lectura(*a, **kw))
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-not-a-key")  # the daily job has a key: F2 must still make no paid call
    active = {f for f, c in reg["families"].items() if c.get("status") == "active"}
    assert "F2" in active and active <= set(runner.BUILDERS)
    assert runner.main(["--root", str(root), "--as-of", TODAY.isoformat()]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert fefi_calls and fetch.calls == [URL, URL_PREV] and summary["capture_fefi"]["verified"] >= 2
    assert set(others) == active - {"F2"}
    f2s = summary["F2"]
    assert f2s["status"] == "pass" and f2s["published"] and f2s["lectura"] == "not_attempted" and not f2s["cost_usd"]
    assert lectura_enabled and not any(lectura_enabled)
    live = json.loads(Path(f2s["live"]).read_text(encoding="utf-8"))
    assert live["kicker"] == "Estados financieros Isapres · marzo 2026" and "marzo 2025" in live["headline"]
    assert all("sistema sin Esencial" in k["label"] for k in live["kpis"])
    # --no-capture never downloads
    assert runner.main(["--root", str(root), "--as-of", TODAY.isoformat(), "--family", "F2", "--no-capture"]) == 0
    assert len(fefi_calls) == 1


# ---------------------------------------------------------------------------------------------
# Shared helpers and the playbook


def test_figure_template_review_rules():
    assert ft.review_state(None) == "not_configured"
    assert ft.review_state({"pattern": "<<x>>", "reviewed_by": "a", "reviewed_at": "b"}) == "placeholder"
    assert ft.review_state({"pattern": "x", "_doc": "use <<…>> markers", "reviewed_by": "a", "reviewed_at": "b"}) == "ok"
    assert ft.review_state({"pattern": "x", "reviewed_by": "TODO", "reviewed_at": "b"}) == "unreviewed"
    assert ft.normalize_text("Total  General\n1.004.982 Ñuñoa ") == "total general 1004982 nunoa"
    pat, _ = ft.compile_pattern(r"\btotal\b")
    assert ft.match_once(pat, [(1, "total"), (2, "x")])[2] == "ok"
    assert ft.match_once(pat, [(1, "total"), (2, "total")])[2] == "multiple_matches:2"
    assert ft.match_once(pat, [(1, "x")])[2] == "no_match"
    assert ft.compile_pattern("(a)(b)", groups=1)[1] == "invalid"
    assert ft.compile_pattern("{t_year} x")[1] == "invalid"


def test_playbook_is_linked_and_its_code_references_exist():
    import importlib
    import re
    playbook = (REPO / "data/stats_fichas/PLAYBOOK.md").read_text(encoding="utf-8")
    assert "PLAYBOOK.md" in (REPO / "data/stats_fichas/POLICY.md").read_text(encoding="utf-8")
    mods = {"sf": "stats_fichas", "stats_capture": "stats_capture", "stats_capture_fefi": "stats_capture_fefi",
            "figure_templates": "figure_templates", "stats_ficha_f2": "stats_ficha_f2", "lectura_verifier": "lectura_verifier"}
    refs = re.findall(r"`(sf|stats_capture_fefi|stats_capture|figure_templates|stats_ficha_f2|lectura_verifier)\.([A-Za-z_]+)", playbook)
    assert len(refs) >= 20
    for mod, name in refs:
        if mod == "stats_capture" and name == "_recheck_doc":
            continue  # F6 re-check lands with #112 (marked as such in the playbook)
        assert hasattr(importlib.import_module(f"radar_salud.{mods[mod]}"), name), f"{mod}.{name}"
    for path in re.findall(r"`((?:tests|src|scripts|config|web|data)/[\w/.\-*]+)`", playbook):
        if "*" in path or path.endswith("test_stats_fichas_f6_real_pdf.py"):
            continue
        assert (REPO / path).exists(), path
