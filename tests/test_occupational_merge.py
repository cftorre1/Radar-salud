"""Merged counts come from unique, dated rows rather than summed surfaces."""
import copy

import pytest

from radar_salud.models import RawItem
from radar_salud.occupational_recovery import _merge

AS_OF = '2026-10-11'
URL = 'https://clinicaportada.cl/nuevo-pabellon/'


def row(url=URL, published='2026-10-10', status='candidate', role='provider_achs'):
    return {'url': url, 'title': 'Nueva capacidad clínica verificada', 'publication_date': published,
            'event_date': published, 'status': status, 'market_role': role,
            'within_30_days': True, 'within_90_days': True}


def raw(url=URL, published='2026-10-10'):
    return RawItem('clinicas_achs_salud', 'Nueva capacidad clínica verificada', url,
                   'Clínica Portada', 'corporate', event_date=published)


def report(rows, raws=(), *, surface='initial', complete=True, as_of=AS_OF):
    return {'source_slug': 'clinicas_achs_salud', 'surface_slug': surface, 'as_of': as_of,
            'rows': copy.deepcopy(rows), 'raw_items': list(raws), 'pages': [], 'errors': [],
            'coverage_complete': complete, 'technical_status': 'ok',
            'metrics': {str(days): {'dated_articles': 100, 'expected_role': 100, 'candidates': 100,
                                    'rejected': 100, 'pending': 100, 'unknown_date_items': 100}
                        for days in (30, 90)}}


def test_duplicate_surfaces_keep_one_url_and_count_it_once_for_each_window():
    first = report([row()], [raw()])
    extra = report([row(), row()], [raw(), raw()], surface='achs_clinics_network')
    merged = _merge(first, extra)
    assert len(merged['rows']) == len(merged['raw_items']) == 1
    for metrics in merged['metrics'].values():
        assert metrics['dated_articles'] == metrics['expected_role'] == metrics['candidates'] == 1
        assert metrics['rejected'] == metrics['pending'] == metrics['unknown_date_items'] == 0
    assert merged['unknown_publication_dates'] == 0


def test_repeated_merge_does_not_inflate_existing_duplicates_or_counts():
    first = report([row(), row()], [raw(), raw()])
    for surface in ('blog', 'clinic_network', 'replay'):
        first = _merge(first, report([row()], [raw()], surface=surface))
    assert len(first['rows']) == len(first['raw_items']) == 1
    assert first['metrics']['90']['dated_articles'] == 1
    assert set(first['surface_reports']) == {'blog', 'clinic_network', 'replay'}


def test_raw_items_deduplicate_independently_of_whether_a_row_preexisted():
    first = report([row()], [])
    merged = _merge(first, report([row()], [raw(), raw()], surface='clinic_network'))
    assert len(merged['rows']) == len(merged['raw_items']) == 1


def test_metrics_recompute_dates_status_roles_and_inclusive_boundaries():
    rows = [row(), row(URL + 'thirty', '2026-09-11', 'rejected', 'provider_achs_centers'),
            row(URL + 'ninety', '2026-07-13', 'excluded_role', 'mutuality'),
            row(URL + 'old', '2026-07-12', 'outside_window'),
            row(URL + 'pending', '2026-10-09', 'pending'),
            row(URL + 'unknown', None, 'pending'), row(URL + 'future', '2026-10-12')]
    merged = _merge(report(rows), report([row()], surface='extra', complete=False))
    assert merged['metrics']['30'] == {
        'start': '2026-09-11', 'end': AS_OF, 'dated_articles': 3, 'expected_role': 3,
        'candidates': 1, 'rejected': 1, 'excluded_role': 0, 'pending': 1,
        'unknown_date_items': 2, 'complete': False}
    assert merged['metrics']['90'] == {
        'start': '2026-07-13', 'end': AS_OF, 'dated_articles': 4, 'expected_role': 3,
        'candidates': 1, 'rejected': 1, 'excluded_role': 1, 'pending': 1,
        'unknown_date_items': 2, 'complete': False}
    assert merged['rows'][3]['within_90_days'] is False
    assert merged['rows'][-1]['within_30_days'] is False
    assert merged['technical_status'] == 'partial' and not merged['coverage_complete']


def test_event_date_or_stale_true_flags_do_not_substitute_for_publication_date():
    undated = row(published=None, status='pending')
    undated['event_date'] = '2026-10-10'
    merged = _merge(report([undated]), report([], surface='extra'))
    assert merged['metrics']['90']['dated_articles'] == 0
    assert merged['metrics']['90']['unknown_date_items'] == 1
    assert merged['rows'][0]['within_90_days'] is False
    assert not merged['coverage_complete'] and merged['technical_status'] == 'partial'


def test_different_as_of_days_are_rejected_before_mutating_either_report():
    first = report([row()])
    original = copy.deepcopy(first)
    with pytest.raises(ValueError, match='as_of'):
        _merge(first, report([row()], surface='extra', as_of='2026-10-10'))
    assert first == original


def test_two_verified_dates_for_same_url_preserve_both_evidences_and_remove_raw():
    first_row, extra_row = row(published='2026-09-24'), row(published='2026-10-01')
    for item, listing in ((first_row, 'https://clinicaportada.cl/noticias/'),
                          (extra_row, 'https://clinicaportada.cl/feed/')):
        item['listing_url'] = listing
        item['date_evidence'] = 'article:published_time'
        item['publication_evidence'] = {'kind': 'article:published_time', 'url': URL,
                                       'value': item['publication_date'], 'date': item['publication_date']}
    merged = _merge(report([first_row], [raw(published='2026-09-24')]),
                    report([extra_row], [raw(published='2026-10-01')], surface='clinic_network'))
    assert len(merged['rows']) == 1 and merged['raw_items'] == []
    item = merged['rows'][0]
    assert item['status'] == 'pending' and item['reason'] == 'merged_publication_date_conflict'
    assert item['publication_date'] is None and item['event_date'] is None
    assert item['publication_evidence'] is None
    assert [observation['publication_date'] for observation in item['publication_date_observations']] == ['2026-09-24', '2026-10-01']
    assert [observation['publication_evidence'] for observation in item['publication_date_observations']] == [first_row['publication_evidence'], extra_row['publication_evidence']]
    assert not merged['coverage_complete'] and merged['technical_status'] == 'partial'
    assert all(metrics['dated_articles'] == metrics['candidates'] == 0 for metrics in merged['metrics'].values())
    assert merged['unknown_publication_dates'] == 1
    assert merged['errors'][0]['verified_dates'] == ['2026-09-24', '2026-10-01']


def test_merge_conflict_survives_repeated_reconciliation_with_one_matching_date():
    merged = _merge(report([row(published='2026-09-24')], [raw()]),
                    report([row(published='2026-10-01')], [raw()], surface='first'))
    merged = _merge(merged, report([row(published='2026-10-01')], [raw()], surface='second'))
    assert merged['rows'][0]['status'] == 'pending' and not merged['raw_items']
    assert len(merged['rows'][0]['publication_date_observations']) == 2
    assert len([error for error in merged['errors'] if error['code'] == 'merged_publication_date_conflict']) == 1
    assert not merged['coverage_complete']


def test_pending_or_unverifiable_ledger_row_cannot_keep_raw_from_another_surface():
    for item in (row(published=None, status='pending'), row(published='2026-10-12')):
        merged = _merge(report([item]), report([item], [raw()], surface='clinic_network'))
        assert not merged['raw_items'] and not merged['coverage_complete']
