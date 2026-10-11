"""Small robots-respecting official metadata diagnostic; no Reuters requests."""
import json
import os
from datetime import date
from pathlib import Path
from radar_salud.global_discovery_common import CaptureClient, Document

client = CaptureClient(Path('work/global-diagnostic-captures'))
rows = []
for url in (
    'https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON620',
    'https://www.paho.org/en/news?page=8',
    'https://www.paho.org/es/noticias',
    'https://www.paho.org/es/noticias?c%5B%5D=65',
    'https://www.paho.org/en/news?page=9',
    'https://www.paho.org/sitemap.xml',
    'https://www.paho.org/en/rss.xml',
):
    try:
        raw, capture = client.fetch(url)
        doc = Document(raw.decode(errors='replace')).root
        rows.append({'url': url, 'capture': capture,
            'h1': [n.text() for n in doc.nodes('h1')],
            'dates': [n.text() for n in doc.nodes() if n.has_class('date')],
            'publication_meta': [n.attrs for n in doc.nodes('meta') if 'publish' in str(n.attrs).lower()],
            'pager': [{'text': n.text(), 'attrs': n.attrs} for n in doc.nodes('a')
                      if 'page=' in n.attrs.get('href', '')],
            'filters': [n.attrs for n in doc.nodes('select')],
            'chile_option': [n.attrs for n in doc.nodes('option') if n.text() == 'Chile'],
            'sitemap_locations': [n.text() for n in doc.nodes('loc')],
            'feed_count': sum(1 for _ in doc.nodes('item')),
            'feed_publication_dates': [n.text() for n in doc.nodes('pubdate')],
            'card_count': sum(n.has_class('views-field-title') for n in doc.nodes())})
    except Exception as exc:
        rows.append({'url': url, 'error': str(exc)})
path = Path('data/audits/global_source_recovery_2026_10_11/diagnostics') / (os.environ.get('GITHUB_RUN_ID', 'local') + '.json')
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(rows, ensure_ascii=False))
