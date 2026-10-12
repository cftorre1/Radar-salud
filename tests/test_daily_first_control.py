from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from radar_salud.daily_first import (SurfaceHeld, monitor_scope, controlled_download,
                                    annotate_health, freshness)
from radar_salud.pending_queue import atomic_json

NOW=datetime(2026,10,12,4,14,tzinfo=timezone.utc)
URL='https://www.fonasa.gob.cl/noticias/'


def test_two_equivalent_failures_stop_loss_and_one_controlled_probe_after_24h(tmp_path):
    attempts=[]
    def fail():
        attempts.append(1)
        raise HTTPError(URL,403,'Forbidden',{},None)
    with monitor_scope(tmp_path,'fonasa',now=NOW) as monitor:
        for _ in range(2):
            with pytest.raises(HTTPError):controlled_download(URL,'fonasa',fail)
        with pytest.raises(SurfaceHeld):controlled_download(URL,'fonasa',fail)
    assert len(attempts)==2 and len(monitor['held'])==1
    with monitor_scope(tmp_path,'fonasa',now=NOW+timedelta(hours=23)):
        with pytest.raises(SurfaceHeld):controlled_download(URL,'fonasa',fail)
    with monitor_scope(tmp_path,'fonasa',now=NOW+timedelta(hours=24)):
        with pytest.raises(HTTPError):controlled_download(URL,'fonasa',fail)
        with pytest.raises(SurfaceHeld):controlled_download(URL,'fonasa',fail)
    assert len(attempts)==3
    with monitor_scope(tmp_path,'fonasa',now=NOW+timedelta(hours=48)):
        assert controlled_download(URL,'fonasa',lambda:'recovered')=='recovered'
    state=json.loads((tmp_path/'data/state/daily_first_surfaces.json').read_text())
    assert next(iter(state.values()))['equivalent_failures']==0


def test_failure_change_resets_equivalence_and_does_not_hold_independent_surface(tmp_path):
    with monitor_scope(tmp_path,'fonasa',now=NOW):
        for status in (403,404):
            with pytest.raises(HTTPError):controlled_download(URL,'fonasa',lambda:(_ for _ in ()).throw(HTTPError(URL,status,'Error',{},None)))
        assert controlled_download('https://www.fonasa.gob.cl/feed/','fonasa',lambda:'ok')=='ok'
        assert controlled_download(URL,'fonasa',lambda:'ok')=='ok'


def test_context_does_not_change_unrelated_sources_or_write_without_runtime_scope(tmp_path):
    assert controlled_download(URL,'fonasa',lambda:'ok')=='ok'
    with monitor_scope(tmp_path,'deis',now=NOW):
        assert controlled_download('https://deis.minsal.cl/','deis',lambda:'ok')=='ok'
    assert not (tmp_path/'data').exists()


def test_www_bare_alias_share_stop_loss_but_gob_domain_is_independent(tmp_path):
    def fail():raise TimeoutError('timed out')
    with monitor_scope(tmp_path,'isp_anamed',now=NOW):
        for host in ('www.ispch.cl','ispch.cl'):
            with pytest.raises(TimeoutError):controlled_download('https://'+host+'/anamed/','isp_anamed',fail)
        with pytest.raises(SurfaceHeld):controlled_download('https://www.ispch.cl/anamed/','isp_anamed',fail)
        assert controlled_download('https://www.ispch.gob.cl/anamed/','isp_anamed',lambda:'ok')=='ok'


def test_http_200_does_not_certify_coverage_and_holds_do_not_refresh_poll_time(tmp_path):
    prior={'checked_at':(NOW-timedelta(hours=25)).isoformat(),'last_signal_at':'2026-10-07'}
    path=tmp_path/'data/source_health.json'
    atomic_json(path,{'sources':{'minsal':dict(prior,published=0),'untouched':{'checked_at':'2020-01-01'}}})
    monitor={'requests':[{'outcome':'captured','last_attempt_at':NOW.isoformat(),'last_successful_capture_at':NOW.isoformat()}],'held':[]}
    annotate_health(tmp_path,'minsal',previous=prior,monitor=monitor,items=[],now=NOW)
    health=json.loads(path.read_text())
    assert not health['sources']['minsal']['coverage_complete']
    assert health['sources']['minsal']['unique_items'] is None
    assert health['sources']['untouched']=={'checked_at':'2020-01-01'}
    annotate_health(tmp_path,'minsal',previous=prior,monitor={'requests':[],'held':[{'url':URL}]},items=[],now=NOW)
    row=json.loads(path.read_text())['sources']['minsal']
    assert row['checked_at']==prior['checked_at']
    assert row['daily_check_state']=='overdue_24h'
    assert row['technical_status']=='held'


def test_known_external_blocker_is_preserved_during_hold(tmp_path):
    prior={'checked_at':NOW.isoformat(),'recovery_outcome':'EXTERNAL_BLOCKER_PROVEN'}
    path=tmp_path/'data/source_health.json'
    atomic_json(path,{'sources':{'fonasa':dict(prior,published=0)}})
    annotate_health(tmp_path,'fonasa',previous=prior,monitor={'requests':[],'held':[{'url':URL}]},items=[],error='SurfaceHeld',now=NOW)
    row=json.loads(path.read_text())['sources']['fonasa']
    assert row['recovery_outcome']=='EXTERNAL_BLOCKER_PROVEN'
    assert row['checked_at']==prior['checked_at']
    assert row['items_recent'] is None


@pytest.mark.parametrize('hours,expected',[(0,'checked_within_24h'),(24,'overdue_24h'),(48,'stale_48h'),(-1,'invalid_future')])
def test_daily_freshness_boundaries(hours,expected):
    assert freshness({'checked_at':(NOW-timedelta(hours=hours)).isoformat()},now=NOW)['daily_check_state']==expected
