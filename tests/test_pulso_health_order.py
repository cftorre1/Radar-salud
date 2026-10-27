from src.radar_salud.engine_cli import _prioritize_pulso_ready


def _p(key, title, day):
    return (key, {"source": "pulso_latercera", "lane": "LIVE", "attempts": 0,
                  "raw": {"title": title, "event_date": day}})


def test_health_items_first_inside_pulso_slot_without_dropping():
    ready = [_p("a", "Colo-Colo gana el clásico", "2026-10-25"),
             _p("b", "Isapres enfrentan nueva alza de costos", "2026-10-20"),
             ("m", {"source": "minsal", "lane": "LIVE", "attempts": 0, "raw": {"title": "x", "event_date": "2026-10-24"}}),
             _p("c", "Kast firma convenio para agilizar listas de espera", "2026-10-22"),
             _p("d", "Bolsa cierra al alza", "2026-10-26")]
    out = [k for k, _ in _prioritize_pulso_ready(ready)]
    assert sorted(out) == sorted(k for k, _ in ready)          # nothing dropped
    assert out[2] == "m"                                        # other sources keep their slot
    pulso = [k for k in out if k != "m"]
    assert pulso == ["c", "b", "d", "a"]                        # health first, then newest first
