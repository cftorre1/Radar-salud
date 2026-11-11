"""Datos page index (Dirección, 3-nov-2026): latest published ficha per family, copied verbatim from the snapshot."""
import json
from pathlib import Path

import pytest

from radar_salud import datos_index as di
from radar_salud import stats_fichas as sf

ROOT = Path(__file__).resolve().parents[1]


def card(family, period, *, kpis=None, feed=None, validation="2026-11-01", status="PASS"):
    ficha = {"id": f"stats-ficha:{family}:{period}", "family": family, "period": period, "status": status,
             "published_at": "2026-10-02", "headline": f"Titular {family}",
             "tabs": [{"id": "total", "label": "Cartera total"}, {"id": "isapres", "label": "Por Isapre"},
                      {"label": ""}, {"label": "Sin id"}],
             "kpis": kpis or [{"id": "a", "label": "A", "value": "1.234"}, {"id": "b", "label": "B", "value": "5,6%"},
                              {"id": "c", "label": "C", "value": "7"}]}
    c = {"piece_id": f"stats-ficha:{family}:{period}", "stats_ficha": ficha, "source_name": "Superintendencia de Salud",
         "display_title": f"Titular {family}", "date_basis": "first_detected", "first_detected_at": "2026-10-02",
         "source_url": "https://example.org/x.xlsx", "radar_score": 72,
         "validation_date": validation, "event_date": "2026-10-02", "share_url": f"data/fichas/{family.lower()}.html"}
    if feed:
        c["feed_date"] = feed
    return c


def test_every_config_family_has_a_known_group():
    reg = sf.load_registry()
    keys = [g["key"] for g in reg["datos"]["groups"]]
    assert [g["label"] for g in reg["datos"]["groups"]] == ["Aseguradores", "Prestadores", "Empleadores y licencias",
                                                            "Sector público"]
    for fam, cfg in reg["families"].items():
        assert cfg.get("group") in keys, fam
    fams = reg["families"]
    assert {f: fams[f]["group"] for f in ("F1", "F2", "F4", "F9")} == dict.fromkeys(("F1", "F2", "F4", "F9"), "aseguradores")
    assert fams["F6"]["group"] == "prestadores" and fams["F3"]["group"] == "empleadores_licencias"


def test_period_short_is_spanish():
    assert di.period_short("2026-08") == "ago 2026"
    assert di.period_short("2026-03") == "mar 2026"
    assert di.period_short("2026-13") is None and di.period_short(None) is None


def test_live_planned_and_pending_rows(tmp_path):
    reg = sf.load_registry()
    out = di.build([card("F1", "2026-08", feed="2026-10-28"), card("F2", "2026-03", kpis=[
        {"id": "resultado", "label": "Resultado", "value": "34.120 MM$"},
        {"id": "ingresos", "label": "Ingresos", "value": "1.091.349 MM$"},
        {"id": "siniestralidad", "label": "Siniestralidad", "value": "82,9%"}])], registry=reg, root=tmp_path)
    rows = {r["family"]: r for r in out["families"]}
    assert list(rows) == list(reg["families"])  # one row per config family, registry order
    f1 = rows["F1"]
    assert f1["state"] == "live" and f1["piece_id"] == "stats-ficha:F1:2026-08"
    assert f1["headline"] == "Titular F1" and f1["period_label"] == "ago 2026" and f1["source"] == "SIS"
    assert f1["updated_on"] == "2026-10-28" and f1["status"] == "current"
    # F1 asks for ids that this fake ficha lacks: nothing is invented.
    assert f1["kpis"] == []
    # datos_kpis picks by id, in config order, values verbatim.
    assert rows["F2"]["kpis"] == [{"id": "siniestralidad", "label": "Siniestralidad", "value": "82,9%"},
                                  {"id": "ingresos", "label": "Ingresos", "value": "1.091.349 MM$"}]
    assert rows["F4"]["state"] == "pending" and "kpis" not in rows["F4"]  # active, no live ficha
    assert rows["F7"]["state"] == "pending" and "headline" not in rows["F7"]  # active since the F7 PR, awaiting review
    for fam in ("F3", "F5", "F8", "F9"):
        assert rows[fam]["state"] == "planned" and "headline" not in rows[fam]


def test_default_kpis_are_the_first_two_and_hold_or_fail_is_not_live(tmp_path):
    reg = json.loads(json.dumps(sf.load_registry()))
    reg["families"]["F1"].pop("datos_kpis")
    out = di.build([card("F1", "2026-08"), card("F6", "2026-06", status="HOLD")], registry=reg, root=tmp_path)
    rows = {r["family"]: r for r in out["families"]}
    assert [k["value"] for k in rows["F1"]["kpis"]] == ["1.234", "5,6%"]
    assert rows["F1"]["updated_on"] == "2026-11-01"  # validation day when there is no feed day
    assert rows["F6"]["state"] == "pending"


def test_newer_hold_marks_updating(tmp_path):
    hold = tmp_path / "data/stats_fichas/hold"
    hold.mkdir(parents=True)
    (hold / "f6_prestadores-2026-06.json").write_text(json.dumps({"period": "2026-06", "errors": ["x"]}))
    out = di.build([card("F6", "2026-06")], root=tmp_path)
    f6 = next(r for r in out["families"] if r["family"] == "F6")
    assert f6["status"] == "current"  # same period is not newer
    (hold / "f6_prestadores-2026-09.json").write_text(json.dumps({"period": "2026-09", "errors": ["x"]}))
    out = di.build([card("F6", "2026-06")], root=tmp_path)
    f6 = next(r for r in out["families"] if r["family"] == "F6")
    assert f6["status"] == "updating" and f6["updating_period_label"] == "sep 2026"


def test_unknown_group_fails_closed(tmp_path):
    reg = json.loads(json.dumps(sf.load_registry()))
    reg["families"]["F3"]["group"] = "otros"
    with pytest.raises(ValueError, match="datos_group_unknown:F3"):
        di.build([], registry=reg, root=tmp_path)


def test_published_index_matches_the_published_snapshot():
    """web/data/datos.json repeats only strings already in the published fichas of radar_today.json."""
    snap = json.loads((ROOT / "web/data/radar_today.json").read_text(encoding="utf-8"))
    pub = json.loads((ROOT / "web/data/datos.json").read_text(encoding="utf-8"))
    fichas = {c["piece_id"]: c["stats_ficha"] for c in snap["signals"] if c.get("stats_ficha")}
    live = [r for r in pub["families"] if r["state"] == "live"]
    assert live and {r["piece_id"] for r in live} <= set(fichas)
    for r in live:
        f = fichas[r["piece_id"]]
        assert r["headline"] == f["headline"] and r["period"] == f["period"]
        shown = {(k["label"], k["value"]) for k in f["kpis"]}
        assert r["kpis"] and all((k["label"], k["value"]) in shown for k in r["kpis"])
        kind = (sf.load_registry()["families"].get(f["family"]) or {}).get("period_kind")
        assert r["period_label"] == di.period_short(f["period"], kind)


def test_export_writes_datos_next_to_the_snapshot():
    src = (ROOT / "scripts/export_web_snapshot.py").read_text(encoding="utf-8")
    assert 'datos_index.build(payload["signals"]' in src and '"datos.json"' in src


def test_card_title_topics_and_feed_row(tmp_path):
    """Dirección 10-nov-2026: descriptive title from the registry, the ficha's tabs verbatim as topics, and the fields of
    the Chile row's date line copied verbatim (nothing invented)."""
    reg = sf.load_registry()
    out = di.build([card("F1", "2026-08", feed="2026-10-28")], registry=reg, root=tmp_path)
    rows = {r["family"]: r for r in out["families"]}
    f1 = rows["F1"]
    assert f1["index_title"] == "Cartera de beneficiarios Isapre"
    # Same rule as the ficha renderer: tabs with a label, in order; id = tab id, else its position among them.
    assert f1["topics"] == [{"id": "total", "label": "Cartera total"}, {"id": "isapres", "label": "Por Isapre"},
                            {"id": "2", "label": "Sin id"}]
    assert f1["share_title"] == "Titular F1"
    assert f1["feed_row"] == {"date_basis": "first_detected", "first_detected_at": "2026-10-02",
                              "event_date": "2026-10-02", "source_name": "Superintendencia de Salud"}
    # A family without index_title falls back to its label; planned rows carry no topics.
    assert rows["F3"]["index_title"] == reg["families"]["F3"]["label"] and "topics" not in rows["F3"]


def test_registry_index_titles_approved_10_nov():
    fams = sf.load_registry()["families"]
    assert {f: fams[f].get("index_title") for f in ("F1", "F2", "F4", "F6", "F7", "F12", "F13", "F14")} == {
        "F1": "Cartera de beneficiarios Isapre", "F2": "Resultados financieros de las Isapres",
        "F4": "Casos GES por problema de salud", "F6": "Prestadores acreditados y reclamos",
        "F7": "Ejecución presupuestaria de Salud", "F12": "Prestaciones bonificadas por Isapre",
        "F13": "Licencias médicas por Isapre", "F14": "GES por patología en Isapres"}


def test_published_topics_are_the_live_fichas_tabs():
    """web/data/datos.json topics repeat the published live ficha's tabs (data/stats_fichas/live/*.json) verbatim."""
    pub = json.loads((ROOT / "web/data/datos.json").read_text(encoding="utf-8"))
    live = {}
    for p in (ROOT / "data/stats_fichas/live").glob("*.json"):
        f = json.loads(p.read_text(encoding="utf-8"))
        live[f"stats-ficha:{f['family']}:{f['period']}"] = f
    rows = [r for r in pub["families"] if r["state"] == "live"]
    assert rows
    for r in rows:
        tabs = [t for t in live[r["piece_id"]]["tabs"] if t.get("label")]
        assert r["topics"] == [{"id": str(t.get("id") or i), "label": t["label"]} for i, t in enumerate(tabs)]
        assert r["index_title"]
