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
    listed = {r["url"] for c in out for k in ("bill_history", "same_event_sources") for r in c.get(k) or []}
    assert removed <= listed
    assert fd.apply(out) == out  # idempotent
