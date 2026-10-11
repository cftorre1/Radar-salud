"""Official public metadata diagnostics; no AI and no WAF challenge handling."""
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urljoin,urlparse

from provider_inventory import Inventory,Metadata,SLUGS
from radar_salud.pending_queue import atomic_json
from radar_salud.public_source_pipeline import _PfizerArticle


class HeaderStructure(HTMLParser):
    def __init__(self):
        super().__init__();self.before=[];self.fields=[];self.h1=False;self.stack=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);self.stack.append((tag,a.get('class'),a.get('slot')))
        if tag=='h1' or tag=='helix-core-heading' and a.get('variant')=='h1':self.h1=True
        for key,value in a.items():
            if re.search(r'publish|fecha|date|artic|time',key,re.I) and value and len(value)<200:
                self.fields.append({'tag':tag,'attribute':key,'value':value})
    def handle_endtag(self,tag):
        index=next((n for n in range(len(self.stack)-1,-1,-1) if self.stack[n][0]==tag),None)
        if index is not None:self.stack=self.stack[:index]
    def handle_data(self,value):
        text=' '.join(value.split())
        if not self.h1 and text and not any(t[0] in ('script','style','nav','header','footer') for t in self.stack):
            self.before.append({'text':text[:100],'parent':self.stack[-1] if self.stack else None})


def main():
    root=Path('.');out={'version':1,'promotion':'none','ai_calls':0,'sources':{}}
    for slug in SLUGS:
        inv=Inventory(slug,date(2026,10,11),root,limit=70)
        capture=json.loads((root/f'data/audits/provider_inventory_2026_10_11/{slug}.json').read_text())
        rows=[]
        targets=[]
        if slug=='redsalud':targets=[x['url'] for x in capture['items'] if x.get('date_reason')=='conflicting_publication_stamps']
        if slug=='bupa_chile':targets=[x['url'] for x in capture['items'][:7]]
        if slug=='pfizer_chile':targets=[x['url'] for x in capture['items']]
        if slug=='indisa':targets=[inv.page.replace('www.',''),inv.origin+'/blog',inv.origin+'/sitemap-0.xml',inv.origin+'/rss',inv.origin+'/api/noticias']
        if slug in ('red_davila','clinicas_achs_salud','clinicas_chile'):targets=[inv.page]
        for url in targets:
            page=inv.fetch(url,'official_metadata_diagnostic')
            if not page:continue
            meta=Metadata();meta.feed(page);header=HeaderStructure();header.feed(page)
            row={'url':url,'metadata':{k:v for k,v in meta.meta.items() if re.search(r'date|publish|modified|created|type|url|fecha',k,re.I)},'header_structure':header.before[-12:],'date_attributes':header.fields,
                 'scripts':meta.scripts,'public_same_host_endpoints':[]}
            if slug=='pfizer_chile':
                article=_PfizerArticle();article.feed(page);article.finish()
                row.update(title=article.title,body_words=len(article.body.split()),excerpt=' '.join(article.body.split()[:20]))
            if slug in ('red_davila','clinicas_achs_salud','bupa_chile'):
                for script in [s for s in meta.scripts if inv.own(urljoin(url,s))][-5:]:
                    js=inv.fetch(urljoin(url,script),'official_public_frontend_script')
                    if not js:continue
                    endpoints=set(re.findall(r'https?://[^\s"<>`\\]+',js))
                    for endpoint in endpoints:
                        p=urlparse(endpoint)
                        if re.search(r'api|notic|noved|cms|content|prontus',p.path,re.I):
                            row['public_same_host_endpoints'].append({'host':p.netloc,'path':p.path[:250],'same_host':inv.own(endpoint)})
                    # Code fragments contain only route names near newsroom
                    # pagination, no article body or private credentials.
                    row.setdefault('frontend_route_hints',[]).extend(
                        re.findall(r'.{0,80}(?:api/noticias|api/novedades|artic_fecha|fechapub|pageSize|GetNews|newsApi|novedades\?).{0,100}',js)[:15])
            rows.append(row)
        if slug=='clinicas_chile':
            text=inv.fetch('/kbe_knowledgebase-sitemap.xml','library_sitemap_diagnostic')
            if text:rows.append({'url':inv.origin+'/kbe_knowledgebase-sitemap.xml','sitemap_locations':re.findall(r'<loc>(.*?)</loc>',text)})
            text=inv.fetch('/?feed=rss2&post_type=kbe_knowledgebase','library_feed_diagnostic')
            if text:rows.append({'url':inv.origin+'/?feed=rss2&post_type=kbe_knowledgebase','feed_publications':re.findall(r'<pubDate>(.*?)</pubDate>',text),'feed_links':re.findall(r'<link>(.*?)</link>',text)})
        out['sources'][slug]={'requests':inv.requests,'metadata':rows}
        if slug=='indisa':
            chrome=shutil.which('google-chrome') or shutil.which('chromium')
            browser=[]
            for target in (inv.page,'https://www.indisa.cl/blog/clinica-indisa-fortalece-su-propuesta-de-atencion-preferente-junto-a-isapre-esencial'):
                row={'url':target,'method':'ordinary unauthenticated native Chrome navigation; no challenge handling','http_status':'not_observed_by_dump_dom'}
                if not chrome:row['error']='native_chrome_unavailable'
                else:
                    try:
                        result=subprocess.run([chrome,'--headless','--disable-gpu','--no-sandbox',
                            '--user-data-dir='+str(root.resolve()/'work/provider_inventory/browser-profile'),
                            '--virtual-time-budget=6000','--dump-dom',target],capture_output=True,text=True,timeout=25)
                        from radar_salud.public_source_pipeline import _IndisaArticle
                        article=_IndisaArticle();article.feed(result.stdout);article.finish()
                        row.update(exit_code=result.returncode,dom_sha256=__import__('hashlib').sha256(result.stdout.encode()).hexdigest(),
                            original_article_title=article.title,original_publication_date=article.event_date(),
                            challenge_detected=bool(re.search(r'Just a moment|cf-chl-|captcha|Access denied',result.stdout,re.I)),
                            stderr_kind='TLS_or_browser_error' if re.search(r'ERR_|SSL|certificate',result.stderr) else None)
                    except Exception as exc:row['error']=type(exc).__name__
                browser.append(row)
            out['sources'][slug]['ordinary_browser']=browser
    atomic_json('data/audits/provider_original_diagnostics_2026_10_11.json',out)
    print('PROVIDER_DIAGNOSTICS_JSON '+json.dumps(out,ensure_ascii=False,separators=(',',':')))


if __name__=='__main__':main()
