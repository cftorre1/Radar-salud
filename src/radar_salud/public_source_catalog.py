"""Sanitized catalogue, derived from current evidence; diagnostics stay administrative."""
from datetime import datetime, timezone

CATALOG={
 'deis':('Datos oficiales','https://deis.minsal.cl/','Estadísticas oficiales de salud.'),
 'prestadores_data':('Datos oficiales','https://www.superdesalud.gob.cl/','Datos públicos de prestadores; superficie verificada.'),
 'achs_seguro_laboral':('Seguridad laboral','https://www.achs.cl/centro-de-noticias/','Noticias verificadas de seguridad laboral.'),
 'global_who':('Global · evidencia internacional','https://www.who.int/publications/','Publicaciones OMS; superficie de metadatos verificada.'),
 'global_paho':('Global · evidencia internacional','https://www.paho.org/es/publicaciones','Publicaciones OPS; superficie de metadatos verificada.'),
 'superintendencia_normativa':('Organismos públicos y reguladores','https://www.superdesalud.gob.cl/normativa/','Normas y actos de la Superintendencia de Salud.'),
 'superintendencia':('Datos oficiales','https://www.superdesalud.gob.cl/biblioteca-digital/','Publicaciones estadísticas del sistema de salud.'),
 'superintendencia_fiscalizacion':('Organismos públicos y reguladores','https://www.superdesalud.gob.cl/','Resoluciones y fiscalización.'),
 'minsal':('Organismos públicos y reguladores','https://www.minsal.cl/','Noticias del Ministerio de Salud.'),
 'suseso':('Organismos públicos y reguladores','https://www.suseso.cl/','Normativa de seguridad social.'),
 'suseso_news':('Organismos públicos y reguladores','https://www.suseso.cl/','Noticias institucionales.'),
 'suseso_fiscalizacion':('Organismos públicos y reguladores','https://www.suseso.cl/','Fiscalización de seguridad social.'),
 'diario_oficial':('Organismos públicos y reguladores','https://www.diariooficial.interior.gob.cl/','Publicaciones oficiales.'),
 'diario_financiero':('Noticias y mercado','https://www.df.cl/empresas/salud','Textos públicos verificables; cobertura parcial.'),
 'pulso_latercera':('Noticias y mercado','https://www.latercera.com/pulso/','Noticias públicas del sector.'),
 'redsalud':('Prestadores e industria','https://www.redsalud.cl/','Noticias institucionales.'),
 'bupa_chile':('Prestadores e industria','https://www.bupa.cl/','Noticias institucionales.'),
 'red_davila':('Prestadores e industria','https://www.davila.cl/','Noticias institucionales.'),
 'andes_salud':('Prestadores e industria','https://www.andessalud.cl/','Noticias institucionales.'),
 'clinicas_chile':('Prestadores e industria','https://www.clinicasdechile.cl/noticias/','Noticias gremiales.'),
 'pfizer_chile':('Prestadores e industria','https://www.pfizer.cl/','Noticias institucionales.'),
 'ist':('Seguridad laboral','https://www.ist.cl/','Noticias institucionales.')}

def eligible(row,now=None):
    if row.get('error') or row.get('error_type'):return False
    try:
        checked=datetime.fromisoformat(str(row.get('checked_at')).replace('Z','+00:00'))
        if checked.tzinfo is None:return False
        if checked>(now or datetime.now(timezone.utc)):return False
    except (ValueError,TypeError):return False
    states=' '.join(str(row.get(k) or '').lower() for k in ('status','technical_status','coverage_status','access_status'))
    if any(x in states for x in ('paused','blocked','held','license','not_permitted','unverified','error')):return False
    return (row.get('technical_status')=='ok' and row.get('coverage_status') in {'observed','verified','complete'}
            or row.get('technical_status')=='partial' and row.get('textual_capture_status')=='verified'
            and (row.get('format_capability') or {}).get('text')=='runtime_verified')

def build_catalog(sources,now=None):
    rows=[]
    for key,row in sources.items():
        if key not in CATALOG or not row.get('name') or not eligible(row,now):continue
        group,url,description=CATALOG[key]
        rows.append({'id':key,'name':row['name'],'group':group,'url':url,'description':description})
    return {'schema_version':1,'sources':sorted(rows,key=lambda x:(x['group'],x['name']))}
