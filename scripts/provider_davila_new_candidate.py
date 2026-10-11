"""Process the one new dated operational candidate found by full browser audit."""
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
from radar_salud.pending_queue import atomic_json
from reconcile_providers import run,canonical_url

URL='https://www.davila.cl/novedades/medicina-deportiva-llega-a-red-davila'
PATH='data/audits/provider_davila_new_candidate_2026_10_11.json'

def main():
    root=Path('.');read=lambda p:json.loads((root/p).read_text())
    before=read('data/state/pending_queue.json');terminal={k:v for k,v in before.items() if v['status'] in ('published','rejected','archived')}
    path='data/audits/providers_2026_10_11/red_davila.json';audit=read(path)
    audit['original_items'].append({'url':URL,'title':'Medicina Deportiva llega a Red Dávila',
        'publication_date':'2026-08-01','date_evidence':'verified_article_header','materiality':'candidate','recover':True,
        'evidence':'Original H1/header and own URL JSONLD agree in actual Chrome capture38119508799; specialty added at two existing centres, no investment/capacity amount stated.'})
    # Existing terminal decisions remain frozen; only this new original can run.
    for item in audit['original_items']:
        if item['url']!=URL:item['recover']=False
    atomic_json(path,audit)
    run(root,'red_davila',apply=True,live=True,limit=1,urls=(URL,),checkpoint_path=PATH)
    out=read(PATH);queue=read('data/state/pending_queue.json')
    assert all(queue.get(k)==v for k,v in terminal.items())
    selected={k:v for k,v in queue.items() if canonical_url(v['raw']['url'])==canonical_url(URL)}
    for item in selected.values():item['raw']['raw_text']='';item['raw'].get('metadata',{}).pop('page_text',None)
    out.update(checkout_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        promotion='none',recovered_queue=selected,prior_terminal_unchanged=True,
        usage_ledger=read('data/ai_usage/2026-10.json'),
        original_discovery_run='https://github.com/cftorre1/Radar-salud/actions/runs/38119508799')
    atomic_json(PATH,out)
    print('PROVIDER_DAVILA_NEW_JSON '+json.dumps(out,ensure_ascii=False,separators=(',',':')))

if __name__=='__main__':main()
