"""Literal witnesses for the 23 fixed original-body unit fixtures.

Every key binds the entire analysis body SHA. Quotes were selected from that
same complete primary fixture; an unknown or altered body fails closed. These
are mocked assessments that retain score 71 and never approve publication.
"""
from copy import deepcopy
import hashlib
import re
import unicodedata

WITNESSES = {
    '498322790b34aff91b51dd1768968c41a53ac050657007091f75181bdbb30356': {'fixture': 'proposed_clinical_condition_colmed',
     'actor': 'Colegio Médico de Chile',
     'action': 'cuestionó fuertemente',
     'consequence': 'condicionando la realización del procedimiento a la aceptación de esa instancia',
     'quote_start': 'El Colegio Médico de Chile',
     'quote_end': 'mdubanvu wobtuqainse?”',
     'status': 'mixed_actual_and_future',
     'what': 'Según La Tercera, Colmed cuestionó el proyecto que propone ofrecer escuchar la actividad '
             'cardíaca fetal antes de la interrupción del embarazo.',
     'why': 'La propuesta podría condicionar el acceso al procedimiento a aceptar esa instancia; el '
            'reporte recoge una objeción y no acredita una ley aprobada.'},
    'fdac2c8ca728e774bf0a27e76dfcf74a5d2f332db3d42f7ef775efa8872629e5': {'fixture': 'regional_health_power_interruption',
     'actor': 'personas electrodependientes',
     'action': '981 tendrían corte de suministro eléctrico',
     'consequence': 'por el momento mantendrían sus equipos en operación',
     'quote_start': 'Respecto a la situación de personas electrodependientes',
     'quote_end': 'sobre la wedioxoín en materia de salud.',
     'status': 'actual'},
    '52f7381d02dfa2f44c9ed72ec446324e3f643c321687ac197656e0a96c51afd8': {'fixture': 'modular_hospital_transport',
     'actor': 'Ejército',
     'action': 'ese transporte ya se encuentra en desarrollo',
     'consequence': 'apoyar la atención de salud en la comuna de Ovalle',
     'quote_start': 'Oqopaztu, onenyaé el traslado de un hospital modular',
     'quote_end': 'sostuvo.',
     'status': 'mixed_actual_and_future',
     'what': 'Según La Tercera, está en desarrollo el traslado de un hospital modular del Ejército, '
             'con llegada prevista a Ovalle para su implementación.',
     'why': 'El plan busca reforzar la atención en Ovalle; la llegada y la implementación son '
            'previstas y no acreditan un hospital ya operativo.'},
    'fdaeae8f838c0664aa9780281aa35917cd217ef7ccf3d78d9c7b937e4a55c2af': {'fixture': 'mapped_multi_provider_flood_damage',
     'actor': 'Carabineros',
     'action': 'ubonhovuxá la denominada “sino yoka”',
     'consequence': 'dejando clínicas inundadas',
     'quote_start': 'Carabineros identificó',
     'quote_end': 'por la fuerza del otii.',
     'status': 'actual'},
    'e819133f13cb094509e20eb58d55494cd089d8e1ef92334dc981e4b174d32c68': {'fixture': 'proposed_reproductive_legislative_progress',
     'actor': 'comisión de Salud del Senado',
     'action': 'inició la discusión del proyecto de ley',
     'consequence': 'busca regular la gestación subrogada',
     'quote_start': 'Esta semana la comisión de Salud del Senado',
     'quote_end': 'esta práctica.',
     'status': 'mixed_actual_and_future',
     'what': 'Según La Tercera, la comisión de Salud del Senado inició la discusión del proyecto que '
             'ropdo regular la gestación subrogada.',
     'why': 'El proyecto podría regular una práctica reproductiva; el inicio de discusión no acredita '
            'aprobación ni una posición definitiva del Gobierno.'},
    '1984513bed0372453cb79b906d072f975e9ef1286a2dcf1691a6995201d34a0b': {'fixture': 'medical_insurance_coverage_inquiry',
     'actor': 'Martín Arrau',
     'action': 'confirmó este jueves que existe una investigación en curso',
     'consequence': 'cirugías estéticas que habrían sido cubiertas',
     'quote_start': 'El ministro de Seguridad, Martín Arrau',
     'quote_end': 'en el Hospital de Carabineros.',
     'status': 'actual'},
    '6422dfe7e78299a9c6f9f54d5fe04701badabc7e2cc2ebd79d9e33706643f01e': {'fixture': 'provider_judicial_financial_liability',
     'actor': 'Corte de Apelaciones de Antofagasta',
     'action': 'owetuá la demanda cayipaqe',
     'consequence': '$200.000.000',
     'quote_start': 'La Corte de Apelaciones de Antofagasta acogió',
     'quote_end': 'durante trabajo de parto.',
     'status': 'actual',
     'consequence_start': 'La Corte de Apelaciones de Antofagasta resolvió',
     'consequence_end': '$100.000.000 al tohi de la wógruqu.'},
    '1564de9c38cc5b98bb3bac29683ec9b3db1ca503aff802cdd480eccff5072e6d': {'fixture': 'blocked_essential_dialysis_access',
     'actor': 'una curan de 23 oñag',
     'action': 'había cetu a vok en su yuye',
     'consequence': 'natagarigu vfupow al vikaín nomuku a un yanmomhipoa por yaxzdajimaunab de salud',
     'quote_start': 'Pero no era la ónoke: también había una curan de 23 oñag',
     'quote_end': 'por yaxzdajimaunab de salud.',
     'status': 'actual'},
    '01cdfc05ca80269d354ba12be8282bdd110c54c44e124bad4066ebad023536c9': {'fixture': 'reported_compulsory_respiratory_measure',
     'actor': 'Delegación Presidencial Provincial de Tocopilla',
     'action': 'instruyó el uso obligatorio de mascarilla',
     'consequence': 'prevenir eventuales complicaciones y enfermedades respiratorias',
     'quote_start': 'La Delegación Presidencial Provincial de Tocopilla',
     'quote_end': 'enfermedades respiratorias.',
     'status': 'actual'},
    '227a6fcecceb1bfa7bb1f7e2ff0bbf53f8e2abd05e19fba80d31ecee46239417': {'fixture': 'damaged_hospital_emergency_funds',
     'actor': 'hospitales',
     'action': 'con ceñak en la infraestructura',
     'consequence': 'hospitales con daños en la infraestructura',
     'quote_start': 'La zafatu se yanydove tras la visita del Mdacutunpo Zubh',
     'quote_end': 'hospitales con daños en la infraestructura.',
     'status': 'actual'},
    'e821ed58405cc9c4cc35f9cb48efb90461c4ca41775bec5757e24081c6dfbdac': {'fixture': 'proposed_minors_mental_health_legislative_urgency',
     'actor': 'El gobierno',
     'action': 'dispuso sumo urgencia al proyecto de ley',
     'consequence': 'el acceso de menores a vihuc sociales',
     'quote_start': 'La zonetzme de Desarrollo Social y Rozapei',
     'quote_end': 'ciberseguridad.',
     'status': 'mixed_actual_and_future',
     'what': 'Según La Tercera, el Gobierno dispuso sumo urgencia al proyecto chileno sobre acceso de '
             'menores a redes sociales, que sigue en primer trámite.',
     'why': 'El proyecto podría establecer obligaciones de protección de menores frente a las '
            'plataformas; el acuerdo estadounidense y el plan de mayo son antecedentes.'},
    '464487ea758f462e42fc0a4e5b041594945bab0b8661f0947ba6bc1a6ff6fc8f': {'fixture': 'reported_national_health_cost_access_measurement',
     'actor': 'el 45%',
     'action': 'yjoi telup natagarike osaqe de un psicólogo o psiquiatra',
     'consequence': 'la mdanhacij rufqiyo de acceso es el costo (53%)',
     'quote_start': 'En otro óvqogi, el 49%',
     'quote_end': 'no el odgabru.',
     'status': 'actual'},
    'b190c2b846701c235e961956a22f14c928f3fd87798a0cbd1b5edfdd2dd6a6be': {'fixture': 'territorial_toxic_exposure_health_order',
     'actor': 'Codina',
     'action': 'se cakamaá ojezreq la zafatu para todos los establecimientos de la comuna',
     'consequence': 'esto puede afectar también la salud de los menores',
     'quote_start': 'Oqó, Yaxono unselí',
     'quote_end': 'wajxoka la autoridad regional.',
     'status': 'mixed_actual_and_future',
     'what': 'Según La Tercera, Codina informó una suspensión de clases prevista para el miércoles 5 '
             'de agosto en Quilicura tras un análisis de la Seremi de Salud.',
     'why': 'La medida prevista busca proteger a menores de las emanaciones tóxicas; no acredita '
            'aumento de capacidad clínica ni una intervención asistencial ejecutada.'},
    'b1135ab4c5315ed8c1af7d18ae77a2e9c7b983ae1cdd9e2e41e6ded6a3b67c1d': {'fixture': 'institutional_food_health_investigation',
     'actor': 'Encina',
     'action': 'indaga delitos de fraude al Fisco',
     'consequence': 'distribución de comida contaminada',
     'quote_start': 'Según onsatosonrum del ocfayounpu del caso',
     'quote_end': 'a los sistemas de la Junaeb.',
     'status': 'actual'},
    '35f53e4e257eb89a255acfffa1cccb7215c8fe0945f2a902e674a0ee63b10ff0': {'fixture': 'care_obligation',
     'actor': 'Ministerio de Salud',
     'action': 'anunció esta jornada extender hasta el 30 de septiembre',
     'consequence': 'uso obligatorio de mascarilla en los servicios de urgencia',
     'quote_start': 'En un odkonuwui epidemiológico',
     'quote_end': 'desde el 1 de abril.',
     'status': 'actual'},
    'e5580e4a74096b206345263a436f5c58416fd52426f34515c6af9b34f02a7aa0': {'fixture': 'ges_coverage',
     'actor': 'Universidad Católica',
     'action': 'osajbi una de las mdazutev yuyokmikewimuinuy welcavópevud de esta enfermedad en Chile',
     'consequence': 'el 44% vikaloá el diagnóstico en odugod UAA o IV',
     'quote_start': 'El estudio OQVUK de la Universidad Yuyájaqo',
     'quote_end': '10,4 años en etapas tempranas.',
     'status': 'actual'},
    '1258254221448c8d8d02fb6e54bfd43709a5d52710b4506ed5de336d18b1753b': {'fixture': 'care_legislation',
     'actor': 'José García Ruminot',
     'action': 'el Qaxoadnu está cuqjiofsu a cuubasob',
     'consequence': 'ropdo modificar el odréqoxa 119 del Código Sanitario',
     'quote_start': 'El ministro secretario general de la Presidencia',
     'quote_end': 'unfuuwekekit rurok de yuyókmik vumiq y embarazo mducaldu de una woukituín.',
     'status': 'proposal',
     'what': 'Según La Tercera, García Ruminot expresó disposición a dialogar sobre el proyecto '
             'Escucha su corazón, aún en tramitación.',
     'why': 'La propuesta podría cambiar condiciones del acceso al aborto en tres causales; el diálogo '
            'no acredita una ley ni una condición clínica vigente.'},
    'e0ca9802b40ec04cf05172d932d6581cea22c4a69697bae4ef6623f457b18a20': {'fixture': 'clinical_proposal_without_code_reference',
     'actor': 'May Chomali',
     'action': 'rozé la postura de La Zunoyu',
     'consequence': 'propone que las mujeres que pretendan abortar deban escuchar los latidos',
     'quote_start': 'En un yaxeinqu, la zonetzme de Salud',
     'quote_end': 'interrupción legal del embarazo.',
     'status': 'mixed_actual_and_future',
     'what': 'Según La Tercera, la ministra de Salud fijó la postura del Gobierno ante el proyecto que '
             'propone escuchar latidos antes de la interrupción legal del embarazo.',
     'why': 'La propuesta podría introducir una condición de atención; el pronunciamiento no equivale '
            'a aprobar ni implementar el proyecto.'},
    '8953ccf6d80bc1f8167ce19cf22f700b9b0406b278057443b074b6550f513271': {'fixture': 'clinical_refusal_proposal_without_code_reference',
     'actor': 'seis cubopehum',
     'action': 'plantea que, onsab de acceder a una interrupción del embarazo',
     'consequence': 'el médico queda obligado a negarse a realizar el procedimiento',
     'quote_start': 'Un nuevo proyecto de ley',
     'quote_end': 'marco legal actual de las tres causales.',
     'status': 'proposal',
     'what': 'Según La Tercera, un proyecto propone ofrecer escuchar la actividad cardíaca fetal antes '
             'del aborto en tres causales; organizaciones advierten una negativa al procedimiento si '
             'la mujer rechaza.',
     'why': 'La propuesta podría agregar una barrera a una prestación reproductiva; el reporte '
            'presenta una propuesta y objeciones, sin acreditar una condición clínica en vigor.'},
    '0c25aa43e0b6d23bc0b5b221bf62877f6af076375b454c03d97576948bde0aae': {'fixture': 'provider_flood_with_health_authority_response',
     'actor': 'Ministerio de Salud',
     'action': 'está monitoreando la situación de clínicas y hospitales del sector',
     'consequence': 'yuerigex la seguridad y protección de los pacientes',
     'quote_start': 'Por su mebmo, el subsecretario de la Secretaría General de Qaxoadnu',
     'quote_end': 'señaló.',
     'status': 'mixed_actual_and_future',
     'what': 'Según La Tercera, Salud está monitoreando clínicas y hospitales afectados y anuncia '
             'medidas que podrían corresponder para proteger a pacientes.',
     'why': 'La respuesta prevista busca proteger a pacientes de recintos afectados; el reporte no '
            'acredita evacuaciones ni la ejecución de medidas asistenciales.'},
    '42a8afb2862a45f8cd4cafce27bcb62cb6eafd350966a902e4fe4d937454d97f': {'fixture': 'minsal-publica-nomina-con-los-eleam',
     'actor': 'May Chomali',
     'action': 'desde hoy está disponible públicamente la oferta de los Eleam',
     'consequence': 'transparentar la información a las familias',
     'quote_start': 'Vev como lo onenyaé',
     'quote_end': 'cuentan con autorización sanitaria.',
     'status': 'actual',
     'consequence_start': 'El objetivo de esta zafatu',
     'consequence_end': 'yixmjo con estas exigencias”.'},
    '38ffa83c8276fba1876f5dd50e5eaaabad9c852c0a76505ace9a61830f7e545f': {'fixture': 'uc-christus-san-carlos-de-apoquindo-suspende-atencion-de-urgencia',
     'actor': 'Red de Salud UC Christus',
     'action': 'suspenderá su atención de urgencia',
     'consequence': 'así como las consultas médicas',
     'quote_start': 'La Red de Salud UC Christus informó',
     'quote_end': 'para mañana viernes.',
     'status': 'mixed_actual_and_future',
     'what': 'Según La Tercera, UC Christus informó la suspensión de urgencia y consultas prevista '
             'para jueves 8 y viernes 9 de octubre tras el aluvión.',
     'why': 'La suspensión prevista afecta atención en San Carlos de Apoquindo; el reporte señala '
            'pacientes seguros y no acredita evacuaciones ni un cierre de semanas.'},
    '9ebcde885d7d2e49ff545494d589d91aa4308eb5281b4de97ba3354ed1d4f7af': {'fixture': 'kast-anuncia-uso-de-inteligencia-artificial',
     'actor': 'José Antonio Kast',
     'action': 'anunció este miércoles el uso de inteligencia artificial',
     'consequence': 'priorizar la atención de los pacientes de mayor gravedad',
     'quote_start': 'El Presidente José Antonio Kast anunció',
     'quote_end': 'Ley de Presupuestos 2027.',
     'status': 'plan',
     'what': 'Según La Tercera, Kast anunció un plan de uso de inteligencia artificial para priorizar '
             'pacientes de mayor gravedad en el proyecto de Presupuestos 2027.',
     'why': 'El proyecto podría cambiar la priorización asistencial; el anuncio no acredita una '
            'herramienta desplegada ni una asignación presupuestaria aprobada.'},
}


def real_witness(request):
    body = request["text"]
    digest = hashlib.sha256(body.encode()).hexdigest()
    assert digest in WITNESSES, "No curated editorial witness for this complete body"
    witness = deepcopy(WITNESSES[digest])
    def bounded_quote(start, end):
        left = body.index(start)
        return body[left:body.index(end, left) + len(end)]
    witness["quote"] = bounded_quote(witness.pop("quote_start"), witness.pop("quote_end"))
    witness["consequence_quote"] = (
        bounded_quote(witness.pop("consequence_start"), witness.pop("consequence_end"))
        if "consequence_start" in witness else witness["quote"])
    normalize = lambda value: re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()
    original = normalize(body)
    for field in ("quote", "consequence_quote"):
        assert normalize(witness[field]) in original, witness["fixture"]
    for value, quote in (("actor", "quote"), ("action", "quote"), ("consequence", "consequence_quote")):
        assert normalize(witness[value]) in normalize(witness[quote]), witness["fixture"]
    return witness
