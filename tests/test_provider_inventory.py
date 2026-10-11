"""Publication isolation protects against plausible, unrelated timestamps."""
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('provider_inventory',Path(__file__).parents[1]/'scripts/provider_inventory.py')
inventory=importlib.util.module_from_spec(spec);spec.loader.exec_module(inventory)


def test_related_jsonld_does_not_date_current_article():
    html='''<h1>New capacity</h1><p>Capacity article</p><script type="application/ld+json">{"@type":"NewsArticle","url":"https://www.redsalud.cl/noticias/other","headline":"Other article","datePublished":"2026-09-04"}</script>'''
    row=inventory.detail_evidence('redsalud','https://www.redsalud.cl/noticias/current',html)
    assert row['date_stamps']==[]
    assert row['article_schemas'][0]['datePublished']=='2026-09-04'


def test_modified_and_body_event_are_not_publication():
    html='''<meta property="article:modified_time" content="2026-10-05"><h1>Agreement</h1><p>Effective October 1, 2026</p>'''
    row=inventory.detail_evidence('bupa_chile','https://www.bupa.cl/agreement',html)
    assert row['date_stamps']==[]
    assert row['date_modified']=='2026-10-05'


def test_current_jsonld_publication_is_associated_by_url():
    html='''<h1>New capacity</h1><script type="application/ld+json">{"@graph":[{"@type":"NewsArticle","url":"https://www.redsalud.cl/noticias/current/","datePublished":"2026-09-04T13:00:00-04:00","dateModified":"2026-09-21"}]}</script>'''
    row=inventory.detail_evidence('redsalud','https://www.redsalud.cl/noticias/current',html)
    assert row['date_stamps'][0]['date']=='2026-09-04'
    assert row['article_schemas'][0]['dateModified']=='2026-09-21'
