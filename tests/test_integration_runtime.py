from scripts.integration_runtime import validate_discovery
import pytest


def test_missing_or_stale_source_receipt_is_not_live_success():
    for rows in ({}, {'sis': {'checked_at':'2026-10-10T01:00:00Z','discovered':10,'technical_status':'ok'}}):
        with pytest.raises(AssertionError):
            validate_discovery({'sources':['sis']},{'sources':rows},'2026-10-11T00:00:00Z')


def test_errors_are_only_preserved_as_explicit_blockers():
    receipt={'sources':{'isp':{'checked_at':'2026-10-11T01:00:00Z','discovered':0,'technical_status':'error','error_type':'TimeoutError'}}}
    with pytest.raises(AssertionError):
        validate_discovery({'sources':['isp']},receipt,'2026-10-11T00:00:00Z')
    assert validate_discovery({'sources':['isp'],'expectations':{'isp':{'allow_external_blocker':True}}},receipt,'2026-10-11T00:00:00Z') == {'isp':'EXTERNAL_BLOCKER_OBSERVED'}


def test_http_success_without_capture_is_not_operative():
    receipt={'sources':{'sis':{'checked_at':'2026-10-11T01:00:00Z','discovered':0,'technical_status':'ok'}}}
    with pytest.raises(AssertionError):
        validate_discovery({'sources':['sis']},receipt,'2026-10-11T00:00:00Z')
    receipt['sources']['sis']['discovered']=2
    assert validate_discovery({'sources':['sis']},receipt,'2026-10-11T00:00:00Z') == {'sis':'EXECUTED_WITH_CAPTURE'}
