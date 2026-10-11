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

def checks(raw,single=False):
 ordered=sorted(raw,key=lambda u:int(dict(audit.parse_qsl(audit.urlsplit(u).query)).get('page',0)))
 readers={u:audit.NativeHTML(b) for u,b in raw.items()}
 rows={u:audit.independent_index(b,{'format':'paho_html','section':'regional_news'},u,date(2026,10,11)) for u,b in raw.items()}
 return audit.native_empty_end_checks(ordered,readers,rows,single)

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

if __name__=='__main__':unittest.main(verbosity=2)
