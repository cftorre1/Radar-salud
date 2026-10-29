"""Test fixtures for the F4 (GES) and F6 (Boletín IP) fichas. Never used by the product.

- GES: synthetic workbooks (clearly fixture values) in the SIS layout: one sheet per year, the reporting year pinned,
  problem rows plus a declared 'Total' row. Fonasa/Isapre columns declare 'casos acumulados enero a <mes>'.
- Boletín IP: minimal PDFs that contain the figures of the independent reading in
  ``config/statistical_analysis_verified_v1.json`` (N°2-2026); other releases' PDFs carry no verified figures.

``python tests/stats_ficha_fixtures.py`` rewrites ``tests/fixtures/stats_fichas/*.json`` (fichas and feed cards) used by
the node and Playwright tests. Hashes in those fichas are hashes of these fixture bytes, not of SIS files.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from io import BytesIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from radar_salud import stats_capture as cap  # noqa: E402

GES_URL = "https://www.superdesalud.gob.cl/app/uploads/fixture/ges-{period}.xlsx"
MONTHS = cap.MONTHS
FIXTURE_DIR = REPO / "tests/fixtures/stats_fichas"
INPUTS = ("data/market/isapre_portfolio.json", "data/entities/isapres.json", "data/history/superintendencia_signals.json",
          "config/statistical_analysis_verified_v1.json")

# Year-to-date cuts (Fonasa, Isapre) per problem. Fixture values only.
GES_CUTS = {
    "2025-03": {"Diabetes Mellitus Tipo 2": (10000, 1000), "Hipertensión arterial en personas de 15 años y más": (20000, 2000),
                "Cáncer de mama en personas de 15 años y más": (1000, 400), "Depresión en personas de 15 años y más": (5000, 1500),
                "Hipoacusia bilateral en personas de 65 años y más": (600, 50), "Problema retirado de prueba": (300, 20)},
    "2025-06": {"Diabetes Mellitus Tipo 2": (21000, 2100), "Hipertensión arterial en personas de 15 años y más": (41000, 4100),
                "Cáncer de mama en personas de 15 años y más": (2100, 850), "Depresión en personas de 15 años y más": (10500, 3100),
                "Hipoacusia bilateral en personas de 65 años y más": (1250, 110), "Problema retirado de prueba": (600, 40)},
    "2026-03": {"Diabetes Mellitus Tipo 2": (11000, 1100), "Hipertensión arterial en personas de 15 años y más": (21000, 2200),
                "Cáncer de mama en personas de 15 años y más": (1200, 500), "Depresión en personas de 15 años y más": (6000, 1700),
                "Hipoacusia bilateral en personas de 65 años y más": (700, 60), "Problema nuevo de prueba": (800, 200)},
    "2026-06": {"Diabetes Mellitus Tipo 2": (23500, 2350), "Hipertensión arterial en personas de 15 años y más": (43000, 4500),
                "Cáncer de mama en personas de 15 años y más": (2700, 1100), "Depresión en personas de 15 años y más": (12600, 3500),
                "Hipoacusia bilateral en personas de 65 años y más": (1450, 125), "Problema nuevo de prueba": (1700, 450)},
}
GES_PUBLISHED = {"2025-03": "2025-10-03", "2025-06": "2025-10-03", "2026-03": "2026-07-10", "2026-06": "2026-10-14"}


def ges_workbook(period: str, rows: dict, *, header: str | None = None, extra=("Año 2005",), total_delta=(0, 0)) -> bytes:
    from openpyxl import Workbook
    year, month = period[:4], MONTHS[int(period[5:7]) - 1]
    head = header if header is not None else f"casos acumulados enero a {month}"
    book = Workbook()
    book.active.title = extra[0] if extra else f"Año {year}"
    for i, name in enumerate(extra):
        ws = book.active if i == 0 else book.create_sheet(name)
        ws.append(["N°", "Problema de salud", "Fonasa", "Isapre"])
        for j in range(3):
            ws.append([j + 21, str(j + 21), 900000, 900000])
    ws = book.create_sheet(f"Año {year}") if extra else book.active
    ws.append([f"Casos GES (AUGE) de Fonasa y Sistema Isapre, año {year}"])
    ws.append([])
    ws.append(["N°", "Problema de salud", f"Fonasa {head}", f"Isapre {head}"])
    for i, (label, (f, s)) in enumerate(rows.items(), 1):
        ws.append([i, label, f, s])
    ws.append([None, "Total", sum(f for f, _ in rows.values()) + total_delta[0], sum(s for _, s in rows.values()) + total_delta[1]])
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def pdf_with_text(lines: list[str]) -> bytes:
    """A minimal valid PDF (Helvetica text) that pypdf can read."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = "BT /F1 11 Tf 50 780 Td 14 TL " + " ".join(f"({esc(x)}) '" for x in lines) + " ET"
    stream = content.encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out = BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def boletin_pdf(url: str, root: Path) -> bytes:
    metrics = (cap.verified_metrics(root).get(url) or {}).get("metrics") or {}
    lines = [f"Boletin fixture {url.rsplit('/', 1)[-1]}"]
    for key, v in metrics.items():
        lines.append(f"{key}: {f'{int(v):,}'.replace(',', '.')}")
    return pdf_with_text(lines)


def ges_signals() -> list[dict]:
    out = []
    for period in GES_CUTS:
        month = MONTHS[int(period[5:7]) - 1]
        out.append({"title": f"Estadística Trimestral de Casos GES (AUGE) de Fonasa y Sistema ISAPRE – a {month} {period[:4]}",
                    "source_name": "Superintendencia de Salud", "signal_types": ["Datos"],
                    "source_url": f"https://www.superdesalud.gob.cl/biblioteca-digital/fixture-ges-{period}/",
                    "event_date": GES_PUBLISHED[period], "source_documents": [{"url": GES_URL.format(period=period)}]})
    return out


def make_root(tmp: Path, *, ges: bool = True) -> Path:
    """Copy the inputs; replace the GES releases of the history by the fixture ones (Boletín releases stay real)."""
    for rel in INPUTS:
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp / rel)
    hist_path = tmp / INPUTS[2]
    hist = json.loads(hist_path.read_text(encoding="utf-8"))
    hist["signals"] = [s for s in hist["signals"] if "casos ges" not in cap._fold(s.get("title"))] + (ges_signals() if ges else [])
    hist_path.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    return tmp


def fetcher(root: Path, books: dict[str, bytes] | None = None, *, fail: set[str] | None = None):
    books = dict(books or {})
    for period, rows in GES_CUTS.items():
        books.setdefault(GES_URL.format(period=period), ges_workbook(period, rows))
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        if fail and url in fail:
            raise OSError("offline")
        if url in books:
            return books[url]
        if url.endswith(".pdf"):
            return boletin_pdf(url, root)
        raise OSError(f"unknown fixture url {url}")
    fetch.calls = calls
    return fetch


def capture_all(root: Path, fetch) -> None:
    for _ in range(8):  # bounded per run: several runs capture everything
        cap.capture(root, fetch=fetch)


def write_fixtures() -> None:
    import tempfile
    from radar_salud import stats_ficha_f4 as f4, stats_ficha_f6 as f6, stats_fichas as sf
    reg = sf.load_registry()
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(Path(tmp))
        capture_all(root, fetcher(root))
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        for fam, mod in (("F4", f4), ("F6", f6)):
            out = mod.run(root, today=date(2026, 10, 29), registry=reg, llm=False)
            assert out["status"] == "pass", out.get("errors")
            ficha = out["ficha"]
            card = sf.ficha_card(ficha, reg["families"][fam])
            card["fixture_note"] = "Fixture de prueba: hashes de bytes de prueba" + (", cifras GES sintéticas" if fam == "F4" else
                                                                                      ", cifras de la lectura verificada N°2-2026")
            slug = reg["families"][fam]["slug"]
            (FIXTURE_DIR / f"{slug}.card.json").write_text(json.dumps(card, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_fixtures()
