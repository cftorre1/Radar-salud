import copy
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.robotparser import RobotFileParser

import pytest

from radar_salud.global_discovery_common import CaptureClient, USER_AGENT, canonical_url, publication_day
from radar_salud.global_source_discovery import classify, collect_route, detail_metadata, in_window, parse_paho_index, parse_who_index, reporting_period, verify_item
from radar_salud.global_discovery_common import PublicRedirect
from radar_salud.global_native_control import native_control
from radar_salud.global_source_discovery import deduplicate_translations
from scripts.discover_global_sources import cadence_is_valid, health_counts, new_identity_count, window_boundary_verified
from urllib.request import Request

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
    metadata=detail_metadata((PROBES/'38141711504/who_detail.metadata.html').read_text(),AS_OF,url)
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

@pytest.mark.parametrize('value',['2026-10-09Tnot-a-time','2026-10-09T25:30:00Z','2026-10-09T12:00:00+99:99'])
def test_malformed_timestamp_cannot_be_truncated_to_a_valid_day(value):
    assert publication_day(value,AS_OF) is None

@pytest.mark.parametrize('value',['2026-12-01','2026-10-09Tnot-a-time',''])
def test_any_invalid_detail_publication_field_keeps_candidate_pending(value):
    row=parse_paho_index(CARD,'regional_news',AS_OF,ROUTE['url'])[0][0]
    html=f'<h1>Material guidelines</h1><meta property="article:published_time" content="2026-10-09"><meta name="citation_publication_date" content="{value}">'
    result=verify_item(FakeClient([html]),row,AS_OF)
    assert result['published_at'] is None and result['status']=='pending'
    assert result['reason']=='invalid_or_future_detail_publication_field'
    assert not health_counts([result],AS_OF)['30']

def test_each_redirect_checks_destination_robots_before_following(tmp_path):
    client=CaptureClient(tmp_path);policy=RobotFileParser();policy.parse(['User-agent: *','Disallow: /private/'])
    client.robots['https://www.paho.org']=policy
    request=Request('https://www.who.int/news');request._global_redirect_chain=[]
    with pytest.raises(ValueError,match='robots_disallowed'):
        PublicRedirect(client).redirect_request(request,None,302,'Found',{},'https://www.paho.org/private/item')
    assert client.network_requests==0 and request._global_redirect_chain==[]
    result=PublicRedirect(client).redirect_request(request,None,301,'Moved',{},'https://www.paho.org/en/news')
    assert result.full_url=='https://www.paho.org/en/news'
    assert result._global_redirect_chain[0]['destination_robots_checked'] is True
    assert result._global_redirect_chain[0]['http_status']==301

def test_final_capture_identity_must_match_requested_item():
    row=parse_paho_index(CARD,'regional_news',AS_OF,ROUTE['url'])[0][0]
    class Redirected(FakeClient):
        def fetch(self,url):
            raw,capture=super().fetch(url);capture['final_url']='https://www.who.int/news/item/other';return raw,capture
    result=verify_item(Redirected(['<h1>Material guidelines</h1>']),row,AS_OF)
    assert not result['detail_verified'] and 'final_identity' in result['technical_error']

def test_don_live_geography_article_variation_is_narrowly_compatible():
    payload=json.loads((PROBES/'38141711504/who_emergencies_api.body').read_text())
    row=parse_who_index(payload,'disease_outbreak_news',AS_OF)[0]
    h1=json.loads(Path('data/audits/global_source_recovery_2026_10_11/diagnostics/38143343664.json').read_text())[0]['h1'][0]
    item=verify_item(FakeClient([f'<h1>{h1}</h1><div class="date">10 October 2026</div>']),row,AS_OF)
    assert item['detail_verified'] and item['published_at']=='2026-10-10'
    bad=verify_item(FakeClient(['<h1>Different emergency - Russian Federation</h1>']),row,AS_OF)
    assert not bad['detail_verified']

def test_health_counts_verified_details_separately_from_indexed_dates():
    row=parse_paho_index(CARD,'regional_news',AS_OF,ROUTE['url'])[0][0]
    item=verify_item(FakeClient([ValueError('http_403')]),row,AS_OF)
    assert item['index_published_at']=='2026-10-09' and item['published_at']=='2026-10-09'
    assert health_counts([item],AS_OF)=={'30':0,'90':0}

def test_cadence_requires_distinct_successful_live_runs_at_the_configured_interval():
    ledger={'runs':[{'run_id':'prior','mode':'live_discovery','capture_reuse':{'reused_url_count':0},'sources':{'who':{'coverage_completeness':'complete','coverage_contract_id':'contract-A','checked_at':'2026-10-10T13:00:00+00:00'}}}]}
    args=(ledger,'who','2026-10-11T13:00:00+00:00','current')
    assert cadence_is_valid(*args,True,86400,contract_id='contract-A')
    assert not cadence_is_valid(*args,False,86400,contract_id='contract-A')
    assert not cadence_is_valid(*args,True,86400,replay=True,contract_id='contract-A')
    assert not cadence_is_valid(*args,True,86400,contract_id='contract-B')
    assert not cadence_is_valid(ledger,'who','2026-10-11T13:00:00+00:00','prior',True,86400,contract_id='contract-A')
    assert not cadence_is_valid(ledger,'who','2026-10-11T12:59:59+00:00','current',True,86400,contract_id='contract-A')

def test_independent_native_control_measures_real_official_cards_and_detects_omissions(monkeypatch):
    raw=(PROBES/'38141320771/paho_reports.body').read_bytes()
    route=dict(ROUTE,section='technical_reports',url='https://www.paho.org/es/informes-tecnicos')
    control=native_control(raw,route,AS_OF,route['url'])
    rows,_=parse_paho_index(raw.decode(),route['section'],AS_OF,route['url'])
    assert len(control)==18 and {r['url'] for r in control}=={r['url'] for r in rows}
    monkeypatch.setattr('radar_salud.global_source_discovery.parse_paho_index',lambda *args:([],None))
    result=collect_route(FakeClient([CARD]),ROUTE,AS_OF,10)
    assert result['stop_reason']=='independent_native_control_mismatch' and not result['archive_complete']

def test_spanish_material_titles_are_discovered_without_automatic_publication():
    assert classify('Plan Andino de Salud y Cambio Climático 2026–2031','regional_news_es')['materiality']=='candidate'
    assert classify('Semana de Vacunación en las Américas. Informe final','technical_reports')['materiality']=='candidate'
    assert classify('Seminario web de capacitación','regional_news_es')['materiality']=='routine'

def test_only_reciprocal_publisher_language_aliases_merge_and_keep_chile_scope():
    en=parse_paho_index(CARD,'regional_news',AS_OF,ROUTE['url'])[0][0]
    en['index_evidence']=[]
    es=dict(en,url=en['url'].replace('/en/','/es/'),section='chile_news_es',title='Directrices materiales')
    first=verify_item(FakeClient([f'<h1>{en["title"]}</h1><a class="language-link" hreflang="es" href="{es["url"]}">ES</a>']),en,AS_OF)
    second=verify_item(FakeClient([f'<h1>{es["title"]}</h1><a class="language-link" hreflang="en" href="{en["url"]}">EN</a>']),es,AS_OF)
    result=deduplicate_translations([first,second]);assert len(result)==1
    assert len(result[0]['translation_members'])==2
    assert any(e['name']=='Chile' for e in result[0]['entities'])
    second['published_at']='2026-10-08'
    assert deduplicate_translations([first,second])[0]['published_at'] is None
    second['detail_evidence']['metadata']['alternate_language_urls']=[]
    assert len(deduplicate_translations([first,second]))==2

def test_new_counts_compare_prior_identity_and_do_not_reannounce_translations():
    old=[{'source':'paho','url':'en','source_aliases':['en']}]
    items=[{'source_aliases':['en','es']},{'source_aliases':['another']}]
    assert new_identity_count(items,old,'paho')==1
    assert new_identity_count(items,[],'paho')==2

def test_observed_older_date_requires_ordered_boundary_for_window_coverage():
    route={'items':[{'index_published_at':'2026-09-09'},{'index_published_at':'2026-09-01'}]}
    assert window_boundary_verified(route,AS_OF,30)
    assert not window_boundary_verified(route,AS_OF,90)
    route['items'].reverse()
    assert not window_boundary_verified(route,AS_OF,30)


class RateResponse:
    def __init__(self,url,code=429,retry='3600'):
        self.url,self.code,self.headers=url,code,{'Retry-After':retry}
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,*args): return b'rate limited' if self.code==429 else b'<h1>PAHO</h1>'

class RateOpener:
    def __init__(self,retry='3600'): self.calls=[];self.retry=retry
    def open(self,request,**kwargs):
        self.calls.append(request.full_url)
        return RateResponse(request.full_url,429 if 'who.int' in request.full_url else 200,self.retry)

def allow_test_hosts(client):
    policy=RobotFileParser();policy.parse(['User-agent: *','Allow: /'])
    for origin in ('https://www.who.int','https://www.paho.org'): client.robots[origin]=policy

@pytest.mark.parametrize('retry',['3600','Sun, 11 Oct 2037 16:00:00 GMT','invalid'])
def test_429_stops_queued_requests_persists_cooldown_and_preserves_other_source(tmp_path,retry):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime,timezone
    state=tmp_path/'cooldown.json';client=CaptureClient(tmp_path/'first',delay=0,cooldown_file=state)
    allow_test_hosts(client);client.opener=RateOpener(retry)
    def attempt(n):
        try: client.fetch('https://www.who.int/news/item/'+str(n))
        except ValueError as exc: return str(exc)
    with ThreadPoolExecutor(max_workers=3) as pool: outcomes=list(pool.map(attempt,range(8)))
    assert outcomes.count('http_429')==1
    assert sum('deferred_without_request' in value for value in outcomes)==7
    assert len(client.opener.calls)==1 and client.network_requests==1
    assert len(list((tmp_path/'first').glob('*.body')))==1
    persisted=json.loads(state.read_text())['https://www.who.int']
    assert persisted['retry_after']==retry
    assert datetime.fromisoformat(persisted['retry_until'])>datetime.now(timezone.utc)
    client.fetch('https://www.paho.org/en/news')
    assert client.network_requests==2
    second=CaptureClient(tmp_path/'second',delay=0,cooldown_file=state);allow_test_hosts(second);second.opener=RateOpener()
    with pytest.raises(ValueError,match='deferred_without_request'): second.fetch('https://www.who.int/news/item/next')
    assert second.network_requests==0 and not second.opener.calls
    request=Request('https://www.paho.org/en/news');request._global_redirect_chain=[]
    with pytest.raises(ValueError,match='deferred_without_request'):
        PublicRedirect(second).redirect_request(request,None,302,'Found',{},'https://www.who.int/news/item/next')
    assert request._global_redirect_chain==[]

def test_expired_cooldown_allows_normal_access_without_rotating_identity(tmp_path):
    state=tmp_path/'cooldown.json';state.write_text(json.dumps({'https://www.paho.org':{'retry_until':'2020-01-01T00:00:00+00:00'}}))
    client=CaptureClient(tmp_path/'captures',delay=0,cooldown_file=state);allow_test_hosts(client);client.opener=RateOpener()
    client.fetch('https://www.paho.org/en/news')
    assert client.network_requests==1

def test_live_campaign_budget_preserves_evidence_and_denies_new_requests(tmp_path,monkeypatch):
    clock=[100.]
    monkeypatch.setattr('radar_salud.global_discovery_common.time.monotonic',lambda:clock[0])
    client=CaptureClient(tmp_path/'captures',delay=0,live_budget_seconds=10)
    allow_test_hosts(client);client.opener=RateOpener()
    first='https://www.paho.org/en/news/first'
    client.fetch(first)
    clock[0]=110.
    with pytest.raises(ValueError,match='budget_exhausted_without_request'):
        client.fetch('https://www.paho.org/en/news/next')
    assert client.network_requests==1 and client.opener.calls==[first]
    assert client.fetch(first)[1]['requested_url']==first
    request=Request(first);request._global_redirect_chain=[]
    with pytest.raises(ValueError,match='budget_exhausted_without_request'):
        PublicRedirect(client).redirect_request(request,None,302,'Found',{},'https://www.paho.org/en/news/redirect')
    assert request._global_redirect_chain==[] and client.network_requests==1

def test_live_budget_is_rechecked_after_pacing_before_network(tmp_path,monkeypatch):
    clock=[100.]
    monkeypatch.setattr('radar_salud.global_discovery_common.time.monotonic',lambda:clock[0])
    monkeypatch.setattr('radar_salud.global_discovery_common.time.sleep',lambda _:clock.__setitem__(0,110.))
    client=CaptureClient(tmp_path/'captures',live_budget_seconds=10)
    allow_test_hosts(client);client.opener=RateOpener()
    with pytest.raises(ValueError,match='budget_exhausted_without_request'):
        client.fetch('https://www.paho.org/en/news/first')
    assert client.network_requests==0 and not client.opener.calls

def test_replay_never_expires_live_campaign_budget(tmp_path,monkeypatch):
    clock=[100.]
    monkeypatch.setattr('radar_salud.global_discovery_common.time.monotonic',lambda:clock[0])
    client=CaptureClient(tmp_path/'output',replay=tmp_path/'input',live_budget_seconds=10)
    clock[0]=200.
    client.check_live_budget()
    assert client.network_requests==0

def test_redirect_rechecks_live_budget_after_destination_robots(tmp_path,monkeypatch):
    clock=[100.]
    monkeypatch.setattr('radar_salud.global_discovery_common.time.monotonic',lambda:clock[0])
    client=CaptureClient(tmp_path/'captures',delay=0,live_budget_seconds=10)
    monkeypatch.setattr(client,'check_robots',lambda _:clock.__setitem__(0,110.))
    request=Request('https://www.paho.org/en/news');request._global_redirect_chain=[]
    with pytest.raises(ValueError,match='budget_exhausted_without_request'):
        PublicRedirect(client).redirect_request(request,None,302,'Found',{},'https://iris.paho.org/')
    assert request._global_redirect_chain==[] and client.network_requests==0

def test_replay_of_older_429_evidence_never_suppresses_captured_history_or_contacts_network(tmp_path):
    capture=tmp_path/'old';capture.mkdir()
    for url,status in [('https://www.who.int/news/first',429),('https://www.who.int/news/second',200)]:
        key=hashlib.sha256(url.encode()).hexdigest()[:24];raw=b'evidence'
        record={'requested_url':url,'final_url':url,'http_status':status,'fetched_at':'2026-10-11T14:02:51+00:00','tls_verified':True,'body_file':key+'.body','body_sha256':hashlib.sha256(raw).hexdigest(),'headers':{'retry-after':'3600'}}
        (capture/(key+'.body')).write_bytes(raw);(capture/(key+'.json')).write_text(json.dumps(record))
    replay=CaptureClient(tmp_path/'replay',replay=capture,delay=0);allow_test_hosts(replay)
    with pytest.raises(ValueError,match='http_429'): replay.fetch('https://www.who.int/news/first')
    assert replay.fetch('https://www.who.int/news/second')[1]['http_status']==200
    assert replay.network_requests==0 and not replay.cooldowns


class DateArchiveClient:
    def __init__(self,ignore=False,saturated=False,empty=False): self.calls=[];self.ignore=ignore;self.saturated=saturated;self.empty=empty
    def fetch(self,url):
        from urllib.parse import urlsplit,parse_qsl
        from datetime import timedelta
        self.calls.append(url);query=dict(parse_qsl(urlsplit(url).query))
        start=query.get('date[min]','');end=query.get('date[max]','')
        form=f'<form method="get" action="/en/news"><input name="date[min]" value="{start}"><input name="date[max]" value="{end}"></form>'
        if not start: html=form
        elif self.empty: html=form+'<div class="view-empty">No news found.</div>'
        else:
            day=(date.fromisoformat(start)+timedelta(days=1)).isoformat()
            card=CARD.replace('2026-10-09',day).replace('9-10-2026-test',day+'-test')
            html=(form if not self.ignore else '')+card
            if self.saturated and (date.fromisoformat(end)-date.fromisoformat(start)).days>5:
                html+='<a rel="last" href="?page=8">Last</a>'
        raw=html.encode();return raw,{'http_status':200,'tls_verified':True,'fetched_at':'2026-10-11T14:18:00Z','body_sha256':hashlib.sha256(raw).hexdigest()}

def test_official_date_slices_cover_all_90_days_using_card_dates_not_query_dates():
    route=dict(ROUTE,date_slice_days=7)
    result=collect_route(DateArchiveClient(),route,AS_OF,100)
    assert result['archive_complete'] and result['stop_reason']=='verified_date_partition_coverage'
    assert result['date_partitions'][0]['from']=='2026-07-14'
    assert result['date_partitions'][-1]['to']=='2026-10-11'
    assert all(p['native_control'] for p in result['pages'])
    assert window_boundary_verified(result,AS_OF,30) and window_boundary_verified(result,AS_OF,90)
    result['date_partitions'].pop(3)
    assert not window_boundary_verified(result,AS_OF,90)

def test_date_filter_echo_is_required_and_never_substitutes_for_publication():
    result=collect_route(DateArchiveClient(ignore=True),dict(ROUTE,date_slice_days=7),AS_OF,100)
    assert not result['archive_complete']
    assert all(s['stop_reason'].startswith('page_parse_failure') for s in result['date_partitions'])

def test_native_archive_cap_triggers_bounded_date_subdivision_instead_of_claiming_complete():
    result=collect_route(DateArchiveClient(saturated=True),dict(ROUTE,date_slice_days=7),AS_OF,100)
    assert result['archive_complete'] and len(result['date_partitions'])>13
    assert all(s['stop_reason'] in {'date_partition_native_archive_exhausted_after_public_end_probe','verified_older_boundary'} for s in result['date_partitions'])
    limited=collect_route(DateArchiveClient(saturated=True),dict(ROUTE,date_slice_days=7),AS_OF,2)
    assert not limited['archive_complete'] and limited['unvisited_partitions']>0

def test_official_empty_date_partitions_are_explicit_evidence_not_missing_html():
    result=collect_route(DateArchiveClient(empty=True),dict(ROUTE,date_slice_days=7),AS_OF,100)
    assert result['archive_complete'] and not result['items']
    assert all(s['stop_reason']=='date_partition_official_empty' for s in result['date_partitions'])

def test_date_query_cannot_operate_if_official_filter_form_disappears():
    with pytest.raises(ValueError,match='form_missing'):
        collect_route(FakeClient([CARD]),dict(ROUTE,date_slice_days=7),AS_OF,100)

def test_resume_campaign_reuses_verified_bytes_without_fresh_requests_and_rejects_stale_capture(tmp_path):
    first=CaptureClient(tmp_path,delay=0);allow_test_hosts(first);first.opener=RateOpener()
    url='https://www.paho.org/en/news';first.fetch(url)
    second=CaptureClient(tmp_path,delay=0,resume=True);allow_test_hosts(second);second.opener=RateOpener()
    assert second.fetch(url)[0]==b'<h1>PAHO</h1>' and second.network_requests==0
    assert second.reused_urls=={url}
    path=next(tmp_path.glob('*.json'));record=json.loads(path.read_text());record['fetched_at']='2020-01-01T00:00:00+00:00';path.write_text(json.dumps(record))
    with pytest.raises(ValueError,match='one-hour bound'): CaptureClient(tmp_path,resume=True)


@pytest.mark.parametrize('conflict',[False,True])
def test_overlapping_slices_preserve_each_receipt_and_close_on_conflicting_publication(conflict):
    from urllib.parse import parse_qsl,urlsplit
    class Overlap(DateArchiveClient):
        def fetch(self,url):
            raw,capture=super().fetch(url);query=dict(parse_qsl(urlsplit(url).query))
            start=query.get('date[min]')
            if start in {'2026-07-13','2026-07-20'}:
                day='2026-07-19' if conflict and start=='2026-07-13' else '2026-07-20'
                html=raw.decode();html=__import__('re').sub(r'datetime="[^"]+"',f'datetime="{day}T12:00:00Z"',html)
                html=__import__('re').sub(r'/en/news/[^" ]+', '/en/news/shared',html)
                raw=html.encode();capture['body_sha256']=hashlib.sha256(raw).hexdigest()
            return raw,capture
    result=collect_route(Overlap(),dict(ROUTE,date_slice_days=7),AS_OF,100)
    row=next(r for r in result['items'] if r['url'].endswith('/shared'))
    assert len(row['index_evidence'])>=4
    assert row['index_published_at']==(None if conflict else '2026-07-20')
    if conflict:
        assert row['publication_date_error']=='conflicting_official_listing_dates' and result['date_pending']==1
        observed=[r['index_published_at'] for page in result['pages'] for r in page['items'] if r['url'].endswith('/shared')]
        assert '2026-07-19' in observed and '2026-07-20' in observed and None not in observed

def test_cadence_prior_resume_or_legacy_unknown_provenance_never_proves_recurrence():
    row={'run_id':'prior','mode':'live_resume','capture_reuse':{'reused_url_count':5},'sources':{'who':{'coverage_completeness':'complete','coverage_contract_id':'A','checked_at':'2026-10-10T13:00:00+00:00'}}}
    args=({'runs':[row]},'who','2026-10-11T13:00:00+00:00','next',True,86400)
    assert not cadence_is_valid(*args,contract_id='A')
    row.pop('mode');row.pop('capture_reuse');assert not cadence_is_valid(*args,contract_id='A')
    row.update(mode='live_discovery',capture_reuse={'reused_url_count':0});assert cadence_is_valid(*args,contract_id='A')

def test_resume_rechecks_age_when_receipt_is_used_and_never_recaptures_stale_bytes(tmp_path,monkeypatch):
    from datetime import datetime,timedelta,timezone
    first=CaptureClient(tmp_path,delay=0);allow_test_hosts(first);first.opener=RateOpener()
    url='https://www.paho.org/en/news';first.fetch(url)
    second=CaptureClient(tmp_path,delay=0,resume=True);allow_test_hosts(second);second.opener=RateOpener()
    stamp=datetime.fromisoformat(first.records[url]['fetched_at'])
    class Later(datetime):
        @classmethod
        def now(cls,tz=None): return stamp+timedelta(hours=2)
    monkeypatch.setattr('radar_salud.global_discovery_common.datetime',Later)
    with pytest.raises(ValueError,match='one-hour bound'): second.fetch(url)
    assert second.network_requests==0 and not second.opener.calls
