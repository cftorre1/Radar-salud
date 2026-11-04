"""Test fixtures for the F4 (GES) and F6 (Boletín IP) fichas. Never used by the product.

- GES: synthetic workbooks (clearly fixture values) in the SIS layout: one sheet per year, a two-row header with the
  cumulative-since-July-2005 cuts and the 'Ingresos entre Ene y <mes>' (year-to-date) column over FONASA/ISAPRE pairs,
  problem rows, a 'Subtotal' row and the declared 'Total' row.
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

# Year-to-date flows (Fonasa, Isapre) per GES problem number: cases that entered between January and the cut, as the SIS
# column 'Ingresos entre Ene y <mes> <año>'. Fixture values only. The workbook carries, as the SIS does, cumulative counts
# since July 2005 per cut: BASE_DEC_2023 + the year-to-date flows of every year since 2024.
# Like the real GES list (80+ problems, numbered 1…n without gaps; registry F4.capture.min_problems), the fixture has
# problems 1–5 with their own figures, fillers 6–84 (small, constant flows: below the ranking's 500-case base) and
# problem 85, added by decree in 2026.
FILLERS = range(6, 85)
NEW_CODE = 85


def _filler_label(code: int) -> str:
    a, b = divmod(code - 6, 26)
    return f"Problema de relleno {chr(97 + a)}{chr(97 + b)}"  # no digits: a label number would be a showable figure


GES_LABELS = {1: "Diabetes Mellitus Tipo 2", 2: "Hipertensión arterial en personas de 15 años y más",
              3: "Cáncer de mama en personas de 15 años y más", 4: "Depresión en personas de 15 años y más",
              5: "Hipoacusia bilateral en personas de 65 años y más", **{c: _filler_label(c) for c in FILLERS},
              NEW_CODE: "Problema nuevo de prueba (3)"}
BASE_DEC_2023 = {1: (2_000_000, 150_000), 2: (4_000_000, 350_000), 3: (250_000, 50_000), 4: (1_500_000, 400_000),
                 5: (60_000, 5_000), **{c: (300_017 + 1_013 * c, 30_011 + 101 * c) for c in FILLERS}}
_Y24 = {1: (9500, 950), 2: (19000, 1900), 3: (950, 380), 4: (4800, 1400), 5: (550, 45)}


def _fill(rows: dict, q: int) -> dict:
    return {**rows, **{c: (5 * q, q) for c in FILLERS}}


GES_YTD = {
    **{f"2024-{m:02d}": _fill({c: (f * k, i * k) for c, (f, i) in _Y24.items()}, k) for k, m in ((1, 3), (2, 6), (3, 9), (4, 12))},
    "2025-03": _fill({1: (10000, 1000), 2: (20000, 2000), 3: (1000, 400), 4: (5000, 1500), 5: (600, 50)}, 1),
    "2025-06": _fill({1: (21000, 2100), 2: (41000, 4100), 3: (2100, 850), 4: (10500, 3100), 5: (1250, 110)}, 2),
    "2025-09": _fill({1: (31000, 3100), 2: (61000, 6100), 3: (3100, 1250), 4: (15500, 4600), 5: (1850, 160)}, 3),
    "2025-12": _fill({1: (42000, 4200), 2: (82000, 8200), 3: (4200, 1700), 4: (21000, 6200), 5: (2500, 220)}, 4),
    "2026-03": _fill({1: (11000, 1100), 2: (21000, 2200), 3: (1200, 500), 4: (6000, 1700), 5: (700, 60), NEW_CODE: (800, 200)}, 1),
    "2026-06": _fill({1: (23500, 2350), 2: (43000, 4500), 3: (2700, 1100), 4: (12600, 3500), 5: (1450, 125), NEW_CODE: (1700, 450)}, 2),
}
GES_RELEASES = ("2025-03", "2025-06", "2026-03", "2026-06")
GES_PUBLISHED = {"2025-03": "2025-10-03", "2025-06": "2025-10-03", "2026-03": "2026-07-10", "2026-06": "2026-10-14"}
MON3 = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")


def ges_cumulative(ytd: dict) -> dict:
    """Cumulative counts since July 2005 per cut: {period: {code: (f, i)}} (2023-12 and every cut of ``ytd``)."""
    cum = {"2023-12": dict(BASE_DEC_2023)}
    for per in sorted(ytd):
        prev_dec = cum.get(f"{int(per[:4]) - 1}-12") or {}
        cum[per] = {c: ((prev_dec.get(c) or (0, 0))[0] + f, (prev_dec.get(c) or (0, 0))[1] + i) for c, (f, i) in ytd[per].items()}
    return cum


def ges_workbook(period: str, ytd: dict | None = None, *, ytd_header: str | None = None, total_delta=(0, 0),
                 ytd_delta: dict | None = None, extra=("Indice", "Notas", "Año 2005"), cum: dict | None = None,
                 first_year: int = 2023, labels: dict | None = None) -> bytes:
    """A synthetic workbook in the SIS layout: one sheet per year (2023 … year of ``period``); two-row header (group
    titles 'Número de casos acumulados Jul-2005 a <Mes>-<año>' / 'Ingresos entre Ene y <Mes> <año>' over FONASA/ISAPRE
    pairs); the line of cut dates; one row per problem (N°, label); a 'Subtotal' row and the declared 'Total' row.

    ``total_delta`` shifts the declared Total of the year-to-date column of the reporting year; ``ytd_delta``
    ({code: (df, di)}) shifts that column for one problem and its total (rows still add up, the identity breaks).
    ``cum`` ({period: {code: (f, i)}}) gives the cumulative cuts directly (e.g. figures copied from a SIS text receipt)
    instead of deriving them from ``ytd``; then ``ytd`` holds only the SIS year-to-date columns."""
    from datetime import datetime
    from openpyxl import Workbook
    ytd = GES_YTD if ytd is None else ytd
    y, m = int(period[:4]), int(period[5:7])
    labels = labels or GES_LABELS
    cum = cum if cum is not None else ges_cumulative({p: v for p, v in ytd.items() if p <= period})
    book = Workbook()
    first = True
    for name in extra:
        ws = book.active if first else book.create_sheet(name)
        ws.title, first = name, False
        if name == "Notas":
            ws.append(["N°", "DESCRIPCIÓN"])
            ws.append([2, "A partir de julio 2012 la fuente de datos es el archivo de solicitudes de acceso a la GES."])
            ws.append([3, "Esta información no incorpora casos de VIH atendidos por FONASA (fixture)."])
            ws.append([4, "Las diferencias en el problema 57 se deben a la eliminación de casos del archivo, por parte de una isapre."])
        elif name.startswith("Año"):
            ws.append(["N°", "PROBLEMA DE SALUD", "Número de casos acumulados Jul-2005 a Dic-2005"])
            ws.append([None, None, "FONASA", "ISAPRE"])
            for j in range(3):
                ws.append([j + 21, str(j + 21), 900000, 900000])
    for year in range(first_year, y + 1):
        ws = book.create_sheet(f"Año {year}")
        last = m if year == y else 12
        groups = [("cut", f"{year}-{q:02d}") for q in (3, 6, 9, 12)] + [("ytd", f"{year}-{last:02d}")]
        head = ["N°", "PROBLEMA DE SALUD"]
        for kind, per in groups:
            mm = int(per[5:])
            if kind == "cut":
                head += [f"Número de casos acumulados\n Jul-2005 a {MON3[mm - 1]}-{year}", None]
            else:
                head += [ytd_header if (ytd_header is not None and year == y) else f"Ingresos entre \nEne  y {MON3[mm - 1]} {year}", None]
        ws.append(["CASOS GES ACUMULADOS POR PROBLEMA DE SALUD"])
        ws.append([])
        ws.append(head)
        ws.append([None, None] + ["FONASA", "ISAPRE"] * len(groups))
        ws.append([None, None] + [datetime(year, int(per[5:]), 28) if kind == "cut" else None for kind, per in groups for _ in (0, 1)])
        codes = sorted({c for kind, per in groups for c in ((cum.get(per) or {}) if kind == "cut" else (ytd.get(per) or {}))})
        totals = [0] * (2 * len(groups))
        for n, code in enumerate(codes):
            row = [code, labels[code]]
            for g, (kind, per) in enumerate(groups):
                src = (cum.get(per) or {}) if kind == "cut" else (ytd.get(per) or {}) if per <= period else {}
                pair = src.get(code)
                if pair and kind == "ytd" and year == y and ytd_delta and code in ytd_delta:
                    pair = (pair[0] + ytd_delta[code][0], pair[1] + ytd_delta[code][1])
                row += list(pair) if pair else [None, None]
                if pair:
                    totals[2 * g] += pair[0]
                    totals[2 * g + 1] += pair[1]
            ws.append(row)
            if n == 1:
                ws.append([None, "Subtotal Casos GES Decreto Supremo de prueba", *[None] * (2 * len(groups))])
        tot = [x if x else None for x in totals]
        if year == y:
            g = len(groups) - 1
            tot[2 * g] = (tot[2 * g] or 0) + total_delta[0]
            tot[2 * g + 1] = (tot[2 * g + 1] or 0) + total_delta[1]
        ws.append([None, "Total Casos GES", *tot])
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def pdf_with_text(lines: list[str], *, pages: list[list[str]] | None = None) -> bytes:
    """A minimal valid PDF (Helvetica text) that pypdf can read: one page of ``lines``, or one page per ``pages``."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    pages = pages if pages is not None else [lines]
    n = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    font = 3 + 2 * n
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode()]
    for i, page in enumerate(pages):
        content = "BT /F1 11 Tf 50 780 Td 14 TL " + " ".join(f"({esc(x)}) '" for x in page) + " ET"
        stream = content.encode("cp1252")  # WinAnsiEncoding (en dash, bullet, …)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {4 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode())
        objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
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


# Spanish wording next to each verified figure, as in the SIS bulletins (the capture requires a context word nearby).
LABELS = {"accredited_providers": "Prestadores acreditados", "with_observations": "Acreditados con observaciones",
          "pending_applications": "Solicitudes en tramite", "private_pending": "Solicitudes de prestadores privados",
          "public_pending": "Solicitudes de prestadores publicos", "registered_mediators": "Mediadores inscritos",
          "cumulative_requests_2019_to_june2026": "Solicitudes de mediacion acumuladas",
          "cumulative_requests_2019_to_september2026": "Solicitudes de mediacion acumuladas",
          "monthly_average_2026": "Promedio mensual de reclamos 2026", "monthly_average_2025": "Promedio mensual de reclamos 2025",
          "reported_growth_percent_rounded": "Aumento de reclamos (%)", "registered_titles": "Titulos inscritos",
          "records_without_birth_date": "Registros sin fecha de nacimiento"}


def figure_line(key: str, v) -> str:
    return f"{LABELS.get(key, 'Reclamos acreditados titulos')}: {f'{int(v):,}'.replace(',', '.')}"


def boletin_pdf(url: str, root: Path) -> bytes:
    """Figures on the first page cited by the verified reading (earlier pages carry only a page number)."""
    info = cap.verified_metrics(root).get(url) or {}
    metrics = info.get("metrics") or {}
    first = min(info.get("pages_1based") or [1])
    body = [f"Boletin fixture {url.rsplit('/', 1)[-1]}", *(figure_line(k, v) for k, v in metrics.items())]
    rel = cap.doc_release(url)
    if rel and rel["topic"] == "acreditacion":
        # Checker v3: these two figures are placed only by the approved templates, so the fixture carries the SIS
        # wording they anchor on (p.2 sentence; p.8 table title with its cut-off date and the 'total general' row).
        month = MONTHS[int(rel["period"][5:]) - 1]
        if "with_observations" in metrics:
            body.append(f"{metrics['with_observations']} prestadores institucionales obtuvieron el resultado de acreditado "
                        "con observaciones")
        if {"pending_applications", "private_pending", "public_pending"} <= set(metrics):
            body += [f"Numero de solicitudes de acreditacion que estan en tramitacion, al 30 de {month} de {rel['period'][:4]}, "
                     "desagregadas por region del prestador y tipo",
                     f"Total general {metrics['private_pending']} {metrics['public_pending']} {metrics['pending_applications']}"]
    return pdf_with_text([], pages=[[f"Pagina {i}"] for i in range(1, first)] + [body])


def ges_signals() -> list[dict]:
    out = []
    for period in GES_RELEASES:
        month = MONTHS[int(period[5:7]) - 1]
        out.append({"title": f"Estadística Trimestral de Casos GES (AUGE) de Fonasa y Sistema ISAPRE – a {month} {period[:4]}",
                    "source_name": "Superintendencia de Salud", "signal_types": ["Datos"],
                    "source_url": f"https://www.superdesalud.gob.cl/biblioteca-digital/fixture-ges-{period}/",
                    "event_date": GES_PUBLISHED[period], "source_documents": [{"url": GES_URL.format(period=period)}]})
    return out


def make_root(tmp: Path, *, ges: bool = True, readings_until: str | None = None) -> Path:
    """Copy the inputs; replace the GES releases of the history by the fixture ones (Boletín releases stay real).

    ``readings_until='2026-06'`` keeps only the independent readings of Boletín releases up to that period: the state
    before the N°3-2026 reading was committed (2-nov-2026), for the tests written for that state (N°2 live, N°3
    captured without a reading)."""
    for rel in INPUTS:
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp / rel)
    if readings_until:
        path = tmp / cap.VERIFIED
        cfg = json.loads(path.read_text(encoding="utf-8"))
        docs = cfg["primary_review"]["documents"]
        cfg["primary_review"]["documents"] = [d for d in docs if ((cap.doc_release(d.get("url") or "") or {}).get("period")
                                                                   or "0000-00") <= readings_until]
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    hist_path = tmp / INPUTS[2]
    hist = json.loads(hist_path.read_text(encoding="utf-8"))
    hist["signals"] = [s for s in hist["signals"] if "casos ges" not in cap._fold(s.get("title"))] + (ges_signals() if ges else [])
    hist_path.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    return tmp


def fetcher(root: Path, books: dict[str, bytes] | None = None, *, fail: set[str] | None = None):
    books = dict(books or {})
    for period in GES_RELEASES:
        books.setdefault(GES_URL.format(period=period), ges_workbook(period))
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


def confirmed_registry(registry: dict | None = None, by: str = "revisor de prueba") -> dict:
    """Registry copy with the F4 measure confirmed by a (test) reviewer (the committed registry carries Dirección's
    confirmation of 3-nov-2026; F4 HOLDs without one) and without the first-publication review gate
    (``first_pass_requires_review``), so builder tests see the PASS; the gate has its own test."""
    import copy
    from radar_salud import stats_fichas as sf
    reg = copy.deepcopy(registry or sf.load_registry())
    reg["families"]["F4"]["measure"].update(confirmed=True, confirmed_by=by)
    reg["families"]["F4"]["first_pass_requires_review"] = False
    return reg


def capture_all(root: Path, fetch) -> None:
    for _ in range(8):  # bounded per run: several runs capture everything
        cap.capture(root, fetch=fetch)


def write_f1_fixture(feed_date: str = "2026-10-10") -> Path:
    """F1 card for the browser spec (``python -c "import sys; sys.path.insert(0, 'tests'); import stats_ficha_fixtures as f;
    f.write_f1_fixture()"``), built offline from the committed cartera capture with the Lectura off: no download, no model
    call. ``feed_date`` keeps the card inside the spec's 30-day window."""
    import tempfile
    from radar_salud import stats_ficha_f1 as f1, stats_fichas as sf
    reg = sf.load_registry()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel in ("data/market/isapre_portfolio.json", "data/excel/validated_series.json", "data/entities/isapres.json",
                    "data/history/superintendencia_signals.json"):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / rel, root / rel)
        out = f1.run(root, today=date(2026, 10, 28), registry=reg, llm=False)
        assert out["status"] == "pass", out.get("errors")
        card = sf.ficha_card(out["ficha"], reg["families"]["F1"], feed_date=feed_date)
    card["fixture_note"] = "Fixture de prueba: cifras de la captura de cartera comprometida, sin Lectura"
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURE_DIR / "f1_cartera.card.json"
    path.write_text(json.dumps(card, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def write_fixtures() -> None:
    import tempfile
    from radar_salud import stats_ficha_f4 as f4, stats_ficha_f6 as f6, stats_fichas as sf
    reg = sf.load_registry()
    with tempfile.TemporaryDirectory() as tmp:
        root = make_root(Path(tmp), readings_until="2026-06")  # fixture cards dated 29-oct: N°2 live
        capture_all(root, fetcher(root))
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        for fam, mod in (("F4", f4), ("F6", f6)):
            out = mod.run(root, today=date(2026, 10, 29), registry=confirmed_registry(reg) if fam == "F4" else reg, llm=False)
            assert out["status"] == "pass", out.get("errors")
            ficha = out["ficha"]
            card = sf.ficha_card(ficha, reg["families"][fam])
            card["fixture_note"] = "Fixture de prueba: hashes de bytes de prueba" + (", cifras GES sintéticas" if fam == "F4" else
                                                                                      ", cifras de la lectura verificada N°2-2026")
            slug = reg["families"][fam]["slug"]
            (FIXTURE_DIR / f"{slug}.card.json").write_text(json.dumps(card, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_fixtures()
