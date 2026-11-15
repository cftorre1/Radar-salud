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
                       call=_call([GOOD, {"verdict": "PASS"}], calls))
    assert stats["written"] == 1 and calls == [ci.DRAFT_FEATURE, ci.REVIEW_FEATURE]
    assert all("tramitacion.senado.cl" in u for u in urls)
    again = ci.refresh(tmp_path, [ROW], today=date(2026, 11, 15), fetch=_fetch(urls), call=_call([], calls))
    assert again["candidates"] == 0 and len(calls) == 2  # paid once
    card = cg.with_report_summary(ROW, tmp_path)
    assert card["key_facts"][1].startswith("El informe dice que la comisión aprobó en general el proyecto")
    assert card["key_facts"][0].startswith("Trámite oficial") and card["key_facts"][2].startswith("Etapa actual")


def test_failed_review_or_verification_publishes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "_pdf_text", lambda data: REPORT)
    calls = []
    ci.refresh(tmp_path, [ROW], today=date(2026, 11, 15), fetch=_fetch([]),
               call=_call([GOOD, {"verdict": "FAIL", "reason": "exagera"}], calls))
    assert cg.with_report_summary(ROW, tmp_path) == ROW
    rec = json.loads((tmp_path / ci.CACHE_DIR / "18255-31_2026-11-11.json").read_text(encoding="utf-8"))
    assert rec["summary"]["status"] == "fail" and rec["summary"]["problems"] == ["independent_review:exagera"]


def test_no_link_yet_is_retried_and_other_milestones_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "_pdf_text", lambda data: REPORT)
    early = {**ROW, "event_date": "2026-11-12"}
    stats = ci.refresh(tmp_path, [early, {**ROW, "bill_milestone": "ingreso"}], today=date(2026, 11, 15),
                       fetch=_fetch([]), call=_call([], []))
    assert stats == {"candidates": 1, "no_link_yet": 1, "written": 0, "failed": 0, "errors": 0}
    assert not (tmp_path / ci.CACHE_DIR).exists()
