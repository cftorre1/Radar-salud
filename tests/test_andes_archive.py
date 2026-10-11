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


def test_reviewed_campaign_does_not_block_watermark_but_unknown_path_does(monkeypatch):
    post={'status':'publish','link':'https://www.andessalud.cl/destacamos/campana-me-chequeare/','date':'2026-10-05T10:00:00','title':{'rendered':'Campaña: Me Chequearé'}}
    url='https://www.andessalud.cl/novedades/capacidad/'
    article={'id':2,'status':'publish','link':url,'date':'2026-09-08T10:00:00','title':{'rendered':'Nueva capacidad hospitalaria'}}
    def fetch(target):
        if '/wp-json/' in target:return json.dumps([post,article])
        if target.rstrip('/')==url.rstrip('/'):return '<h1>Nueva capacidad hospitalaria</h1><div>septiembre 8, 2026</div><p>Capacidad verificada.</p>'
        return f'<a href="{url}">Nueva capacidad hospitalaria</a>'
    monkeypatch.setattr(beta_sources,'fetch_html',fetch)
    scout=beta_sources.CuratedBetaSourceScout('andes_salud')
    assert len(scout.discover())==1 and not scout.discovery_errors
    post['date']='2026-10-06T10:00:00'
    scout.discover()
    assert any('outside reviewed path' in x for x in scout.discovery_errors)
