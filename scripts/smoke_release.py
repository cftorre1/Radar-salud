"""Verify release identity or restore bytes, with bounded CDN propagation retry."""
import argparse,hashlib,json,time
from pathlib import Path
from urllib.request import urlopen

def get(url,path):
    with urlopen(url.rstrip('/')+'/'+path+f'?v={time.time_ns()}',timeout=15) as response:
        if response.status!=200:raise ValueError('HTTP failure: '+path)
        return response.read()

def check(url,sha=None,expected_dir=None):
    if expected_dir:
        for name in ('index.html','app.js','data/radar_today.json','admin/product.html','data/product.json'):
            path=Path(expected_dir)/name
            if path.exists() and hashlib.sha256(get(url,name)).digest()!=hashlib.sha256(path.read_bytes()).digest():
                raise ValueError('Rollback bytes differ: '+name)
        return
    if json.loads(get(url,'release.json'))['sha']!=sha:raise ValueError('Deployed SHA mismatch')
    for path in ('index.html','app.js','admin/product.html','admin/product.js','data/radar_today.json','data/product.json'):
        if not get(url,path):raise ValueError('Missing asset: '+path)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('sha',nargs='?');p.add_argument('--expected-dir');a=p.parse_args()
    if not a.sha and not a.expected_dir:p.error('SHA or expected directory required')
    for attempt in range(6):
        try:check(a.url,a.sha,a.expected_dir);print('Release verified');break
        except Exception:
            if attempt==5:raise
            time.sleep(10)
