"""Bounded official daily-recovery capture; no AI or operational writes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess

from recover_public_sources_runtime import probe, tls_diagnostic, now

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    pending = json.loads((ROOT / 'data/state/pending_queue.json').read_text())
    endpoints = {
        'fonasa': ['https://www.fonasa.gob.cl/noticias/'],
        'fonasa_datos_abiertos': ['https://datosabiertos.fonasa.cl/noticias/'],
        'isp_anamed': ['https://www.ispch.cl/categorias-alertas/anamed/'],
        'isp_surveillance': ['https://www.ispch.cl/boletin/'],
        'minsal': ['https://www.minsal.cl/category/noticias/',
                   'https://www.minsal.cl/category/noticias/page/2/',
                   'https://www.minsal.cl/category/noticias/feed/'],
    }
    endpoints['minsal'] += [v['raw']['url'] for v in pending.values()
                           if v['source'] == 'minsal' and v['status'] in ('pending', 'retry')][:4]
    tasks = [(slug, url) for slug, urls in endpoints.items() for url in urls]
    with ThreadPoolExecutor(max_workers=4) as pool:
        captures = list(pool.map(lambda p: probe(*p, args.output, timeout=15), tasks))
        tls = list(pool.map(tls_diagnostic, ('www.fonasa.gob.cl', 'www.ispch.cl', 'www.minsal.cl')))
    receipt = {'captured_at': now(), 'run_id': os.getenv('GITHUB_RUN_ID'),
               'candidate_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'probes': captures, 'tls_diagnostics': tls, 'ai_calls': 0,
               'window_priority_hours': 72, 'maximum_days': 30,
               'scope': 'transport_and_primary_capture_only_not_coverage_or_publication'}
    (args.output / 'capture.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps({'requests': len(captures), 'outcomes': [(p['source'], p['outcome'], p['http_status']) for p in captures]}))


if __name__ == '__main__':
    main()
