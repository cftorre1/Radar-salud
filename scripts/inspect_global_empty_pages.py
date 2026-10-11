"""Inspect existing empty listing bytes; makes no publisher requests."""
import hashlib
import json
from pathlib import Path
from radar_salud.global_discovery_common import Document

root=Path(__file__).resolve().parents[1]
inventory=json.loads((root/'data/global_intelligence/discovery.json').read_text())
rows=[]
for route in inventory['routes']:
    for page in route['pages']:
        if page['native_records'] or 'date%5Bmin%5D' not in page['url']:
            continue
        key=hashlib.sha256(page['url'].encode()).hexdigest()[:24]
        capture=json.loads((root/'work/global-runtime-captures'/(key+'.json')).read_text())
        raw=(root/'work/global-runtime-captures'/capture['body_file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=capture['body_sha256']:
            raise ValueError('capture hash mismatch')
        document=Document(raw.decode(errors='replace')).root
        main=list(document.nodes('main'))
        rows.append({'url':page['url'],'section':route['route']['section'],'capture':capture,
            'h1':[n.text() for n in document.nodes('h1')],
            'view_nodes':[{'tag':n.tag,'attrs':n.attrs,'text':n.text()[:1200]} for n in document.nodes()
                          if any(c.startswith(('view-id-','view-display-id-')) or c in {'view-empty','view-content','views-exposed-form'} for c in n.attrs.get('class','').split())],
            'main_text':main[0].text()[:2000] if main else None,
            'inputs':[{k:n.attrs.get(k) for k in ('name','value')} for n in document.nodes('input') if n.attrs.get('name') in {'date[min]','date[max]'}]})
path=root/'data/audits/global_source_recovery_2026_10_11/runs'/inventory['run_id']/'empty_listing_diagnostic.json'
path.write_text(json.dumps({'run_id':inventory['run_id'],'network_requests':0,'empty_pages':rows},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'empty_listing_pages_inspected':len(rows),'evidence':str(path.relative_to(root))}))
