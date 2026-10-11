"""Synthetic independent raw-reader regression; no product/parser/network imports."""
import importlib.util
from pathlib import Path
from datetime import date
from urllib.parse import urlencode
import unittest

spec=importlib.util.spec_from_file_location('reviewer_audit',Path(__file__).resolve().parents[1]/'scripts/audit_global_captures.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
Q={'date[min]':'2026-07-20','date[max]':'2026-07-28'}
base='https://www.paho.org/en/news'
def url(n):return base+'?'+urlencode(Q|({'page':str(n)} if n else {}))
FORM='<div class="view-filters"><form id="views-exposed-form-news-news-page" data-drupal-selector="views-exposed-form-news-news-page" method="get" action="/en/news"><input name="date[min]" value="2026-07-20"><input name="date[max]" value="2026-07-28"></form></div>'
VIEW='<div class="news-grid view view-news view-id-news view-display-id-news_page">'
CARD='<div class="views-row"><time datetime="2026-07-23"></time><div class="views-field-title"><a href="/en/news/23-7-2026-official-update">Official update</a></div></div>'
def html(content='',extra='',form=FORM):return ('<html><main><h1>News</h1>'+VIEW+form+content+'</div>'+extra+'</main></html>').encode()
def last(n):return '<nav class="pager"><a rel="last" href="'+url(n)+'">Last</a></nav>'
def setup(single=False):
 raw={url(0):html(CARD+('' if single else last(1))),url(1):html() if single else html(CARD+last(1))}
 if not single:raw[url(2)]=html()
 return raw

def checks(raw,single=False,numbered=False):
 ordered=sorted(raw,key=lambda u:int(dict(audit.parse_qsl(audit.urlsplit(u).query)).get('page',0)))
 readers={u:audit.NativeHTML(b) for u,b in raw.items()}
 rows={u:audit.independent_index(b,{'format':'paho_html','section':'regional_news'},u,date(2026,10,11)) for u,b in raw.items()}
 return audit.native_empty_end_checks(ordered,readers,rows,single,numbered)

def numbered_pager(n,language='en'):
 active='Página actual' if language=='es' else 'Current page'
 regular='Página' if language=='es' else 'Page'
 first='<li class="pager__item pager__item--first"><a href="'+url(0)+'" rel="prev" title="Go to first page">First page «</a></li>'
 prior='<li class="pager__item pager__item--previous"><a href="'+url(n-1)+'" rel="prev" title="Go to previous page">Previous page ‹</a></li>'
 numbers=''.join('<li class="pager__item"><a href="'+url(i)+'" title="Go to page '+str(i+1)+'">'+regular+' '+str(i+1)+'</a></li>' for i in range(n))
 current='<li class="pager__item is-active active"><a href="'+url(n)+'" title="'+active+'" aria-current="page">'+active+' '+str(n+1)+'</a></li>'
 # Unlike normal page 0, publisher pager anchors explicitly carry page=0.
 body=first+prior+numbers+current
 body=body.replace(url(0)+'"',url(0)+'&page=0"')
 return '<nav class="pager-nav text-center" role="navigation" aria-labelledby="pagination-heading"><h2 id="pagination-heading">Pagination</h2><ul class="pagination js-pager__items">'+body+'</ul></nav>'

def numbered_setup(n=1):
 raw={url(i):html(CARD) for i in range(n+1)}
 raw[url(n)]=html(CARD+numbered_pager(n))
 raw[url(n+1)]=html()
 return raw

class EndProof(unittest.TestCase):
 def test_advertised_native_last_positive(self):self.assertTrue(all(checks(setup()).values()))
 def test_single_page_positive(self):self.assertTrue(all(checks(setup(True),True).values()))
 def test_current_negations(self):
  mutations={
   'bare_200':b'<html><h1>News</h1></html>',
   'unclosed_view':html().replace(b'</div></main>',b'</main>'),
   'unclosed_form':html().replace(b'</form>',b''),
   'missing_view_class':html().replace(b'view-id-news',b'view-id-other'),
   'wrong_title':html().replace(b'>News</h1>',b'>Search</h1>'),
   'duplicate_view':html(extra=VIEW+'</div>'),
   'form_outside':html(form='',extra=FORM),
   'wrong_action':html().replace(b'action="/en/news"',b'action="/en/alerts"'),
   'wrong_selector':html().replace(b'data-drupal-selector="views-exposed-form-news-news-page"',b'data-drupal-selector="other"'),
   'wrong_method':html().replace(b'method="get"',b'method="post"'),
   'wrong_echo':html().replace(b'value="2026-07-20"',b'value="2026-08-20"'),
   'duplicate_date_input':html(form=FORM.replace('</form>','<input name="date[min]" value="2026-07-20"></form>')),
   'error_inside_view':html(content='<div>Unable to load news</div>'),
   'empty_view_content':html(content='<div class="view-content"></div>'),
   'current_pager':html(content='<nav class="pager"></nav>'),
   'current_empty_native_nav':html(content='<nav class="pager-nav text-center" role="navigation" aria-labelledby="pagination-heading"></nav>'),
   'current_empty_native_list':html(content='<ul class="pagination"></ul>'),
   'outside_native_next':html(extra='<a rel="next" href="'+url(3)+'">Next</a>'),
   'current_news_card':html(content=CARD),
  }
  for name,body in mutations.items():
   with self.subTest(name=name):
    raw=setup();raw[url(2)]=body;self.assertFalse(all(checks(raw).values()))
 def test_previous_and_last_negations(self):
  cases={
   'prior_next':html(CARD+last(1)+'<a rel="next" href="'+url(2)+'">Next</a>'),
   'prior_empty':html(last(1)),
   'prior_invalid_date':html(CARD.replace('2026-07-23','not-a-date')+last(1)),
   'prior_query_outside_date':html(CARD.replace('2026-07-23','2026-08-23')+last(1)),
   'prior_unclosed_view':html(CARD+last(1)).replace(b'</div></main>',b'</main>'),
   'prior_cards_outside_view':html(last(1),extra=CARD),
   'last_other_query':html(CARD+last(1).replace('2026-07-20','2026-06-20')),
   'cap8':html(CARD+last(8)),
  }
  for name,body in cases.items():
   with self.subTest(name=name):
    raw=setup();raw[url(1)]=body;self.assertFalse(all(checks(raw).values()))
  raw={url(0):html(CARD),url(1):html(CARD),url(2):html()};self.assertFalse(all(checks(raw).values()))
  self.assertFalse(all(checks({url(0):html()}).values()))
  raw=setup();raw[url(3)]=raw.pop(url(2));self.assertFalse(all(checks(raw).values()))
 def test_single_page_negations(self):
  for content in (CARD+last(0),CARD+'<nav class="pager"></nav>',CARD+'<a rel="next" href="'+url(1)+'">Next</a>'):
   with self.subTest(content=content):
    raw=setup(True);raw[url(0)]=html(content);self.assertFalse(all(checks(raw,True).values()))

class NumberedEndProof(unittest.TestCase):
 def test_native_numbered_en_positive(self):
  self.assertTrue(all(checks(numbered_setup(),numbered=True).values()))
  self.assertTrue(all(checks(numbered_setup(7),numbered=True).values()))
 def test_native_numbered_es_positive(self):
  raw=numbered_setup(4)
  raw[url(4)]=html(CARD+numbered_pager(4,'es'))
  raw={u.replace('/en/news','/es/noticias'):b.replace(b'/en/news',b'/es/noticias').replace(b'>News</h1>',b'>Noticias</h1>') for u,b in raw.items()}
  self.assertTrue(all(checks(raw,numbered=True).values()))
 def test_native_numbered_mutations(self):
  body=numbered_pager(1)
  mutations={
   'no_nav_role':body.replace(' role="navigation"',''),
   'no_aria_label':body.replace('aria-labelledby="pagination-heading"','aria-labelledby="other"'),
   'nav_unclosed':body.replace('</nav>',''),
   'list_unclosed':body.replace('</ul>',''),
   'list_wrong_class':body.replace('js-pager__items','other'),
   'nested_list':body.replace('<ul ','<div><ul ').replace('</ul>','</ul></div>'),
   'li_unclosed':body.replace('</li>','',1),
   'a_unclosed':body.replace('</a>','',1),
   'no_active':body.replace('pager__item is-active active','pager__item').replace(' aria-current="page"','').replace('title="Current page"','title="Go to page 2"').replace('>Current page 2<','>Page 2<'),
   'no_active_aria':body.replace(' aria-current="page"',''),
   'wrong_aria':body.replace('aria-current="page"','aria-current="true"'),
   'wrong_current_title':body.replace('title="Current page"','title="Last page"'),
   'wrong_current_label':body.replace('>Current page 2<','>Current page 3<'),
   'duplicate_active':body.replace('class="pager__item"><a','class="pager__item is-active active"><a'),
   'wrong_href_bound':body.replace('2026-07-20','2026-07-19',1),
   'wrong_full_query':body.replace('page=0"','page=0&extra=x"',1),
   'first_wrong_target':body.replace('page=0"','page=1"',1),
   'previous_wrong_target':body.replace('href="'+url(0)+'&page=0" rel="prev" title="Go to previous page"','href="'+url(1)+'" rel="prev" title="Go to previous page"'),
   'duplicate_page':body.replace('page=0"','page=0&page=0"',1),
   'wrong_host':body.replace('www.paho.org','www.who.int',1),
   'fragment':body.replace('page=0"','page=0#other"',1),
   'missing_href':body.replace('href="','data-href="',1),
   'forward':body.replace('</ul>','<li class="pager__item pager__item--next"><a rel="next" href="'+url(2)+'">Next</a></li></ul>'),
   'ellipsis':body.replace('</ul>','<li class="pager__item pager__item--ellipsis">…</li></ul>'),
   'extra_anchor':body.replace('</nav>','<a href="'+url(2)+'">Extra</a></nav>'),
   'wrong_regular_title':body.replace('Go to page 1','Go to page 2'),
   'wrong_regular_label':body.replace('>Page 1<','>Page 2<'),
   'foreign_regular_rel':body.replace('title="Go to page 1"','title="Go to page 1" rel="last"'),
   'sparse':body.replace('<li class="pager__item"><a href="'+url(0)+'&page=0" title="Go to page 1">Page 1</a></li>',''),
   'duplicate_number':body.replace('<li class="pager__item"><a','<li class="pager__item"><a href="'+url(0)+'&page=0" title="Go to page 1">Page 1</a></li><li class="pager__item"><a',1),
  }
  for name,pager in mutations.items():
   with self.subTest(name=name):
    raw=numbered_setup();raw[url(1)]=html(CARD+pager)
    self.assertFalse(all(checks(raw,numbered=True).values()))
  raw=numbered_setup();raw[url(1)]=html(CARD,extra=body)
  self.assertFalse(all(checks(raw,numbered=True).values()))
 def test_native_numbered_cap_on_every_positive_page(self):
  self.assertFalse(all(checks(numbered_setup(8),numbered=True).values()))
  for single,numbered in ((False,False),(True,False),(False,True)):
   with self.subTest(single=single,numbered=numbered):
    raw=numbered_setup() if numbered else setup(single)
    raw[url(0)]=html(CARD+numbered_pager(8))
    self.assertFalse(all(checks(raw,single,numbered).values()))
  raw=numbered_setup();raw[url(0)]=html(CARD+numbered_pager(8).replace('title="Go to page 9"','title="Unrecognized page"'))
  self.assertFalse(all(checks(raw,numbered=True).values()))

if __name__=='__main__':unittest.main(verbosity=2)
