import copy
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.robotparser import RobotFileParser

import pytest

from radar_salud.global_discovery_common import CaptureClient, USER_AGENT, canonical_url, publication_day
from radar_salud.global_source_discovery import classify, collect_route, detail_metadata, in_window, parse_paho_index, parse_who_index, reporting_period, verify_item

AS_OF = date(2026,10,11)
PROBES = Path('data/audits/global_source_recovery_2026_10_11/probes')

def test_strict_calendar_windows_do_not_include_the_31st_or_91st_day():
    assert in_window('2026-09-12', AS_OF, 30)
    assert not in_window('2026-09-11', AS_OF, 30)
    assert in_window('2026-07-14', AS_OF, 90)
    assert not in_window('2026-07-13', AS_OF, 90)
    assert not in_window('2026-10-12', AS_OF, 30)

@pytest.mark.parametrize('value', ['2026','September 2026','2026-10-12','n.d.','2026-02-30'])
def test_unknown_period_future_or_invalid_date_never_becomes_publication(value):
    assert publication_day(value, AS_OF) is None

def test_official_dates_keep_source_local_day_and_ignore_capture_day():
    assert publication_day('2026-09-25T23:00:00-04:00', AS_OF) == '2026-09-25'
    assert publication_day('25 septiembre 2026', AS_OF) == '2026-09-25'
    assert publication_day('25 September 2026', AS_OF) == '2026-09-25'

def test_real_who_notifications_distinguish_publication_from_event_start():
    rows=parse_who_index(json.loads((PROBES/'38141711504/who_emergencies_api.body').read_text()),'disease_outbreak_news',AS_OF)
    ebola=rows[1]
    assert ebola['index_published_at']=='2026-10-08'
    assert ebola['event_date'].startswith('2026-05-14')
    assert ebola['event_id']=='2026-E000253'
    assert '/2026-DON619' in ebola['url']

def test_conflicting_api_publication_fields_are_pending():
    payload={'value':[{'Title':'Outbreak', 'ItemDefaultUrl':'/2026-DON620','FormattedDate':'9 October 2026','PublicationDateAndTime':'2026-10-10T15:00:00Z'}]}
    row=parse_who_index(payload,'disease_outbreak_news',AS_OF)[0]
    assert row['index_published_at'] is None
    assert row['publication_date_error']

def test_actual_who_detail_corroborates_official_index_date():
    url='https://www.who.int/news/item/09-10-2026-who-urges-shift-from-institutional-to-community-based-mental-health-care'
    metadata=detail_metadata((PROBES/'38141711504/who_detail.body').read_text(),AS_OF,url)
    assert metadata['publication_dates']==['2026-10-09']
    assert metadata['canonical_url']==url

def test_actual_paho_technical_list_does_not_substitute_epi_week_for_publication():
    rows,next_url=parse_paho_index((PROBES/'38141320771/paho_reports.body').read_text(),'technical_reports',AS_OF,'https://www.paho.org/es/informes-tecnicos')
    assert len(rows)==18 and next_url.endswith('?page=1')
    flu=next(row for row in rows if row['reporting_period'] and row['reporting_period']['week']==37)
    assert flu['index_published_at']=='2026-09-25'
    assert flu['reporting_period']['year'] is None
    assert flu['publication_date_basis']=='official_list_displayed_created_time'

def test_marketing_and_appointments_are_not_material_by_authority_alone():
    assert classify('WHO Youth Council welcomes 2026–2028 members in Berlin','news')['materiality']=='routine'
    assert classify('Chilean Minister elected President','regional_news')['materiality']=='routine'
    assert classify('WHO issues guidelines on community-based mental health care','news')['materiality']=='candidate'

def test_reuters_default_robots_prohibits_even_metadata_automation():
    parser=RobotFileParser();parser.parse((PROBES/'38141320771/reuters_robots.body').read_text().splitlines())
    assert not parser.can_fetch(USER_AGENT,'https://www.reuters.com/business/healthcare-pharmaceuticals/')
    text=(PROBES/'38141320771/reuters_robots.body').read_text()
    assert 'prior written consent' in text and 'data and/or information' in text

def test_who_actual_declared_product_identity_is_allowed():
    parser=RobotFileParser();parser.parse((PROBES/'38141320771/who_robots.body').read_text().splitlines())
    assert parser.can_fetch(USER_AGENT,'https://www.who.int/api/hubs/newsitems')

@pytest.mark.parametrize('url', ['http://www.who.int/news','https://www.who.int.evil.org/news','https://user:secret@www.who.int/news','https://www.reuters.com/business/','https://www.who.int:444/news'])
def test_fetcher_cannot_reach_unapproved_hosts_or_journalism(url):
    with pytest.raises(ValueError): canonical_url(url)

def test_modified_date_and_report_year_cannot_supply_publication_date():
    html='<h1>Report 2025</h1><meta property="article:modified_time" content="2026-10-11"><p>Data 2025</p>'
    result=detail_metadata(html,AS_OF,'https://www.who.int/publications/i/item/test')
    assert not result['publication_dates']

class FakeClient:
    def __init__(self,bodies): self.bodies=bodies;self.calls=[]
    def fetch(self,url):
        self.calls.append(url);value=self.bodies.pop(0)
        if isinstance(value,Exception):raise value
        raw=value.encode();return raw,{'http_status':200,'tls_verified':True,'fetched_at':'2026-10-11T13:00:00Z','body_sha256':hashlib.sha256(raw).hexdigest()}

CARD='<div class="col"><div class="views-field-created"><time datetime="2026-10-09T12:00:00Z">9 Oct 2026</time></div><div class="views-field-title"><a href="/en/news/9-10-2026-test">Material guidelines</a></div></div>'
ROUTE={'format':'paho_html','section':'regional_news','source':'paho','url':'https://www.paho.org/en/news'}

def test_repeating_archive_is_incomplete_not_success():
    html=CARD+'<a rel="next" href="?page=1">Next</a>'
    result=collect_route(FakeClient([html,html]),ROUTE,AS_OF,10)
    assert not result['archive_complete'] and result['stop_reason']=='repeated_pagination_page'

def test_later_http_failure_retains_previous_discoveries():
    html=CARD+'<a rel="next" href="?page=1">Next</a>'
    result=collect_route(FakeClient([html,ValueError('http_403')]),ROUTE,AS_OF,10)
    assert len(result['items'])==1 and not result['archive_complete']
    assert 'http_403' in result['stop_reason']

def test_empty_initial_response_is_not_coverage_proof():
    result=collect_route(FakeClient(['<h1>News</h1>']),ROUTE,AS_OF,10)
    assert not result['archive_complete']

def test_detail_redirect_or_title_mismatch_cannot_verify_content():
    row=parse_paho_index(CARD,'regional_news',AS_OF,ROUTE['url'])[0][0]
    result=verify_item(FakeClient(['<h1>Home page</h1>']),row,AS_OF)
    assert not result['detail_verified'] and result['status']=='pending'
    assert 'index_detail_title_mismatch' in result['technical_error']

def test_conflicting_detail_date_is_retained_but_never_publication_ready():
    row=parse_paho_index(CARD,'regional_news',AS_OF,ROUTE['url'])[0][0]
    result=verify_item(FakeClient(['<h1>Material guidelines</h1><meta property="article:published_time" content="2026-10-08">']),row,AS_OF)
    assert result['published_at'] is None and result['reason']=='index_detail_publication_conflict'
    assert result['publication_ready'] is False

def test_replay_rejects_modified_bytes_and_unverified_tls(tmp_path):
    url='https://www.who.int/news';key=hashlib.sha256(url.encode()).hexdigest()[:24]
    raw=b'original';(tmp_path/(key+'.body')).write_bytes(raw)
    record={'requested_url':url,'final_url':url,'http_status':200,'body_file':key+'.body','body_sha256':hashlib.sha256(raw).hexdigest(),'tls_verified':False}
    (tmp_path/(key+'.json')).write_text(json.dumps(record))
    with pytest.raises(ValueError,match='TLS'):CaptureClient(tmp_path/'out',replay=tmp_path).fetch(url)
    record['tls_verified']=True;(tmp_path/(key+'.json')).write_text(json.dumps(record));(tmp_path/(key+'.body')).write_bytes(b'tampered')
    with pytest.raises(ValueError,match='identity/hash'):CaptureClient(tmp_path/'out',replay=tmp_path).fetch(url)
