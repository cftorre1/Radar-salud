from datetime import date

from scripts.send_weekly_digest import build_free_digest,select_weekly_signals


def signal(day='2026-09-22',**changes):
    item=dict(title='Norma relevante',event_date=day,radar_score=75,
              confidence_score=90,source_url='https://example.org/norma',
              what_happened='Cambio completo y sustentado.',validation_status='automatic')
    item.update(changes)
    return item


def test_weekly_digest_requires_recent_material_and_valid_source():
    today=date(2026,9,24)
    for candidate in (signal('2026-09-16'),signal('2026-09-25'),
                      signal(source_url='http://example.org'),signal(radar_score=49),
                      signal(validation_status=None),signal(event_date='2026-09'),
                      signal(what_happened='')):
        assert build_free_digest([candidate],today) is None


def test_weekly_digest_keeps_full_evidence_and_caps_items():
    full='La información completa conserva el desenlace y las condiciones.'
    candidates=[signal(title=f'Señal {i}',what_happened=full) for i in range(7)]
    assert len(select_weekly_signals(candidates,date(2026,9,24)))==5
    digest=build_free_digest(candidates,date(2026,9,24))
    assert full in digest['body']
    assert 'Señal 6' not in digest['body']
    assert 'Señal 0' in digest['body']
