from urllib.error import HTTPError
from types import SimpleNamespace
import pytest
from radar_salud.provider_original_reader import read_provider_detail

URL='https://www.davila.cl/novedades/medicina-deportiva-llega-a-red-davila'

def denied(code):
    def fetch(url):raise HTTPError(url,code,'denied',{},None)
    return fetch

def test_successful_http_does_not_launch_browser(monkeypatch):
    monkeypatch.setattr('radar_salud.provider_original_reader.subprocess.run',lambda *a,**k:pytest.fail('HTTP succeeds'))
    assert read_provider_detail(URL,lambda _: '<h1>Original</h1>')=='<h1>Original</h1>'

@pytest.mark.parametrize('url,code',[(URL,429),('https://www.indisa.cl/blog/noticia',403),('https://www.davila.cl/privado',403)])
def test_browser_is_restricted_to_official_davila_article_403(monkeypatch,url,code):
    monkeypatch.setattr('radar_salud.provider_original_reader.shutil.which',lambda _:pytest.fail('Not eligible'))
    with pytest.raises(HTTPError):read_provider_detail(url,denied(code))

def test_ordinary_browser_preserves_tls_and_source_validation_contract(monkeypatch):
    monkeypatch.setattr('radar_salud.provider_original_reader.shutil.which',lambda _: '/usr/bin/chromium')
    def run(command,**kwargs):
        assert command[-1]==URL
        assert not any('ignore-certificate' in x or 'proxy' in x or 'user-agent' in x for x in command)
        assert kwargs['timeout']==25
        return SimpleNamespace(returncode=0,stdout=own_dom())
    monkeypatch.setattr('radar_salud.provider_original_reader.subprocess.run',run)
    assert read_provider_detail(URL,denied(403))==own_dom()

def test_unavailable_native_browser_preserves_denied_error(monkeypatch):
    monkeypatch.setattr('radar_salud.provider_original_reader.shutil.which',lambda _:None)
    with pytest.raises(HTTPError):read_provider_detail(URL,denied(403))

def own_dom(canonical=URL,schema=URL):
    import json
    return (f'<link rel="canonical" href="{canonical}"><meta property="article:published_time" content="2026-08-01">'
        '<h1>Medicina Deportiva llega a Red Dávila</h1><p>Nuevas prestaciones en dos centros existentes.</p>'
        '<script type="application/ld+json">'+json.dumps({'@type':'NewsArticle','url':schema,'datePublished':'2026-08-01'})+'</script>')

@pytest.mark.parametrize('dom',[own_dom(schema='https://other.example/press-copy'),
    own_dom(canonical='https://other.example/press-copy'),own_dom()+'<div>Just a moment cf-chl-</div>'])
def test_foreign_identity_and_challenge_dom_stop_before_paid_analysis(monkeypatch,dom):
    from radar_salud.beta_sources import process_curated_beta_source
    from radar_salud.models import RawItem
    from radar_salud.processing import DeferredProcessing
    monkeypatch.setattr('radar_salud.beta_sources.fetch_html',denied(403))
    monkeypatch.setattr('radar_salud.provider_original_reader.shutil.which',lambda _: '/usr/bin/chromium')
    monkeypatch.setattr('radar_salud.provider_original_reader.subprocess.run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=dom))
    monkeypatch.setattr('radar_salud.llm_analysis.analyze_news',lambda **kw:pytest.fail('Unverified identity must not consume AI'))
    raw=RawItem('red_davila','Medicina Deportiva llega a Red Dávila',URL,'Red Dávila','corporate',
        '2026-08-01',metadata={'market_role':'provider','source_quality_gate':'passed','publication_date_source':'verified_article_header'})
    with pytest.raises(DeferredProcessing,match='detail unavailable'):process_curated_beta_source(raw,{'slug':'red_davila'})

@pytest.mark.parametrize('suffix',['?alternate=1','#related'])
def test_unreviewed_browser_query_and_fragment_are_not_eligible(monkeypatch,suffix):
    monkeypatch.setattr('radar_salud.provider_original_reader.shutil.which',lambda _:pytest.fail('Not eligible'))
    with pytest.raises(HTTPError):read_provider_detail(URL+suffix,denied(403))
