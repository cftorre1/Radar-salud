"""Small robots-respecting official metadata diagnostic; no Reuters requests."""
import json
import os
from datetime import date
from pathlib import Path
from radar_salud.global_discovery_common import CaptureClient, Document

client = CaptureClient(Path('work/global-diagnostic-captures'))
rows = []
targets = ['https://www.paho.org/en/news?date%5Bmin%5D=2026-07-14&date%5Bmax%5D=2026-09-11',
           'https://www.paho.org/es/noticias?date%5Bmin%5D=2026-07-14&date%5Bmax%5D=2026-09-11',
           'https://www.paho.org/es/noticias?date%5Bmin%5D=2026-09-12&date%5Bmax%5D=2026-09-18',
           'https://iris.paho.org/']
for url in targets:
    try:
        raw, capture = client.fetch(url)
        doc = Document(raw.decode(errors='replace')).root
        if url == 'https://www.paho.org/sitemap.xml':
            targets.extend(n.text() for n in doc.nodes('loc') if n.text().startswith('https://www.paho.org/sitemap.xml?page='))
        locations = [n.text() for n in doc.nodes('loc')]
        news_locations = [u for u in locations if '/news/' in u or '/noticias/' in u]
        recent_hints = []
        for location in news_locations:
            import re
            match = re.search(r'/(\d{1,2})-(\d{1,2})-(2026)-', location)
            if match:
                try:
                    hint = date(int(match[3]),int(match[2]),int(match[1]))
                    if date(2026,7,14) <= hint <= date(2026,10,11): recent_hints.append(location)
                except ValueError: pass
        rows.append({'url': url, 'capture': capture,
            'h1': [n.text() for n in doc.nodes('h1')],
            'dates': [n.text() for n in doc.nodes() if n.has_class('date')],
            'publication_meta': [n.attrs for n in doc.nodes('meta') if 'publish' in str(n.attrs).lower()],
            'pager': [{'text': n.text(), 'attrs': n.attrs} for n in doc.nodes('a')
                      if 'page=' in n.attrs.get('href', '')],
            'filters': [n.attrs for n in doc.nodes('select')],
            'form_fields': [n.attrs for n in doc.nodes('input') if n.attrs.get('name','').startswith('date')],
            'official_repository_api_links': [n.attrs for n in doc.nodes() if n.tag in ('link','script','a') and any(x in str(n.attrs).lower() for x in ('/server/api','/rest','iris.paho'))],
            'chile_option': [n.attrs for n in doc.nodes('option') if n.text() == 'Chile'],
            'sitemap_locations': locations if not news_locations else [],
            'sitemap_total_urls': len(locations), 'sitemap_news_urls': len(news_locations),
            'sitemap_news_sample': news_locations[:5]+news_locations[-5:],
            'recent_url_date_hints_not_publication_dates': recent_hints,
            'cards': [{'title':n.text(),'urls':[a.attrs.get('href') for a in n.nodes('a')]} for n in doc.nodes() if n.has_class('views-field-title')],
            'times': [n.attrs.get('datetime') for n in doc.nodes('time')],
            'feed_count': sum(1 for _ in doc.nodes('item')),
            'feed_publication_dates': [n.text() for n in doc.nodes('pubdate')],
            'card_count': sum(n.has_class('views-field-title') for n in doc.nodes())})
    except Exception as exc:
        rows.append({'url': url, 'error': str(exc)})
path = Path('data/audits/global_source_recovery_2026_10_11/diagnostics') / (os.environ.get('GITHUB_RUN_ID', 'local') + '.json')
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(rows, ensure_ascii=False))
