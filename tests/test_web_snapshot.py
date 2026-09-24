import importlib.util
import json
from pathlib import Path
spec=importlib.util.spec_from_file_location("snap",Path("scripts/export_web_snapshot.py"));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def sig(title,event="2026-09-14",score=70,url=None,cat="Aseguramiento"):
    return {"title":title,"source_name":"Superintendencia de Salud","source_url":url or "https://x/"+str(abs(hash(title))),"category":cat,"event_date":event,"radar_score":score,"confidence_score":100,"validation_status":"automatic","what_happened":"x","why_it_matters":"y","key_facts":["Información actualizada a julio 2026."],"system_domain":"HEALTH_INSURANCE"}

def test_bupa_card_preserves_all_three_projects_without_ellipsis():
    rows=json.loads(Path("web/data/radar_today.json").read_text())["signals"]
    bupa=next(s for s in rows if s["title"].startswith("Bupa acelera inversiones"))
    card=m._card_micro(bupa)
    assert all(x in card["card_what"] for x in ("La Dehesa","Huinganal","Mindplace","San Damián"))
    assert "…" not in card["card_what"]


def test_tea_resolution_card_keeps_outcome_requirement_and_deadline_compact():
    row=sig("Resolución Exenta IF/N°11156",event="2026-09-23",cat="Regulación & Legal")
    row.update(
        source_name="Superintendencia de Salud",
        source_url="https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n11156/",
        what_happened="La Superintendencia modificó la Circular IF/Nº528, confirmó la eliminación de esos topes e incorporó requisitos diagnósticos y un mecanismo de registro para acceder a la cobertura.",
        why_it_matters="Las isapres deben mantener la bonificación sin tope anual y adecuar la compra directa de bonos.",
        key_points=["Las isapres deben implementar el mecanismo de registro a más tardar el 1 de noviembre de 2026."])
    card=m._card_micro(row)
    assert "cinco prestaciones" in card["card_what"] and "requisitos" in card["card_what"]
    assert "1 de noviembre de 2026" in card["card_why"] and "compra directa" in card["card_why"]
    assert len(card["card_what"])+len(card["card_why"])<300


def test_backfilled_bupa_emergency_has_truthful_card_and_scope():
    rows=json.loads(Path("web/data/radar_today.json").read_text())["signals"]
    bupa=next(s for s in rows if s.get("source_name")=="Bupa Chile")
    assert bupa["ingestion_mode"]=="BACKFILL"
    assert "Farma / medicamentos" not in bupa["scopes"]
    assert "vigente ahora" not in bupa["why_it_matters"].lower()
    assert all(bupa.get(k) for k in ("card_what","card_why","source_title_full"))
    history=json.loads(Path("data/history/superintendencia_signals.json").read_text())["signals"]
    original=next(s for s in history if s.get("source_url")==bupa["source_url"])
    replay=m._card_micro(original)
    assert all(replay.get(k)==bupa.get(k) for k in ("title","card_what","card_why","scopes","source_title_full"))

def test_backfilled_redsalud_convenio_preserves_material_and_facets():
    rows=json.loads(Path("web/data/radar_today.json").read_text())["signals"]
    row=next(s for s in rows if s.get("source_name")=="RedSalud")
    assert row["ingestion_mode"]=="BACKFILL"
    assert row["scopes"]==["Prestadores","Isapres"]
    assert all(term in row["card_what"] for term in ("Libre Elección","Preferente","9 clínicas","Sanatorio Alemán","I-Med"))
    assert "reembolso" in row["card_why"]
    history=json.loads(Path("data/history/superintendencia_signals.json").read_text())["signals"]
    original=next(s for s in history if s.get("source_url")==row["source_url"])
    replay=m._card_micro(original)
    assert all(replay.get(k)==row.get(k) for k in ("title","card_what","card_why","scopes","source_title_full"))


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

def test_individual_routine_accreditation_stays_in_history_but_not_feed():
    routine=sig("Resolución Exenta IP/N°5024",event="2026-07-23",score=82,cat="Regulación & Legal")
    routine.update(distribution="archive",signal_types=["Normativa"],scopes=["Prestadores"],
        what_happened="La Superintendencia de Salud inscribió al Centro de Salud Familiar X en el Registro Público de Prestadores Institucionales de Salud Acreditados.")
    strategic=dict(routine,title="Cambio del estándar de acreditación",source_url="https://x/strategic",
        what_happened="La Superintendencia modificó el estándar de acreditación y sus requisitos para los prestadores.")
    assert m._routine_accreditation(routine) and not m._routine_accreditation(strategic)
    assert [x["title"] for x in m.curate([routine,strategic],resolve_external=False)]==["Cambio del estándar de acreditación"]
    registry=dict(routine,title="Resolución Exenta IP/N°4417",source_url="https://x/registry",
        what_happened="La resolución ordena inscribir en el Registro de Entidades Certificadoras 79 programas acreditados de formación de especialistas.")
    assert m._routine_accreditation(registry)

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
    assert all(len(x["source_alternatives"])==x["sanction_count"] for x in pulses if x.get("sanction_count"))
    assert all(x["ingestion_mode"]=="LIVE" for x in pulses if x.get("sanction_count"))
    assert "1 incorporadas desde el histórico" in next(x["what_happened"] for x in pulses if x.get("sanction_count")==3)

def test_offline_recuration_keeps_local_context_without_fetching(monkeypatch):
    row=sig("Circular IF/N°535",event="2026-09-23",cat="Regulación & Legal")
    row.update(signal_types=["Normativa"],related_reference_ids=["Circular IF/N°529"])
    monkeypatch.setattr(m,"resolve_reference",lambda *args: (_ for _ in ()).throw(AssertionError("network")))
    refs=m.curate([row],resolve_external=False)[0]["related_context"]
    assert refs[0]["title"]=="Circular IF/N°529" and refs[0]["url"] is None and refs[0]["verified"] is False

def test_real_prestador_pulse_keeps_material_and_all_three_resolutions():
    history=json.loads(Path("data/history/superintendencia_signals.json").read_text())["signals"]
    pulse=next(s for s in m.curate(history,resolve_external=False) if s.get("sanction_count") and "Prestadores" in s["title"])
    assert pulse["sanction_count"]==len(pulse["source_alternatives"])==3
    assert "Clínica Los Carrera · 70 UF · cheque en garantía" in pulse["card_what"]
    assert all("UF" in x["material"] and x["title"] and x["url"] for x in pulse["source_alternatives"])

def test_real_circular_535_keeps_unverified_77_relationship():
    history=json.loads(Path("data/history/superintendencia_signals.json").read_text())["signals"]
    row=next(s for s in m.curate(history,resolve_external=False) if s.get("title")=="Circular IF/N°535")
    ref=next(x for x in row["related_context"] if "IF/N°77" in x["title"])
    assert ref["verified"] is False and ref["url"] is None and "Norma modificada" in ref["relationship"]

def test_df_headline_keeps_teaser_out_of_title():
    row=sig("Bupa acelera inversiones en Santiago con tres proyectos por US$ 15 millones El plan incluye una clínica y un centro de salud mental.")
    row.update(source_name="Diario Financiero",what_happened="Bupa anunció inversiones y nuevos centros médicos.",why_it_matters="Amplía la red asistencial y modifica capacidad competitiva de prestadores.")
    row["title"] += " La publicación describe además la estrategia para ampliar la red en el sector oriente."
    out=m.curate([row],resolve_external=False)
    assert out[0]["title"].endswith("US$ 15 millones")
    assert "El plan incluye" in out[0]["source_title_full"]
