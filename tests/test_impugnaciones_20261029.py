"""Impugnaciones per circular (Dirección 29-oct-2026) and the judicial source registry.

Deterministic, offline: subjects are the regulator's listing text (tests/fixtures/sis), insurers
come only from config/entities.json and only when the subject names them as filers.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from radar_salud import regulatory
from radar_salud.normative_relations import (apply_backlinks, challenge_entry, challenge_petitioners,
                                             challenge_summary, extract_relations)

SIS = "Superintendencia de Salud"
FIX = Path(__file__).parent / "fixtures" / "sis"
BASE = "https://www.superdesalud.gob.cl/normativa/"
# IF/5382: the repository keeps only the listing wording quoted in normative_relations.py
# ("Acoge la suspensión de la Circular IF/N°521"); its full subject is not captured.
IF5382 = "Acoge la suspensión de la Circular IF/N°521."


def _circular(n):
    return {"title": f"Circular IF/N°{n}", "source_name": SIS, "source_url": f"{BASE}circular-if-n{n}/",
            "event_date": "2026-05-26"}


def _act(number, subject, date="2026-10-01", url=None, source=SIS):
    title = f"Resolución Exenta IF/N°{number}"
    return {"title": title, "source_name": source, "event_date": date, "official_subject": subject,
            "source_url": url if url is not None else f"{BASE}resolucion-exenta-if-n{number}/",
            "normative_relations": extract_relations(subject, title, SIS)}


def _real_listing(monkeypatch):
    html = (FIX / "aseguradoras_resoluciones_20261028.html").read_text(encoding="utf-8")
    monkeypatch.setattr(regulatory, "fetch_html", lambda url: html)
    scout = regulatory.SuperintendenciaNormativaScout()
    monkeypatch.setattr(scout, "PAGES", [("Para ISAPREs y FONASA", "https://www.superdesalud.gob.cl/x/", "Isapres / Fonasa")])
    return {i.title: i for i in scout.discover()}


def _by_title(rows):
    return {r["title"]: r for r in rows}


def test_real_resolutions_build_impugnaciones(monkeypatch):
    items = _real_listing(monkeypatch)
    acts = [_act(t.rsplit("°", 1)[1], items[t].raw_text, items[t].event_date)
            for t in ("Resolución Exenta IF/N°8760", "Resolución Exenta IF/N°9994", "Resolución Exenta IF/N°11156")]
    acts.append(_act("5382", IF5382, "2026-04-10"))
    out = _by_title(apply_backlinks([_circular(n) for n in (521, 528, 529, 532)] + acts))

    c528 = out["Circular IF/N°528"]["normative_challenges"]
    assert len(c528) == 1 and c528[0]["filing"] == "reposición" and c528[0]["outcome"] == "acoge parcialmente"
    assert [p["name"] for p in c528[0]["petitioners"]] == [
        "Isapre Banmédica", "Isapre Vida Tres", "Isapre Colmena", "Isapre Cruz Blanca", "Isapre Nueva Masvida",
        "Isapre Esencial"]
    assert c528[0]["resolution_id"] == "Resolución Exenta IF/N°11156" and c528[0]["date"] == "2026-09-23"
    assert c528[0]["url"] == f"{BASE}resolucion-exenta-if-n11156/"

    c532 = out["Circular IF/N°532"]["normative_challenges"][0]
    assert (c532["filing"], c532["outcome"], c532["accepted"]) == ("solicitud de suspensión", "rechaza", False)
    assert [p["id"] for p in c532["petitioners"]] == ["cl:isapre:108"]  # "efectuada por la Isapre Esencial S.A."

    c529 = out["Circular IF/N°529"]["normative_challenges"][0]
    assert (c529["filing"], c529["outcome"], c529["accepted"]) == ("solicitud de suspensión", "ha lugar", True)
    assert c529["petitioners"] == [] and c529["petitioner_basis"] == "not_identified"

    c521 = out["Circular IF/N°521"]["normative_challenges"][0]
    assert (c521["outcome"], c521["petitioners"], c521["resolution_id"]) == ("acoge", [], "Resolución Exenta IF/N°5382")
    assert out["Circular IF/N°532"]["normative_challenge_summary"] == "1 impugnación · 0 acogidas"
    assert out["Circular IF/N°528"]["normative_challenge_summary"] == "1 impugnación · 1 acogida"


def test_counts_and_newest_first_and_one_entry_per_resolution():
    c = _circular(534)
    a = _act("1", "Rechaza la solicitud de suspensión de los efectos de la Circular IF/N°534, efectuada por la Isapre Colmena.", "2026-10-01")
    b = _act("2", "Acoge parcialmente los recursos de reposición interpuestos por Isapre Consalud S.A. en contra de la Circular IF/N°534.", "2026-10-20")
    d = _act("3", "Rechaza los recursos jerárquicos interpuestos por Isapre Cruz Blanca S.A. en contra de la Circular IF/N°534.", "2026-10-25")
    dup = dict(b, title="Isapres: titular editorial · IF/N°2")  # same act as feed card and history record
    out = _by_title(apply_backlinks([c, a, b, d, dup]))["Circular IF/N°534"]
    assert [x["resolution_id"] for x in out["normative_challenges"]] == [
        "Resolución Exenta IF/N°3", "Resolución Exenta IF/N°2", "Resolución Exenta IF/N°1"]
    assert [x["filing"] for x in out["normative_challenges"]] == ["jerárquico", "reposición", "solicitud de suspensión"]
    assert out["normative_challenge_summary"] == "3 impugnaciones · 1 acogida"
    assert challenge_summary([]) == ""


@pytest.mark.parametrize("subject,outcome,accepted", [
    ("No ha lugar a la suspensión de los efectos de la Circular IF/N°530, de fecha 24 de julio de 2026.", "no ha lugar", False),
    ("Ha lugar, en parte, a lo solicitado de suspender los efectos de la Circular IF/N°530.", "ha lugar en parte", True),
    ("Rechaza recursos de reposición contra la Circular IF/N°530", "rechaza", False),
])
def test_outcome_verbs_and_negation(subject, outcome, accepted):
    out = _by_title(apply_backlinks([_circular(530), _act("9", subject)]))["Circular IF/N°530"]
    assert (out["normative_challenges"][0]["outcome"], out["normative_challenges"][0]["accepted"]) == (outcome, accepted)


@pytest.mark.parametrize("subject", [
    "No acoge la suspensión de la Circular IF/N°530.",
    "No suspende los efectos de la Circular IF/N°530.",
    "Acoge desistimiento de Isapre Colmena de solicitud de suspender los efectos de la Circular IF/N°530.",
    # A suspension with no stated request is never presented as a decided impugnación.
    "Suspende los efectos de la Circular IF/N°530 hasta resolver los recursos de reposición.",
])
def test_no_impugnacion_without_an_explicit_decision(subject):
    out = _by_title(apply_backlinks([_circular(530), _act("9", subject)]))["Circular IF/N°530"]
    assert "normative_challenges" not in out and "normative_challenge_summary" not in out


@pytest.mark.parametrize("subject", [
    "Rechaza recursos de reposición contra la Circular IF/N°531, que instruye a Isapre Colmena sobre bonos.",
    "Ha lugar a la suspensión de los efectos de la Circular IF/N°531, conforme a lo resuelto respecto de Isapre Consalud.",
    "Rechaza la solicitud de suspensión de los efectos de la Circular IF/N°531, no efectuada por Isapre Colmena.",
    "Acoge los recursos de reposición en contra de la Circular IF/N°531 sobre afiliados de Isapre Banmédica.",
])
def test_insurer_named_in_passing_does_not_count(subject):
    entry = _by_title(apply_backlinks([_circular(531), _act("9", subject)]))["Circular IF/N°531"]["normative_challenges"][0]
    assert entry["petitioners"] == [] and entry["petitioner_basis"] == "not_identified"


def test_petitioner_via_request_of_and_only_insurers():
    assert [p["name"] for p in challenge_petitioners(
        "Rechaza solicitud de Isapre Esencial S.A. de suspender los efectos de la Circular IF/N°534.")] == ["Isapre Esencial"]
    # Not an insurer in the catalog: never invented.
    assert challenge_petitioners("Rechaza la solicitud de suspensión efectuada por la Clínica Alemana.") == []


def test_only_sis_actors_https_links_and_instruction_targets():
    foreign = _act("9", "Rechaza recursos de reposición contra la Circular IF/N°530", source="Diario Financiero")
    out = _by_title(apply_backlinks([_circular(530), foreign]))["Circular IF/N°530"]
    assert "normative_challenges" not in out
    plain = _act("9", "Rechaza recursos de reposición contra la Circular IF/N°530", url="http://insecure.example/r9")
    entry = _by_title(apply_backlinks([_circular(530), plain]))["Circular IF/N°530"]["normative_challenges"][0]
    assert entry["url"] is None
    assert challenge_entry("modifica", {"title": "Resolución Exenta IF/N°1"}, "Modifica la Circular IF/N°1") is None


def test_exporter_carries_impugnaciones_to_the_circular_card():
    spec = importlib.util.spec_from_file_location("exporter_impug", Path("scripts/export_web_snapshot.py"))
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    c, a = _circular(532), _act("9994", "RECHAZA la solicitud de suspensión de los efectos de la Circular IF/Nº 532, "
                                         "de fecha 31 de julio de 2026, efectuada por la Isapre Esencial S.A.", "2026-08-26")
    out = _by_title(exporter._normative_status([c], [c, a]))["Circular IF/N°532"]
    assert out["normative_challenge_summary"] == "1 impugnación · 0 acogidas"
    assert out["normative_challenges"][0]["petitioners"][0]["name"] == "Isapre Esencial"
    # An instruction without decided challenges gets no empty block.
    assert "normative_challenges" not in exporter._normative_status([_circular(1)], [_circular(1)])[0]


def test_judicial_sources_registry_is_conservative():
    data = json.loads(Path("config/judicial_sources.json").read_text(encoding="utf-8"))
    required = {"id", "name", "status", "reason", "evidence_urls", "verified_at", "next_step", "reevaluate_after"}
    ids = [s["id"] for s in data["sources"]]
    assert len(ids) == len(set(ids))
    for s in data["sources"]:
        assert required <= set(s), s["id"]
        assert s["status"] in data["statuses"] and s["status"] != "enabled"
        assert s["live_search"] is False and s["scout_enabled"] is False
        assert all(u.startswith("https://") for u in s["evidence_urls"])
    assert {s["id"]: s["status"] for s in data["sources"]}["pjud_oficina_judicial_virtual"] == "rejected"
