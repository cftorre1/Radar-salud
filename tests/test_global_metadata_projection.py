"""Metadata requalification must never alter live dates or source evidence."""
import copy
import json
from pathlib import Path
import pytest
from scripts.requalify_global_metadata import assert_metadata_projection

def pair():
    original=json.loads(Path('data/global_intelligence/discovery.json').read_text())
    projected=copy.deepcopy(original);projected['network_requests']=0;projected['mode']='projection_replay'
    return original,projected

def test_projection_accepts_existing_verified_metadata_without_publisher_requests():
    before,after=pair();assert_metadata_projection(before,after)

@pytest.mark.parametrize('change',[
    lambda p:p['items'][0].update(published_at='1900-01-01'),
    lambda p:p['items'][0]['index_evidence'][0].update(body_sha256='unverified'),
    lambda p:p['items'][0]['source_aliases'].append('https://www.paho.org/unverified'),
    lambda p:p['source_health']['who'].update(checked_at='2026-10-11T23:00:00Z'),
    lambda p:p['source_health']['paho'].update(recurrent_operation_proven=True),
    lambda p:p['source_health']['reuters'].update(material_items=999),
    lambda p:p['source_health'].update(rogue={}),
])
def test_projection_rejects_rejuvenated_dates_receipts_identity_and_cadence(change):
    before,after=pair();change(after)
    with pytest.raises(ValueError):assert_metadata_projection(before,after)
