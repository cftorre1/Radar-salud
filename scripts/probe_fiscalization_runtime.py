"""Read-only external probe. Network success and coverage are separate outcomes."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urljoin, urlsplit

from radar_salud.pending_queue import atomic_json
from radar_salud.scouts import _AnchorParser
from radar_salud.superintendencia_fiscalizacion import PAGES as SIS, parse_listing, canonical_url
from radar_salud.suseso_fiscalizacion import PAGES as SUSESO, ENFORCEMENT_PAGES, parse_actor_listing, parse_enforcement_listing, parse_official_news_listing, NEWS_PAGE

HOSTS = {'www.superdesalud.gob.cl', 'superdesalud.gob.cl', 'www.suseso.gob.cl', 'suseso.gob.cl'}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def fetch(url, output):
    """Persist body, response chain and verified TLS diagnostics without credentials."""
    if urlsplit(url).scheme != 'https' or urlsplit(url).hostname not in HOSTS:
        raise ValueError('Probe requires an official HTTPS URL')
    key = hashlib.sha256(url.encode()).hexdigest()[:20]
    output.mkdir(parents=True, exist_ok=True)
    body, headers, trace = (output / (key + suffix) for suffix in ('.body', '.headers', '.tls.txt'))
    started = utcnow()
    command = ['curl', '--location', '--proto', '=https', '--proto-redir', '=https',
        '--connect-timeout', '15', '--max-time', '60', '--max-redirs', '8',
        '--user-agent', 'RadarSaludBot/0.1 (+public-source-monitor)',
        '--dump-header', str(headers), '--output', str(body), '--write-out', '%{json}',
        '--verbose', url]
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
    receipt = dict(url=url, started_at=started, completed_at=utcnow(), curl_returncode=result.returncode,
        network=network, body_file=str(body), header_file=str(headers), tls_trace_file=str(trace),
        bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), waf_hints=waf,
        transport_ok=result.returncode == 0 and 200 <= status < 300 and network.get('ssl_verify_result') == 0,
        proxy_environment_names=[k for k in os.environ if k.lower() in ('http_proxy','https_proxy','all_proxy')])
    return receipt, text


def links(html, base):
    parser = _AnchorParser(); parser.feed(html)
    return [{'url': urljoin(base, href), 'title': title} for href, title in parser.links
        if href and urlsplit(urljoin(base, href)).hostname in HOSTS]


def within(value, as_of, days):
    try:
        return 0 <= (as_of-date.fromisoformat(value)).days <= days
    except (TypeError, ValueError):
        return False


def probe(output, as_of):
    captures = output / 'captures'
    seeds = [dict(url=url, source='superintendencia_fiscalizacion', name=name, scope=scope, kind=kind)
        for name,url,scope,kind in SIS]
    seeds += [dict(url=url, source='suseso_fiscalizacion', scope=actor, kind='related_actor_taxonomy') for actor,url in SUSESO]
    seeds += [dict(url='https://www.suseso.gob.cl/601/w3-channel.html',source='suseso',kind='navigation'),
        dict(url='https://www.superdesalud.gob.cl/fiscalizacion/',source='superintendencia_fiscalizacion',kind='navigation')]
    # Independent official enforcement and alternative result indexes. The actor
    # taxonomy at /612 is a normative index, not the /609 enforcement channel.
    seeds += [dict(url=url, source=source, kind='navigation') for source, url in [
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/609/w3-channel.html'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/605/w3-propertyname-536.html'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/612/w3-propertyvalue-30973.html'),
        ('superintendencia_fiscalizacion', 'https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/informes-de-fiscalizacion-3218/'),
        ('superintendencia_fiscalizacion', 'https://www.superdesalud.gob.cl/tax-otros-actos-de-la-superintendencia/sanciones-aplicadas-5113/'),
        ('superintendencia_fiscalizacion', 'https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/sanciones-aplicadas-5185/'),
        ('superintendencia_fiscalizacion', 'https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/sanciones-aplicadas-5185/sanciones-a-entidades-acreditadoras-7059/'),
        ('superintendencia_fiscalizacion', 'https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/sanciones-aplicadas-5185/sanciones-agentes-de-ventas-7441/'),
        ('superintendencia_fiscalizacion', 'https://www.superdesalud.gob.cl/app/themes/supersalud-bloom/assets/dist/datatables.js'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/609/w3-propertyvalue-10378.html'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/609/w3-propertyvalue-408634.html'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/609/w3-propertyname-566.html'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/609/w3-propertyname-535.html'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/609/w3-propertyvalue-806511.html'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/609/w3-propertyvalue-799701.html'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/609/w3-propertyvalue-559470.html'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/609/w3-propertyvalue-559471.html'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/609/w3-propertyvalue-715128.html'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/609/w3-propertyvalue-814414.html'),
        ('suseso_fiscalizacion', 'https://www.suseso.gob.cl/609/w3-propertyvalue-715129.html'),
    ]]
    seeds = list({seed['url']: seed for seed in reversed(seeds)}.values())[::-1]
    enforcement = {url:(name,kind) for name,url,kind in ENFORCEMENT_PAGES}
    for seed in seeds:
        if seed['url'] in enforcement:
            seed['name'], kind = enforcement[seed['url']]
            seed['kind'] = 'enforcement_' + kind
        if seed['url']==NEWS_PAGE:
            seed['kind']='official_news'
    receipts=[]; inventory=[]; navigation=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda seed: fetch(seed['url'],captures), seeds))
    for seed,(receipt,html) in zip(seeds,results):
        receipt.update(source=seed['source'],surface_kind=seed['kind'])
        found=[]
        if receipt['transport_ok']:
            try:
                if seed['source']=='superintendencia_fiscalizacion' and seed['kind']!='navigation':
                    found=parse_listing(html,seed['name'],seed['url'],seed['scope'],seed['kind'])
                elif seed['kind']=='related_actor_taxonomy':
                    found=parse_actor_listing(html,seed['scope'],seed['url'])
                elif seed['kind'].startswith('enforcement_'):
                    found=parse_enforcement_listing(html,seed['name'],seed['url'],seed['kind'].removeprefix('enforcement_'))
                elif seed['kind']=='official_news':
                    found=parse_official_news_listing(html,seed['url'])
                receipt.update(parsed_items=len(found),parse_error=None if found or seed['kind']=='navigation' else 'no_identifiable_rows')
            except Exception as exc:
                receipt.update(parsed_items=0,parse_error=type(exc).__name__)
            navigation.extend(dict(link,from_url=seed['url']) for link in links(html,seed['url'])
                if re.search(r'fiscal|sancion|transparen|resultado|notici|circula|dictam|informe|pagin|page|siguiente',link['title']+' '+link['url'],re.I))
        else:
            receipt.update(parsed_items=0,parse_error='transport_failure')
        receipts.append(receipt)
        inventory.extend(asdict(raw) for raw in found)
    recent = {(raw['url'],raw['metadata'].get('source_record_id')):raw for raw in inventory if any(within(raw['metadata'].get(k) or raw.get('event_date'),as_of,90)
        for k in ('publication_date','emission_date'))}
    targets={raw['url'] for raw in recent.values()}
    targets.update(attachment['url'] for raw in recent.values() for attachment in raw['metadata'].get('attachments',[]))
    for raw in inventory:
        if raw['metadata'].get('document_class') == 'enforcement_report_candidate':
            targets.add(raw['url'])
            targets.update(a['url'] for a in raw['metadata'].get('attachments', []))
    # The complete official yearly news archive covers the 90-day boundary. Read
    # every recent detail, including items ultimately rejected from enforcement.
    news_seed = next(seed for seed in seeds if seed['url']=='https://www.suseso.gob.cl/605/w3-propertyname-536.html')
    news_receipt = next(r for r in receipts if r['url']==news_seed['url'])
    news_rows = []
    if news_receipt['transport_ok']:
        news_html = Path(news_receipt['body_file']).read_text(errors='replace')
        for day, href, title in re.findall(r'iso8601-(\d{8})T[^"\']*["\'][^>]*>[\s\S]*?<h3[^>]*>[\s\S]*?<a[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', news_html):
            published = f'{day[:4]}-{day[4:6]}-{day[6:]}'
            row = dict(url=urljoin(news_seed['url'],href),title=' '.join(re.sub('<[^>]*>',' ',title).split()),publication_date=published)
            news_rows.append(row)
            if within(published,as_of,90):targets.add(row['url'])
    atomic_json(output/'official_news_inventory.json',news_rows)
    # A duplicate primary attachment on two SIS rows needs document-level review;
    # a shared title alone cannot establish whether it is one act or two fines.
    attachments = {}
    for raw in inventory:
        if raw['source_slug']=='superintendencia_fiscalizacion':
            for attachment in raw['metadata'].get('attachments', []):
                attachments.setdefault(attachment['url'],set()).add(raw['url'])
    targets.update(url for url, acts in attachments.items() if len(acts)>1)
    targets.update(acts_url for acts in attachments.values() if len(acts)>1 for acts_url in acts)
    # Inspect detail and primary documents for every recent candidate, including held dates.
    with ThreadPoolExecutor(max_workers=3) as pool:
        for receipt,_ in pool.map(lambda url: fetch(url,captures),sorted(targets)):
            receipt.update(surface_kind='recent_detail_or_document');receipts.append(receipt)
    atomic_json(output/'inventory.json',inventory)
    atomic_json(output/'navigation.json',navigation)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    report=dict(schema_version=1,mode='read_only_external_native_http',as_of=as_of.isoformat(),
        started_from_sha=sha,completed_at=utcnow(),github_run_id=os.environ.get('GITHUB_RUN_ID'),
        github_run_url=f"https://github.com/cftorre1/Radar-salud/actions/runs/{os.environ.get('GITHUB_RUN_ID')}" if os.environ.get('GITHUB_RUN_ID') else None,
        receipts=receipts,inventory_file=str(output/'inventory.json'),navigation_file=str(output/'navigation.json'),
        surfaces_checked=len(seeds),rows_discovered=len(inventory),unique_items=len({(canonical_url(r['url']),r['metadata'].get('source_record_id')) for r in inventory}),
        recent_unique_items=len(recent),coverage_complete=False,
        coverage_reason='Initial native seed probe; pagination/dynamic surfaces and enforcement-specific taxonomy require subsequent reconciliation.',
        writes_to_source_state=False,writes_to_staging_or_main=False)
    atomic_json(output/'manifest.json',report)
    print(json.dumps({k:report[k] for k in ['started_from_sha','surfaces_checked','rows_discovered','unique_items','recent_unique_items','coverage_complete']}))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('artifacts/fiscalization-runtime'))
    parser.add_argument('--as-of',type=date.fromisoformat,default=date.today())
    args=parser.parse_args();probe(args.output,args.as_of)
