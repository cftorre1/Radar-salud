"""CI-only: build the F2 ficha from the real FEFI workbooks, so Dirección reads its text before the daily run publishes it.

Downloads the latest 'Estadísticas Financieras del Sistema Isapre' workbook listed in
``data/history/superintendencia_signals.json`` and the one of the same quarter a year earlier through the production
``SisFetcher`` (SIS allowlist, robots.txt, 25 MB cap, deadline). It skips when the network or the SIS is unavailable (this
sandbox has no egress to the SIS). When it runs (GitHub Actions) it writes GitHub ``::notice`` annotations to the real
stdout (pytest's capture suspended with ``capsys.disabled()``), at most 9, each ≤ ~3,000 characters and escaped:

1. format, SHA-256, size and sheet names of the latest workbook;
2. the F2 ficha built from those bytes in a temporary root, exactly as the daily run would (capture → reviewed template
   → ``stats_ficha_f2.run`` with the Lectura off): kicker, headline, dek, KPI cards and topic list, or the HOLD reasons;
3. the coverage note (Notas Explicativas) that the Esencial exclusion rule depends on;
4. the parse status of both workbooks with the committed template.

The template was approved on 2-nov-2026, so the row dumps of 'E. Resultados I.' printed while it was being written
are no longer emitted (lower value than the ficha text within the annotation budget). Nothing is written to the
repository and no model is called.

It asserts only rules, never counts: the workbook opens; the two E. Resultados I. sheets exist; a reviewed template reads
the real workbook as ``verified``; the ficha either PASSes (verified, no Lectura attempted, no Esencial figure, totals
labelled 'sistema sin Esencial' while the exclusion applies) or HOLDs with its reasons printed. A HOLD does not fail the
test: the daily workflow runs this suite before collecting, and an external change (e.g. A18) must hold the ficha,
not stop the daily run. Only one annotation-emitting test should run per PR: GitHub keeps about 10 notices per step.
"""
import hashlib
PINNED_2026_03 = "e3c4f7b3cfee"  # sha256 prefix of finan_ifrs_mar_2026_web_v2.xls, the file the template was approved on
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

import pytest

from radar_salud import figure_templates as ft
from radar_salud import stats_capture as cap
from radar_salud import stats_capture_fefi as fc
from radar_salud import stats_ficha_f2 as f2
from radar_salud import stats_fichas as sf
from radar_salud.weekly_freshness import chile_today

CHUNK_CHARS = 3000
MAX_ANNOTATIONS = 9
SHEETS = re.compile(r"^e\. resultados i\. (abiertas|cerradas)$")


def escape_data(text: str) -> str:
    """GitHub workflow-command message escaping: '%' → %25, '\\r' → %0D, '\\n' → %0A."""
    return str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_prop(text: str) -> str:
    """Property values (the title) also escape ':' and ','."""
    return escape_data(text).replace(":", "%3A").replace(",", "%2C")


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


def annotation_lines(meta: str, ficha: str, note: str, status: str) -> list[str]:
    """``::notice`` lines: the workbook summary, the ficha text in ~CHUNK_CHARS chunks, the A18 note and the parse status;
    ≤ MAX_ANNOTATIONS (the ficha text loses its last chunks first, and says so)."""
    parts = chunks(ficha)
    budget = MAX_ANNOTATIONS - 3
    trimmed = len(parts) > budget
    parts = parts[:budget]
    out = [f"::notice title=F2 FEFI workbook::{escape_data(meta[:CHUNK_CHARS])}"]
    for i, c in enumerate(parts, 1):
        tail = " [truncado: límite de anotaciones]" if trimmed and i == len(parts) else ""
        out.append(f"::notice title={escape_prop(f'F2 ficha ({i}/{len(parts)})')}::{escape_data(c + tail)}")
    out.append(f"::notice title=F2 nota Esencial::{escape_data(note[:CHUNK_CHARS])}")
    out.append(f"::notice title=F2 plantilla revisada::{escape_data(status[:CHUNK_CHARS])}")
    return out


def ficha_text(res: dict) -> str:
    """What Dirección needs to read before publication: kicker, headline, dek, KPI cards and topics (or the HOLD)."""
    fi = res.get("ficha") or {}
    lect = (fi.get("lectura") or {}).get("status")
    if res.get("status") != "pass":
        cand = (res.get("candidate") or {}) if isinstance(res.get("candidate"), dict) else {}
        lines = [f"HOLD · período {res.get('period')} · no se publicaría", "Motivos: " + "; ".join(map(str, res.get("errors") or []))[:1500]]
        if cand.get("headline"):
            lines.append(f"Titular candidato: {cand['headline']}")
        return "\n".join(lines)
    lines = [f"PASS · período {fi.get('period')} · verificación {(fi.get('verification') or {}).get('verdict')} · Lectura {lect}",
             f"Antetítulo: {fi.get('kicker')}", f"Meta: {fi.get('kicker_meta')}", f"Titular: {fi.get('headline')}",
             f"Bajada: {fi.get('dek')}", "Tarjetas KPI:"]
    for k in fi.get("kpis") or []:
        lines.append(f"- {k.get('label')}: {k.get('value')}" + "".join(f" · {ln}" for ln in k.get("lines") or []))
    lines.append("Temas:")
    for t in fi.get("tabs") or []:
        lines.append(f"- {t.get('label')}: {t.get('index_line') or ''}")
    # F2 v5: the per-Isapre split (prestaciones · SIL · total) and SIL / cotizaciones, as 'Ver datos' shows them.
    for cid in SPLIT_TABLES:
        c = next((c for t in fi.get("tabs") or [] for c in t.get("charts") or [] if c.get("id") == cid), None)
        if c:
            lines.append(f"{c.get('headline')} ({' · '.join(map(str, c['table']['columns'][1:]))}):")
            lines += [f"- {r[0]}: {' · '.join(map(str, r[1:]))}" for r in c["table"]["rows"]]
    return "\n".join(lines)


SPLIT_TABLES = ("f2-siniestralidad-isapres", "f2-sil-cotizaciones")


def build_ficha(tmp: Path, latest: dict, data: bytes, prior: dict | None, prior_data: bytes | None) -> dict:
    """The daily run on a temporary root: the already downloaded bytes are served to ``capture_fefi`` (no new request),
    read with the committed (reviewed) template, then ``stats_ficha_f2.run`` with the Lectura off."""
    root = tmp / "root"
    for rel in ("config/stats_fichas_v1.json", "config/editorial_rules_v3.json", "data/entities/isapres.json"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(sf.ROOT / rel, root / rel)
    sigs = [s for s in cap._signals(sf.ROOT) if fc.TITLE_KEY in cap._fold(str(s.get("title") or ""))]
    (root / cap.HISTORY).parent.mkdir(parents=True, exist_ok=True)
    (root / cap.HISTORY).write_text(json.dumps({"signals": sigs}, ensure_ascii=False), encoding="utf-8")
    files = {latest["documents"][0]["url"]: data}
    if prior and prior_data is not None:
        files[prior["documents"][0]["url"]] = prior_data

    def serve(url):
        if url not in files:
            raise PermissionError("not served in this test")
        return files[url]
    fc.capture_fefi(root, fetch=serve)
    return f2.run(root, today=chile_today(), llm=False)


def emit(lines: list[str], capsys) -> None:
    with capsys.disabled():
        sys.stdout.write("\n" + "\n".join(lines) + "\n")
        sys.stdout.flush()


def test_ficha_text_prints_the_per_isapre_split_for_review():
    chart = {"id": "f2-siniestralidad-isapres", "headline": "Siniestralidad por Isapre",
             "table": {"columns": ["Isapre", "Prestaciones", "SIL", "Total"], "rows": [["Colmena", "70,0%", "12,6%", "82,6%"]]}}
    text = ficha_text({"status": "pass", "ficha": {"tabs": [{"label": "Siniestralidad", "index_line": "x", "charts": [chart]}]}})
    assert "Siniestralidad por Isapre (Prestaciones · SIL · Total):\n- Colmena: 70,0% · 12,6% · 82,6%" in text


def test_annotation_lines_are_escaped_chunked_and_capped():
    big = "\n".join(f"- KPI {i}: " + "x" * 500 for i in range(60))
    lines = annotation_lines("xls · sha\nhojas", big, "Notas Explicativas!A18: 100% Esencial\r\n", "2026-03: verified")
    assert len(lines) == MAX_ANNOTATIONS and lines[0] == "::notice title=F2 FEFI workbook::xls · sha%0Ahojas"
    assert lines[1].startswith("::notice title=F2 ficha (1/6)::- KPI 0: ")
    assert lines[6].endswith("[truncado: límite de anotaciones]")
    assert lines[-2] == "::notice title=F2 nota Esencial::Notas Explicativas!A18: 100%25 Esencial%0D%0A"
    assert lines[-1] == "::notice title=F2 plantilla revisada::2026-03: verified"
    assert all("\n" not in ln and len(ln) < CHUNK_CHARS * 1.2 + 120 for ln in lines)
    short = annotation_lines("m", "PASS\nTitular: a%b", "n", "s")
    assert len(short) == 4 and short[1] == "::notice title=F2 ficha (1/1)::PASS%0ATitular: a%25b"


def test_ficha_text_lists_headline_dek_kpis_and_topics():
    res = {"status": "pass", "ficha": {"period": "2026-03", "kicker": "Estados financieros Isapres · marzo 2026",
                                       "headline": "H", "dek": "D", "verification": {"verdict": "PASS"},
                                       "lectura": {"status": "not_attempted"},
                                       "kpis": [{"label": "Ingresos (sistema sin Esencial)", "value": "1 MM$", "lines": ["l"]}],
                                       "tabs": [{"label": "Ingresos", "index_line": "1 MM$"}]}}
    txt = ficha_text(res)
    assert "Antetítulo: Estados financieros Isapres · marzo 2026" in txt and "Titular: H" in txt and "Bajada: D" in txt
    assert "- Ingresos (sistema sin Esencial): 1 MM$ · l" in txt and "Temas:\n- Ingresos: 1 MM$" in txt
    assert ficha_text({"status": "hold", "period": "2026-03", "errors": ["x"]}).startswith("HOLD · período 2026-03")


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


def test_real_fefi_ficha_note_and_template_rule(real_books, capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_ROOT", str(tmp_path / "ledger-root"))
    latest, data, prior, prior_data = real_books
    url, sha = latest["documents"][0]["url"], hashlib.sha256(data).hexdigest()
    try:
        book = fc.read_workbook(data)
    except fc.XlsReaderUnavailable:
        emit([f"::notice title=F2 FEFI xls::{escape_data('formato xls y xlrd no instalado: ' + url + ' sha256 ' + sha)}"], capsys)
        pytest.skip("xls workbook and xlrd not installed")
    names = [s["name"] for s in book["sheets"]]
    eres = [s for s in book["sheets"] if SHEETS.fullmatch(ft.normalize_text(s["name"]))]
    meta = (f"{latest['title']} · período {latest['period']} · {url}\nformato {book['format']} · sha256 {sha} · {len(data)} bytes\n"
            f"{len(names)} hojas: " + " · ".join(names))
    notes = fc.find_cells(book, r"^notas explicativas$", r"esencial", limit=3)
    note = "\n".join(f"{c['sheet']}!{c['cell']}: {c['text']}" for c in notes) or "Ninguna celda de 'Notas Explicativas' nombra a Esencial."
    template = sf.load_registry()["families"]["F2"]["parser_template"]
    status = []
    for rel, raw in ((latest, data), (prior, prior_data)):
        if not rel:
            status.append("año anterior: no listado en el historial")
            continue
        if raw is None:
            status.append(f"{rel['period']}: no descargado")
            continue
        p = fc.parse_fefi_workbook(raw, template, rel["period"])
        status.append(f"{rel['period']} ({hashlib.sha256(raw).hexdigest()[:12]}…): {p['status']}"
                      + (f" · {'; '.join(p.get('failures') or [])[:900]}" if p.get("failures") else "")
                      + (f" · nota {p['coverage_note']['sheet'].strip()}!{p['coverage_note']['cell']}" if p.get("coverage_note") else ""))
    reviewed = ft.review_state(template) == "ok"
    res = build_ficha(tmp_path, latest, data, prior, prior_data) if reviewed else {"status": "hold", "period": latest["period"],
                                                                                   "errors": ["plantilla sin revisar"]}
    emit(annotation_lines(meta, ficha_text(res), note, "\n".join(status)), capsys)
    parse = fc.parse_fefi_workbook(data, template, latest["period"])
    if not reviewed:
        assert parse["status"] in ("template_placeholder", "template_unreviewed")
        return
    # A new SIS workbook that the template refuses must HOLD the ficha, never stop the daily run (review 2-nov):
    # the exact-read assertions apply only to the file the template was approved on.
    if hashlib.sha256(data).hexdigest().startswith(PINNED_2026_03):
        assert len(eres) == 2, names
        assert parse["status"] == "verified", parse.get("failures")  # the approved file must read exactly
    assert res["status"] in ("pass", "hold"), res
    if res["status"] == "pass":
        fi = res["ficha"]
        assert fi["verification"]["verdict"] == "PASS" and fi["lectura"]["status"] == "not_attempted"  # no paid call
        assert fi["kicker"] == f"Estados financieros Isapres · {sf.month_label(fi['period'])}"
        if any(n["id"] == "n0" for n in fi["notes"]):  # Esencial excluded by the A18 rule
            assert not any(".108." in vid for vid in fi["evidence"]["values"])
            assert not any("Esencial" in k["label"] for k in fi["kpis"]) and "Esencial" in fi["scope_note"]
            assert "Esencial" not in fi["headline"]
    else:
        assert res.get("errors")  # a HOLD always says why (printed above); it never publishes
