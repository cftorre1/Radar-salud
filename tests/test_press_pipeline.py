from radar_salud.press_pipeline import parse_df_listing, process_df_item, raw_reuters_item, process_reuters_item
from radar_salud.source_scouts import DfHealthScout

DF_CFG={'slug':'diario_financiero','name':'Diario Financiero','source_type':'press_high_trust','system_domain':'HEALTH','base_confidence':93,'default_category':'Mercado'}
REU_CFG={'slug':'reuters','name':'Reuters','source_type':'press_high_trust','system_domain':'GLOBAL_HEALTH','base_confidence':96,'default_category':'Radar Mundo'}

def test_df_high_trust_without_second_source():
    html='<a href="/empresas/salud/noticia">Las isapres logran aumento de cotizantes por primera vez</a><a href="/autos">Nuevo automóvil</a>'
    items=parse_df_listing(html)
    assert len(items)==1
    sig=process_df_item(items[0], DF_CFG)
    assert sig.confidence_score >= 93
    assert sig.validation_status == 'high_trust_press'
    assert sig.corroboration_status == 'not_required'

def test_reuters_is_world_signal():
    raw=raw_reuters_item('AI reshapes healthcare software market','https://reuters.com/x','Healthcare firms are changing strategy.')
    sig=process_reuters_item(raw, REU_CFG)
    assert sig.category == 'Radar Mundo'
    assert sig.system_domain == 'GLOBAL_HEALTH'
    assert sig.confidence_score >= 96


def test_df_scout_binds_detail_date_before_queue_classification(monkeypatch):
    listing='<a href="/empresas/salud/nueva-inversion-clinica">Clínica anuncia nueva inversión hospitalaria</a>'
    detail='<meta property="article:published_time" content="2026-10-10T09:15:00-03:00"><meta name="description" content="La clínica anunció una inversión relevante."><div id="articleLock" class="CUERPO"><p>Detalle de inversión hospitalaria y expansión de capacidad.</p></div>'
    def fake_fetch(url):
        return listing if url in DfHealthScout.PAGES else detail
    monkeypatch.setattr("radar_salud.source_scouts.fetch_html", fake_fetch)
    items=DfHealthScout().discover()
    assert len(items)==1
    assert items[0].event_date=="2026-10-10"
    assert "inversión relevante" in items[0].raw_text
    assert items[0].metadata["page_text"]
