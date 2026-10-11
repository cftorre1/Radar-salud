"""Parse actual browser DOMs with the same strict original publication parser."""
from datetime import date, datetime, timezone
import gzip
import json
from pathlib import Path
import subprocess

from provider_inventory import Inventory
from radar_salud.pending_queue import atomic_json

def main():
    root=Path('.')
    capture=json.loads((root/'work/provider_davila_browser/capture.json').read_text())
    path=root/'data/audits/provider_inventory_2026_10_11/red_davila.json'
    inventory=json.loads(path.read_text());by_url={x['url']:x for x in inventory['items']}
    parser=Inventory('red_davila',date(2026,10,11),root)
    rows=[]
    for request in capture['results']:
        item=by_url[request['url']]
        row={k:v for k,v in request.items() if k!='file'}
        if request.get('status')==200 and not request.get('error') and not request.get('challenge_detected'):
            html=gzip.decompress(Path(request['file']).read_bytes()).decode()
            parser.cache[item['url']]=html;parser.verify_detail(item)
            item['previous_http_access_error']=item.pop('access_error',None)
            item['browser_access_evidence']=row
            row.update(title=item['title'],publication_date=item['publication_date'],
                       publication_evidence=item['date_reason'],date_stamps=item['date_stamps'],
                       body_sha256=item.get('body_sha256'),in_90_days=item.get('in_90_days'))
        rows.append(row)
    inventory['requests'].extend(rows)
    inventory['captured_at']=datetime.now(timezone.utc).isoformat()
    inventory['pages_checked']=len(inventory['requests'])
    inventory['recent_30_count']=sum(x.get('in_30_days') is True for x in inventory['items'])
    inventory['recent_90_count']=sum(x.get('in_90_days') is True for x in inventory['items'])
    inventory['latest_original_at']=max((x['publication_date'] for x in inventory['items'] if x.get('publication_date')),default=None)
    inventory['browser_archive']={'targets':capture['target_count'],'completed':len(rows),
        'dated':sum(bool(x.get('publication_date')) for x in rows),'method':'ordinary native Chrome, two concurrent pages, no challenge handling'}
    atomic_json(path,inventory)
    out={'captured_at':inventory['captured_at'],'checkout_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'ai_calls':0,'promotion':'none','inventory':inventory,'browser_requests':rows}
    atomic_json('data/audits/provider_davila_browser_checkpoint_2026_10_11.json',out)
    print('PROVIDER_DAVILA_BROWSER_JSON '+json.dumps(out,ensure_ascii=False,separators=(',',':')))

if __name__=='__main__':main()
