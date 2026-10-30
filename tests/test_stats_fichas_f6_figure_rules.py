"""F6 (Boletín IP) acreditación, checker version 2: per-figure anchored templates (Dirección 2026-10-29).

A verified figure counts as present on a cited page when EITHER holds:
- context window (v1, unchanged): a metric keyword within 80 characters;
- template (v2): the metric's template in ``config/stats_fichas_v1.json`` (families.F6.figure_templates.acreditacion)
  matches the normalized text of the cited pages exactly once, captures the verified figure, passes its sum / part
  checks, and carries ``reviewed_by`` + ``reviewed_at`` from a human (placeholder '<<…>>' or 'pendiente' → HOLD).
No generic sentence or table heuristic exists any more. Review probes: ``test_stats_fichas_f6_review_probes.py``.

Synthetic text reproduces the two real layouts of boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf (sha256
8b7f7c7a385e…): 101 on p.2 broken by a line break 82 characters from 'observaciones', and 584 only in Total rows
(p.7, whose cells do not add up, and p.8 'Total general 367 217 584' under its caption). No network.
"""
import copy
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
M = {"with_observations": 101, "pending_applications": 584, "private_pending": 367, "public_pending": 217}
OBS = cap.METRIC_CONTEXT["with_observations"]
TRA = cap.METRIC_CONTEXT["pending_applications"]
CITED = [1, 2, 7, 8]
CAPTION = "Tabla 7. Solicitudes de acreditación en tramitación al 30 de junio de 2026, según región y tipo"
REPO_TEMPLATES = cap.figure_templates(fx.REPO, "acreditacion")


def filled(templates=None, caption=CAPTION, by="revisor de prueba", at="2026-10-29") -> dict:
    """The repo templates with the p.8 caption filled in and a (test) human review."""
    t = copy.deepcopy(templates or REPO_TEMPLATES)
    t["pending_applications"]["caption"] = caption
    for v in t.values():
        v.update(reviewed_by=by, reviewed_at=at)
    return t


@pytest.fixture(autouse=True)
def isolated_ledgers(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_ROOT", str(tmp_path / "ledger-root"))


# p.2: real wording; the extraction's whitespace around the line break puts 'observaciones' 82 characters away.
P2 = ["Resultados del proceso de acreditacion",
      "Del conjunto de prestadores acreditados al 30 de junio, 101 prestadores institucionales     ",
      "      obtuvieron el resultado de acreditado con observaciones en su ultimo proceso."]
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


def p8(caption=CAPTION, total="Total general 367 217 584") -> list[str]:
    """Caption far (> 80 chars) from the Total row; rows by region; 'Total general 367 217 584'."""
    return [caption, "Region Privado Publico Total general",
            *(f"{r} {a} {b} {a + b}" for r, a, b in zip(REGIONS, PRIV, PUB)), total]


def doc(p2=None, p7_lines=None, p8_lines=None, p1_extra=()) -> bytes:
    pages = [["Boletin Estadistico Informativo IP N 2 2026",
              "Al 30 de junio de 2026 hay 971 prestadores institucionales acreditados.",
              "De las solicitudes en tramite, 367 corresponden a prestadores privados y 217 a prestadores publicos.",
              *p1_extra],
             p2 or P2, ["Pagina 3"], ["Pagina 4"], ["Pagina 5"], ["Pagina 6"], p7_lines or p7(), p8_lines or p8()]
    return fx.pdf_with_text([], pages=pages)


def text_of(pdf: bytes, page: int) -> str:
    return cap.pdf_pages(pdf)[page - 1]


def parse(pdf=None, templates=None, metrics=M, cited=CITED, topic="acreditacion"):
    return cap.parse_boletin_pdf(pdf or doc(), metrics, cited, topic, templates)


def test_synthetic_layouts_fail_the_80_char_window_like_the_real_pdf():
    pdf = doc()
    folded = cap._fold(text_of(pdf, 2))
    assert folded.index("observacion") - (folded.index("101") + 3) == 82  # as in the real p.2
    assert not cap.present_in(text_of(pdf, 2), 101, OBS)
    assert not any(cap.present_in(text_of(pdf, p), 584, TRA) for p in (7, 8))
    res = parse(pdf, filled(), topic=None)  # checker v1: templates never used → today's HOLD
    assert res["checker_version"] == 1 and res["status"] == "verified_figure_missing" and res["templates_sha256"] is None
    assert res["verified_present"]["with_observations"] is False and res["verified_present"]["pending_applications"] is False


def test_repo_templates_are_placeholder_or_unreviewed_so_f6_holds():
    t = REPO_TEMPLATES
    assert t["pending_applications"]["caption"] == "<<CAPTION_P8>>"
    assert all(v["reviewed_by"] == "pendiente" and not v["reviewed_at"] for v in t.values())
    res = parse(templates=t)
    assert res["status"] == "verified_figure_missing"
    assert res["template_status"] == {"with_observations": "unreviewed", "pending_applications": "placeholder"}
    # Even reviewed, a placeholder caption is 'not configured'.
    t2 = filled(caption="<<CAPTION_P8>>")
    assert parse(templates=t2)["template_status"] == {"pending_applications": "placeholder"}


def test_filled_and_reviewed_templates_pass_the_real_layouts():
    res = parse(templates=filled())
    assert res["checker_version"] == 2 and res["status"] == "verified", res.get("template_status")
    obs, tra = res["figure_rules"]["with_observations"], res["figure_rules"]["pending_applications"]
    assert obs["rule"] == "template" and obs["page"] == 2 and obs["reviewed_by"] == "revisor de prueba"
    assert obs["match"] == "101 prestadores institucionales obtuvieron el resultado de acreditado con observaciones"
    assert tra["rule"] == "template" and tra["page"] == 8 and tra["sum_check"] == "367 + 217 = 584"
    assert tra["parts_equal"] == {"private_pending": 367, "public_pending": 217}
    assert res["figure_rules"]["private_pending"]["rule"] == "context_window"  # the window is unchanged
    assert res["templates_sha256"] == cap.templates_sha256(filled())


@pytest.mark.parametrize("by,at", [("pendiente", "2026-10-29"), ("revisor", None), ("", "2026-10-29"), (None, None)])
def test_unreviewed_templates_hold(by, at):
    res = parse(templates=filled(by=by, at=at))
    assert res["status"] == "verified_figure_missing"
    assert set(res["template_status"].values()) == {"unreviewed"}


def test_template_matching_twice_holds():
    dup = ["101 prestadores institucionales obtuvieron el resultado de acreditado con observaciones"]
    res = parse(doc(p1_extra=dup), filled())
    assert res["template_status"]["with_observations"] == "multiple_matches:2"
    # A second match on an uncited page does not count; a match only on an uncited page is no match.
    assert parse(doc(p1_extra=dup), filled(), cited=[2, 7, 8])["figure_rules"]["with_observations"]["page"] == 2
    assert parse(templates=filled(), cited=[1, 7, 8])["template_status"]["with_observations"] == "no_match"


def test_template_negative_cases_hold():
    # Different wording (other sentence) → no match.
    other = ["Del conjunto de prestadores acreditados al 30 de junio, 101 prestadores institucionales fueron evaluados.",
             "Varios obtuvieron el resultado de acreditado con observaciones."]
    assert parse(doc(p2=other), filled())["template_status"]["with_observations"] == "no_match"
    # Caption differs from the configured one → no match.
    res = parse(doc(p8_lines=p8(caption="Tabla 7. Distribucion al 30 de junio de 2026, segun region y tipo")), filled())
    assert res["template_status"]["pending_applications"] == "no_match"
    # Total row whose sum does not match.
    res = parse(doc(p8_lines=p8(total="Total general 367 216 584")), filled())
    assert res["template_status"]["pending_applications"] == "sum_mismatch"
    # Parts that add up but differ from the separately verified private / public figures.
    res = parse(templates=filled(), metrics={**M, "private_pending": 366, "public_pending": 218})
    assert res["template_status"]["pending_applications"] == "part_mismatch:private_pending"
    # Captured figure differs from the independent reading.
    res = parse(templates=filled(), metrics={**M, "with_observations": 102})
    assert res["template_status"]["with_observations"] == "figure_mismatch"
    # The first 'Total general' after the caption is the anchored one: another table's row in between → mismatch.
    lines = p8()
    lines.insert(1, "Total general 1 2 3")
    assert parse(doc(p8_lines=lines), filled())["template_status"]["pending_applications"] == "figure_mismatch"
    # A caption that comes after the Total row anchors nothing.
    assert parse(doc(p8_lines=p8()[1:] + ["relleno " * 15, CAPTION]), filled())["template_status"]["pending_applications"] == "no_match"


def test_invalid_templates_hold():
    t = filled()
    t["with_observations"]["pattern"] = "<<WORDING>> (\\d+)"
    t["pending_applications"]["groups"] = 2
    assert parse(templates=t)["template_status"] == {"with_observations": "placeholder", "pending_applications": "invalid"}
    assert parse(templates={})["template_status"] == {"with_observations": "not_configured",
                                                      "pending_applications": "not_configured"}


def test_normalization():
    assert cap.normalize_page("Títulos:  1.004.982\n\tÉXITO  ") == "titulos: 1004982 exito"
    assert cap.normalize_page("v 2.0 y 12.5%") == "v 2.0 y 12.5%"


# --- re-check on a checker version bump or a template change --------------------------------------------------

def _store(r: Path) -> dict:
    return json.loads((r / STORE).read_text(encoding="utf-8"))


def _acr(r: Path) -> dict:
    return next(d for rel in _store(r)["releases"] for d in rel["documents"] if d["url"] == ACR)


def _write_templates(r: Path, templates: dict) -> None:
    """The root's registry = the repo registry with these acreditación figure templates."""
    reg = sf.load_registry()
    reg["families"]["F6"]["figure_templates"]["acreditacion"] = templates
    (r / cap.REGISTRY).parent.mkdir(parents=True, exist_ok=True)
    (r / cap.REGISTRY).write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def _root_captured_with_v1(tmp_path, monkeypatch, templates=None):
    """Capture everything with the pre-bump checker (acreditación at v1): reproduces today's HOLD."""
    r = fx.make_root(tmp_path / "r")
    _write_templates(r, templates if templates is not None else REPO_TEMPLATES)
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


def test_version_bump_rechecks_once_and_repo_placeholder_templates_keep_the_hold(tmp_path, monkeypatch):
    r, fetch = _root_captured_with_v1(tmp_path, monkeypatch)
    sha, fetched_at = _acr(r)["sha256"], _acr(r)["fetched_at"]
    before = list(fetch.calls)
    cap.capture(r, fetch=fetch)
    assert fetch.calls[len(before):] == [ACR]  # only the bumped topic's verified document is downloaded again
    d = _acr(r)
    assert d["status"] == "captured" and d["sha256"] == sha and d["fetched_at"] == fetched_at
    assert d["parse"]["checker_version"] == 2 and d["parse"]["status"] == "verified_figure_missing"
    assert d["parse"]["template_status"] == {"with_observations": "unreviewed", "pending_applications": "placeholder"}
    assert d["parse"]["templates_sha256"] == cap.templates_sha256(REPO_TEMPLATES)
    assert d["rechecked_from_checker_version"] == 1 and d["rechecked_at"]
    assert d["previous_parse"]["checker_version"] == 1 and d["previous_parse"]["status"] == "verified_figure_missing"
    pkg = f6.build_package(r, sf.load_registry())
    assert "2026-06:verified_figure_not_in_document:acreditacion:with_observations,pending_applications" \
        in pkg["reconciliation"]["failures"]  # intentional HOLD until a human fills and reviews the templates
    n = len(fetch.calls)
    cap.capture(r, fetch=fetch)
    assert len(fetch.calls) == n  # same version, same templates: not downloaded again


def test_filling_and_reviewing_the_templates_triggers_one_recheck_and_lifts_the_hold(tmp_path, monkeypatch):
    r, fetch = _root_captured_with_v1(tmp_path, monkeypatch)
    cap.capture(r, fetch=fetch)  # v2 with placeholders: still HOLD
    _write_templates(r, filled())
    n = len(fetch.calls)
    cap.capture(r, fetch=fetch)
    assert fetch.calls[n:] == [ACR]  # template change → one re-check
    d = _acr(r)
    assert d["parse"]["status"] == "verified" and d["previous_parse"]["template_status"]["pending_applications"] == "placeholder"
    assert d["parse"]["figure_rules"]["pending_applications"]["sum_check"] == "367 + 217 = 584"
    pkg = f6.build_package(r, sf.load_registry())
    assert pkg["releases_state"]["2026-06"] == ["ok"]
    assert not any("acreditacion" in f for f in pkg["reconciliation"]["failures"])
    # The other F6 checks still run on the figures (privadas + públicas = tramitación, etc.).
    assert "privadas_mas_publicas_distinto_de_tramite" not in pkg["reconciliation"]["failures"]
    n = len(fetch.calls)
    cap.capture(r, fetch=fetch)
    assert len(fetch.calls) == n  # up to date: never downloaded again


def test_recheck_uses_stored_bytes_without_downloading(tmp_path, monkeypatch):
    r, fetch = _root_captured_with_v1(tmp_path, monkeypatch, filled())
    n = len(fetch.calls)
    cap.capture(r, fetch=fetch, stored=lambda d: doc() if d["url"] == ACR else None)
    assert len(fetch.calls) == n and _acr(r)["parse"]["status"] == "verified"


def test_recheck_with_sha_mismatch_holds(tmp_path, monkeypatch):
    r, fetch = _root_captured_with_v1(tmp_path, monkeypatch, filled())
    sha = _acr(r)["sha256"]
    changed = fx.fetcher(r, {ACR: doc(p8_lines=p8(total="Total general 367 216 584"))})
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
