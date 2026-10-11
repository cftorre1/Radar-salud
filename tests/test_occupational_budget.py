import copy
import pytest
from radar_salud.occupational_budget import BASELINE,reconcile_budget


def add(ledger,n):
    d=copy.deepcopy(ledger)
    for metric in ('attempted','successful'):d['fast'][metric]+=n
    return d


def test_sequential_divergent_staging_and_isolated_calls_are_added_without_loss():
    local=add(BASELINE,10)
    total,receipt=reconcile_budget(local,BASELINE)
    assert total['fast']['attempted']==41
    total,receipt=reconcile_budget(total,add(BASELINE,20),receipt)
    assert total['fast']['attempted']==61
    repeated,_=reconcile_budget(total,add(BASELINE,20),receipt)
    assert repeated==total
    total,receipt=reconcile_budget(add(total,3),add(BASELINE,20),receipt)
    assert total['fast']['attempted']==64
    assert receipt['isolated_delta']['fast']['attempted']==13


def test_invalid_or_regressing_upstream_fails_closed():
    _,receipt=reconcile_budget(add(BASELINE,5),BASELINE)
    bad=copy.deepcopy(BASELINE);bad['fast']['attempted']=30
    with pytest.raises(ValueError,match='regressed'):reconcile_budget(add(BASELINE,5),bad,receipt)
    bad['fast']['attempted']='31'
    with pytest.raises(ValueError,match='invalid'):reconcile_budget(BASELINE,bad)


def test_processing_requires_durable_phase_receipt_and_never_reopens_used_capacity(tmp_path,monkeypatch):
    import json
    from radar_salud.occupational_budget import remaining_phase_calls
    path=tmp_path/'receipt.json'
    monkeypatch.setattr('radar_salud.occupational_budget.receipt_path',lambda:path)
    with pytest.raises(RuntimeError,match='receipt missing'):remaining_phase_calls()
    for attempted,expected in ((5,25),(29,1),(30,0),(31,0)):
        path.write_text(json.dumps({'phase_fast_limit':30,'isolated_delta':{'fast':{'attempted':attempted}}}))
        assert remaining_phase_calls()==expected
