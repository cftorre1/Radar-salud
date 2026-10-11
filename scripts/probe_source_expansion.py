"""Verified public transport for isolated source expansion; no repository writes."""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess
from threading import Lock
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor
HOSTS={"www.superdesalud.gob.cl","superdesalud.gob.cl","www.cmfchile.cl","cmfchile.cl","www.dipres.gob.cl","dipres.gob.cl"}
CMF_LOCK = Lock()
def utcnow():
    return datetime.now(timezone.utc).isoformat()


def fetch(url, output, post=None):
    if urlsplit(url).hostname in ('www.cmfchile.cl', 'cmfchile.cl'):
        with CMF_LOCK: return fetch_verified(url, output, post)
    return fetch_verified(url, output, post)


def fetch_verified(url, output, post=None):
    """Persist body, response chain and verified TLS diagnostics without credentials."""
    if urlsplit(url).scheme != 'https' or urlsplit(url).hostname not in HOSTS:
        raise ValueError('Probe requires an official HTTPS URL')
    key = hashlib.sha256((url + (post or '')).encode()).hexdigest()[:20]
    output.mkdir(parents=True, exist_ok=True)
    body, headers, trace = (output / (key + suffix) for suffix in ('.body', '.headers', '.tls.txt'))
    started = utcnow()
    command = ['curl', '--location', '--proto', '=https', '--proto-redir', '=https',
        '--connect-timeout', '15', '--max-time', '60', '--max-redirs', '8',
        '--user-agent', 'RadarSaludBot/0.1 (+public-source-monitor)',
        '--dump-header', str(headers), '--output', str(body), '--write-out', '%{json}',
        '--verbose', url]
    if post: command[1:1] = ['--data', post]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=70)
    except subprocess.TimeoutExpired as exc:
        result = subprocess.CompletedProcess(command, 28, stdout='', stderr='subprocess_timeout')
    # Never retain authorization headers, cookies or proxy credential values.
    diagnostics = re.sub(r'(?im)^.*(?:authorization:|cookie:|proxy environment variable).*$', '[redacted]', result.stderr)
    trace.write_text(diagnostics)
    try:
        network = json.loads(result.stdout)
    except ValueError:
        network = {'diagnostic': 'curl_writeout_unavailable'}
    keep = ['http_code', 'http_connect', 'url_effective', 'num_redirects', 'ssl_verify_result',
        'remote_ip', 'remote_port', 'local_ip', 'time_total', 'time_connect', 'time_appconnect',
        'content_type', 'size_download', 'exitcode', 'errormsg', 'http_version']
    network = {k: network.get(k) for k in keep}
    content = body.read_bytes() if body.exists() else b''
    if content.startswith(b'%PDF'):
        document_dir = output / 'documents' / str(int(key[0], 16) // 4)
        document_dir.mkdir(parents=True, exist_ok=True)
        renamed = document_dir / (key + '.pdf')
        body.rename(renamed)
        body = renamed
    text = content.decode('utf-8', errors='replace')
    waf = [term for term in ['access denied', 'captcha', 'cloudflare', 'request rejected', 'proxy error'] if term in text.lower()]
    status = int(network.get('http_code') or 0)
    receipt = dict(url=url, request_method='POST' if post else 'GET', request_body=post,
        started_at=started, completed_at=utcnow(), curl_returncode=result.returncode,
        network=network, body_file=str(body.relative_to(output.parent)), header_file=str(headers.relative_to(output.parent)), tls_trace_file=str(trace.relative_to(output.parent)),
        bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), waf_hints=waf,
        transport_ok=result.returncode == 0 and 200 <= status < 300 and network.get('ssl_verify_result') == 0,
        proxy_environment_names=[k for k in os.environ if k.lower() in ('http_proxy','https_proxy','all_proxy')])
    return receipt, text


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.href=None; self.label=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='a': self.href=d.get('href'); self.label=[]
        if tag=='link' and 'appendix' in d.get('rel',''): self.links.append((d.get('href'),d.get('rel')))
    def handle_data(self,text):
        if self.href is not None: self.label.append(text)
    def handle_endtag(self,tag):
        if tag=='a' and self.href is not None:
            self.links.append((self.href,' '.join(''.join(self.label).split())));self.href=None

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--seeds',type=Path,default=Path('config/source_expansion_runtime.json'));args=p.parse_args()
    seeds=json.loads(args.seeds.read_text())['seeds']; receipts=[];seen=set();todo=seeds
    for depth in range(3):
        batch=list({(s['url'],s.get('post')):s for s in todo if (s['url'],s.get('post')) not in seen}.values())[:180]
        todo=[];seen.update((s['url'],s.get('post')) for s in batch)
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda seed:fetch(seed['url'],args.output/'captures',seed.get('post')),batch))
        for seed,(receipt,html) in zip(batch,results):
            receipt.update(package=seed['package'],kind=seed.get('kind','discovered'),depth=depth)
            discovery_html=html
            if seed['package']=='dipres' and re.search(r'alt-multipropertyvalues-2518[345]',seed['url']):
                start=html.find('pvid-14626 cid')
                end=html.find('pv-pid-0',start+1)
                discovery_html=html[start:end] if start>=0 and end>start else ''
            parser=Links();parser.feed(discovery_html);receipt['links']=[{'url':urljoin(seed['url'],h),'label':t} for h,t in parser.links if h and urlsplit(urljoin(seed['url'],h)).hostname in HOSTS]
            receipts.append(receipt)
            print(seed['package'],receipt['network']['http_code'],receipt['bytes'],seed['url'],flush=True)
            if not receipt['transport_ok'] or depth==2:continue
            for link in receipt['links']:
                u=link['url']; label=link['label']; host=urlsplit(u).hostname
                relevant=False
                if seed['package']=='isapres': relevant=bool(re.search(r'\.xlsx?(?:$|\?)|/(?:biblioteca-digital|publicaciones)/.*(?:cartera|financ|beneficiar|isapre)',u,re.I))
                if seed['package']=='cmf': relevant=bool(re.search(r'ver_sgd|hechos_esenciales|hechos.*archivo|hes_|safec_ifrs_verarchivo',u,re.I)) or bool(re.search(r'\.pdf$',u,re.I))
                if seed['package']=='dipres': relevant=bool(re.search(r'/(?:alt|aux)-multipropertyvalues-',u)) or bool(re.search(r'articles-.*(?:pdf|xlsx|csv)',u) and re.search('Proyecto de Ley|Comparativo|Ejecuci.n',label,re.I))
                if relevant and host in HOSTS:todo.append({'url':u,'package':seed['package'],'kind':label[:100]})
            (args.output/'receipts.json').write_text(json.dumps({'captured_at':utcnow(),'bounded_depth':2,'page_cap_per_depth':180,'coverage_complete':False,'receipts':receipts},ensure_ascii=False,indent=2)+'\n')
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'receipts.json').write_text(json.dumps({'captured_at':utcnow(),'bounded_depth':2,'page_cap_per_depth':180,'coverage_complete':False,'receipts':receipts},ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
