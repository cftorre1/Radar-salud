"""Sanitized catalogue, derived from current evidence; diagnostics stay administrative."""
from datetime import datetime, timezone
import json
from pathlib import Path

CATALOG={
 'deis':('Datos oficiales','https://deis.minsal.cl/','Estadísticas oficiales de salud.'),
 'prestadores_data':('Datos oficiales','https://www.superdesalud.gob.cl/','Datos públicos de prestadores; superficie verificada.'),
 'achs_seguro_laboral':('Seguridad laboral','https://www.achs.cl/centro-de-noticias/','Noticias verificadas de seguridad laboral.'),
 'global_who':('Global · evidencia internacional','https://www.who.int/publications/','Publicaciones OMS; superficie de metadatos verificada.'),
 'global_paho':('Global · evidencia internacional','https://www.paho.org/es/publicaciones','Publicaciones OPS; superficie de metadatos verificada.'),
 'superintendencia_normativa':('Organismos públicos y reguladores','https://www.superdesalud.gob.cl/normativa/','Normas y actos de la Superintendencia de Salud.'),
 'superintendencia':('Datos oficiales','https://www.superdesalud.gob.cl/biblioteca-digital/','Publicaciones estadísticas del sistema de salud.'),
 'superintendencia_fiscalizacion':('Organismos públicos y reguladores','https://www.superdesalud.gob.cl/','Resoluciones y fiscalización.'),
 'superintendencia_noticias':('Organismos públicos y reguladores','https://www.superdesalud.gob.cl/noticias/','Noticias y comunicados oficiales de la Superintendencia de Salud.'),
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

# Short public labels for narrow screens; the official name stays in the row for screen readers
# and search (review N3, 27-oct-2026). Sources without an entry show their official name.
SHORT_NAMES={'deis':'DEIS · Minsal','suseso':'SUSESO','suseso_news':'SUSESO','suseso_fiscalizacion':'SUSESO',
 'prestadores_data':'Intendencia de Prestadores','superintendencia':'Superintendencia de Salud',
 'superintendencia_normativa':'Superintendencia de Salud','superintendencia_fiscalizacion':'Superintendencia de Salud','superintendencia_noticias':'Superintendencia de Salud',
 'global_who':'OMS','global_paho':'OPS','minsal':'Minsal'}

TRIAL_MODES={'isolated_qualification','manual_curated_only'}

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
        if row.get('operation_mode') in TRIAL_MODES:
            # Honest label: verified once, not polled by the daily capture.
            description=description.replace('superficie de metadatos verificada','metadatos verificados en prueba')+' En prueba: sin consulta diaria.'
        item={'id':key,'name':row['name'],'group':group,'url':url,'description':description}
        if SHORT_NAMES.get(key) and SHORT_NAMES[key]!=row['name']:item['short_name']=SHORT_NAMES[key]
        rows.append(item)
    return {'schema_version':1,'sources':sorted(rows,key=lambda x:(x['group'],x['name']))}

def export_public_sources(source_path=Path('data/source_health.json'),output=Path('web/data/public_sources.json')):
    data=json.loads(source_path.read_text(encoding='utf-8'))
    payload=build_catalog(data.get('sources') or {})
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return payload
