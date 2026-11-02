"""Text receipts of captured SIS statistics documents (data/stats_fichas/text/<sha256[:16]>.json, 2-nov-2026).

The reviewer who writes the independent reading of a new Boletín release needs the documents' text; only the daily
run can download SIS files. Rules tested here, offline with fake fetchers:
- a capture writes one receipt per sha256 (url, sha256, extracted_at, extractor, raw + normalized text per page);
- caps: 60 pages (sheets) and 200 KB of JSON per document;
- only allowlisted SIS hosts get a receipt;
- xlsx: sheet names and the first 40 rows of each sheet;
- a document captured before receipts existed is downloaded once more for its receipt, within the run's budget.
"""
import json
import sys
from io import BytesIO
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import stats_ficha_fixtures as fx  # noqa: E402
from radar_salud import stats_capture as cap  # noqa: E402

BOLETIN = "data/stats_fichas/captures/boletin_ip.json"
GES = "data/stats_fichas/captures/ges_quarterly.json"
SIS_PDF = "https://www.superdesalud.gob.cl/app/uploads/2026/10/boletin-n3-2026-reclamos-enero-septiembre-2026.pdf"


@pytest.fixture(autouse=True)
def isolated_ledgers(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_ROOT", str(tmp_path / "ledger-root"))


def receipts(root: Path) -> dict[str, dict]:
    d = root / cap.TEXT_STORE
    return {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))} if d.exists() else {}


def captured_docs(root: Path) -> list[dict]:
    bol = json.loads((root / BOLETIN).read_text(encoding="utf-8"))
    ges = json.loads((root / GES).read_text(encoding="utf-8"))
    return ([d for r in bol["releases"] for d in r["documents"]] + [r["document"] for r in ges["releases"]])


def test_capture_writes_one_receipt_per_sha_and_never_rewrites(tmp_path):
    root = fx.make_root(tmp_path)
    fetch = fx.fetcher(root)
    fx.capture_all(root, fetch)
    docs = [d for d in captured_docs(root) if d.get("status") == "captured"]
    got = receipts(root)
    assert docs and len(got) == len({d["sha256"] for d in docs})
    for d in docs:
        rec = got[f"{d['sha256'][:16]}.json"]
        assert d["text_receipt"]["status"] == "written"
        assert d["text_receipt"]["path"] == f"data/stats_fichas/text/{d['sha256'][:16]}.json"
        assert rec["url"] == d["url"] and rec["sha256"] == d["sha256"] and rec["extracted_at"]
        assert rec["extractor"]["name"] == ("pypdf" if d["format"] == "pdf" else "openpyxl") and rec["extractor"]["version"]
    pdf = next(d for d in docs if d["format"] == "pdf" and "acreditacion-enero-junio-2026" in d["url"])
    rec = got[f"{pdf['sha256'][:16]}.json"]
    assert rec["pages_total"] == rec["pages_kept"] == len(rec["pages"]) and not rec["truncated"]
    for page in rec["pages"]:
        assert page["text_normalized"] == cap.normalize_page(page["text_raw"])
    assert any("prestadores acreditados" in p["text_normalized"] for p in rec["pages"])

    before = {p.name: p.read_bytes() for p in (root / cap.TEXT_STORE).glob("*.json")}
    calls = len(fetch.calls)
    cap.capture(root, fetch=fetch)  # nothing new: no download, no rewrite
    assert len(fetch.calls) == calls
    assert {p.name: p.read_bytes() for p in (root / cap.TEXT_STORE).glob("*.json")} == before
    data = fetch(pdf["url"])
    assert cap.write_text_receipt(root, pdf["url"], data)["status"] == "exists"
    assert (root / cap.TEXT_STORE / f"{pdf['sha256'][:16]}.json").read_bytes() == before[f"{pdf['sha256'][:16]}.json"]


def test_caps_hold_pages_and_bytes(tmp_path):
    long_line = "Reclamos acreditados " + "x" * 90
    pdf = fx.pdf_with_text([], pages=[[f"Pagina {i}", *[long_line] * 40] for i in range(1, 66)])
    out = cap.write_text_receipt(tmp_path, SIS_PDF, pdf)
    assert out["status"] == "written" and out["truncated"]
    path = tmp_path / out["path"]
    assert path.stat().st_size <= cap.TEXT_MAX_BYTES
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["pages_total"] == 65 and rec["pages_kept"] <= cap.TEXT_MAX_UNITS
    assert set(rec["truncated_reasons"]) == {"max_units", "max_bytes"}
    assert rec["pages"][-1].get("text_truncated") is True

    few = fx.pdf_with_text([], pages=[[f"Pagina {i}"] for i in range(1, 64)])
    rec = cap.build_text_receipt(SIS_PDF, few)
    assert rec["pages_total"] == 63 and rec["pages_kept"] == 60 and rec["truncated_reasons"] == ["max_units"]
    assert [p["page"] for p in rec["pages"]] == list(range(1, 61))


def test_byte_cap_keeps_a_prefix_of_an_oversized_first_page(tmp_path, monkeypatch):
    monkeypatch.setattr(cap, "TEXT_MAX_BYTES", 4000)
    pdf = fx.pdf_with_text(["Titulos inscritos " + "y" * 90] * 60)
    out = cap.write_text_receipt(tmp_path, SIS_PDF, pdf)
    rec = json.loads((tmp_path / out["path"]).read_text(encoding="utf-8"))
    assert (tmp_path / out["path"]).stat().st_size <= 4000
    assert rec["pages_kept"] == 1 and rec["pages"][0]["text_truncated"] and rec["truncated_reasons"] == ["max_bytes"]
    assert rec["pages"][0]["text_raw"].startswith("Titulos inscritos")


@pytest.mark.parametrize("url", ["https://example.com/boletin.pdf", "http://www.superdesalud.gob.cl/a.pdf",
                                 "https://www.superdesalud.gob.cl.evil.cl/a.pdf", "https://user:pw@www.superdesalud.gob.cl/a.pdf",
                                 "https://www.superdesalud.gob.cl:8443/a.pdf", "https://www.df.cl/estadisticas.pdf"])
def test_non_sis_hosts_are_refused(tmp_path, url):
    out = cap.write_text_receipt(tmp_path, url, fx.pdf_with_text(["Reclamos 2026: 1.234"]))
    assert out == {"status": "refused", "reason": "host_not_allowlisted"}
    assert not (tmp_path / cap.TEXT_STORE).exists()
    doc = {"url": url, "status": "captured", "format": "pdf", "sha256": "ab" * 32}
    assert not cap.needs_text_backfill(tmp_path, doc)


def test_xlsx_receipt_has_sheet_names_and_first_40_rows(tmp_path):
    from openpyxl import Workbook
    book = Workbook()
    book.active.title = "Año 2005"
    book.active.append(["N°", "Problema de salud", "Fonasa", "Isapre"])
    ws = book.create_sheet("Año 2026")
    ws.append(["Casos GES (AUGE) de Fonasa y Sistema Isapre, año 2026"])
    ws.append([])
    ws.append(["N°", "Problema de salud", "Fonasa casos acumulados enero a junio", "Isapre"])
    for i in range(1, 60):
        ws.append([i, f"Problema {i}", 1000.0 + i, 1234567])
    out = BytesIO()
    book.save(out)
    url = "https://www.superdesalud.gob.cl/app/uploads/2026/10/estadistica-trimestral-de-casos-ges-junio-2026.xlsx"
    res = cap.write_text_receipt(tmp_path, url, out.getvalue())
    assert res["status"] == "written" and not res["truncated"]
    rec = json.loads((tmp_path / res["path"]).read_text(encoding="utf-8"))
    assert rec["format"] == "xlsx" and rec["extractor"]["name"] == "openpyxl"
    assert rec["sheet_names"] == ["Año 2005", "Año 2026"] and rec["sheets_total"] == rec["sheets_kept"] == 2
    assert rec["limits"]["rows_per_sheet"] == 40
    first, second = rec["sheets"]
    assert first == {"sheet": 1, "name": "Año 2005", "text_raw": "N°\tProblema de salud\tFonasa\tIsapre",
                     "text_normalized": "n° problema de salud fonasa isapre"}
    rows = second["text_raw"].split("\n")
    assert len(rows) == 40 and rows[1] == ""
    assert rows[3] == "1\tProblema 1\t1001\t1234567"
    assert rows[-1].startswith("37\tProblema 37\t") and "Problema 38" not in second["text_raw"]
    assert "1001 1234567" in second["text_normalized"] and second["text_normalized"] == cap.normalize_page(second["text_raw"])


def _strip_receipts(root: Path) -> None:
    """The store as left by a capture that predates text receipts."""
    import shutil
    shutil.rmtree(root / cap.TEXT_STORE)
    for rel in (BOLETIN, GES):
        path = root / rel
        store = json.loads(path.read_text(encoding="utf-8"))
        for r in store["releases"]:
            for d in r.get("documents") or [r["document"]]:
                d.pop("text_receipt", None)
        path.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")


def test_missing_receipt_is_backfilled_once_within_the_budget(tmp_path):
    root = fx.make_root(tmp_path)
    fetch = fx.fetcher(root)  # one fetcher: the fixture xlsx bytes carry a save timestamp
    fx.capture_all(root, fetch)
    _strip_receipts(root)
    bol = json.loads((root / BOLETIN).read_text(encoding="utf-8"))
    newest = bol["releases"][-1]
    assert newest["period"] == "2026-09" and all(d["status"] == "captured" for d in newest["documents"])
    ges_newest = json.loads((root / GES).read_text(encoding="utf-8"))["releases"][-1]["document"]

    del fetch.calls[:]
    summary = cap.capture(root, fetch=fetch, max_new=3)
    # Budget: 3 per kind. GES: its newest xlsx; Boletín: 3 of the 4 newest PDFs, the 4th waits for the next run.
    assert summary["ges"]["text_backfills"] == 1 and summary["boletin_ip"]["text_backfills"] == 3
    assert summary["boletin_ip"]["downloads"] <= 3
    assert sorted(fetch.calls) == sorted([ges_newest["url"], *[d["url"] for d in newest["documents"]][:3]])
    cap.capture(root, fetch=fetch, max_new=3)
    assert len(fetch.calls) == 5 and fetch.calls[-1] == newest["documents"][3]["url"]
    got = receipts(root)
    for d in [*newest["documents"], ges_newest]:
        assert got[f"{d['sha256'][:16]}.json"]["sha256"] == d["sha256"]
    assert len(got) == 5  # older releases are not backfilled
    stored = json.loads((root / BOLETIN).read_text(encoding="utf-8"))["releases"][-1]["documents"]
    assert all(d["text_receipt"]["status"] == "written" and d["text_receipt"]["backfill"] for d in stored)
    assert [d["parse"] for d in stored] == [d["parse"] for d in newest["documents"]]  # capture record unchanged

    for _ in range(3):  # once: never downloaded again
        cap.capture(root, fetch=fetch)
    assert len(fetch.calls) == 5


def test_backfill_hash_mismatch_writes_nothing_and_is_not_retried(tmp_path):
    root = fx.make_root(tmp_path)
    fx.capture_all(root, fx.fetcher(root))
    _strip_receipts(root)
    newest = json.loads((root / BOLETIN).read_text(encoding="utf-8"))["releases"][-1]["documents"]
    changed = newest[0]["url"]
    fetch = fx.fetcher(root, {changed: fx.pdf_with_text(["Archivo reemplazado por el SIS"])})
    cap.capture(root, fetch=fetch)
    rec = json.loads((root / BOLETIN).read_text(encoding="utf-8"))["releases"][-1]["documents"][0]
    assert rec["text_receipt"]["status"] == "hash_mismatch" and rec["status"] == "captured"
    assert not (root / cap.text_receipt_path(rec["sha256"])).exists()
    n = len(fetch.calls)
    cap.capture(root, fetch=fetch)
    assert changed not in fetch.calls[n:]


def test_backfill_fetch_failure_is_retried_up_to_three_times(tmp_path):
    root = fx.make_root(tmp_path)
    fx.capture_all(root, fx.fetcher(root))
    _strip_receipts(root)
    ges_url = json.loads((root / GES).read_text(encoding="utf-8"))["releases"][-1]["document"]["url"]
    fetch = fx.fetcher(root, fail={ges_url})
    for _ in range(5):
        cap.capture(root, fetch=fetch)
    assert fetch.calls.count(ges_url) == cap.MAX_ATTEMPTS
    doc = json.loads((root / GES).read_text(encoding="utf-8"))["releases"][-1]["document"]
    assert doc["text_receipt"]["status"] == "fetch_failed" and doc["text_receipt"]["attempts"] == cap.MAX_ATTEMPTS



def test_daily_workflow_commits_the_receipt_folder():
    """daily-radar.yml (scheduled from main, checks out staging) commits data/stats_fichas, which holds the receipts."""
    wf = (fx.REPO / ".github/workflows/daily-radar.yml").read_text(encoding="utf-8")
    assert "git add data/stats_fichas" in wf
    assert cap.TEXT_STORE.as_posix().startswith("data/stats_fichas/")
