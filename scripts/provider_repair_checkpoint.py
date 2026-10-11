"""Reassess two repaired intake records; probe RedSalud dates without inference.

Only the two allowlisted, still-deferred URLs can use the existing AI budget.
Previously published/rejected candidates are never reassessed. Outputs stay in
the isolated checkout and a compact job log; no promotion or remote writes.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from radar_salud.pending_queue import atomic_json
from radar_salud.public_source_pipeline import fetch_html, _RedSaludArticle, _date
from reconcile_providers import run

URLS = (
    'https://www.bupa.cl/chile-tendra-su-primera-base-genomica-de-referencia-bupa-lanza-1000',
    'https://www.davila.cl/novedades/operativo-medico-sotero',
)


def main():
    root = Path('.')
    initial_path = root/'data/audits/provider_live_checkpoint_2026_10_11.json'
    initial = json.loads(initial_path.read_text())
    probe = {}
    red_url = 'https://www.redsalud.cl/noticias/nueva-unidad-trasplante-medula-osea'
    try:
        article = _RedSaludArticle(); article.feed(fetch_html(red_url)); article.finish()
        probe = {'url': red_url, 'article_headline': article.title,
                 'article_date_raw': article.published, 'article_date': _date(article.published),
                 'audited_listing_date': '2026-08-27', 'body_characters': len(article.body)}
    except Exception as exc:
        probe = {'url': red_url, 'error_type': type(exc).__name__, 'error': str(exc)}
    if os.getenv('OPENAI_API_KEY'):
        run(root, apply=True, live=True, limit=2, urls=URLS)
        repair = json.loads(initial_path.read_text())
    else:
        repair = {'attempted': 0, 'results': [], 'assessment_blocker': 'OPENAI_API_KEY_unavailable'}
    atomic_json(initial_path, initial)
    queue = json.loads((root/'data/state/pending_queue.json').read_text())
    selected = {k:v for k,v in queue.items() if v['raw']['url'].rstrip('/') in URLS}
    for item in selected.values():
        item['raw']['raw_text'] = ''; item['raw']['metadata'].pop('page_text', None)
    repair.update(at=datetime.now(timezone.utc).isoformat(), commit=os.getenv('GITHUB_SHA'),
                  redsalud_date_probe=probe, recovered_queue=selected,
                  usage_ledgers={p.name:json.loads(p.read_text()) for p in (root/'data/ai_usage').glob('*.json')},
                  runtime='GitHub Actions isolated PR checkout', promotion='none', accepted=False)
    atomic_json(root/'data/audits/provider_repair_checkpoint_2026_10_11.json', repair)
    print('PROVIDER_REPAIR_JSON='+json.dumps(repair, ensure_ascii=False, separators=(',',':')))


if __name__ == '__main__':
    main()
