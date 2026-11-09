"""Dirección 9-nov-2026 (punto B): every SIS normative listing, live only (14 days), no duplicates,
no internal administration. Listing structure as read by probe 42711886047."""
from datetime import date

import pytest

import scripts.export_web_snapshot as exporter
from radar_salud import regulatory
from radar_salud.regulatory import act_identity, listing_event_date

HEAD = "<table><tr><th>Fecha de publicación</th><th>Título</th><th>Resumen y modificaciones</th></tr>"
B = "https://www.superdesalud.gob.cl"


def row(pub, slug, title, subject):
    return (f'<tr><td>{pub}</td><td><a href="{B}/normativa/{slug}/">{title}</a> '
            f'<a href="{B}/app/uploads/2026/11/{slug}.pdf">Descargar pdf</a></td><td>{subject}</td></tr>')


ASEGURADORAS = HEAD + row("05/11/2026", "circular-if-n541-emision-5-11-2026", "Circular IF/N°541 - Emisión: 5/11/2026",
                          "Aclara la determinación de la base de cálculo del deducible de la CAEC.") + row(
    "23/10/2026", "resolucion-exenta-if-n12392-emision-23-10-2026", "Resolución Exenta IF/N°12392 - Emisión: 23/10/2026",
    "Resuelve recurso de reposición.") + "</table>"
MARCO_RES = HEAD + "".join([
    # Same act as in 'Para ISAPREs y FONASA' (other URL spelling): captured once.
    row("23/10/2026", "res-ex-if-12392", "Resolución Exenta IF/N° 12392", "Resuelve recurso de reposición."),
    # Internal administration: never captured.
    row("05/11/2026", "resolucion-exenta-n-1560-2026", "Resolución Exenta Nº 1560-2026",
        "DESIGNA MIEMBROS DE LA COMISIÓN EVALUADORA PARA EL PROCESO DE LICITACIÓN PÚBLICA ID 601-17-LE26"),
    # Live normative act only listed here: captured with its emission date.
    row("06/11/2026", "resolucion-exenta-ss-n-1580-emision-4-11-2026", "Resolución Exenta SS/N°1580 - Emisión: 4/11/2026",
        "Fija porcentaje máximo de ajuste que las instituciones de salud previsional deberán considerar en las adecuaciones."),
    # Older than 14 days: no backfill.
    row("07/03/2023", "resolucion-exenta-ss-n276", "Resolución Exenta SS N°276",
        "Fija porcentaje máximo de ajuste que las instituciones de salud previsional deberán considerar."),
]) + "</table>"
OTRAS = HEAD + row("02/11/2026", "resolucion-exenta-ss-n-1500", "Resolución Exenta SS/N° 1500",
                   "Indica Sujetos Pasivos de la Superintendencia de Salud de acuerdo a la Ley N°20.730 que regula el Lobby.") + "</table>"
DECRETOS = HEAD + row("03/11/2026", "decreto-exento-n-40", "Decreto Exento N° 40",
                      "Pone término al Decreto Ex. N° 31 y establece nuevo orden de subrogancia al cargo de Superintendente/a.") + "</table>"


def _scout(monkeypatch, extra=None):
    pages = {"https://www.superdesalud.gob.cl/robots.txt": "User-agent: *\nDisallow: /portal/w3-issues.html\n",
             "https://www.superdesalud.gob.cl/aseguradoras/": ASEGURADORAS,
             regulatory.SuperintendenciaNormativaScout.EXTRA_PAGES[0][1]: OTRAS,
             regulatory.SuperintendenciaNormativaScout.EXTRA_PAGES[1][1]: MARCO_RES,
             regulatory.SuperintendenciaNormativaScout.EXTRA_PAGES[2][1]: DECRETOS}
    pages.update(extra or {})
    monkeypatch.setattr(regulatory, "fetch_html", lambda url: pages[url])
    scout = regulatory.SuperintendenciaNormativaScout()
    monkeypatch.setattr(scout, "PAGES", [("Para ISAPREs y FONASA", "https://www.superdesalud.gob.cl/aseguradoras/", "Isapres / Fonasa")])
    scout.today = date(2026, 11, 9)
    return scout


def test_extra_listings_add_only_live_normative_acts_without_duplicates(monkeypatch):
    scout = _scout(monkeypatch)
    items = scout.discover()
    titles = [i.title for i in items]
    assert titles.count("Resolución Exenta IF/N°12392 - Emisión: 23/10/2026") == 1
    assert "Resolución Exenta IF/N° 12392" not in titles
    new = next(i for i in items if i.title.startswith("Resolución Exenta SS/N°1580"))
    assert new.event_date == "2026-11-04" and new.metadata["listing_date"] == "2026-11-06"
    assert new.metadata["listing_family"] == "otros_actos_o_marco_normativo"
    assert new.source_slug == "superintendencia_normativa"  # same downstream pipeline (minimal card + autorecord)
    for absent in ("1560-2026", "SS N°276", "SS/N° 1500", "Decreto Exento N° 40"):
        assert not any(absent in t for t in titles), absent
    assert scout.extra_skipped == {"already_listed": 1, "admin_noise": 3, "outside_live_window": 1}


def test_instrucciones_dictadas_keep_their_full_window(monkeypatch):
    items = _scout(monkeypatch).discover()
    # The daily listings are not cut to 14 days (their 30/90-day window applies downstream).
    assert any(i.title.startswith("Circular IF/N°541") for i in items)


def test_act_identity_normalises_spelling_and_keeps_the_year():
    assert act_identity("Resolución Exenta IF/N°12392 - Emisión: 23/10/2026", "2026") == act_identity("Resolución Exenta IF/N° 12392", "2026")
    assert act_identity("Circular IF/N°541", "2026") != act_identity("Circular IP N°541", "2026")
    assert act_identity("Oficio Circular IF/N° 20", "2026") == "oficio circular|if|20|2026"
    # SIS numbers restart every year: 2026's IF/N°12502 is not 2019's.
    assert act_identity("Resolución Exenta IF/N°12502", "2026") != act_identity("Resolución Exenta IF/N°12502", "2019")


def test_same_number_from_another_year_is_not_skipped(monkeypatch):
    old = HEAD + row("12/03/2019", "resolucion-exenta-if-n12502-2019", "Resolución Exenta IF/N°12502",
                     "Resuelve recurso de reposición.") + "</table>"
    new = HEAD + row("07/11/2026", "resolucion-exenta-if-n12502-emision-6-11-2026", "Resolución Exenta IF/N°12502 - Emisión: 6/11/2026",
                     "Instruye a las isapres sobre la contratación de planes de salud.") + "</table>"
    scout = _scout(monkeypatch, {"https://www.superdesalud.gob.cl/aseguradoras/": old,
                                 regulatory.SuperintendenciaNormativaScout.EXTRA_PAGES[0][1]: new})
    items = scout.discover()
    assert [i.event_date for i in items if "12502" in i.title] == ["2026-11-06", "2019-03-12"]


@pytest.mark.parametrize("subject", [
    "Instruye a las isapres sobre la contratación de planes de salud y sus beneficios.",
    "Imparte instrucciones sobre la compra de bonos electrónicos en farmacias.",
])
def test_regulation_mentioning_contratacion_or_compra_is_not_admin_noise(monkeypatch, subject):
    page = HEAD + row("07/11/2026", "resolucion-exenta-ss-n-1590", "Resolución Exenta SS/N°1590", subject) + "</table>"
    scout = _scout(monkeypatch, {regulatory.SuperintendenciaNormativaScout.EXTRA_PAGES[0][1]: page})
    assert any(i.title == "Resolución Exenta SS/N°1590" for i in scout.discover())


def test_live_cutoff_uses_listing_date_not_emission(monkeypatch):
    page = HEAD + row("08/11/2026", "resolucion-exenta-ss-n-1570-emision-20-10-2026", "Resolución Exenta SS/N°1570 - Emisión: 20/10/2026",
                      "Fija instrucciones generales a las isapres.") + "</table>"
    scout = _scout(monkeypatch, {regulatory.SuperintendenciaNormativaScout.EXTRA_PAGES[0][1]: page})
    item = next(i for i in scout.discover() if "1570" in i.title)
    assert item.event_date == "2026-10-20" and item.metadata["listing_date"] == "2026-11-08"


def test_emission_after_listing_is_clamped():
    assert listing_event_date("Circular IF/N°9 - Emisión: 9/11/2026", "", "05/11/2026 Circular IF/N°9") == "2026-11-05"


def test_new_listing_is_capped_newest_first(monkeypatch, capsys):
    rows = "".join(row(f"{d:02d}/11/2026", f"resolucion-exenta-ss-n-{2000 + n}", f"Resolución Exenta SS/N°{2000 + n}",
                       "Fija instrucciones generales a las isapres.") for n, d in enumerate([1, 2, 3, 4, 5, 6, 7, 8] * 3))
    scout = _scout(monkeypatch, {regulatory.SuperintendenciaNormativaScout.EXTRA_PAGES[0][1]: HEAD + rows + "</table>"})
    got = [i for i in scout.discover() if i.metadata["listing_name"] == "Otras resoluciones"]
    assert len(got) == 20 and scout.extra_skipped["cap_overflow"] == 4
    assert min(i.metadata["listing_date"] for i in got) == "2026-11-02"  # the four oldest wait for the next run
    assert "over the cap of 20" in capsys.readouterr().out


def test_robots_disallow_is_reported_not_zero(monkeypatch):
    scout = _scout(monkeypatch, {"https://www.superdesalud.gob.cl/robots.txt":
                                 "User-agent: *\nDisallow: /tax-marco-normativo/\n"})
    scout.discover()
    assert any("robots_disallowed" in e for e in scout.discovery_errors)


def test_same_act_in_two_listings_on_different_days_is_one_card():
    a = {"title": "Resolución Exenta SS/N°1580 - Emisión: 4/11/2026", "source_name": "Superintendencia de Salud",
         "source_url": "https://www.superdesalud.gob.cl/normativa/resolucion-exenta-ss-n-1580-emision-4-11-2026/",
         "event_date": "2026-11-04", "detected_at": "2026-11-06T06:00:00+00:00", "signal_types": ["Normativa"]}
    b = {**a, "title": "Resolución Exenta SS/N° 1580", "detected_at": "2026-11-07T06:00:00+00:00",
         "source_url": "https://www.superdesalud.gob.cl/normativa/resolucion-exenta-ss-n1580/"}
    merged = exporter._merge_duplicates([a, b])
    assert len(merged) == 1 and merged[0]["source_alternatives"][0]["url"] in (a["source_url"], b["source_url"])
    assert act_identity(a["title"], "2026") == act_identity(b["title"], "2026")


# Every type/prefix combination read in probe receipts 42710380828 and 42711886047.
@pytest.mark.parametrize("title,kind,label", [
    ("Circular IF/N°538 - Emisión: 26/10/2026", "Circular", "Circular IF/N°538"),
    ("Circular IP N°68", "Circular", "Circular IP/N°68"),
    ("Circular Interna IP /N° 8", "Circular Interna", "Circular Interna IP/N°8"),
    ("Oficio Circular IF/N° 20", "Oficio Circular", "Oficio Circular IF/N°20"),
    ("Oficio Circular IP/ N° 14", "Oficio Circular", "Oficio Circular IP/N°14"),
    ("Ordinario Circular IF/N° 82", "Ordinario Circular", "Ordinario Circular IF/N°82"),
    ("Ordinario Circular IP/ N° 2", "Ordinario Circular", "Ordinario Circular IP/N°2"),
    ("Oficio IF/N° 6355", "Oficio", "Oficio IF/N°6355"),
    ("Oficio N°1445 de 2023", "Oficio", "Oficio N°1445"),
    ("Resolución Exenta IF/N°12392 - Emisión: 23/10/2026", "Resolución Exenta", "Resolución Exenta IF/N°12392"),
    ("Resolución Exenta IP/N° 8337", "Resolución Exenta", "Resolución Exenta IP/N°8337"),
    ("Resolución Exenta SS/N° 618", "Resolución Exenta", "Resolución Exenta SS/N°618"),
    ("Resolución Exenta SS N°276", "Resolución Exenta", "Resolución Exenta SS/N°276"),
    ("Resolución Exenta Nº 1560-2026", "Resolución Exenta", "Resolución Exenta N°1560"),
    ("Resolución SS IF/N°948", "Resolución", "Resolución IF/N°948"),
    ("Resolución N° 107", "Resolución", "Resolución N°107"),
    ("Decreto Exento N° 31", "Decreto Exento", "Decreto Exento N°31"),
    ("Decreto Nº 3", "Decreto", "Decreto N°3"),
    ("Dictamen N° 1234", "Dictamen", "Dictamen N°1234"),
])
def test_export_reads_exact_type_and_prefix(title, kind, label):
    r = exporter._normative_contract({"event_type": "REGULATION", "signal_types": ["Normativa"], "title": title,
                                      "source_url": "https://www.superdesalud.gob.cl/normativa/x/"})
    assert (r["normative_document_type"], r["normative_document_label"]) == (kind, label)
