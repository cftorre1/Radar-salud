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
    rows.append(dict(rows[0],title="Resolución backfill",source_url="https://x/backfill",event_date="2026-09-21",ingestion_mode="BACKFILL"))
    rows.append(dict(rows[0],title="Resolución antigua",source_url="https://x/old",event_date="2026-08-01"))
    pulses=m._sanction_pulses(rows,date(2026,9,23))
    assert sorted(x["sanction_count"] for x in pulses if x.get("sanction_count"))==[2,3]
    assert not [x for x in pulses if x["source_url"]=="https://x/old"]
    assert {x["source_url"] for x in pulses if x.get("sanction_count")} <= {r["source_url"] for r in rows}
    assert all(len(x["source_alternatives"])==x["sanction_count"]-1 for x in pulses if x.get("sanction_count"))
    assert all(x["ingestion_mode"]=="LIVE" for x in pulses if x.get("sanction_count"))
    assert "1 incorporadas desde el histórico" in next(x["what_happened"] for x in pulses if x.get("sanction_count")==3)

def test_offline_recuration_keeps_local_context_without_fetching(monkeypatch):
    row=sig("Circular IF/N°535",event="2026-09-23",cat="Regulación & Legal")
    row.update(signal_types=["Normativa"],related_reference_ids=["Circular IF/N°529"])
    monkeypatch.setattr(m,"resolve_reference",lambda *args: (_ for _ in ()).throw(AssertionError("network")))
    assert m.curate([row],resolve_external=False)[0]["related_context"]==[]

def test_df_headline_keeps_teaser_out_of_title():
    row=sig("Bupa acelera inversiones en Santiago con tres proyectos por US$ 15 millones El plan incluye una clínica y un centro de salud mental.")
    row.update(source_name="Diario Financiero",what_happened="Bupa anunció inversiones y nuevos centros médicos.",why_it_matters="Amplía la red asistencial y modifica capacidad competitiva de prestadores.")
    row["title"] += " La publicación describe además la estrategia para ampliar la red en el sector oriente."
    out=m.curate([row],resolve_external=False)
    assert out[0]["title"].endswith("US$ 15 millones")
    assert "El plan incluye" in out[0]["source_title_full"]
