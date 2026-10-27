from src.radar_salud.engine_cli import _prioritize_official


def _item(source, lane):
    return {"source": source, "lane": lane, "attempts": 0}


def test_official_backfill_precedes_press_live_and_orders_are_stable():
    ready = [("p1", _item("pulso_latercera", "LIVE")), ("d1", _item("diario_financiero", "LIVE")),
             ("s1", _item("superintendencia_normativa", "BACKFILL")), ("p2", _item("pulso_latercera", "LIVE")),
             ("u1", _item("suseso_fiscalizacion", "BACKFILL")), ("s2", _item("superintendencia_normativa", "BACKFILL"))]
    assert [k for k, _ in _prioritize_official(ready)] == ["s1", "u1", "s2", "p1", "d1", "p2"]


def test_nothing_is_dropped():
    ready = [(str(i), _item("pulso_latercera" if i % 2 else "minsal", "LIVE")) for i in range(9)]
    assert sorted(k for k, _ in _prioritize_official(ready)) == sorted(k for k, _ in ready)
