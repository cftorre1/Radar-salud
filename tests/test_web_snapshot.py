import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location("snap",Path("scripts/export_web_snapshot.py"));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def sig(title,event="2026-09-14",score=70,url=None,cat="Aseguramiento"):
    return {"title":title,"source_name":"Superintendencia de Salud","source_url":url or "https://x/"+str(abs(hash(title))),"category":cat,"event_date":event,"radar_score":score,"confidence_score":100,"validation_status":"automatic","what_happened":"x","why_it_matters":"y","key_facts":["Información actualizada a julio 2026."],"system_domain":"HEALTH_INSURANCE"}

def test_group_has_all_sources_and_tags():
    xs=[sig("Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE – año 2026",url="https://x/a"),sig("Estadística Mensual de Movilidad de Cartera de Cotizantes del Sistema ISAPRE a Nivel Regional – Año 2026",url="https://x/b"),sig("Estadística Mensual de Suscripciones y Desahucios del Sistema ISAPRE – año 2026",url="https://x/c")]
    out=m.curate(xs)
    assert out[0]["grouped_count"]==3 and len(out[0]["related_sources"])==3
    assert out[0]["signal_types"]==["Datos"] and out[0]["scopes"]==["Isapres"]

def test_regulation_survives_and_is_recent():
    r=sig("Circular IF/N°535",event="2026-09-14",score=82,cat="Regulación & Legal");r["signal_types"]=["Normativa"];r["scopes"]=["Isapres"]
    out=m.curate([r])
    assert out[0]["signal_types"]==["Normativa"]
