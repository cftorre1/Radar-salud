"""«El informe dice que…» (Dirección 13-nov-2026): verified + reviewed summary of a committee report, paid once."""
import json
from datetime import date
from types import SimpleNamespace

from src.radar_salud import congreso_informe as ci
from src.radar_salud import congreso_sources as cg

XML = ("<proyectos><proyecto><informes>"
       "<informe><FECHAINFORME>21/07/2026</FECHAINFORME><TRAMITE>Primer informe de comisión de Salud </TRAMITE>"
       "<ETAPA>Primer trámite constitucional</ETAPA></informe>"
       "<informe><FECHAINFORME>11/11/2026</FECHAINFORME><TRAMITE>Primer informe de comisión de Familia, Infancia y "
       "Adolescencia </TRAMITE><ETAPA>Segundo trámite constitucional</ETAPA><LINK_INFORME>http://www.senado.cl/"
       "appsenado/index.php?mo=tramitacion&amp;ac=getDocto&amp;iddocto=28400&amp;tipodoc=info</LINK_INFORME></informe>"
       "</informes></proyecto></proyectos>").encode("utf-8")
REPORT = ("INFORME DE LA COMISIÓN DE FAMILIA, INFANCIA Y ADOLESCENCIA recaído en el proyecto de ley que establece un "
          "beneficio de compensación por la compra de pañales y de medicamentos. " * 8 +
          "La Comisión aprobó en general el proyecto por la unanimidad de sus 5 miembros presentes. "
          "Se acordó solicitar informe a la Dirección de Presupuestos antes de la discusión en particular.")
GOOD = {"dice": "la comisión aprobó en general el proyecto por la unanimidad de sus 5 miembros presentes y pidió un "
                "informe a la Dirección de Presupuestos antes de discutirlo en particular",
        "quotes": ["La Comisión aprobó en general el proyecto por la unanimidad de sus 5 miembros presentes.",
                   "Se acordó solicitar informe a la Dirección de Presupuestos antes de la discusión en particular."]}
ROW = {"bill_boletin": "18255-31", "bill_milestone": "informe_comision", "event_date": "2026-11-11",
       "bill_title": "Establece un beneficio de compensación por la compra de pañales y de medicamentos",
       "what_happened": "La comisión de Familia, Infancia y Adolescencia emitió informe sobre el proyecto «…» "
                        "(Boletín N° 18255-31) el 11 de noviembre de 2026, en el Senado.",
       "key_facts": ["Trámite oficial: «Primer informe de comisión de Familia, Infancia y Adolescencia».",
                     "Etapa actual: Segundo trámite constitucional (Senado)."]}


def _fetch(log):
    def fetch(url, accept):
        log.append(url)
        return XML if "wspublico" in url else b"%PDF-fake"
    return fetch


def _call(outputs, log):
    it = iter(outputs)
    def call(prompt, *, feature, preferred_model, allow_luna_fallback=True):
        log.append(feature)
        return SimpleNamespace(output=next(it), estimated_cost_usd=0.01)
    return call


def test_parse_and_match_use_the_open_tramitacion_host():
    infs = ci.parse_informes(XML)
    assert infs[0]["url"] is None and infs[0]["date"] == "2026-07-21"
    hit = ci.match_informe(infs, "2026-11-11", "Primer informe de comisión de Familia, Infancia y Adolescencia")
    assert hit["url"] == ("https://tramitacion.senado.cl/appsenado/index.php?mo=tramitacion&ac=getDocto&iddocto=28400"
                          "&tipodoc=info")
    assert ci.match_informe(infs, "2026-11-12", "Primer informe de comisión de Familia") is None


def test_verify_rejects_invented_numbers_quotes_and_opinions():
    assert ci.verify(GOOD, REPORT) == []
    bad = {**GOOD, "dice": GOOD["dice"].replace("5 miembros", "7 miembros") + "; probablemente se aprobará"}
    assert {"number_not_in_report:7", "opinion_or_guess"} <= set(ci.verify(bad, REPORT))
    assert "quote_not_literal" in ci.verify({**GOOD, "quotes": [GOOD["quotes"][0], "La Comisión rechazó todo el proyecto."]}, REPORT)


def test_refresh_drafts_reviews_caches_and_never_pays_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "_pdf_text", lambda data: REPORT)
    urls, calls = [], []
    stats = ci.refresh(tmp_path, [ROW], today=date(2026, 11, 15), fetch=_fetch(urls),
                       call=_call([GOOD, {"verdict": "PASS"}], calls), robots=lambda u: True)
    assert stats["written"] == 1 and calls == [ci.DRAFT_FEATURE, ci.REVIEW_FEATURE]
    assert all("tramitacion.senado.cl" in u for u in urls)
    again = ci.refresh(tmp_path, [ROW], today=date(2026, 11, 15), fetch=_fetch(urls), call=_call([], calls),
                       robots=lambda u: True)
    assert again["candidates"] == 0 and len(calls) == 2  # paid once
    card = cg.with_report_summary(ROW, tmp_path)
    assert card["key_facts"][1].startswith("El informe dice que la comisión aprobó en general el proyecto")
    assert card["key_facts"][0].startswith("Trámite oficial") and card["key_facts"][2].startswith("Etapa actual")
    link = card["source_alternatives"][-1]
    assert link["url"].startswith("https://tramitacion.senado.cl/") and link["title"] == "Informe de la comisión (PDF)"
    assert cg.with_report_summary(card, tmp_path) == card  # idempotent: no second line, no second link
    path = tmp_path / ci.CACHE_DIR / f"{ci.cache_key('18255-31', '2026-11-11', ci.official_tramite(ROW))}.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**rec, "url": "https://www.senado.cl/x?iddocto=1"}), encoding="utf-8")
    assert "source_alternatives" not in cg.with_report_summary(ROW, tmp_path)  # only the open tramitacion host (review of #210)


def test_failed_review_or_verification_publishes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "_pdf_text", lambda data: REPORT)
    calls = []
    ci.refresh(tmp_path, [ROW], today=date(2026, 11, 15), fetch=_fetch([]),
               call=_call([GOOD, {"verdict": "FAIL", "reason": "exagera"}], calls), robots=lambda u: True)
    assert cg.with_report_summary(ROW, tmp_path) == ROW
    path = tmp_path / ci.CACHE_DIR / f"{ci.cache_key('18255-31', '2026-11-11', ci.official_tramite(ROW))}.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["summary"]["status"] == "fail" and rec["summary"]["problems"] == ["independent_review:exagera"]


def test_no_link_yet_is_retried_and_other_milestones_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "_pdf_text", lambda data: REPORT)
    early = {**ROW, "event_date": "2026-11-12"}
    stats = ci.refresh(tmp_path, [early, {**ROW, "bill_milestone": "ingreso"}], today=date(2026, 11, 15),
                       fetch=_fetch([]), call=_call([], []), robots=lambda u: True)
    assert stats == {"candidates": 1, "no_link_yet": 1, "written": 0, "failed": 0, "errors": 0}
    last = json.loads((tmp_path / ci.CACHE_DIR / "_last_run.json").read_text(encoding="utf-8"))
    assert last["reasons"] == ["18255-31:no_link_yet"] and last["day"] == "2026-11-15"  # readable without Actions logs
    assert [p.name for p in (tmp_path / ci.CACHE_DIR).iterdir()] == ["_last_run.json"]  # no report cached


def test_other_committee_same_day_is_never_attached_and_lowercasing_keeps_proper_nouns():
    infs = ci.parse_informes(XML.replace(b"Familia, Infancia y \nAdolescencia", b"x"))
    assert ci.match_informe(infs, "2026-11-11", "Primer informe de comisión de Hacienda") is None
    assert ci.doc_url("https://evil.example/x?iddocto=1") is None
    assert ci.fact({"summary": {"dice": "FONASA deberá informar"}}) == "El informe dice que FONASA deberá informar."
    assert ci.fact({"summary": {"dice": "La comisión aprobó"}}) == "El informe dice que la comisión aprobó."
    assert ci.cache_key("1-1", "2026-11-11", "Primer informe de comisión de Salud") != \
        ci.cache_key("1-1", "2026-11-11", "Primer informe de comisión de Hacienda")


def test_model_error_after_billing_is_cached_as_final_and_counts_toward_the_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "_pdf_text", lambda data: REPORT)
    def boom(*a, **k):
        raise RuntimeError("model_call_failed:ValueError:not json")
    rows = [ROW, {**ROW, "bill_boletin": "18256-31"}]
    stats = ci.refresh(tmp_path, rows, today=date(2026, 11, 15), fetch=_fetch([]), call=boom, max_new=1,
                       robots=lambda u: True)
    assert stats["failed"] == 1 and stats["candidates"] == 1  # the cap stops after one paid attempt
    again = ci.refresh(tmp_path, [ROW], today=date(2026, 11, 15), fetch=_fetch([]), call=boom, robots=lambda u: True)
    assert again["candidates"] == 0  # never paid twice


def test_robots_disallow_fetches_nothing(tmp_path):
    urls = []
    stats = ci.refresh(tmp_path, [ROW], today=date(2026, 11, 15), fetch=_fetch(urls), call=_call([], []),
                       robots=lambda u: False)
    assert urls == [] and stats["errors"] == 1
    assert json.loads((tmp_path / ci.CACHE_DIR / "_last_run.json").read_text(encoding="utf-8"))["reasons"] == ["18255-31:robots_ws"]
