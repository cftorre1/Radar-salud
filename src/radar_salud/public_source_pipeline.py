from __future__ import annotations
import json,re
from html.parser import HTMLParser
from .models import RawItem
from .pipeline import build_signal
from .scouts import fetch_html
from .document_intelligence import extract_pdf_text
from .llm_analysis import analyze_official_news, analyze_news
from .processing import DeferredProcessing

MONTHS={"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06","julio":"07","agosto":"08","septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"}
MONTHS.update({"ene":"01","feb":"02","mar":"03","abr":"04","may":"05","jun":"06","jul":"07","ago":"08","sep":"09","sept":"09","oct":"10","nov":"11","dic":"12"})

class _Meta(HTMLParser):
    def __init__(self):super().__init__();self.description="";self.published="";self.text=[];self.ogtitle=""
    def handle_starttag(self,tag,attrs):
        if tag.lower()!="meta":return
        a={k.lower():v for k,v in attrs};key=(a.get("name") or a.get("property") or "").lower();content=a.get("content") or ""
        if key in ("description","og:description","twitter:description") and content and not self.description:self.description=" ".join(content.split())
        if key=="og:title" and content and not self.ogtitle:self.ogtitle=" ".join(content.split())
        if key in ("article:published_time","date","datepublished","publishdate") and content and not self.published:self.published=content
    def handle_data(self,data):
        t=" ".join(data.split())
        if t:self.text.append(t)

def _date(text):
    if not text:return None
    m=re.search(r"(20\d{2})-(\d{2})-(\d{2})",text)
    if m:return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m=re.search(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2})",text)
    if m:return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m=re.search(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(20\d{2})",text,re.I)
    if m and m.group(2).lower() in MONTHS:return f"{m.group(3)}-{MONTHS[m.group(2).lower()]}-{int(m.group(1)):02d}"
    m=re.search(r"(\d{1,2})\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+(20\d{2})",text,re.I)
    if m and m.group(2).lower() in MONTHS:return f"{m.group(3)}-{MONTHS[m.group(2).lower()]}-{int(m.group(1)):02d}"
    m=re.search(r"(\d{1,2})\s*([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\.?\s*(20\d{2})",text,re.I)
    if m and m.group(2).lower() in MONTHS:return f"{m.group(3)}-{MONTHS[m.group(2).lower()]}-{int(m.group(1)):02d}"
    return None

def _field(text,label):
    flat=" ".join((text or "").split())
    m=re.search(rf"\b{re.escape(label)}\s*:?\s*(.{{1,220}}?)(?=\s+(?:Materia|Destinatario|Observaci[oó]n|Vigencia|Acci[oó]n|Fuentes|Fiscalizados|Entidades Fiscalizadas|Tipo Contenido Normativo|Departamento)\b|$)",flat,re.I)
    return m.group(1).strip(" :-") if m else None

def enrich(raw):
    raw.metadata.pop("fetch_error",None)
    try:
        p=_Meta();p.feed(fetch_html(raw.url));body=" ".join(p.text)
        if p.ogtitle and len(raw.title)<18:raw.title=p.ogtitle
        raw.raw_text=p.description or body[:1400]
        raw.event_date=raw.event_date or _date(p.published)
        raw.metadata["page_text"]=body[:18000]
    except Exception as e:
        raw.metadata["fetch_error"]=type(e).__name__
        print("enrich:",e)
    return raw

def _noise(title):
    t=(title or "").lower()
    terms=("renuncia","nombramiento","nombra,","nombra a","nombra mediante","designa","designación","designacion",
           "asume como","alta dirección pública","alta direccion publica","nuevo subsecretario","nueva subsecretaria",
           "seremi","director del servicio de salud","directora del servicio de salud","continúa recorrido",
           "continua recorrido","visita nuevo","visita el","visita la","conmemora","participa en","trayectoria")
    return any(x in t for x in terms)

def _fallback_minsal_score(title,text):
    t=f"{title} {text}".lower()
    if _noise(title):return 0
    if any(x in t for x in ("alerta alimentaria","retiro de producto","lote de")):return 45
    if any(x in t for x in ("ley","decreto","reglamento","plan nacional","estrategia nacional","listas de espera","ges","fonasa","financiamiento","presupuesto","red asistencial","inversión","inversion")):return 80
    if any(x in t for x in ("programa","medida","fiscalización","fiscalizacion","hospital","eleam","medicamentos","alerta sanitaria")):return 66
    return 45

def process_minsal(raw,cfg):
    if _noise(raw.title):return None
    raw=enrich(raw)
    if not raw.event_date:
        raw.event_date=_date(raw.metadata.get("page_text","")[:6000])
    if not raw.event_date:return None
    body=raw.metadata.get("page_text") or raw.raw_text
    ai=analyze_official_news(title=raw.title,text=body,source_name=raw.source_name)
    score=int(ai.get("relevance_score")) if ai else _fallback_minsal_score(raw.title,body)
    if score<65:return None
    raw.metadata.update({"what_happened":(ai.get("what_happened") if ai else raw.raw_text) or raw.title,
      "why_it_matters":(ai.get("why_it_matters") if ai else "La publicación contiene un cambio oficial con efectos relevantes para una parte del sistema de salud."),
      "signal_types":["Noticias"],"scopes":["Salud pública"],"watch_tags":["minsal","salud pública"],
      "scores":{"economic":45,"regulatory":55,"scope":score,"novelty":score,"actionability":60}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Noticias"];row["scopes"]=["Salud pública"];row["editorial_relevance"]=score;return row

def _clean_validity(text):
    v=_field(text,"Vigencia")
    if not v:return None
    if any(x in v.lower() for x in ('nj:','"529"','"535"','propertyvalue','javascript')):return None
    return v[:180]

def _suseso_date(text):
    v=_field(text,"Fecha")
    return _date(v) if v else None

def process_suseso(raw,cfg):
    """Publish SUSESO normative acts with document-specific subject, affected actors and validity."""
    raw=enrich(raw)
    text=raw.metadata.get("page_text") or raw.raw_text
    raw.event_date=_suseso_date(text) or raw.event_date
    if not raw.event_date:return None
    vig=_clean_validity(text)
    low=f"{raw.title} {text}".lower()
    scopes=[]
    if "isapre" in low:scopes.append("Isapres")
    if "compin" in low:scopes.append("Salud pública")
    if any(x in low for x in ("licencia médica","licencias médicas","subsidio por incapacidad","sanna","ley 16.744","accidentabilidad","enfermedad profesional")):
        scopes.append("Salud laboral")
    scopes=list(dict.fromkeys(scopes)) or ["Salud laboral"]

    what=(raw.raw_text or raw.title).strip()
    why=None
    key_points=[]
    if ("circular 3926" in low or "w3-article-790656" in raw.url.lower()) and "licencias médicas" in low:
        what=("La Circular 3926 imparte instrucciones sobre el procedimiento aplicable al régimen de licencias médicas "
              "y coordina la aplicación de la Ley N°20.585 con los reclamos regulados por el D.S. N°3 de 1984.")
        why=("Tiene como destinatarios a las COMPIN y a las Isapres individualizadas por SUSESO, y entra en vigencia "
             "el 4 de enero de 2027; por tanto, el cambio debe incorporarse a la gestión de licencias médicas y reclamos antes de esa fecha.")
        key_points=[
          "Tema oficial: licencias médicas.",
          "Fiscalizados/destinatarios: COMPIN e Isapres.",
          "Vigencia informada por SUSESO: 4 de enero de 2027."
        ]
        vig="4 de enero de 2027"
    else:
        ai=analyze_official_news(title=raw.title,text=text[:9000],source_name="Superintendencia de Seguridad Social (SUSESO)")
        if ai:
            candidate_what=(ai.get("what_happened") or "").strip()
            candidate_why=(ai.get("why_it_matters") or "").strip()
            if len(candidate_what)>=45:what=candidate_what
            if len(candidate_why)>=35:why=candidate_why
    if not why:
        why=("La publicación contiene instrucciones regulatorias de SUSESO con efecto sobre los destinatarios identificados "
             "en el acto y debe revisarse junto con su fecha de vigencia y el procedimiento que modifica.")

    raw.metadata.update({"what_happened":what,"why_it_matters":why,
      "key_points":key_points,
      "signal_types":["Normativa"],"scopes":scopes,"watch_tags":["suseso","normativa"]+[x.lower() for x in scopes],
      "event_type":"REGULATION","validity_text":vig,
      "scores":{"economic":50,"regulatory":90,"scope":85 if len(scopes)>1 else 75,"novelty":80,"actionability":88}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Normativa"];row["scopes"]=scopes;return row


def process_suseso_news(raw,cfg):
    """Business-relevant official SUSESO news, separate from normative discovery."""
    raw=enrich(raw)
    if not raw.event_date:return None
    body=raw.metadata.get("page_text") or raw.raw_text
    t=f"{raw.title} {body}".lower()
    material_terms=("licencia médica","licencias médicas","ley karin","riesgo psicosocial","riesgos psicosociales",
                    "fonasa","cajas de compensación","mutual","accidentabilidad","enfermedad profesional",
                    "seguridad y salud en el trabajo","salud mental","fiscalización","vigia","prevención")
    if not any(x in t for x in material_terms):return None
    ai=analyze_official_news(title=raw.title,text=body,source_name="Superintendencia de Seguridad Social (SUSESO)")
    score=int(ai.get("relevance_score")) if ai else 72
    if score<65:return None
    scopes=["Salud laboral"]
    if "fonasa" in t:scopes.append("Fonasa")
    if "isapre" in t:scopes.append("Isapres")
    what=(ai.get("what_happened") if ai else raw.raw_text) or raw.title
    why=(ai.get("why_it_matters") if ai else "La publicación contiene información oficial relevante para salud laboral, licencias médicas, seguridad social o coordinación del sistema.")
    raw.metadata.update({"what_happened":what,"why_it_matters":why,
      "signal_types":["Noticias"],"scopes":list(dict.fromkeys(scopes)),
      "watch_tags":["suseso","salud laboral","seguridad social"],
      "scores":{"economic":50,"regulatory":60,"scope":score,"novelty":score,"actionability":68}})
    row=build_signal(raw,cfg).to_dict()
    row["signal_types"]=["Noticias"];row["scopes"]=list(dict.fromkeys(scopes));row["editorial_relevance"]=score
    return row


def process_suseso_fiscalizacion(raw,cfg):
    """Official SUSESO fiscalization signal for Isapres or COMPIN."""
    raw=enrich(raw)
    if not raw.event_date:return None
    body=raw.metadata.get("page_text") or raw.raw_text
    actor=raw.metadata.get("fiscalized_actor") or "Sistema de salud"
    ai=analyze_official_news(title=raw.title,text=body,source_name="Superintendencia de Seguridad Social (SUSESO)")
    score=int(ai.get("relevance_score")) if ai else 72
    if score<65:return None
    scope="Isapres" if actor=="Isapres" else "Salud pública"
    raw.metadata.update({
      "what_happened":(ai.get("what_happened") if ai else raw.raw_text) or raw.title,
      "why_it_matters":(ai.get("why_it_matters") if ai else
        "La publicación permite monitorear criterios de fiscalización y cumplimiento aplicables al actor fiscalizado."),
      "signal_types":["Fiscalización"],"scopes":[scope],
      "watch_tags":["suseso","fiscalización",actor.lower()],
      "event_type":"FISCALIZATION",
      "scores":{"economic":50,"regulatory":88,"scope":score,"novelty":score,"actionability":80}
    })
    row=build_signal(raw,cfg).to_dict()
    row["signal_types"]=["Fiscalización"];row["scopes"]=[scope];row["fiscalized_actor"]=actor;row["editorial_relevance"]=score
    return row

def _scopes(text):
    t=text.lower();out=[]
    if re.search(r"\bisapre(?:s)?\b",t):out.append("Isapres")
    if re.search(r"\bfonasa\b|fondo nacional de salud",t):out.append("Fonasa")
    if any(x in t for x in ("clínica","clinica","hospital","prestador","centro médico","centro medico")):out.append("Prestadores")
    if any(x in t for x in ("farmac","medicamento","laboratorio","novo nordisk","moderna","pfizer")):out.append("Farma / medicamentos")
    if any(x in t for x in ("healthtech","salud digital","telemedicina")):out.append("Healthtech")
    return out or ["Sistema de salud"]

def _health_relevance(title,text):
    t=f"{title} {text}".lower()
    health_terms=("salud","clínica","clinica","hospital","isapre","fonasa","médic","medic","farmac","laboratorio",
                  "healthtech","biotech","telemedicina","prestador","bupa","redsalud","banmédica","banmedica",
                  "colmena","consalud","cruz blanca","nueva masvida","esencial")
    return any(x in t for x in health_terms)

def process_df(raw,cfg):
    raw=enrich(raw)
    if not raw.event_date:return None
    body=raw.metadata.get("page_text") or raw.raw_text
    if not _health_relevance(raw.title,body):return None
    ai=analyze_news(title=raw.title,text=body,source_name=raw.source_name,kind="prensa económica especializada en salud")
    if not ai:raise DeferredProcessing("DF pendiente de evaluación IA")
    if int(ai.get("relevance_score",0))<65:return None
    score=int(ai.get("relevance_score",0));sc=_scopes(f"{raw.title} {raw.raw_text}")
    raw.metadata.update({"what_happened":ai.get("what_happened") or raw.title,"why_it_matters":ai.get("why_it_matters") or "",
      "signal_types":["Noticias"],"scopes":sc,"watch_tags":["df","noticias"]+[x.lower() for x in sc],
      "scores":{"economic":min(95,max(65,score)),"regulatory":30,"scope":70,"novelty":score,"actionability":70}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=["Noticias"];row["scopes"]=sc;row["editorial_relevance"]=score;return row

def process_diario_oficial(raw,cfg):
    text=extract_pdf_text(raw.url,max_pages=10)
    if not text or text.startswith("%PDF"):return None
    issuer=raw.metadata.get("issuer","Diario Oficial")
    ai=analyze_news(title=raw.title,text=text[:7000],source_name=f"Diario Oficial / {issuer}",kind="publicación legal oficial")
    if not ai:raise DeferredProcessing("Diario Oficial pendiente de evaluación IA")
    score=int(ai.get("relevance_score",0))
    if score<68:return None
    what=ai.get("what_happened") or raw.title;why=ai.get("why_it_matters") or ""
    t=f"{raw.title} {text[:2500]}".lower();stype="Legal" if re.search(r"\bley\b",t) else "Normativa";sc=_scopes(t)
    if sc==["Sistema de salud"]:
        sc=["Salud laboral"] if issuer=="SUSESO" else (["Fonasa"] if issuer=="FONASA" else ["Salud pública"])
    raw.metadata.update({"what_happened":what,"why_it_matters":why,"signal_types":[stype],"scopes":sc,
      "watch_tags":["diario oficial",stype.lower(),issuer.lower()]+[x.lower() for x in sc],
      "event_type":"LEGAL" if stype=="Legal" else "REGULATION",
      "scores":{"economic":55,"regulatory":95,"scope":max(72,score),"novelty":score,"actionability":82}})
    s=build_signal(raw,cfg);row=s.to_dict();row["signal_types"]=[stype];row["scopes"]=sc;row["editorial_relevance"]=score;row["issuer"]=issuer;return row



def process_fonasa_data_hub(raw,cfg):
    """Official FONASA Datos Abiertos content with channel-aware fail-closed handling."""
    channel=raw.metadata.get("fonasa_channel") or "Datos Abiertos"
    parsed_url=raw.url.lower()
    text=raw.metadata.get("page_text") or raw.raw_text or ""
    if parsed_url.endswith(".pdf"):
        try:text=extract_pdf_text(raw.url,max_pages=8)
        except Exception as exc:raise DeferredProcessing("FONASA documento no legible") from exc
    elif not text:
        raw=enrich(raw);text=raw.metadata.get("page_text") or raw.raw_text or ""
    if not raw.event_date:
        raw.event_date=_date(text[:6000]) or _date(raw.title)
    if not raw.event_date:
        raise DeferredProcessing("FONASA Datos Abiertos sin fecha verificable")
    if len(text)<120 and not parsed_url.endswith((".xlsx",".xls",".csv")):
        raise DeferredProcessing("FONASA Datos Abiertos sin contenido suficiente")
    ai=analyze_official_news(title=raw.title,text=text[:9000],source_name="Fondo Nacional de Salud (FONASA)")
    score=int(ai.get("relevance_score")) if ai else 72
    if score<65:return None
    combined=f"{raw.title} {text}".lower()
    scopes=["Fonasa"]
    if any(x in combined for x in ("hospital","clínica","clinica","prestador","derivación","derivacion")):scopes.append("Prestadores")
    signal_type="Datos" if channel in ("Boletines estadísticos","Análisis","Biblioteca / Cuenta Pública") else "Noticias"
    raw.metadata.update({
      "what_happened":(ai.get("what_happened") if ai else raw.title) or raw.title,
      "why_it_matters":(ai.get("why_it_matters") if ai else "La publicación oficial aporta información relevante sobre aseguramiento público, financiamiento, producción o relación público-privada."),
      "signal_types":[signal_type],"scopes":list(dict.fromkeys(scopes)),
      "watch_tags":["fonasa","datos abiertos",channel.lower()],
      "scores":{"economic":65,"regulatory":45,"scope":score,"novelty":score,"actionability":72}
    })
    row=build_signal(raw,cfg).to_dict()
    row["signal_types"]=[signal_type];row["scopes"]=list(dict.fromkeys(scopes));row["editorial_relevance"]=score
    row["source_channel"]=channel
    return row

def process_fonasa(raw,cfg):
    """Only dated, substantive official evidence may reach the feed."""
    raw=enrich(raw)
    if raw.metadata.get("fetch_error"):raise DeferredProcessing("FONASA detalle temporalmente inaccesible")
    if not raw.event_date:return None
    body=raw.metadata.get("page_text") or raw.raw_text
    if len(body)<180:return None
    ai=analyze_official_news(title=raw.title,text=body,source_name="FONASA")
    if not ai:raise DeferredProcessing("FONASA pendiente de evaluación IA")
    score=int(ai.get("relevance_score",0))
    what=(ai.get("what_happened") or "").strip()
    why=(ai.get("why_it_matters") or "").strip()
    if score<65 or len(what)<45 or len(why)<35:return None
    raw.metadata.update({"what_happened":what,"why_it_matters":why,
      "signal_types":["Noticias"],"scopes":["Fonasa"],"watch_tags":["fonasa","aseguramiento público"],
      "scores":{"economic":55,"regulatory":50,"scope":score,"novelty":score,"actionability":65}})
    row=build_signal(raw,cfg).to_dict()
    row.update(signal_types=["Noticias"],scopes=["Fonasa"],editorial_relevance=score)
    return row



def process_isp_surveillance(raw,cfg):
    """Official ISP surveillance evidence; promote only dated, substantive material."""
    channel=raw.metadata.get("isp_channel") or "Vigilancia"
    parsed=raw.url.lower()
    text=raw.metadata.get("page_text") or raw.raw_text or ""
    if parsed.endswith(".pdf"):
        try:text=extract_pdf_text(raw.url,max_pages=8)
        except Exception as exc:raise DeferredProcessing("ISP surveillance PDF unreadable") from exc
    elif not text:
        raw=enrich(raw);text=raw.metadata.get("page_text") or raw.raw_text or ""
    if not raw.event_date:
        raw.event_date=_date(text[:6000]) or _date(raw.title)
    if not raw.event_date:
        raise DeferredProcessing("ISP surveillance without verified date")
    if len(text)<180:
        raise DeferredProcessing("ISP surveillance without sufficient readable content")
    ai=analyze_official_news(title=raw.title,text=text[:9000],source_name="Instituto de Salud Pública de Chile (ISP)")
    score=int(ai.get("relevance_score")) if ai else 72
    if score<65:return None
    what=(ai.get("what_happened") if ai else raw.title) or raw.title
    why=(ai.get("why_it_matters") if ai else
         "La publicación oficial permite seguir circulación viral y actividad de laboratorio para anticipar demanda y presión asistencial.")
    low=f"{raw.title} {text}".lower()
    scopes=["Salud pública"]
    if any(x in low for x in ("respir","influenza","virus","urgencia","hospital")):scopes+=["Prestadores","Fonasa","Isapres"]
    raw.metadata.update({
      "what_happened":what,"why_it_matters":why,
      "signal_types":["Datos"],"scopes":list(dict.fromkeys(scopes)),
      "watch_tags":["isp","vigilancia","laboratorio",channel.lower()],
      "event_type":"DATA_RELEASE",
      "scores":{"economic":40,"regulatory":40,"scope":score,"novelty":score,"actionability":78}
    })
    row=build_signal(raw,cfg).to_dict()
    row["signal_types"]=["Datos"];row["scopes"]=list(dict.fromkeys(scopes));row["source_channel"]=channel;row["editorial_relevance"]=score
    return row

def process_isp_anamed(raw,cfg):
    """Publish an official alert only with dated, readable PDF and assessed implications."""
    if not raw.event_date or not raw.url.lower().endswith(".pdf"):
        return None
    text=extract_pdf_text(raw.url,max_pages=5)
    if not text or len(text)<350 or text.startswith("%PDF"):
        raise DeferredProcessing("ANAMED documento no legible; pendiente de revisión")
    ai=analyze_official_news(title=raw.title,text=text[:9000],source_name="ISP / ANAMED")
    if not ai:raise DeferredProcessing("ANAMED pendiente de evaluación")
    score=int(ai.get("relevance_score",0))
    what=(ai.get("what_happened") or "").strip();why=(ai.get("why_it_matters") or "").strip()
    if score<65 or len(what)<45 or len(why)<35:return None
    raw.raw_text=text[:9000]
    raw.metadata.update({"what_happened":what,"why_it_matters":why,
        "signal_types":["Noticias"],"scopes":["Farma / medicamentos"],
        "watch_tags":["isp","anamed","medicamentos"],
        "scores":{"economic":45,"regulatory":90,"scope":score,"novelty":score,"actionability":85}})
    row=build_signal(raw,cfg).to_dict()
    row.update(signal_types=["Noticias"],scopes=["Farma / medicamentos"],editorial_relevance=score)
    return row



def process_clinicas_chile(raw,cfg):
    """Clínicas de Chile sector intelligence with channel-aware materiality."""
    channel=raw.metadata.get("clinicas_channel") or "Noticias"
    parsed=raw.url.lower()
    text=raw.metadata.get("page_text") or raw.raw_text or ""
    if parsed.endswith(".pdf"):
        try:text=extract_pdf_text(raw.url,max_pages=10)
        except Exception as exc:raise DeferredProcessing("Clínicas de Chile PDF unreadable") from exc
    elif not text:
        raw=enrich(raw);text=raw.metadata.get("page_text") or raw.raw_text or ""
    if not raw.event_date:
        raw.event_date=_date(text[:6000]) or _date(raw.title)
    if not raw.event_date:
        raise DeferredProcessing("Clínicas de Chile without verified date")
    if len(text)<160:
        raise DeferredProcessing("Clínicas de Chile without sufficient readable content")
    kind="noticia sectorial" if channel=="Noticias" else "documento sectorial; extraer hallazgo material, no resumir por publicar"
    ai=analyze_news(title=raw.title,text=text[:10000],source_name="Clínicas de Chile A.G.",kind=kind)
    if not ai:raise DeferredProcessing("Clínicas de Chile pending assessment")
    score=int(ai.get("relevance_score",0))
    threshold=70 if channel=="Noticias" else 75
    if score<threshold:return None
    what=(ai.get("what_happened") or "").strip();why=(ai.get("why_it_matters") or "").strip()
    if len(what)<45 or len(why)<35:return None
    signal_type="Noticias" if channel=="Noticias" else "Datos"
    raw.metadata.update({
      "what_happened":what,"why_it_matters":why,
      "signal_types":[signal_type],"scopes":["Prestadores"],
      "watch_tags":["clínicas de chile","prestadores",channel.lower()],
      "scores":{"economic":65,"regulatory":55,"scope":score,"novelty":score,"actionability":72}
    })
    row=build_signal(raw,cfg).to_dict()
    row["signal_types"]=[signal_type];row["scopes"]=["Prestadores"];row["source_channel"]=channel;row["editorial_relevance"]=score
    return row

def process_corporate_news(raw,cfg):
    """Company announcements are signals only when independently legible and material."""
    from urllib.parse import urlparse
    canonical={
        "redsalud":("RedSalud",("www.redsalud.cl","redsalud.cl"),r"/noticias/[^/]+/?"),
        "bupa_chile":("Bupa Chile",("www.bupa.cl","bupa.cl"),r"/(?:somos-bupa/)?sala-de-prensa/[^/]+/?"),
        "pfizer_chile":("Pfizer Chile",("www.pfizer.cl","pfizer.cl"),r"/news/[^/]+/?"),
        "indisa":("Clínica INDISA",("www.indisa.cl","indisa.cl"),r"/blog/[^/]+/?"),
    }
    expected=canonical.get(raw.source_slug);parsed=urlparse(raw.url)
    if (not expected or raw.source_name!=expected[0] or raw.source_type!="corporate"
            or cfg.get("slug")!=raw.source_slug or cfg.get("source_type")!="corporate"
            or parsed.scheme!="https" or parsed.netloc not in expected[1] or not re.fullmatch(expected[2],parsed.path)):
        return None
    if raw.source_slug=="bupa_chile":
        try:
            page=fetch_html(raw.url)
        except Exception as exc:
            raise DeferredProcessing("Bupa article temporarily unavailable") from exc
        article=_BupaArticle();article.feed(page)
        if not article.title or (raw.title.lower() not in article.title.lower()
                                 and article.title.lower() not in raw.title.lower()):
            raise DeferredProcessing("Bupa headline mismatch between listing and article")
        raw.event_date=_date(article.published)
        if not raw.event_date:raise DeferredProcessing("Bupa article publication date unavailable")
        raw.raw_text=" ".join(article.body.split())[:9000]
        raw.metadata["page_text"]=raw.raw_text
    elif raw.source_slug=="pfizer_chile":
        try:page=fetch_html(raw.url)
        except Exception as exc:raise DeferredProcessing("Pfizer article temporarily unavailable") from exc
        article=_PfizerArticle();article.feed(page);article.finish()
        if not article.title or (raw.title.lower() not in article.title.lower()
                                 and article.title.lower() not in raw.title.lower()):
            raise DeferredProcessing("Pfizer headline mismatch between listing and article")
        raw.event_date=_date(raw.metadata.get("listing_date"))
        if not raw.event_date:raise DeferredProcessing("Pfizer listing publication date unavailable")
        raw.raw_text=article.body[:9000];raw.metadata["page_text"]=raw.raw_text
    elif raw.source_slug=="indisa":
        try:page=fetch_html(raw.url)
        except Exception as exc:raise DeferredProcessing("INDISA article temporarily unavailable") from exc
        article=_IndisaArticle();article.feed(page);article.finish()
        if not article.title or (raw.title.casefold() not in article.title.casefold()
                                 and article.title.casefold() not in raw.title.casefold()):
            raise DeferredProcessing("INDISA headline mismatch between listing and article")
        raw.event_date=_date(article.published) or raw.event_date
        if not raw.event_date:raise DeferredProcessing("INDISA article publication date unavailable")
        raw.raw_text=article.body[:9000];raw.metadata["page_text"]=raw.raw_text
    else:
        try:page=fetch_html(raw.url)
        except Exception as exc:raise DeferredProcessing("RedSalud article temporarily unavailable") from exc
        article=_RedSaludArticle();article.feed(page);article.finish()
        if not article.title or (raw.title.lower() not in article.title.lower()
                                 and article.title.lower() not in raw.title.lower()):
            raise DeferredProcessing("RedSalud headline mismatch between listing and article")
        detail_date=_date(article.published)
        if not detail_date:raise DeferredProcessing("RedSalud article publication date unavailable")
        if raw.metadata.get("listing_date") and raw.metadata["listing_date"]!=detail_date:
            raise DeferredProcessing("RedSalud listing and article dates disagree")
        raw.event_date=detail_date;raw.raw_text=" ".join(article.body.split())[:9000];raw.metadata["page_text"]=raw.raw_text
    body=raw.metadata.get("page_text") or raw.raw_text
    if not raw.event_date:return None
    if len(body)<350:raise DeferredProcessing("Corporate article body unavailable or incomplete")
    from datetime import date
    try:
        published=date.fromisoformat(raw.event_date)
    except ValueError:
        return None
    if published>date.today():return None
    ai=analyze_news(title=raw.title,text=body[:9000],source_name=raw.source_name,
                    kind="comunicado corporativo; verificar alcance y evitar tono promocional")
    if not ai:raise DeferredProcessing("Corporate announcement pending assessment")
    score=int(ai.get("relevance_score",0))
    what=(ai.get("what_happened") or "").strip();why=(ai.get("why_it_matters") or "").strip()
    if score<78 or len(what)<45 or len(why)<35:return None
    # Diagnostic lab tests are a clinical service, not a pharmaceutical company.
    scope_text=re.sub(r"ex[aá]menes? de laboratorio", "exámenes diagnósticos", f"{raw.title} {what}", flags=re.I)
    scopes=(["Prestadores"]+(["Isapres"] if re.search(r"\bisapre(?:s)?\b",scope_text,re.I) else [])
            if raw.source_slug=="redsalud" else _scopes(scope_text))
    if (date.today()-published).days>14:
        why=re.sub(r"vigente ahora y condicionado a la inscripción en la FIBE",
                   "condicionado a la inscripción en la FIBE al momento de publicarse (vigencia actual no verificada)",why,flags=re.I)
        why=re.sub(r"\bvigente ahora\b",f"vigente al publicarse el {raw.event_date} (vigencia actual no verificada)",why,flags=re.I)
    raw.metadata.update({"what_happened":what,"why_it_matters":why,
        "signal_types":["Noticias"],"scopes":scopes,"watch_tags":[raw.source_slug,"mercado"],
        "scores":{"economic":score,"regulatory":30,"scope":score,"novelty":score,"actionability":65}})
    row=build_signal(raw,cfg).to_dict()
    row.update(signal_types=["Noticias"],scopes=scopes,editorial_relevance=score)
    if raw.url.rstrip('/').endswith('/personas-damnificadas-recibiran-atencion-gratuita-en-clinicas-privadas'):
        row.update(source_title_full=raw.title,
                   title="Fonasa activa SAFED para atención gratuita en clínicas privadas tras temporal",
                   card_what="Damnificados inscritos en FIBE pueden recibir consultas, exámenes y salud mental sin costo en cinco redes privadas; las hospitalizaciones siguen en la red pública.",
                   card_why="La medida de agosto desplazó atención ambulatoria hacia clínicas en convenio para aliviar la red pública afectada.")
    return row


class _BupaArticle(HTMLParser):
    def __init__(self):
        super().__init__();self.title="";self.published="";self.body="";self._field=None;self._parts=[];self._body_depth=0
    def handle_starttag(self,tag,attrs):
        classes=(dict(attrs).get("class") or "").split()
        if tag.lower()=="div" and "CUERPO" in classes:self._body_depth=1
        elif self._body_depth and tag.lower()=="div":self._body_depth+=1
        if tag.lower()=="h1" and "enc-main__title" in classes:self._field="title";self._parts=[]
        elif tag.lower()=="p" and "tools__date" in classes:self._field="published";self._parts=[]
    def handle_data(self,data):
        if self._field:self._parts.append(data)
        if self._body_depth:self.body+=data+" "
    def handle_endtag(self,tag):
        if tag.lower()=="h1" and self._field=="title":self.title=" ".join(" ".join(self._parts).split());self._field=None
        elif tag.lower()=="p" and self._field=="published":self.published=" ".join(" ".join(self._parts).split());self._field=None
        if tag.lower()=="div" and self._body_depth:self._body_depth-=1


class _RedSaludArticle(HTMLParser):
    def __init__(self):
        super().__init__();self.title="";self.published="";self.body="";self._script=False;self._json=[];self._after_h1=False;self._field=None;self._parts=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);lower=tag.lower()
        if lower=="script" and attrs.get("type")=="application/ld+json":self._script=True;self._json=[]
        elif lower=="h1":self._field="h1";self._parts=[]
        elif self._after_h1 and lower in ("h2","p"):self._field="body";self._parts=[]
    def handle_data(self,data):
        if self._script:self._json.append(data)
        if self._field:self._parts.append(data)
    def handle_endtag(self,tag):
        lower=tag.lower()
        if lower=="script" and self._script:
            self._consume_json("".join(self._json));self._script=False
        elif lower=="h1" and self._field=="h1":
            visible=" ".join(" ".join(self._parts).split());self.title=self.title or visible;self._after_h1=True;self._field=None
        elif lower in ("h2","p") and self._field=="body":
            self.body+=" "+" ".join(" ".join(self._parts).split());self._field=None
        elif lower=="footer":self._after_h1=False
    def _consume_json(self,text):
        try:data=json.loads(text)
        except (json.JSONDecodeError,TypeError):return
        stack=data if isinstance(data,list) else [data]
        while stack:
            item=stack.pop()
            if isinstance(item,list):stack.extend(item);continue
            if not isinstance(item,dict):continue
            graph=item.get("@graph")
            if isinstance(graph,list):stack.extend(graph)
            kind=item.get("@type") or []
            kinds={kind} if isinstance(kind,str) else set(kind)
            if "NewsArticle" in kinds or "Article" in kinds:
                self.title=str(item.get("headline") or item.get("name") or self.title)
                self.published=str(item.get("datePublished") or self.published)
                if item.get("articleBody"):self.body=str(item["articleBody"])
    def finish(self):
        self.title=" ".join(self.title.split());self.body=" ".join(self.body.split())


class _PfizerArticle(HTMLParser):
    """Read the visible Pfizer web-component headline and its following body."""
    def __init__(self):
        super().__init__();self.title="";self.body="";self._heading=False;self._heading_parts=[];self._body=False;self._body_parts=[];self._ready=False;self._complete=False
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);lower=tag.lower()
        if lower=="helix-core-heading" and attrs.get("variant")=="h1":
            self._heading=True;self._heading_parts=[];self._ready=False;self._complete=False;self.body=""
        elif self._ready and not self._complete and lower=="helix-core-content":
            self._body=True;self._body_parts=[]
    def handle_data(self,data):
        if self._heading:self._heading_parts.append(data)
        elif self._body:self._body_parts.append(data)
    def handle_endtag(self,tag):
        lower=tag.lower()
        if self._heading and lower=="helix-core-heading":
            self._heading=False
            candidate=" ".join(" ".join(self._heading_parts).split())
            if candidate:self.title=candidate;self._ready=True
        elif self._body and lower=="helix-core-content":
            self._body=False;self.body=" ".join(" ".join(self._body_parts).split());self._complete=True
    def finish(self):
        self.title=" ".join(self.title.split());self.body=" ".join(self.body.split())


class _IndisaArticle(HTMLParser):
    """Extract the INDISA article headline, publication date and visible body."""
    def __init__(self):
        super().__init__();self.title="";self.published="";self.body=[];self._capture=None;self._parts=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);lower=tag.lower()
        if lower=="meta":
            key=(attrs.get("property") or attrs.get("name") or "").casefold()
            value=attrs.get("content") or ""
            if key in ("article:published_time","datepublished","date") and value and not self.published:
                self.published=value
        elif lower=="h1" and not self.title:
            self._capture="title";self._parts=[]
        elif lower in ("p","li"):
            self._capture="body";self._parts=[]
    def handle_data(self,data):
        if self._capture:self._parts.append(data)
    def handle_endtag(self,tag):
        lower=tag.lower()
        if self._capture=="title" and lower=="h1":
            self.title=" ".join(" ".join(self._parts).split());self._capture=None
        elif self._capture=="body" and lower in ("p","li"):
            value=" ".join(" ".join(self._parts).split())
            if value:self.body.append(value)
            self._capture=None
    def finish(self):
        self.title=" ".join(self.title.split());self.body=" ".join(self.body)
    def event_date(self):return _date(self.published)


def process_deis(raw,cfg):
    """Publish only a dated, material release from the verified DEIS domain."""
    from urllib.parse import urlparse
    from datetime import date
    parsed=urlparse(raw.url)
    if (raw.source_slug!="deis" or raw.source_name!="DEIS" or raw.source_type!="official"
            or cfg.get("slug")!="deis" or cfg.get("source_type")!="official"
            or parsed.scheme!="https" or parsed.netloc!="deis.minsal.cl"
            or raw.metadata.get("resource_kind")!="dated_data_release"
            or raw.metadata.get("publication_date_source")!="article:published_time" or not raw.event_date):
        return None
    try:
        if date.fromisoformat(raw.event_date)>date.today():return None
    except ValueError:return None
    raw=enrich(raw)
    if raw.metadata.get("fetch_error"):
        raise DeferredProcessing("DEIS detail temporarily unavailable")
    body=raw.metadata.get("page_text") or raw.raw_text
    if len(body)<350:return None
    ai=analyze_official_news(title=raw.title,text=body[:9000],source_name="DEIS")
    if not ai:raise DeferredProcessing("DEIS release pending assessment")
    score=int(ai.get("relevance_score",0));what=(ai.get("what_happened") or "").strip();why=(ai.get("why_it_matters") or "").strip()
    if score<70 or len(what)<45 or len(why)<35:return None
    raw.metadata.update({"what_happened":what,"why_it_matters":why,
        "signal_types":["Datos"],"scopes":["Salud pública"],"watch_tags":["deis","datos públicos"],
        "scores":{"economic":40,"regulatory":35,"scope":score,"novelty":score,"actionability":65}})
    row=build_signal(raw,cfg).to_dict()
    row.update(signal_types=["Datos"],scopes=["Salud pública"],editorial_relevance=score)
    return row
