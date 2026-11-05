"""Dirección 3-nov-2026: one card per bill and per event in the Chile feed (feed_dedupe)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from radar_salud import feed_dedupe as fd  # noqa: E402

BILL = "https://tramitacion.senado.cl/appsenado/templates/tramitacion/index.php?boletin_ini=18803-13"


def bill(kind, label, day, boletin="18803-13"):
    return {"title": f"{label}: Modifica la ley N° 21.063 (Ley Sanna) (Boletín {boletin})", "bill_boletin": boletin,
            "bill_milestone": kind, "event_date": day, "source_type": "official",
            "source_name": "Congreso Nacional · Tramitación (Senado, datos abiertos)",
            "source_url": f"{BILL}#hito-{kind}-{day}"}


def news(src, title, day="2026-10-28", stype="press_high_trust", url=None, **kw):
    return {"title": title, "source_name": src, "source_type": stype, "event_date": day,
            "source_url": url or f"https://example.cl/{abs(hash((src, title)))}", **kw}


MINSAL = news("Ministerio de Salud", "Minsal buscó y vacunó a más de 44 mil niños y niñas contra el sarampión y llama "
              "a vacunar a más de 140 mil con su esquema pendiente", stype="official")
PULSO = news("Pulso / La Tercera", "“Chile contra el sarampión”: Minsal logra vacunar a 44 mil niños, pero persisten "
             "más de 140 mil con esquema pendiente", paywalled=True)


def test_two_milestones_of_one_bill_on_the_same_day_are_one_card_with_the_latest_milestone():
    a, b = bill("ingreso", "Ingresó a tramitación", "2026-10-27"), bill("despacho", "Despachado", "2026-10-27")
    other = bill("ingreso", "Ingresó a tramitación", "2026-10-27", boletin="17765-35")
    out = fd.collapse_bill_milestones([a, other, b])
    assert len(out) == 2 and out[0] is other  # the kept card stays where it was in the curated order
    kept = out[1]
    assert kept["title"].startswith("Despachado") and kept["source_url"] == b["source_url"]
    assert kept["bill_history"] == [{"source_name": a["source_name"], "title": a["title"], "url": a["source_url"],
                                     "event_date": "2026-10-27", "material": "Ingresó a tramitación"}]
    assert kept["dedupe"]["bill_milestones"] == {"boletin": "18803-13", "merged": 1}
    assert "bill_history" not in b  # inputs are never mutated


def test_a_later_milestone_wins_over_a_higher_one_on_an_earlier_day():
    out = fd.collapse_bill_milestones([bill("despacho", "Despachado", "2026-10-20"),
                                       bill("informe_comision", "Informe de comisión", "2026-10-28")])
    assert len(out) == 1 and out[0]["title"].startswith("Informe de comisión")


def test_official_release_and_press_piece_on_the_same_event_merge_into_the_official_card():
    out = fd.merge_same_event([PULSO, MINSAL])
    assert len(out) == 1
    kept = out[0]
    assert kept["source_name"] == "Ministerio de Salud" and kept["title"] == MINSAL["title"]
    assert kept["same_event_sources"] == [{"source_name": "Pulso / La Tercera", "title": PULSO["title"],
                                           "url": PULSO["source_url"], "event_date": "2026-10-28", "paywalled": True}]
    ev = kept["dedupe"]["same_event"][0]
    assert {"44", "140", "sarampi"} <= set(ev["shared_terms"]) and ev["jaccard"] >= fd.MIN_JACCARD


def test_different_events_on_the_same_topic_stay_separate():
    other = news("Pulso / La Tercera", "Minsal informa nuevo caso importado de sarampión en Chile", day="2026-10-28")
    assert len(fd.merge_same_event([MINSAL, other])) == 2


def test_far_apart_dates_or_the_same_source_never_merge():
    late = dict(PULSO, event_date="2026-11-05")
    assert len(fd.merge_same_event([MINSAL, late])) == 2
    same_src = dict(PULSO, source_name="Ministerio de Salud")
    assert len(fd.merge_same_event([MINSAL, same_src])) == 2


def test_records_bills_fichas_and_syntheses_never_merge():
    for extra in ({"source_name": "Diario Oficial", "source_type": "official"}, {"bill_boletin": "1-11"},
                  {"stats_ficha": {"family": "F6"}}, {"source_type": "editorial_synthesis"},
                  {"event_type": "STORY_SUMMARY"}, {"derived_from": "editorial_story_group"}):
        assert len(fd.merge_same_event([MINSAL, dict(PULSO, **extra)])) == 2, extra


def test_open_press_is_kept_over_paywalled_press_when_no_official_card():
    df = news("Diario Financiero", PULSO["title"].replace("“", "").replace("”", ""))
    out = fd.merge_same_event([PULSO, df])
    assert len(out) == 1 and out[0]["source_name"] == "Diario Financiero"


def test_a_chain_without_a_direct_match_to_the_kept_card_is_not_merged():
    a = news("Ministerio de Salud", "Campaña invierno vacunación influenza hospitales regiones", stype="official")
    b = news("Pulso / La Tercera", "Campaña invierno vacunación influenza colegios apoderados")
    c = news("Diario Financiero", "Influenza colegios apoderados licencias empresas ausentismo")
    out = fd.merge_same_event([a, b, c])
    kept = next(x for x in out if x["source_name"] == "Ministerio de Salud")
    assert [r["source_name"] for r in kept.get("same_event_sources", [])] in (["Pulso / La Tercera"], [])
    assert any(x["source_name"] == "Diario Financiero" for x in out)


def test_apply_on_the_committed_snapshot_only_removes_cards_it_lists_on_a_kept_card():
    import json
    snap = json.loads((Path(__file__).resolve().parents[1] / "web/data/radar_today.json").read_text(encoding="utf-8"))
    cards = snap["signals"]
    out = fd.apply(cards)
    removed = {c.get("source_url") for c in cards} - {c.get("source_url") for c in out}
    listed = {r["url"] for c in out for k in ("bill_history", "same_event_sources", "group_items") for r in c.get(k) or []}
    assert removed <= listed
    assert fd.apply(out) == out  # idempotent


# Review of #135: titles that differ in one name share many generic words; without a shared figure they stay apart.
ADVERSARIAL = [
    ("Superintendencia multa a Isapre Colmena por incumplir garantías GES",
     "Superintendencia multa a Isapre Cruz Blanca por incumplir garantías GES"),
    ("Hospital Sótero del Río suspende cirugías por falta de anestesistas",
     "Hospital Barros Luco suspende cirugías por falta de anestesistas"),
    ("ISP alerta retiro de lote de paracetamol por defecto de calidad",
     "ISP alerta retiro de lote de ibuprofeno por defecto de calidad"),
    ("Ministra anuncia plan nacional de listas de espera", "Ministra anuncia plan nacional de vacunación"),
    ("Fonasa abre licitación de cirugías en la Región Metropolitana", "Fonasa abre licitación de cirugías en Valparaíso"),
    ("Contraloría detecta licencias médicas irregulares en funcionarios municipales",
     "Contraloría detecta licencias médicas irregulares en funcionarios de Gendarmería"),
]


ADVERSARIAL += [  # second review of #135: one shared round figure, or one differing place in a long title
    ("Superintendencia multa con 500 UF a Isapre Colmena", "Superintendencia multa con 500 UF a Isapre Cruz Blanca"),
    ("Licencias médicas aumentan 20% en el primer semestre", "Consultas de urgencia aumentan 20% en el primer semestre"),
    ("Listas de espera quirúrgicas aumentan 15% en el último año", "Listas de espera oncológicas aumentan 15% en el último año"),
    ("Fonasa licita 50 camas críticas en la Región Metropolitana", "Fonasa licita 50 camas críticas en la Región del Biobío"),
    ("Minsal confirma 12 casos de sarampión en la última semana", "Minsal confirma 12 casos de hepatitis en la última semana"),
    ("Contraloría detecta irregularidades en compras de medicamentos del hospital de Viña del Mar",
     "Contraloría detecta irregularidades en compras de medicamentos del hospital de Concepción"),
]

ADVERSARIAL += [  # third review: thousands separators, law numbers, single digits, acronyms
    ("Colmena devolverá $1.200 millones a 3.000 afiliados por alza de precio base",
     "Banmédica devolverá $1.200 millones a 3.000 afiliados por alza de precio base"),
    ("Senado aprueba 20 indicaciones al proyecto que modifica la Ley 21.063",
     "Cámara rechaza 20 indicaciones al proyecto que modifica la Ley 21.063"),
    ("Brote en hogar de ancianos deja 3 muertes en Temuco", "Brote en hogar de ancianos deja 4 muertes en Temuco"),
    ("Hospital suspende 5 cirugías por falta de insumos", "Hospital suspende 8 cirugías por falta de insumos"),
    ("Minsal lanza campaña de vacunación contra el VIH", "Minsal lanza campaña de vacunación contra el VRS"),
    ("Minsal amplía vacuna VPH a adolescentes", "Minsal amplía vacuna BCG a adolescentes"),
]

ADVERSARIAL += [  # fourth review: small figures carrying the match
    ("Clínica en Temuco despide a 30 enfermeras y cierra 2 pabellones",
     "Clínica en Temuco despide a 30 técnicos y cierra 2 pabellones"),
]


def test_identical_titles_two_days_apart_stay_separate():
    t = "Hospital suspende 40 cirugías y posterga 120 consultas por paro"
    a, b = news("Ministerio de Salud", t, stype="official"), news("Pulso / La Tercera", t, day="2026-10-30")
    assert len(fd.merge_same_event([a, b])) == 2
    assert len(fd.merge_same_event([a, dict(b, event_date="2026-10-29")])) == 1


def test_figures_are_read_whole_and_identifiers_are_not_figures():
    assert fd.figures("$1.200 millones a 3.000 afiliados") == {"1200", "3000"}
    assert fd.figures("modifica la Ley 21.063 y el Boletín 18803-13") == set()
    assert fd.figures("3 muertes, 3,5% más que en 2025") == {"3", "3,5"}
    assert fd.figures("44 mil niños") == {"44"}


def test_reviewer_adversarial_pairs_stay_separate():
    for a, b in ADVERSARIAL:
        out = fd.merge_same_event([news("Ministerio de Salud", a, stype="official"), news("Pulso / La Tercera", b)])
        assert len(out) == 2, (a, b)


def test_cards_naming_different_entities_never_merge_even_with_a_shared_figure():
    ref = lambda i: [{"canonical_id": i, "name": i}]  # noqa: E731
    a = dict(MINSAL, entity_refs=ref("cl:org:colmena"))
    b = dict(PULSO, entity_refs=ref("cl:org:cruz-blanca"))
    assert len(fd.merge_same_event([a, b])) == 2
    # Both naming entities but not the same ones (one card's extraction missed its actor) is not merged either.
    c = dict(MINSAL, entity_refs=ref("cl:org:sis") + ref("cl:org:colmena"))
    assert len(fd.merge_same_event([c, dict(PULSO, entity_refs=ref("cl:org:sis"))])) == 2
    # Only one card naming entities is no conflict.
    assert len(fd.merge_same_event([dict(MINSAL), b])) == 1


def test_kept_card_inherits_entity_refs_and_identity_keys_of_merged_cards():
    b = dict(PULSO, entity_refs=[{"canonical_id": "cl:org:minsal", "name": "Minsal"}], event_type="NEWS")
    kept = fd.merge_same_event([MINSAL, b])[0]
    assert [r["canonical_id"] for r in kept["entity_refs"]] == ["cl:org:minsal"]
    assert kept["merged_from"] == [{"source_url": PULSO["source_url"], "event_date": "2026-10-28", "event_type": "NEWS"}]
    a, d = bill("ingreso", "Ingresó a tramitación", "2026-10-27"), bill("despacho", "Despachado", "2026-10-27")
    k2 = fd.collapse_bill_milestones([a, d])[0]
    assert k2["merged_from"] == [{"source_url": a["source_url"], "event_date": "2026-10-27"}]


def test_v3_cards_never_merge():
    assert len(fd.merge_same_event([dict(MINSAL, editorial_schema_version="3"), PULSO])) == 2


# ---------------------------------------------------------------------------------------------------------------
# 3. One act, several health services (Dirección 4-nov-2026)

DO_URL = "https://www.diariooficial.interior.gob.cl/publicaciones/2026/11/04/44590/01/{}.pdf"


def act(num, op, day="2026-11-04", kind="Res. exenta", pdf="1", **kw):
    t = f"{kind} {num}/2026 · {op}"
    return {"title": t, "display_title": t, "source_name": "Diario Oficial", "source_type": "official",
            "event_type": "LEGAL", "event_date": day, "source_url": DO_URL.format(pdf),
            "what_happened": f"Acto {num}.", "source_documents": [{"url": DO_URL.format(pdf)}], **kw}


NORTE = act("CP 14.658", "Aprueba actualización de Arsenal Farmacológico para establecimientos de Atención Primaria de "
            "Salud, del Servicio de Salud Araucanía Norte", pdf="2893118")
SUR = act("CP 24.861", "Actualiza Arsenal Farmacológico para Establecimientos de Atención Primaria de Salud, del Servicio "
          "de Salud Araucanía Sur", pdf="2893117")


def test_one_act_for_two_services_is_one_card_that_keeps_every_act_number_and_link():
    other = news("Ministerio de Salud", "Otra noticia", stype="official")
    out = fd.apply([SUR, other, NORTE])
    assert len(out) == 2
    g = next(c for c in out if c.get("group_items"))
    # Both normative IDs and both services stay in the title; services come first (the feed clamps long titles).
    assert g["title"] == ("Res. exenta CP 14.658 y CP 24.861/2026 · Servicios de Salud Araucanía Norte y Araucanía Sur · "
                          "Arsenal Farmacológico para establecimientos de Atención Primaria de Salud")
    assert [x["url"] for x in g["group_items"]] == [NORTE["source_url"], SUR["source_url"]]
    assert g["what_happened"] == "Res. exenta CP 14.658/2026 (Servicio de Salud Araucanía Norte): Acto CP 14.658."
    assert g["key_points"] == ["Res. exenta CP 24.861/2026 (Servicio de Salud Araucanía Sur): Acto CP 24.861."]
    assert g["dedupe"] == {"rule": "act_series", "acts": ["CP 14.658", "CP 24.861"],
                           "services": ["Araucanía Norte", "Araucanía Sur"]}
    # A shared link of the absorbed act opens the group.
    assert any(k.get("source_url") == SUR["source_url"] for k in g["merged_from"])
    assert {d["url"] for d in g["source_documents"]} == {NORTE["source_url"], SUR["source_url"]}
    assert "group_items" not in NORTE and "group_items" not in SUR  # inputs are never mutated


def test_act_series_stays_apart_when_any_condition_fails():
    sur_tomorrow = {**SUR, "event_date": "2026-11-05"}
    same_service = act("CP 24.861", "Actualiza Arsenal Farmacológico para Establecimientos de Atención Primaria de Salud, "
                       "del Servicio de Salud Araucanía Norte", pdf="9")
    other_object = act("CP 24.862", "Aprueba Norma Técnica de farmacia, del Servicio de Salud Araucanía Sur", pdf="8")
    decree = act("CP 24.861", SUR["title"].split(" · ", 1)[1], kind="Decreto exento", pdf="7")
    press = {**SUR, "source_name": "Pulso / La Tercera", "source_type": "press_high_trust"}
    for b in (sur_tomorrow, same_service, other_object, decree, press):
        assert len(fd.group_act_series([NORTE, b])) == 2, b["title"]
    # Two acts on different products (no health service in the title) are not this rule.
    tramadol = act("E 5.187", "Modifica folletos de información de productos con tramadol", pdf="5")
    metamizol = act("E 5.188", "Modifica folletos de información de productos con metamizol", pdf="6")
    assert len(fd.group_act_series([tramadol, metamizol])) == 2


def test_three_services_are_named_in_order():
    c = act("CP 30.001", "Actualiza Arsenal Farmacológico para Establecimientos de Atención Primaria de Salud, del "
            "Servicio de Salud Aconcagua", pdf="3")
    out = fd.group_act_series([SUR, c, NORTE])
    assert len(out) == 1
    assert out[0]["title"].startswith("Res. exenta CP 14.658, CP 24.861 y CP 30.001/2026 · Servicios de Salud "
                                      "Araucanía Norte, Araucanía Sur y Aconcagua · ")
