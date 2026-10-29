"""F6 (Boletín IP) figure rules, checker version 2 (acreditación), approved by Dirección 2026-10-29.

A verified figure counts as present on a cited page when ANY of these holds:
- context window (v1, unchanged): a metric keyword within 80 characters;
- (a) sentence (v2): the figure and a metric keyword in the same sentence (bounded by . ; : or a blank line; a single
  line break does not end it); a figure printed as a table cell never counts by sentence;
- (b) Total row (v2): the figure is a cell of a 'Total' / 'Total general' row whose table caption / heading contains
  the keyword, and (>= 3 cells) equals the sum of the other cells.

Synthetic text reproduces the two real layouts of boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf (sha256
8b7f7c7a385e…): 101 on p.2 split by a line break 82 characters from 'observaciones', and 584 only in Total rows
(p.7, whose cells do not add up, and p.8 'Total general 367 217 584'). No network.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import stats_ficha_fixtures as fx  # noqa: E402
from radar_salud import stats_capture as cap  # noqa: E402
from radar_salud import stats_ficha_f6 as f6, stats_fichas as sf  # noqa: E402

ACR = "https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf"
STORE = "data/stats_fichas/captures/boletin_ip.json"
M = {"with_observations": 101, "pending_applications": 584}
OBS = cap.METRIC_CONTEXT["with_observations"]
TRA = cap.METRIC_CONTEXT["pending_applications"]


@pytest.fixture(autouse=True)
def isolated_ledgers(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_ROOT", str(tmp_path / "ledger-root"))


# p.2: the figure and its keyword in one sentence across a single line break, 82 characters apart.
P2 = ["Resultados del proceso de acreditacion",
      "Del conjunto de prestadores acreditados al 30 de junio, 101 prestadores institucionales",
      "obtuvieron finalmente el resultado de acreditado con observaciones en su ultimo proceso."]
# p.2 variant: same figure, keyword in the NEXT sentence (beyond the window).
P2_OTHER_SENTENCE = ["Resultados del proceso de acreditacion",
                     "Del conjunto de prestadores acreditados al 30 de junio, 101 prestadores institucionales fueron",
                     "evaluados en procesos de alta, media y baja complejidad durante el periodo informado. Varios",
                     "obtuvieron el resultado de acreditado con observaciones."]
REGIONS = ["Region de Arica y Parinacota", "Region de Tarapaca", "Region de Antofagasta", "Region de Atacama",
           "Region de Coquimbo", "Region de Valparaiso", "Region Metropolitana", "Region de OHiggins", "Region del Maule"]
PRIV = [10, 12, 25, 9, 20, 41, 180, 30, 40]
PUB = [8, 10, 15, 7, 18, 30, 60, 30, 39]


def p7() -> list[str]:
    """Table by provider type; its Total row's cells do not add up to 584 (157+37+5+30+117+237 = 583)."""
    return ["Grafico 6. Solicitudes de acreditacion en tramitacion segun tipo de prestador y estado del proceso",
            "Atencion abierta Atencion cerrada Laboratorio Imagenologia Otros Sin clasificar Total",
            *(f"Estado {i} {i} {i + 1} 1 {i + 2} {i + 3} {i + 4} {5 * i + 11}" for i in range(1, 9)),
            "157 37 5 30 117 237 584"]


def p8(caption="Tabla 7. Solicitudes de acreditacion en tramitacion al 30 de junio de 2026, segun region y tipo",
       total="Total general 367 217 584") -> list[str]:
    """Caption far (> 80 chars) from the Total row; rows by region; 'Total general 367 217 584'."""
    return [caption, "Region Privado Publico Total general",
            *(f"{r} {a} {b} {a + b}" for r, a, b in zip(REGIONS, PRIV, PUB)), total]


def doc(p2=P2, p7_lines=None, p8_lines=None) -> bytes:
    pages = [["Boletin Estadistico Informativo IP N 2 2026",
              "Al 30 de junio de 2026 hay 971 prestadores institucionales acreditados.",
              "De las solicitudes en tramite, 367 corresponden a prestadores privados y 217 a prestadores publicos."],
             p2, ["Pagina 3"], ["Pagina 4"], ["Pagina 5"], ["Pagina 6"], p7_lines or p7(), p8_lines or p8()]
    return fx.pdf_with_text([], pages=pages)


def text_of(pdf: bytes, page: int) -> str:
    return cap.pdf_pages(pdf)[page - 1]


def test_synthetic_layouts_fail_the_80_char_window_like_the_real_pdf():
    pdf = doc()
    assert sum(PRIV) == 367 and sum(PUB) == 217
    folded = cap._fold(text_of(pdf, 2))
    assert folded.index("observacion") - (folded.index("101") + 3) == 82  # as in the real p.2
    assert not cap.present_in(text_of(pdf, 2), 101, OBS)
    assert not any(cap.present_in(text_of(pdf, p), 584, TRA) for p in (7, 8))
    # Version 1 (pre-bump) reproduces today's HOLD.
    res = cap.parse_boletin_pdf(pdf, M, [1, 2, 7, 8])
    assert res["checker_version"] == 1 and res["status"] == "verified_figure_missing"
    assert res["verified_present"] == {"with_observations": False, "pending_applications": False}


def test_101_passes_by_sentence_and_584_by_total_row_with_caption():
    res = cap.parse_boletin_pdf(doc(), M, [1, 2, 7, 8], "acreditacion")
    assert res["checker_version"] == 2 and res["status"] == "verified"
    assert res["figure_rules"]["with_observations"] == {"rule": "sentence", "page": 2}
    tot = res["figure_rules"]["pending_applications"]
    assert tot["rule"] == "total_row" and tot["page"] == 8  # p.7's row does not add up
    assert tot["row"] == "total general 367 217 584" and tot["sum_check"] == "367 + 217 = 584"
    assert "tramitacion" in tot["heading"]
    # The single line break does not end the sentence; the p.7 Total row fails its sum check on its own.
    assert cap.in_same_sentence(text_of(doc(), 2), 101, OBS)
    assert cap.total_row_match(text_of(doc(), 7), 584, TRA) is None


def test_number_in_another_sentence_is_not_accepted():
    pdf = doc(p2=P2_OTHER_SENTENCE)
    assert not cap.present_in(text_of(pdf, 2), 101, OBS)
    res = cap.parse_boletin_pdf(pdf, M, [1, 2, 7, 8], "acreditacion")
    assert res["status"] == "verified_figure_missing" and res["verified_present"]["with_observations"] is False
    # ';', ':' and a blank line end a sentence too; a single line break does not.
    assert not cap.in_same_sentence("101 prestadores; con observaciones", 101, OBS)
    assert not cap.in_same_sentence("101 prestadores: con observaciones", 101, OBS)
    assert not cap.in_same_sentence("101 prestadores\n\ncon observaciones", 101, OBS)
    assert cap.in_same_sentence("101 prestadores\ncon observaciones", 101, OBS)
    assert cap.in_same_sentence("1.004.982 titulos", 1004982, ("titulo",))  # thousands dots do not end a sentence


def test_total_row_whose_caption_lacks_the_keyword_is_not_accepted():
    pdf = doc(p8_lines=p8(caption="Tabla 7. Distribucion al 30 de junio de 2026, segun region y tipo de prestador"))
    res = cap.parse_boletin_pdf(pdf, M, [1, 2, 7, 8], "acreditacion")
    assert res["status"] == "verified_figure_missing" and res["verified_present"]["pending_applications"] is False
    # The keyword in prose far above another table's heading does not count: only the nearest heading is read.
    text = "\n".join(["Solicitudes en tramitacion", "Otra tabla 1 2", "Distribucion por region",
                      "Region Privado Publico Total general", "Norte 367 217 584", "Total general 367 217 584"])
    assert cap.total_row_match(text, 584, TRA) is None


def test_number_on_an_uncited_page_is_not_accepted():
    res = cap.parse_boletin_pdf(doc(), M, [1, 7], "acreditacion")  # p.2 and p.8 not cited
    assert res["status"] == "verified_figure_missing"
    assert res["verified_present"] == {"with_observations": False, "pending_applications": False}
    assert res["figure_rules"] == {"with_observations": None, "pending_applications": None}


def test_total_row_whose_sum_does_not_match_is_not_accepted():
    pdf = doc(p8_lines=p8(total="Total general 367 216 584"))
    res = cap.parse_boletin_pdf(pdf, M, [1, 2, 7, 8], "acreditacion")
    assert res["status"] == "verified_figure_missing" and res["figure_rules"]["pending_applications"] is None
    # A table cell never passes by the sentence rule, even with the caption in the same 'sentence'.
    assert not cap.in_same_sentence("solicitudes en tramitacion\nTotal general 367 216 584", 584, TRA)
    # Rows with 1-2 cells: the structure allows no sum check ('not_applicable'); the caption is still required.
    assert cap.total_row_match("Solicitudes en tramitacion\nRegion Total\nNorte 584\nTotal 584", 584, TRA)["sum_check"] \
        == "not_applicable"


# --- re-check on a checker version bump -------------------------------------------------------------------------

def _store(r: Path) -> dict:
    return json.loads((r / STORE).read_text(encoding="utf-8"))


def _acr(r: Path) -> dict:
    return next(d for rel in _store(r)["releases"] for d in rel["documents"] if d["url"] == ACR)


def _root_captured_with_v1(tmp_path, monkeypatch):
    """Capture everything with the pre-bump checker (acreditación at v1): reproduces today's HOLD."""
    r = fx.make_root(tmp_path / "r")
    fetch = fx.fetcher(r, {ACR: doc()})
    monkeypatch.setattr(cap, "CHECKER_VERSIONS", {})
    fx.capture_all(r, fetch)
    monkeypatch.setattr(cap, "CHECKER_VERSIONS", {"acreditacion": 2})
    d = _acr(r)
    assert d["status"] == "captured" and d["parse"]["checker_version"] == 1
    assert d["parse"]["verified_present"] == {"accredited_providers": True, "with_observations": False,
                                              "pending_applications": False, "private_pending": True, "public_pending": True}
    pkg = f6.build_package(r, sf.load_registry())
    assert "2026-06:verified_figure_not_in_document:acreditacion:with_observations,pending_applications" \
        in pkg["reconciliation"]["failures"]
    return r, fetch


def test_version_bump_rechecks_the_captured_document_once_and_lifts_the_hold(tmp_path, monkeypatch):
    r, fetch = _root_captured_with_v1(tmp_path, monkeypatch)
    sha, fetched_at = _acr(r)["sha256"], _acr(r)["fetched_at"]
    before = list(fetch.calls)
    cap.capture(r, fetch=fetch)
    assert fetch.calls[len(before):] == [ACR]  # only the bumped topic's verified document is downloaded again
    d = _acr(r)
    assert d["status"] == "captured" and d["sha256"] == sha and d["fetched_at"] == fetched_at
    assert d["parse"]["checker_version"] == 2 and d["parse"]["status"] == "verified"
    assert d["rechecked_from_checker_version"] == 1 and d["rechecked_at"]
    assert d["parse"]["figure_rules"]["with_observations"]["rule"] == "sentence"
    assert d["parse"]["figure_rules"]["pending_applications"]["rule"] == "total_row"
    pkg = f6.build_package(r, sf.load_registry())
    assert pkg["releases_state"]["2026-06"] == ["ok"]
    assert not any("acreditacion" in f for f in pkg["reconciliation"]["failures"])
    # The other F6 checks still run on the re-checked figures (privadas + públicas = tramitación, etc.).
    assert "privadas_mas_publicas_distinto_de_tramite" not in pkg["reconciliation"]["failures"]
    n = len(fetch.calls)
    cap.capture(r, fetch=fetch)
    assert len(fetch.calls) == n  # up to date: never downloaded again


def test_recheck_uses_stored_bytes_without_downloading(tmp_path, monkeypatch):
    r, fetch = _root_captured_with_v1(tmp_path, monkeypatch)
    n = len(fetch.calls)
    cap.capture(r, fetch=fetch, stored=lambda d: doc() if d["url"] == ACR else None)
    assert len(fetch.calls) == n and _acr(r)["parse"]["status"] == "verified"


def test_recheck_with_sha_mismatch_holds(tmp_path, monkeypatch):
    r, fetch = _root_captured_with_v1(tmp_path, monkeypatch)
    sha = _acr(r)["sha256"]
    changed = fx.fetcher(r, {ACR: doc(p2=P2_OTHER_SENTENCE)})
    cap.capture(r, fetch=changed)
    d = _acr(r)
    assert d["status"] == "hash_mismatch" and d["sha256"] == sha and d["parse"]["checker_version"] == 1
    assert d["recheck"]["recorded_sha256"] == sha and d["recheck"]["fetched_sha256"] != sha
    pkg = f6.build_package(r, sf.load_registry())
    assert "2026-06:sha256_mismatch_on_recheck:acreditacion" in pkg["reconciliation"]["failures"]
    assert not pkg["reconciliation"]["ok"]
    cap.capture(r, fetch=changed)
    assert changed.calls.count(ACR) == 1  # HOLD: not re-captured automatically


def test_recheck_fetch_failure_keeps_the_record_and_retries(tmp_path, monkeypatch):
    r, _ = _root_captured_with_v1(tmp_path, monkeypatch)
    old = _acr(r)
    down = fx.fetcher(r, fail={ACR})
    for _ in range(cap.MAX_ATTEMPTS + 2):
        cap.capture(r, fetch=down)
    assert down.calls.count(ACR) == cap.MAX_ATTEMPTS  # then weekly, like a first capture
    d = _acr(r)
    assert d["status"] == "captured" and d["parse"] == old["parse"] and d["recheck"]["status"] == "fetch_failed"


def test_recheck_goes_through_the_sis_fetcher_limits(tmp_path, monkeypatch):
    """No special path: the default fetch is SisFetcher (allowlist, robots, byte cap, deadline)."""
    r, _ = _root_captured_with_v1(tmp_path, monkeypatch)
    seen = []

    class Guard(cap.SisFetcher):
        def __call__(self, url):
            seen.append(url)
            raise PermissionError("robots_disallowed: test")
    monkeypatch.setattr(cap, "SisFetcher", Guard)
    cap.capture(r)
    assert seen == [ACR] and _acr(r)["recheck"]["error"].startswith("PermissionError:robots_disallowed")
