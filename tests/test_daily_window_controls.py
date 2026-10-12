import json
from datetime import date
from urllib.parse import parse_qs, urlparse
import pytest
from radar_salud.daily_window import eligible_daily_item, requested_window_days
from radar_salud.pulso_source import discover_public_feeds
from test_pulso_archive_discovery import ans_feed, html_article

@pytest.mark.parametrize('published,expected', [('2026-09-12',True),('2026-09-11',False),('2026-10-12',True),('2026-10-13',False),(None,False),('invalid',False)])
def test_daily_processing_date_boundary_preserves_input(published,expected):
    item={'raw':{'event_date':published},'lane':'BACKFILL','detected_at':'2026-09-01T00:00:00Z'}
    original=json.dumps(item)
    assert eligible_daily_item(item,today=date(2026,10,12),days=30) is expected
    assert json.dumps(item)==original

def test_historical_default_and_invalid_window(monkeypatch):
    monkeypatch.delenv('RADAR_DAILY_WINDOW_DAYS',raising=False)
    assert requested_window_days()==90
    monkeypatch.setenv('RADAR_DAILY_WINDOW_DAYS','30')
    assert requested_window_days()==30
    monkeypatch.setenv('RADAR_DAILY_WINDOW_DAYS','0')
    with pytest.raises(ValueError): requested_window_days()

def test_daily_frontend_stops_at_30_day_boundary_and_keeps_history(tmp_path):
    cache=tmp_path/'cache.json'
    cache.write_text(json.dumps({'version':1,'articles':{'historical-proof':{'immutable':True}}}))
    offsets=[]
    def loader(url):
        if '/canal/' in url:return 'Fusion.deployment="1284";'
        if '/pf/api/' in url:
            offset=json.loads(parse_qs(urlparse(url).query)['query'][0])['feedOffset'];offsets.append(offset)
            assert offset<=72, 'Daily mode traversed beyond its verified boundary'
            return ans_feed(offset,day='2026-10-09' if offset==0 else '2026-09-01')
        number=int(url.rstrip('/').rsplit('-',1)[1])
        return html_article(url,day='2026-10-09' if number<24 else '2026-09-01')
    items,receipt=discover_public_feeds(loader,[],cache,today=date(2026,10,12),feeds=[('section','nacional')],window_days=30)
    assert offsets==[0,24,48,72] and len(items)==24
    assert receipt['coverage_complete'] and receipt['window_days']==30
    assert receipt['complete_90_days'] is None
    assert json.loads(cache.read_text())['articles']['historical-proof']=={'immutable':True}

def test_global_candidates_above_ten_remain_pending_and_deduplicated():
    from scripts.discover_global_sources import editorial_topics
    rows=[{'url':f'https://www.who.int/item/{i}','title':str(i),'event_id':str(i),'published_at':'2026-10-10','detail_verified':True,'classification':{'materiality':'candidate','priority':80}} for i in range(14)]
    rows.append({**rows[0],'url':'https://www.paho.org/duplicate'})
    topics=editorial_topics(rows,date(2026,10,12))
    assert len(topics)==14
    assert all(t['status']=='pending_editorial' and t['publication_ready'] is False for t in topics)
    assert len(next(t for t in topics if 'https://www.who.int/item/0' in t['related_discovered_urls'])['related_discovered_urls'])==2
