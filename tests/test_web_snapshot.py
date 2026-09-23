import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location("snap",Path("scripts/export_web_snapshot.py"));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def sig(title,event="2026-09-14",score=70,url=None,cat="Aseguramiento"):
    return {"title":title,"source_name":"Superintendencia de Salud","source_url":url or "https://x/"+str(abs(hash(title))),"category":cat,"event_date":event,"radar_score":score,"confidence_score":100,"validation_status":"automatic","what_happened":"x","why_it_matters":"y","key_facts":["Información actualizada a julio 2026."],"system_domain":"HEALTH_INSURANCE"}

def test_distinct_statistical_families_keep_their_sources():
    xs=[sig("Estadística Mensual de Cartera de Beneficiarios del Sistema ISAPRE – año 2026",url="https://x/a"),sig("Estadística Mensual de Movilidad de Cartera de Cotizantes del Sistema ISAPRE a Nivel Regional – Año 2026",url="https://x/b"),sig("Estadística Mensual de Suscripciones y Desahucios del Sistema ISAPRE – año 2026",url="https://x/c")]
    for row in xs:
        row.update(signal_types=["Datos"],scopes=["Isapres"])
    out=m.curate(xs)
    assert len(out)==3
    assert {x["source_url"] for x in out}=={"https://x/a","https://x/b","https://x/c"}
    assert all(x["signal_types"]==["Datos"] and x["scopes"]==["Isapres"] for x in out)

def test_regulation_survives_and_is_recent():
    r=sig("Circular IF/N°535",event="2026-09-14",score=82,cat="Regulación & Legal");r["signal_types"]=["Normativa"];r["scopes"]=["Isapres"]
    out=m.curate([r])
    assert out[0]["signal_types"]==["Normativa"]

def test_sanctions_become_two_rolling_pulses_without_losing_individual_sources():
    from datetime import date
    rows=[]
    for sector in ("Isapres", "Prestadores"):
        for n in (1,2):
            row=sig(f"Resolución sancionatoria {sector} {n}",event="2026-09-22",url=f"https://x/{sector}/{n}")
            row.update(event_type="SANCTION",signal_types=["Fiscalización"],scopes=[sector],ingestion_mode="LIVE")
            rows.append(row)
    rows.append(dict(rows[0],title="Resolución antigua",source_url="https://x/old",event_date="2026-08-01"))
    pulses=m._sanction_pulses(rows,date(2026,9,23))
    assert len([x for x in pulses if x.get("sanction_count")==2])==2
    assert len([x for x in pulses if x["source_url"]=="https://x/old"])==1
    assert {x["source_url"] for x in pulses if x.get("sanction_count")==2} <= {r["source_url"] for r in rows}
    assert all(len(x["source_alternatives"])==1 for x in pulses if x.get("sanction_count")==2)
