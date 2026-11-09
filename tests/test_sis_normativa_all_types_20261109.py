"""Dirección 9-nov-2026 (punto B): every SIS normative listing, live only (14 days), no duplicates,
no internal administration. Listing structure as read by probe 42711886047."""
from datetime import date

from radar_salud import regulatory
from radar_salud.regulatory import act_identity

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


def _scout(monkeypatch):
    pages = {"https://www.superdesalud.gob.cl/aseguradoras/": ASEGURADORAS,
             regulatory.SuperintendenciaNormativaScout.EXTRA_PAGES[0][1]: OTRAS,
             regulatory.SuperintendenciaNormativaScout.EXTRA_PAGES[1][1]: MARCO_RES,
             regulatory.SuperintendenciaNormativaScout.EXTRA_PAGES[2][1]: DECRETOS}
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


def test_act_identity_normalises_spelling():
    assert act_identity("Resolución Exenta IF/N°12392 - Emisión: 23/10/2026") == act_identity("Resolución Exenta IF/N° 12392")
    assert act_identity("Circular IF/N°541") != act_identity("Circular IP N°541")
    assert act_identity("Oficio Circular IF/N° 20") == "oficio circular|if|20"
