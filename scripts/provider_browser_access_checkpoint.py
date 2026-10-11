"""Ordinary official-site navigation after denied HTTP originals; no AI."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from radar_salud.beta_sources import _ProviderPublication
from radar_salud.pending_queue import atomic_json
from radar_salud.public_source_pipeline import _RedSaludArticle, _VisibleArticle

TARGETS = {
    'red_davila': [
        'https://www.davila.cl/novedades/nueva-unidad-para-el-manejo-integral-de-la-esclerosis-lateral-amiotrofica',
        'https://www.davila.cl/novedades/nuevo-centro-de-la-mama',
        'https://www.davila.cl/novedades/nuevo-centro-integral-del-manejo-de-la-fibrilacion-auricular',
    ],
    'redsalud': [
        'https://www.redsalud.cl/noticias/clinica-redsalud-mayor-temuco-avanzamos-hacia-la-excelencia-en-atencion-cardiovascular-0',
        'https://www.redsalud.cl/noticias/redsalud-lanza-teletrombolisis-247-una-respuesta-a-la-vanguardia-ante-acv',
    ],
}

def main():
    chrome = shutil.which('google-chrome') or shutil.which('chromium')
    out = {'captured_at': datetime.now(timezone.utc).isoformat(), 'checkout_head':
        subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'ai_calls': 0, 'promotion': 'none', 'method':
        'ordinary unauthenticated native Chrome; no challenge handling, no TLS bypass', 'sources': {}}
    Path('work/provider_browser_access').mkdir(parents=True, exist_ok=True)
    for slug, targets in TARGETS.items():
        rows = []
        for index, url in enumerate(targets):
            row = {'url': url, 'http_status': 'not_observed_by_dump_dom'}
            if not chrome:
                row['error'] = 'native_chrome_unavailable'
            else:
                try:
                    run = subprocess.run([chrome, '--headless', '--disable-gpu', '--no-sandbox',
                        '--user-data-dir=' + str(Path(f'work/provider_browser_access/{slug}-{index}').resolve()),
                        '--virtual-time-budget=5000', '--dump-dom', url], capture_output=True, text=True, timeout=25)
                    article = _RedSaludArticle(url) if slug == 'redsalud' else _VisibleArticle()
                    article.feed(run.stdout)
                    if slug == 'redsalud':
                        article.finish(); published = article.published; reason = 'own_redsalud_publication_parser'
                        words = len(article.body.split())
                    else:
                        stamps = _ProviderPublication(url); stamps.feed(run.stdout)
                        published, reason = stamps.publication(); words = len(' '.join(article.text).split())
                    row.update(exit_code=run.returncode, dom_sha256=hashlib.sha256(run.stdout.encode()).hexdigest(),
                        title=article.title, publication_date=published, publication_evidence=reason,
                        article_words=words, challenge_detected=bool(re.search(
                            r'Just a moment|cf-chl-|captcha|Access denied|403 Forbidden', run.stdout, re.I)),
                        browser_error=bool(re.search(r'ERR_|SSL|certificate', run.stderr)))
                except subprocess.TimeoutExpired:
                    row['error'] = 'ordinary_browser_timeout_25s'
            rows.append(row)
        out['sources'][slug] = rows
    atomic_json('data/audits/provider_browser_access_2026_10_11.json', out)
    print('PROVIDER_BROWSER_ACCESS_JSON ' + json.dumps(out, ensure_ascii=False, separators=(',', ':')))

if __name__ == '__main__':
    main()
