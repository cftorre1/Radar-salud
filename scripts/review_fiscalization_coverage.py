"""Read-only independent coverage Reviewer; never imports collector/parser code.

Parse the captured official HTML independently and compare dated records to
stock and visible source references. This proves bounded coverage, not absence
of activity on every possible official surface.
"""
from __future__ import annotations
import argparse
from datetime import date
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin

AS_OF=date(2026,10,11)
class Tables(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        elif tag in ('td','th') and self.row is not None:self.cell={'text':'','links':[]}
        elif tag=='a' and self.cell is not None:self.cell['links'].append(dict(attrs).get('href',''))
    def handle_data(self,data):
        if self.cell is not None:self.cell['text']+=data+' '
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.cell['text']=' '.join(self.cell['text'].split());self.row.append(self.cell);self.cell=None
        elif tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None

def iso(text):
    m=re.search(r'\b(\d{1,2})[/-](\d{1,2})[/-]((?:19|20)\d{2})\b',text)
    if m:
        try:return date(int(m[3]),int(m[2]),int(m[1])).isoformat()
        except ValueError:return None

def recent(day,days):
    return bool(day and 0<=(AS_OF-date.fromisoformat(day)).days<=days)

def run(runtime,root=Path('.')):
    manifest=json.loads((runtime/'manifest.json').read_text());reconciliation=json.loads((root/'data/audits/fiscalizacion/native_reconciliation_2026_10_11.json').read_text())
    reviews=json.loads((root/'config/fiscalization_editorial_reviews.json').read_text());failures=[]
    sis={};professional={};professional_validity={};undated=set();official_news={}
    for receipt in manifest['receipts']:
        url=receipt['url']
        if url not in {r['url'] for rows in reconciliation['native_engine']['surfaces'].values() for r in rows}:continue
        file=next(runtime.rglob(Path(receipt['body_file']).name));content=file.read_bytes()
        if hashlib.sha256(content).hexdigest()!=receipt['sha256']:failures.append('receipt_hash_mismatch:'+url);continue
        parser=Tables();parser.feed(content.decode('utf-8',errors='replace'))
        if 'superdesalud.gob.cl' in url:
            for cells in parser.rows:
                if not cells or not iso(cells[0]['text']):continue
                published=iso(cells[0]['text'])
                target=next(((urljoin(url,link).rstrip('/'),c['text']) for c in cells for link in c['links'] if re.search(r'/(?:normativa|fiscalizacion|observatorio)/',urljoin(url,link)) and not link.endswith('.pdf')),None)
                if not target:
                    target=next(((urljoin(url,link).rstrip('/'),c['text']) for c in cells for link in c['links'] if '.pdf' in link.lower() and re.search(r'informe|instrucci[oó]n|resoluci[oó]n',c['text'],re.I)),None)
                if not target or target[1].startswith('Decreto'):continue
                act,title=target;emitted=iso(title.split('Emisi',1)[1]) if 'Emisi' in title else None
                review=reviews['primary_document_reviews'].get(act)
                if review:
                    pdf=next((r for r in manifest['receipts'] if r['url']==review['primary_document_url']),{})
                    if pdf.get('sha256')!=review['primary_document_sha256']:failures.append('primary_review_receipt_mismatch:'+act)
                    emitted=review['emission_date']
                    if review.get('publication_unreliable'):published=None
                sis[act]=dict(publication=published,emission=emitted)
        elif url.endswith('799701.html'):
            for cells in parser.rows:
                if len(cells)==10 and re.fullmatch(r'O-\d{2}-[A-Z]+-\d+-20\d{2}',cells[4]['text']):
                    identity=cells[4]['text'];professional[identity]=iso(cells[5]['text'])
                    professional_validity[identity]=(iso(cells[8]['text']),iso(cells[9]['text']))
        elif url.endswith('814414.html'):
            for cells in parser.rows:
                if len(cells)>=5:
                    for c in cells:
                        undated.update(urljoin(url,link).rstrip('/') for link in c['links'] if '/609/w3-article-' in urljoin(url,link))
        elif url.endswith('536.html'):
            # Independent paired-block extraction keeps the full yearly inventory.
            for block in content.decode(errors='replace').split('class="fecha'):
                day=re.search(r'iso8601-(\d{8})T',block)
                link=re.search(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"',block)
                if day and link:
                    d=day[1];official_news[urljoin(url,link[1])]=f'{d[:4]}-{d[4:6]}-{d[6:]}'
    published_news={url:review['publication_date'] for url,review in reviews['enforcement_news_reviews'].items() if review['decision']=='publish_fiscalization'}
    receipts_by_url={r['url']:r for r in manifest['receipts']}
    news_primary_reviews_verified=0
    for url,review in reviews['enforcement_news_reviews'].items():
        if recent(review['event_date'],90):
            if receipts_by_url.get(url,{}).get('sha256')!=review['primary_html_sha256']:
                failures.append('news_primary_review_receipt_mismatch:'+url)
            else:news_primary_reviews_verified+=1
    for url,day in published_news.items():
        if official_news.get(url)!=day:failures.append('official_news_date_unverified:'+url)
    history=json.loads((root/'data/history/superintendencia_signals.json').read_text())['signals'];feed=json.loads((root/'web/data/radar_today.json').read_text())['signals']
    def identity(row):return (row.get('source_url',row.get('url','')).rstrip('/'),row.get('source_record_id'))
    history_ids={identity(r) for r in history if 'Fiscalización' in r.get('signal_types',[])}
    feed_ids={identity(r) for r in feed if 'Fiscalización' in r.get('signal_types',[])}
    feed_ids.update(identity(alt) for r in feed if 'Fiscalización' in r.get('signal_types',[]) for alt in r.get('source_alternatives',[]))
    context_ids={identity(alt) for r in feed if 'Fiscalización' in r.get('signal_types',[]) for alt in r.get('historical_sanction_context',[])}
    old_current={('https://www.suseso.gob.cl/609/w3-propertyvalue-799701.html',key) for key,day in professional.items()
        if not recent(day,90) and all(professional_validity[key]) and professional_validity[key][0]<=AS_OF.isoformat()<=professional_validity[key][1]}
    for missing in old_current-history_ids:failures.append('missing_current_historical_stock_history:'+str(missing))
    for missing in old_current-context_ids:failures.append('missing_current_historical_stock_context:'+str(missing))
    if len(old_current)!=reconciliation.get('current_historical_sanction_stock',{}).get('published'):
        failures.append('current_historical_stock_count_mismatch')
    counts={}
    for days in (30,90):
        sis_ids={(url,None) for url,v in sis.items() if recent(v['publication'],days) or recent(v['emission'],days)}
        su_ids={('https://www.suseso.gob.cl/609/w3-propertyvalue-799701.html',key) for key,day in professional.items() if recent(day,days)}|{(url,None) for url,day in published_news.items() if recent(day,days)}
        counts[str(days)]={'sis':len(sis_ids),'suseso':len(su_ids)}
        for source,ids in (('superintendencia_fiscalizacion',sis_ids),('suseso_fiscalizacion',su_ids)):
            declared=reconciliation['windows'][source][str(days)]['official_confirmed']
            if declared!=len(ids):failures.append(f'count_mismatch:{source}:{days}:{declared}:{len(ids)}')
            for missing in ids-history_ids:failures.append('missing_history:'+str(missing))
            for missing in ids-feed_ids:failures.append('missing_feed_reference:'+str(missing))
    if len(undated)!=10:failures.append('undated_report_inventory_incomplete')
    if len(professional)!=101:failures.append('professional_register_inventory_incomplete')
    for row in history:
        if row.get('source_record_id') in professional and row.get('publication_date') is not None:failures.append('invented_register_publication:'+row['source_record_id'])
    expected_stock={r['url'].rstrip('/') for r in json.loads((runtime/'isolated-replay/collector_inventory.json').read_text()) if r['source_slug']=='superintendencia_fiscalizacion'}
    if expected_stock-set(sis):failures.append('historical_listing_inventory_mismatch')
    exact={str(days):{'sis':sum(recent(v['publication'],days-1) or recent(v['emission'],days-1) for v in sis.values()),'suseso':sum(recent(day,days-1) for day in professional.values())+sum(recent(day,days-1) for day in published_news.values())} for days in (30,90)}
    for days,values in exact.items():
        for slug,label in (('superintendencia_fiscalizacion','sis'),('suseso_fiscalizacion','suseso')):
            if reconciliation['exact_calendar_windows'][slug][days]['official_confirmed']!=values[label]:failures.append('exact_calendar_count_mismatch')
    return dict(historical_listing_inventory_differences=sorted(expected_stock-set(sis)),reviewer='independent_read_only_official_html_reconciliation',verdict='PASS' if not failures else 'FAIL',failures=failures,counts=counts,sis_unique_listing_urls=len(sis),professional_offices=len(professional),current_historical_stock=len(old_current),exact_calendar_windows=exact,official_news_inventory=len(official_news),news_primary_reviews_verified=news_primary_reviews_verified,date_uncertain_reports=len(undated),coverage_complete=False,limits=['Bounded dated coverage; daily publication dates of ten reports remain unknown.','Primary legal readings are explicit editorial reviews with matching native PDF hashes; this script does not certify legal interpretation.','Global QA and existing product Reviewer remain independent release gates.'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();result=run(a.runtime);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False));raise SystemExit(bool(result['failures']))
