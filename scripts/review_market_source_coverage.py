"""Independent original-page reconciliation, separate from the production adapters."""
import argparse
import hashlib
import json
import re
from html import unescape
from pathlib import Path
from pypdf import PdfReader


def digest_market(root):
    result={}
    for p in sorted((root/'data/market').glob('*.json')):
        if p.name=='collection_result.json':continue
        result[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted((root/'data/entities').glob('*.json')):result[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def review(capture, root):
    rs=json.loads((capture/'receipts.json').read_text())['receipts'];failures=[];checks=[]
    def check(condition,label):
        checks.append(label)
        if not condition:failures.append(label)
    for r in rs:
        body=capture/r['body_file']
        if body.exists():check(hashlib.sha256(body.read_bytes()).hexdigest()==r['sha256'],'immutable_capture:'+r['body_file'])
    official={}
    for r in rs:
        if r['kind']!='essential_90d' or not r['transport_ok']:continue
        for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',(capture/r['body_file']).read_text(),re.I|re.S):
            cells=[unescape(re.sub('<[^>]+>',' ',s)).strip() for s in re.findall(r'<td\b[^>]*>(.*?)</td>',row,re.I|re.S)]
            if len(cells)!=4:continue
            number=re.search(r'\b20\d{11}\b',cells[1]);date_match=re.match(r'(\d{2})/(\d{2})/(20\d{2})',cells[0])
            if number and date_match:official[number[0]]=f'{date_match[3]}-{date_match[2]}-{date_match[1]}'
    stock=json.loads((root/'data/market/cmf_disclosures.json').read_text())['documents']
    actual={d['official_document_number']:d['published_at'] for d in stock}
    check(all(actual.get(n)==day for n,day in official.items()),'all_original_cmf_rows_and_communication_dates_captured')
    check(all(not d['subsidiary_attribution'] for d in stock),'no_parent_event_propagation')
    check(len({d['record_id'] for d in stock})==len(stock),'unique_official_disclosure_identity')
    known=json.loads((root/'data/entities/isapres.json').read_text())['entities']
    check({e['official_code'] for e in known}=={63,67,76,78,80,81,94,99,107,108},'ten_official_insurer_codes')
    budget=json.loads((root/'data/market/dipres_health_budget.json').read_text())
    check(all(r['budget_state']=='project' and r['price_base_year']==2027 for r in budget['records'] if r['fiscal_year']==2027),'2027_project_never_approved_or_executed')
    fonasa=next((r for r in budget['records'] if r['source_url'].endswith('430523_doc_pdf.pdf') and r['metric']=='gastos'),None)
    receipt=next(r for r in rs if '430523_doc_pdf.pdf' in r['url'])
    raw='\n'.join(p.extract_text(extraction_mode='layout') or '' for p in PdfReader(capture/receipt['body_file']).pages)
    original=re.search(r'^\s*GASTOS\s+(\d[\d.]*)\s*$',raw,re.M)
    check(fonasa is not None and original and fonasa['value']==int(original[1].replace('.','')),'fonasa_original_total_independently_reconciled')
    check(all(r['published_at'] is None for r in budget['records']),'capture_and_reporting_period_never_fabricate_publication')
    return {'status':'PASS' if not failures else 'FAIL','checks':len(checks),'failures':failures,
            'cmf_official_disclosures':len(official),'cmf_captured':len(stock),
            'scope':'Independent parser/checks for captured declared surfaces; no exhaustive universe or cadence certification'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capture-dir',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=review(a.capture_dir,a.root);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result)
    if result['status']!='PASS':raise SystemExit(1)
