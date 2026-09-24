from src.radar_salud.newsletter import render_free_weekly,weekly_material


def signal(**changes):
    item=dict(title='Norma relevante',event_date='2026-09-22',ingestion_mode='LIVE',radar_score=75,
              confidence_score=90,source_url='https://example.org/norma',
              what_happened='Cambio completo y sustentado.',validation_status='automatic')
    item.update(changes)
    return item


def test_weekly_digest_requires_recent_material_and_valid_source():
    for candidate in (signal(event_date='2026-09-16'),signal(event_date='2026-09-25'),
                      signal(ingestion_mode='BACKFILL'),signal(source_url='http://example.org'),
                      signal(radar_score=69),signal(radar_score='invalid'),
                      signal(confidence_score='invalid'),signal(validation_status=None),signal(event_date='2026-09'),
                      signal(what_happened='')):
        assert weekly_material([candidate],'2026-09-24')==[]


def test_weekly_digest_keeps_full_evidence_and_caps_items():
    full='La información completa conserva el desenlace y las condiciones.'
    candidates=[signal(title=f'Señal {i}',what_happened=full) for i in range(7)]
    digest=render_free_weekly(weekly_material(candidates,'2026-09-24'),'2026-09-24')
    assert full in digest[1] and digest[1].count(full)==5
    assert 'Señal 6' not in digest[1]


def test_scores_from_json_are_ordered_numerically():
    candidates=[signal(title='Bajo',radar_score='75'),signal(title='Alto',radar_score=80)]
    selected=weekly_material(candidates,'2026-09-24')
    assert [row['title'] for row in selected]==['Alto','Bajo']
