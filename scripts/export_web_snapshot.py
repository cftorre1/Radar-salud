from __future__ import annotations
import argparse,json,re,shutil,base64
from collections import defaultdict
from datetime import datetime,timezone,date
from pathlib import Path
from radar_salud.reference_resolver import resolve_reference
from radar_salud.editorial_gate import publication_ready
from radar_salud.story_groups import date_basis_fields
from radar_salud.editorial_copy import apply_reviewed_copy
from radar_salud.isapre_pulse import build_pulse
from radar_salud.editorial_committee import build_committee_artifact

_NORMATIVE_V2_PATH=Path(__file__).resolve().parents[1]/"config"/"normative_editorial_v2.json"
def _normative_v2_config():
    try:human=json.loads(_NORMATIVE_V2_PATH.read_text(encoding="utf-8"))
    except Exception:human={"records":{},"title_contract":{}}
    # Verified automatic records (official text + literal checks + 2nd model) fill gaps; human wins.
    from radar_salud.normative_autorecord import merged_config
    return merged_config(_NORMATIVE_V2_PATH.parents[1],human)

TYPES=("Normativa","Legal","Noticias","Datos","Fiscalización")

def _audit_map(path=Path("data/editorial_audit_90d_2026_09_26.json")):
    if not path.exists(): return {}
    try: payload=json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}
    return {str(x.get("id") or ""):x for x in payload.get("items",[]) if isinstance(x,dict) and x.get("id")}

def _exclusions(path=Path("config/editorial_exclusions.json")):
    try:return {str(x["url"]):x for x in json.loads(path.read_text(encoding="utf-8")).get("items",[]) if x.get("url")}
    except (OSError,ValueError,KeyError):return {}

def _apply_persistent_editorial_decisions(signals):
    audit=_audit_map();excluded=_exclusions();out=[]
    for s in signals:
        if str(s.get("source_url") or "") in excluded:
            # Dirección exclusion: kept in history, never shown in the feed.
            r=dict(s);r["feed_visibility"]=False;r["editorial_exclusion"]=excluded[str(s["source_url"])]["reason"];out.append(r);continue
        r=dict(s);row=audit.get(str(r.get("source_url") or ""))
        if row:
            source_decision=str(row.get("decision") or "accept")
            aggregate=bool(r.get("event_type")=="DATA_PULSE" or str(r.get("title") or "").startswith("Pulso de sanciones"))
            r["editorial_source_decision"]=source_decision
            r["editorial_decision"]="accept" if aggregate and source_decision=="group" else source_decision
            r["editorial_materiality_score"]=row.get("materiality_score")
            r["editorial_business_review"]=row.get("business_review")
            r["editorial_value_category"]=row.get("value_category")
        else:
            r.setdefault("editorial_decision","accept")
        r["editorial_committee"]=build_committee_artifact(r)
        # A publication hold set earlier in curation (e.g. a sanction card without a descriptive
        # title) must survive the editorial pass; only an explicit reject adds a new hold here.
        held=r.get("feed_visibility") is False and r.get("publication_gate_reason")=="fiscalization_title_needs_description"
        r["feed_visibility"]=False if held or r.get("editorial_decision")=="reject" else True
        out.append(r)
    return out

def _d(v):
    if not v:return None
    try:return datetime.fromisoformat(str(v).replace("Z","+00:00")).date()
    except:
        try:return date.fromisoformat(str(v)[:10])
        except:return None

def _normalize_type(s):
    r=dict(s);types=[]
    for x in r.get("signal_types",[]) or []:
        x=str(x).strip();x="Noticias" if x=="Mercado" else x
        if x in TYPES and x not in types:types.append(x)
    if not types:
        cat=(r.get("category") or "").lower()
        types=["Fiscalización" if "fiscal" in cat else ("Normativa" if "regul" in cat else ("Legal" if "legal" in cat else "Noticias"))]
    r["signal_types"]=types;return r

def _normalize_scopes(s):
    r=dict(s);out=[];text=" ".join(str(r.get(k,"") or "") for k in ("title","what_happened","why_it_matters")).lower()
    for scope in r.get("scopes",[]) or []:
        x=str(scope).strip();low=x.lower()
        if "isapre" in low and "fonasa" in low:
            if re.search(r"\bisapre(?:s)?\b|instituciones? de salud previsional",text):out.append("Isapres")
            if re.search(r"\bfonasa\b|fondo nacional de salud",text):out.append("Fonasa")
        elif low in ("isapre","isapres"):out.append("Isapres")
        elif low=="fonasa":out.append("Fonasa")
        else:out.append(x)
    r["scopes"]=list(dict.fromkeys(out)) or ["Sistema de salud"];return r

def _separate_df_deck(s):
    r=dict(s)
    title=str(r.get("title") or "")
    # The DF listing sometimes concatenates its headline with a full teaser.
    # Keep the original in history; the public card needs the headline only.
    if r.get("source_name")=="Diario Financiero" and len(title)>180:
        match=re.search(r"\s+El\s+(?=(?:plan|alcalde|principal ejecutivo)\b)",title)
        if match and match.start()>=60:
            r["source_title_full"]=title
            r["title"]=title[:match.start()].strip()
    return r

def _card_micro(s):
    """Condense a verified complex announcement without dropping its outcome."""
    r=dict(s)
    what=str(r.get("what_happened") or "")
    if (r.get("source_url")=="https://www.redsalud.cl/noticias/redsalud-y-nueva-masvida-convenio"
        and r.get("event_date")=="2026-09-21"
        and all(x in what for x in ("Nueva Masvida","Libre Elección","Preferente","9 clínicas","Sanatorio Alemán","I-Med"))):
        r["source_title_full"]=r["title"]
        r["title"]="RedSalud y Nueva Masvida amplían convenio a escala nacional"
        r["card_what"]="El convenio habilita Libre Elección y Preferente en 9 clínicas, centros médicos y dentales y el Sanatorio Alemán, con bonificación I-Med."
        r["card_why"]="Afiliados Nueva Masvida pueden usar esa red pagando el copago de su plan; reemplaza el esquema de atención solo contra reembolso."
        r["scopes"]=list(dict.fromkeys([*r.get("scopes",[]),"Isapres"]))
    if (r.get("source_url")=="https://www.bupa.cl/somos-bupa/sala-de-prensa/personas-damnificadas-recibiran-atencion-gratuita-en-clinicas-privadas"
        and r.get("event_date")=="2026-08-13"
        and all(x in what for x in ("SAFED","FIBE","cinco redes privadas"))):
        r["source_title_full"]=r["title"]
        r["title"]="Fonasa activa SAFED para atención gratuita en clínicas privadas tras temporal"
        r["card_what"]="Damnificados inscritos en FIBE pueden recibir consultas, exámenes y salud mental sin costo en cinco redes privadas; las hospitalizaciones siguen en la red pública."
        r["card_why"]="La medida de agosto desplazó atención ambulatoria hacia clínicas en convenio para aliviar la red pública afectada."
        why=str(r.get("why_it_matters") or "")
        r["why_it_matters"]=why.replace("vigente ahora y condicionado a la inscripción en la FIBE",
            "condicionado a la inscripción en la FIBE al momento de publicarse (vigencia actual no verificada)")
        r["scopes"]=[x for x in r.get("scopes",[]) if x!="Farma / medicamentos"]
    if (str(r.get("title") or "").startswith("Bupa acelera inversiones")
        and all(token in what for token in ("US$15 millones","La Dehesa","Huinganal","Mindplace","San Damián"))):
        r["source_title_full"]=r.get("source_title_full") or r["title"]
        r["title"]="Bupa refuerza su red en el sector oriente con inversión, compra y salud mental"
        r["card_what"]="Bupa destina US$15 millones a tres movimientos simultáneos: un centro médico en La Dehesa, la compra de Clínicas Huinganal y Mindplace en San Damián."
        r["card_why"]="No es solo expansión física: combina nueva capacidad ambulatoria, una adquisición y entrada específica en salud mental, elevando presión competitiva en el sector oriente."
        r["key_points"]=[
            "La Dehesa: inauguración del primer centro médico que operará bajo la marca Bupa en Chile.",
            "Clínicas Huinganal: crecimiento mediante adquisición de activos clínicos existentes.",
            "Mindplace San Damián: incorporación de una oferta específica de salud mental dentro del mismo plan de expansión.",
            "Lectura competitiva: Bupa está creciendo por tres vías distintas a la vez —capacidad nueva, compra y diversificación de servicios— en una misma zona."
        ]
        r["affected_processes"]=["Estrategia de red","Competencia prestadores","M&A / expansión","Salud mental"]
    if (str(r.get("title") or "").startswith("Ministerio de Salud publica listado de Eleam")
        and all(token in what for token in ("Ministerio de Salud","Eleam","autorización sanitaria"))):
        r["card_what"]="El Minsal publicó un listado de Eleam con autorización sanitaria."
        r["card_why"]="Permite identificar establecimientos autorizados para usuarios, familias y supervisión de cuidados de larga estadía."
    if (str(r.get("title") or "").startswith("Max Luksic propone alianza entre municipalidades")
        and all(token in what for token in ("alianza entre municipalidades","$300 millones","Huechuraba"))):
        r["card_what"]="El alcalde de Huechuraba propuso una alianza municipal para mejorar la atención primaria; afirmó que ahora ejecuta $300 millones antes devueltos al Minsal."
        r["card_why"]="Plantea mejorar la ejecución de recursos de APS sin aumentar presupuesto; aún no es una medida sectorial adoptada."
    why=str(r.get("why_it_matters") or "")
    support=" ".join([why, *map(str, r.get("key_points") or [])])
    if (str(r.get("title") or "").startswith("Resolución Exenta IF/N°11156")
        and r.get("source_name")=="Superintendencia de Salud"
        and str(r.get("source_url") or "").startswith("https://www.superdesalud.gob.cl/")
        and all(token in what for token in ("Circular IF/Nº528","eliminación de esos topes","mecanismo de registro"))
        and all(token in support for token in ("bonificación sin tope anual","1 de noviembre de 2026","compra directa de bonos"))):
        r["source_title_full"]=r.get("source_title_full") or r["title"]
        r["title"]="Isapres: cobertura TEA sin tope anual y nuevo registro obligatorio · IF/N°11156"
        r["card_what"]="La Superintendencia mantuvo cobertura TEA sin tope anual para cinco prestaciones y prohibió exigir RND, renovaciones o evaluaciones repetidas."
        r["card_why"]="Las isapres deben habilitar registro presencial/digital, resolver en 15 días hábiles y compra directa de bonos sin tope antes del 1 de noviembre de 2026."
    return r

def _editorial_enrichment(s):
    """Attach only context that adds material evidence or decision value."""
    r=dict(s)
    if r.get("source_url")=="https://www.df.cl/empresas/salud/bupa-acelera-inversiones-en-sector-oriente-de-santiago-con-tres-proyectos":
        # Pre-production review: extra links that do not prove an additional
        # material fact are noise. Keep the original DF evidence only.
        r.pop("editorial_enrichment",None)
        r.pop("historical_connections",None)
        r.pop("historical_context_status",None)
    return r

def _compact_subject(text, max_chars=105):
    value=" ".join(str(text or "").split()).strip(" .:;-")
    # Turn an obligation/impact sentence into a subject phrase suitable for a title.
    value=re.sub(r"^(?:las?|los?)\s+(?:isapres?|prestadores?|entidades?|instituciones?|empleadores?|beneficiarios?|aseguradores?)\s+(?:deben|deberán|debe|deberá)\s+","",value,flags=re.I)
    value=re.sub(r"^(?:la|el)\s+superintendencia\s+(?:de\s+salud\s+)?(?:dispuso|instruyó|estableció|establece|modificó|modifica|ordenó|ordena)\s+","",value,flags=re.I)
    if len(value)<=max_chars:return value
    cut=value[:max_chars+1].rsplit(" ",1)[0].rstrip(" ,;:-")
    return cut


def _suseso_normative_upgrade(s):
    """Re-evaluate already-captured SUSESO acts with document-specific evidence."""
    r=dict(s)
    url=str(r.get("source_url") or "")
    title=str(r.get("title") or "")
    if r.get("source_name")!="Superintendencia de Seguridad Social (SUSESO)":
        return r
    if "Normativa" not in (r.get("signal_types") or []) and r.get("event_type")!="REGULATION":
        return r
    low=f"{title} {r.get('what_happened') or ''}".lower()
    if "circular 3926" in low or "w3-article-790656" in url.lower():
        r["display_title"]="Circular 3926 · Licencias médicas: nuevo procedimiento para COMPIN e Isapres desde enero de 2027"
        r["card_what"]="SUSESO instruye el procedimiento aplicable al régimen de licencias médicas y coordina la Ley N°20.585 con los reclamos del D.S. N°3."
        r["card_why"]="La circular tiene como destinatarios a COMPIN e Isapres y entra en vigencia el 4 de enero de 2027."
        r["what_happened"]=r["card_what"]
        r["why_it_matters"]=r["card_why"]
        r["validity_text"]="4 de enero de 2027"
        r["scopes"]=["Isapres","Salud pública","Salud laboral"]
        r["key_points"]=[
            "Tema oficial: licencias médicas.",
            "Destinatarios/fiscalizados: COMPIN e Isapres.",
            "Vigencia: 4 de enero de 2027."
        ]
        r["radar_score"]=max(80,int(r.get("radar_score") or 0))
        r["actionability_score"]=max(88,int(r.get("actionability_score") or 0))
    return r

def _normative_contract(s):
    r=dict(s)
    if r.get("event_type")!="REGULATION" and "Normativa" not in (r.get("signal_types") or []):return r
    title=str(r.get("source_title_full") or r.get("title") or "").strip()
    m=re.search(r"\b(Resolución(?:\s+Exenta)?|Circular|Oficio(?:\s+Ord(?:inario)?)?|Decreto)\s+(?:(IF|IP)\s*[/\-]?\s*)?N?[°º]?\s*([\d\.]+)",title,re.I)
    if not m:m=re.search(r"\b(Resolución(?:\s+Exenta)?|Circular|Oficio(?:\s+Ord(?:inario)?)?|Decreto)\s+(?:(IF|IP)\s*[/\-]?\s*)?N?[°º]?\s*([\d\.]+)",str(r.get("normative_document_label") or ""),re.I)
    cfg=_normative_v2_config()
    if not m:
        record=cfg.get("source_records",{}).get(str(r.get("source_url") or ""),{})
        label=str(record.get("legal_identity") or "")
        if not label:return r
        r.update(normative_document_label=label,legal_identity=label,normative_document_number=label)
    else:
        kind=" ".join(m.group(1).split());prefix=(m.group(2) or "").upper();raw_number=m.group(3);number=re.sub(r"\D","",raw_number)
        label=f"{kind} {prefix+'/' if prefix else ''}N°{raw_number}"
        r.update({"normative_document_type":kind,"normative_document_number":f"{prefix+'/' if prefix else ''}N°{raw_number}","normative_document_label":label,"legal_identity":label})
        record=cfg.get("source_records",{}).get(str(r.get("source_url") or "")) or cfg.get("records",{}).get(number,{})
    plain=str(record.get("plain_language_title") or "").strip();context=str(record.get("normative_context") or "").strip()
    subtitle=str(record.get("legal_subtitle") or label).strip()
    norm=lambda x:re.sub(r"[^a-z0-9]+"," ",str(x or "").lower().translate(str.maketrans("áéíóúüñ","aeiouun"))).strip()
    title_norm=norm(plain);identity_norm=norm(label)
    has_identity=bool(identity_norm and identity_norm in title_norm)
    has_subject=any(norm(x) in title_norm for x in record.get("subject_terms",[]))
    has_action=any(norm(x) in title_norm for x in record.get("action_terms",[]))
    reviewed=bool(record and plain and context and has_identity and has_subject and has_action and title_norm.count(identity_norm)==1)
    if not reviewed:
        from radar_salud.normative_minimal import minimal_card
        if r.get("normative_minimal"):return r  # already reduced to verifiable facts
        minimal=minimal_card(r,label)
        if minimal:
            # Opción A: verifiable facts only, badge visible; interpretation waits for review.
            r.pop("normative_title_review_required",None)
            r.update(minimal);r["legal_subtitle"]=subtitle
            r["normative_editorial"]={"legal_identity":label,"plain_language_title":minimal["display_title"],"legal_subtitle":subtitle,"editorial_state":"minimal_unreviewed","affected_actor":r.get("scopes") or []}
            return r
        r["normative_title_review_required"]=True
        if not plain:
            plain=str(r.get("display_title") or r.get("title") or label).strip()
            if identity_norm not in norm(plain):plain=f"{label} · {plain}"
        context=""
    else:r.pop("normative_title_review_required",None)
    r["display_title"]=plain;r["legal_subtitle"]=subtitle;r["normative_context"]=context
    r["normative_editorial"]={"legal_identity":label,"legal_action":r.get("what_happened"),"affected_rule":r.get("normative_subject") or r.get("related_reference_contexts"),"business_subject":r.get("normative_subject") or r.get("card_what") or r.get("what_happened"),"affected_actor":r.get("scopes") or r.get("affected_actors") or [],"required_change":r.get("card_why") or r.get("why_it_matters"),"effective_date_or_status":r.get("validity_text"),"plain_language_title":plain,"legal_subtitle":subtitle,"editorial_state":"reviewed" if reviewed else "needs_review"}
    return r

def _doc_key(s):
    if "Fiscalización" in (s.get("signal_types") or []) and s.get("source_url"):
        from radar_salud.superintendencia_fiscalizacion import canonical_url
        identity = s.get('source_record_id')
        return "fiscalization:"+canonical_url(s["source_url"])+(f'|record:{identity}' if identity else '')
    title=s.get("title","") or ""
    m=re.search(r"resoluci[oó]n(?:\s+exenta)?\s+(?:n[uú]mero\s+)?(?:if|ip)?\s*[/\-]?\s*n?[°º]?\s*([\d\.]+)",title,re.I)
    if m:return "res-"+re.sub(r"\D","",m.group(1))
    m=re.search(r"circular\s+(?:n[uú]mero\s+)?(?:if|ip)?\s*[/\-]?\s*n?[°º]?\s*(\d+)",title,re.I)
    if m:return "circular-"+m.group(1)
    return None

def _merge_duplicates(signals):
    groups=defaultdict(list);other=[]
    for s in signals:
        k=_doc_key(s)
        if k:groups[k].append(s)
        else:other.append(s)
    merged=[]
    for _,items in groups.items():
        if len(items)==1:merged.append(items[0]);continue
        base=max(items,key=lambda x:(x.get("source_name")=="Superintendencia de Salud",len(x.get("key_points",[]) or []),len(x.get("what_happened",""))))
        r=dict(base);alts=[];seen={r.get("source_url")}
        for x in items:
            if x is base:continue
            u=x.get("source_url")
            if u and u not in seen:
                alts.append({"title":x.get("title"),"source_name":x.get("source_name"),"url":u,"event_date":x.get("event_date"),**date_basis_fields(x)});seen.add(u)
        r["source_alternatives"]=alts;merged.append(r)
    return other+merged

def _relmap(s):
    return {str(x["id"]).strip():str(x.get("relationship") or "").strip() for x in s.get("related_reference_contexts",[]) or [] if isinstance(x,dict) and x.get("id")}

def _ref_key(text):
    m=re.search(r"circular\s+(?:if\s*[/\-]?\s*)?n?[°º]?\s*(\d+)",text or "",re.I)
    return "circular-"+m.group(1) if m else None

def _related_context(signals,resolve_external=True):
    idx={_doc_key(s):s for s in signals if _doc_key(s)};out=[]
    for s in signals:
        if s.get("normative_minimal"):
            out.append(dict(s));continue  # Opción A: no automated relations on unreviewed acts
        r=dict(s);rels=[];seen=set();relmap=_relmap(r)
        for ref in r.get("related_reference_ids",[]) or []:
            k=_ref_key(ref);relationship=relmap.get(ref) or "Antecedente normativo citado por el documento actual."
            target=idx.get(k) if k else None
            if target and target.get("source_url")!=r.get("source_url"):
                item={"title":target.get("title"),"summary":target.get("what_happened"),"relationship":relationship,
                      "url":target.get("source_url"),"event_date":target.get("event_date"),"verified":True,**date_basis_fields(target)}
            else:item=resolve_reference(ref,relationship) if resolve_external else None
            if not item:item={"title":ref,"summary":None,"relationship":relationship,"url":None,"event_date":None,"verified":False}
            identity=item.get("url") or item.get("title")
            if not identity or identity in seen or item.get("url")==r.get("source_url"):continue
            seen.add(identity);rels.append(item)
        r["related_context"]=rels[:5]
        related_keys={_doc_key({"title":x.get("title","")}) for x in rels}
        r["source_alternatives"]=[x for x in (r.get("source_alternatives") or []) if _doc_key(x) not in related_keys and x.get("url") not in {y.get("url") for y in rels}]
        r.pop("related_norms",None);r.pop("related_sources",None);out.append(r)
    return out

def _statistical_analysis_overrides(
    path=Path("data/statistical_analysis_overrides_v1.json"),
    verified_path=Path(__file__).resolve().parents[1]/"config"/"statistical_analysis_verified_v1.json",
):
    # Replays need the reviewed primary evidence, not an uncommitted CI file.
    # A newly built analysis may supersede that presentation; malformed inputs
    # must fail explicitly rather than silently degrading to an empty inventory.
    merged={}
    for candidate in (verified_path,path):
        if not candidate.exists():
            continue
        payload=json.loads(candidate.read_text(encoding="utf-8"))
        rows=payload.get("signals") if isinstance(payload,dict) else None
        if not isinstance(rows,dict) or any(not isinstance(row,dict) for row in rows.values()):
            raise ValueError(f"Invalid statistical analysis signals: {candidate}")
        identity_fields={"event_date","source_url","source_name","detected_at","ingestion_mode"}
        if any(identity_fields.intersection(row) for row in rows.values()):
            raise ValueError(f"Statistical presentation must preserve source identity/date: {candidate}")
        merged.update(rows)
    return merged

def add_material_epidemiology(signals, payload):
    """Append only a promoted material-week pulse; never leak provider-ready drafts."""
    if not isinstance(payload,dict) or payload.get("status")!="promoted_material_weekly_change":
        return list(signals)
    return [*signals, *(x for x in payload.get("signals",[]) if isinstance(x,dict))]

def _apply_statistical_analysis(signals):
    overrides=_statistical_analysis_overrides()
    out=[]
    for s in signals:
        r=dict(s)
        patch=overrides.get(str(r.get("source_url") or ""))
        if isinstance(patch,dict):
            for key,value in patch.items():
                r[key]=value
        if 'estadisticas-financieras-del-sistema-isapre-a-marzo-2026/' in str(r.get('source_url') or ''):
            # Preserve the historical analysis as evidence; conflicting coverage
            # must never be upgraded by a successful arithmetic/table parser.
            r['legacy_statistical_analysis']={key:r.get(key) for key in ('summary_table','data_insights','data_insight_evidence','statistical_conclusion')}
            r['statistical_view']={'family':'fefi','publication_status':'HOLD','hold_reason':'HOLD_COVERAGE_ESENCIAL',
                'limitations':['La nota de cobertura contradice cifras institucionales de Esencial; comparaciones y agregados afectados pendientes de aclaración.'],
                'source_url':r.get('source_url')}
            r['summary_table']={'columns':[],'rows':[]};r['data_insights']=[];r['data_insight_evidence']=[];r['statistical_conclusion']=''
            r['statistical_value_level']='publication_inventory'
            r['incremental_value_gate']={'limited_inventory':'Original accesible; comparación retenida por contradicción de cobertura.'}
        out.append(r)
    return out

def _resolution_relation_titles(signals):
    """Name the act once, its principal referenced norm once, then the material effect."""
    out=[]
    for s in signals:
        r=dict(s)
        if r.get("normative_minimal"):
            out.append(r);continue  # Opción A: never compose a headline from unreviewed copy
        kind=str(r.get("normative_document_type") or "")
        visible_title=str(r.get("title") or "")
        opaque=bool(re.fullmatch(r"(?:Resolución(?:\s+Exenta)?)\s+(?:(?:IF|IP)\s*[/\-]?\s*)?N?[°º]?\s*[\d\.]+",visible_title,re.I))
        if kind.lower().startswith("resolución"):
            rels=r.get("related_context") or []
            parent=next((x for x in rels if re.search(r"^(Circular|Oficio|Resolución|Decreto)\b",str(x.get("title") or ""),re.I)),None)
            if parent:
                parent_title=" ".join(str(parent.get("title") or "").split())
                label=str(r.get("normative_document_label") or "").strip()
                current=str(r.get("display_title") or r.get("title") or "").strip()
                # Preserve already-curated descriptive titles (e.g. TEA). This
                # relation formatter exists for opaque/legal-identity titles.
                if not opaque and label and not current.lower().startswith(label.lower()):
                    out.append(r)
                    continue
                evidence=" ".join(str(r.get(k) or "") for k in ("what_happened","why_it_matters","card_what","card_why")).lower()
                if "suspend" in evidence and ("caec" in evidence or "deriv" in evidence):
                    effect="suspende temporalmente sus instrucciones y cambia la operación CAEC"
                elif ("rechaz" in evidence and "suspend" in evidence) or "mantiene su ejecución" in evidence or "mantiene vigente" in evidence:
                    effect="mantiene su vigencia durante la impugnación"
                else:
                    base=_compact_subject(r.get("normative_subject") or r.get("card_why") or r.get("why_it_matters") or r.get("card_what") or r.get("what_happened"),86)
                    base=re.sub(re.escape(parent_title),"",base,flags=re.I)
                    base=re.sub(r"\b(?:la|el)\s+Circular\s+(?:IF\s*[/\-]?\s*)?N?[°º]?\s*\d+\b","",base,flags=re.I)
                    base=" ".join(base.split()).strip(" ·,:;-")
                    effect=base or "define un efecto operativo transitorio"
                r["display_title"]=f"{label} sobre {parent_title}: {effect}"
                r["editorial_committee"]=dict(r.get("editorial_committee") or {})
                r["editorial_committee"]["public_title"]=r["display_title"]
        out.append(r)
    return out

def _individual_sanction_titles(signals):
    """Sanctions left outside a sector pulse are shown one by one: their card title must say
    what the act does. Build it from captured fields only; otherwise hold the card."""
    from radar_salud.superintendencia_fiscalizacion import is_bare_act_title, sanction_card_title
    out=[]
    for s in signals:
        r=dict(s)
        if "Fiscalización" in (r.get("signal_types") or []) and not r.get("display_title") and is_bare_act_title(r.get("title")):
            title=sanction_card_title(r)
            if title:r["display_title"]=title
            else:r["feed_visibility"]=False;r["publication_gate_reason"]="fiscalization_title_needs_description"
        out.append(r)
    return out

def _normative_status(recent, universe):
    """Instructions show the later acts that suspend/modify/confirm them (from any retained act,
    even one older than the visible window), read from the regulator's listing subject."""
    from radar_salud.normative_relations import apply_backlinks
    linked={s.get("source_url"):s for s in apply_backlinks(list(universe)+[s for s in recent if s not in universe])
            if s.get("normative_status_events") and s.get("source_url")}
    out=[]
    for s in recent:
        r=dict(s);t=linked.get(r.get("source_url"))
        if t:r.update(normative_status_events=t["normative_status_events"],normative_status=t["normative_status"])
        out.append(r)
    return out

def _stat_family(s):
    if s.get("source_name")!="Superintendencia de Salud" or "Datos" not in (s.get("signal_types") or []):return None
    t=(s.get("title") or "").lower()
    if "movilidad" in t:return "movilidad"
    if "cartera" in t and ("regional" in t or "nivel regional" in t):return "cartera_regional"
    if "cartera" in t:return "cartera_total"
    if "suscripciones" in t or "desahucios" in t:return "suscripciones"
    if "financier" in t:return "financiero"
    if "ges" in t or "auge" in t:return "ges"
    if "boletín" in t or "boletin" in t:return "boletin"
    return None

def _latest_stats(signals):
    fam=defaultdict(list);other=[]
    pulses=[s for s in signals if s.get("event_type")=="DATA_PULSE" and str(s.get("title") or "").startswith("Pulso Isapre")]
    pulse_present=bool(pulses)
    pulse_day=max((_d(s.get("publication_date") or s.get("event_date")) or date.min for s in pulses),default=date.min)
    for s in signals:
        f=_stat_family(s)
        if f:fam[f].append(s)
        else:other.append(s)
    for family,items in fam.items():
        if pulse_present and family in {"cartera_total","cartera_regional","suscripciones","movilidad"}:
            # When the aggregate pulse already covers the same release period,
            # routine component cards are redundant unless they add a distinct,
            # evidenced decision insight of their own. A release published after
            # the pulse's own release is new information the pulse does not cover.
            candidates=[x for x in items if x.get("distinct_decision_value") is True or x.get("data_insights")
                        or (_d(x.get("event_date")) or date.min)>pulse_day]
            if not candidates:
                continue
            items=candidates
        other.append(max(items,key=lambda x:(_d(x.get("event_date")) or date.min,x.get("radar_score",0))))
    return other

def _routine_accreditation(s):
    """Retain individual accreditation acts in history, omit them from executive feed."""
    if s.get("source_name")!="Superintendencia de Salud" or s.get("distribution")!="archive":return False
    text=" ".join(str(s.get(k) or "") for k in ("title","what_happened","why_it_matters")).lower()
    registry=("registro público de prestadores institucionales de salud acreditados" in text)
    individual=registry and any(x in text for x in (
        "inscripción n°","inscripción nº","mantiene su inscripción","mantener su inscripción",
        "inscribió al","inscribio al","declara acreditado","declaró acreditado","plan de corrección","certificado de acreditación"
    ))
    programs=("registro de entidades certificadoras" in text
              and "programas acreditados" in text and "inscribir" in text)
    strategic=bool(re.search(r"\b(modific[oó]|sustituy[oó]|derog[oó])\s+(?:el|la|los|las)\s+(?:reglamento|est[aá]ndar|norma|circular)",text))
    system_wide=bool(re.search(r"\b(todos los prestadores|prestadores institucionales en general|nuevo estándar|cambia el estándar|modifica el sistema de acreditación)\b",text))
    return bool((individual or programs) and not strategic and not system_wide)

def _is_material_statistical_release(s):
    if s.get("source_name")!="Superintendencia de Salud" or "Datos" not in (s.get("signal_types") or []):
        return False
    t=(s.get("title") or "").lower()
    return bool("estadíst" in t or "estadist" in t or "boletín" in t or "boletin" in t
                or "ges" in t or "auge" in t or "cartera" in t or "movilidad" in t
                or "suscripciones" in t or "desahucios" in t)

def _document_inventory(s):
    docs=s.get("source_documents") or []
    names=[]
    for d in docs:
        text=(" ".join([str(d.get("label") or ""),str(d.get("url") or "")])).lower()
        for key,label in (
            ("financier","finanzas"),("cartera","cartera"),("prestaciones","prestaciones"),
            ("licencias","licencias médicas"),("egresos","egresos hospitalarios"),
            ("planes","planes de salud"),("ges","GES"),("auge","GES"),
            ("acreditacion","acreditación"),("mediacion","mediación"),
            ("reclamos","reclamos"),("rnpi","registro de prestadores")
        ):
            if key in text and label not in names:names.append(label)
    return names

def _statistical_value_ladder(s):
    """Always publish material public statistics at the highest supported value level."""
    r=dict(s)
    if not _is_material_statistical_release(r):
        return r
    connected=bool(r.get("historical_connections") or r.get("related_context") or r.get("distinct_decision_value") is True)
    deep=bool(r.get("data_insights") or r.get("data_insight_evidence") or r.get("summary_table") or r.get("key_points"))
    title=str(r.get("title") or "")
    facts=[str(x).strip() for x in (r.get("key_facts") or []) if str(x).strip()]
    inventory=_document_inventory(r)
    docs=r.get("source_documents") or []
    inventory_preferred=bool(docs) and bool(re.search(r"series estad[ií]sticas|bolet[ií]n estad[ií]stico",title,re.I))
    central=bool(r.get("key_numbers") or [x for x in facts if str(x).strip()!=title and " - superintendencia de salud" not in str(x).lower()])
    if connected and deep:
        level="connected_insight"
    elif deep:
        level="deep_analysis"
    elif inventory_preferred:
        level="publication_inventory"
    elif central:
        level="central_finding"
    else:
        level="publication_inventory"
    r["statistical_value_level"]=level

    if level=="central_finding":
        if "ges" in title.lower() or "auge" in title.lower():
            period=next((x for x in facts if "actualiz" in x.lower()),"")
            r["card_what"]="La publicación reúne casos y tasas de uso GES por problema de salud y seguro (Fonasa e Isapres)."+(f" {period}" if period else "")
            r["card_why"]="Permite saber qué patologías y tasas pueden compararse entre seguros; Alicanto aún no ha calculado variaciones entre períodos para esta entrega."
        elif facts:
            r["card_what"]=facts[0]
            r["card_why"]="Alicanto identificó el contenido central del documento; el análisis comparativo aún no está disponible."
    elif level=="publication_inventory":
        if inventory:
            r["card_what"]=f"La publicación reúne {len(docs)} archivos oficiales sobre "+", ".join(inventory)+"."
        elif docs:
            r["card_what"]=f"La publicación incorpora {len(docs)} archivos estadísticos oficiales."
        else:
            r["card_what"]=r.get("what_happened") or f"Se publicó {title}."
        r["card_why"]=""
        r["card_why_optional"]=True
        r["methodology_visibility"]="collapsed"
        r["incremental_value_gate"]={"inventory":"Official document links and topic coverage only; no calculated statistical finding"}
        r["statistical_methodology"]={"source_url":r.get("source_url"),"scope":"document_inventory_only","analysis_status":"not_performed"}
    elif level=="deep_analysis" and not r.get("card_what"):
        r["card_what"]=r.get("what_happened")
        r["card_why"]=r.get("why_it_matters")

    return r

def _enforcement_register_pulses(signals, today=None):
    """Keep legal records individually; aggregate only reviewed register families."""
    today=today or date.today()
    from radar_salud.suseso_fiscalizacion import current_professional_suspension
    groups=defaultdict(list);contexts=defaultdict(list);other=[]
    for signal in signals:
        family=('suseso_emisores' if signal.get('source_record_id') and
            signal.get('document_class')=='enforcement_sanction' else
            'sis_agentes' if signal.get('scopes')==['Agentes de ventas'] else None)
        emitted=_d(signal.get('emission_date'))
        if family and emitted and 0 <= (today-emitted).days <=90:
            groups[family].append(signal)
        elif family=='suseso_emisores' and current_professional_suspension(signal['source_url'],signal,today):
            contexts[family].append(signal)
        else:other.append(signal)
    for family,items in groups.items():
        items.sort(key=lambda s:(s['emission_date'],s.get('source_record_id') or s['source_url']),reverse=True)
        recent30=sum((today-_d(s['emission_date'])).days<=30 for s in items)
        latest=items[0]
        alternatives=[]
        current_context=[]
        for s in items+contexts[family]:
            amount=s.get('sanction_amount');unit=s.get('sanction_unit')
            material=s.get('regulated_entity') or ''
            if amount is not None and unit:material+=f' · {amount:g} {unit}'
            material+=' · '+(s.get('validity_text') or s.get('what_happened') or '')
            reference=dict(title=s['title'],url=s['source_url'],source_record_id=s.get('source_record_id'),
                event_date=s['emission_date'],emission_date=s['emission_date'],publication_date=s.get('publication_date'),
                event_date_basis='emission',material=material,ingestion_mode=s.get('ingestion_mode'),detected_at=s.get('detected_at'))
            (current_context if s in contexts[family] else alternatives).append(reference)
        if family=='suseso_emisores':
            title='SUSESO sanciona a emisores de licencias · registro de 90 días'
            what=f'{recent30} oficios emitidos en 30 días y {len(items)} en 90 días, con multas y suspensión de emisión de licencias. Las fechas de suspensión se detallan por profesional.'
            if current_context:
                what+=f' Además, {len(current_context)} oficios anteriores mantienen suspensiones vigentes; se muestran como antecedentes y no se suman a las novedades.'
            why='Prestadores, COMPIN e Isapres deben contrastar las licencias con las suspensiones del registro. Los sancionados son los profesionales emisores.'
        else:
            from collections import Counter
            effects=Counter(s['event_type'] for s in items)
            title='SIS sanciona a agentes de ventas · registro de 90 días'
            what=f'{recent30} resoluciones emitidas en 30 días y {len(items)} en 90: {effects["REGISTRATION_CANCELLATION"]} cancelaciones directas, {effects["SANCTION_SUBSTITUTION"]} multas impagas sustituidas por cancelación, {effects["SANCTION"]} multas y {effects["SANCTION_WARNING"]} censuras.'
            why='Las Isapres deben revisar habilitación, consentimiento y veracidad de la venta. La cancelación del registro impide actuar como agente; no equivale a una absolución.'
        pulse=dict(latest,title=title,what_happened=what,why_it_matters=why,card_what=what,card_why=why,
            event_type='SANCTION_REGISTER',source_record_id=family+':rolling90',regulated_entity=None,
            event_date=latest['emission_date'],emission_date=latest['emission_date'],publication_date=None,
            event_date_basis='emission',window_basis='emission_date',sanction_count=len(items),
            counts={'30':recent30,'90':len(items)},source_alternatives=alternatives,source_documents=[],
            historical_sanction_context=current_context,
            sanction_amount=None,sanction_unit=None,key_points=[],related_reference_ids=[],
            validity_text='Cada acto conserva su fecha de emisión y efecto. La fecha de publicación del registro no está acreditada; consulte la vigencia individual.',
            ingestion_mode='BACKFILL',risk_notes=[],key_facts=[])
        other.append(pulse)
    return other

def _sanction_pulses(signals, today=None):
    """Keep individual records in history, show one rolling pulse per sector."""
    today=today or date.today()
    signals=_enforcement_register_pulses(signals,today)
    groups=defaultdict(list);other=[]
    for s in signals:
        scopes=s.get("scopes") or []
        sector=next((x for x in ("Isapres","Prestadores") if x in scopes),None)
        if s.get('date_reconciliation') and not s.get('publication_date'):
            # A verified issuance is visible individually; an inconsistent listing
            # publication must never become a fictitious new publication pulse.
            other.append(s)
            continue
        publication = _d(s.get("publication_date") or s.get("event_date"))
        age=(today-publication).days if publication else 999
        if s.get("event_type")=="SANCTION" and sector:
            if 0<=age<=30:groups[(sector,30)].append(s)
            elif 30<age<=90:groups[(sector,90)].append(s)
            # Individual and older resolutions stay in durable history.
            continue
        other.append(s)
    for (sector,window),items in groups.items():
        items.sort(key=lambda x:_d(x.get("event_date")) or date.min,reverse=True)
        live=[s for s in items if s.get("ingestion_mode")=="LIVE"]
        latest=live[0] if live else items[0]
        def material(s):
            parts=[str(s.get("regulated_entity") or "").strip()]
            amount=s.get("sanction_amount")
            unit=str(s.get("sanction_unit") or "").strip()
            if isinstance(amount,(int,float)) and not isinstance(amount,bool) and amount>=0 and unit:
                parts.append(f"{amount:g} {unit}")
            topic=str(s.get("fiscalization_topic") or "").strip()
            if topic:parts.append(topic)
            return " · ".join(x for x in parts if x)
        resolutions=[{"title":s.get("title"),"source_name":s.get("source_name"),
            "url":s.get("source_url"),"event_date":s.get("event_date"),"publication_date":s.get("publication_date"),"material":material(s),
            "emission_date":s.get("emission_date"),"event_date_basis":s.get("event_date_basis"),"signal_types":["Fiscalización"],
            "ingestion_mode":s.get("ingestion_mode"),"detected_at":s.get("detected_at")}
            for s in items if s.get("source_url")]
        lead=material(items[0])
        brief_topic=str(items[0].get("fiscalization_topic") or "")
        if "cheque en garantía" in brief_topic.lower():brief_topic="cheque en garantía"
        brief_parts=[str(items[0].get("regulated_entity") or "").strip()]
        amount=items[0].get("sanction_amount");unit=str(items[0].get("sanction_unit") or "").strip()
        if isinstance(amount,(int,float)) and not isinstance(amount,bool) and amount>=0 and unit:brief_parts.append(f"{amount:g} {unit}")
        if brief_topic:brief_parts.append(brief_topic)
        brief_material=" · ".join(x for x in brief_parts if x)
        period='últimos 30 días' if window==30 else 'días 31 a 90'
        title=f"Pulso de sanciones a {sector} · {period}" if window==30 else f"Sanciones a {sector} · {period}"
        pulse=dict(latest,title=title,
            what_happened=f"{len(items)} {'resolución sancionadora publicada' if len(items)==1 else 'resoluciones sancionadoras publicadas'} en {period}. {len(live)} detectadas en LIVE; {len(items)-len(live)} incorporadas desde el histórico."+(f" Entre ellas: {lead}." if lead else ""),
            why_it_matters="Permite observar focos recientes de fiscalización y revisar cada resolución en su fuente original.",
            source_alternatives=resolutions,
            card_what=f"{len(items)} sanciones a {sector} · {period}."+(f" Entre ellas: {brief_material}." if brief_material else ""),
            event_date=max((s.get("publication_date") or s.get("event_date") or "" for s in items)),
            publication_date=max((s.get("publication_date") or s.get("event_date") or "" for s in items)),
            event_date_basis="publication", emission_date=None,
            window_basis="publication_date", sanction_count=len(items),source_documents=[],key_points=[f"{x['material']} · {x['title']}" for x in resolutions if x['material']],risk_notes=[],key_facts=[],
            related_reference_ids=[],related_reference_contexts=[],affected_processes=[],
            regulated_entity=None,sanction_amount=None,sanction_unit=None,fiscalization_topic=None,
            radar_score=max(s.get("radar_score") or 0 for s in items),
            confidence_score=min(s.get("confidence_score") or 0 for s in items),
            detected_at=max((s.get("detected_at") or "" for s in live),default=latest.get("detected_at")),
            ingestion_mode="LIVE" if live else "BACKFILL")
        other.append(pulse)
    return other

def curate(signals,resolve_external=True,as_of=None):
    # Version3 is already reviewed as a complete public artifact. Legacy copy
    # transforms must never rewrite it after its receipt was signed.
    from radar_salud.editorial_v3 import validate_depth
    v3=[]
    all_dates=[_d(s.get('event_date')) for s in signals if _d(s.get('event_date'))]
    v3_reference=as_of or max(all_dates or [date.today()])
    for source in signals:
        if str(source.get("editorial_schema_version"))!="3":continue
        record=dict(source)
        ok,reason,score=publication_ready(record)
        if ok and record.get("feed_visibility") is not False and _d(record.get("event_date")) and 0<=(v3_reference-_d(record["event_date"])).days<90:
            record["depth_gate"]=validate_depth(record)
            record["publication_gate_reason"]=reason
            record["publication_ready_score"]=score
            v3.append(record)
    # Same piece, same canonical card. Related analyses keep their own IDs.
    def piece_id(s):
        return s.get("piece_id") or base64.b64encode((str(s.get("source_url") or "")+'|'+str(s.get("event_date") or "")+'|'+str(s.get("event_type") or "OTHER")).encode()).decode()
    approved={};conflicts=set()
    for record in v3:
        identity=piece_id(record)
        if identity in approved and approved[identity]["depth_gate"]["content_version"]!=record["depth_gate"]["content_version"]:conflicts.add(identity)
        else:approved[identity]=record
    v3=[r for identity,r in approved.items() if identity not in conflicts]
    replacements={piece_id(r) for r in v3}|{alias for r in v3 for alias in r.get("read_aliases",[])}
    signals=[s for s in signals if str(s.get("editorial_schema_version"))!="3" and piece_id(s) not in replacements]
    normalized=[]
    for s in signals:
        r=_normative_contract(_suseso_normative_upgrade(_editorial_enrichment(_card_micro(_separate_df_deck(_normalize_scopes(_normalize_type(s)))))))
        ok,reason,q=publication_ready(r);r["publication_ready_score"]=q;r["publication_gate_reason"]=reason
        if ok:normalized.append(r)
    if not normalized:return v3
    latest=as_of or max([_d(x.get("event_date")) for x in normalized if _d(x.get("event_date"))] or [date.today()])
    def within_window(s):
        from radar_salud.suseso_fiscalizacion import current_professional_suspension
        if 'Fiscalización' in s.get('signal_types',[]) and current_professional_suspension(s.get('source_url',''),s,latest):
            return True
        dates=[_d(s.get('event_date'))]
        if 'Fiscalización' in s.get('signal_types',[]):dates.append(_d(s.get('publication_date')))
        return any(day and 0<=(latest-day).days<=90 for day in dates)
    recent=[s for s in normalized if within_window(s) and not _routine_accreditation(s)]
    # Public statistics remain visible even when deep analysis is unavailable.
    # Enrich each one to the highest supported level: connected insight -> deep analysis
    # -> central finding -> useful publication inventory.
    recent=_apply_statistical_analysis(recent)
    recent=[_statistical_value_ladder(s) for s in recent]
    recent=_latest_stats(recent);recent=_merge_duplicates(recent);recent=_sanction_pulses(recent,today=as_of);recent=_related_context(recent,resolve_external);recent=_resolution_relation_titles(recent);recent=_individual_sanction_titles(recent)
    recent=_normative_status(recent,normalized)
    # An explicitly reviewed DF corroboration yields to its official event when
    # that counterpart is present. Keep both source records in durable history.
    counterpart_urls={s.get('source_url') for s in recent}
    recent=[s for s in recent if not (s.get('source_name')=='Diario Financiero' and s.get('df_duplicate_of')
        and s.get('df_duplicate_of') in counterpart_urls)]
    recent=_apply_persistent_editorial_decisions(recent)
    recent=[_normative_contract(s) if s.get("event_type")=="REGULATION" or "Normativa" in (s.get("signal_types") or []) else s for s in recent]
    recent=[s for s in recent if s.get("feed_visibility") is not False]
    from radar_salud.normative_minimal import strip_interpretation
    recent=[strip_interpretation(dict(s)) for s in recent]
    # One card per story (Dirección, punto II): same-event coverage folds into a lead card;
    # long running stories become one reviewed synthesis. Members stay in history.
    from radar_salud.story_groups import apply_story_groups, load_groups
    def story_gate(card):
        ok,reason,score=publication_ready(card)
        if not ok:return False
        card["publication_gate_reason"]=reason;card["publication_ready_score"]=score
        card["editorial_decision"]="accept"
        card["editorial_committee"]=build_committee_artifact(card)
        return card["editorial_committee"].get("verdict")=="PASS"
    recent,summaries=apply_story_groups(recent,load_groups(),gate=story_gate)
    recent.extend(summaries)
    # Individual accreditation acts stay out of the feed; one verifiable rolling pulse instead.
    from radar_salud.accreditation_pulse import accreditation_pulse
    pulse=accreditation_pulse(signals,latest)
    if pulse:
        ok,reason,score=publication_ready(pulse)
        if ok:
            pulse["publication_gate_reason"]=reason;pulse["publication_ready_score"]=score
            # Same committee gate as every visible card (web contract requires a PASS artifact).
            pulse["editorial_decision"]="accept"
            pulse["editorial_committee"]=build_committee_artifact(pulse)
            pulse["feed_visibility"]=pulse["editorial_committee"].get("verdict")=="PASS"
            recent.append(pulse)
    recent.extend(v3)
    recent.sort(key=lambda s:(_d(s.get("event_date")) or date.min,s.get("radar_score",0)),reverse=True);return recent

def preserve_v3_copy(signals):
    legacy=iter(apply_reviewed_copy([s for s in signals if str(s.get("editorial_schema_version"))!="3"]))
    return [s if str(s.get("editorial_schema_version"))=="3" else next(legacy) for s in signals]


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",default="web/data/radar_today.json");ap.add_argument("--offline",action="store_true",help="Rebuild only from recorded evidence");ap.add_argument("--as-of",type=date.fromisoformat,default=None,help="Curation date for deterministic test fixtures (YYYY-MM-DD); omit for the real snapshot");args=ap.parse_args()
    raw=json.loads(Path(args.input).read_text(encoding="utf-8"));signals=raw.get("signals",raw) if isinstance(raw,dict) else raw
    signals=list(signals)
    canonical=Path("data/excel/validated_series.json")
    if canonical.exists():
        try:pulse=build_pulse(json.loads(canonical.read_text(encoding="utf-8")),signals)
        except (OSError,ValueError,TypeError):pulse=None
        if pulse:signals.append(pulse)
    epidemiology_path=Path("web/data/epidemiology.json")
    if epidemiology_path.exists():
        try:
            epidemiology=json.loads(epidemiology_path.read_text(encoding="utf-8"))
            signals=add_material_epidemiology(signals,epidemiology)
        except (OSError,ValueError,TypeError):
            pass
    cards=preserve_v3_copy(curate(signals,resolve_external=not args.offline,as_of=args.as_of))
    # WATCH (Dirección 27-oct): every card carries explicit entity refs; aggregates inherit their acts.
    from radar_salud import entity_watch
    entity_watch.apply(cards,history=signals)
    # Dirección 28-oct-2026: paywalled press shows only title + public lead; every
    # rendered link must be a valid absolute URL or no link at all.
    from radar_salud.source_rights import redact_signal
    from radar_salud.source_urls import sanitize_card_links
    cards=[sanitize_card_links(redact_signal(card)) for card in cards]
    payload={"date":(args.as_of or date.today()).isoformat(),"generated_at":datetime.now(timezone.utc).isoformat(),"entities":entity_watch.public_catalog(),"signals":cards}
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    health=Path("data/source_health.json")
    if health.exists():shutil.copyfile(health,out.parent/"source_health.json")
    from radar_salud.public_source_catalog import export_public_sources
    if health.exists():export_public_sources(health,out.parent/"public_sources.json")
    print(f"snapshot={out} signals={len(payload['signals'])}")
if __name__=="__main__":main()
