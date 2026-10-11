"""Inspect existing empty listing bytes; makes no publisher requests."""
import hashlib
import json
from pathlib import Path
from radar_salud.global_discovery_common import Document

root=Path(__file__).resolve().parents[1]
inventory=json.loads((root/'data/global_intelligence/discovery.json').read_text())
rows=[]
page_documents={}
for route in inventory['routes']:
    for page in route['pages']:
        if 'date%5Bmin%5D' not in page['url']:
            continue
        key=hashlib.sha256(page['url'].encode()).hexdigest()[:24]
        capture=json.loads((root/'work/global-runtime-captures'/(key+'.json')).read_text())
        raw=(root/'work/global-runtime-captures'/capture['body_file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=capture['body_sha256']:
            raise ValueError('capture hash mismatch')
        document=Document(raw.decode(errors='replace')).root
        page_documents[page['url']]=document
        if page['native_records']:
            continue
        main=list(document.nodes('main'))
        rows.append({'url':page['url'],'section':route['route']['section'],'capture':capture,
            'h1':[n.text() for n in document.nodes('h1')],
            'view_nodes':[{'tag':n.tag,'attrs':n.attrs,'closed':n.closed,'text':n.text()[:1200]} for n in document.nodes()
                          if any(c.startswith(('view-id-','view-display-id-')) or c in {'view-empty','view-content','views-exposed-form'} for c in n.attrs.get('class','').split())],
            'publication_meta_or_time':[{'tag':n.tag,'attrs':n.attrs} for n in document.nodes() if n.tag=='time' or n.tag=='meta' and (n.attrs.get('property') or n.attrs.get('name') or '').lower() in {'article:published_time','datepublished','citation_publication_date','dc.date.issued'}],
            'page_article_wrappers':[{'attrs':n.attrs,'contains_news_view':any(v.has_class('view-id-news') for v in n.nodes())} for n in document.nodes('article')],
            'native_heading_nodes':[{'tag':n.tag,'attrs':n.attrs,'text':n.text(),'closed':n.closed,'parent':n.parent.tag} for n in document.nodes('h2') if n.attrs.get('id')=='pagination-heading'],
            'empty_contract':__import__('radar_salud.global_source_discovery',fromlist=['verified_empty_news_view']).verified_empty_news_view(document,route['route'],next(part for part in route['date_partitions'] if part['query_from'] in page['url'] and part['query_to'] in page['url'])),
            'forbidden_or_pager_nodes':[{'tag':n.tag,'attrs':n.attrs,'closed':n.closed,'text':n.text()[:100]} for n in document.nodes() if any(c in {'pager','pager-nav','pagination','views-row','view-content','views-field-title','views-field-created','field--name-created'} or c.startswith(('pager__','js-pager__')) for c in n.attrs.get('class','').split())],
            'pagination_rel_links':[{'attrs':a.attrs,'text':a.text()} for a in document.nodes('a') if {'next','last','prev','previous','first'}&set(a.attrs.get('rel','').split())],
            'view_text_equals_form':[v.text()==f.text() for v in document.nodes() if v.has_class('view-id-news') for f in v.nodes('form')],
            'main_text':main[0].text()[:2000] if main else None,
            'inputs':[{k:n.attrs.get(k) for k in ('name','value')} for n in document.nodes('input') if n.attrs.get('name') in {'date[min]','date[max]'}]})
from urllib.parse import parse_qsl,urlsplit,urlunsplit,urlencode
for row in rows:
    parts=urlsplit(row['url']);query=parse_qsl(parts.query)
    current=int(dict(query).get('page','0'))
    prior=urlunsplit((*parts[:3],urlencode([(k,v) for k,v in query if k!='page']+([('page',str(current-1))] if current>1 else [])),''))
    if current>0 and prior in page_documents:
        doc=page_documents[prior]
        context=next(r for r in inventory['routes'] if r['route']['section']==row['section'])
        bounds=next(p for p in context['date_partitions'] if p['query_from'] in row['url'] and p['query_to'] in row['url'])
        from radar_salud.global_source_discovery import verified_news_view,verified_clamped_empty_end
        row['empty_view_with_terminal_pager_contract']=verified_news_view(page_documents[row['url']],context['route'],bounds,empty=True,allow_pager=True)
        row['primary_clamped_receipt']=verified_clamped_empty_end(page_documents[row['url']],doc,context['route'],bounds,row['url'],prior)
        row['preceding_page']={'url':prior,'pager_nodes':[{'tag':n.tag,'attrs':n.attrs,'closed':n.closed,'text':n.text()[:500],'links':[{'attrs':a.attrs,'text':a.text(),'closed':a.closed} for a in n.nodes('a')]} for n in doc.nodes() if any(c.startswith(('pager','js-pager')) for c in n.attrs.get('class','').split())],
            'pagination_links':[{'attrs':n.attrs,'text':n.text()} for n in doc.nodes('a') if {'next','last','prev','previous','first'}&set(n.attrs.get('rel','').split())]}
path=root/'data/audits/global_source_recovery_2026_10_11/runs'/inventory['run_id']/'empty_listing_diagnostic.json'
path.write_text(json.dumps({'run_id':inventory['run_id'],'network_requests':0,'empty_pages':rows},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'empty_listing_pages_inspected':len(rows),'evidence':str(path.relative_to(root))}))
for row in rows[:2]:
    print(json.dumps({'url':row['url'],'preceding_page':row.get('preceding_page'),'empty_views':row['view_nodes']},ensure_ascii=False))
