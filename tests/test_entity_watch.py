"""WATCH: deterministic entity tagging (Dirección 27-oct-2026)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from radar_salud import entity_watch as ew

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'config/entities.json').read_text(encoding='utf-8'))


def ids(text):
    return set(ew.match_text(text))


REQUIRED = {
    'cl:org:clinica-alemana', 'cl:org:clinica-las-condes', 'cl:org:empresas-banmedica', 'cl:org:clinica-santa-maria',
    'cl:org:uc-christus', 'cl:org:clinica-uandes', 'cl:org:clinica-udd', 'cl:org:meds', 'cl:org:hcuch', 'cl:org:bupa',
    'cl:org:interclinica', 'cl:org:indisa', 'cl:org:red-davila', 'cl:org:achs-salud',
    'cl:isapre:99', 'cl:isapre:67', 'cl:isapre:107', 'cl:isapre:78', 'cl:isapre:81', 'cl:isapre:80', 'cl:isapre:108', 'cl:isapre:76',
    'cl:org:fonasa', 'cl:org:compin', 'cl:org:achs', 'cl:org:mutual-de-seguridad', 'cl:org:ist', 'cl:org:isl',
    'cl:org:redsalud-ilc', 'cl:org:clinicas-de-chile', 'cl:org:isp', 'cl:org:cenabast'}


def test_catalog_covers_directors_list_with_valid_kinds_and_unique_ids():
    entities = CONFIG['entities']
    assert REQUIRED <= {e['id'] for e in entities}
    assert len({e['id'] for e in entities}) == len(entities)
    for e in entities:
        assert e['kind'] in CONFIG['kinds'] and e['display_name'] and e['aliases'] and e['patterns']
        assert set(e.get('kinds', [e['kind']])) <= set(CONFIG['kinds'])


def test_isapre_ids_reuse_official_register_codes():
    official = {e['canonical_id'] for e in json.loads((ROOT / 'data/entities/isapres.json').read_text())['entities']}
    assert {e['id'] for e in CONFIG['entities'] if e['kind'] == 'isapre'} == official


def test_cmf_identities_come_only_from_repository_register():
    register = {a['rut']: a for a in json.loads((ROOT / 'data/entities/cmf_reporting_actors.json').read_text())['actors']}
    by_id = {e['id']: e for e in CONFIG['entities']}
    for e in CONFIG['entities']:
        for c in e['cmf']:
            assert c['rut'] in register and c['source_url'] == register[c['rut']]['source_url']
            assert c['registration_status'] == register[c['rut']]['issuer_registration_status']
    assert [c['rut'] for c in by_id['cl:org:clinica-las-condes']['cmf']] == ['93930000-7']
    assert [c['rut'] for c in by_id['cl:org:indisa']['cmf']] == ['92051000-0']
    assert not by_id['cl:org:clinica-alemana']['cmf'] and not by_id['cl:org:meds']['cmf']


@pytest.mark.parametrize('text,expected', [
    ('Clínica Las Condes finaliza aumento de capital y recauda $80 mil millones', 'cl:org:clinica-las-condes'),
    ('La CLC informó resultados', 'cl:org:clinica-las-condes'),
    ('La isapre del Grupo Alemana se lanza a masificar su modelo', 'cl:org:clinica-alemana'),
    ('Clínica Alemana abre un centro en Chicureo', 'cl:org:clinica-alemana'),
    ('Empresas Banmédica designa nuevo gerente general de Clínica Santa María', 'cl:org:empresas-banmedica'),
    ('Empresas Banmédica designa nuevo gerente general de Clínica Santa María', 'cl:org:clinica-santa-maria'),
    ('Banmédica y Vida Tres demandan al Fisco por desfase en el cobro del GES', 'cl:isapre:99'),
    ('Imponer a la Isapre BANMEDICA S.A. una multa de 500 UF', 'cl:isapre:99'),
    ('Clínica UC Christus de San Carlos de Apoquindo termina traslado de pacientes', 'cl:org:uc-christus'),
    ('Imponer al prestador "CLINICA SAN CARLOS DE APOQUINDO - RED SALUD UC CHRISTUS"', 'cl:org:uc-christus'),
    ('La Clínica Universidad de los Andes suspendió cirugías', 'cl:org:clinica-uandes'),
    ('Clínica MEDS y Universidad Diego Portales sellan alianza', 'cl:org:meds'),
    ('Multa a Hospital Clínico de la Universidad de Chile Dr. José Joaquín Aguirre', 'cl:org:hcuch'),
    ('Bupa acelera inversiones en sector oriente', 'cl:org:bupa'),
    ('Red Interclínica se expande', 'cl:org:interclinica'),
    ('Clínica Indisa alista su debut en el mercado de bonos', 'cl:org:indisa'),
    ('La Superintendencia mantuvo a Clínica Dávila, de Recoleta, en el registro', 'cl:org:red-davila'),
    ('Multa a Clínica Atacama ACHS Salud', 'cl:org:achs-salud'),
    ('rechazó los recursos de Nueva Masvida, Cruz Blanca, Colmena Golden Cross, Esencial y Consalud', 'cl:isapre:108'),
    ('rechazó los recursos de Nueva Masvida, Cruz Blanca, Colmena Golden Cross, Esencial y Consalud', 'cl:isapre:67'),
    ('Ganancias de ILC suben 45%; RedSalud registró mayor utilidad', 'cl:org:redsalud-ilc'),
    ('Clínica Redsalud Santiago S.A. sancionada', 'cl:org:redsalud-ilc'),
    ('La SUSESO coordinará la asistencia técnica de IST, ACHS, Mutual de Seguridad e ISL', 'cl:org:ist'),
    ('La SUSESO coordinará la asistencia técnica de IST, ACHS, Mutual de Seguridad e ISL', 'cl:org:isl'),
    ('La SUSESO coordinará la asistencia técnica de IST, ACHS, Mutual de Seguridad e ISL', 'cl:org:achs'),
    ('La SUSESO coordinará la asistencia técnica de IST, ACHS, Mutual de Seguridad e ISL', 'cl:org:mutual-de-seguridad'),
    ('ISP aprueba primer genérico de Ozempic en Chile', 'cl:org:isp'),
    ('Farmacias Ahumada adhiere a Ley Cenabast', 'cl:org:cenabast'),
    ('Compin e Isapres deberán rechazar las licencias', 'cl:org:compin'),
    ('Kast anuncia convenio entre Minsal, Fonasa y Caja Los Andes', 'cl:org:fonasa'),
    ('Clínicas de Chile y CENS realizan jornada', 'cl:org:clinicas-de-chile'),
])
def test_true_positives(text, expected):
    assert expected in ids(text)


@pytest.mark.parametrize('text,absent', [
    ('Aluvión en Las Condes obliga a cerrar por semanas la Clínica San Carlos', 'cl:org:clinica-las-condes'),
    ('Gobierno decreta zona de catástrofe en Las Condes tras aluvión', 'cl:org:clinica-las-condes'),
    ('Multa a Clínica Alemana de Temuco por cheque en garantía', 'cl:org:clinica-alemana'),
    ('Sanatorio Alemán aportó $1.412 millones', 'cl:org:clinica-alemana'),
    ('Acreditado el Centro de Salud Familiar Santa María de Talcahuano', 'cl:org:clinica-santa-maria'),
    ('Un estudio del CIPS-UDD sobre financiamiento GES', 'cl:org:clinica-udd'),
    ('La Universidad de los Andes abre postulaciones', 'cl:org:clinica-uandes'),
    ('meds and supplies shortage in hospitals', 'cl:org:meds'),
    ('Ministra visitó a la familia Dávila', 'cl:org:red-davila'),
    ('El estudio del Centro UC de Envejecimiento e ILC identificó 82 iniciativas', 'cl:org:redsalud-ilc'),
    ('Multa a Hospital Clínico UC Red Salud UC Christus', 'cl:org:redsalud-ilc'),
    ('La red salud mental comunitaria se amplía', 'cl:org:redsalud-ilc'),
    ('La ley califica a la salud como servicio esencial; canasta esencial de medicamentos', 'cl:isapre:108'),
    ('Fundación Nuestros Hijos construirá centro oncológico', 'cl:isapre:76'),
    ('Empresas Banmédica ejecuta cambio en su estructura organizacional', 'cl:isapre:99'),
    ('Clínica Atacama ACHS Salud sancionada', 'cl:org:achs'),
    ('La colmena de abejas del parque', 'cl:isapre:67'),
    ('Bupa lanza 1000 Genomas', 'cl:isapre:78'),
    ('la unidad está disponible para pacientes Fonasa e Isapre', 'cl:org:fonasa'),
    ('el 57% del gasto era financiado por Fonasa o isapres', 'cl:org:fonasa'),
    ('las clínicas de Chile enfrentan alzas de costos', 'cl:org:clinicas-de-chile'),
])
def test_false_positives_are_not_tagged(text, absent):
    assert absent not in ids(text)


def test_diario_oficial_capture_tags_only_its_own_act():
    neighbour = {'title': 'Resolución exenta número CP 20.192, de 2026.- Declara zona de riesgo sanitario la comuna de Renaico Ver PDF (CVE-2862808) Superintendencia de Seguridad Social Resolución exenta número 1.- Aprueba guía', 'source_name': 'Diario Oficial'}
    assert ew.direct_ids(neighbour) == ([], [])
    own = {'title': 'Decreto número 22, de 2026.- Acepta renuncia Ver PDF (CVE-2855168) Instituto de Salud Pública Resolución exenta número 4.010, de 2026.- Instruye actualizar folletos <a target="_blank"', 'source_name': 'Diario Oficial'}
    assert ew.direct_ids(own)[0] == ['cl:org:isp']
    inherited = {'title': 'Instituto de Salud Pública Extracto de resolución exenta número 4.011 Ver PDF (CVE-2863854) Extracto de resolución exenta número 4.142, de 2026.- Aprueba Guía', 'source_name': 'Diario Oficial'}
    assert ew.direct_ids(inherited)[0] == ['cl:org:isp']


def test_newsroom_source_assigns_owner_and_aggregates_inherit_member_acts():
    own = ew.entity_refs({'title': 'Chile tendrá su primera base genómica', 'source_name': 'Bupa Chile'})
    assert [(r['canonical_id'], r['basis']) for r in own] == [('cl:org:bupa', 'source')]
    history = [{'source_url': 'https://sis/ip-1', 'title': 'Resolución Exenta IP/N°1', 'what_happened': 'Acredita a Clínica Santa María', 'source_name': 'Superintendencia de Salud'}]
    pulse = {'title': 'Acreditación de prestadores · últimos 30 días: 1 acto', 'source_name': 'Superintendencia de Salud',
             'source_alternatives': [{'title': 'Resolución Exenta IP/N°1', 'url': 'https://sis/ip-1'},
                                     {'title': 'IP/N°2', 'material': 'Clínica Indisa · 50 UF', 'url': 'https://sis/ip-2'}],
             'entity_refs': [{'name': 'Nueva Masvida', 'canonical_id': 'cl:isapre:81'}, {'name': 'Otro', 'canonical_id': 'x:other'}]}
    ew.apply([pulse], history=history)
    refs = {r['canonical_id']: r['basis'] for r in pulse['entity_refs']}
    assert refs == {'cl:org:indisa': 'member', 'cl:org:clinica-santa-maria': 'member', 'cl:isapre:81': 'pipeline', 'x:other': 'pipeline'}


def test_exporter_writes_entity_refs_on_every_card_and_a_public_catalog(tmp_path):
    out = tmp_path / 'radar_today.json'
    subprocess.run([sys.executable, 'scripts/export_web_snapshot.py', '--input', 'data/history/superintendencia_signals.json',
                    '--offline', '--as-of', '2026-10-12', '--output', str(out)], cwd=ROOT, check=True, capture_output=True,
                   env={**__import__('os').environ, 'PYTHONPATH': str(ROOT / 'src') + ':' + __import__('os').environ.get('PYTHONPATH', '')})
    payload = json.loads(out.read_text(encoding='utf-8'))
    catalog = {e['id'] for e in payload['entities']}
    assert REQUIRED <= catalog
    assert all(isinstance(s.get('entity_refs'), list) for s in payload['signals'])
    tagged = [s for s in payload['signals'] if s['entity_refs']]
    assert len(tagged) >= 20
    for s in payload['signals']:
        for r in s['entity_refs']:
            assert r['basis'] in {'text', 'source', 'member', 'pipeline'}
            assert r['canonical_id'] in catalog or r['basis'] == 'pipeline'
    aluvion = [s for s in payload['signals'] if 'Aluvión en Las Condes' in s.get('title', '')]
    assert aluvion and all('cl:org:clinica-las-condes' not in {r['canonical_id'] for r in s['entity_refs'] if r['basis'] == 'text'} for s in aluvion)


def test_published_snapshot_carries_entity_refs():
    payload = json.loads((ROOT / 'web/data/radar_today.json').read_text(encoding='utf-8'))
    assert payload['entities'] and all(isinstance(s.get('entity_refs'), list) for s in payload['signals'])
    assert any(s['entity_refs'] for s in payload['signals'])
