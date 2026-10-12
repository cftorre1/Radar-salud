"""A recovery cohort explains untouched backlog without editorial decisions."""
import copy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('pulse_selection_audit', Path(__file__).parents[1] / 'scripts/audit_pulso_runtime.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)

URL = 'https://www.latercera.com/pulso/noticia/presupuesto-salud/'
OTHER = 'https://www.latercera.com/nacional/noticia/otra-noticia/'


def report():
    return dict(matrix=[dict(url=url, editorial_outcome='pending', exact_reason='not_processed; no_editorial_verdict',
                           queue=[dict(status='pending', publication_date='2026-10-07')]) for url in (URL, OTHER)])


def test_only_observed_unselected_pending_get_operational_reason_with_no_editorial_rejection():
    value = report()
    audit.annotate_pending(value, dict(mode='real_core_processing', engine_completed=True,
        finished_at='2026-10-11T13:00:00+00:00', processing_selection=dict(
            source='pulso_latercera', sha256='a'*64, selected_urls=[URL])))
    selected, excluded = value['matrix']
    assert selected['exact_reason'] == 'not_processed; no_editorial_verdict'
    assert selected['operational_reason_unresolved'] is True
    assert excluded['exact_reason'] == 'processing_not_attempted:explicit_queue_selection_excluded'
    assert excluded['editorial_outcome'] == 'pending'
    assert excluded['queue'][0]['status'] == 'pending'
    assert excluded['processing_selection_evidence'] == dict(sha256='a'*64, selected=False, source='pulso_latercera')
    assert value['unresolved_pending_operational_reasons'] == [URL]


@pytest.mark.parametrize('change', [dict(source='minsal'), dict(sha256=None), dict(selected_urls=None)])
def test_unproven_or_wrong_source_selection_cannot_explain_unprocessed_articles(change):
    value = report()
    selection = dict(source='pulso_latercera', sha256='a'*64, selected_urls=[URL]); selection.update(change)
    audit.annotate_pending(value, dict(mode='real_core_processing', engine_completed=True,
                                    processing_selection=selection))
    assert value['unresolved_pending_operational_reasons'] == [URL, OTHER]


def test_selection_cannot_hide_a_real_failed_core_execution():
    value = report()
    original = copy.deepcopy(value)
    audit.annotate_pending(value, dict(mode='real_core_processing', engine_called=True, engine_completed=False,
        error_type='RuntimeError', processing_selection=dict(source='pulso_latercera', sha256='a'*64, selected_urls=[URL])))
    assert all(row['exact_reason'] == 'processing_not_completed:runtime_error:RuntimeError' for row in value['matrix'])
    assert [row['queue'] for row in value['matrix']] == [row['queue'] for row in original['matrix']]
    assert all(row['editorial_outcome'] == 'pending' for row in value['matrix'])
