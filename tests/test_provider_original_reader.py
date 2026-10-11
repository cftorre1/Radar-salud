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
        return SimpleNamespace(returncode=0,stdout='<h1>Actual DOM</h1>')
    monkeypatch.setattr('radar_salud.provider_original_reader.subprocess.run',run)
    assert read_provider_detail(URL,denied(403))=='<h1>Actual DOM</h1>'

def test_unavailable_native_browser_preserves_denied_error(monkeypatch):
    monkeypatch.setattr('radar_salud.provider_original_reader.shutil.which',lambda _:None)
    with pytest.raises(HTTPError):read_provider_detail(URL,denied(403))
