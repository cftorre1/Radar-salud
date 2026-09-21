from .models import Signal
from .personalization import DEFAULT_PROFILES
from .radar_daily import build_whatsapp_daily


def s(title, source, category, domain, score, conf, why):
    return Signal(
        title=title, source_name=source, source_type='demo', source_url='https://example.com/'+str(abs(hash(title))),
        category=category, subcategory='Demo', system_domain=domain, what_happened=title,
        why_it_matters=why, radar_score=score, confidence_score=conf,
        regulatory_impact_score=90 if category=='Regulación & Legal' else 35,
    )


def main():
    signals = [
        s('Superintendencia publica nueva circular sobre Isapres','Superintendencia de Salud','Regulación & Legal','HEALTH_INSURANCE',96,100,'Puede cambiar obligaciones operativas o financieras de las Isapres.'),
        s('Cartera Isapre muestra cambio relevante en cotizantes','Superintendencia de Salud','Aseguramiento','HEALTH_INSURANCE',91,100,'Actualiza la lectura competitiva del aseguramiento privado.'),
        s('SUSESO emite circular sobre gestión de mutualidades','SUSESO','Regulación & Legal','OCCUPATIONAL_HEALTH',86,100,'Puede modificar criterios operativos para mutualidades.'),
        s('Servicio de Salud licita prestación oncológica','Mercado Público','Oportunidades & Licitaciones','HEALTH',82,96,'Es una oportunidad comercial y señal de demanda pública.'),
        s('COMPIN refuerza fiscalización de licencias médicas','Minsal / COMPIN','Regulación & Legal','SOCIAL_SECURITY',84,100,'Puede afectar emisores, aseguradores y empleadores.'),
        s('Clínica anuncia nueva inversión regional','Diario Financiero','Mercado','HEALTH_PROVIDERS',80,93,'Señala expansión de capacidad y competencia regional.'),
        s('Healthcare AI company expands into clinical workflows','Reuters','Radar Mundo','GLOBAL_HEALTH',75,96,'Puede anticipar la entrada de agentes de IA a procesos centrales de salud.'),
        s('Hospital consolidation accelerates abroad','Reuters','Radar Mundo','GLOBAL_HEALTH',73,96,'Puede anticipar tendencias de escala y consolidación relevantes para prestadores.'),
    ]
    print(build_whatsapp_daily(signals, DEFAULT_PROFILES['isapre'], '2026-09-21'))

if __name__ == '__main__':
    main()
