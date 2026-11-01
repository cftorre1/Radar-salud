"""CI-only: print what a person still needs to finish the F2 template, from the real FEFI workbook.

Downloads the latest 'Estadísticas Financieras del Sistema Isapre' workbook listed in
``data/history/superintendencia_signals.json`` (and the one of the same quarter a year earlier, for the a/a plan)
through the production ``SisFetcher`` (SIS allowlist, robots.txt, 25 MB cap, deadline). It skips when the network or the
SIS is unavailable (this sandbox has no egress to the SIS). When it runs (GitHub Actions, qa.yml job 'tests') it writes
GitHub ``::notice`` annotations to the real stdout (pytest's capture suspended with ``capsys.disabled()``), at most 9,
each ≤ ~3,000 characters and escaped:

1. format, SHA-256, size and sheet names of the latest workbook;
2. rows r17 onwards of the two sheets the template reads ('Ctas. de Resultados I. Abierta ' and '… I. Cerradas'),
   normalized as the template sees them (rows r1–r16 were printed on PR #117 and are already in the template);
3. the coverage note (Notas Explicativas!A18) that the Esencial exclusion rule depends on;
4. a dry-run status: the committed template with its ``<<…>>`` rows dropped and the review simulated, applied to the
   latest workbook and to the previous-year one. This is a display aid only; it never marks anything as reviewed.

It asserts only rules, never counts: the workbook opens; the two Ctas sheets exist; while the committed template is
unreviewed the parse is ``template_placeholder``/``template_unreviewed``; once a person reviews it, it must be ``verified``.
Only one annotation-emitting test should run per PR: GitHub keeps about 10 notices per step.
"""
import copy
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
FIRST_ROW = 17
CTAS = re.compile(r"^ctas\. de resultados i\. (abierta|cerradas)$")


def escape_data(text: str) -> str:
    """GitHub workflow-command message escaping: '%' → %25, '\\r' → %0D, '\\n' → %0A."""
    return str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_prop(text: str) -> str:
    """Property values (the title) also escape ':' and ','."""
    return escape_data(text).replace(":", "%3A").replace(",", "%2C")


def sheet_rows(sheet: dict, first: int = FIRST_ROW) -> str:
    lines = [f"r{i + 1}: {fc.row_text(r)}" for i, r in enumerate(sheet["rows"]) if i + 1 >= first and fc.row_text(r)]
    return "\n".join(lines) or f"(sin filas desde r{first})"


def chunks(text: str) -> list[str]:
    lines, out, cur = text.split("\n"), [], ""
    for ln in lines:
        ln = ln if len(ln) <= CHUNK_CHARS else ln[:CHUNK_CHARS - 40] + " [truncado]"
        if cur and len(cur) + 1 + len(ln) > CHUNK_CHARS:
            out.append(cur)
            cur = ln
        else:
            cur = f"{cur}\n{ln}" if cur else ln
    return out + ([cur] if cur else [])


def annotation_lines(meta: str, sheets: list[tuple[str, str]], note: str, status: str) -> list[str]:
    """``::notice`` lines: the workbook summary, each Ctas sheet's rows in ~CHUNK_CHARS chunks, the A18 note and the
    dry-run status; ≤ MAX_ANNOTATIONS (the longest sheet loses its last chunks first, and says so)."""
    parts = {name: chunks(text) for name, text in sheets}
    budget = MAX_ANNOTATIONS - 3
    trimmed = set()
    while sum(len(c) for c in parts.values()) > budget:
        name = max(parts, key=lambda n: len(parts[n]))
        parts[name].pop()
        trimmed.add(name)
    out = [f"::notice title=F2 FEFI workbook::{escape_data(meta[:CHUNK_CHARS])}"]
    for name, cs in parts.items():
        for i, c in enumerate(cs, 1):
            tail = " [truncado: límite de anotaciones]" if name in trimmed and i == len(cs) else ""
            out.append(f"::notice title={escape_prop(f'F2 {name.strip()} r{FIRST_ROW}+ ({i}/{len(cs)})')}::{escape_data(c + tail)}")
    out.append(f"::notice title=F2 nota Esencial::{escape_data(note[:CHUNK_CHARS])}")
    out.append(f"::notice title=F2 plantilla (simulada)::{escape_data(status[:CHUNK_CHARS])}")
    return out


def dry_run_template(template: dict) -> dict:
    """Display aid: the committed template without its ``<<…>>`` accounts and with the review simulated."""
    tpl = copy.deepcopy(template)
    for tab in tpl.get("tables", {}).values():
        tab["accounts"] = {k: v for k, v in tab.get("accounts", {}).items() if not ft.has_placeholder(v)}
    tpl.update(reviewed_by="simulado en CI (no es revisión)", reviewed_at="simulado")
    return tpl


def emit(lines: list[str], capsys) -> None:
    with capsys.disabled():
        sys.stdout.write("\n" + "\n".join(lines) + "\n")
        sys.stdout.flush()


def test_annotation_lines_are_escaped_chunked_and_capped():
    big = "\n".join(f"r{i}: " + "x" * 500 for i in range(17, 60))
    lines = annotation_lines("xls · sha\nhojas", [("Ctas. de Resultados I. Abierta ", big), ("Ctas. de Resultados I. Cerradas", "r17: a%b")],
                             "Notas Explicativas!A18: 100% Esencial\r\n", "2026-03: verified")
    assert len(lines) == MAX_ANNOTATIONS and lines[0] == "::notice title=F2 FEFI workbook::xls · sha%0Ahojas"
    assert lines[1].startswith("::notice title=F2 Ctas. de Resultados I. Abierta r17+ (1/5)::r17: ")
    assert "[truncado: límite de anotaciones]" in lines[5] and lines[6].endswith("::r17: a%25b")
    assert lines[-2] == "::notice title=F2 nota Esencial::Notas Explicativas!A18: 100%25 Esencial%0D%0A"
    assert lines[-1] == "::notice title=F2 plantilla (simulada)::2026-03: verified"
    assert all("\n" not in ln and len(ln) < CHUNK_CHARS * 1.2 + 120 for ln in lines)
    tpl = dry_run_template(sf.load_registry()["families"]["F2"]["parser_template"])
    assert ft.review_state(tpl) == "ok" and "resultado_ejercicio.t" not in tpl["tables"]["ctas_abiertas"]["accounts"]


def _fetch(url):
    return cap.SisFetcher(deadline=time.monotonic() + 90, timeout=30)(url)


@pytest.fixture
def real_books(capsys):
    rels = fc.fefi_releases(sf.ROOT)
    if not rels:
        pytest.skip("no FEFI release listed in the SIS history")
    latest = rels[-1]
    try:
        data = _fetch(latest["documents"][0]["url"])
    except Exception as exc:  # no egress, proxy refusal, robots/SIS down: nothing to test here
        reason = f"real FEFI workbook not reachable: {type(exc).__name__}: {exc}"[:200]
        if os.environ.get("GITHUB_ACTIONS") == "true":
            emit([f"::notice title=F2 FEFI skipped::{escape_data(reason)}"], capsys)
        pytest.skip(reason)
    y, m = latest["period"].split("-")
    prior = next((r for r in rels if r["period"] == f"{int(y) - 1}-{m}"), None)
    prior_data = None
    if prior:
        try:
            prior_data = _fetch(prior["documents"][0]["url"])
        except Exception:
            prior_data = None
    return latest, data, prior, prior_data


def test_real_fefi_rows_note_and_template_rule(real_books, capsys):
    latest, data, prior, prior_data = real_books
    url, sha = latest["documents"][0]["url"], hashlib.sha256(data).hexdigest()
    try:
        book = fc.read_workbook(data)
    except fc.XlsReaderUnavailable:
        emit([f"::notice title=F2 FEFI xls::{escape_data('formato xls y xlrd no instalado: ' + url + ' sha256 ' + sha)}"], capsys)
        pytest.skip("xls workbook and xlrd not installed")
    names = [s["name"] for s in book["sheets"]]
    ctas = [s for s in book["sheets"] if CTAS.fullmatch(ft.normalize_text(s["name"]))]
    meta = (f"{latest['title']} · período {latest['period']} · {url}\nformato {book['format']} · sha256 {sha} · {len(data)} bytes\n"
            f"{len(names)} hojas: " + " · ".join(names))
    notes = fc.find_cells(book, r"^notas explicativas$", r"esencial", limit=3)
    note = "\n".join(f"{c['sheet']}!{c['cell']}: {c['text']}" for c in notes) or "Ninguna celda de 'Notas Explicativas' nombra a Esencial."
    template = sf.load_registry()["families"]["F2"]["parser_template"]
    dry = dry_run_template(template)
    status = []
    for rel, raw in ((latest, data), (prior, prior_data)):
        if not rel:
            status.append("año anterior: no listado en el historial")
            continue
        if raw is None:
            status.append(f"{rel['period']}: no descargado")
            continue
        p = fc.parse_fefi_workbook(raw, dry, rel["period"])
        status.append(f"{rel['period']} ({hashlib.sha256(raw).hexdigest()[:12]}…): {p['status']}"
                      + (f" · {'; '.join(p.get('failures') or [])[:900]}" if p.get("failures") else "")
                      + (f" · nota {p['coverage_note']['sheet'].strip()}!{p['coverage_note']['cell']}" if p.get("coverage_note") else ""))
    emit(annotation_lines(meta, [(s["name"], sheet_rows(s)) for s in ctas], note, "\n".join(status)), capsys)
    assert len(ctas) == 2, names
    parse = fc.parse_fefi_workbook(data, template, latest["period"])
    if ft.review_state(template) != "ok":
        assert parse["status"] in ("template_placeholder", "template_unreviewed")
    else:  # a reviewed template must read the real workbook exactly
        assert parse["status"] == "verified", parse.get("failures")
