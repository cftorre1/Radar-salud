"""Exactly three audited cases; preserve earlier paid outputs and diagnostics."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from radar_salud.pending_queue import atomic_json
from reconcile_providers import run,canonical_url

URLS=(
    'https://www.redsalud.cl/noticias/nueva-unidad-trasplante-medula-osea',
    'https://www.andessalud.cl/novedades/andes-salud-inaugura-nuevo-centro-medico-en-frutillar-para-acercar-consultas-medicas-y-examenes-a-la-comunidad/',
    'https://www.davila.cl/novedades/operativo-medico-sotero',
)
PATH='data/audits/provider_followup_checkpoint_2026_10_11.json'


def main():
    if not os.getenv('OPENAI_API_KEY'):raise RuntimeError('OPENAI_API_KEY unavailable; assessment not performed')
    root=Path('.')
    before=json.loads((root/'data/state/pending_queue.json').read_text())
    terminals={key:row for key,row in before.items() if row['status']=='published'}
    run(root,apply=True,live=True,limit=3,urls=URLS,checkpoint_path=PATH)
    checkpoint=json.loads((root/PATH).read_text())
    queue=json.loads((root/'data/state/pending_queue.json').read_text())
    assert all(queue.get(key)==row for key,row in terminals.items()),'Previously published queue output changed'
    selected={key:row for key,row in queue.items() if canonical_url(row['raw']['url']) in {canonical_url(url) for url in URLS}}
    for row in selected.values():
        row['raw']['raw_text']='';row['raw'].get('metadata',{}).pop('page_text',None)
    checkpoint.update(at=datetime.now(timezone.utc).isoformat(),commit=os.getenv('GITHUB_SHA'),
        runtime='isolated actual provider processors; three explicitly audited original cases',promotion='none',
        prior_published_unchanged=len(terminals),recovered_queue=selected,
        usage_ledger=json.loads((root/'data/ai_usage/2026-10.json').read_text()),
        source_health=json.loads((root/'data/source_health.json').read_text())['sources'])
    atomic_json(root/PATH,checkpoint)
    print('PROVIDER_FOLLOWUP_JSON '+json.dumps(checkpoint,ensure_ascii=False,separators=(',',':')))


if __name__=='__main__':main()
