"""Read-only, bounded original inventories. No AI, admissions, or promotions.

Publication evidence is distinct from sitemap lastmod, upload paths, event dates
and capture time. Failed alternatives and request limits are durable evidence;
an accessible landing page alone never establishes coverage completeness.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import quote, urljoin, urlparse, urlunparse
from urllib.request import Request, HTTPRedirectHandler, build_opener
import xml.etree.ElementTree as ET

from radar_salud.pending_queue import atomic_json
from radar_salud.source_scouts import CorporateNewsroomScout, ClinicasChileScout
from radar_salud.beta_sources import CuratedBetaSourceScout, _ProviderPublication
from radar_salud.public_source_pipeline import (
    _BupaArticle, _IndisaArticle, _PfizerArticle, _RedSaludArticle, _VisibleArticle, _date,
)

SLUGS = ('redsalud', 'bupa_chile', 'indisa', 'red_davila', 'andes_salud',
         'clinicas_chile', 'pfizer_chile', 'clinicas_achs_salud')
UA = 'RadarSaludBot/0.1 (+public-source-monitor)'


class RedirectRecorder(HTTPRedirectHandler):
    def __init__(self):super().__init__();self.chain=[]
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        self.chain.append({'from':req.full_url,'status':code,'to':newurl})
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def canonical(url):
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip('/'), '', p.query, ''))


def iso(value):
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.meta={}; self.schemas=[]
        self.scripts=[]; self._json=None; self._anchor=None; self._parts=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs); tag=tag.lower()
        if tag=='meta': self.meta[(a.get('property') or a.get('name') or '').lower()]=a.get('content')
        if tag=='link' and a.get('href'): self.links.append((a['href'],a.get('rel','')))
        if tag=='a': self._anchor=a.get('href'); self._parts=[]
        if tag=='script':
            if a.get('src'): self.scripts.append(a['src'])
            if a.get('type')=='application/ld+json': self._json=[]
    def handle_data(self, value):
        if self._json is not None: self._json.append(value)
        if self._anchor: self._parts.append(value)
    def handle_endtag(self, tag):
        if tag.lower()=='a' and self._anchor:
            self.links.append((self._anchor,' '.join(' '.join(self._parts).split())))
            self._anchor=None
        if tag.lower()=='script' and self._json is not None:
            try: self.schemas.append(json.loads(''.join(self._json)))
            except (ValueError,TypeError): pass
            self._json=None


def schema_articles(value):
    if isinstance(value,list):
        for item in value: yield from schema_articles(item)
    elif isinstance(value,dict):
        kind=value.get('@type'); kinds=kind if isinstance(kind,list) else [kind]
        if any(x in ('Article','NewsArticle','BlogPosting') for x in kinds):
            yield {k:value.get(k) for k in ('@type','@id','url','mainEntityOfPage','headline','datePublished','dateModified')}
        # @graph represents separate entities, not arbitrary related body data.
        if '@graph' in value: yield from schema_articles(value['@graph'])


def detail_evidence(slug, url, html):
    meta=Metadata(); meta.feed(html)
    visible=_VisibleArticle(); visible.feed(html)
    title=visible.title; body=' '.join(visible.text)
    stamps=[]
    if meta.meta.get('article:published_time'):
        stamps.append({'kind':'article:published_time','value':meta.meta['article:published_time'],
                       'date':iso(meta.meta['article:published_time'])})
    schemas=[x for schema in meta.schemas for x in schema_articles(schema)]
    for schema in schemas:
        identity=schema.get('url') or schema.get('mainEntityOfPage') or schema.get('@id')
        if isinstance(identity,dict): identity=identity.get('@id') or identity.get('url')
        matches_url=bool(identity and canonical(urljoin(url,str(identity)))==canonical(url))
        matches_title=bool(title and str(schema.get('headline') or '').casefold()==title.casefold())
        if schema.get('datePublished') and (matches_url or matches_title):
            stamps.append({'kind':'url_associated_jsonld_datePublished','value':schema['datePublished'],
                           'date':iso(schema['datePublished'])})
    if slug=='bupa_chile':
        a=_BupaArticle();a.feed(html);title=a.title or title;body=a.body or body
        if a.published:stamps.append({'kind':'verified_article_header','value':a.published,'date':_date(a.published)})
    elif slug=='indisa':
        a=_IndisaArticle();a.feed(html);a.finish();title=a.title or title;body=a.body or body
        if a.event_date():stamps.append({'kind':'verified_article_header','value':a.event_date(),'date':a.event_date()})
    elif slug=='redsalud':
        a=_RedSaludArticle(url);a.feed(html);a.finish()
        if a.header_date:stamps.append({'kind':'verified_article_header','value':a.header_date,'date':a.header_date})
    elif slug=='pfizer_chile':
        a=_PfizerArticle();a.feed(html);a.finish();title=a.title;body=a.body
        # Some historical Pfizer cards route to a different article. The
        # component's initial publication field is independent of those cards.
        stamp=re.match(r'^(\d{2}/\d{2}/20\d{2})(?:\s|$)',body)
        if stamp:stamps.append({'kind':'verified_component_publication_header','value':stamp.group(1),'date':_date(stamp.group(1))})
    elif slug in CuratedBetaSourceScout.SOURCES:
        a=_ProviderPublication();a.feed(html);stamp,provenance=a.publication()
        if stamp:stamps.append({'kind':provenance,'value':stamp,'date':stamp})
    return {'detail_title':title,'date_stamps':stamps,'article_schemas':schemas,
            'date_modified':meta.meta.get('article:modified_time'),
            'body_sha256':hashlib.sha256(body.encode()).hexdigest(),
            'body_words':len(body.split()),'excerpt':' '.join(body.split()[:25]),
            'canonical_links':[urljoin(url,x) for x,rel in meta.links if rel=='canonical'],
            'scripts':meta.scripts[:12]}


class Inventory:
    def __init__(self,slug,as_of,root,limit=240,exhaustive=False):
        self.slug=slug;self.as_of=as_of;self.cutoff=as_of-timedelta(days=90)
        self.root=root;self.limit=limit;self.cache={};self.requests=[];self.items={};self.notes=[];self.archive_index=[]
        self.exhaustive=exhaustive
        if slug=='clinicas_chile':
            self.scout=ClinicasChileScout();self.page=self.scout.PAGES[0][1];self.pattern=r'/(?:noticias/)?[^/]+/?'
        elif slug in CorporateNewsroomScout.SOURCES:
            self.scout=CorporateNewsroomScout(slug);self.page=self.scout.PAGE;self.pattern=self.scout.pattern
        else:
            self.scout=CuratedBetaSourceScout(slug);self.page=self.scout.cfg['page'];self.pattern=self.scout.cfg['path']
        self.origin=urlunparse((*urlparse(self.page)[:2],'','','',''))
        self.host=urlparse(self.page).netloc.removeprefix('www.')

    def own(self,url):
        p=urlparse(url)
        return p.scheme=='https' and p.netloc.removeprefix('www.')==self.host

    def fetch(self,url,kind):
        url=urljoin(self.origin+'/',url)
        if not self.own(url):
            self.notes.append({'reason':'alternative_outside_reviewed_official_host','url':url});return None
        if url in self.cache:return self.cache[url]
        if len(self.requests)>=self.limit:
            self.notes.append({'reason':'request_limit_reached','url':url});return None
        now=datetime.now(timezone.utc).isoformat(); row={'url':url,'kind':kind,'captured_at':now,'user_agent':UA,'tls_verified':True}
        encoded=quote(url,safe=':/?&=%+#;,@!$()*[]')
        redirects=RedirectRecorder()
        try:
            with build_opener(redirects).open(Request(encoded,headers={'User-Agent':UA}),timeout=10) as response:
                data=response.read(6*1024*1024+1)
                row.update(status=response.status,final_url=response.url,content_type=response.headers.get('Content-Type'),
                           server=response.headers.get('Server'),wp_total=response.headers.get('X-WP-Total'),
                           wp_total_pages=response.headers.get('X-WP-TotalPages'),response_sha256=hashlib.sha256(data).hexdigest())
                if len(data)>6*1024*1024:raise ValueError('response_size_limit')
                if not self.own(response.url):raise ValueError('unreviewed_redirect_host')
                text=data.decode(response.headers.get_content_charset() or 'utf-8',errors='replace')
        except HTTPError as exc:
            error_body=exc.read(200000)
            row.update(status=exc.code,error_type=type(exc).__name__,error=str(exc),server=exc.headers.get('Server'),
                       response_sha256=hashlib.sha256(error_body).hexdigest(),response_bytes=len(error_body),
                       waf_markers=[token for token in ('Cloudflare','Access Denied','Forbidden','captcha','challenge') if token.lower() in error_body.decode('utf-8',errors='replace').lower()])
            text=None
        except Exception as exc:
            row.update(status=None,error_type=type(exc).__name__,error=str(exc)[:300]);text=None
        row['redirects']=redirects.chain
        self.requests.append(row);self.cache[url]=text
        if text:
            private=self.root/'work/provider_inventory/private'/self.slug
            private.mkdir(parents=True,exist_ok=True)
            (private/(row['response_sha256']+'.txt')).write_text(text)
        return text

    def add(self,url,title,discovered_from,channel='Noticias',stamp=None,provenance=None):
        url=urljoin(discovered_from,url); key=canonical(url)
        if not self.own(url):return
        item=self.items.setdefault(key,{'url':url,'title':unescape(title),'institution':self.slug,
            'category':channel,'discovered_from':[],'date_stamps':[],
            'publication_date':None,'event_date':None,'reporting_period':None,'effective_date':None,
            'materiality':'awaiting_editorial_review','capture_date':datetime.now(timezone.utc).isoformat()})
        if discovered_from not in item['discovered_from']:item['discovered_from'].append(discovered_from)
        if stamp:item['date_stamps'].append({'kind':provenance,'date':stamp,'value':stamp})

    def listing(self,url,channel='Noticias'):
        html=self.fetch(url,'listing:'+channel)
        if not html:return 0
        before=len(self.items)
        try:
            if self.slug=='clinicas_chile':raws=self.scout.discover_from_html(html,channel,url)
            elif self.slug in CorporateNewsroomScout.SOURCES:raws=self.scout.discover_from_html(html)
            else:
                p=Metadata();p.feed(html);raws=[]
                for href,title in p.links:
                    target=urljoin(url,href)
                    if re.fullmatch(self.pattern,urlparse(target).path):
                        self.add(target,title,url,channel)
            for raw in raws:
                self.add(raw.url,raw.title,url,channel,raw.event_date,
                         raw.metadata.get('publication_date_source') or 'dated_news_listing')
        except Exception as exc:self.notes.append({'url':url,'reason':'listing_parse_error','error':str(exc)[:250]})
        # Follow real pagination controls, same reviewed host and listing path.
        p=Metadata();p.feed(html)
        for href,title in p.links:
            target=urljoin(url,href)
            path=urlparse(target).path;listing_path=urlparse(self.page).path.rstrip('/')
            if (self.own(target) and (path.rstrip('/')==listing_path and re.fullmatch(r'page=\d+',urlparse(target).query)
                    or re.fullmatch(re.escape(listing_path)+r'/page/\d+/?',path))):
                self.pagination.add(canonical(target))
        return len(self.items)-before

    def wordpress(self):
        types=self.fetch('/wp-json/wp/v2/types','cms_types')
        bases=['posts']
        if types:
            try:
                for key,value in json.loads(types).items():
                    base=value.get('rest_base')
                    if base and re.search(r'news|notic|knowledge|bibli|estud',key,re.I):bases.append(base)
            except (ValueError,AttributeError):pass
        self.cms_complete=[]
        for base in dict.fromkeys(bases):
            pages=1
            for number in range(1,21):
                url=f'{self.origin}/wp-json/wp/v2/{base}?after={self.cutoff}T00:00:00&before={self.as_of+timedelta(days=1)}T00:00:00&per_page=100&page={number}'
                text=self.fetch(url,'cms_published_posts')
                if not text:break
                try:posts=json.loads(text)
                except ValueError:break
                if not isinstance(posts,list):break
                headers=next(x for x in self.requests if x['url']==url)
                pages=int(headers.get('wp_total_pages') or 1)
                for post in posts:
                    if post.get('status')!='publish' or not post.get('link'):continue
                    target=post['link']
                    title=re.sub('<[^>]+>',' ',post.get('title',{}).get('rendered',''))
                    self.add(target,title,url,'Noticias' if base=='posts' else 'Biblioteca',iso(post.get('date')),'cms_published_post_date')
                if number>=pages:
                    self.cms_complete.append({'rest_base':base,'pages':number,'posts':headers.get('wp_total')});break

    def xml_alternatives(self):
        robots=self.fetch('/robots.txt','robots') or ''
        xmls=[self.origin+x for x in ('/sitemap.xml','/sitemap_index.xml','/sitemap-news.xml','/feed/','/rss.xml')]
        if self.slug=='clinicas_chile':xmls.insert(0,self.origin+'/?feed=rss2&post_type=kbe_knowledgebase')
        xmls.extend(re.findall(r'(?im)^sitemap:\s*(\S+)',robots));visited=set()
        while xmls and len(visited)<18:
            url=xmls.pop(0)
            if url in visited:continue
            visited.add(url);text=self.fetch(url,'sitemap_or_rss')
            if not text:continue
            try:tree=ET.fromstring(text)
            except ET.ParseError:continue
            for node in tree.iter():
                local=node.tag.split('}')[-1]
                children={x.tag.split('}')[-1]:(x.text or '').strip() for x in node}
                target=children.get('loc') or children.get('link')
                if local=='sitemap' and target:
                    if re.search(r'post|news|notic|blog|knowledge|sitemap\.xml',target,re.I):xmls.append(target)
                elif local=='item' and target:
                    stamp=None
                    try:stamp=parsedate_to_datetime(children.get('pubDate','')).date().isoformat()
                    except (ValueError,TypeError,AttributeError):pass
                    if re.fullmatch(self.pattern,urlparse(target).path):self.add(target,children.get('title',''),url,stamp=stamp,provenance='official_rss_pubDate')
                elif local=='url' and target and re.fullmatch(self.pattern,urlparse(target).path):
                    # Bupa root pages include the entire site. Only news-card
                    # provenance can make a root article eligible.
                    if self.slug=='bupa_chile' and canonical(target) not in self.items:continue
                    self.archive_index.append({'url':target,'sitemap':url,'lastmod':children.get('lastmod'),'date_role':'modification_only'})
                    # A complete CMS publication inventory is the authoritative
                    # 90-day index. Do not spend requests on hundreds of old
                    # sitemap articles while current items remain unresolved.
                    if self.cms_complete and canonical(target) not in self.items:continue
                    if self.slug=='clinicas_chile' and canonical(target) not in self.items:continue
                    if self.slug=='red_davila' and not self.exhaustive and canonical(target) not in self.items:continue
                    self.add(target,'',url)
                    item=self.items[canonical(target)]
                    if children.get('lastmod'):item['sitemap_lastmod']=children['lastmod']
                elif local=='url' and target and self.slug=='clinicas_chile' and '/knowledgebase/' in target:
                    self.add(target,'',url,'Library entry')
        self.xml_pages_checked=len(visited)

    def run(self):
        self.pagination=set();self.listing(self.page)
        if self.slug=='clinicas_chile':
            for channel,page in self.scout.PAGES[1:]:
                for n in range(1,5):self.listing(page if n==1 else f'{page}page/{n}/?mostrar=6',channel)
        # Check official archives, including real next links and WordPress routes.
        archive=[f'{self.page}?page={n}' for n in range(1,9)] if self.slug=='redsalud' else [f'{self.page.rstrip("/")}/page/{n}/' for n in range(2,9)]
        if self.slug=='clinicas_achs_salud':archive=[f'{self.page}/{n}' for n in range(2,9)]
        for url in archive:
            added=self.listing(url)
            if added==0 and self.cache.get(url):break
        for url in sorted(self.pagination)[:12]:self.listing(url)
        self.wordpress();self.xml_alternatives()
        if self.slug=='redsalud':self.listing(self.origin+'/observatorio/noticias-clinicas')
        if self.slug=='clinicas_chile':
            self.fetch('/?rest_route=/wp/v2/types','cms_alternative')
            self.fetch('/?rest_route=/wp/v2/posts&after='+str(self.cutoff)+'T00:00:00&per_page=100','cms_alternative')
            self.fetch('/?feed=rss2&post_type=kbe_knowledgebase','library_rss')
        # Public internal search is another official alternative, never a WAF bypass.
        self.listing(self.origin+'/?s='+quote('convenio inversión clínicas'))
        # Include the audited holdings even when listing parsing fails.
        audit=json.loads((self.root/f'data/audits/providers_2026_10_11/{self.slug}.json').read_text())
        for item in audit['original_items']:self.add(item['url'],item['title'],audit['surfaces'][0]['url'],item.get('channel','Noticias'))
        for item in list(self.items.values()):
            if urlparse(item['url']).path.lower().endswith(('.pdf','.xls','.xlsx','.csv')):
                item['date_reason']='document_release_unverified; upload path and body period excluded';continue
            existing={x['date'] for x in item['date_stamps'] if x.get('date')}
            # Sitemap-only old articles need an original detail date; no lastmod
            # cutoff is used to manufacture a chronological inventory.
            html=self.fetch(item['url'],'article_detail')
            if not html:
                item['access_error']=next((x for x in reversed(self.requests) if x['url']==item['url']),{'error':'request_limit_reached'});continue
            detail=detail_evidence(self.slug,item['url'],html)
            if self.slug=='pfizer_chile' and item['title'] and detail['detail_title'] and item['title'].casefold()!=detail['detail_title'].casefold():
                item['listing_title_before_detail_verification']=item['title']
                item['date_stamps']=[x for x in item['date_stamps'] if x['kind']!='listing_date']
                item['listing_identity_mismatch']=True
            item['date_stamps'].extend(detail.pop('date_stamps'));item.update(detail)
            if item.get('detail_title'):item['title']=item['detail_title']
            stamps={x['date'] for x in item['date_stamps'] if x.get('date')}
            item['publication_date']=next(iter(stamps)) if len(stamps)==1 else None
            item['date_reason']='verified_original_publication' if len(stamps)==1 else 'conflicting_publication_stamps' if stamps else 'publication_date_not_exposed'
            if self.slug=='redsalud' and len(stamps)>1:
                article=_RedSaludArticle(item['url']);article.feed(html);article.finish()
                canonical_host=urlparse(article.canonical_url or '').netloc.removeprefix('www.')
                if (canonical_host==self.host and '/observatorio/noticias/' in (article.canonical_url or '')
                        and article.canonical_schema_match and article.header_date==_date(article.published)):
                    item.update(publication_date=article.header_date,date_reason='canonical_identity_jsonld_and_visible_header_agree')
            stamp=item['publication_date']
            item['in_30_days']=bool(stamp and 0<=(self.as_of-date.fromisoformat(stamp)).days<=30) if stamp else None
            item['in_90_days']=bool(stamp and 0<=(self.as_of-date.fromisoformat(stamp)).days<=90) if stamp else None
        dates=[x['publication_date'] for x in self.items.values() if x.get('publication_date')]
        result={'version':2,'slug':self.slug,'as_of':str(self.as_of),'captured_at':datetime.now(timezone.utc).isoformat(),
            'requests':self.requests,'notes':self.notes,'items':list(self.items.values()),'archive_index':self.archive_index,
            'cms_complete':self.cms_complete,'xml_pages_checked':self.xml_pages_checked,
            'pages_checked':len(self.requests),'discovered':len(self.items),'unique':len(self.items),
            'latest_original_at':max(dates) if dates else None,
            'recent_30_count':sum(x.get('in_30_days') is True for x in self.items.values()),
            'recent_90_count':sum(x.get('in_90_days') is True for x in self.items.values()),
            'access_errors':sum(bool(x.get('error')) for x in self.requests),
            'coverage_complete':False,'coverage_reason':'inventory captured; editorial reconciliation and archive boundary review required',
            'promotion':'none','ai_calls':0}
        path=self.root/f'data/audits/provider_inventory_2026_10_11/{self.slug}.json';atomic_json(path,result)
        # Compact durable public metadata, never full original article bodies.
        print('PROVIDER_INVENTORY_JSON '+json.dumps(result,ensure_ascii=False,separators=(',',':')),flush=True)
        return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',choices=SLUGS);ap.add_argument('--as-of',default='2026-10-11');ap.add_argument('--request-limit',type=int,default=240);ap.add_argument('--exhaustive',action='store_true')
    args=ap.parse_args();slugs=[args.source] if args.source else SLUGS
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(Inventory(s,date.fromisoformat(args.as_of),Path('.'),args.request_limit,args.exhaustive).run) for s in slugs]
        for future in futures:future.result()


if __name__=='__main__':main()
