"""Review probes of PR #112 (independent reviews, 2026-10-29: probe112b, probe112d, probe112e), copied verbatim.

Checker v2 has no generic sentence / table rule any more: the only addition over the unchanged 80-char window is a
human-reviewed anchored template per figure. Every probe must be rejected by v2 with the repo templates (filled from
the real PDF and approved by Dirección on 2026-10-30) and with a placeholder copy: v2 accepts exactly what v1's window
accepts and nothing else. The real normalized pp. 2 and 8 are the only positives. No network.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_stats_fichas_f6_figure_rules as real  # noqa: E402
from radar_salud import stats_capture as cap  # noqa: E402

C = cap.METRIC_CONTEXT
OBS, TRA, PRIV, PUB, ACR = (C["with_observations"], C["pending_applications"], C["private_pending"],
                            C["public_pending"], C["accredited_providers"])
KEY = {OBS: "with_observations", TRA: "pending_applications", PRIV: "private_pending", PUB: "public_pending",
       ACR: "accredited_providers"}
PAD = " ".join(["relleno"] * 14)  # ~110 chars, defeats the 80-char window
L = "establecimientos institucionales de los servicios metropolitanos correspondientes administrativamente"
L4 = "establecimientos institucionales metropolitanos administrativamente de la de los"
H2 = PAD + "\n" + PAD
VERIFIED = {"with_observations": 101, "pending_applications": 584, "private_pending": 367, "public_pending": 217,
            "accredited_providers": 971}
# Probes accepted by the unchanged v1 window (out of scope of this change): v2 must give the same answer.
WINDOW_ACCEPTED = {"'Fig.' abbreviation splits (fail-closed ok)", "A12 PRIV 'ademas de 217 publicos' later"}

PROBES = [
    ('probe112b', "diff sentence",
     f"Hay 101 prestadores {PAD}. Varios tienen observaciones.",
     101, OBS),
    ('probe112b', "other metric kw in sentence",
     f"Hay 101 prestadores {PAD} con solicitudes en tramitacion.",
     101, OBS),
    ('probe112b', "substring public<-publicado",
     f"Este boletin fue publicado en agosto {PAD} con 217 graficos.",
     217, PUB),
    ('probe112b', "substring public<-Republica",
     f"La Republica de Chile {PAD} tiene 217 hospitales.",
     217, PUB),
    ('probe112b', "substring privad<-privadamente",
     f"Se informo privadamente {PAD} a 367 hospitales.",
     367, PRIV),
    ('probe112b', "negation: sin observaciones",
     f"Del total, 101 prestadores {PAD} fueron acreditados sin observaciones.",
     101, OBS),
    ('probe112b', "semantics: public accredited (not pending)",
     f"De los 971 prestadores acreditados, 217 {PAD} son publicos.",
     217, PUB),
    ('probe112b', "pct-column table, no periods, heading kw",
     "\n".join(
    ["Prestadores privados acreditados segun tipo de establecimiento y complejidad", PAD, "Tipo Numero Porcentaje",
     "Clinicas de alta complejidad 367 37,8%"]),
     367, PRIV),
    ('probe112b', "single-cell rows table (rows treated as prose)",
     "\n".join(
    ["Prestadores publicos acreditados por region", PAD, "Region Metropolitana 90", "Region de Valparaiso 217"]),
     217, PUB),
    ('probe112b', "running header merges into first sentence",
     "\n".join(
    ["Intendencia de Prestadores Publicos y Privados", PAD, "217 prestadores fueron fiscalizados en el semestre."]),
     217, PUB),
    ('probe112b', "decimal '2.0' joins sentences",
     f"Hubo observaciones en la version 2.0 del informe. {PAD} 101 casos de otra cosa",
     101, OBS),
    ('probe112b', "'Fig.' abbreviation splits (fail-closed ok)",
     f"Ver Fig. 2 {PAD} 101 con observaciones",
     101, OBS),
    ('probe112b', "Total row of next table inherits prev heading (2-cell rows, year caption)",
     "\n".join(
    ["Solicitudes en tramitacion segun sector", PAD, "Privados 367 10", "Publicos 217 12", "Reclamos por Isapre 2024 2025",
     "Isapre A 300 284", "Isapre B 1 2", "Isapre C 1 2", "Isapre D 1 2", "Total 300 284 584"]),
     584, TRA),
    ('probe112b', "Total row: adjacent tables separated only by blanks",
     "\n".join(
    ["Solicitudes en tramitacion por region", PAD, "Arica 3 4 7", "Total 3 4 7", "", "", "Isapre A 300 284 584",
     "Isapre B 1 2 3", "Isapre C 1 2 3", "Total 300 284 584"]),
     584, TRA),
    ('probe112b', "Total row: prose line above caption supplies kw",
     "\n".join(
    ["el numero de solicitudes en tramitacion se informa mas abajo", "Cuadro 2. Reclamos por mes " + PAD,
     "Enero 300 284", "Febrero 1 2", "Marzo 1 2", "Abril 1 2", "Total 300 284 584"]),
     584, TRA),
    ('probe112b', "Total row: heading across many blank lines",
     "\n".join(
    ["Solicitudes en tramitacion", "", "", "", "", "", PAD, "Ene 300 284", "Feb 1 2", "Mar 1 2", "Abr 1 2", "Total 300 284 584"]),
     584, TRA),
    ('probe112b', "Total row: heading 4 non-table lines away",
     "\n".join(
    ["Solicitudes en tramitacion", PAD, "linea dos", "linea tres", "Ene 300 284", "Feb 1 2", "Mar 1 2", "Total 300 284 584"]),
     584, TRA),
    ('probe112b', "Total 2-cell: wrong-year column",
     "\n".join(
    ["Solicitudes en tramitacion 2025 y 2026", PAD, "Sector 2025 2026", "Privados 300 367", "Publicos 1 2", "Otros 1 2", "Total 584 600"]),
     584, TRA),
    ('probe112b', "Total 2-cell: 217 accepted as private",
     "\n".join(
    ["Solicitudes privadas y publicas en tramitacion", PAD, "Region 1 1", "Region 2 2", "Region 3 3", "Region 4 4", "Total 367 217"]),
     217, PRIV),
    ('probe112b', "Total 1-cell: prose lines ending in a number are 'body'",
     "\n".join(
    ["Solicitudes en tramitacion", PAD, "Reclamos de 2025", "Reclamos ingresados en junio 2026", "Total 584"]),
     584, TRA),
    ('probe112b', "Total 4-cell: figure is any cell equal to sum of others",
     "\n".join(
    ["Solicitudes en tramitacion", PAD, "a 1 2 3 4", "b 1 2 3 4", "c 1 2 3 4", "d 1 2 3 4", "Total 100 200 284 584"]),
     584, TRA),
    ('probe112b', "Total: middle cell = sum (non-total column)",
     "\n".join(
    ["Solicitudes en tramitacion", PAD, "a 1 2 3", "b 1 2 3", "c 1 2 3", "d 1 2 3", "Total 300 584 284"]),
     584, TRA),
    ('probe112b', "space-thousands split into cells",
     "\n".join(
    ["Solicitudes en tramitacion", PAD, "a 1 2 3", "b 1 2 3", "c 1 2 3", "d 1 2 3", "Total 1 000 583 1 585"]),
     584, TRA),
    ('probe112b', "same number in unrelated table, no kw",
     "\n".join(
    ["Reclamos por mes", PAD, "a 1 2", "b 1 2", "c 1 2", "Total 300 284 584"]),
     584, TRA),
    ('probe112d', "A0 control (should accept): 101 <L> con observaciones",
     f"Se informan {PAD} 101 {L} con observaciones.",
     101, OBS),
    ('probe112d', "A1 stopword padding, 101 = reviewed",
     f"Se revisaron {PAD} 101 de los prestadores del sistema de salud de la red de la de la region de la de la, de la, varios con observaciones.",
     101, OBS),
    ('probe112d', "A2 'de los cuales algunos'",
     f"Se fiscalizaron {PAD} 101 {L}, de los cuales algunos con observaciones.",
     101, OBS),
    ('probe112d', "A3 'no fueron acreditados con observaciones'",
     f"Del total {PAD}, 101 {L} no fueron acreditados con observaciones.",
     101, OBS),
    ('probe112d', "A4 'excepto los con observaciones'",
     f"Se acreditaron {PAD} 101 {L} excepto los con observaciones.",
     101, OBS),
    ('probe112d', "A5 'ninguno con observaciones'",
     f"Se acreditaron {PAD} 101 {L}, ninguno con observaciones.",
     101, OBS),
    ('probe112d', "A6 'nunca con observaciones'",
     f"Se acreditaron {PAD} 101 {L} nunca con observaciones.",
     101, OBS),
    ('probe112d', "A7 ACR 'no acreditados'",
     f"Al cierre {PAD} 101 {L} no acreditados.",
     101, ACR),
    ('probe112d', "A8 ACR 'que fueron des-acreditados'... 'que dejaron de estar acreditados'",
     f"Al cierre {PAD} 101 {L} dejaron de estar acreditados.",
     101, ACR),
    ('probe112d', "A9 subordinate clause 'que en su mayoria quedaron con observaciones'",
     f"Ingresaron {PAD} 971 solicitudes institucionales correspondientes administrativamente metropolitanas, que en su mayoria quedaron con observaciones.",
     971, OBS),
    ('probe112d', "A10 PRIV via 'publicos y privados'",
     f"Hay {PAD} 584 solicitudes en tramitacion de los establecimientos institucionales, publicos y privados.",
     584, PRIV),
    ('probe112d', "A11 PUB 'no publicos'",
     f"Hay {PAD} 584 solicitudes en tramitacion de los establecimientos institucionales metropolitanos no publicos.",
     584, PUB),
    ('probe112d', "A12 PRIV 'ademas de 217 publicos' later",
     f"En tramitacion hay {PAD} 584 solicitudes de los establecimientos institucionales metropolitanos privados.",
     584, PRIV),
    ('probe112d', "A13 date exemption: '30 de junio' real number is count",
     f"Se informan {PAD} 30 de junio a la fecha de los establecimientos institucionales metropolitanos con observaciones.",
     30, OBS),
    ('probe112d', "A14 table row with date label read as prose",
     "Region Metropolitana junio 2026 101 " + L + " con observaciones",
     101, OBS),
    ('probe112d', "A15 OBS sentence negated by 'sin' 4 words back",
     f"Se acreditaron {PAD} 101 {L} sin ningun tipo de observaciones ni con observaciones menores.",
     101, OBS),
    ('probe112d', "B0 control",
     "\n".join(["Solicitudes en tramitacion por region", H2, "Arica 300 284 584", "Tarapaca 1 2 3", "Total 301 286 587"]),
     587, TRA),
    ('probe112d', "B1 caption BELOW table A labels table B",
     "\n".join(
    ["Reclamos por region", "Arica 1 2 3", "Total 1 2 3", "Cuadro 1. Solicitudes en tramitacion por region", H2,
     "Isapre A 300 284 584", "Isapre B 1 2 3", "Total 301 286 587"]),
     587, TRA),
    ('probe112d', "B2 prose above other heading supplies kw",
     "\n".join(
    ["Las solicitudes en tramitacion se describen antes", "Reclamos ingresados por mes", PAD, "Ene 300 284 584",
     "Feb 1 2 3", "Total 301 286 587"]),
     587, TRA),
    ('probe112d', "B3 two stacked tables same cell count, no blank",
     "\n".join(
    ["Solicitudes en tramitacion por region", H2, "Arica 1 2 3", "Tarapaca 1 2 3", "Reclamos Isapre A 300 284 584",
     "Reclamos Isapre B 1 2 3", "Total 303 290 593"]),
     593, TRA),
    ('probe112d', "B4 caption about other metric incl tramitacion (ACR)",
     "\n".join(
    ["Cuadro 4. Prestadores acreditados con reacreditacion en tramitacion", H2, "Privados 40 30 70", "Publicos 20 10 30",
     "Total 60 40 100"]),
     100, ACR),
    ('probe112d', "B5 PRIV: Total column of a privados+publicos table",
     "\n".join(
    ["Solicitudes en tramitacion de prestadores privados y publicos", H2,
     "Norte 200 100 300", "Sur 167 117 284", "Total 367 217 584"]),
     584, PRIV),
    ('probe112d', "B6 percent Total row w/o % signs",
     "\n".join(
    ["Distribucion porcentual de solicitudes en tramitacion", H2, "Privados 63 37 100", "Total 63 37 100"]),
     100, TRA),
    ('probe112d', "B7 percent Total row with %",
     "\n".join(
    ["Solicitudes en tramitacion (%)", H2, "Privados 63% 37% 100%", "Total 63% 37% 100%"]),
     100, TRA),
    ('probe112d', "B8 caption line naming two tables",
     "\n".join(
    ["Cuadro 3. Solicitudes en tramitacion y Cuadro 4. Reclamos por mes", H2, "Ene 300 284 584", "Total 300 284 584"]),
     584, TRA),
    ('probe112d', "B9 'sin tramitacion' heading",
     "\n".join(
    ["Solicitudes sin tramitacion por region", H2, "Arica 300 284 584", "Total 300 284 584"]),
     584, TRA),
    ('probe112d', "B10 OBS: heading 'en tramite, sin observaciones'",
     "\n".join(
    ["Acreditaciones en tramite sin observaciones", H2, "Arica 60 41 101", "Total 60 41 101"]),
     101, OBS),
    ('probe112d', "B11 OBS: 'con observaciones' column but Total is all",
     "\n".join(
    ["Solicitudes en tramitacion con y sin observaciones", H2, "Arica 60 41 101", "Total 60 41 101"]),
     101, OBS),
    ('probe112d', "B12 heading: 'tramitacion' only in 3rd line up of prose",
     "\n".join(
    ["Reclamos: se excluyen las solicitudes en tramitacion", "Reclamos por prestador privado", PAD, "Ene 300 284 584", "Total 300 284 584"]),
     584, PRIV),
    ('probe112d', "B13 caption 'Tabla 2' of other metric, kw in following subtitle line",
     "\n".join(
    ["Solicitudes en tramitacion", "Tabla 2", "Reclamos por mes", PAD, "Ene 300 284 584", "Total 300 284 584"]),
     584, TRA),
    ('probe112e', "N1 'no fueron'",
     f"Del total {PAD}, 101 {L4} no fueron con observaciones.",
     101, OBS),
    ('probe112e', "N2 'excepto los'",
     f"Se acreditaron {PAD} 101 {L4} excepto los con observaciones.",
     101, OBS),
    ('probe112e', "N3 'ninguno'",
     f"Se acreditaron {PAD} 101 {L4}, ninguno con observaciones.",
     101, OBS),
    ('probe112e', "N4 'no obtuvieron'",
     f"Se acreditaron {PAD} 101 {L4} no obtuvieron con observaciones.",
     101, OBS),
    ('probe112e', "N5 ACR 'no acreditados'",
     f"Al cierre {PAD} 101 {L4} no acreditados.",
     101, ACR),
    ('probe112e', "N6 subordinate 'que quedaron'",
     f"Ingresaron {PAD} 971 {L4}, que quedaron con observaciones.",
     971, OBS),
    ('probe112e', "N7 subordinate 'cuyos pares'",
     f"Ingresaron {PAD} 971 {L4}, cuyos pares quedaron con observaciones.",
     971, OBS),
    ('probe112e', "N8 PUB 'no publicos ... tramitacion'",
     f"Hay {PAD} 584 {L4} no publicos en tramitacion.",
     584, PUB),
]


def _ids():
    return [f"{p[0]}:{re.sub(r'[^A-Za-z0-9]+', '_', p[1])[:60]}" for p in PROBES]


@pytest.mark.parametrize("templates", ["repo_reviewed", "placeholder_copy"])
@pytest.mark.parametrize("tag,name,text,n,ctx", PROBES, ids=_ids())
def test_review_probe_is_rejected(tag, name, text, n, ctx, templates):
    tpl = real.REPO_TEMPLATES if templates == "repo_reviewed" else real.placeholder_copy()
    v1 = cap.figure_evidence([text], [1], n, ctx, 1)
    v2 = cap.figure_evidence([text], [1], n, ctx, 2, KEY.get(ctx), tpl, VERIFIED)
    if name in WINDOW_ACCEPTED:
        assert v1 == v2 == {"rule": "context_window", "page": 1}
    else:
        assert v1 is None and v2 is None, v2
    if KEY.get(ctx) in tpl:  # the template itself, applied directly, never matches a probe
        assert cap.template_evidence([text], [1], n, tpl[KEY[ctx]], VERIFIED)[0] is None


def test_probe_count():
    assert len(PROBES) == 62


def test_uncited_page_page_boundary_and_other_topics():
    tpl = real.REPO_TEMPLATES
    p2 = real.REAL_PAGES[2]
    assert cap.figure_evidence(["x", p2], [1], 101, OBS, 2, "with_observations", tpl, VERIFIED) is None
    head, tail = p2.split(" obtuvieron el resultado de acreditado", 1)
    assert cap.figure_evidence([head, "obtuvieron el resultado de acreditado" + tail], [1, 2], 101, OBS, 2,
                               "with_observations", tpl, VERIFIED) is None  # a template never spans pages
    assert [cap.checker_version(t) for t in ("mediacion", "rnpi", "reclamos", None)] == [1, 1, 1, 1]
    assert cap.checker_version("acreditacion") == 2
    assert cap.figure_evidence([p2], [1], 101, OBS, 1, "with_observations", tpl, VERIFIED) is None  # v1: no templates


def test_real_layouts_are_the_only_positives():
    p2, p7, p8 = real.REAL_PAGES[2], real.REAL_PAGES[7], real.REAL_PAGES[8]
    tpl = real.REPO_TEMPLATES
    assert cap.figure_evidence([p2], [1], 101, OBS, 1) is None
    assert cap.figure_evidence([p7, p8], [1, 2], 584, TRA, 1) is None
    obs = cap.figure_evidence([p2], [1], 101, OBS, 2, "with_observations", tpl, VERIFIED)
    assert obs["rule"] == "template" and obs["match"] == real.SENTENCE_P2
    tot = cap.figure_evidence([p7, p8], [1, 2], 584, TRA, 2, "pending_applications", tpl, VERIFIED)
    assert tot["rule"] == "template" and tot["page"] == 2 and tot["sum_check"] == "367 + 217 = 584"
    # p.7's own '… 237 584' row is not anchored by the p.8 title: the only match is on p.8.
    assert cap.template_evidence([p7], [1], 584, tpl["pending_applications"], VERIFIED)[1] == "no_match"
    # The same pages with the placeholder / unreviewed copy stay on HOLD.
    ph = real.placeholder_copy()
    assert cap.figure_evidence([p2], [1], 101, OBS, 2, "with_observations", ph, VERIFIED) is None
    assert cap.figure_evidence([p8], [1], 584, TRA, 2, "pending_applications", ph, VERIFIED) is None
