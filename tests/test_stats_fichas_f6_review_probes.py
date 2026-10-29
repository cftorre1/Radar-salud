"""Review probes of PR #112 (independent review, 2026-10-29): every probe must be rejected by checker v2 except the
two real layouts of the N°2-2026 acreditación PDF (and the 'Fig.' probe, accepted by the unchanged 80-char window,
and the well-formed 4-cell Total row). Copied verbatim from the reviewer's probe112b.py. No network.
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
PAD = " ".join(["relleno"] * 14)  # ~110 chars, defeats the 80-char window

PROBES = [
    ("diff sentence", f"Hay 101 prestadores {PAD}. Varios tienen observaciones.", 101, OBS, False),
    ("other metric kw in sentence", f"Hay 101 prestadores {PAD} con solicitudes en tramitacion.", 101, OBS, False),
    ("substring public<-publicado", f"Este boletin fue publicado en agosto {PAD} con 217 graficos.", 217, PUB, False),
    ("substring public<-Republica", f"La Republica de Chile {PAD} tiene 217 hospitales.", 217, PUB, False),
    ("substring privad<-privadamente", f"Se informo privadamente {PAD} a 367 hospitales.", 367, PRIV, False),
    ("negation: sin observaciones", f"Del total, 101 prestadores {PAD} fueron acreditados sin observaciones.", 101, OBS, False),
    ("semantics: public accredited (not pending)", f"De los 971 prestadores acreditados, 217 {PAD} son publicos.", 217, PUB,
     False),
    ("pct-column table, no periods, heading kw", "\n".join(
        ["Prestadores privados acreditados segun tipo de establecimiento y complejidad", PAD, "Tipo Numero Porcentaje",
         "Clinicas de alta complejidad 367 37,8%"]), 367, PRIV, False),
    ("single-cell rows table (rows treated as prose)", "\n".join(
        ["Prestadores publicos acreditados por region", PAD, "Region Metropolitana 90", "Region de Valparaiso 217"]), 217,
     PUB, False),
    ("running header merges into first sentence", "\n".join(
        ["Intendencia de Prestadores Publicos y Privados", PAD, "217 prestadores fueron fiscalizados en el semestre."]),
     217, PUB, False),
    ("decimal '2.0' joins sentences", f"Hubo observaciones en la version 2.0 del informe. {PAD} 101 casos de otra cosa",
     101, OBS, False),
    ("'Fig.' abbreviation splits (fail-closed ok)", f"Ver Fig. 2 {PAD} 101 con observaciones", 101, OBS, True),
    ("Total row of next table inherits prev heading (2-cell rows, year caption)", "\n".join(
        ["Solicitudes en tramitacion segun sector", PAD, "Privados 367 10", "Publicos 217 12", "Reclamos por Isapre 2024 2025",
         "Isapre A 300 284", "Isapre B 1 2", "Isapre C 1 2", "Isapre D 1 2", "Total 300 284 584"]), 584, TRA, False),
    ("Total row: adjacent tables separated only by blanks", "\n".join(
        ["Solicitudes en tramitacion por region", PAD, "Arica 3 4 7", "Total 3 4 7", "", "", "Isapre A 300 284 584",
         "Isapre B 1 2 3", "Isapre C 1 2 3", "Total 300 284 584"]), 584, TRA, False),
    ("Total row: prose line above caption supplies kw", "\n".join(
        ["el numero de solicitudes en tramitacion se informa mas abajo", "Cuadro 2. Reclamos por mes " + PAD,
         "Enero 300 284", "Febrero 1 2", "Marzo 1 2", "Abril 1 2", "Total 300 284 584"]), 584, TRA, False),
    ("Total row: heading across many blank lines", "\n".join(
        ["Solicitudes en tramitacion", "", "", "", "", "", PAD, "Ene 300 284", "Feb 1 2", "Mar 1 2", "Abr 1 2",
         "Total 300 284 584"]), 584, TRA, False),
    ("Total row: heading 4 non-table lines away", "\n".join(
        ["Solicitudes en tramitacion", PAD, "linea dos", "linea tres", "Ene 300 284", "Feb 1 2", "Mar 1 2",
         "Total 300 284 584"]), 584, TRA, False),
    ("Total 2-cell: wrong-year column", "\n".join(
        ["Solicitudes en tramitacion 2025 y 2026", PAD, "Sector 2025 2026", "Privados 300 367", "Publicos 1 2", "Otros 1 2",
         "Total 584 600"]), 584, TRA, False),
    ("Total 2-cell: 217 accepted as private", "\n".join(
        ["Solicitudes privadas y publicas en tramitacion", PAD, "Region 1 1", "Region 2 2", "Region 3 3", "Region 4 4",
         "Total 367 217"]), 217, PRIV, False),
    ("Total 1-cell: prose lines ending in a number are 'body'", "\n".join(
        ["Solicitudes en tramitacion", PAD, "Reclamos de 2025", "Reclamos ingresados en junio 2026", "Total 584"]), 584, TRA,
     False),
    ("Total 4-cell: figure is any cell equal to sum of others", "\n".join(
        ["Solicitudes en tramitacion", PAD, "a 1 2 3 4", "b 1 2 3 4", "c 1 2 3 4", "d 1 2 3 4", "Total 100 200 284 584"]),
     584, TRA, True),
    ("Total: middle cell = sum (non-total column)", "\n".join(
        ["Solicitudes en tramitacion", PAD, "a 1 2 3", "b 1 2 3", "c 1 2 3", "d 1 2 3", "Total 300 584 284"]), 584, TRA, False),
    ("space-thousands split into cells", "\n".join(
        ["Solicitudes en tramitacion", PAD, "a 1 2 3", "b 1 2 3", "c 1 2 3", "d 1 2 3", "Total 1 000 583 1 585"]), 584, TRA,
     False),
    ("same number in unrelated table, no kw", "\n".join(
        ["Reclamos por mes", PAD, "a 1 2", "b 1 2", "c 1 2", "Total 300 284 584"]), 584, TRA, False),
]


@pytest.mark.parametrize("name,text,n,ctx,accept", PROBES, ids=[p[0] for p in PROBES])
def test_review_probe(name, text, n, ctx, accept):
    assert cap.figure_evidence([text], [1], n, ctx, 1) is None or name.startswith("'Fig.'")  # v1 misses (window)
    v2 = cap.figure_evidence([text], [1], n, ctx, 2)
    assert (v2 is not None) == accept, v2
    if name.startswith("'Fig.'"):
        assert v2["rule"] == "context_window"  # accepted by the unchanged window, not by the new rules
    if name.startswith("Total 4-cell"):
        assert v2["rule"] == "total_row" and v2["sum_check"] == "100 + 200 + 284 = 584"


def test_uncited_page_page_boundary_and_other_topics():
    assert cap.figure_evidence(["x", "Hay 101 con observaciones"], [1], 101, OBS, 2) is None
    assert cap.figure_evidence([f"101 prestadores {PAD}", "con observaciones."], [1, 2], 101, OBS, 2) is None
    assert [cap.checker_version(t) for t in ("mediacion", "rnpi", "reclamos", None)] == [1, 1, 1, 1]
    assert cap.checker_version("acreditacion") == 2
    # Metrics without v2 rules (other topics, generic context) never use the new rules.
    assert cap.figure_evidence([f"Hay 175 {PAD} mediadores."], [1], 175, C["registered_mediators"], 2) is None


def test_real_layouts_are_the_accepted_positives():
    pdf = real.doc()
    p2, p8 = real.text_of(pdf, 2), real.text_of(pdf, 8)
    assert cap.figure_evidence([p2], [1], 101, OBS, 1) is None and cap.figure_evidence([p8], [1], 584, TRA, 1) is None
    assert cap.figure_evidence([p2], [1], 101, OBS, 2) == {"rule": "sentence", "page": 1}
    tot = cap.figure_evidence([p8], [1], 584, TRA, 2)
    assert tot["rule"] == "total_row" and tot["sum_check"] == "367 + 217 = 584" and tot["heading"].startswith("tabla 7.")


@pytest.mark.parametrize("text,key,ok", [
    ("Del total, 101 prestadores obtuvieron el resultado de acreditado con observaciones.", "with_observations", True),
    ("Del total, 101 prestadores sin y con observaciones.", "with_observations", False),  # 'sin' within 3 words
    ("Hay 101 prestadores que en sus procesos regionales anteriores finalmente obtuvieron el resultado con observaciones.",
     "with_observations", False),  # > 6 content words between
    ("Hay 101 prestadores y 30 clinicas con observaciones.", "with_observations", False),  # another number in between
    ("Hay 367 solicitudes de prestadores privados en tramitacion.", "private_pending", True),
    ("Hay 367 solicitudes de prestadores privados.", "private_pending", False),  # pending word required
    ("Hay 584 solicitudes en tramitacion.", "pending_applications", True),
    ("Hay 101 prestadores " + "con " * 100 + "observaciones.", "with_observations", False),  # > 300 chars
    ("Total 101 prestadores con observaciones.", "with_observations", False),  # 'Total …' line
    ("Hay 101 prestadores con observaciones 2026 2025", "with_observations", False),  # ends in a number: table-like
])
def test_sentence_rule_details(text, key, ok):
    assert cap.in_same_sentence(text, int(re.search(r"\d+", text)[0]), key) is ok

