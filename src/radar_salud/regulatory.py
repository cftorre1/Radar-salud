from __future__ import annotations
import re
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urljoin
from .models import RawItem
from .scouts import fetch_html

SIS_INDEX_PATH="data/state/sis_normative_index.json"
MONTHS={"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06","julio":"07","agosto":"08","septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"}

def _date(text:str)->Optional[str]:
    m=re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})",text)
    if m:return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m=re.search(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(20\d{2})",text,re.I)
    if m and m.group(2).lower() in MONTHS:return f"{m.group(3)}-{MONTHS[m.group(2).lower()]}-{int(m.group(1)):02d}"
    return None

_EMISSION_RE=re.compile(r"(?:Fecha\s+(?:de\s+)?)?emisi[oó]n\s*:\s*([^|]{1,40})",re.I)

def _emission_date(*texts:str)->Optional[str]:
    """Emission date stated by the regulator itself ("Circular IF/N°538 - Emisión: 26/10/2026",
    "Fecha de emisión: 26 de octubre de 2026"). The listing's own date column is the date the
    act was posted (SIS posted IF/N°538-541 together on 5-nov-2026) and must not replace it."""
    for text in texts:
        m=_EMISSION_RE.search(str(text or ""))
        found=_date(m.group(1)) if m else None
        if found:return found
    return None

def listing_event_date(title:str,summary:str,row_text:str)->Optional[str]:
    """Official emission date (title, then subject) wins over the first date found in the row."""
    return _emission_date(title,summary) or _date(row_text)

_IDENTITY_RE=re.compile(r"(oficio\s+circular|ordinario\s+circular|circular|oficio|resoluci[oó]n(?:\s+exenta)?|decreto(?:\s+exento)?)"
    r"\s*(?:(IF|IP|SS|RA)\s*/?)?\s*(?:N\s*[°º.]?\s*)?(\d{1,3}(?:\.\d{3})+|\d+)",re.I)

def act_identity(title:str)->Optional[str]:
    """'Resolución Exenta IF/N°12392 - Emisión: 23/10/2026' -> 'resolucion exenta|if|12392' (dedupe key)."""
    m=_IDENTITY_RE.search(" ".join(str(title or "").split()))
    if not m:return None
    kind=" ".join(m.group(1).lower().replace("ó","o").split())
    number=re.sub(r"\D","",m.group(3))
    return f"{kind}|{(m.group(2) or '').lower()}|{number}"

class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self._row=None;self._cell=None;self._href=None;self._anchor=[]
    def handle_starttag(self,tag,attrs):
        tag=tag.lower()
        if tag=="tr":self._row=[]
        elif tag in ("td","th") and self._row is not None:self._cell={"text":[],"links":[]}
        elif tag=="a" and self._cell is not None:self._href=dict(attrs).get("href");self._anchor=[]
    def handle_data(self,data):
        if self._cell is not None:
            t=" ".join(data.split())
            if t:self._cell["text"].append(t)
        if self._href is not None:self._anchor.append(data)
    def handle_endtag(self,tag):
        tag=tag.lower()
        if tag=="a" and self._href is not None and self._cell is not None:
            self._cell["links"].append((self._href," ".join("".join(self._anchor).split())));self._href=None;self._anchor=[]
        elif tag in ("td","th") and self._cell is not None and self._row is not None:
            self._cell["text"]=" ".join(self._cell["text"]).strip();self._row.append(self._cell);self._cell=None
        elif tag=="tr" and self._row is not None:
            if self._row:self.rows.append(self._row)
            self._row=None

def merge_sis_index(index_path,listing_index):
    """Merge this run's listing identities into the persisted index; a corrupt index is
    logged and rebuilt from this run, never a discovery failure."""
    import json
    from datetime import datetime, timezone
    from .pending_queue import atomic_json
    try:
        previous=json.loads(index_path.read_text()) if index_path.exists() else {}
        acts=dict(previous.get("acts",{}))
    except (OSError,ValueError,AttributeError,TypeError) as exc:
        print("SIS normative index unreadable; rebuilding:",type(exc).__name__)
        acts={}
    acts.update(listing_index)
    atomic_json(index_path,{"captured_at":datetime.now(timezone.utc).isoformat(),
        "source":"Superintendencia de Salud · Instrucciones dictadas (listados oficiales)","acts":acts})
    return acts

def official_sis_url(url):
    from urllib.parse import urlsplit
    parts=urlsplit(str(url or ""));host=(parts.hostname or "").lower()
    return parts.scheme=="https" and (host=="superdesalud.gob.cl" or host.endswith(".superdesalud.gob.cl"))

def record_listing_identity(index,title,url,event_date,subject,listing_url):
    """Official identity -> URL, read from the regulator's own listing (no constructed URLs).
    Used to link a late resolution to the circular it acts on when that circular is not in history."""
    from .normative_relations import clean_subject, target_key
    key=target_key(title or "")
    if not key or not official_sis_url(url):return
    if not key.startswith(("circular-","oficio-circular-")):return
    current=index.get(key)
    record={"id":" ".join(str(title).split()),"url":url,"event_date":event_date,
            "official_subject":clean_subject(" ".join(str(subject or "").split())[:400]),"listing_url":listing_url}
    if current is None or (event_date or "")>(current.get("event_date") or ""):index[key]=record

class SuperintendenciaNormativaScout:
    SOURCE_SLUG="superintendencia_normativa";SOURCE_NAME="Superintendencia de Salud";SOURCE_TYPE="official"
    PAGES=[
      ("Para ISAPREs y FONASA","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-aseguradoras-4097/","Isapres / Fonasa"),
      ("Para Prestadores Institucionales","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-prestadores-institucionales-6256/","Prestadores"),
      ("Para Entidades Acreditadoras","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-entidades-acreditadoras-6266/","Prestadores"),
      ("Para Entidades Certificadoras","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-entidades-certificadoras-6271/","Prestadores"),
      ("Para Prestadores Individuales","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-prestadores-individuales-6261/","Prestadores"),
      ("Para otros destinatarios","https://www.superdesalud.gob.cl/tax-instrucciones-dictadas-por-la-superintendencia/para-otros-destinatarios-7926/","Sistema de salud"),
    ]
    # Dirección 9-nov-2026 (punto B): the SIS has no /normativa/ archive nor WordPress REST API (probes
    # 42710009565, 42710380828, 42711886047). Every normative type is listed in taxonomy pages; the six
    # "Instrucciones dictadas" parents above already aggregate circulares, oficios, oficios circulares and
    # resoluciones. These listings are the remaining normative ones. Live only: acts issued in the last
    # LIVE_ONLY_DAYS days, never a backfill; acts already listed above are not captured twice.
    EXTRA_PAGES=[
      ("Otras resoluciones","https://www.superdesalud.gob.cl/tax-otros-actos-de-la-superintendencia/otras-resoluciones-5112/","Sistema de salud"),
      ("Marco normativo: resoluciones","https://www.superdesalud.gob.cl/tax-marco-normativo/resoluciones-3015/","Sistema de salud"),
      ("Marco normativo: decretos","https://www.superdesalud.gob.cl/tax-marco-normativo/decretos-3016/","Sistema de salud"),
    ]
    LIVE_ONLY_DAYS=14
    # Internal administration published next to normative acts (personnel, purchasing, lobby registry...).
    EXTRA_NOISE=("subrogancia","sujetos pasivos","lobby","delega facultad","encomendación de funciones",
                 "encomendacion de funciones","administradores de sistemas","comité de integridad","comite de integridad",
                 "costo directo de reproducción","costo directo de reproduccion","dotación","dotacion","nombra en calidad",
                 "llamado a concurso","encasillamiento","convenio de colaboración","convenio de colaboracion",
                 "reserva o secreto","declaración de patrimonio","declaracion de patrimonio","horas extraordinarias",
                 "cometido","feriado","teletrabajo","compra","adquisición","adquisicion","contratación","contratacion",
                 "trato directo","adjudica","bases de licitación","bases de licitacion")
    TITLE_RE=re.compile(r"(Circular|Oficio(?:\s+Circular)?|Ordinario(?:\s+Circular)?|Resoluci[oó]n(?:\s+Exenta)?|Decreto(?:\s+Exento)?)",re.I)
    ADMIN_NOISE=("licitación","licitacion","comisión evaluadora","comision evaluadora","aseo","fumigación","fumigacion",
                 "mantenciones","mantenimiento","licencias hcl","tableau","data center","monitoreo de medios",
                 "concurso de personal","designa miembros")
    def discover(self)->List[RawItem]:
        out=[];seen=set();self.listing_index={};self.discovery_errors=[];self.extra_skipped={}
        from datetime import date, datetime, timedelta
        from zoneinfo import ZoneInfo
        today=getattr(self,"today",None) or datetime.now(ZoneInfo("America/Santiago")).date()
        pages=[(n,u,s,False) for n,u,s in self.PAGES]+[(n,u,s,True) for n,u,s in self.EXTRA_PAGES]
        known_urls=set();known_ids=set()
        def skip(reason):self.extra_skipped[reason]=self.extra_skipped.get(reason,0)+1
        for page_name,page_url,scope,live_only in pages:
            try:html=fetch_html(page_url)
            except Exception as e:
                print("SuperSalud regulatory fetch:",page_name,e);self.discovery_errors.append(f"{page_name}: {type(e).__name__}");continue
            p=_TableParser();p.feed(html)
            for row in p.rows:
                row_text=" ".join(c["text"] for c in row if c.get("text"))
                if (page_name=="Para otros destinatarios" or live_only) and any(x in row_text.lower() for x in self.ADMIN_NOISE):
                    if live_only:skip("admin_noise")
                    continue
                if live_only and any(x in row_text.lower() for x in self.EXTRA_NOISE):skip("admin_noise");continue
                if not self.TITLE_RE.search(row_text):continue
                event_date=_date(row_text);title=None;detail=None;pdf=None
                for c in row:
                    for href,label in c.get("links",[]):
                        absolute=urljoin(page_url,href)
                        if self.TITLE_RE.search(label) and "descargar" not in label.lower():
                            title=label;detail=absolute
                        if ".pdf" in absolute.lower() or "pdf" in label.lower():pdf=absolute
                if not title:
                    m=re.search(r"((?:Resoluci[oó]n(?:\s+Exenta)?|Oficio(?:\s+Circular)?|Ordinario(?:\s+Circular)?|Circular)\s+[A-Z/°Nºn°\-\d\s]+)",row_text,re.I)
                    if m:title=" ".join(m.group(1).split())
                if not title:continue
                url=detail or pdf or page_url;key=(title,url,scope)
                if key in seen:continue
                seen.add(key)
                summary=row[-1]["text"] if row else row_text
                listing_date=event_date
                event_date=listing_event_date(title,summary,row_text)
                identity=act_identity(title)
                if live_only:
                    if url.rstrip("/") in known_urls or (identity and identity in known_ids):skip("already_listed");continue
                    try:issued=date.fromisoformat(str(event_date))
                    except ValueError:skip("undated");continue
                    if not (today-timedelta(days=self.LIVE_ONLY_DAYS)<=issued<=today):skip("outside_live_window");continue
                known_urls.add(url.rstrip("/"))
                if identity:known_ids.add(identity)
                record_listing_identity(self.listing_index,title,url,event_date,summary,page_url)
                if len(summary)<15:summary=row_text
                out.append(RawItem(self.SOURCE_SLUG,title,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                    event_date=event_date,raw_text=summary,
                    metadata={"listing_url":page_url,"listing_name":page_name,"scope":scope,"pdf_url":pdf,
                              "listing_family":"otros_actos_o_marco_normativo" if live_only else "instrucciones_dictadas",
                              "listing_date":listing_date,
                              "event_date_basis":"official_emission" if event_date!=listing_date or _emission_date(title,summary) else "listing",
                              "attachments":[{"url":pdf,"label":"PDF"}] if pdf else []}))
        out.sort(key=lambda x:x.event_date or "",reverse=True)
        return out
