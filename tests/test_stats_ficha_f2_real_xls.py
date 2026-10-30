"""CI-only: print the real FEFI workbook's structure so a person can write and review the F2 parser template.

Downloads the latest 'Estadísticas Financieras del Sistema Isapre' workbook listed in
``data/history/superintendencia_signals.json`` through the production ``SisFetcher`` (SIS allowlist, robots.txt, 25 MB
cap, deadline) and skips when the network or the SIS is unavailable (this sandbox has no egress to the SIS). When it
runs (GitHub Actions, qa.yml job 'tests') it writes GitHub ``::notice`` annotations to the real stdout (pytest's capture
suspended with ``capsys.disabled()``), at most 9, each ≤ ~3,000 characters and escaped:

1. format, SHA-256, size and every sheet name;
2. up to 7 sheets (financial statements first): their first non-empty rows, normalized as the template sees them
   (``r<row>: cell | cell | …``);
3. the coverage note that names Esencial ('Notas Explicativas', A18 according to Work6), so Dirección can read the
   contradiction behind HOLD_COVERAGE_ESENCIAL.

It asserts only rules, never counts: the workbook opens; while the committed template is unreviewed the parse is
``template_placeholder``/``template_unreviewed`` (HOLD); once a person reviews it, the parse must be ``verified``.
Only one annotation-emitting test should run per PR: GitHub keeps about 10 notices per step.
"""
import hashlib
import os
import re
import sys
import time

import pytest

from radar_salud import figure_templates as ft
from radar_salud import stats_capture as cap
from radar_salud import stats_capture_fefi as fc
from radar_salud import stats_fichas as sf

CHUNK_CHARS = 3000
MAX_ANNOTATIONS = 9
MAX_SHEETS = 7
RELEVANT = re.compile(r"resultado|balance|situacion|patrimonio|indicador|costo|ingreso|cotiz|siniestr")


def escape_data(text: str) -> str:
    """GitHub workflow-command message escaping: '%' → %25, '\\r' → %0D, '\\n' → %0A."""
    return str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_prop(text: str) -> str:
    """Property values (the title) also escape ':' and ','."""
    return escape_data(text).replace(":", "%3A").replace(",", "%2C")


def pick_sheets(summary: list[dict]) -> list[dict]:
    rel = [s for s in summary if RELEVANT.search(ft.normalize_text(s["name"]))]
    rest = [s for s in summary if s not in rel and "nota" not in ft.normalize_text(s["name"])]
    return (rel + rest)[:MAX_SHEETS]


def annotation_lines(meta: str, sheets: list[dict], note: str) -> list[str]:
    """``::notice`` lines: the workbook summary, one per picked sheet, the Esencial note; ≤ MAX_ANNOTATIONS, each chunk
    ≤ CHUNK_CHARS before escaping (a longer text is cut and says so)."""
    def clip(text: str) -> str:
        return text if len(text) <= CHUNK_CHARS else text[:CHUNK_CHARS - 40] + " [truncado: límite de anotación]"
    out = [f"::notice title=F2 FEFI workbook::{escape_data(clip(meta))}"]
    for s in sheets[:MAX_ANNOTATIONS - 2]:
        body = f"{s['name']} ({s['rows']} filas × {s['cols']} columnas)\n" + "\n".join(s["head"])
        out.append(f"::notice title={escape_prop('F2 hoja ' + s['name'][:60])}::{escape_data(clip(body))}")
    out.append(f"::notice title=F2 nota Esencial::{escape_data(clip(note))}")
    return out[:MAX_ANNOTATIONS]


def emit(lines: list[str], capsys) -> None:
    with capsys.disabled():
        sys.stdout.write("\n" + "\n".join(lines) + "\n")
        sys.stdout.flush()


def test_annotation_lines_are_escaped_clipped_and_capped():
    sheets = [{"name": f"Hoja {i}: a,b", "rows": 10, "cols": 3, "head": [f"r1: x%{i}", "r2: y"]} for i in range(12)]
    lines = annotation_lines("xlsx · sha\nhojas", sheets, "Nota 100% sobre Esencial\r\n" + "z" * 5000)
    assert len(lines) == MAX_ANNOTATIONS
    assert lines[0] == "::notice title=F2 FEFI workbook::xlsx · sha%0Ahojas"
    assert lines[1].startswith("::notice title=F2 hoja Hoja 0%3A a%2Cb::Hoja 0: a,b (10 filas × 3 columnas)%0Ar1: x%250")
    assert lines[-1].startswith("::notice title=F2 nota Esencial::Nota 100%25 sobre Esencial%0D%0A")
    assert lines[-1].endswith("[truncado: límite de anotación]") and all("\n" not in ln for ln in lines)
    assert all(len(ln) < CHUNK_CHARS * 1.2 + 120 for ln in lines)
    summary = [{"name": n, "rows": 1, "cols": 1, "head": []} for n in ("Índice", "Notas Explicativas", "E. Resultados comparado por Isa", "Balance")]
    assert [s["name"] for s in pick_sheets(summary)] == ["E. Resultados comparado por Isa", "Balance", "Índice"]


@pytest.fixture
def real_book(capsys):
    rels = fc.fefi_releases(sf.ROOT)
    if not rels:
        pytest.skip("no FEFI release listed in the SIS history")
    url = rels[-1]["documents"][0]["url"]
    try:
        data = cap.SisFetcher(deadline=time.monotonic() + 90, timeout=30)(url)
    except Exception as exc:  # no egress, proxy refusal, robots/SIS down: nothing to test here
        reason = f"real FEFI workbook not reachable: {type(exc).__name__}: {exc}"[:200]
        if os.environ.get("GITHUB_ACTIONS") == "true":
            emit([f"::notice title=F2 FEFI skipped::{escape_data(reason)}"], capsys)
        pytest.skip(reason)
    return rels[-1], url, data


def test_real_fefi_structure_is_printed_and_the_template_rule_holds(real_book, capsys):
    rel, url, data = real_book
    sha = hashlib.sha256(data).hexdigest()
    try:
        book = fc.read_workbook(data)
    except fc.XlsReaderUnavailable:
        emit([f"::notice title=F2 FEFI xls::{escape_data('formato xls y xlrd no instalado: ' + url + ' sha256 ' + sha)}"], capsys)
        pytest.skip("xls workbook and xlrd not installed")
    assert book["sheets"], "the workbook has no sheets"
    summary = fc.structure_summary(book)
    names = [s["name"] for s in book["sheets"]]
    meta = (f"{rel['title']} · período {rel['period']} · {url}\nformato {book['format']} · sha256 {sha} · {len(data)} bytes\n"
            f"{len(names)} hojas: " + " · ".join(names))
    notes = fc.find_cells(book, r"nota", r"esencial", limit=4)
    a18 = [{"sheet": s["name"], "cell": "A18", "text": str(s["rows"][17][0])[:1500]}
           for s in book["sheets"] if "nota" in ft.normalize_text(s["name"]) and len(s["rows"]) > 17 and s["rows"][17] and s["rows"][17][0]]
    seen, note_lines = set(), []
    for c in a18 + notes:
        if (c["sheet"], c["cell"]) not in seen:
            seen.add((c["sheet"], c["cell"]))
            note_lines.append(f"{c['sheet']}!{c['cell']}: {c['text']}")
    note = "\n".join(note_lines) or "Ninguna celda de una hoja 'Notas' nombra a Esencial y A18 está vacía."
    emit(annotation_lines(meta, pick_sheets(summary), note), capsys)
    template = sf.load_registry()["families"]["F2"]["parser_template"]
    parse = fc.parse_fefi_workbook(data, template, rel["period"])
    if ft.review_state(template) != "ok":
        assert parse["status"] in ("template_placeholder", "template_unreviewed")
    else:  # a reviewed template must read the real workbook exactly
        assert parse["status"] == "verified", parse.get("failures")
