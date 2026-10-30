"""F6 (Boletín IP) acreditación, checker version 2: per-figure anchored templates (Dirección 2026-10-29/30).

A verified figure counts as present on a cited page when EITHER holds:
- context window (v1, unchanged): a metric keyword within 80 characters;
- template (v2): the metric's template in ``config/stats_fichas_v1.json`` (families.F6.figure_templates.acreditacion)
  matches the normalized text of the cited pages exactly once, captures the verified figure, passes its sum / part
  checks, and carries ``reviewed_by`` + ``reviewed_at`` from a human (placeholder '<<…>>' or 'pendiente' → HOLD).
The repo templates were filled from the real PDF text and approved by Dirección (cftorre1) on 2026-10-30.

Positive fixtures are the REAL normalized text of pp. 2, 7 and 8 of boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf
(sha256 8b7f7c7a385e…), as emitted by the CI real-PDF test (``tests/fixtures/f6_acreditacion_real_text.json``); the
fixture PDF carries that text, so the 80-char window misses 101 (p.2) and 584 (p.7, p.8) exactly as on the real file.
Placeholder / unreviewed cases run on copies of the config. Review probes: ``test_stats_fichas_f6_review_probes.py``.
No network.
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
REAL = json.loads((fx.REPO / "tests/fixtures/f6_acreditacion_real_text.json").read_text(encoding="utf-8"))
REAL_PAGES = {int(k): v for k, v in REAL["pages"].items()}
M = {"with_observations": 101, "pending_applications": 584, "private_pending": 367, "public_pending": 217}
OBS = cap.METRIC_CONTEXT["with_observations"]
TRA = cap.METRIC_CONTEXT["pending_applications"]
CITED = [1, 2, 7, 8]
REPO_TEMPLATES = cap.figure_templates(fx.REPO, "acreditacion")
TITLE_P8 = ("numero de solicitudes de acreditacion que estan en tramitacion, al 30 de junio de 2026, desagregadas por "
            "region del prestador y tipo")
SENTENCE_P2 = "101 prestadores institucionales obtuvieron el resultado de acreditado con observaciones"


def placeholder_copy() -> dict:
    """A config copy as before Dirección's review: p.8 anchored to a placeholder caption, both 'pendiente'."""
    t = copy.deepcopy(REPO_TEMPLATES)
    t["pending_applications"]["caption"] = "<<CAPTION_P8>>"
    t["pending_applications"]["pattern"] = r"{caption}(?:(?!total general \d).)*?\btotal general (\d+) (\d+) (\d+)(?![\d])"
    for v in t.values():
        v.update(reviewed_by="pendiente", reviewed_at=None)
    return t


def review_copy(by, at) -> dict:
    t = copy.deepcopy(REPO_TEMPLATES)
    for v in t.values():
        v.update(reviewed_by=by, reviewed_at=at)
    return t


@pytest.fixture(autouse=True)
def isolated_ledgers(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_ROOT", str(tmp_path / "ledger-root"))


def lines(text: str, width: int = 95) -> list[str]:
    """Wrap normalized text into PDF lines at spaces (normalization joins them back with single spaces)."""
    out, cur = [], ""
    for w in text.split(" "):
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    return out + ([cur] if cur else [])


def doc(p2=None, p7=None, p8=None, p1_extra=()) -> bytes:
    """Fixture PDF: p.1 cover, pp. 2, 7, 8 = the real normalized text (or a variant), other pages a page number."""
    pages = [["Boletin Estadistico Informativo IP N 2 2026", *p1_extra], lines(p2 or REAL_PAGES[2]),
             ["Pagina 3"], ["Pagina 4"], ["Pagina 5"], ["Pagina 6"], lines(p7 or REAL_PAGES[7]), lines(p8 or REAL_PAGES[8])]
    return fx.pdf_with_text([], pages=pages)


def variant(page: int, old: str, new: str) -> str:
    assert REAL_PAGES[page].count(old) == 1, old
    return REAL_PAGES[page].replace(old, new)


def text_of(pdf: bytes, page: int) -> str:
    return cap.pdf_pages(pdf)[page - 1]


def parse(pdf=None, templates=None, metrics=M, cited=CITED, topic="acreditacion"):
    return cap.parse_boletin_pdf(pdf or doc(), metrics, cited, topic, REPO_TEMPLATES if templates is None else templates)


def test_fixture_pdf_reproduces_the_real_normalized_text_and_the_window_miss():
    pdf = doc()
    for p in (2, 7, 8):
        assert cap.normalize_page(text_of(pdf, p)) == REAL_PAGES[p]
    assert not cap.present_in(text_of(pdf, 2), 101, OBS)
    assert not any(cap.present_in(text_of(pdf, p), 584, TRA) for p in (7, 8))
    res = parse(pdf, topic=None)  # checker v1: templates never used → the HOLD seen in production
    assert res["checker_version"] == 1 and res["status"] == "verified_figure_missing" and res["templates_sha256"] is None
    assert res["verified_present"]["with_observations"] is False and res["verified_present"]["pending_applications"] is False


def test_repo_templates_are_reviewed_and_verify_the_real_layout():
    assert all(v["reviewed_by"] == "Dirección (cftorre1)" and v["reviewed_at"] == "2026-10-30"
               for v in REPO_TEMPLATES.values())
    assert all(cap.template_pattern(v)[1] == "ok" for v in REPO_TEMPLATES.values())
    res = parse()
    assert res["checker_version"] == 2 and res["status"] == "verified", res.get("template_status")
    obs, tra = res["figure_rules"]["with_observations"], res["figure_rules"]["pending_applications"]
    assert obs["rule"] == "template" and obs["page"] == 2 and obs["match"] == SENTENCE_P2
    assert obs["reviewed_by"] == "Dirección (cftorre1)"
    assert tra["rule"] == "template" and tra["page"] == 8 and tra["sum_check"] == "367 + 217 = 584"
    assert tra["match"].startswith(TITLE_P8) and tra["match"].endswith("total general 367 217 584")
    assert tra["parts_equal"] == {"private_pending": 367, "public_pending": 217}
    assert "template_status" not in res and res["templates_sha256"] == cap.templates_sha256(REPO_TEMPLATES)
    # Directly on the real normalized pages: exactly one match each, on the cited pages only.
    for key, n, page in (("with_observations", 101, 2), ("pending_applications", 584, 8)):
        ev, why = cap.template_evidence([REAL_PAGES[2], REAL_PAGES[7], REAL_PAGES[8]], [1, 2, 3], n,
                                        REPO_TEMPLATES[key], M)
        assert why == "ok" and ev["page"] == {2: 1, 8: 3}[page]
    # The cut-off date in the p.8 title is variable (next bulletins), the rest of the title is literal.
    later = REAL_PAGES[8].replace("al 30 de junio de 2026, desagregadas", "al 30 de septiembre de 2026, desagregadas")
    assert cap.template_evidence([later], [1], 584, REPO_TEMPLATES["pending_applications"], M)[1] == "ok"


def test_placeholder_config_copy_holds():
    t = placeholder_copy()
    res = parse(templates=t)
    assert res["status"] == "verified_figure_missing"
    assert res["template_status"] == {"with_observations": "unreviewed", "pending_applications": "placeholder"}
    reviewed_placeholder = placeholder_copy()
    for v in reviewed_placeholder.values():
        v.update(reviewed_by="revisor", reviewed_at="2026-10-30")
    assert parse(templates=reviewed_placeholder)["template_status"] == {"pending_applications": "placeholder"}


@pytest.mark.parametrize("by,at", [("pendiente", "2026-10-30"), ("Dirección", None), ("", "2026-10-30"), (None, None),
                                   ("PENDIENTE ", "2026-10-30")])
def test_unreviewed_config_copies_hold(by, at):
    res = parse(templates=review_copy(by, at))
    assert res["status"] == "verified_figure_missing"
    assert set(res["template_status"].values()) == {"unreviewed"}


def test_template_matching_twice_holds():
    res = parse(doc(p1_extra=[SENTENCE_P2]))
    assert res["template_status"]["with_observations"] == "multiple_matches:2"
    # A second match on an uncited page does not count; a match only on an uncited page is no match.
    assert parse(doc(p1_extra=[SENTENCE_P2]), cited=[2, 7, 8])["figure_rules"]["with_observations"]["page"] == 2
    assert parse(cited=[1, 7, 8])["template_status"]["with_observations"] == "no_match"
    # The p.8 table repeated on a cited page → two matches → HOLD.
    twice = REAL_PAGES[8] + " " + REAL_PAGES[8]
    assert parse(doc(p8=twice))["template_status"]["pending_applications"] == "multiple_matches:2"


def test_template_negative_cases_hold():
    # Other wording (the figure in another sentence) → no match.
    p2 = variant(2, "101 prestadores institucionales obtuvieron", "101 prestadores institucionales fueron evaluados. varios obtuvieron")
    assert parse(doc(p2=p2))["template_status"]["with_observations"] == "no_match"
    # Title of the table differs → no match.
    p8 = variant(8, "desagregadas por region del prestador y tipo", "desagregadas por tipo")
    assert parse(doc(p8=p8))["template_status"]["pending_applications"] == "no_match"
    # Total row whose sum does not match.
    p8 = variant(8, "total general 367 217 584", "total general 367 216 584")
    assert parse(doc(p8=p8))["template_status"]["pending_applications"] == "sum_mismatch"
    # Parts that add up but differ from the separately verified private / public figures.
    res = parse(metrics={**M, "private_pending": 366, "public_pending": 218})
    assert res["template_status"]["pending_applications"] == "part_mismatch:private_pending"
    # Captured figure differs from the independent reading.
    assert parse(metrics={**M, "with_observations": 102})["template_status"]["with_observations"] == "figure_mismatch"
    # The first 'total general <n>' after the title is the anchored one: another row in between → mismatch.
    p8 = variant(8, "desagregadas por region del prestador y tipo", "desagregadas por region del prestador y tipo total general 1 2 3")
    assert parse(doc(p8=p8))["template_status"]["pending_applications"] == "figure_mismatch"
    # Title after the Total row anchors nothing.
    p8 = variant(8, TITLE_P8, "titulo movido") + " " + "relleno " * 15 + TITLE_P8
    assert parse(doc(p8=p8))["template_status"]["pending_applications"] == "no_match"
    # Uncited p.8.
    assert parse(cited=[1, 2, 7])["template_status"]["pending_applications"] == "no_match"


def test_invalid_templates_hold():
    t = copy.deepcopy(REPO_TEMPLATES)
    t["with_observations"]["pattern"] = "<<WORDING>> (\\d+)"
    t["pending_applications"]["groups"] = 2
    assert parse(templates=t)["template_status"] == {"with_observations": "placeholder", "pending_applications": "invalid"}
    assert parse(templates={})["template_status"] == {"with_observations": "not_configured",
                                                      "pending_applications": "not_configured"}


def test_normalization():
    assert cap.normalize_page("Títulos:  1.004.982\n\tÉXITO  ") == "titulos: 1004982 exito"
    assert cap.normalize_page("v 2.0 y 12.5%") == "v 2.0 y 12.5%"
    assert all(cap.normalize_page(t) == t for t in REAL_PAGES.values())  # the fixture is already normalized


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
    """Capture everything with the pre-bump checker (acreditación at v1): reproduces the production HOLD."""
    r = fx.make_root(tmp_path / "r")
    _write_templates(r, REPO_TEMPLATES if templates is None else templates)
    fetch = fx.fetcher(r, {ACR: doc()})
    monkeypatch.setattr(cap, "CHECKER_VERSIONS", {})
    fx.capture_all(r, fetch)
    monkeypatch.setattr(cap, "CHECKER_VERSIONS", {"acreditacion": 2})
    d = _acr(r)
    assert d["status"] == "captured" and d["parse"]["checker_version"] == 1
    assert d["parse"]["verified_present"]["with_observations"] is False
    assert d["parse"]["verified_present"]["pending_applications"] is False
    pkg = f6.build_package(r, sf.load_registry())
    assert any(f.startswith("2026-06:verified_figure_not_in_document:acreditacion:") and "with_observations" in f
               and "pending_applications" in f for f in pkg["reconciliation"]["failures"])
    return r, fetch


def _assert_f6_ok(r: Path) -> None:
    pkg = f6.build_package(r, sf.load_registry())
    assert pkg["releases_state"]["2026-06"] == ["ok"]
    assert not any("acreditacion" in f for f in pkg["reconciliation"]["failures"])
    # The other F6 checks still run on the figures (privadas + públicas = tramitación, etc.).
    assert "privadas_mas_publicas_distinto_de_tramite" not in pkg["reconciliation"]["failures"]
    assert "observaciones_sobre_acreditados" not in pkg["reconciliation"]["failures"]
    assert pkg["reconciliation"]["ok"] is True and pkg["reconciliation"]["failures"] == [], pkg["reconciliation"]


def test_version_bump_rechecks_once_and_the_reviewed_templates_lift_the_hold(tmp_path, monkeypatch):
    r, fetch = _root_captured_with_v1(tmp_path, monkeypatch)
    sha, fetched_at = _acr(r)["sha256"], _acr(r)["fetched_at"]
    before = list(fetch.calls)
    cap.capture(r, fetch=fetch)
    assert fetch.calls[len(before):] == [ACR]  # only the bumped topic's verified document is downloaded again
    d = _acr(r)
    assert d["status"] == "captured" and d["sha256"] == sha and d["fetched_at"] == fetched_at
    assert d["parse"]["checker_version"] == 2 and d["parse"]["status"] == "verified"
    assert d["parse"]["figure_rules"]["with_observations"]["rule"] == "template"
    assert d["parse"]["figure_rules"]["pending_applications"]["sum_check"] == "367 + 217 = 584"
    assert d["parse"]["templates_sha256"] == cap.templates_sha256(REPO_TEMPLATES)
    assert d["rechecked_from_checker_version"] == 1 and d["rechecked_at"]
    assert d["previous_parse"]["checker_version"] == 1 and d["previous_parse"]["status"] == "verified_figure_missing"
    _assert_f6_ok(r)
    n = len(fetch.calls)
    cap.capture(r, fetch=fetch)
    assert len(fetch.calls) == n  # same version, same templates: not downloaded again


def test_placeholder_templates_hold_then_the_review_triggers_one_recheck(tmp_path, monkeypatch):
    r, fetch = _root_captured_with_v1(tmp_path, monkeypatch, placeholder_copy())
    cap.capture(r, fetch=fetch)  # v2 with the placeholder copy: still HOLD
    d = _acr(r)
    assert d["parse"]["status"] == "verified_figure_missing"
    assert d["parse"]["template_status"] == {"with_observations": "unreviewed", "pending_applications": "placeholder"}
    pkg = f6.build_package(r, sf.load_registry())
    assert any("verified_figure_not_in_document:acreditacion" in f for f in pkg["reconciliation"]["failures"])
    n = len(fetch.calls)
    cap.capture(r, fetch=fetch)
    assert len(fetch.calls) == n  # unchanged templates: no download
    _write_templates(r, REPO_TEMPLATES)  # Dirección's review lands in the config
    cap.capture(r, fetch=fetch)
    assert fetch.calls[n:] == [ACR]  # template change → one re-check
    d = _acr(r)
    assert d["parse"]["status"] == "verified" and d["previous_parse"]["template_status"]["pending_applications"] == "placeholder"
    _assert_f6_ok(r)
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
    changed = fx.fetcher(r, {ACR: doc(p8=variant(8, "total general 367 217 584", "total general 367 216 584"))})
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
