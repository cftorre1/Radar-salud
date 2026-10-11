import json
from radar_salud import beta_sources
from radar_salud.public_source_pipeline import _VisibleArticle


def test_cms_archive_recovers_hidden_capacity_and_verifies_own_publication(monkeypatch):
    url='https://www.andessalud.cl/novedades/frutillar-nueva-capacidad/'
    title='Andes Salud inaugura un nuevo centro en Frutillar'
    post={'id':123,'status':'publish','link':url,'date':'2026-07-23T10:00:00','title':{'rendered':title}}
    def fetch(target):
        if '/wp-json/' in target:return json.dumps([post])
        if target.rstrip('/')==url.rstrip('/'):return f'<h1>{title}</h1><span>julio 23, 2026</span><p>Nueva capacidad con tres box de consultas.</p>'
        return '<h1>Novedades</h1>'
    monkeypatch.setattr(beta_sources,'fetch_html',fetch)
    scout=beta_sources.CuratedBetaSourceScout('andes_salud')
    rows=scout.discover()
    assert len(rows)==1 and rows[0].event_date=='2026-07-23'
    assert rows[0].metadata['cms_post_id']==123
    post['date']='2026-07-24T10:00:00'
    import pytest
    with pytest.raises(RuntimeError):scout.discover()


def test_related_cards_cannot_make_an_educational_article_material():
    html='<h1>Meningitis: síntomas y prevención</h1><p>Información médica educativa.</p><h3>Blog Andes Salud</h3><a>Andes y MetLife renuevan convenio estratégico</a>'
    article=_VisibleArticle();article.feed(html)
    assert 'MetLife' not in ' '.join(article.text)
