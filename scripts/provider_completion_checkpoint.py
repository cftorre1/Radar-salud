"""Assess only nine new or deferred verified cases, preserving paid terminals."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
from radar_salud.pending_queue import atomic_json
from reconcile_providers import run,canonical_url

PATH='data/audits/provider_completion_checkpoint_2026_10_11.json'
URLS=tuple('https://www.redsalud.cl/noticias/'+x for x in (
    'nueva-unidad-trasplante-medula-osea','fibrilacion-auricular-varipulse-pro',
    'nuevo-servicio-de-urgencia-elqui','redsalud-y-facultadla-universidad-de-chile',
    'el-exitoso-primer-tavi-en-temuco','cirugia-robotica-mars-en-chile'))+tuple(
    'https://www.davila.cl/novedades/'+x for x in ('operativo-medico-en-valparaiso',
    'resonancia-cardiaca-en-clinica-davila-vespucio',
    'clinica-davila-recoleta-incorpora-nuevo-servicio-de-fototerapia-dermatologica'))

def main():
    if not os.getenv('OPENAI_API_KEY'):raise RuntimeError('No API key; assessment not performed')
    root=Path('.')
    before=json.loads((root/'data/state/pending_queue.json').read_text())
    terminal={k:v for k,v in before.items() if v['status'] in ('published','rejected','archived')}
    run(root,apply=True,live=True,limit=len(URLS),urls=URLS,checkpoint_path=PATH)
    result=json.loads((root/PATH).read_text())
    queue=json.loads((root/'data/state/pending_queue.json').read_text())
    assert all(queue.get(k)==v for k,v in terminal.items()),'Previous terminal result changed'
    selected={k:v for k,v in queue.items() if canonical_url(v['raw']['url']) in {canonical_url(u) for u in URLS}}
    for item in selected.values():
        item['raw']['raw_text']='';item['raw']['metadata'].pop('page_text',None)
    result.update(at=datetime.now(timezone.utc).isoformat(),commit=os.getenv('GITHUB_SHA'),
        runtime='actual registered processors; nine original verified new/deferred cases',
        prior_terminal_unchanged=len(terminal),recovered_queue=selected,promotion='none',
        usage_ledger=json.loads((root/'data/ai_usage/2026-10.json').read_text()))
    atomic_json(root/PATH,result)
    print('PROVIDER_COMPLETION_JSON '+json.dumps(result,ensure_ascii=False,separators=(',',':')))

if __name__=='__main__':main()
