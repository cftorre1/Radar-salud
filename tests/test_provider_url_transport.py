from radar_salud import scouts


def test_official_unicode_slug_is_encoded_without_double_escaping(monkeypatch):
    requests=[]
    class Headers:
        def get_content_charset(self):return 'utf-8'
    class Response:
        headers=Headers()
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return b'original'
    monkeypatch.setattr(scouts,'urlopen',lambda req,timeout:requests.append(req) or Response())
    url='https://www.achs.cl/centro-de-noticias/noticia/2026/comieé?category=salud%20laboral'
    assert scouts.fetch_html(url)=='original'
    assert requests[0].full_url.endswith('/comie%C3%A9?category=salud%20laboral')
    assert requests[0].headers['User-agent']=='RadarSaludBot/0.1 (+public-source-monitor)'
