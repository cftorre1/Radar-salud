from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import zipfile

import pytest

from radar_salud.models import RawItem
from radar_salud.minsal_news import bind_minsal, rss_candidates
from radar_salud.pending_queue import PendingQueue, fingerprint
from radar_salud.processing import DeferredProcessing
from radar_salud.scouts import MinsalNewsScout
from radar_salud import public_source_pipeline as pipeline

NOW = datetime(2026,10,12,4,14,tzinfo=timezone.utc)
ARCHIVE = Path(__file__).parents[1]/'data/audits/daily_first_20261012/initial-primary-capture.zip'


def bodies():
    with zipfile.ZipFile(ARCHIVE) as z:
        receipt = json.loads(z.read('capture.json'))
        return {r['url']:z.read(r['body_path']).decode() for r in receipt['probes'] if r.get('body_path')}


def article():
    data = bodies(); url = next(u for u in data if 'acelerador-lineal' in u)
    return RawItem('minsal','Listing old title',url,'Ministerio de Salud','official'), data[url]


def test_real_capture_recovers_four_pending_bodies_and_three_recent_stamps():
    data = bodies()
    scout = MinsalNewsScout(fetcher=lambda u:data[u], now=NOW)
    items = scout.discover()
    assert len(items) == 4
    assert sorted(r.event_date for r in items) == ['2026-10-08']+['2026-10-09']*3
    assert scout.inventory['items_recent'] == 3
    assert not scout.inventory['coverage_complete']
    assert scout.inventory['parse_errors'] == 6  # Six detail bodies not in this initial capture.
    assert all(len(r.metadata['page_text']) > 1800 for r in items)
    assert all(r.metadata['publication_date_evidence']['url'] == r.url for r in items)


@pytest.mark.parametrize('mutation', ['wrong_identity','no_body','only_modified','date_conflict','future'])
def test_bad_article_provenance_never_borrows_navigation_or_incident_dates(mutation):
    raw, html = article()
    if mutation == 'wrong_identity':
        html = html.replace('rel="canonical"', 'rel="another"')
    elif mutation == 'no_body':
        html = html.replace('elementor-widget-theme-post-content','unrelated-recommendation')
    elif mutation == 'only_modified':
        html = html.replace('article:published_time','article:modified_time')
    elif mutation == 'date_conflict':
        html += '<meta property="article:published_time" content="2026-10-08T20:48:24+00:00">'
    else:
        html = html.replace('2026-10-09T20:48:24+00:00','2026-10-13T20:48:24+00:00')
    with pytest.raises(DeferredProcessing):
        bind_minsal(raw, html, now=NOW)


def test_article_body_excludes_related_title_navigation_and_modified_time():
    raw, html = article()
    html += '<nav><h1>FONASA financiamiento presupuesto ley</h1><p>Fecha del hecho 12 octubre 2026</p></nav>'
    html += '<meta property="article:modified_time" content="2026-10-12T01:00:00Z">'
    bound = bind_minsal(raw, html, now=NOW)
    assert 'FONASA financiamiento presupuesto ley' not in bound.metadata['page_text']
    assert 'FONASA financiamiento presupuesto ley' not in bound.title
    assert bound.event_date == '2026-10-09'


def test_rss_stamp_bound_to_detail_and_maximum_window():
    data = bodies(); feed = data['https://www.minsal.cl/category/noticias/feed/']
    candidates = rss_candidates(feed,now=NOW)
    assert len(candidates) == 10
    raw = candidates[0]; raw.metadata['rss_published_at'] = '2026-10-08T20:48:24+00:00'
    with pytest.raises(DeferredProcessing):bind_minsal(raw,data[raw.url],now=NOW)
    with pytest.raises(ValueError):rss_candidates(feed,now=NOW,days=90)


def test_rediscovery_preserves_key_detection_backfill_and_terminal_decisions(tmp_path):
    raw, html = article(); queue = PendingQueue(tmp_path/'queue.json')
    queue.discover('minsal',[raw],now=NOW)
    key = fingerprint(raw); before = json.loads(json.dumps(queue.items[key]))
    bind_minsal(raw,html,now=NOW)
    queue.discover('minsal',[raw],now=NOW)
    repaired = queue.items[key]
    assert repaired['detected_at'] == before['detected_at']
    assert repaired['lane'] == before['lane'] == 'BACKFILL'
    assert repaired['attempts'] == 0
    assert repaired['reason'] == 'minsal_verified_primary_pending_editorial_assessment'
    saved = (tmp_path/'queue.json').read_bytes()
    queue.discover('minsal',[raw],now=NOW)
    assert (tmp_path/'queue.json').read_bytes() == saved
    repaired.update(status='published',reason=None); queue.save()
    raw.title += 'Changed listing'
    queue.discover('minsal',[raw],now=NOW)
    assert queue.items[key]['status'] == 'published'
    assert len(queue.items) == 1


def test_no_ai_response_defers_instead_of_publishing_keyword_fallback(monkeypatch):
    raw, html = article()
    monkeypatch.setattr(pipeline,'fetch_official_html',lambda *a,**k:html)
    monkeypatch.setattr(pipeline,'analyze_official_news',lambda **k:None)
    with pytest.raises(DeferredProcessing,match='pending_editorial_assessment'):
        pipeline.process_minsal(raw,{'slug':'minsal'})
