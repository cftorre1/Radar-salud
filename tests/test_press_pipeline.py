from radar_salud.press_pipeline import parse_df_listing, process_df_item, raw_reuters_item, process_reuters_item

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
